from __future__ import annotations

import json
from urllib import request, error

from ai.base import ProviderResponse


class OllamaProvider:
    def __init__(self, base_url: str, model: str, timeout: int = 45):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def available(self) -> bool:
        try:
            with request.urlopen(f"{self.base_url}/api/tags", timeout=2) as response:
                return response.status == 200
        except (OSError, error.URLError):
            return False

    def chat(self, messages: list[dict[str, str]], instructions: str) -> ProviderResponse:
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": instructions}, *messages],
            "stream": False,
        }).encode("utf-8")
        req = request.Request(f"{self.base_url}/api/chat", data=payload,
                              headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                text = data.get("message", {}).get("content", "O Ollama não retornou uma resposta.").strip()
                return ProviderResponse(text=text)
        except error.HTTPError as exc:
            raise RuntimeError(f"Ollama respondeu com erro HTTP {exc.code}.") from exc
        except (OSError, error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError("Não foi possível comunicar com o Ollama.") from exc
