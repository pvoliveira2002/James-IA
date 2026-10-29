import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from config.settings import Settings
from core.assistant import Assistant
from core.reminder_parser import parse_reminder_command
from core.scheduler import ReminderScheduler
from memory.database import Database
from tools.windows_notifications import WindowsReminderNotifier


NOW = datetime(2026, 10, 24, 10, 0, 0)


class FakeNotifier:
    def __init__(self, succeeds=True):
        self.succeeds = succeeds; self.shown = []

    def show(self, reminder, on_snooze, on_complete, on_error):
        self.shown.append((dict(reminder), on_snooze, on_complete))
        if not self.succeeds: on_error("notificação indisponível")
        return self.succeeds


class ReminderParserTests(unittest.TestCase):
    def test_tomorrow_and_relative_time(self):
        command = parse_reminder_command("me lembre de pagar a conta amanhã às 14h", NOW)
        self.assertEqual(command.title, "pagar a conta")
        self.assertEqual(command.remind_at, datetime(2026, 10, 25, 14, 0))
        relative = parse_reminder_command("crie um lembrete para conferir a prensa daqui a 30 minutos", NOW)
        self.assertEqual(relative.remind_at, NOW + timedelta(minutes=30))
        scheduled = parse_reminder_command("agende reunião amanhã às 16h", NOW)
        self.assertEqual((scheduled.title, scheduled.remind_at), ("reunião", datetime(2026, 10, 25, 16, 0)))

    def test_daily_and_weekly_recurrence(self):
        daily = parse_reminder_command("agende um lembrete para tomar remédio todos os dias às 08h", NOW)
        weekly = parse_reminder_command("agende um lembrete para reunião toda segunda-feira às 9h", NOW)
        self.assertEqual((daily.title, daily.recurrence), ("tomar remédio", "daily"))
        self.assertEqual(daily.remind_at, datetime(2026, 10, 25, 8, 0))
        self.assertEqual((weekly.recurrence, weekly.remind_at), ("weekly", datetime(2026, 10, 26, 9, 0)))

    def test_ambiguous_date_requests_clarification(self):
        command = parse_reminder_command("crie um lembrete para ligar para Maria às 15h", NOW)
        self.assertIn("ambígua", command.error)

    def test_management_commands(self):
        self.assertEqual(parse_reminder_command("mostre os lembretes de hoje", NOW).filter_name, "today")
        self.assertEqual(parse_reminder_command("adie o lembrete 2 por 30 minutos", NOW).postpone_minutes, 30)
        self.assertEqual(parse_reminder_command("conclua o lembrete 4", NOW).action, "complete")
        self.assertEqual(parse_reminder_command("exclua o lembrete 5", NOW).action, "delete")
        edited = parse_reminder_command("edite o lembrete 3 para comprar tinta 25/10/2026 às 10:30", NOW)
        self.assertEqual((edited.title, edited.remind_at), ("comprar tinta", datetime(2026, 10, 25, 10, 30)))
        self.assertIsNone(parse_reminder_command("lembre que trabalho com gráfica", NOW))


class ReminderDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.path = Path(self.temp.name) / "james.db"

    def tearDown(self): self.temp.cleanup()

    def test_existing_minimal_table_is_migrated(self):
        con = sqlite3.connect(self.path)
        try:
            con.execute("CREATE TABLE reminders (id INTEGER PRIMARY KEY,title TEXT NOT NULL,remind_at TEXT NOT NULL,notified INTEGER DEFAULT 0)")
            con.execute("INSERT INTO reminders(title,remind_at) VALUES('Antigo','2026-10-24T12:00:00')")
            con.commit()
        finally:
            con.close()
        db = Database(self.path); row = db.reminders("all")[0]
        self.assertEqual(row["recurrence"], "none"); self.assertEqual(row["completed"], 0)
        self.assertTrue(row["created_at"])

    def test_crud_filters_postpone_and_completion(self):
        db = Database(self.path)
        first = db.add_reminder("Hoje", NOW + timedelta(hours=1))
        recurring = db.add_reminder("Diário", NOW - timedelta(minutes=1), "daily")
        self.assertEqual(len(db.reminders("today", NOW)), 2)
        db.postpone_reminder(first, NOW + timedelta(days=2))
        db.complete_reminder(recurring, NOW)
        self.assertEqual(db.reminder(recurring)["remind_at"], "2026-10-25T09:59:00")
        db.complete_reminder(first, NOW)
        self.assertEqual(len(db.reminders("completed", NOW)), 1)
        self.assertTrue(db.delete_reminder(first))


class ReminderSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.db = Database(Path(self.temp.name) / "james.db"); self.events = []

    def tearDown(self): self.temp.cleanup()

    def test_notification_is_not_duplicated_and_can_be_snoozed(self):
        reminder_id = self.db.add_reminder("Teste", NOW - timedelta(minutes=1))
        notifier = FakeNotifier(); scheduler = ReminderScheduler(self.db, self.events.append, notifier, now_factory=lambda: NOW)
        self.assertEqual(scheduler.check_due(NOW), 1)
        self.assertEqual(scheduler.check_due(NOW), 0)
        notifier.shown[0][1]()
        row = self.db.reminder(reminder_id)
        self.assertEqual(row["notified"], 0)
        self.assertEqual(row["remind_at"], "2026-10-24T10:10:00")

    def test_recurring_notification_persists_next_occurrence(self):
        reminder_id = self.db.add_reminder("Semanal", NOW - timedelta(days=7), "weekly")
        notifier = FakeNotifier(); scheduler = ReminderScheduler(self.db, self.events.append, notifier, now_factory=lambda: NOW)
        self.assertEqual(scheduler.check_due(NOW), 1)
        row = self.db.reminder(reminder_id)
        self.assertGreater(datetime.fromisoformat(row["remind_at"]), NOW)
        self.assertEqual(row["notified"], 0)
        self.assertEqual(scheduler.check_due(NOW), 0)

    def test_failed_notification_is_restored_for_later_retry(self):
        reminder_id = self.db.add_reminder("Falha", NOW - timedelta(minutes=1))
        scheduler = ReminderScheduler(self.db, self.events.append, FakeNotifier(False), now_factory=lambda: NOW)
        self.assertEqual(scheduler.check_due(NOW), 0)
        self.assertEqual(self.db.reminder(reminder_id)["notified"], 0)
        self.assertEqual(self.events[-1].kind, "error")


class NotificationAdapterTests(unittest.TestCase):
    def test_native_buttons_call_only_registered_callbacks(self):
        actions = []

        class Button:
            def __init__(self, _content, arguments): self.arguments = arguments
        class Toast:
            def __init__(self, _fields): self.actions = []; self.tag = "test"
            def AddAction(self, action): self.actions.append(action)
        class Toaster:
            def __init__(self, _name): pass
            def show_toast(self, toast):
                event = type("Event", (), {"arguments": "snooze"})()
                toast.on_activated(event)
        module = type("Module", (), {"Toast": Toast, "ToastButton": Button, "InteractableWindowsToaster": Toaster})
        notifier = WindowsReminderNotifier(lambda *_args, **_kwargs: module)
        result = notifier.show({"id": 1, "title": "Teste"}, lambda: actions.append("snooze"), lambda: actions.append("complete"), actions.append)
        self.assertTrue(result); self.assertEqual(actions, ["snooze"])


class ReminderAssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.settings = Settings(root); self.db = Database(root / "data" / "test.db")
        self.assistant = Assistant(self.db, self.settings)

    def tearDown(self): self.assistant.close(); self.temp.cleanup()

    def test_chat_create_list_and_request_delete_confirmation(self):
        created = self.assistant.process("crie um lembrete para separar os pedidos daqui a 30 minutos")
        self.assertEqual(created.action, "refresh_reminders"); self.assertEqual(len(self.db.reminders()), 1)
        listed = self.assistant.process("mostre meus lembretes")
        self.assertIn("separar os pedidos", listed.text)
        deletion = self.assistant.process("exclua o lembrete 1")
        self.assertEqual(deletion.action, "confirm_delete_reminder")
        self.assertIsNotNone(self.db.reminder(1))


if __name__ == "__main__": unittest.main()
