import tempfile
import unittest
from pathlib import Path
from tools.file_manager import category_for, execute_organization, find_files, preview_organization


class FileManagerTests(unittest.TestCase):
    def test_category(self):
        self.assertEqual(category_for(Path("foto.JPG")), "Imagens")
        self.assertEqual(category_for(Path("contrato.pdf")), "PDFs")
        self.assertEqual(category_for(Path("texto.docx")), "Documentos Word")
        self.assertEqual(category_for(Path("arquivo.xyz")), "Outros arquivos")

    def test_preview_and_execute(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / "foto.jpg").write_text("x")
            plans = preview_organization(root)
            self.assertEqual(len(plans), 1)
            self.assertEqual(execute_organization(plans), 1)
            self.assertTrue((root / "Imagens" / "foto.jpg").exists())

    def test_analysis_does_not_move_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for name in ("foto.png", "contrato.pdf", "texto.docx", "dados.xlsx", "outro.xyz"):
                (root / name).write_bytes(b"conteudo")
            plans = preview_organization(root)
            self.assertEqual(len(plans), 5)
            self.assertTrue(all(plan.source.exists() for plan in plans))
            self.assertTrue(all(not plan.destination.exists() for plan in plans))

    def test_direct_files_only_unless_requested(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); nested = root / "sub"; nested.mkdir()
            (root / "direto.pdf").write_bytes(b"x"); (nested / "interno.pdf").write_bytes(b"x")
            self.assertEqual(len(preview_organization(root)), 1)
            self.assertEqual(len(preview_organization(root, include_subfolders=True)), 2)

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(preview_organization(Path(raw)), [])

    def test_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / "foto.jpg").write_bytes(b"nova")
            target = root / "Imagens"; target.mkdir(); (target / "foto.jpg").write_bytes(b"original")
            plans = preview_organization(root); self.assertEqual(plans[0].destination.name, "foto_2.jpg")
            execute_organization(plans)
            self.assertEqual((target / "foto.jpg").read_bytes(), b"original")
            self.assertEqual((target / "foto_2.jpg").read_bytes(), b"nova")

    def test_find(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / "curriculo_joao.pdf").write_text("x")
            self.assertEqual(len(find_files(root, "joao")), 1)


if __name__ == "__main__": unittest.main()
