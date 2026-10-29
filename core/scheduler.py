from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from memory.database import Database
from tools.windows_notifications import WindowsReminderNotifier


@dataclass(frozen=True)
class SchedulerEvent:
    kind: str
    message: str = ""
    reminder_id: int | None = None


class ReminderScheduler:
    def __init__(self, database: Database, event_sink: Callable[[SchedulerEvent], None],
                 notifier=None, interval_seconds: float = 15.0,
                 now_factory: Callable[[], datetime] = datetime.now):
        self.db = database
        self._emit = event_sink
        self.notifier = notifier or WindowsReminderNotifier()
        self.interval_seconds = max(2.0, interval_seconds)
        self.now_factory = now_factory
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._failed_until: dict[int, datetime] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive(): return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="james-reminder-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set(); self._wake.set()

    def wake(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.check_due()
            except Exception as exc:
                self._emit(SchedulerEvent("error", f"Falha controlada no agendador: {exc}"))
            self._wake.wait(self.interval_seconds)
            self._wake.clear()

    def check_due(self, now: datetime | None = None) -> int:
        current = now or self.now_factory(); shown = 0
        for row in self.db.due_reminders(current):
            reminder_id = int(row["id"])
            if self._failed_until.get(reminder_id, datetime.min) > current:
                continue
            old_remind_at = str(row["remind_at"])
            if not self.db.mark_reminder_notified(reminder_id, current):
                continue

            def snooze(item_id=reminder_id) -> None:
                self.db.postpone_reminder(item_id, self.now_factory() + timedelta(minutes=10))
                self._emit(SchedulerEvent("refresh", "Lembrete adiado por 10 minutos.", item_id))
                self.wake()

            def complete(item_id=reminder_id) -> None:
                self.db.acknowledge_notification(item_id, self.now_factory())
                self._emit(SchedulerEvent("refresh", "Lembrete concluído.", item_id))

            failure_reported = [False]

            def notification_error(message: str, item_id=reminder_id, original=old_remind_at) -> None:
                if failure_reported[0]: return
                failure_reported[0] = True
                self.db.restore_pending_reminder(item_id, original)
                self._failed_until[item_id] = self.now_factory() + timedelta(minutes=5)
                self._emit(SchedulerEvent("error", message, item_id))

            success = self.notifier.show(
                row, snooze, complete,
                notification_error,
            )
            if not success:
                if not failure_reported[0]: notification_error("Não foi possível exibir a notificação.")
                continue
            shown += 1
            self._emit(SchedulerEvent("notified", str(row["title"]), reminder_id))
        return shown
