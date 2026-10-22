from __future__ import annotations

from memory.database import Database


class ConversationContext:
    """Monta contexto local limitado, evitando crescimento ilimitado do prompt."""

    def __init__(self, database: Database, max_messages: int = 12, max_chars: int = 8000):
        self.db, self.max_messages, self.max_chars = database, max_messages, max_chars

    def recent_messages(self) -> list[dict[str, str]]:
        rows = self.db.conversations(self.max_messages)
        result: list[dict[str, str]] = []
        used = 0
        for row in reversed(rows):
            content = str(row["content"])
            remaining = self.max_chars - used
            if remaining <= 0: break
            content = content[-remaining:]
            result.append({"role": row["role"], "content": content})
            used += len(content)
        return list(reversed(result))

    def authorized_memories(self, limit: int = 12) -> list[str]:
        return [str(row["content"]) for row in self.db.memories()[:limit]]
