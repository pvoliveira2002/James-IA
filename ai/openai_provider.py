from __future__ import annotations

import importlib.util
import json
import os
from collections.abc import Callable
from typing import Any

from ai.base import ProviderResponse, ToolCall


TOOLS = [
    {"type": "function", "name": "open_calculator", "description": "Solicita abrir a calculadora do Windows.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "open_notepad", "description": "Solicita abrir o Bloco de Notas.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "open_browser", "description": "Solicita abrir o navegador padrão.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "open_directory", "description": "Solicita abrir uma pasta já autorizada pelo usuário.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}},
    {"type": "function", "name": "show_tasks", "description": "Consulta as tarefas pendentes cadastradas localmente.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "list_memories", "description": "Consulta somente memórias que o usuário autorizou salvar.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "organize_files", "description": "Solicita abrir o organizador supervisionado; não move nada automaticamente.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"type": "function", "name": "find_files", "description": "Solicita pesquisar um nome de arquivo em pasta escolhida pelo usuário.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}},
    {"type": "function", "name": "find_application", "description": "Localiza no catálogo local um aplicativo para uma intenção do usuário. Não invente IDs nem diga que abriu; forneça apenas a busca em linguagem natural.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False}},
    {"type": "function", "name": "navigate_public_web", "description": "Solicita navegação pública supervisionada. Use apenas para site conhecido, Google, YouTube, escolher resultado ou voltar; nunca forneça código nem URL local.", "parameters": {"type": "object", "properties": {"request": {"type": "string"}}, "required": ["request"], "additionalProperties": False}},
]


class OpenAIProvider:
    def __init__(self, model: str, timeout: float = 45):
        self.model, self.timeout = model, timeout

    def status(self) -> tuple[bool, str]:
        if importlib.util.find_spec("openai") is None:
            return False, "SDK OpenAI não instalado"
        if not os.environ.get("OPENAI_API_KEY"):
            return False, "chave OPENAI_API_KEY não configurada"
        return True, "configurado (conexão verificada ao conversar)"

    def chat(self, messages: list[dict[str, str]], instructions: str) -> ProviderResponse:
        ready, reason = self.status()
        if not ready: raise RuntimeError(f"OpenAI indisponível: {reason}.")
        try:
            from openai import OpenAI
            client = OpenAI(timeout=self.timeout)
            response = client.responses.create(
                model=self.model, instructions=instructions, input=messages,
                tools=TOOLS, tool_choice="auto", store=False, max_output_tokens=700,
            )
        except Exception as exc:
            raise RuntimeError(f"Falha ao consultar a OpenAI: {exc}") from exc
        return self._result(response)

    def chat_stream(self, messages: list[dict[str, str]], instructions: str,
                    on_delta: Callable[[str], None]) -> ProviderResponse:
        ready, reason = self.status()
        if not ready: raise RuntimeError(f"OpenAI indisponível: {reason}.")
        try:
            from openai import OpenAI
            client = OpenAI(timeout=self.timeout)
            stream = client.responses.create(
                model=self.model, instructions=instructions, input=messages,
                tools=TOOLS, tool_choice="auto", store=False, max_output_tokens=700, stream=True,
            )
            parts: list[str] = []; completed = None
            for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    delta = str(getattr(event, "delta", ""))
                    if delta: parts.append(delta); on_delta(delta)
                elif event_type == "response.completed":
                    completed = getattr(event, "response", None)
                elif event_type == "error":
                    raise RuntimeError(str(getattr(event, "message", "erro desconhecido")))
        except Exception as exc:
            raise RuntimeError(f"Falha ao consultar a OpenAI: {exc}") from exc
        result = self._result(completed) if completed is not None else ProviderResponse("".join(parts).strip())
        return result if result.text or result.tool_calls else ProviderResponse("".join(parts).strip())

    @staticmethod
    def _result(response: Any) -> ProviderResponse:
        calls: list[ToolCall] = []
        for item in getattr(response, "output", ()):
            if getattr(item, "type", None) == "function_call":
                try: arguments = json.loads(getattr(item, "arguments", "{}"))
                except json.JSONDecodeError: arguments = {}
                calls.append(ToolCall(getattr(item, "name", ""), arguments))
        return ProviderResponse((getattr(response, "output_text", "") or "").strip(), tuple(calls))
