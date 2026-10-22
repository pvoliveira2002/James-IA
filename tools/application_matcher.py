from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re

from memory.database import Database
from tools.application_discovery import normalize_app_name


INTENT_HINTS = {
    "editar imagem": ("photoshop", "gimp", "paint"), "editor de fotos": ("photoshop", "gimp", "paint"),
    "fazer documento": ("word", "writer", "wordpad"), "documento no word": ("word",),
    "planilha": ("excel", "calc"), "minha impressora": ("epson", "printer", "impressora"),
    "navegar internet": ("chrome", "firefox", "edge"),
}


@dataclass(frozen=True)
class ApplicationMatch:
    app_id: str
    display_name: str
    score: float


class ApplicationMatcher:
    def __init__(self, database: Database): self.db = database

    def match(self, query: str, limit: int = 5, threshold: float = .55) -> list[ApplicationMatch]:
        normalized = normalize_app_name(query)
        normalized = re.sub(r"^(?:o |a )?(?:aplicativo|programa|app)(?: do| da| de)?\s+", "", normalized).strip()
        aliases = {row["normalized_alias"]: row["application_id"] for row in self.db.application_aliases()}
        if normalized in aliases:
            app = self.db.get_application(aliases[normalized])
            return [ApplicationMatch(app["id"], app["display_name"], 1.0)] if app else []
        hints: tuple[str, ...] = ()
        for phrase, values in INTENT_HINTS.items():
            if phrase in normalized: hints += values
        results = []
        query_tokens = set(normalized.split())
        applications = [app for app in self.db.applications() if app["app_type"] != "web_app"]
        exact = [ApplicationMatch(app["id"], app["display_name"], 1.0)
                 for app in applications if str(app["normalized_name"]) == normalized]
        if exact:
            return exact[:limit]
        for app in applications:
            name = str(app["normalized_name"]); name_tokens = set(name.split())
            sequence = SequenceMatcher(None, normalized, name).ratio()
            overlap = len(query_tokens & name_tokens) / max(1, len(name_tokens))
            contains = .92 if name in normalized or normalized in name else 0
            hinted = .88 if any(hint in name for hint in hints) else 0
            score = max(sequence, overlap, contains, hinted)
            if score >= threshold: results.append(ApplicationMatch(app["id"], app["display_name"], score))
        return sorted(results, key=lambda item: (-item.score, item.display_name.casefold()))[:limit]
