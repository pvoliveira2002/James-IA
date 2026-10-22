import tempfile
import tkinter as tk
import unittest
import time
from pathlib import Path

from config.settings import Settings
from core.assistant import Assistant, AssistantResponse
from interface.app import JamesApp
from memory.database import Database
from tools.system_monitor import SystemMonitor


class DashboardInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.settings = Settings(root); self.db = Database(root / "data" / "test.db")
        try:
            self.app = JamesApp(Assistant(self.db, self.settings), self.db, self.settings)
            self.app.root.withdraw()
        except tk.TclError as exc:
            self.temp.cleanup(); self.skipTest(f"Tkinter indisponível: {exc}")

    def tearDown(self):
        if hasattr(self, "app"): self.app.root.destroy()
        self.temp.cleanup()

    def test_main_pages_are_navigable(self):
        for page in ("dashboard", "core", "conversations", "reports", "tasks", "memory", "apps", "automations", "settings", "store"):
            self.app.show_page(page); self.app.root.update_idletasks()
            self.assertEqual(self.app.current_page, page)

    def test_dashboard_uses_real_database_counts(self):
        self.db.add_task("Teste visual"); self.db.add_memory("Memória visual")
        self.assertEqual(self.db.counts()["tasks"], 1)
        self.assertEqual(self.db.counts()["memories"], 1)

    def test_system_monitor_returns_real_percentages(self):
        snapshot = SystemMonitor().snapshot()
        self.assertEqual(set(snapshot), {"CPU", "RAM", "Disco"})
        self.assertTrue(all(0 <= value <= 100 for value in snapshot.values()))

    def test_dashboard_contains_live_chat_without_duplicate_database(self):
        self.app.show_page("dashboard"); before = self.db.counts()["conversations"]
        self.app._append("user", "Mensagem visível na central")
        self.assertIn("Mensagem visível na central", self.app.chat.get("1.0", "end"))
        self.assertEqual(self.db.counts()["conversations"], before + 1)
        self.app.show_page("tasks"); self.app.show_page("dashboard")
        self.assertIn("Mensagem visível na central", self.app.chat.get("1.0", "end"))
        self.assertEqual(self.db.counts()["conversations"], before + 1)

    def test_background_response_appears_on_command_center(self):
        self.app.show_page("dashboard")
        self.app.responses.put(AssistantResponse("Resposta em tempo real"))
        self.app._poll(); self.app.root.update_idletasks()
        self.assertIn("Resposta em tempo real", self.app.chat.get("1.0", "end"))

    def test_reports_are_accessible_from_dashboard(self):
        run_id = self.db.start_automation("Gerar relatório de teste")
        step = self.db.add_automation_step(run_id, 1, "Executar teste")
        self.db.update_automation_step(step, "concluido", "Arquivo pronto")
        self.db.finish_automation(run_id, "concluido", "Resultado completo")
        self.app.show_page("dashboard"); self.app.show_report(run_id); self.app.root.update_idletasks()
        self.assertEqual(self.app.current_page, "reports")
        self.assertIn("Resultado completo", self.app.report_detail.get("1.0", "end"))

    def test_dashboard_build_is_lightweight(self):
        started = time.perf_counter(); self.app.show_page("dashboard"); self.app.root.update_idletasks()
        self.assertLess(time.perf_counter() - started, 1.5)

    def test_sidebar_and_activity_panel_are_collapsible(self):
        self.app.show_page("dashboard")
        self.app.toggle_sidebar(); self.assertTrue(self.app.sidebar_collapsed); self.assertEqual(self.app.sidebar.cget("width"), 72)
        self.app.toggle_sidebar(); self.assertFalse(self.app.sidebar_collapsed)
        self.app.toggle_right_panel(); self.assertTrue(self.app.right_panel_collapsed); self.assertFalse(self.app.right_dashboard_panel.winfo_ismapped())
        self.app.toggle_right_panel(); self.app.root.update_idletasks(); self.assertFalse(self.app.right_panel_collapsed)

    def test_chat_bubbles_use_opposite_alignment(self):
        self.db.add_conversation("assistant", "Resposta à esquerda")
        self.db.add_conversation("user", "Mensagem à direita")
        self.app.show_page("dashboard"); self.app.root.update_idletasks()
        lines = self.app.chat.messages.winfo_children()
        assistant_bubble = lines[-2].winfo_children()[0]; user_bubble = lines[-1].winfo_children()[0]
        self.assertEqual(assistant_bubble.pack_info()["side"], "left")
        self.assertEqual(user_bubble.pack_info()["side"], "right")

    def test_dashboard_resizes_for_supported_resolutions(self):
        for width, height in ((1920, 1080), (1600, 900), (1366, 768)):
            self.app.root.geometry(f"{width}x{height}"); self.app.show_page("dashboard"); self.app.root.update_idletasks()
            self.assertGreater(self.app.chat.winfo_width(), 450)
            self.assertGreater(self.app.chat.winfo_height(), 250)


if __name__ == "__main__": unittest.main()
