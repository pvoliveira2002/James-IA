from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
 id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL,
 conversation_id TEXT NOT NULL DEFAULT 'default',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS tasks (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, due_date TEXT, priority TEXT DEFAULT 'normal',
 completed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS memories (
 id INTEGER PRIMARY KEY, content TEXT NOT NULL, category TEXT DEFAULT 'geral',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS action_log (
 id INTEGER PRIMARY KEY, action TEXT NOT NULL, details TEXT, authorized INTEGER NOT NULL,
 success INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reminders (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, remind_at TEXT NOT NULL,
 recurrence TEXT NOT NULL DEFAULT 'none', completed INTEGER NOT NULL DEFAULT 0,
 notified INTEGER NOT NULL DEFAULT 0, last_notified_at TEXT, last_completed_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS store_info (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders (
 id INTEGER PRIMARY KEY, customer TEXT NOT NULL, service TEXT NOT NULL, status TEXT DEFAULT 'pendente',
 due_date TEXT, price REAL, notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS applications (
 id TEXT PRIMARY KEY, display_name TEXT NOT NULL, normalized_name TEXT NOT NULL,
 launch_target TEXT, app_user_model_id TEXT, app_type TEXT NOT NULL,
 discovery_source TEXT NOT NULL, icon_path TEXT, last_verified TEXT NOT NULL,
 is_available INTEGER NOT NULL DEFAULT 1, is_favorite INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_applications_normalized ON applications(normalized_name);
CREATE TABLE IF NOT EXISTS application_aliases (
 id INTEGER PRIMARY KEY, application_id TEXT NOT NULL, alias TEXT NOT NULL,
 normalized_alias TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(application_id) REFERENCES applications(id)
);
CREATE TABLE IF NOT EXISTS application_permissions (
 application_id TEXT PRIMARY KEY, decision TEXT NOT NULL,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(application_id) REFERENCES applications(id)
);
CREATE TABLE IF NOT EXISTS application_launch_history (
 id INTEGER PRIMARY KEY, application_id TEXT NOT NULL, success INTEGER NOT NULL,
 details TEXT, opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(application_id) REFERENCES applications(id)
);
CREATE TABLE IF NOT EXISTS application_associations (
 phrase TEXT PRIMARY KEY, normalized_phrase TEXT NOT NULL, application_id TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(application_id) REFERENCES applications(id)
);
CREATE TABLE IF NOT EXISTS websites (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, normalized_name TEXT NOT NULL UNIQUE,
 url TEXT NOT NULL, favorite INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS website_aliases (
 id INTEGER PRIMARY KEY, website_id INTEGER NOT NULL, alias TEXT NOT NULL,
 normalized_alias TEXT NOT NULL UNIQUE, FOREIGN KEY(website_id) REFERENCES websites(id)
);
CREATE TABLE IF NOT EXISTS automation_runs (
 id INTEGER PRIMARY KEY, objective TEXT NOT NULL, status TEXT NOT NULL,
 current_site TEXT, result TEXT, error TEXT, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 finished_at TEXT
);
CREATE TABLE IF NOT EXISTS automation_steps (
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, step_index INTEGER NOT NULL,
 description TEXT NOT NULL, status TEXT NOT NULL, details TEXT,
 started_at TEXT, finished_at TEXT, FOREIGN KEY(run_id) REFERENCES automation_runs(id)
);
CREATE TABLE IF NOT EXISTS navigation_history (
 id INTEGER PRIMARY KEY, url TEXT NOT NULL, title TEXT, action TEXT NOT NULL,
 success INTEGER NOT NULL, details TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate_conversations(connection)
            self._migrate_reminders(connection)

    @staticmethod
    def _migrate_conversations(connection: sqlite3.Connection) -> None:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(conversations)")}
        if "conversation_id" not in columns:
            connection.execute("ALTER TABLE conversations ADD COLUMN conversation_id TEXT NOT NULL DEFAULT 'default'")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_conversations_scope ON conversations(conversation_id,id)")

    @staticmethod
    def _migrate_reminders(connection: sqlite3.Connection) -> None:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(reminders)")}
        additions = {
            "recurrence": "TEXT NOT NULL DEFAULT 'none'",
            "completed": "INTEGER NOT NULL DEFAULT 0",
            "last_notified_at": "TEXT",
            "last_completed_at": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE reminders ADD COLUMN {name} {definition}")
        now = datetime.now().isoformat(timespec="seconds")
        connection.execute("UPDATE reminders SET created_at=COALESCE(created_at,?),updated_at=COALESCE(updated_at,?)", (now, now))
        connection.execute("CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(completed,notified,remind_at)")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def add_conversation(self, role: str, content: str, conversation_id: str = "default") -> int:
        if role not in {"user", "assistant"}:
            raise ValueError("papel de conversa inválido")
        scope = conversation_id.strip()[:80] or "default"
        with self.connect() as con:
            cur = con.execute("INSERT INTO conversations(role,content,conversation_id) VALUES(?,?,?)", (role, content, scope))
            return int(cur.lastrowid)

    def conversations(self, limit: int = 100, conversation_id: str = "default") -> list[sqlite3.Row]:
        scope = conversation_id.strip()[:80] or "default"
        with self.connect() as con:
            return list(con.execute(
                "SELECT * FROM (SELECT * FROM conversations WHERE conversation_id=? ORDER BY id DESC LIMIT ?) ORDER BY id",
                (scope, limit),
            ))

    def add_task(self, title: str, due_date: str | None = None, priority: str = "normal") -> int:
        with self.connect() as con:
            cur = con.execute("INSERT INTO tasks(title,due_date,priority) VALUES(?,?,?)", (title, due_date, priority))
            return int(cur.lastrowid)

    def tasks(self, include_completed: bool = False) -> list[sqlite3.Row]:
        query = "SELECT * FROM tasks" + ("" if include_completed else " WHERE completed=0") + " ORDER BY due_date IS NULL,due_date,id"
        with self.connect() as con:
            return list(con.execute(query))

    def complete_task(self, task_id: int) -> bool:
        with self.connect() as con:
            return con.execute("UPDATE tasks SET completed=1 WHERE id=?", (task_id,)).rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        with self.connect() as con:
            return con.execute("DELETE FROM tasks WHERE id=?", (task_id,)).rowcount > 0

    def add_reminder(self, title: str, remind_at: datetime | str, recurrence: str = "none") -> int:
        when = remind_at.isoformat(timespec="seconds") if isinstance(remind_at, datetime) else str(remind_at)
        recurrence = recurrence if recurrence in ("none", "daily", "weekly") else "none"
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as con:
            cur = con.execute(
                "INSERT INTO reminders(title,remind_at,recurrence,created_at,updated_at) VALUES(?,?,?,?,?)",
                (title.strip(), when, recurrence, now, now),
            )
            return int(cur.lastrowid)

    def reminder(self, reminder_id: int) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()

    def reminders(self, filter_name: str = "upcoming", now: datetime | None = None) -> list[sqlite3.Row]:
        current = (now or datetime.now()).isoformat(timespec="seconds")
        today = current[:10]
        clauses = {
            "today": ("completed=0 AND substr(remind_at,1,10)=?", (today,)),
            "upcoming": ("completed=0", ()),
            "recurring": ("completed=0 AND recurrence!='none'", ()),
            "completed": ("completed=1", ()),
            "all": ("1=1", ()),
        }
        where, values = clauses.get(filter_name, clauses["upcoming"])
        with self.connect() as con:
            return list(con.execute(f"SELECT * FROM reminders WHERE {where} ORDER BY completed,remind_at,id", values))

    def update_reminder(self, reminder_id: int, title: str | None = None,
                        remind_at: datetime | str | None = None, recurrence: str | None = None) -> bool:
        fields, values = [], []
        if title is not None:
            fields.append("title=?"); values.append(title.strip())
        if remind_at is not None:
            when = remind_at.isoformat(timespec="seconds") if isinstance(remind_at, datetime) else str(remind_at)
            fields.extend(("remind_at=?", "notified=0", "completed=0")); values.append(when)
        if recurrence is not None:
            fields.append("recurrence=?"); values.append(recurrence if recurrence in ("none", "daily", "weekly") else "none")
        if not fields: return False
        fields.append("updated_at=?"); values.append(datetime.now().isoformat(timespec="seconds")); values.append(reminder_id)
        with self.connect() as con:
            return con.execute(f"UPDATE reminders SET {','.join(fields)} WHERE id=?", values).rowcount > 0

    @staticmethod
    def _next_occurrence(remind_at: str, recurrence: str, now: datetime) -> datetime:
        current = datetime.fromisoformat(remind_at)
        step = timedelta(days=1 if recurrence == "daily" else 7)
        while current <= now: current += step
        return current

    def complete_reminder(self, reminder_id: int, now: datetime | None = None) -> bool:
        current = now or datetime.now(); row = self.reminder(reminder_id)
        if not row: return False
        stamp = current.isoformat(timespec="seconds")
        with self.connect() as con:
            if row["recurrence"] in ("daily", "weekly"):
                next_at = self._next_occurrence(row["remind_at"], row["recurrence"], current)
                return con.execute(
                    "UPDATE reminders SET remind_at=?,notified=0,last_completed_at=?,updated_at=? WHERE id=?",
                    (next_at.isoformat(timespec="seconds"), stamp, stamp, reminder_id),
                ).rowcount > 0
            return con.execute(
                "UPDATE reminders SET completed=1,last_completed_at=?,updated_at=? WHERE id=?",
                (stamp, stamp, reminder_id),
            ).rowcount > 0

    def acknowledge_notification(self, reminder_id: int, now: datetime | None = None) -> bool:
        row = self.reminder(reminder_id)
        if not row: return False
        if row["recurrence"] in ("daily", "weekly"): return True
        return self.complete_reminder(reminder_id, now)

    def postpone_reminder(self, reminder_id: int, remind_at: datetime) -> bool:
        return self.update_reminder(reminder_id, remind_at=remind_at)

    def delete_reminder(self, reminder_id: int) -> bool:
        with self.connect() as con:
            return con.execute("DELETE FROM reminders WHERE id=?", (reminder_id,)).rowcount > 0

    def due_reminders(self, now: datetime | None = None) -> list[sqlite3.Row]:
        current = (now or datetime.now()).isoformat(timespec="seconds")
        with self.connect() as con:
            return list(con.execute(
                "SELECT * FROM reminders WHERE completed=0 AND notified=0 AND remind_at<=? ORDER BY remind_at,id", (current,)
            ))

    def mark_reminder_notified(self, reminder_id: int, now: datetime | None = None) -> bool:
        current = now or datetime.now(); row = self.reminder(reminder_id)
        if not row or row["completed"] or row["notified"]: return False
        stamp = current.isoformat(timespec="seconds")
        with self.connect() as con:
            if row["recurrence"] in ("daily", "weekly"):
                next_at = self._next_occurrence(row["remind_at"], row["recurrence"], current)
                return con.execute(
                    "UPDATE reminders SET remind_at=?,notified=0,last_notified_at=?,updated_at=? WHERE id=? AND notified=0",
                    (next_at.isoformat(timespec="seconds"), stamp, stamp, reminder_id),
                ).rowcount > 0
            return con.execute(
                "UPDATE reminders SET notified=1,last_notified_at=?,updated_at=? WHERE id=? AND notified=0",
                (stamp, stamp, reminder_id),
            ).rowcount > 0

    def restore_pending_reminder(self, reminder_id: int, remind_at: str) -> bool:
        with self.connect() as con:
            return con.execute(
                "UPDATE reminders SET remind_at=?,notified=0,last_notified_at=NULL,updated_at=? WHERE id=? AND completed=0",
                (remind_at, datetime.now().isoformat(timespec="seconds"), reminder_id),
            ).rowcount > 0

    def add_memory(self, content: str, category: str = "geral") -> int:
        with self.connect() as con:
            cur = con.execute("INSERT INTO memories(content,category) VALUES(?,?)", (content, category))
            return int(cur.lastrowid)

    def memories(self, search: str = "") -> list[sqlite3.Row]:
        with self.connect() as con:
            if search:
                return list(con.execute("SELECT * FROM memories WHERE content LIKE ? ORDER BY id DESC", (f"%{search}%",)))
            return list(con.execute("SELECT * FROM memories ORDER BY id DESC"))

    def memory(self, memory_id: int) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()

    def update_memory(self, memory_id: int, content: str) -> bool:
        with self.connect() as con:
            return con.execute(
                "UPDATE memories SET content=?,updated_at=? WHERE id=?",
                (content, datetime.now().isoformat(timespec="seconds"), memory_id),
            ).rowcount > 0

    def delete_memory(self, memory_id: int) -> bool:
        with self.connect() as con:
            return con.execute("DELETE FROM memories WHERE id=?", (memory_id,)).rowcount > 0

    def log_action(self, action: str, details: str, authorized: bool, success: bool) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO action_log(action,details,authorized,success) VALUES(?,?,?,?)",
                        (action, details, int(authorized), int(success)))

    def recent_actions(self, limit: int = 8) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute("SELECT * FROM action_log ORDER BY id DESC LIMIT ?", (limit,)))

    def counts(self) -> dict[str, int]:
        with self.connect() as con:
            return {
                "tasks": int(con.execute("SELECT COUNT(*) FROM tasks WHERE completed=0").fetchone()[0]),
                "memories": int(con.execute("SELECT COUNT(*) FROM memories").fetchone()[0]),
                "conversations": int(con.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]),
            }

    def replace_discovered_applications(self, apps: list[dict]) -> int:
        """Atualiza o cache sem remover aplicativos manuais nem histórico."""
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as con:
            con.execute("UPDATE applications SET is_available=0 WHERE discovery_source!='manual'")
            for app in apps:
                con.execute("""INSERT INTO applications
                    (id,display_name,normalized_name,launch_target,app_user_model_id,app_type,
                     discovery_source,icon_path,last_verified,is_available)
                    VALUES(?,?,?,?,?,?,?,?,?,1)
                    ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,
                    normalized_name=excluded.normalized_name,launch_target=excluded.launch_target,
                    app_user_model_id=excluded.app_user_model_id,app_type=excluded.app_type,
                    discovery_source=excluded.discovery_source,icon_path=excluded.icon_path,
                    last_verified=excluded.last_verified,is_available=1""",
                    (app["id"], app["display_name"], app["normalized_name"], app.get("launch_target"),
                     app.get("app_user_model_id"), app["app_type"], app["discovery_source"],
                     app.get("icon_path"), now))
        return len(apps)

    def applications(self, search: str = "", available_only: bool = True) -> list[sqlite3.Row]:
        clauses, values = [], []
        if available_only: clauses.append("is_available=1")
        if search:
            clauses.append("(normalized_name LIKE ? OR display_name LIKE ?)")
            values.extend((f"%{search}%", f"%{search}%"))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as con:
            return list(con.execute("SELECT * FROM applications" + where + " ORDER BY is_favorite DESC,display_name", values))

    def get_application(self, app_id: str) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute("SELECT * FROM applications WHERE id=? AND is_available=1", (app_id,)).fetchone()

    def add_manual_application(self, app: dict) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.connect() as con:
            con.execute("""INSERT INTO applications
                (id,display_name,normalized_name,launch_target,app_user_model_id,app_type,
                 discovery_source,icon_path,last_verified,is_available)
                VALUES(?,?,?,?,?,?,?,?,?,1)
                ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,
                normalized_name=excluded.normalized_name,launch_target=excluded.launch_target,
                icon_path=excluded.icon_path,last_verified=excluded.last_verified,is_available=1""",
                (app["id"], app["display_name"], app["normalized_name"], app.get("launch_target"),
                 app.get("app_user_model_id"), "portable", "manual", app.get("icon_path"), now))

    def set_application_alias(self, app_id: str, alias: str, normalized_alias: str) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO application_aliases(application_id,alias,normalized_alias) VALUES(?,?,?) ON CONFLICT(normalized_alias) DO UPDATE SET application_id=excluded.application_id,alias=excluded.alias", (app_id, alias, normalized_alias))

    def application_aliases(self) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute("SELECT * FROM application_aliases"))

    def set_application_permission(self, app_id: str, decision: str) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO application_permissions(application_id,decision) VALUES(?,?) ON CONFLICT(application_id) DO UPDATE SET decision=excluded.decision,updated_at=CURRENT_TIMESTAMP", (app_id, decision))

    def application_permission(self, app_id: str) -> str | None:
        with self.connect() as con:
            row = con.execute("SELECT decision FROM application_permissions WHERE application_id=?", (app_id,)).fetchone()
            return str(row[0]) if row else None

    def clear_application_permission(self, app_id: str) -> None:
        with self.connect() as con:
            con.execute("DELETE FROM application_permissions WHERE application_id=?", (app_id,))

    def log_application_launch(self, app_id: str, success: bool, details: str) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO application_launch_history(application_id,success,details) VALUES(?,?,?)", (app_id, int(success), details[:500]))

    def application_launch_history(self, limit: int = 30) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute("""SELECT h.*,a.display_name FROM application_launch_history h
                JOIN applications a ON a.id=h.application_id ORDER BY h.id DESC LIMIT ?""", (limit,)))

    def set_application_favorite(self, app_id: str, favorite: bool) -> None:
        with self.connect() as con:
            con.execute("UPDATE applications SET is_favorite=? WHERE id=?", (int(favorite), app_id))

    def seed_websites(self, sites: list[dict]) -> None:
        with self.connect() as con:
            for site in sites:
                con.execute("INSERT INTO websites(name,normalized_name,url,favorite) VALUES(?,?,?,?) ON CONFLICT(normalized_name) DO UPDATE SET url=excluded.url",
                            (site["name"], site["normalized_name"], site["url"], int(site.get("favorite", False))))
                site_id = con.execute("SELECT id FROM websites WHERE normalized_name=?", (site["normalized_name"],)).fetchone()[0]
                for alias in site.get("aliases", []):
                    con.execute("INSERT INTO website_aliases(website_id,alias,normalized_alias) VALUES(?,?,?) ON CONFLICT(normalized_alias) DO UPDATE SET website_id=excluded.website_id",
                                (site_id, alias, alias.casefold()))

    def websites(self) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute("SELECT * FROM websites WHERE enabled=1 ORDER BY favorite DESC,name"))

    def website_aliases(self) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute("SELECT a.*,w.name,w.url FROM website_aliases a JOIN websites w ON w.id=a.website_id WHERE w.enabled=1"))

    def start_automation(self, objective: str) -> int:
        with self.connect() as con:
            return int(con.execute("INSERT INTO automation_runs(objective,status) VALUES(?,'executando')", (objective,)).lastrowid)

    def add_automation_step(self, run_id: int, index: int, description: str, status: str = "pendente") -> int:
        with self.connect() as con:
            return int(con.execute("INSERT INTO automation_steps(run_id,step_index,description,status) VALUES(?,?,?,?)", (run_id,index,description,status)).lastrowid)

    def update_automation_step(self, step_id: int, status: str, details: str = "") -> None:
        with self.connect() as con:
            con.execute("UPDATE automation_steps SET status=?,details=?,started_at=COALESCE(started_at,CURRENT_TIMESTAMP),finished_at=CASE WHEN ? IN ('concluido','erro','cancelado') THEN CURRENT_TIMESTAMP ELSE finished_at END WHERE id=?", (status,details[:1000],status,step_id))

    def finish_automation(self, run_id: int, status: str, result: str = "", error: str = "") -> None:
        with self.connect() as con:
            con.execute("UPDATE automation_runs SET status=?,result=?,error=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (status,result[:2000],error[:1000],run_id))

    def automation_runs(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute("SELECT * FROM automation_runs ORDER BY id DESC LIMIT ?", (limit,)))

    def automation_steps(self, run_id: int) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute("SELECT * FROM automation_steps WHERE run_id=? ORDER BY step_index", (run_id,)))

    def log_navigation(self, url: str, title: str, action: str, success: bool, details: str = "") -> None:
        with self.connect() as con:
            con.execute("INSERT INTO navigation_history(url,title,action,success,details) VALUES(?,?,?,?,?)", (url,title,action,int(success),details[:1000]))

    def navigation_history(self, limit: int = 30) -> list[sqlite3.Row]:
        with self.connect() as con:
            return list(con.execute("SELECT * FROM navigation_history ORDER BY id DESC LIMIT ?", (limit,)))
