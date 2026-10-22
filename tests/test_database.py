import tempfile
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
        self.assertEqual(len(self.db.memories("7h")), 1)
        self.assertTrue(self.db.update_memory(memory_id, "A loja abre às 8h"))
        self.assertTrue(self.db.delete_memory(memory_id))

    def test_conversations(self):
        self.db.add_conversation("user", "Olá")
        self.assertEqual(self.db.conversations()[0]["content"], "Olá")


if __name__ == "__main__": unittest.main()
