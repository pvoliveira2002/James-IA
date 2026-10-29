from __future__ import annotations

import importlib
import json
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from config.settings import Settings


@dataclass(frozen=True)
class VoiceEvent:
    kind: str
    message: str = ""


class VoiceService:
    """Reconhecimento sob demanda e síntese opcional, sem persistir áudio."""

    def __init__(
        self,
        settings: Settings,
        event_sink: Callable[[VoiceEvent], None],
        module_loader: Callable[[str], Any] = importlib.import_module,
    ):
        self.settings = settings
        self._emit = event_sink
        self._module_loader = module_loader
        self._recording_lock = threading.Lock()
        self._recording = False
        self._stop_event = threading.Event()
        self._cancel_event = threading.Event()
        self._recognition_thread: threading.Thread | None = None
        self._model: Any = None
        self._model_path: Path | None = None
        self._speech_queue: queue.Queue[str | None] = queue.Queue(maxsize=8)
        self._speech_thread: threading.Thread | None = None
        self._closed = False

    @property
    def recording(self) -> bool:
        with self._recording_lock:
            return self._recording

    def start_recording(self) -> bool:
        with self._recording_lock:
            if self._closed or self._recording:
                return False
            self._recording = True
            self._stop_event.clear()
            self._cancel_event.clear()
        self._recognition_thread = threading.Thread(
            target=self._recognize_worker, name="james-voice-recognition", daemon=True
        )
        self._recognition_thread.start()
        return True

    def stop_recording(self, cancel: bool = False) -> bool:
        with self._recording_lock:
            if not self._recording:
                return False
            if cancel:
                self._cancel_event.set()
            self._stop_event.set()
        return True

    def speak(self, text: str) -> bool:
        if self._closed or not self.settings.get("voice_output_enabled", False) or not text.strip():
            return False
        if not self._speech_thread or not self._speech_thread.is_alive():
            self._speech_thread = threading.Thread(
                target=self._speech_worker, name="james-voice-synthesis", daemon=True
            )
            self._speech_thread.start()
        try:
            self._speech_queue.put_nowait(text.strip())
        except queue.Full:
            return False
        return True

    def close(self) -> None:
        self._closed = True
        self.stop_recording(cancel=True)
        try:
            self._speech_queue.put_nowait(None)
        except queue.Full:
            pass

    def _voice_model(self, vosk: Any) -> Any:
        raw_path = str(self.settings.get("voice_model_path", "")).strip()
        if not raw_path:
            raise RuntimeError("Configure a pasta do modelo Vosk em Configurações.")
        path = Path(raw_path).expanduser().resolve()
        if not path.is_dir():
            raise RuntimeError("A pasta configurada para o modelo Vosk não existe.")
        if self._model is None or self._model_path != path:
            self._model = vosk.Model(str(path))
            self._model_path = path
        return self._model

    def _input_device(self, sounddevice: Any) -> int | str | None:
        configured = self.settings.get("voice_input_device")
        if configured not in (None, ""):
            return int(configured) if str(configured).isdigit() else str(configured)
        try:
            default_input = int(sounddevice.default.device[0])
            if default_input >= 0:
                return default_input
        except (AttributeError, IndexError, TypeError, ValueError):
            pass
        try:
            devices = list(sounddevice.query_devices())
        except Exception as exc:
            raise RuntimeError("Não foi possível consultar os microfones do Windows.") from exc
        inputs = [
            (index, device) for index, device in enumerate(devices)
            if int(device.get("max_input_channels", 0)) > 0
        ]
        if not inputs:
            raise RuntimeError("Nenhum microfone disponível no Windows.")
        preferred = next(
            (item for item in inputs if "microf" in str(item[1].get("name", "")).casefold()),
            inputs[0],
        )
        return preferred[0]

    def _sample_rate(self, sounddevice: Any, device: int | str | None) -> int:
        preferred = int(self.settings.get("voice_sample_rate", 16000))
        checker = getattr(sounddevice, "check_input_settings", None)
        if not checker:
            return preferred
        try:
            checker(device=device, channels=1, dtype="int16", samplerate=preferred)
            return preferred
        except Exception:
            try:
                info = sounddevice.query_devices(device, "input")
                fallback = int(float(info["default_samplerate"]))
                checker(device=device, channels=1, dtype="int16", samplerate=fallback)
                return fallback
            except Exception as exc:
                raise RuntimeError("O microfone encontrado não aceita um formato de captura compatível.") from exc

    def _recognize_worker(self) -> None:
        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=32)

        def audio_callback(indata, _frames, _time, status) -> None:
            if status:
                self._emit(VoiceEvent("error", f"Falha de captura do microfone: {status}"))
            try:
                audio_queue.put_nowait(bytes(indata))
            except queue.Full:
                pass

        try:
            if not self.settings.get("voice_input_enabled", False):
                raise RuntimeError("Ative a entrada por voz em Configurações.")
            try:
                vosk = self._module_loader("vosk")
                sounddevice = self._module_loader("sounddevice")
            except (ImportError, OSError) as exc:
                raise RuntimeError(
                    "Dependências de voz indisponíveis. Instale requirements-voice.txt."
                ) from exc
            input_device = self._input_device(sounddevice)
            sample_rate = self._sample_rate(sounddevice, input_device)
            recognizer = vosk.KaldiRecognizer(self._voice_model(vosk), sample_rate)
            recognized_parts: list[str] = []

            def recognize(data: bytes) -> None:
                if recognizer.AcceptWaveform(data):
                    result_method = getattr(recognizer, "Result", None)
                    if result_method:
                        partial = json.loads(result_method() or "{}")
                        text = str(partial.get("text", "")).strip()
                        if text:
                            recognized_parts.append(text)

            stream = sounddevice.RawInputStream(
                device=input_device,
                samplerate=sample_rate,
                blocksize=4000,
                dtype="int16",
                channels=1,
                callback=audio_callback,
            )
            with stream:
                self._emit(VoiceEvent("state", "Ouvindo"))
                while not self._stop_event.is_set():
                    if not getattr(stream, "active", True):
                        raise RuntimeError(
                            "O microfone foi localizado, mas não permaneceu ativo. Verifique a conexão e as permissões do Windows."
                        )
                    try:
                        recognize(audio_queue.get(timeout=0.1))
                    except queue.Empty:
                        continue
                while True:
                    try:
                        recognize(audio_queue.get_nowait())
                    except queue.Empty:
                        break
            if self._cancel_event.is_set():
                self._emit(VoiceEvent("state", "Pronto"))
                return
            result = json.loads(recognizer.FinalResult() or "{}")
            final_text = str(result.get("text", "")).strip()
            if final_text:
                recognized_parts.append(final_text)
            text = " ".join(recognized_parts).strip()
            if not text:
                raise RuntimeError("Nenhuma fala foi reconhecida. Tente novamente mais perto do microfone.")
            self._emit(VoiceEvent("transcript", text))
        except Exception as exc:
            self._emit(VoiceEvent("error", str(exc)))
        finally:
            with self._recording_lock:
                self._recording = False

    def _speech_worker(self) -> None:
        try:
            try:
                pyttsx3 = self._module_loader("pyttsx3")
            except (ImportError, OSError) as exc:
                raise RuntimeError(
                    "Síntese de voz indisponível. Instale requirements-voice.txt."
                ) from exc
            engine = pyttsx3.init(driverName="sapi5")
            engine.setProperty("rate", int(self.settings.get("voice_rate", 175)))
            engine.setProperty("volume", float(self.settings.get("voice_volume", 1.0)))
            while not self._closed:
                text = self._speech_queue.get()
                if text is None:
                    break
                engine.say(text)
                engine.runAndWait()
            engine.stop()
        except Exception as exc:
            self._emit(VoiceEvent("error", str(exc)))

