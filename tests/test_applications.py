import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from config.settings import Settings
from core.assistant import Assistant
from memory.database import Database
from tools.application_discovery import (
    ApplicationDiscoveryService, DiscoveredApplication, is_web_application, make_app_id, normalize_app_name,
)
from tools.application_launcher import ApplicationLauncherService
from tools.application_matcher import ApplicationMatcher


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.db = Database(self.root / "apps.db"); self.settings = Settings(self.root / "config")
        self.exe = self.root / "PhotoEditor.exe"; self.exe.write_bytes(b"MZ-test")
        self.app_id = make_app_id("portable", str(self.exe), "Photo Editor")
        self.db.add_manual_application({"id": self.app_id, "display_name": "Photo Editor",
            "normalized_name": normalize_app_name("Photo Editor"), "launch_target": str(self.exe),
            "app_user_model_id": None, "app_type": "portable", "discovery_source": "manual", "icon_path": str(self.exe)})

    def tearDown(self): self.temp.cleanup()

    def test_name_normalization(self):
        self.assertEqual(normalize_app_name("Ádobe Photoshop.EXE"), "adobe photoshop")
        self.assertEqual(normalize_app_name("Chrome (1)"), "chrome")

    def test_deduplication_prefers_registered_path(self):
        shortcut = DiscoveredApplication("1", "Chrome", "chrome", "x.lnk", None, "shortcut", "start_menu")
        registered = DiscoveredApplication("2", "Chrome", "chrome", "chrome.exe", None, "win32", "app_paths")
        result = ApplicationDiscoveryService._deduplicate([shortcut, registered])
        self.assertEqual(len(result), 1); self.assertEqual(result[0].discovery_source, "app_paths")

    def test_internal_services_are_filtered(self):
        from tools.application_discovery import is_safe_catalog_name
        self.assertFalse(is_safe_catalog_name("AgentService.exe"))
        self.assertFalse(is_safe_catalog_name("Agendador de Tarefas"))
        self.assertTrue(is_safe_catalog_name("Adobe Photoshop"))

    def test_chrome_pwa_is_classified_as_web_not_desktop(self):
        self.assertTrue(is_web_application("WhatsApp Web", app_id="Chrome._crx_abc"))
        self.assertTrue(is_web_application("WhatsApp Web", target=r"C:\Menu\Apps do Chrome\WhatsApp Web.lnk"))
        self.assertFalse(is_web_application("WhatsApp", app_id="5319275A.WhatsAppDesktop_xyz!App"))

    def test_web_app_is_not_matched_as_installed_program(self):
        web_id = make_app_id("web_app", "Chrome._crx_abc", "WhatsApp Web")
        self.db.replace_discovered_applications([{"id": web_id, "display_name": "WhatsApp Web", "normalized_name": "whatsapp web",
            "launch_target": None, "app_user_model_id": "Chrome._crx_abc", "app_type": "web_app", "discovery_source": "get_start_apps"}])
        self.assertEqual(ApplicationMatcher(self.db).match("WhatsApp"), [])

    def test_uwp_uses_shell_apps_folder_app_user_model_id(self):
        app_id = make_app_id("uwp", "Vendor.Product_abc!App", "Modern App")
        self.db.replace_discovered_applications([{"id": app_id, "display_name": "Modern App", "normalized_name": "modern app",
            "launch_target": None, "app_user_model_id": "Vendor.Product_abc!App", "app_type": "uwp", "discovery_source": "get_start_apps"}])
        self.db.set_application_permission(app_id, "allow"); popen = Mock()
        success, _ = ApplicationLauncherService(self.db, popen).launch(app_id)
        self.assertTrue(success); popen.assert_called_once_with(["explorer.exe", r"shell:AppsFolder\Vendor.Product_abc!App"], shell=False)

    def test_alias_is_reused(self):
        self.db.set_application_alias(self.app_id, "editor de fotos", normalize_app_name("editor de fotos"))
        matches = ApplicationMatcher(self.db).match("editor de fotos")
        self.assertEqual(matches[0].app_id, self.app_id); self.assertEqual(matches[0].score, 1.0)

    def test_approximate_match_and_missing_application(self):
        matcher = ApplicationMatcher(self.db)
        self.assertEqual(matcher.match("photo editr")[0].app_id, self.app_id)
        self.assertEqual(matcher.match("aplicativo totalmente inexistente"), [])

    def test_missing_whatsapp_does_not_offer_unrelated_apps(self):
        self.assertEqual(ApplicationMatcher(self.db).match("WhatsApp"), [])
        self.assertEqual(ApplicationMatcher(self.db).match("aplicativo do WhatsApp"), [])

    def test_launcher_requires_permission(self):
        popen = Mock(); success, message = ApplicationLauncherService(self.db, popen).launch(self.app_id)
        self.assertFalse(success); self.assertIn("não foi autorizada", message); popen.assert_not_called()

    def test_authorized_launcher_uses_list_and_shell_false(self):
        self.db.set_application_permission(self.app_id, "allow"); popen = Mock()
        success, _ = ApplicationLauncherService(self.db, popen).launch(self.app_id)
        self.assertTrue(success); popen.assert_called_once_with([str(self.exe.resolve())], shell=False)

    def test_unknown_id_and_scripts_are_blocked(self):
        launcher = ApplicationLauncherService(self.db, Mock())
        self.assertFalse(launcher.launch("id-inventado")[0])
        script = self.root / "perigoso.cmd"; script.write_text("echo x")
        app_id = make_app_id("portable", str(script), "Arquivo")
        self.db.add_manual_application({"id": app_id, "display_name": "Arquivo", "normalized_name": "arquivo",
            "launch_target": str(script), "app_user_model_id": None, "app_type": "portable", "discovery_source": "manual"})
        self.db.set_application_permission(app_id, "allow")
        self.assertFalse(launcher.launch(app_id)[0])

    def test_broken_shortcut_is_reported(self):
        app_id = make_app_id("shortcut", str(self.root / "missing.lnk"), "Atalho")
        self.db.replace_discovered_applications([{"id": app_id, "display_name": "Atalho", "normalized_name": "atalho",
            "launch_target": str(self.root / "missing.lnk"), "app_user_model_id": None, "app_type": "shortcut", "discovery_source": "start_menu"}])
        self.db.set_application_permission(app_id, "allow")
        success, message = ApplicationLauncherService(self.db, Mock()).launch(app_id)
        self.assertFalse(success); self.assertIn("Não foi possível", message)

    def test_assistant_requests_confirmation_without_ai_provider(self):
        assistant = Assistant(self.db, self.settings)
        response = assistant.process("James, abra o Photo Editor")
        self.assertEqual(response.action, "confirm_application"); self.assertEqual(response.payload, self.app_id)

    def test_multiple_results_request_choice(self):
        other = self.root / "PhotoEditorPro.exe"; other.write_bytes(b"MZ")
        other_id = make_app_id("portable", str(other), "Photo Editor Pro")
        self.db.add_manual_application({"id": other_id, "display_name": "Photo Editor Pro", "normalized_name": "photo editor pro",
            "launch_target": str(other), "app_user_model_id": None, "app_type": "portable", "discovery_source": "manual"})
        response = Assistant(self.db, self.settings).request_application("photo")
        self.assertEqual(response.action, "choose_application")


if __name__ == "__main__": unittest.main()
