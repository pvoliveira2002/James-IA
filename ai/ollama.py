from __future__ import annotations

import json
import logging
from collections.abc import Callable
from urllib import request, error

from ai.base import ProviderResponse


logger = logging.getLogger(__name__)


class OllamaProvider:
    def __init__(self, base_url: str, model: str, timeout: int = 60,
                 num_ctx: int = 4096, num_predict: int = 512):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.num_ctx = max(1024, min(int(num_ctx), 8192))
        self.num_predict = max(64, min(int(num_predict), 1024))

    def available(self) -> bool:
        try:
            with request.urlopen(f"{self.base_url}/api/tags", timeout=2) as response:
                return response.status == 200
        except (OSError, error.URLError):
            return False

    def chat(self, messages: list[dict[str, str]], instructions: str) -> ProviderResponse:
        payload = self._payload(messages, instructions, False)
        req = request.Request(f"{self.base_url}/api/chat", data=json.dumps(payload).encode("utf-8"),
                              headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                text = data.get("message", {}).get("content", "O Ollama não retornou uma resposta.").strip()
                return ProviderResponse(text=text)
        except error.HTTPError as exc:
            logger.warning("ollama_request_failed model=%s kind=http_%s", self.model, exc.code)
            raise RuntimeError(f"Ollama respondeu com erro HTTP {exc.code}.") from exc
        except (OSError, error.URLError, json.JSONDecodeError) as exc:
            logger.warning("ollama_request_failed model=%s kind=%s", self.model, type(exc).__name__)
            raise RuntimeError("Não foi possível comunicar com o Ollama.") from exc

    def chat_stream(self, messages: list[dict[str, str]], instructions: str,
                    on_delta: Callable[[str], None]) -> ProviderResponse:
        payload = self._payload(messages, instructions, True)
        req = request.Request(f"{self.base_url}/api/chat", data=json.dumps(payload).encode("utf-8"),
                              headers={"Content-Type": "application/json"})
        parts: list[str] = []
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                for raw in response:
                    if not raw.strip(): continue
                    data = json.loads(raw.decode("utf-8"))
                    if data.get("error"): raise RuntimeError(f"Ollama: {data['error']}")
                    delta = str(data.get("message", {}).get("content", ""))
                    if delta: parts.append(delta); on_delta(delta)
            text = "".join(parts).strip()
            return ProviderResponse(text or "O Ollama não retornou uma resposta.")
        except error.HTTPError as exc:
            logger.warning("ollama_stream_failed model=%s kind=http_%s", self.model, exc.code)
            raise RuntimeError(f"Ollama respondeu com erro HTTP {exc.code}.") from exc
        except RuntimeError:
            logger.warning("ollama_stream_failed model=%s kind=provider_error", self.model)
            raise
        except (OSError, error.URLError, json.JSONDecodeError) as exc:
            logger.warning("ollama_stream_failed model=%s kind=%s", self.model, type(exc).__name__)
            raise RuntimeError("Não foi possível comunicar com o Ollama durante a resposta.") from exc

    def models(self) -> list[str]:
        try:
            with request.urlopen(f"{self.base_url}/api/tags", timeout=3) as response:
                data = json.loads(response.read().decode("utf-8"))
            return sorted({str(item.get("name", "")).strip() for item in data.get("models", ()) if item.get("name")})
        except (OSError, error.URLError, json.JSONDecodeError):
            return []

    def _payload(self, messages: list[dict[str, str]], instructions: str, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": instructions}, *messages],
            "stream": stream,
            "think": False,
            "keep_alive": "5m",
            "options": {"num_ctx": self.num_ctx, "num_predict": self.num_predict,
                        "temperature": .55, "repeat_penalty": 1.08},
        }
