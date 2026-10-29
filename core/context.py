from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from memory.database import Database


@dataclass(frozen=True)
class ContextSnapshot:
    messages: list[dict[str, str]]
    temporary_note: str
    topic_changed: bool


class ConversationContext:
    """Contexto recente é temporário; somente `memories` representa memória persistente."""

    STOPWORDS = {"a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos", "e",
                 "em", "eu", "me", "meu", "minha", "na", "nas", "no", "nos", "o", "os", "para",
                 "por", "que", "se", "um", "uma", "voce", "você"}
    REFERENCES = {"isso", "isto", "aquilo", "ele", "ela", "eles", "elas", "esse", "essa", "anterior",
                  "antes", "primeiro", "segundo", "ultimo", "último", "tambem", "também", "sobre isso"}
    MEMORY_SYNONYMS = (
        {"horario", "hora", "abre", "abertura", "fecha", "fechamento"},
        {"loja", "negocio", "empresa"},
        {"cor", "cores", "coloracao"},
        {"preco", "valor", "custo"},
    )

    def __init__(self, database: Database, max_messages: int = 12, max_chars: int = 8000,
                 conversation_id: str = "default"):
        self.db, self.max_messages, self.max_chars = database, max_messages, max_chars
        self.conversation_id = conversation_id.strip()[:80] or "default"

    def recent_messages(self) -> list[dict[str, str]]:
        rows = self.db.conversations(self.max_messages * 2, self.conversation_id)
        deduplicated = []
        for row in rows:
            if row["role"] not in {"user", "assistant"}:
                continue
            if deduplicated and row["role"] == deduplicated[-1]["role"] and row["content"] == deduplicated[-1]["content"]:
                continue
            deduplicated.append(row)
        rows = deduplicated[-self.max_messages:]
        result: list[dict[str, str]] = []
        used = 0
        for row in reversed(rows):
            content = str(row["content"])
            remaining = self.max_chars - used
            if remaining <= 0: break
            content = content[-remaining:]
            result.append({"role": row["role"], "content": content})
            used += len(content)
        result = list(reversed(result))
        while result and result[0]["role"] == "assistant": result.pop(0)
        return result

    def snapshot(self, current_message: str) -> ContextSnapshot:
        messages = self.recent_messages()
        history = messages[:-1] if messages and messages[-1]["role"] == "user" and messages[-1]["content"] == current_message else messages
        previous_users = [item["content"] for item in history if item["role"] == "user"]
        previous = previous_users[-1] if previous_users else ""
        referenced = self._has_reference(current_message)
        changed = bool(previous and not referenced and self._topic_similarity(previous, current_message) < .12)
        if not previous:
            note = "Esta é a primeira mensagem do contexto temporário disponível."
        elif referenced:
            note = f"A mensagem atual contém uma referência; resolva-a usando os turnos imediatamente anteriores. Último pedido: {previous[:180]}"
        elif changed:
            note = "A mensagem atual parece iniciar outro assunto. Responda ao novo tema sem misturar detalhes do assunto anterior."
        else:
            note = f"A mensagem atual parece continuar o assunto recente. Último pedido relacionado: {previous[:180]}"
        return ContextSnapshot(messages, note, changed)

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        plain = unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()
        return {word for word in re.findall(r"[a-z0-9]+", plain) if len(word) > 2 and word not in cls.STOPWORDS}

    @classmethod
    def _topic_similarity(cls, previous: str, current: str) -> float:
        left, right = cls._tokens(previous), cls._tokens(current)
        if not left or not right: return 0.0
        return len(left & right) / len(left | right)

    @classmethod
    def _memory_tokens(cls, text: str) -> set[str]:
        tokens = cls._tokens(text)
        expanded = set(tokens)
        for group in cls.MEMORY_SYNONYMS:
            if tokens & group:
                expanded |= group
        return expanded

    @classmethod
    def _has_reference(cls, text: str) -> bool:
        normalized = " ".join(re.findall(r"[a-zà-ÿ0-9]+", text.casefold()))
        return any(re.search(rf"\b{re.escape(term)}\b", normalized) for term in cls.REFERENCES)

    def authorized_memories(self, query: str = "", limit: int = 8) -> list[str]:
        """Recupera memórias relevantes sem embeddings ou dependências pesadas."""
        rows = self.db.memories()[:250]
        if not rows:
            return []
        query_tokens = self._memory_tokens(query)
        ranked: list[tuple[float, int, str]] = []
        for row in rows:
            content = str(row["content"])
            memory_tokens = self._memory_tokens(content)
            common = query_tokens & memory_tokens
            if common:
                coverage = len(common) / max(1, len(query_tokens))
                precision = len(common) / max(1, len(memory_tokens))
                ranked.append((coverage * .75 + precision * .25, int(row["id"]), content))
        if ranked:
            ranked.sort(key=lambda item: (-item[0], -item[1]))
            return [item[2] for item in ranked[:limit]]
        normalized = " ".join(re.findall(r"[a-zà-ÿ0-9]+", query.casefold()))
        if any(phrase in normalized for phrase in ("o que voce lembra", "o que você lembra", "memorias", "memórias", "sabe sobre mim")):
            return [str(row["content"]) for row in rows[:min(3, limit)]]
        return []
