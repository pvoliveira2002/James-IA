import tempfile
import unittest
from pathlib import Path
from config.settings import Settings
from core.assistant import Assistant
from memory.database import Database
from ai.base import ProviderResponse, ToolCall


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.settings = Settings(root); self.db = Database(root / "data" / "test.db")
        self.assistant = Assistant(self.db, self.settings)

    def tearDown(self): self.temp.cleanup()

    def test_task_commands(self):
        result = self.assistant.process("James, adicione tarefa imprimir fotos")
        self.assertIn("cadastrada", result.text); self.assertEqual(len(self.db.tasks()), 1)
        self.assertIn("imprimir fotos", self.assistant.process("mostre minhas tarefas").text)

    def test_memory_commands(self):
        self.assistant.process("lembre que a loja abre às 7h")
        self.assertIn("7h", self.assistant.process("o que você lembra").text)

    def test_unknown_basic(self):
        self.assertIn("conversação inteligente está indisponível", self.assistant.process("faça algo impossível").text)

    def test_unregistered_folder_is_refused(self):
        result = self.assistant.process("abra a pasta artes")
        self.assertIn("não encontrei", result.text.casefold())

    def test_natural_conversation_is_sent_to_provider_with_context(self):
        class FakeProvider:
            def chat(inner, messages, instructions):
                self.assertTrue(any("como foi seu dia" in m["content"] for m in messages))
                self.assertIn("Você é James", instructions)
                return ProviderResponse("Foi produtivo. Como posso ajudar?")
        self.settings.set("ai_provider", "openai")
        assistant = Assistant(self.db, self.settings, lambda _name: FakeProvider())
        result = assistant.process("James, como foi seu dia?")
        self.assertIn("produtivo", result.text)

    def test_ai_tool_request_is_not_executed_automatically(self):
        class FakeProvider:
            def chat(self, messages, instructions):
                return ProviderResponse(tool_calls=(ToolCall("open_calculator"),))
        self.settings.set("ai_provider", "openai")
        assistant = Assistant(self.db, self.settings, lambda _name: FakeProvider())
        result = assistant.process("Você poderia cuidar daquele cálculo para mim?")
        self.assertEqual(result.action, "confirm_ai_tool")
        self.assertIsInstance(result.payload, ToolCall)

    def test_talking_about_orders_does_not_open_file_organizer(self):
        class FakeProvider:
            def chat(self, messages, instructions):
                return ProviderResponse("Vamos listar os pedidos e os prazos desta semana.")
        self.settings.set("ai_provider", "openai")
        assistant = Assistant(self.db, self.settings, lambda _name: FakeProvider())
        result = assistant.process("James, preciso organizar meus pedidos desta semana.")
        self.assertIsNone(result.action)
        self.assertIn("pedidos", result.text)

    def test_cloud_memories_are_private_by_default(self):
        self.db.add_memory("Dado privado autorizado apenas localmente")
        class FakeProvider:
            def chat(inner, messages, instructions):
                self.assertNotIn("Dado privado", instructions)
                return ProviderResponse("Privacidade preservada.")
        self.settings.set("ai_provider", "openai")
        assistant = Assistant(self.db, self.settings, lambda _name: FakeProvider())
        self.assertIn("preservada", assistant.process("Vamos conversar").text)

    def test_cloud_memories_can_be_explicitly_shared(self):
        self.db.add_memory("A loja abre às 7h")
        self.settings.set("ai_provider", "openai")
        self.settings.set("share_memories_with_openai", True)
        class FakeProvider:
            def chat(inner, messages, instructions):
                self.assertIn("A loja abre às 7h", instructions)
                return ProviderResponse("Entendido.")
        assistant = Assistant(self.db, self.settings, lambda _name: FakeProvider())
        self.assertEqual(assistant.process("Qual o horário?").text, "Entendido.")


if __name__ == "__main__": unittest.main()
