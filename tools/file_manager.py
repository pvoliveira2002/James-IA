from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


CATEGORIES = {
    "Imagens": {".jpg", ".jpeg", ".png", ".webp"},
    "PDFs": {".pdf"},
    "Documentos Word": {".doc", ".docx"},
    "Planilhas": {".xls", ".xlsx", ".csv", ".ods"},
    "Vídeos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm"},
    "Áudios": {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"},
    "Arquivos compactados": {".zip", ".rar", ".7z", ".tar", ".gz"},
}


@dataclass(frozen=True)
class MovePlan:
    source: Path
    destination: Path
    size: int
    category: str

    @property
    def extension(self) -> str:
        return self.source.suffix.upper() or "Sem extensão"


def category_for(path: Path) -> str:
    suffix = path.suffix.lower()
    for category, suffixes in CATEGORIES.items():
        if suffix in suffixes:
            return category
    return "Outros arquivos"


def preview_organization(directory: Path, include_subfolders: bool = False) -> list[MovePlan]:
    """Analisa arquivos sem alterar o disco; por padrão considera somente o nível atual."""
    directory = directory.expanduser().resolve(strict=True)
    if not directory.is_dir():
        raise NotADirectoryError(str(directory))
    items = directory.rglob("*") if include_subfolders else directory.iterdir()
    plans: list[MovePlan] = []
    reserved: set[Path] = set()
    for item in items:
        if item.is_file():
            category = category_for(item)
            destination = directory / category / item.name
            stem, suffix, number = item.stem, item.suffix, 2
            while destination.exists() or destination in reserved:
                destination = directory / category / f"{stem}_{number}{suffix}"
                number += 1
            reserved.add(destination)
            plans.append(MovePlan(item, destination, item.stat().st_size, category))
    return plans


def execute_organization(plans: list[MovePlan]) -> int:
    moved = 0
    for plan in plans:
        if not plan.source.is_file():
            raise FileNotFoundError(f"Arquivo não encontrado: {plan.source}")
        plan.destination.parent.mkdir(parents=True, exist_ok=True)
        if plan.destination.exists():
            raise FileExistsError(f"O destino já existe: {plan.destination}")
        shutil.move(str(plan.source), str(plan.destination))
        moved += 1
    return moved


def find_files(directory: Path, query: str, limit: int = 50) -> list[Path]:
    query = query.casefold()
    results: list[Path] = []
    for item in directory.rglob("*"):
        if item.is_file() and query in item.name.casefold():
            results.append(item)
            if len(results) >= limit:
                break
    return results
