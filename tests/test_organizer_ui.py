import tempfile
import tkinter as tk
import unittest
from pathlib import Path

from config.settings import Settings
from interface.organizer import OrganizerDialog
from memory.database import Database
from tools.file_manager import preview_organization


class OrganizerInterfaceTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk(); self.root.withdraw()
        except tk.TclError as exc:
            self.skipTest(f"Tkinter indisponível: {exc}")
        self.temp = tempfile.TemporaryDirectory(); self.base = Path(self.temp.name)
        self.settings = Settings(self.base / "config")
        self.db = Database(self.base / "test.db")

    def tearDown(self):
        if hasattr(self, "root"): self.root.destroy()
        if hasattr(self, "temp"): self.temp.cleanup()

    def test_analyzed_files_appear_in_preview_table(self):
        folder = self.base / "arquivos"; folder.mkdir()
        (folder / "foto.png").write_bytes(b"imagem")
        (folder / "contrato.pdf").write_bytes(b"pdf")
        dialog = OrganizerDialog(self.root, self.settings, self.db)
        dialog.window.withdraw(); dialog.plans = preview_organization(folder); dialog._fill(False)
        rows = dialog.tree.get_children()
        self.assertEqual(len(rows), 2)
        values = [dialog.tree.item(row, "values") for row in rows]
        self.assertEqual({value[0] for value in values}, {"foto.png", "contrato.pdf"})
        dialog.show_preview()
        rows = dialog.tree.get_children()
        self.assertTrue(all(dialog.tree.item(row, "values")[5] != "—" for row in rows))
        dialog.window.destroy()


if __name__ == "__main__": unittest.main()
