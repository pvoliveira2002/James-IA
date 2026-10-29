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
                self.assertIn("responda à intenção da última mensagem", instructions)
                self.assertIn("Só cumprimente quando", instructions)
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

    def test_streaming_keeps_continuity_and_emits_progress(self):
        self.db.add_conversation("user", "Quero melhorar a divulgação da loja")
        self.db.add_conversation("assistant", "Podemos começar pelas redes sociais.")
        chunks = []
        class FakeProvider:
            def chat_stream(inner, messages, instructions, on_delta):
                self.assertTrue(any("divulgação" in item["content"] for item in messages))
                self.assertTrue(any("E por onde começo" in item["content"] for item in messages))
                self.assertIn("contexto temporário", instructions)
                on_delta("Comece "); on_delta("pelo catálogo.")
                return ProviderResponse("Comece pelo catálogo.")
        self.settings.set("ai_provider", "openai")
        assistant = Assistant(self.db, self.settings, lambda _name: FakeProvider())
        result = assistant.process("E por onde começo?", on_delta=chunks.append)
        self.assertEqual(chunks, ["Comece ", "pelo catálogo."])
        self.assertEqual(result.text, "Comece pelo catálogo.")

    def test_stream_failure_is_reported_without_inventing_result(self):
        class FakeProvider:
            def chat_stream(self, messages, instructions, on_delta):
                on_delta("Resposta parcial")
                raise RuntimeError("modelo interrompido")
        self.settings.set("ai_provider", "openai")
        assistant = Assistant(self.db, self.settings, lambda _name: FakeProvider())
        with self.assertLogs("core.assistant", level="WARNING") as captured:
            result = assistant.process("Continue", on_delta=lambda _part: None)
        self.assertIn("modelo interrompido", result.text)
        self.assertIn("error_type=RuntimeError", " ".join(captured.output))
        self.assertNotIn("modelo interrompido", " ".join(captured.output))

    def test_only_explicit_authorization_creates_persistent_memory(self):
        class FakeProvider:
            def chat(self, messages, instructions): return ProviderResponse("Entendi, sem memorizar.")
        self.settings.set("ai_provider", "openai")
        assistant = Assistant(self.db, self.settings, lambda _name: FakeProvider())
        assistant.process("Minha cor favorita é azul")
        self.assertEqual(self.db.memories(), [])
        assistant.process("Pode guardar que minha cor favorita é azul")
        self.assertEqual(len(self.db.memories()), 1)

    def test_authorized_teaching_correction_and_confirmed_deletion(self):
        taught = self.assistant.process("Aprenda que uso papel premium nas canecas")
        memory_id = int(self.db.memories()[0]["id"])
        self.assertEqual(taught.status, "executed")
        self.assertEqual(self.db.memory(memory_id)["category"], "ensinamento")
        corrected = self.assistant.process(f"Corrija a memória #{memory_id} para uso papel sublimático nas canecas")
        self.assertEqual(corrected.status, "executed")
        self.assertIn("sublimático", self.db.memory(memory_id)["content"])
        pending = self.assistant.process(f"Apague a memória #{memory_id}")
        self.assertEqual((pending.action, pending.status), ("confirm_delete_memory", "confirmation"))
        self.assertIsNotNone(self.db.memory(memory_id))
        deleted = self.assistant.process("sim")
        self.assertEqual(deleted.status, "executed")
        self.assertIsNone(self.db.memory(memory_id))

    def test_relevant_memory_is_used_without_unrelated_prompt_bloat(self):
        self.db.add_memory("Na sublimação uso 200 graus")
        self.db.add_memory("Minha cor favorita é azul")
        class FakeProvider:
            def chat(inner, messages, instructions):
                self.assertIn("Na sublimação uso 200 graus", instructions)
                self.assertNotIn("Minha cor favorita", instructions)
                return ProviderResponse("Use a configuração autorizada.")
        self.settings.set("ai_provider", "ollama")
        assistant = Assistant(self.db, self.settings, lambda _name: FakeProvider())
        FakeProvider.available = lambda _self: True
        self.assertIn("autorizada", assistant.process("Qual temperatura uso na sublimação?").text)

    def test_memory_delete_can_be_cancelled_contextually(self):
        memory_id = self.db.add_memory("Informação temporária")
        self.assistant.process(f"Exclua a memória {memory_id}")
        cancelled = self.assistant.process("não")
        self.assertIsNotNone(self.db.memory(memory_id))
        self.assertIn("cancelada", cancelled.text.casefold())

    def test_denied_command_is_an_explicit_error_and_never_executes(self):
        permissions = dict(self.settings.get("permissions"))
        permissions["open_calculator"] = False
        self.settings.set("permissions", permissions)
        assistant = Assistant(self.db, self.settings)
        result = assistant.process("Abra a calculadora")
        self.assertEqual(result.status, "error")
        self.assertIn("desativada", result.text.casefold())

    def test_capabilities_are_local_specific_and_not_a_generic_greeting(self):
        result = self.assistant.process("Quais serviços eu posso pedir pra você, James?")
        self.assertIn("Você pode me pedir, agora", result.text)
        self.assertIn("tarefas", result.text)
        self.assertIn("aplicativos", result.text)
        self.assertIn("Ainda não implementado", result.text)
        self.assertNotIn("Como posso te ajudar", result.text)

    def test_objective_question_with_greeting_is_not_reduced_to_greeting(self):
        result = self.assistant.process("Olá, quais são suas funcionalidades?")
        self.assertIn("Você pode me pedir", result.text)
        self.assertNotIn("Estou pronto", result.text)

    def test_capability_followup_and_subject_change(self):
        self.assistant.process("O que você sabe fazer?")
        followup = self.assistant.process("E quais funcionam sem internet?")
        self.assertIn("Sem internet", followup.text)

        class FakeProvider:
            def chat(self, messages, instructions): return ProviderResponse("Sublimação usa calor e pressão.")
        self.settings.set("ai_provider", "openai")
        assistant = Assistant(self.db, self.settings, lambda _name: FakeProvider())
        assistant.process("Quais são seus recursos?")
        changed = assistant.process("Agora explique como funciona sublimação")
        self.assertIn("calor", changed.text)

    def test_duplicate_current_message_reaches_provider_once_and_diagnostics_hide_text(self):
        message = "Dado pessoal exclusivo 92831"
        self.db.add_conversation("user", message)
        self.db.add_conversation("user", message)
        class FakeProvider:
            def chat(inner, messages, instructions):
                self.assertEqual(sum(item["content"] == message for item in messages), 1)
                return ProviderResponse("Entendido.")
        self.settings.set("ai_provider", "openai")
        assistant = Assistant(self.db, self.settings, lambda _name: FakeProvider())
        with self.assertLogs("core.assistant", level="INFO") as captured:
            assistant.process(message)
        diagnostics = " ".join(captured.output)
        self.assertIn("intent=conversation", diagnostics)
        self.assertIn("provider=openai", diagnostics)
        self.assertNotIn("92831", diagnostics)


if __name__ == "__main__": unittest.main()
