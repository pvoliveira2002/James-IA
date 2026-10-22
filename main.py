"""Ponto de entrada do James IA."""
from pathlib import Path
import logging

from config.settings import Settings
from memory.database import Database
from core.assistant import Assistant
from interface.app import JamesApp


def main() -> None:
    base = Path(__file__).resolve().parent
    settings = Settings(base)
    settings.ensure_directories()
    logging.basicConfig(
        filename=settings.log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    database = Database(settings.database_path)
    assistant = Assistant(database, settings)
    JamesApp(assistant, database, settings).run()


if __name__ == "__main__":
    main()
