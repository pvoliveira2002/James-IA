from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ai.base import ProviderResponse, ToolCall
from ai.ollama import OllamaProvider
from ai.openai_provider import OpenAIProvider
from config.settings import Settings
from core.context import ConversationContext
from core.reminder_parser import ReminderCommand, parse_reminder_command
from core.router import Intent, IntentRouter
from memory.database import Database
from security.policy import SecurityPolicy
from tools import windows
from tools.application_launcher import ApplicationLauncherService
from tools.application_matcher import ApplicationMatcher
from tools.application_discovery import normalize_app_name
from tools.browser_automation import BrowserAutomationService
from core.orchestrator import AgentOrchestrator


logger = logging.getLogger(__name__)


@dataclass
class AssistantResponse:
    text: str
    action: str | None = None
    payload: object | None = None
    status: str = "ready"


@dataclass(frozen=True)
class PendingOpenAction:
    kind: str
    target: str
    label: str


class Assistant:
    def __init__(self, database: Database, settings: Settings,
                 provider_factory: Callable[[str], object] | None = None,
                 conversation_id: str = "default"):
        self.db = database
        self.settings = settings
        self.conversation_id = conversation_id.strip()[:80] or "default"
        self.policy = SecurityPolicy(settings)
        self.router = IntentRouter()
        self.context = ConversationContext(
            database, int(settings.get("context_max_messages", 12)),
            int(settings.get("context_max_chars", 8000)), self.conversation_id)
        self.provider_factory = provider_factory
        self._last_provider_status: dict[str, tuple[bool, str]] = {}
        self.app_matcher = ApplicationMatcher(database)
        self.app_launcher = ApplicationLauncherService(database)
        self.browser = BrowserAutomationService(settings.data_dir / "browser_profile", database)
        self.orchestrator = AgentOrchestrator(database, self.browser)
        self._pending_open: PendingOpenAction | None = None
        self._pending_memory_delete: int | None = None
        self._chatgpt_catalog_checked = False
        self._last_local_topic: str | None = None

    def process(self, original: str, on_delta: Callable[[str], None] | None = None) -> AssistantResponse:
        text = original.strip()
        clean = re.sub(r"^(james|jarvis)[,\s:]+", "", text, flags=re.I).strip()
        low = clean.casefold()
        if not clean:
            return AssistantResponse("Digite um comando para eu ajudar.")
        intent = self.router.classify(clean)
        provider_name = str(self.settings.get("ai_provider", "basic"))
        logger.info("route intent=%s provider=%s chars=%d", intent.value, provider_name, len(clean))
        capability_followup = self._last_local_topic == "capabilities" and self.router.is_capability_followup(clean)
        if intent == Intent.CAPABILITIES or capability_followup:
            self._last_local_topic = "capabilities"
            return AssistantResponse(self.capabilities_text(clean))
        self._last_local_topic = None
        confirmation = normalize_app_name(clean)
        if confirmation in {"nao", "cancelar", "cancele", "deixa"} and (self._pending_open or self._pending_memory_delete):
            self.cancel_pending_actions()
            return AssistantResponse("Ação cancelada. Nada foi alterado ou aberto.")
        if confirmation in {"abrir", "abra", "sim", "confirmar", "confirme", "pode abrir"}:
            if self._pending_memory_delete is not None:
                return self.confirm_pending_memory_delete()
            return self.confirm_pending_open()
        reminder_command = parse_reminder_command(clean)
        if reminder_command:
            return self._handle_reminder(reminder_command)
        if self._is_chatgpt_open_request(clean):
            return self._request_chatgpt()
        if self.settings.permission("public_web_navigation") and self.settings.permission("browser_automation"):
            navigation = self.orchestrator.handle(clean)
            if navigation.handled:
                return AssistantResponse(navigation.text, action="refresh_automations", payload=navigation.run_id,
                                         status=self._automation_status())
        if re.search(r"\b(ajuda|comandos)\b", low):
            return AssistantResponse(self.help_text())
        if "calculadora" in low and re.search(r"\b(abra|abrir|inicie)\b", low):
            return self._run_tool("open_calculator", "Abrindo a calculadora.", lambda: windows.open_program("calculator"))
        if ("bloco de notas" in low or "notepad" in low) and re.search(r"\b(abra|abrir|inicie)\b", low):
            return self._run_tool("open_notepad", "Abrindo o Bloco de Notas.", lambda: windows.open_program("notepad"))
        if "navegador" in low and re.search(r"\b(abra|abrir|inicie)\b", low):
            return self._run_tool("open_browser", "Abrindo o navegador.", windows.open_browser)
        folder_match = re.match(r"(?:abra|abrir) (?:minha |a )?pasta(?: de)?\s+(.+)", clean, re.I)
        if folder_match:
            allowed, reason = self.policy.require_permission("open_directory")
            if not allowed:
                return AssistantResponse(reason, status="error")
            wanted = folder_match.group(1).strip().casefold()
            matches = [p for p in self.settings.allowed_directories
                       if wanted in p.name.casefold() or wanted in str(p).casefold()]
            if not matches:
                return AssistantResponse("Não encontrei essa pasta entre os diretórios autorizados nas Configurações.", status="error")
            success, details = windows.open_directory(matches[0])
            self.db.log_action("open_directory", str(matches[0]), True, success)
            return AssistantResponse(details, status="requested" if success else "error")
        if "informações do computador" in low or "informacoes do computador" in low or "sistema" == low:
            allowed, reason = self.policy.require_permission("system_info")
            return AssistantResponse(windows.system_info() if allowed else reason)
        task_match = re.match(r"(?:adicione|crie|cadastrar?|nova) (?:uma )?tarefa[: ]+(.+)", clean, re.I)
        if task_match:
            title = task_match.group(1).strip()
            self.db.add_task(title)
            return AssistantResponse(f"Tarefa cadastrada: {title}", action="refresh_tasks", status="executed")
        if "tarefas" in low and re.search(r"\b(mostre|listar?|quais|consultar?)\b", low):
            tasks = self.db.tasks()
            if not tasks:
                return AssistantResponse("Você não possui tarefas pendentes.")
            return AssistantResponse("Tarefas pendentes:\n" + "\n".join(f"• #{row['id']} {row['title']}" for row in tasks))
        memory_edit = re.match(
            r"(?:corrija|corrigir|atualize|atualizar|edite|editar)\s+(?:a\s+)?mem[oó]ria\s*#?(\d+)\s*(?:para|:|como)\s+(.+)",
            clean, re.I,
        )
        if memory_edit:
            memory_id, content = int(memory_edit.group(1)), memory_edit.group(2).strip()
            if not self.db.memory(memory_id):
                return AssistantResponse("Não encontrei essa memória; nenhuma informação foi alterada.", status="error")
            self.db.update_memory(memory_id, content)
            return AssistantResponse(
                f"Memória #{memory_id} corrigida com sua autorização: {content}",
                action="refresh_memories", status="executed",
            )
        memory_delete = re.match(
            r"(?:apague|apagar|exclua|excluir|esque[cç]a)\s+(?:a\s+)?mem[oó]ria\s*#?(\d+)\s*[.!?]*$",
            clean, re.I,
        )
        if memory_delete:
            memory_id = int(memory_delete.group(1))
            row = self.db.memory(memory_id)
            if not row:
                return AssistantResponse("Não encontrei essa memória; nada foi excluído.", status="error")
            self._pending_memory_delete = memory_id
            return AssistantResponse(
                f"Confirme a exclusão da memória #{memory_id}: {row['content']}",
                action="confirm_delete_memory", payload=memory_id, status="confirmation",
            )
        memory_match = re.match(
            r"(?:(?:por favor|(?:voc[eê]\s+)?pode),?\s+)?"
            r"(?:lembre|lembrar|memorize|memorizar|guarde|guardar|salve|salvar|aprenda|aprender|ensine|ensinar)"
            r"(?:\s+(?:esta\s+)?corre[cç][aã]o)?(?: que)?[: ]+(.+)", clean, re.I,
        )
        if memory_match:
            content = memory_match.group(1).strip()
            duplicate = next((row for row in self.db.memories() if str(row["content"]).casefold() == content.casefold()), None)
            if duplicate:
                return AssistantResponse(f"Essa informação já está na memória #{duplicate['id']}; não criei uma cópia.")
            category = "ensinamento" if re.search(r"\b(aprenda|aprender|ensine|ensinar|corre[cç][aã]o)\b", clean, re.I) else "geral"
            memory_id = self.db.add_memory(content, category)
            return AssistantResponse(
                f"Informação guardada com sua autorização na memória #{memory_id}: {content}",
                action="refresh_memories", status="executed",
            )
        if re.search(r"\b(o que você lembra|memórias|memorias)\b", low):
            memories = self.db.memories()
            return AssistantResponse("Ainda não há memórias cadastradas." if not memories else
                                     "Memórias:\n" + "\n".join(f"• #{m['id']} {m['content']}" for m in memories[:20]))
        if re.search(r"\b(organize|organizar)\b", low) and re.search(r"\b(arquivos?|documentos?|pasta)\b", low):
            return AssistantResponse("Escolha uma pasta autorizada para visualizar a organização.", action="organize")
        if re.search(r"\b(procure|localize|buscar arquivo)\b", low):
            query = re.sub(r"^(procure|localize)(?: (?:o|a|os|as))?\s*", "", clean, flags=re.I).strip()
            return AssistantResponse("Escolha onde pesquisar.", action="find", payload=query)
        if re.fullmatch(r"\s*(?:oi|olá|ola|bom dia|boa tarde|boa noite)(?:[, ]+(?:james|jarvis))?\s*[!.?]*\s*", clean, re.I):
            count = len(self.db.tasks())
            greeting = "Bom dia" if datetime.now().hour < 12 else "Boa tarde" if datetime.now().hour < 18 else "Boa noite"
            return AssistantResponse(f"{greeting}! Estou pronto. Você possui {count} tarefa(s) pendente(s).")
        alias_match = re.search(r"quando eu falar\s+(.+?),?\s+(?:eu )?quero que (?:você )?(?:abra|inicie)\s+(.+)", clean, re.I)
        if alias_match:
            alias, target = alias_match.group(1).strip(), alias_match.group(2).strip(" .")
            matches = self.app_matcher.match(target)
            if len(matches) == 1:
                self.db.set_application_alias(matches[0].app_id, alias, normalize_app_name(alias))
                return AssistantResponse(f"Entendido. Quando você disser “{alias}”, vou localizar {matches[0].display_name}.", action="refresh_app_view")
            return AssistantResponse("Não consegui identificar um único aplicativo para esse apelido. Informe o nome exato exibido no catálogo.")
        app_query = self._application_query(clean)
        if app_query:
            return self.request_application(app_query)
        # Tudo que não foi resolvido localmente segue para o provedor, inclusive
        # pedidos ambíguos de ação, para que ele possa esclarecer ou pedir uma ferramenta.
        return self._conversation(clean, intent, on_delta)

    def _handle_reminder(self, command: ReminderCommand) -> AssistantResponse:
        if command.error:
            return AssistantResponse(command.error)
        if command.action == "create" and command.title and command.remind_at:
            reminder_id = self.db.add_reminder(command.title, command.remind_at, command.recurrence)
            recurrence = "" if command.recurrence == "none" else " com repetição diária" if command.recurrence == "daily" else " com repetição semanal"
            return AssistantResponse(
                f"Lembrete #{reminder_id} criado para {command.remind_at:%d/%m/%Y às %H:%M}{recurrence}: {command.title}.",
                action="refresh_reminders", status="executed",
            )
        if command.action == "list":
            rows = self.db.reminders(command.filter_name)
            if not rows: return AssistantResponse("Nenhum lembrete encontrado nesse filtro.")
            names = {"none": "", "daily": " · diário", "weekly": " · semanal"}
            return AssistantResponse("Lembretes:\n" + "\n".join(
                f"• #{row['id']} {row['title']} — {datetime.fromisoformat(row['remind_at']):%d/%m/%Y às %H:%M}{names.get(row['recurrence'], '')}"
                for row in rows[:30]
            ))
        reminder = self.db.reminder(int(command.reminder_id or 0))
        if not reminder:
            return AssistantResponse("Não encontrei esse lembrete.")
        if command.action == "edit":
            changed = self.db.update_reminder(
                int(command.reminder_id), title=command.title, remind_at=command.remind_at,
                recurrence=command.recurrence if command.remind_at else None,
            )
            return AssistantResponse("Lembrete atualizado." if changed else "Nada foi alterado.", action="refresh_reminders", status="executed" if changed else "ready")
        if command.action == "complete":
            self.db.complete_reminder(int(command.reminder_id))
            return AssistantResponse("Lembrete concluído.", action="refresh_reminders", status="executed")
        if command.action == "postpone":
            when = command.remind_at or datetime.now() + timedelta(minutes=int(command.postpone_minutes or 0))
            self.db.postpone_reminder(int(command.reminder_id), when)
            return AssistantResponse(f"Lembrete adiado para {when:%d/%m/%Y às %H:%M}.", action="refresh_reminders", status="executed")
        if command.action == "delete":
            return AssistantResponse(
                f"Confirme a exclusão do lembrete #{command.reminder_id}: {reminder['title']}.",
                action="confirm_delete_reminder", payload=int(command.reminder_id), status="confirmation",
            )
        return AssistantResponse("Não consegui interpretar a operação do lembrete.")

    def _conversation(self, clean: str, intent: Intent,
                      on_delta: Callable[[str], None] | None = None) -> AssistantResponse:
        provider_name = str(self.settings.get("ai_provider", "basic"))
        if provider_name == "basic":
            return AssistantResponse(
                "A conversação inteligente está indisponível no modo Básico. "
                "Os comandos locais continuam funcionando; escolha Ollama ou OpenAI nas Configurações para conversar naturalmente."
            )
        snapshot = self.context.snapshot(clean)
        messages = snapshot.messages
        if not messages or messages[-1].get("content") != clean:
            messages.append({"role": "user", "content": clean})
        memories: list[str] = []
        if provider_name == "ollama" or bool(self.settings.get("share_memories_with_openai", False)):
            memories = self.context.authorized_memories(clean)
        instructions = self._instructions(memories, provider_name, intent, snapshot.temporary_note)
        try:
            provider = self._provider(provider_name)
            if provider_name == "ollama" and not provider.available():  # type: ignore[attr-defined]
                self._last_provider_status[provider_name] = (False, "desconectado")
                return AssistantResponse("O Ollama está desconectado. Inicie o serviço ou selecione outro provedor nas Configurações.", status="error")
            stream_method = getattr(provider, "chat_stream", None)
            if on_delta and callable(stream_method):
                result: ProviderResponse = stream_method(messages, instructions, on_delta)
            else:
                result = provider.chat(messages, instructions)  # type: ignore[attr-defined]
            self._last_provider_status[provider_name] = (True, "conectado")
        except RuntimeError as exc:
            self._last_provider_status[provider_name] = (False, "indisponível")
            logger.warning("provider_failure provider=%s error_type=%s", provider_name, type(exc).__name__)
            return AssistantResponse(str(exc), status="error")
        if result.tool_calls:
            call = result.tool_calls[0]
            if call.name not in self._tool_descriptions():
                return AssistantResponse("O modelo solicitou uma ferramenta desconhecida; nenhuma ação foi executada.", status="error")
            description = self._describe_tool_call(call)
            return AssistantResponse(
                f"A IA solicitou esta ação: {description}. Confirme para executá-la.",
                action="confirm_ai_tool", payload=call, status="confirmation")
        return AssistantResponse(result.text or "O provedor não retornou texto. Tente reformular a solicitação.")

    def _provider(self, name: str):
        if self.provider_factory: return self.provider_factory(name)
        if name == "ollama":
            return OllamaProvider(
                self.settings.get("ollama_url"), self.settings.get("ollama_model"),
                num_ctx=int(self.settings.get("ollama_num_ctx", 4096)),
                num_predict=int(self.settings.get("ollama_num_predict", 512)),
            )
        if name == "openai": return OpenAIProvider(self.settings.get("openai_model"))
        raise RuntimeError("Provedor de IA inválido. Selecione Básico, Ollama ou OpenAI.")

    def provider_status(self) -> tuple[str, bool, str]:
        name = str(self.settings.get("ai_provider", "basic"))
        if name == "basic": return name, True, "modo básico — IA conversacional desativada"
        if name in self._last_provider_status: return name, *self._last_provider_status[name]
        try:
            provider = self._provider(name)
            if name == "ollama":
                ok = bool(provider.available())
                return name, ok, "conectado" if ok else "desconectado"
            ok, detail = provider.status()
            return name, bool(ok), str(detail)
        except Exception as exc:
            return name, False, str(exc)

    def execute_ai_tool(self, call: ToolCall) -> AssistantResponse:
        """Executa somente ferramentas registradas, depois da confirmação feita pela interface."""
        if call.name == "open_calculator":
            return self._run_tool("open_calculator", "Calculadora aberta.", lambda: windows.open_program("calculator"))
        if call.name == "open_notepad":
            return self._run_tool("open_notepad", "Bloco de Notas aberto.", lambda: windows.open_program("notepad"))
        if call.name == "open_browser":
            return self._run_tool("open_browser", "Navegador aberto.", windows.open_browser)
        if call.name == "show_tasks":
            tasks = self.db.tasks()
            return AssistantResponse("Nenhuma tarefa pendente." if not tasks else
                "Tarefas pendentes:\n" + "\n".join(f"• #{row['id']} {row['title']}" for row in tasks))
        if call.name == "list_memories":
            memories = self.db.memories()
            return AssistantResponse("Nenhuma memória cadastrada." if not memories else
                "Memórias autorizadas:\n" + "\n".join(f"• {row['content']}" for row in memories[:20]))
        if call.name == "organize_files":
            return AssistantResponse("Abra o organizador e revise a prévia antes de confirmar.", action="organize")
        if call.name == "find_files":
            return AssistantResponse("Escolha onde pesquisar.", action="find", payload=str(call.arguments.get("query", "")))
        if call.name == "open_directory":
            wanted = str(call.arguments.get("name", "")).casefold()
            matches = [p for p in self.settings.allowed_directories if wanted and wanted in p.name.casefold()]
            if not matches: return AssistantResponse("Essa pasta não está entre os diretórios autorizados.")
            return self._run_tool("open_directory", f"Pasta aberta: {matches[0]}", lambda: windows.open_directory(matches[0]))
        if call.name == "find_application":
            return self.request_application(str(call.arguments.get("query", "")))
        if call.name == "navigate_public_web":
            request = str(call.arguments.get("request", "")).strip()
            result = self.orchestrator.handle(request)
            status = self._automation_status() if result.handled else "error"
            return AssistantResponse(result.text if result.handled else "Pedido de navegacao nao reconhecido; nenhuma pagina foi aberta.", action="refresh_automations", payload=result.run_id, status=status)
        return AssistantResponse("Ferramenta não autorizada; nenhuma ação foi executada.", status="error")

    def request_application(self, query: str) -> AssistantResponse:
        matches = self.app_matcher.match(query)
        if not matches:
            self._pending_open = None
            action = "refresh_apps" if not self.db.applications() else "application_not_found"
            status = "processing" if action == "refresh_apps" else "error"
            return AssistantResponse(f"Não encontrei um aplicativo instalado compatível com “{query}”.", action=action, payload=query, status=status)
        if len(matches) == 1 or (matches[0].score >= .82 and (len(matches) == 1 or matches[0].score-matches[1].score >= .12)):
            self._pending_open = PendingOpenAction("application", matches[0].app_id, matches[0].display_name)
            return AssistantResponse(f"Encontrei {matches[0].display_name}. Confirme antes de abrir.", action="confirm_application", payload=matches[0].app_id, status="confirmation")
        self._pending_open = None
        return AssistantResponse("Encontrei mais de uma opção compatível. Escolha qual deseja abrir.", action="choose_application", payload=matches, status="confirmation")

    def launch_application(self, app_id: str) -> AssistantResponse:
        if self._pending_open and self._pending_open.kind == "application" and self._pending_open.target == app_id:
            self._pending_open = None
        success, message = self.app_launcher.launch(app_id)
        self.db.log_action("open_application", message, True, success)
        status = "verified" if success and "processo verificado" in message.casefold() else "requested" if success else "error"
        return AssistantResponse(message, action="refresh_app_view", status=status)

    def confirm_pending_open(self) -> AssistantResponse:
        pending = self._pending_open
        if not pending:
            return AssistantResponse("Não há aplicativo ou site pendente para abrir. Informe primeiro o destino.", status="error")
        if pending.kind == "application":
            if not self.db.get_application(pending.target):
                self._pending_open = None
                return AssistantResponse("O aplicativo pendente não está mais disponível; nada foi aberto.", status="error")
            return AssistantResponse(
                f"Confirme a abertura de {pending.label}.",
                action="confirm_application", payload=pending.target, status="confirmed",
            )
        self._pending_open = None
        if not self.settings.permission("public_web_navigation"):
            return AssistantResponse("A navegação em sites públicos está desativada nas permissões; nada foi aberto.", status="error")
        result = self.orchestrator.handle(f"abra o {pending.label}")
        if not result.handled:
            return AssistantResponse("O destino pendente deixou de ser válido; nada foi aberto.", status="error")
        return AssistantResponse(result.text, action="refresh_automations", payload=result.run_id,
                                 status=self._automation_status())

    def cancel_pending_open(self) -> None:
        self._pending_open = None

    def cancel_pending_actions(self) -> None:
        self._pending_open = None
        self._pending_memory_delete = None

    def confirm_pending_memory_delete(self) -> AssistantResponse:
        memory_id = self._pending_memory_delete
        self._pending_memory_delete = None
        if memory_id is None:
            return AssistantResponse("Não há exclusão de memória aguardando confirmação.", status="error")
        if not self.db.delete_memory(memory_id):
            return AssistantResponse("A memória não está mais disponível; nada foi excluído.", status="error")
        return AssistantResponse(f"Memória #{memory_id} excluída.", action="refresh_memories", status="executed")

    def _request_chatgpt(self) -> AssistantResponse:
        matches = self.app_matcher.match("chatgpt")
        if matches:
            return self.request_application("chatgpt")
        if not self._chatgpt_catalog_checked:
            self._chatgpt_catalog_checked = True
            return AssistantResponse(
                "Vou atualizar o catálogo para verificar se o ChatGPT Desktop está instalado.",
                action="refresh_apps", payload="__chatgpt__", status="processing",
            )
        return self.request_chatgpt_after_refresh()

    def request_chatgpt_after_refresh(self) -> AssistantResponse:
        matches = self.app_matcher.match("chatgpt")
        if matches:
            return self.request_application("chatgpt")
        self._pending_open = PendingOpenAction("website", "https://chatgpt.com/", "ChatGPT")
        return AssistantResponse(
            "Não encontrei o ChatGPT Desktop instalado. Posso abrir https://chatgpt.com no navegador padrão. Confirma?",
            action="confirm_website", payload="https://chatgpt.com/", status="confirmation",
        )

    @staticmethod
    def _is_chatgpt_open_request(text: str) -> bool:
        normalized = normalize_app_name(text)
        has_service = bool(re.search(r"\bchat\s*gpt\b", normalized))
        has_action = bool(re.search(r"\b(abra|abre|abrir|acesse|acessar|entre|entrar|inicie|iniciar)\b", normalized))
        return has_service and has_action

    def stop_automation(self) -> AssistantResponse:
        self.orchestrator.stop()
        run_id = self.orchestrator.current_run_id
        if run_id:
            self.db.finish_automation(run_id, "cancelado", "Interrompida pelo usuario.")
        return AssistantResponse("Automacao interrompida. Nenhuma nova etapa sera iniciada.", action="refresh_automations")

    def close(self) -> None:
        self.browser.close()

    @staticmethod
    def _application_query(text: str) -> str | None:
        match = re.search(r"\b(?:abra|abre|abrir|inicia|inicie|execute|executa)\s+(?:o |a )?(.+?)[.!?]*$", text, re.I)
        if match: return match.group(1).strip()
        low = normalize_app_name(text)
        if any(phrase in low for phrase in ("quero editar uma imagem", "preciso editar uma imagem", "preciso fazer um documento", "quero fazer uma planilha", "programa da minha impressora")):
            return text
        return None

    @staticmethod
    def _tool_descriptions() -> dict[str, str]:
        return {"open_calculator": "abrir a calculadora", "open_notepad": "abrir o Bloco de Notas",
                "open_browser": "abrir o navegador", "open_directory": "abrir uma pasta autorizada",
                "show_tasks": "consultar tarefas", "list_memories": "consultar memórias autorizadas",
                "organize_files": "abrir o organizador supervisionado", "find_files": "pesquisar arquivos",
                "find_application": "localizar um aplicativo instalado", "navigate_public_web": "navegar na web publica com supervisao"}

    def _describe_tool_call(self, call: ToolCall) -> str:
        description = self._tool_descriptions()[call.name]
        details = ", ".join(f"{key}={value}" for key, value in call.arguments.items())
        return f"{description} ({details})" if details else description

    def _automation_status(self) -> str:
        context = self.orchestrator.context
        if context.status == "erro":
            return "error"
        step = context.current_step.casefold()
        verified = ("página carregada", "video aberto", "vídeo aberto", "resultado aberto", "processo verificado")
        if any(marker in step for marker in verified):
            return "verified"
        if "solicitada" in step or "solicitado" in step:
            return "requested"
        return "executed" if context.status == "concluido" else "ready"

    @staticmethod
    def _instructions(memories: list[str], provider_name: str, intent: Intent,
                      temporary_note: str = "") -> str:
        memory_text = "\n".join(f"- {item}" for item in memories) or "Nenhuma memória foi compartilhada."
        return (
            "Prioridade absoluta: responda à intenção da última mensagem do usuário. Se houver uma pergunta objetiva, responda-a já na primeira frase. "
            "Só cumprimente quando a mensagem for apenas uma saudação; não substitua respostas por 'como posso ajudar'. Não repita uma resposta anterior sem necessidade. "
            "Você é James, um assistente pessoal brasileiro, amigável, objetivo e profissional. Responda de forma natural e variada, "
            "sem bordões, saudações repetidas ou linguagem robótica. Ajuste o nível de detalhe à pergunta e faça apenas uma pergunta curta quando faltar contexto. "
            "Ajude na vida pessoal, serviços gráficos, administração de loja e Windows. Entenda referências usando os turnos recentes e aceite mudanças de assunto sem misturá-los. "
            "Nunca diga que abriu, encontrou, moveu ou executou algo sem resultado real. Para ações disponíveis, use apenas as ferramentas estruturadas; "
            "não gere comandos de terminal e não trate uma sugestão como autorização. O aplicativo pedirá confirmação ao usuário. "
            "O histórico recente é contexto temporário, não memória permanente. Nunca afirme que uma informação foi memorizada sem ela aparecer nas memórias autorizadas. "
            "Use as memórias recuperadas somente quando forem pertinentes à pergunta; ensinamentos corrigidos mais recentes substituem versões anteriores. "
            f"O roteador local classificou a mensagem como {intent.value}; trate isso como pista, não como autorização. "
            f"Nota do contexto temporário: {temporary_note or 'Sem observações.'}\n"
            f"Provedor atual: {provider_name}. Memórias persistentes autorizadas para este contexto:\n{memory_text}"
        )

    def _run_tool(self, permission: str, success_message: str, function) -> AssistantResponse:
        allowed, reason = self.policy.require_permission(permission)
        if not allowed:
            self.db.log_action(permission, reason, False, False)
            return AssistantResponse(reason, status="error")
        success, details = function()
        self.db.log_action(permission, details, True, success)
        if not success:
            return AssistantResponse(details, status="error")
        return AssistantResponse(f"Solicitação executada: {success_message} Verificação da janela não disponível.", status="requested")

    def capabilities_text(self, question: str = "") -> str:
        """Descreve somente recursos existentes, considerando configuração e permissões."""
        active = [
            "usar o chat por texto para consultas e comandos locais",
            "criar e consultar tarefas, agenda e lembretes",
            "guardar, corrigir, consultar e excluir memórias autorizadas",
            "localizar aplicativos instalados e solicitar abertura com confirmação",
            "consultar histórico de conversas, atividades e relatórios locais",
        ]
        unavailable: list[str] = []
        permission_features = (
            ("open_calculator", "abrir a Calculadora"),
            ("open_notepad", "abrir o Bloco de Notas"),
            ("open_browser", "abrir o navegador padrão"),
            ("open_directory", "abrir pastas autorizadas"),
            ("find_files", "localizar arquivos em pastas autorizadas"),
            ("organize_files", "analisar e organizar arquivos com prévia e confirmação"),
            ("system_info", "consultar informações básicas deste computador"),
            ("public_web_navigation", "abrir sites públicos no navegador padrão"),
        )
        for permission, description in permission_features:
            (active if self.settings.permission(permission) else unavailable).append(description)
        web_automation = "executar pesquisas Web supervisionadas e apresentar resultados reais"
        if self.settings.permission("public_web_navigation") and self.settings.permission("browser_automation"):
            active.append(web_automation)
        else:
            unavailable.append(web_automation)

        provider, connected, detail = self.provider_status()
        if provider == "basic":
            unavailable.append("conversação por IA — modo Básico selecionado")
        elif connected:
            active.append(f"conversação natural com {provider.upper()} conectado")
        else:
            unavailable.append(f"conversação com {provider.upper()} — {detail}")

        normalized = self.router.normalize(question)
        focus = ""
        if re.search(r"\b(offline|local|sem internet)\b", normalized):
            focus = ("Sem internet, continuam disponíveis tarefas, agenda, memórias, aplicativos, arquivos e relatórios locais. "
                     "A conversa inteligente funciona offline somente quando o Ollama está conectado.\n\n")
        elif re.search(r"\b(confirmacao|confirmar|permissao)\b", normalized):
            focus = ("Pedem confirmação as aberturas de aplicativos, ferramentas solicitadas pela IA, exclusões e qualquer "
                     "movimentação feita pelo organizador de arquivos.\n\n")
        elif "o que mais" in normalized:
            focus = "Além dos recursos ativos, as limitações atuais estão separadas abaixo.\n\n"

        lines = [focus + "Você pode me pedir, agora:", *(f"• {item}." for item in active)]
        if unavailable:
            lines.extend(("\nIndisponível ou desativado no momento:", *(f"• {item}." for item in unavailable)))
        lines.extend((
            "\nAinda não implementado nesta fase:",
            "• controle remoto ou integração com celular.",
            "• compras, pagamentos, envio automático de mensagens ou ações sem supervisão.",
        ))
        return "\n".join(lines)

    @staticmethod
    def help_text() -> str:
        return ("Comandos: abra a calculadora; abra o bloco de notas; abra o navegador; "
                "abra a pasta [nome]; informações do computador; adicione tarefa [texto]; mostre minhas tarefas; "
                "crie um lembrete para [assunto] amanhã às [hora]; mostre meus lembretes; adie, conclua ou exclua o lembrete [número]; "
                "lembre/aprenda que [informação]; corrija a memória [número] para [texto]; exclua a memória [número]; "
                "o que você lembra; procure [arquivo]; organize os arquivos.")
