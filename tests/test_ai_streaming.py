import json
import types
import unittest
from unittest.mock import patch

from ai.ollama import OllamaProvider
from ai.openai_provider import OpenAIProvider


class FakeHTTPResponse:
    def __init__(self, lines): self.lines = lines; self.status = 200
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def __iter__(self): return iter(self.lines)
    def read(self): return b""


class AIStreamingTests(unittest.TestCase):
    def test_ollama_stream_emits_deltas_and_uses_resource_limits(self):
        lines = [
            json.dumps({"message": {"content": "Olá "}}).encode() + b"\n",
            json.dumps({"message": {"content": "Paulo"}, "done": True}).encode() + b"\n",
        ]
        captured = {}
        def open_url(req, timeout):
            captured["payload"] = json.loads(req.data.decode())
            return FakeHTTPResponse(lines)
        provider = OllamaProvider("http://127.0.0.1:11434", "qwen3:1.7b", num_ctx=3072, num_predict=320)
        chunks = []
        with patch("ai.ollama.request.urlopen", side_effect=open_url):
            result = provider.chat_stream([{"role": "user", "content": "Oi"}], "Seja natural", chunks.append)
        self.assertEqual(chunks, ["Olá ", "Paulo"])
        self.assertEqual(result.text, "Olá Paulo")
        self.assertTrue(captured["payload"]["stream"])
        self.assertEqual(captured["payload"]["options"]["num_ctx"], 3072)
        self.assertEqual(captured["payload"]["options"]["num_predict"], 320)
        self.assertEqual(captured["payload"]["options"]["repeat_penalty"], 1.08)

    def test_openai_stream_uses_responses_events_without_storing(self):
        events = [
            types.SimpleNamespace(type="response.output_text.delta", delta="Olá "),
            types.SimpleNamespace(type="response.output_text.delta", delta="Paulo"),
            types.SimpleNamespace(
                type="response.completed",
                response=types.SimpleNamespace(output_text="Olá Paulo", output=[]),
            ),
        ]
        captured = {}

        class FakeResponses:
            def create(self, **kwargs):
                captured.update(kwargs)
                return events

        class FakeOpenAI:
            def __init__(self, **_kwargs):
                self.responses = FakeResponses()

        provider = OpenAIProvider("gpt-test")
        chunks = []
        fake_module = types.SimpleNamespace(OpenAI=FakeOpenAI)
        with patch.object(provider, "status", return_value=(True, "ok")), \
                patch.dict("sys.modules", {"openai": fake_module}):
            result = provider.chat_stream(
                [{"role": "user", "content": "Oi"}], "Seja natural", chunks.append,
            )

        self.assertEqual(chunks, ["Olá ", "Paulo"])
        self.assertEqual(result.text, "Olá Paulo")
        self.assertTrue(captured["stream"])
        self.assertFalse(captured["store"])

    def test_openai_without_explicit_key_stays_unavailable(self):
        provider = OpenAIProvider("gpt-test")
        with patch.dict("os.environ", {}, clear=True):
            available, reason = provider.status()
        self.assertFalse(available)
        self.assertIn("OPENAI_API_KEY", reason)


if __name__ == "__main__": unittest.main()
