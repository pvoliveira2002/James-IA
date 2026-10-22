import tempfile
import unittest
from pathlib import Path

from core.context import ConversationContext
from core.router import Intent, IntentRouter
from memory.database import Database


class ContextAndRouterTests(unittest.TestCase):
    def test_context_limits_messages_and_characters(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Database(Path(raw) / "test.db")
            for index in range(8): db.add_conversation("user", f"mensagem-{index}-" + "x" * 20)
            context = ConversationContext(db, max_messages=4, max_chars=80).recent_messages()
            self.assertLessEqual(len(context), 4)
            self.assertLessEqual(sum(len(item["content"]) for item in context), 80)
            self.assertIn("mensagem-7", context[-1]["content"])

    def test_router_distinguishes_conversation_from_real_action(self):
        router = IntentRouter()
        self.assertEqual(router.classify("abra a calculadora"), Intent.LOCAL_ACTION)
        self.assertEqual(router.classify("preciso organizar meus pedidos"), Intent.CONVERSATION)
        self.assertEqual(router.classify("organize os arquivos desta pasta"), Intent.LOCAL_ACTION)
        self.assertEqual(router.classify("como foi seu dia?"), Intent.CONVERSATION)


if __name__ == "__main__": unittest.main()
