import tempfile
import unittest
from pathlib import Path

from config.settings import Settings
from security.policy import SecurityPolicy


class SecurityPolicyTests(unittest.TestCase):
    def test_directory_requires_explicit_authorization(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); selected = root / "selecionada"; selected.mkdir()
            settings = Settings(root / "config")
            allowed, reason = SecurityPolicy(settings).validate_directory(selected)
            self.assertFalse(allowed); self.assertIn("Nenhum diretório", reason)
            settings.set("allowed_directories", [str(selected)])
            self.assertTrue(SecurityPolicy(settings).validate_directory(selected)[0])


if __name__ == "__main__": unittest.main()
