import tempfile
import time
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

    def test_router_recognizes_natural_capability_questions(self):
        router = IntentRouter()
        examples = (
            "Quais serviços eu posso pedir pra você, James?",
            "O que você sabe fazer?",
            "Como o James consegue me ajudar?",
            "Quais são suas funcionalidades?",
            "Do que você é capaz?",
        )
        for text in examples:
            self.assertEqual(router.classify(text), Intent.CAPABILITIES, text)
        self.assertTrue(router.is_capability_followup("E quais funcionam sem internet?"))

    def test_context_detects_continuation_reference_and_topic_change(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Database(Path(raw) / "test.db")
            db.add_conversation("user", "Quero organizar os pedidos atrasados")
            db.add_conversation("assistant", "Vamos separar por prazo e cliente.")
            context = ConversationContext(db)
            continued = context.snapshot("E o que faço com isso primeiro?")
            changed = context.snapshot("Agora explique como funciona sublimação")
            self.assertFalse(continued.topic_changed)
            self.assertIn("referência", continued.temporary_note)
            self.assertTrue(changed.topic_changed)

    def test_context_build_is_bounded_and_fast(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Database(Path(raw) / "test.db")
            for index in range(200): db.add_conversation("user" if index % 2 == 0 else "assistant", f"turno {index} " + "x" * 200)
            context = ConversationContext(db, max_messages=10, max_chars=4000)
            started = time.perf_counter(); snapshot = context.snapshot("continue o assunto")
            self.assertLess(time.perf_counter() - started, .25)
            self.assertLessEqual(len(snapshot.messages), 10)
            self.assertLessEqual(sum(len(item["content"]) for item in snapshot.messages), 4000)

    def test_context_retrieves_relevant_authorized_memory_lightly(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Database(Path(raw) / "test.db")
            db.add_memory("Na sublimação de canecas uso 200 graus", "ensinamento")
            db.add_memory("Minha cor favorita é azul")
            context = ConversationContext(db)
            started = time.perf_counter()
            memories = context.authorized_memories("Qual temperatura uso na sublimação?")
            self.assertLess(time.perf_counter() - started, .10)
            self.assertEqual(memories, ["Na sublimação de canecas uso 200 graus"])

    def test_context_is_ordered_deduplicated_and_isolated_by_conversation(self):
        with tempfile.TemporaryDirectory() as raw:
            db = Database(Path(raw) / "test.db")
            db.add_conversation("user", "primeira", "sessao-a")
            db.add_conversation("assistant", "resposta", "sessao-a")
            db.add_conversation("assistant", "resposta", "sessao-a")
            db.add_conversation("user", "segredo de outra conversa", "sessao-b")
            messages = ConversationContext(db, conversation_id="sessao-a").recent_messages()
            self.assertEqual([item["content"] for item in messages], ["primeira", "resposta"])
            self.assertNotIn("segredo de outra conversa", str(messages))


if __name__ == "__main__": unittest.main()
