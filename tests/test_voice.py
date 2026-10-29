import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from config.settings import Settings
from tools.voice import VoiceEvent, VoiceService


class FakeRecognizer:
    def __init__(self, _model, _sample_rate):
        self.chunks = []

    def AcceptWaveform(self, data):
        self.chunks.append(data)
        return False

    def FinalResult(self):
        return json.dumps({"text": "abra a calculadora"})


class FakeVosk:
    KaldiRecognizer = FakeRecognizer

    @staticmethod
    def Model(path):
        return {"path": path}


class FakeStream:
    def __init__(self, callback, **_kwargs):
        self.callback = callback

    def __enter__(self):
        self.callback(b"audio temporario", 1, None, None)
        return self

    def __exit__(self, *_args):
        return False


class FakeSoundDevice:
    RawInputStream = FakeStream
    class default:
        device = (-1, 0)

    @staticmethod
    def query_devices():
        return [{"name": "Microfone de teste", "max_input_channels": 1}]


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = Settings(self.root)
        self.events: list[VoiceEvent] = []

    def tearDown(self):
        self.temp.cleanup()

    def _loader(self, name):
        return {"vosk": FakeVosk, "sounddevice": FakeSoundDevice}[name]

    def _wait_for(self, kind: str, timeout: float = 1.5) -> VoiceEvent:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for event in self.events:
                if event.kind == kind:
                    return event
            time.sleep(0.01)
        self.fail(f"Evento de voz não recebido: {kind}")

    def test_recognition_requires_explicit_model_path(self):
        self.settings.set("voice_input_enabled", True)
        service = VoiceService(self.settings, self.events.append, self._loader)
        self.assertTrue(service.start_recording())
        event = self._wait_for("error")
        self.assertIn("Configure a pasta do modelo", event.message)
        self.assertFalse(service.recording)

    def test_press_to_talk_returns_transcript_without_audio_file(self):
        model = self.root / "modelo-vosk-pt"; model.mkdir()
        self.settings.set("voice_input_enabled", True)
        self.settings.set("voice_model_path", str(model))
        service = VoiceService(self.settings, self.events.append, self._loader)
        self.assertTrue(service.start_recording())
        self._wait_for("state")
        self.assertTrue(service.stop_recording())
        event = self._wait_for("transcript")
        self.assertEqual(event.message, "abra a calculadora")
        self.assertEqual(list(model.iterdir()), [])

    def test_cancel_discards_transcription(self):
        model = self.root / "modelo-vosk-pt"; model.mkdir()
        self.settings.set("voice_input_enabled", True)
        self.settings.set("voice_model_path", str(model))
        service = VoiceService(self.settings, self.events.append, self._loader)
        service.start_recording(); self._wait_for("state")
        service.stop_recording(cancel=True)
        assert service._recognition_thread is not None
        service._recognition_thread.join(timeout=1)
        self.assertFalse(any(event.kind == "transcript" for event in self.events))
        self.assertEqual(self.events[-1], VoiceEvent("state", "Pronto"))

    def test_missing_optional_dependencies_is_controlled(self):
        self.settings.set("voice_input_enabled", True)
        service = VoiceService(
            self.settings,
            self.events.append,
            lambda _name: (_ for _ in ()).throw(ImportError("ausente")),
        )
        service.start_recording()
        event = self._wait_for("error")
        self.assertIn("requirements-voice.txt", event.message)

    def test_sapi5_synthesis_runs_in_background_when_enabled(self):
        spoken = threading.Event()

        class Engine:
            def setProperty(self, *_args): pass
            def say(self, text): self.text = text
            def runAndWait(self): spoken.set()
            def stop(self): pass

        class FakePyttsx3:
            @staticmethod
            def init(driverName):
                self.assertEqual(driverName, "sapi5")
                return Engine()

        self.settings.set("voice_output_enabled", True)
        service = VoiceService(self.settings, self.events.append, lambda _name: FakePyttsx3)
        self.assertTrue(service.speak("Resposta do James"))
        self.assertTrue(spoken.wait(1))
        service.close()

    def test_synthesis_does_nothing_when_disabled(self):
        service = VoiceService(
            self.settings,
            self.events.append,
            lambda _name: self.fail("Dependência não deveria ser carregada"),
        )
        self.assertFalse(service.speak("Resposta"))


if __name__ == "__main__":
    unittest.main()
