from __future__ import annotations

import re
from enum import Enum


class Intent(str, Enum):
    LOCAL_ACTION = "local_action"
    LOCAL_QUERY = "local_query"
    CONVERSATION = "conversation"


class IntentRouter:
    ACTION_PATTERNS = (
        r"\b(abra|abrir|inicie)\b.*\b(calculadora|bloco de notas|notepad|navegador|pasta)\b",
        r"\b(adicione|crie|cadastrar?|nova)\b.*\btarefa\b",
        r"\b(lembre|memorize|guarde)\b",
        r"\b(organize|organizar)\b.*\b(arquivos?|documentos?|pasta)\b",
        r"\b(procure|localize|buscar arquivo)\b",
    )
    QUERY_PATTERNS = (
        r"\b(ajuda|comandos)\b", r"\b(informações do computador|informacoes do computador)\b",
        r"\b(mostre|listar?|quais|consultar?)\b.*\btarefas\b",
        r"\b(o que você lembra|memórias|memorias)\b",
    )

    def classify(self, text: str) -> Intent:
        low = text.casefold()
        if any(re.search(pattern, low) for pattern in self.ACTION_PATTERNS): return Intent.LOCAL_ACTION
        if any(re.search(pattern, low) for pattern in self.QUERY_PATTERNS): return Intent.LOCAL_QUERY
        return Intent.CONVERSATION
