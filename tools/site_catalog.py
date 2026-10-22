from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

from memory.database import Database


def normalize_site_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def validate_public_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False, "Somente enderecos HTTPS publicos sao permitidos."
        host = (parsed.hostname or "").strip(".").casefold()
        if not host or host == "localhost" or host.endswith(".local"):
            return False, "Endereco local bloqueado pela politica de seguranca."
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global:
                return False, "Endereco privado ou reservado bloqueado."
        except ValueError:
            pass
        if parsed.username or parsed.password:
            return False, "URLs com credenciais embutidas nao sao permitidas."
        return True, ""
    except ValueError:
        return False, "Endereco invalido."


@dataclass(frozen=True)
class Website:
    name: str
    url: str


class SiteCatalog:
    DEFAULTS = (
        {"name": "YouTube", "url": "https://www.youtube.com/", "aliases": ["youtube", "videos", "yt"], "favorite": True},
        {"name": "Google", "url": "https://www.google.com/", "aliases": ["google", "pesquisa", "buscador"], "favorite": True},
        {"name": "Gmail", "url": "https://mail.google.com/", "aliases": ["gmail", "email"]},
        {"name": "WhatsApp Web", "url": "https://web.whatsapp.com/", "aliases": ["whatsapp", "zap", "whatsapp web"], "favorite": True},
        {"name": "Bling", "url": "https://www.bling.com.br/", "aliases": ["bling", "erp"]},
        {"name": "Google Maps", "url": "https://maps.google.com/", "aliases": ["google maps", "maps", "mapas"]},
        {"name": "Epson", "url": "https://epson.com.br/", "aliases": ["epson", "site da epson"]},
    )

    def __init__(self, database: Database):
        self.db = database
        prepared = [{**s, "normalized_name": normalize_site_name(s["name"])} for s in self.DEFAULTS]
        self.db.seed_websites(prepared)

    def find(self, query: str) -> Website | None:
        wanted = normalize_site_name(query)
        for row in self.db.website_aliases():
            if wanted == normalize_site_name(row["alias"]):
                return Website(row["name"], row["url"])
        for row in self.db.websites():
            name = normalize_site_name(row["name"])
            if wanted == name or name in wanted:
                return Website(row["name"], row["url"])
        return None
