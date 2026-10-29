from __future__ import annotations

import re
import unicodedata
from enum import Enum


class Intent(str, Enum):
    LOCAL_ACTION = "local_action"
    LOCAL_QUERY = "local_query"
    CAPABILITIES = "capabilities"
    CONVERSATION = "conversation"


class IntentRouter:
    CAPABILITY_PATTERNS = (
        r"\bquais?\b.*\b(servicos?|recursos?|funcionalidades?|funcoes?|habilidades?|coisas?)\b",
        r"\b(o que|que)\b.*\b(voce|james)\b.*\b(faz|fazer|consegue|pode)\b",
        r"\b(o que|que)\b.*\b(posso|podemos)\b.*\b(pedir|fazer|usar)\b",
        r"\bcomo\b.*\b(voce|james)\b.*\b(pode|consegue)\b.*\b(ajudar|auxiliar)\b",
        r"\bdo que\b.*\b(voce|james)\b.*\b(e capaz|consegue)\b",
        r"\b(suas?|seus?)\b.*\b(capacidades?|recursos?|funcoes?|habilidades?)\b",
    )
    CAPABILITY_FOLLOWUPS = (
        r"\b(e )?o que mais\b", r"\bquais? (deles? )?.*\b(offline|local|internet)\b",
        r"\bquais? (deles? )?.*\b(confirmacao|confirmar|permissao)\b",
        r"\b(e )?(isso|esses?|essas?)\b.*\b(funciona|funcionam|disponiveis?)\b",
    )
    ACTION_PATTERNS = (
        r"\b(abra|abrir|inicie)\b.*\b(calculadora|bloco de notas|notepad|navegador|pasta)\b",
        r"\b(adicione|crie|cadastrar?|nova)\b.*\btarefa\b",
        r"\b(lembre|memorize|guarde)\b",
        r"\b(crie|adicione|agende|edite|altere|conclua|adie|exclua)\b.*\blembrete\b",
        r"\b(organize|organizar)\b.*\b(arquivos?|documentos?|pasta)\b",
        r"\b(procure|localize|buscar arquivo)\b",
    )
    QUERY_PATTERNS = (
        r"\b(ajuda|comandos)\b", r"\b(informações do computador|informacoes do computador)\b",
        r"\b(mostre|listar?|quais|consultar?)\b.*\btarefas\b",
        r"\b(o que você lembra|memórias|memorias)\b",
        r"\b(mostre|listar?|quais|consultar?)\b.*\b(lembretes?|agenda)\b",
    )

    def classify(self, text: str) -> Intent:
        low = text.casefold()
        normalized = self.normalize(text)
        if any(re.search(pattern, normalized) for pattern in self.CAPABILITY_PATTERNS):
            return Intent.CAPABILITIES
        if any(re.search(pattern, low) for pattern in self.ACTION_PATTERNS): return Intent.LOCAL_ACTION
        if any(re.search(pattern, low) for pattern in self.QUERY_PATTERNS): return Intent.LOCAL_QUERY
        return Intent.CONVERSATION

    def is_capability_followup(self, text: str) -> bool:
        normalized = self.normalize(text)
        return any(re.search(pattern, normalized) for pattern in self.CAPABILITY_FOLLOWUPS)

    @staticmethod
    def normalize(text: str) -> str:
        plain = unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()
        return " ".join(re.findall(r"[a-z0-9]+", plain))
