from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


class YouTubeAction(str, Enum):
    OPEN_SITE = "open_site"
    SEARCH = "search"
    SEARCH_AND_OPEN = "search_and_open"


@dataclass(frozen=True)
class YouTubeIntent:
    action: YouTubeAction
    query: str = ""


def _plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()


def _clean_query(text: str) -> str:
    value = _plain(text).strip(" .!?,")
    patterns = (
        r"^(?:abra|abre|abrir|coloca|coloque|quero assistir)\s+(?:no\s+youtube\s+)?",
        r"^(?:procura|procure|pesquisa|pesquise|busca|busque|me mostra|mostre)\s+(?:no\s+youtube\s+)?",
    )
    for pattern in patterns: value = re.sub(pattern, "", value).strip()
    value = re.sub(r"\s+(?:no|na)\s+youtube\s*$", "", value).strip()
    value = re.sub(r"^youtube\s+", "", value).strip()
    value = re.sub(r"^(?:um|uma|o|a)\s+", "", value).strip()
    return " ".join(value.split())


def parse_youtube_intent(text: str) -> YouTubeIntent | None:
    low = _plain(text).strip(" .!?")
    has_youtube = "youtube" in low
    media_words = bool(re.search(r"\b(video|videos|aula|aulas|tutori\w*|assistir|como fazer|ensinando)\b", low))
    media_topic = bool(re.search(r"\b(blusa|camisa|camiseta|sublima\w*|estamparia|prensa termica)\b", low))
    search_words = bool(re.search(r"\b(procura|procure|pesquisa|pesquise|busca|busque|encontre|mostra|mostre)\b", low))
    play_words = bool(re.search(r"\b(abra|abre|abrir|coloca|coloque|assistir)\b", low)) or "quero assistir" in low

    if re.fullmatch(r"(?:abra|abre|abrir|acesse|entre)(?:\s+o|\s+no)?\s+youtube", low):
        return YouTubeIntent(YouTubeAction.OPEN_SITE)
    if has_youtube and play_words and media_words:
        query = _clean_query(low)
        return YouTubeIntent(YouTubeAction.SEARCH_AND_OPEN, query) if query else None
    if has_youtube and search_words:
        query = _clean_query(low)
        return YouTubeIntent(YouTubeAction.SEARCH, query) if query else None
    if media_words and (search_words or play_words):
        query = _clean_query(low)
        action = YouTubeAction.SEARCH_AND_OPEN if play_words and not search_words else YouTubeAction.SEARCH
        return YouTubeIntent(action, query) if query else None
    if search_words and media_topic and "google" not in low and "internet" not in low:
        query = _clean_query(low)
        return YouTubeIntent(YouTubeAction.SEARCH, query) if query else None
    return None
