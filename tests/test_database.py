import tempfile
import sqlite3
import unittest
from pathlib import Path
from memory.database import Database


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "test.db")

    def tearDown(self): self.temp.cleanup()

    def test_tasks_crud(self):
        task_id = self.db.add_task("Imprimir cartões", "2026-10-23")
        self.assertEqual(self.db.tasks()[0]["title"], "Imprimir cartões")
        self.assertTrue(self.db.complete_task(task_id))
        self.assertEqual(self.db.tasks(), [])

    def test_memories_crud(self):
        memory_id = self.db.add_memory("A loja abre às 7h")
        self.assertEqual(self.db.memory(memory_id)["content"], "A loja abre às 7h")
        self.assertEqual(len(self.db.memories("7h")), 1)
        self.assertTrue(self.db.update_memory(memory_id, "A loja abre às 8h"))
        self.assertTrue(self.db.delete_memory(memory_id))

    def test_conversations(self):
        self.db.add_conversation("user", "Olá")
        self.assertEqual(self.db.conversations()[0]["content"], "Olá")

    def test_conversations_are_scoped(self):
        self.db.add_conversation("user", "Conversa A", "a")
        self.db.add_conversation("user", "Conversa B", "b")
        self.assertEqual([row["content"] for row in self.db.conversations(conversation_id="a")], ["Conversa A"])
        self.assertEqual([row["content"] for row in self.db.conversations(conversation_id="b")], ["Conversa B"])

    def test_existing_conversation_history_is_migrated_to_default_scope(self):
        legacy_path = Path(self.temp.name) / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        try:
            connection.execute("CREATE TABLE conversations(id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            connection.execute("INSERT INTO conversations(role,content) VALUES('user','histórico preservado')")
            connection.commit()
        finally:
            connection.close()
        migrated = Database(legacy_path)
        row = migrated.conversations()[0]
        self.assertEqual(row["content"], "histórico preservado")
        self.assertEqual(row["conversation_id"], "default")


if __name__ == "__main__": unittest.main()
