from __future__ import annotations

import queue
import os
import re
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from ai.base import ToolCall
from ai.ollama import OllamaProvider
from config.settings import Settings
from core.assistant import Assistant, AssistantResponse
from core.scheduler import ReminderScheduler, SchedulerEvent
from interface.organizer import OrganizerDialog
from interface.theme import COLORS, FONT, FONT_MONO
from interface.widgets import ConversationView, Gauge, HologramCore, NeonButton, panel, section_title
from memory.database import Database
from security.policy import SecurityPolicy
from tools.file_manager import find_files
from tools.system_monitor import SystemMonitor
from tools.voice import VoiceEvent, VoiceService
from tools.application_discovery import ApplicationDiscoveryService, make_app_id, normalize_app_name
from tools.application_matcher import ApplicationMatch


class JamesApp:
    def __init__(self, assistant: Assistant, database: Database, settings: Settings):
        self.assistant, self.db, self.settings = assistant, database, settings
        self.policy, self.monitor = SecurityPolicy(settings), SystemMonitor()
        self.responses: queue.Queue[AssistantResponse] = queue.Queue()
        self._stream_buffer = ""
        self.voice_events: queue.Queue[VoiceEvent] = queue.Queue()
        self.voice = VoiceService(settings, self.voice_events.put)
        self.voice_state = "Pronto"
        self.scheduler_events: queue.Queue[SchedulerEvent] = queue.Queue()
        self.scheduler = ReminderScheduler(database, self.scheduler_events.put)
        self.root = tk.Tk(); self.root.title("JAMES IA — Assistente Inteligente")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{min(1600, sw-40)}x{min(930, sh-70)}+10+10")
        self.root.minsize(1120, 700); self.root.configure(bg=COLORS["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Destroy>", self._on_root_destroy, add="+")
        self.root.bind("<Escape>", lambda _event: self.cancel_voice())
        self.root.option_add("*Font", (FONT, 9))
        self.nexus_state = "idle"; self.nexus_detail = "Sistema pronto"
        self.nexus_system = tk.StringVar(value="CPU —   RAM —   DISCO —")
        self.chat: tk.Text | None = None; self.nav_buttons: dict[str, tk.Button] = {}
        self.gauges: dict[str, Gauge] = {}; self.current_page = "dashboard"
        self.sidebar_collapsed = False; self.right_panel_collapsed = False
        self._style(); self._ensure_welcome(); self._build_shell(); self.show_page("dashboard")
        self.root.after(100, self._poll); self.root.after(250, self._refresh_provider_status)
        self.root.after(500, self._tick_clock); self.root.after(1200, self._update_monitor)
        self.scheduler.start()
        if not self.db.applications(): self.root.after(800, lambda: self.refresh_app_catalog(auto=True))

    def _style(self) -> None:
        style = ttk.Style(self.root); style.theme_use("clam")
        style.configure("Treeview", background=COLORS["field"], fieldbackground=COLORS["field"], foreground=COLORS["text"], borderwidth=0, rowheight=28)
        style.configure("Treeview.Heading", background=COLORS["panel_alt"], foreground=COLORS["cyan"], borderwidth=0, font=(FONT, 9, "bold"))
        style.map("Treeview", background=[("selected", "#0b4b66")])
        style.configure("TCombobox", fieldbackground=COLORS["field"], background=COLORS["panel_alt"], foreground=COLORS["text"], arrowcolor=COLORS["cyan"])

    def _ensure_welcome(self) -> None:
        if not self.db.conversations(1, self.assistant.conversation_id):
            self.db.add_conversation("assistant", "Olá! Sou James. Como posso ajudar hoje?", self.assistant.conversation_id)

    def _build_shell(self) -> None:
        self.sidebar = tk.Frame(self.root, bg=COLORS["sidebar"], width=230, highlightbackground=COLORS["border_soft"], highlightthickness=1)
        self.sidebar.pack(side="left", fill="y"); self.sidebar.pack_propagate(False)
        self.workspace = tk.Frame(self.root, bg=COLORS["bg"]); self.workspace.pack(side="left", fill="both", expand=True)
        self._build_sidebar(); self._build_topbar()
        self.content = tk.Frame(self.workspace, bg=COLORS["bg"]); self.content.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self._build_command_bar()

    def _build_sidebar(self) -> None:
        brand = tk.Frame(self.sidebar, bg=COLORS["sidebar"], height=92); brand.pack(fill="x"); brand.pack_propagate(False)
        core = tk.Canvas(brand, width=54, height=54, bg=COLORS["sidebar"], highlightthickness=0); core.pack(side="left", padx=(10, 5), pady=16)
        for inset, color in ((5, COLORS["cyan_dim"]), (12, COLORS["cyan"]), (20, COLORS["blue"])): core.create_oval(inset, inset, 54-inset, 54-inset, outline=color, width=2)
        core.create_oval(23, 23, 31, 31, fill=COLORS["cyan"], outline="")
        self.brand_names = tk.Frame(brand, bg=COLORS["sidebar"]); self.brand_names.pack(side="left", pady=20)
        self.brand_title = tk.Label(self.brand_names, text="JAMES", bg=COLORS["sidebar"], fg=COLORS["text"], font=(FONT, 17, "bold")); self.brand_title.pack(anchor="w")
        self.brand_subtitle = tk.Label(self.brand_names, text="ASSISTENTE INTELIGENTE", bg=COLORS["sidebar"], fg=COLORS["cyan"], font=(FONT, 6, "bold")); self.brand_subtitle.pack(anchor="w")
        self.collapse_sidebar_button = tk.Button(brand, text="‹", command=self.toggle_sidebar, bg=COLORS["sidebar"], fg=COLORS["muted"], activebackground=COLORS["panel_alt"], activeforeground=COLORS["cyan"], relief="flat", bd=0, font=(FONT, 15), cursor="hand2")
        self.collapse_sidebar_button.pack(side="right", padx=6)
        groups = (
            ("ASSISTENTE", (("dashboard", "⌂", "Central de Comando"), ("conversations", "◌", "Histórico de Conversas"), ("core", "◎", "Núcleo de IA"))),
            ("PRODUTIVIDADE", (("tasks", "□", "Tarefas"), ("reminders", "◷", "Agenda"), ("memory", "▱", "Memória"), ("files", "◇", "Arquivos"), ("reports", "▤", "Relatórios"))),
            ("FERRAMENTAS", (("apps", "▦", "Aplicativos do Windows"), ("store", "▣", "Loja"), ("agents", "✧", "Agentes"), ("automations", "⚡", "Automações"))),
            ("SISTEMA", (("settings", "⚙", "Configurações"),)),
        )
        self.sidebar_group_labels = []; self.nav_meta = {}
        for group, items in groups:
            label = tk.Label(self.sidebar, text=group, anchor="w", bg=COLORS["sidebar"], fg="#5f7d8d", font=(FONT, 7, "bold"), padx=20, pady=3)
            label.pack(fill="x", pady=(4, 0)); self.sidebar_group_labels.append((label, group))
            for key, icon, title in items:
                cmd = (lambda page=key: self.show_page(page)) if key != "files" else self.organize_dialog
                button = tk.Button(self.sidebar, text=f"{icon}  {title}", command=cmd, anchor="w", bg=COLORS["sidebar"], fg=COLORS["muted"], activebackground=COLORS["panel_alt"], activeforeground=COLORS["cyan"], relief="flat", bd=0, padx=18, pady=6, cursor="hand2", font=(FONT, 9))
                button.pack(fill="x", padx=8, pady=1); self.nav_buttons[key] = button; self.nav_meta[key] = (icon, title)
        self.sidebar_quote = panel(self.sidebar, height=82); self.sidebar_quote.pack(side="bottom", fill="x", padx=10, pady=10); self.sidebar_quote.pack_propagate(False)
        tk.Label(self.sidebar_quote, text="“Mais capacidade para você,\ntodos os dias.”", justify="left", bg=COLORS["panel"], fg=COLORS["text"], font=(FONT, 9)).pack(anchor="w", padx=11, pady=(13, 5))
        tk.Label(self.sidebar_quote, text="JAMES  ──", bg=COLORS["panel"], fg=COLORS["cyan"], font=(FONT, 7, "bold")).pack(anchor="w", padx=11)

    def toggle_sidebar(self) -> None:
        self.sidebar_collapsed = not self.sidebar_collapsed
        self.sidebar.configure(width=72 if self.sidebar_collapsed else 230)
        self.brand_title.configure(text="" if self.sidebar_collapsed else "JAMES")
        self.brand_subtitle.configure(text="" if self.sidebar_collapsed else "ASSISTENTE INTELIGENTE")
        self.collapse_sidebar_button.configure(text="›" if self.sidebar_collapsed else "‹")
        for label, title in self.sidebar_group_labels: label.configure(text="" if self.sidebar_collapsed else title, pady=0 if self.sidebar_collapsed else 3)
        for key, button in self.nav_buttons.items():
            icon, title = self.nav_meta[key]; button.configure(text=icon if self.sidebar_collapsed else f"{icon}  {title}", anchor="center" if self.sidebar_collapsed else "w", padx=4 if self.sidebar_collapsed else 18)
        if self.sidebar_collapsed: self.sidebar_quote.pack_forget()
        elif not self.sidebar_quote.winfo_manager(): self.sidebar_quote.pack(side="bottom", fill="x", padx=10, pady=10)

    def _build_topbar(self) -> None:
        top = tk.Frame(self.workspace, bg=COLORS["bg"], height=70); top.pack(fill="x", padx=10); top.pack_propagate(False)
        identity = tk.Frame(top, bg=COLORS["bg"]); identity.pack(side="left", padx=(4, 16), pady=10)
        tk.Label(identity, text="JAMES / NEXUS", bg=COLORS["bg"], fg=COLORS["text"], font=(FONT, 15, "bold")).pack(anchor="w")
        tk.Label(identity, text="INTERFACE 3.1  ·  LOCAL / SUPERVISIONADA", bg=COLORS["bg"], fg=COLORS["cyan"], font=(FONT, 6, "bold")).pack(anchor="w")
        search = panel(top, width=285, height=38); search.pack(side="left", pady=15); search.pack_propagate(False)
        tk.Label(search, text="⌕", bg=COLORS["panel"], fg=COLORS["cyan"], font=(FONT, 18)).pack(side="left", padx=(12, 5))
        self.search_var = tk.StringVar(value="Pesquisar conversas..."); search_entry = tk.Entry(search, textvariable=self.search_var, bg=COLORS["panel"], fg=COLORS["muted"], insertbackground=COLORS["cyan"], relief="flat", bd=0, font=(FONT, 10))
        search_entry.pack(side="left", fill="both", expand=True, pady=5); search_entry.bind("<Return>", lambda _e: self.search_conversations()); search_entry.bind("<FocusIn>", lambda _e: self.search_var.set("") if self.search_var.get() == "Pesquisar conversas..." else None)
        clock = tk.Frame(top, bg=COLORS["bg"]); clock.pack(side="left", expand=True)
        self.date_label = tk.Label(clock, bg=COLORS["bg"], fg=COLORS["text"], font=(FONT, 8)); self.date_label.pack()
        self.time_label = tk.Label(clock, bg=COLORS["bg"], fg=COLORS["cyan"], font=(FONT, 19, "bold")); self.time_label.pack()
        right = tk.Frame(top, bg=COLORS["bg"]); right.pack(side="right", pady=8)
        self.status = tk.Label(right, text="● SISTEMA · INICIANDO", bg=COLORS["bg"], fg=COLORS["yellow"], font=(FONT, 8, "bold")); self.status.pack(anchor="e")
        tk.Label(right, text="●  Operador", bg=COLORS["panel"], fg=COLORS["text"], font=(FONT, 10, "bold"), padx=18, pady=8, highlightbackground=COLORS["border"], highlightthickness=1).pack(pady=(5, 0))

    def _build_command_bar(self) -> None:
        bar = tk.Frame(self.workspace, bg=COLORS["sidebar"], height=66, highlightbackground=COLORS["cyan_dim"], highlightthickness=1)
        bar.pack(side="bottom", fill="x"); bar.pack_propagate(False)
        tk.Label(bar, text="›_", bg=COLORS["sidebar"], fg=COLORS["cyan"], font=(FONT_MONO, 14, "bold")).pack(side="left", padx=(15, 9))
        self.entry = tk.Entry(bar, bg=COLORS["field"], fg=COLORS["text"], insertbackground=COLORS["cyan"], relief="flat", font=(FONT, 11), highlightbackground=COLORS["border"], highlightthickness=1)
        self.entry.pack(side="left", fill="x", expand=True, ipady=10, pady=10); self.entry.bind("<Return>", lambda _e: self.send())
        NeonButton(bar, "ENVIAR  →", self.send).pack(side="left", padx=10, pady=10)
        self.processing = tk.Label(bar, text="● PRONTO", bg=COLORS["sidebar"], fg=COLORS["cyan"], font=(FONT, 8, "bold")); self.processing.pack(side="right", padx=10)
        self.footer_system = tk.Label(bar, text="CPU —  RAM —  DISCO —", bg=COLORS["sidebar"], fg=COLORS["muted"], font=(FONT, 7)); self.footer_system.pack(side="right", padx=8)

    def show_page(self, page: str) -> None:
        self.current_page = page; self.chat = None
        for child in self.content.winfo_children(): child.destroy()
        for key, button in self.nav_buttons.items():
            active = key == page; button.configure(bg="#083047" if active else COLORS["sidebar"], fg=COLORS["cyan"] if active else "#a9c2d2")
        builders = {"dashboard": self._dashboard, "conversations": self._conversations, "reports": self._reports, "tasks": self._tasks, "reminders": self._reminders, "memory": self._memory, "apps": self._applications, "settings": self._settings, "core": self._core_page, "automations": self._automations}
        builders.get(page, lambda: self._development(page))()

    def _dashboard(self) -> None:
        self.content.grid_columnconfigure(0, weight=1); self.content.grid_columnconfigure(1, weight=0, minsize=310); self.content.grid_rowconfigure(0, weight=1)
        center = tk.Frame(self.content, bg=COLORS["bg"]); self.dashboard_center = center; center.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        center.grid_columnconfigure(0, weight=1); center.grid_rowconfigure(0, weight=5, minsize=250); center.grid_rowconfigure(1, weight=4, minsize=250)
        nexus = panel(center); nexus.grid(row=0, column=0, sticky="nsew", pady=(0, 5)); self._nexus_stage(nexus)
        chat_box = panel(center); chat_box.grid(row=1, column=0, sticky="nsew", pady=(5, 5)); self._dashboard_chat(chat_box)
        quick = panel(center, height=62); quick.grid(row=2, column=0, sticky="ew", pady=(5, 0)); quick.grid_propagate(False); self._compact_quick_actions(quick)
        self.right_dashboard_panel = panel(self.content); self.right_dashboard_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0)); self._dashboard_reports(self.right_dashboard_panel)
        if self.right_panel_collapsed: self._apply_right_panel_state()

    def _nexus_stage(self, parent: tk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=2, minsize=150); parent.grid_columnconfigure(1, weight=5, minsize=280); parent.grid_columnconfigure(2, weight=2, minsize=150); parent.grid_rowconfigure(0, weight=1)
        left = tk.Frame(parent, bg=COLORS["panel"]); left.grid(row=0, column=0, sticky="nsew", padx=(12, 5), pady=10)
        self._nexus_capability(left, "◎", "ENTENDER", "LINGUAGEM E CONTEXTO", COLORS["cyan"])
        self._nexus_capability(left, "◇", "PLANEJAR", "TAREFAS SUPERVISIONADAS", COLORS["blue"])
        counts = self.db.counts()
        tk.Label(left, text=f"{counts['tasks']} TAREFAS\n{counts['memories']} MEMÓRIAS\n{counts['conversations']} MENSAGENS", justify="left", bg=COLORS["panel"], fg=COLORS["muted"], font=(FONT_MONO, 7)).pack(side="bottom", anchor="w", pady=8)
        core_box = tk.Frame(parent, bg=COLORS["panel"]); core_box.grid(row=0, column=1, sticky="nsew")
        self.nexus_core = HologramCore(core_box, state=self.nexus_state); self.nexus_core.pack(fill="both", expand=True)
        right = tk.Frame(parent, bg=COLORS["panel"]); right.grid(row=0, column=2, sticky="nsew", padx=(5, 12), pady=10)
        self._nexus_capability(right, "⚡", "EXECUTAR", "AÇÕES AUTORIZADAS", COLORS["green"])
        self._nexus_capability(right, "✦", "APRENDER", "MEMÓRIA LOCAL", COLORS["yellow"])
        tk.Label(right, textvariable=self.nexus_system, justify="left", bg=COLORS["panel"], fg=COLORS["cyan_dim"], font=(FONT_MONO, 7)).pack(side="bottom", anchor="e", pady=8)

    def _nexus_capability(self, parent: tk.Frame, icon: str, title: str, subtitle: str, color: str) -> None:
        card = tk.Frame(parent, bg=COLORS["panel_alt"], highlightbackground=COLORS["border_soft"], highlightthickness=1)
        card.pack(fill="x", pady=5)
        tk.Label(card, text=icon, bg=COLORS["panel_alt"], fg=color, font=(FONT, 15), width=3).pack(side="left", padx=(4, 0), pady=8)
        text = tk.Frame(card, bg=COLORS["panel_alt"]); text.pack(side="left", fill="x", expand=True, pady=7)
        tk.Label(text, text=title, bg=COLORS["panel_alt"], fg=COLORS["text"], font=(FONT, 8, "bold")).pack(anchor="w")
        tk.Label(text, text=subtitle, bg=COLORS["panel_alt"], fg=COLORS["muted"], font=(FONT, 6)).pack(anchor="w")

    def _compact_assistant_header(self, parent: tk.Frame) -> None:
        core = HologramCore(parent, width=104, height=78); core.pack(side="left", padx=(8, 4), pady=4)
        info = tk.Frame(parent, bg=COLORS["panel"]); info.pack(side="left", fill="y", padx=8, pady=13)
        tk.Label(info, text="JAMES IA", bg=COLORS["panel"], fg=COLORS["text"], font=(FONT, 17, "bold")).pack(anchor="w")
        tk.Label(info, text="Seu assistente inteligente", bg=COLORS["panel"], fg=COLORS["cyan"], font=(FONT, 9)).pack(anchor="w")
        context = self.assistant.orchestrator.context
        state = context.current_step or ("Pronto para ajudar" if context.status == "ocioso" else context.status)
        status = tk.Frame(parent, bg=COLORS["panel_alt"]); status.pack(side="right", padx=12, pady=16)
        tk.Label(status, text="●", bg=COLORS["panel_alt"], fg=COLORS["green"] if context.status != "erro" else COLORS["danger"], font=(FONT, 11)).pack(side="left", padx=(10, 5))
        tk.Label(status, text=state[:55], bg=COLORS["panel_alt"], fg=COLORS["text"], font=(FONT, 8), padx=8, pady=8).pack(side="left")
        NeonButton(parent, "ATIVIDADES ›", self.toggle_right_panel).pack(side="right", padx=4, pady=20)

    def _dashboard_chat(self, parent: tk.Frame) -> None:
        head = tk.Frame(parent, bg=COLORS["panel"]); head.pack(fill="x", padx=10, pady=(8, 3))
        section_title(head, "CANAL DE CONVERSA · CONTEXTO ATIVO").pack(side="left")
        NeonButton(head, "EXPANDIR", lambda: self.show_page("conversations")).pack(side="right")
        self.chat = ConversationView(parent)
        self.chat.pack(fill="both", expand=True, padx=8, pady=(0, 8)); self._render_history()

    def _compact_quick_actions(self, parent: tk.Frame) -> None:
        actions = (("◌ CONVERSAR", lambda: self.entry.focus_set()), ("⌕ PESQUISAR", lambda: self._prefill("pesquise na internet ")),
                   ("◇ ORGANIZAR", self.organize_dialog), ("▦ APLICATIVOS", lambda: self.show_page("apps")),
                   ("□ TAREFAS", lambda: self.show_page("tasks")), ("▤ RELATÓRIOS", lambda: self.show_page("reports")))
        for text, command in actions: NeonButton(parent, text, command).pack(side="left", expand=True, fill="x", padx=3, pady=11)

    def _prefill(self, text: str) -> None:
        self.entry.delete(0, "end"); self.entry.insert(0, text); self.entry.focus_set()

    def _configure_chat(self) -> None:
        self.chat.tag_configure("user", foreground=COLORS["cyan"], spacing1=7)
        self.chat.tag_configure("assistant", foreground=COLORS["text"], spacing1=7)

    def _dashboard_reports(self, parent: tk.Frame) -> None:
        self.dashboard_reports_panel = parent
        head = tk.Frame(parent, bg=COLORS["panel"]); head.pack(fill="x", padx=10, pady=(8, 4))
        section_title(head, "ATIVIDADES E RESULTADOS").pack(side="left")
        NeonButton(head, "‹", self.toggle_right_panel).pack(side="right", padx=(3, 0)); NeonButton(head, "RELATÓRIOS", lambda: self.show_page("reports")).pack(side="right")
        context = self.assistant.orchestrator.context
        current = tk.Frame(parent, bg=COLORS["panel_alt"], highlightbackground=COLORS["border_soft"], highlightthickness=1); current.pack(fill="x", padx=10, pady=(6, 8))
        state_color = COLORS["danger"] if context.status == "erro" else COLORS["yellow"] if context.status == "executando" else COLORS["green"]
        tk.Label(current, text="TAREFA ATUAL", bg=COLORS["panel_alt"], fg=COLORS["muted"], font=(FONT, 7, "bold")).pack(anchor="w", padx=9, pady=(7, 1))
        tk.Label(current, text=f"● {context.status.upper()}", bg=COLORS["panel_alt"], fg=state_color, font=(FONT, 8, "bold")).pack(anchor="w", padx=9)
        tk.Label(current, text=(context.objective or "Nenhuma tarefa em execução")[:55], wraplength=285, justify="left", bg=COLORS["panel_alt"], fg=COLORS["text"], font=(FONT, 8)).pack(anchor="w", padx=9, pady=(2, 8))
        section_title(parent, "RESULTADOS RECENTES").pack(fill="x", padx=12, pady=(4, 3))
        runs = self.db.automation_runs(4)
        if not runs: tk.Label(parent, text="Nenhum resultado ainda.", bg=COLORS["panel"], fg=COLORS["muted"]).pack(pady=12)
        for row in runs:
            item = tk.Frame(parent, bg=COLORS["panel_alt"]); item.pack(fill="x", padx=10, pady=3)
            info = tk.Frame(item, bg=COLORS["panel_alt"]); info.pack(side="left", fill="both", expand=True, padx=8, pady=5)
            tk.Label(info, text=str(row["objective"])[:45], anchor="w", bg=COLORS["panel_alt"], fg=COLORS["text"], font=(FONT, 8, "bold")).pack(fill="x")
            detail = row["error"] or row["result"] or "Em execução"
            tk.Label(info, text=f"{row['status']} · {str(detail)[:55]}", anchor="w", bg=COLORS["panel_alt"], fg=COLORS["danger"] if row["error"] else COLORS["muted"], font=(FONT, 7)).pack(fill="x")
            NeonButton(item, "VER", lambda run_id=int(row["id"]): self.show_report(run_id)).pack(side="right", padx=6)
        section_title(parent, "ATIVIDADE RECENTE").pack(fill="x", padx=12, pady=(10, 3))
        for row in self.db.recent_actions(4):
            color = COLORS["green"] if row["success"] else COLORS["danger"]
            item = tk.Frame(parent, bg=COLORS["panel"]); item.pack(fill="x", padx=11, pady=2)
            tk.Label(item, text="●", bg=COLORS["panel"], fg=color, font=(FONT, 8)).pack(side="left", padx=(2, 6))
            tk.Label(item, text=self._friendly_action(str(row["action"])), anchor="w", bg=COLORS["panel"], fg=COLORS["text"], font=(FONT, 8)).pack(side="left", fill="x", expand=True)
            tk.Label(item, text=str(row["created_at"])[11:16], bg=COLORS["panel"], fg=COLORS["muted"], font=(FONT_MONO, 7)).pack(side="right")

    @staticmethod
    def _friendly_action(action: str) -> str:
        names = {"open_public_site": "Site aberto", "open_application": "Aplicativo solicitado", "open_directory": "Pasta aberta",
                 "organize_files": "Arquivos organizados", "find_files": "Pesquisa de arquivos", "open_calculator": "Calculadora aberta",
                 "abrir_navegador_padrao": "Navegador solicitado"}
        return names.get(action, action.replace("_", " ").capitalize())

    def toggle_right_panel(self) -> None:
        self.right_panel_collapsed = not self.right_panel_collapsed; self._apply_right_panel_state()

    def _apply_right_panel_state(self) -> None:
        if not hasattr(self, "right_dashboard_panel") or not self.right_dashboard_panel.winfo_exists(): return
        if self.right_panel_collapsed:
            self.right_dashboard_panel.grid_remove(); self.dashboard_center.grid_configure(columnspan=2, padx=0); self.content.grid_columnconfigure(1, minsize=0)
        else:
            self.content.grid_columnconfigure(1, minsize=330); self.dashboard_center.grid_configure(columnspan=1, padx=(0, 6)); self.right_dashboard_panel.grid()

    def _refresh_dashboard_panels(self) -> None:
        if self.current_page != "dashboard": return
        for name, builder in (("dashboard_reports_panel", self._dashboard_reports),):
            target = getattr(self, name, None)
            if target and target.winfo_exists():
                for child in target.winfo_children(): child.destroy()
                builder(target)

    def _hero(self, parent: tk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=4); parent.grid_columnconfigure(1, weight=5); parent.grid_columnconfigure(2, weight=3); parent.grid_rowconfigure(0, weight=1)
        intro = tk.Frame(parent, bg=COLORS["panel"]); intro.grid(row=0, column=0, sticky="nsew", padx=(22, 5), pady=18)
        tk.Label(intro, text="▣ PRONTO", bg=COLORS["panel"], fg=COLORS["green"], font=(FONT, 8, "bold")).pack(anchor="w")
        tk.Label(intro, text="J A M E S", bg=COLORS["panel"], fg=COLORS["text"], font=(FONT, 28, "bold")).pack(anchor="w", pady=(18, 2))
        tk.Label(intro, text="SEU ASSISTENTE INTELIGENTE", bg=COLORS["panel"], fg=COLORS["cyan"], font=(FONT, 9, "bold")).pack(anchor="w")
        tk.Label(intro, text="Pense. Planeje. Realize.\nJames está online e pronto para auxiliar\nseu trabalho e sua vida digital.", justify="left", bg=COLORS["panel"], fg=COLORS["muted"], font=(FONT, 9)).pack(anchor="w", pady=(18, 10))
        counts = self.db.counts(); tk.Label(intro, text=f"{counts['tasks']} tarefas  •  {counts['memories']} memórias", bg=COLORS["panel"], fg=COLORS["green"], font=(FONT, 8)).pack(anchor="w")
        HologramCore(parent).grid(row=0, column=1, sticky="nsew", pady=8)
        cap = tk.Frame(parent, bg=COLORS["panel"]); cap.grid(row=0, column=2, sticky="nsew", padx=(4, 18), pady=18)
        for icon, title, sub, color in (("◎", "COMPREENDER", "CONVERSA NATURAL", COLORS["green"]), ("◇", "RACIOCINAR", "CONTEXTO RECENTE", COLORS["cyan"]), ("□", "PLANEJAR", "FOCO EM OBJETIVOS", COLORS["blue"]), ("⚡", "EXECUTAR", "AÇÕES SUPERVISIONADAS", COLORS["green"])):
            row = tk.Frame(cap, bg=COLORS["panel"]); row.pack(fill="x", expand=True)
            tk.Label(row, text=icon, bg=COLORS["panel_alt"], fg=color, font=(FONT, 14), width=3, height=2).pack(side="left")
            texts = tk.Frame(row, bg=COLORS["panel"]); texts.pack(side="left", padx=8)
            tk.Label(texts, text=title, bg=COLORS["panel"], fg=COLORS["text"], font=(FONT, 8, "bold")).pack(anchor="w"); tk.Label(texts, text=sub, bg=COLORS["panel"], fg=COLORS["muted"], font=(FONT, 7)).pack(anchor="w")

    def _activity(self, parent: tk.Frame) -> None:
        self.dashboard_activity_panel = parent
        section_title(parent, "Atividade recente").pack(fill="x", padx=13, pady=(12, 8)); actions = self.db.recent_actions(7)
        if not actions: tk.Label(parent, text="Nenhuma ação executada ainda.", bg=COLORS["panel"], fg=COLORS["muted"]).pack(pady=30)
        for row in actions:
            item = tk.Frame(parent, bg=COLORS["panel_alt"], height=43); item.pack(fill="x", padx=10, pady=3); item.pack_propagate(False)
            tk.Label(item, text="◎", bg=COLORS["panel_alt"], fg=COLORS["green"] if row["success"] else COLORS["danger"], font=(FONT, 13)).pack(side="left", padx=8)
            info = tk.Frame(item, bg=COLORS["panel_alt"]); info.pack(side="left", fill="both", expand=True, pady=5)
            tk.Label(info, text=str(row["action"]).replace("_", " ").title(), bg=COLORS["panel_alt"], fg=COLORS["text"], font=(FONT, 8, "bold")).pack(anchor="w"); tk.Label(info, text=str(row["details"])[:38], bg=COLORS["panel_alt"], fg=COLORS["muted"], font=(FONT, 7)).pack(anchor="w")
            tk.Label(item, text=str(row["created_at"])[11:16], bg=COLORS["panel_alt"], fg=COLORS["muted"], font=(FONT_MONO, 7)).pack(side="right", padx=7)

    def _quick_actions(self, box: tk.Frame) -> tk.Frame:
        section_title(box, "Ações rápidas").pack(fill="x", padx=12, pady=(10, 6)); grid = tk.Frame(box, bg=COLORS["panel"]); grid.pack(fill="both", expand=True, padx=9, pady=(0, 9))
        actions = [("＋  Nova tarefa", self.add_task_dialog), ("▦  Aplicativos", lambda: self.show_page("apps")), ("◇  Organizar arquivos", self.organize_dialog), ("⌕  Localizar arquivo", lambda: self.find_dialog("")), ("▱  Nova memória", self.add_memory_dialog), ("⚙  Configurações", lambda: self.show_page("settings"))]
        for i, (text, cmd) in enumerate(actions): NeonButton(grid, text, cmd).grid(row=i//2, column=i%2, sticky="nsew", padx=3, pady=3)
        grid.grid_columnconfigure(0, weight=1); grid.grid_columnconfigure(1, weight=1); return box

    def _system_panel(self, box: tk.Frame) -> tk.Frame:
        section_title(box, "Monitor do sistema").pack(fill="x", padx=12, pady=(10, 4)); holder = tk.Frame(box, bg=COLORS["panel"]); holder.pack(expand=True)
        for name, color in (("CPU", COLORS["cyan"]), ("RAM", COLORS["green"]), ("Disco", COLORS["blue"])):
            gauge = Gauge(holder, name, color); gauge.pack(side="left", padx=3); self.gauges[name] = gauge
        return box

    def _snapshot(self, box: tk.Frame) -> tk.Frame:
        section_title(box, "Memória do James").pack(fill="x", padx=12, pady=(10, 5)); counts = self.db.counts()
        tk.Label(box, text=f"{counts['memories']:,}", bg=COLORS["panel"], fg=COLORS["text"], font=(FONT, 21, "bold")).pack(side="left", padx=(15, 7)); tk.Label(box, text=f"memórias locais\n{counts['conversations']} mensagens", justify="left", bg=COLORS["panel"], fg=COLORS["muted"], font=(FONT, 7)).pack(side="left"); return box

    def _recent_conversations(self, box: tk.Frame) -> tk.Frame:
        section_title(box, "Conversas recentes").pack(fill="x", padx=12, pady=(8, 3))
        messages = [row for row in self.db.conversations(10, self.assistant.conversation_id) if row["role"] == "user"][-3:]
        for row in reversed(messages):
            tk.Label(box, text="◌  " + str(row["content"]).replace("\n", " ")[:55], anchor="w", bg=COLORS["panel"], fg=COLORS["text"], font=(FONT, 7)).pack(fill="x", padx=12, pady=1)
        return box

    def _provider_panel(self, box: tk.Frame) -> tk.Frame:
        section_title(box, "Provedor e favoritos").pack(fill="x", padx=12, pady=(8, 4))
        provider = str(self.settings.get("ai_provider", "basic")).upper()
        model = self.settings.get("ollama_model") if provider == "OLLAMA" else self.settings.get("openai_model") if provider == "OPENAI" else "Comandos locais"
        tk.Label(box, text="●", bg=COLORS["panel"], fg=COLORS["green"], font=(FONT, 15)).pack(side="left", padx=(15, 7))
        info = tk.Frame(box, bg=COLORS["panel"]); info.pack(side="left")
        tk.Label(info, text=provider, bg=COLORS["panel"], fg=COLORS["text"], font=(FONT, 9, "bold")).pack(anchor="w"); tk.Label(info, text=str(model), bg=COLORS["panel"], fg=COLORS["cyan"], font=(FONT, 7)).pack(anchor="w")
        favorites = [app["display_name"] for app in self.db.applications() if app["is_favorite"]][:2]
        tk.Label(box, text="★ " + ("  •  ".join(favorites) if favorites else "marque aplicativos favoritos"), bg=COLORS["panel"], fg=COLORS["yellow"] if favorites else COLORS["muted"], font=(FONT, 7)).pack(side="bottom", anchor="w", padx=15, pady=5)
        return box

    def _page_header(self, parent, title, subtitle):
        head = tk.Frame(parent, bg=COLORS["bg"]); head.pack(fill="x", pady=(5, 10)); tk.Label(head, text=title.upper(), bg=COLORS["bg"], fg=COLORS["text"], font=(FONT, 17, "bold")).pack(anchor="w"); tk.Label(head, text=subtitle, bg=COLORS["bg"], fg=COLORS["muted"], font=(FONT, 9)).pack(anchor="w")

    def _conversations(self) -> None:
        self._page_header(self.content, "Histórico de Conversas", "Localize, consulte e retome diálogos armazenados no SQLite"); box = panel(self.content); box.pack(fill="both", expand=True)
        self.chat = ConversationView(box); self.chat.pack(fill="both", expand=True, padx=8, pady=8); self._render_history()

    def _reports(self) -> None:
        self._page_header(self.content, "Relatórios", "Resultados completos, etapas e erros das tarefas executadas")
        panes = tk.PanedWindow(self.content, orient="horizontal", bg=COLORS["bg"], sashwidth=6, bd=0); panes.pack(fill="both", expand=True)
        listing, detail = panel(panes), panel(panes); panes.add(listing, minsize=420); panes.add(detail, stretch="always", minsize=500)
        section_title(listing, "RELATÓRIOS ANTERIORES").pack(fill="x", padx=12, pady=10)
        self.report_tree = ttk.Treeview(listing, columns=("objective", "status", "date"), show="headings")
        for col, title, width in (("objective", "Objetivo", 300), ("status", "Estado", 85), ("date", "Data", 130)):
            self.report_tree.heading(col, text=title); self.report_tree.column(col, width=width)
        self.report_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10)); self.report_tree.bind("<<TreeviewSelect>>", lambda _e: self._load_selected_report())
        report_head = tk.Frame(detail, bg=COLORS["panel"]); report_head.pack(fill="x", padx=12, pady=10)
        section_title(report_head, "RESULTADO COMPLETO").pack(side="left")
        self.open_report_file_button = NeonButton(report_head, "ABRIR ARQUIVO", self.open_report_file, state="disabled"); self.open_report_file_button.pack(side="right")
        self.report_detail = tk.Text(detail, bg=COLORS["field"], fg=COLORS["text"], relief="flat", wrap="word", state="disabled", padx=12, pady=10)
        self.report_detail.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for row in self.db.automation_runs(100): self.report_tree.insert("", "end", iid=str(row["id"]), values=(row["objective"], row["status"], row["started_at"]))
        pending = getattr(self, "pending_report_id", None)
        if pending and self.report_tree.exists(str(pending)):
            self.report_tree.selection_set(str(pending)); self.report_tree.see(str(pending)); self._load_selected_report()
        elif self.report_tree.get_children():
            first = self.report_tree.get_children()[0]; self.report_tree.selection_set(first); self._load_selected_report()
        self.pending_report_id = None

    def show_report(self, run_id: int) -> None:
        self.pending_report_id = run_id; self.show_page("reports")

    def _load_selected_report(self) -> None:
        selected = self.report_tree.selection()
        if not selected: return
        run_id = int(selected[0]); run = next((row for row in self.db.automation_runs(200) if int(row["id"]) == run_id), None)
        if not run: return
        steps = self.db.automation_steps(run_id)
        lines = [f"OBJETIVO\n{run['objective']}", f"\nSTATUS\n{run['status']}", f"\nINÍCIO\n{run['started_at']}", f"\nRESULTADO\n{run['result'] or '—'}", f"\nERRO\n{run['error'] or '—'}", "\nETAPAS"]
        lines.extend(f"{step['step_index']}. [{step['status']}] {step['description']}\n   {step['details'] or ''}" for step in steps)
        self.report_detail.configure(state="normal"); self.report_detail.delete("1.0", "end"); self.report_detail.insert("1.0", "\n".join(lines)); self.report_detail.configure(state="disabled")
        self.current_report_file = self._authorized_report_file(" ".join((str(run["result"] or ""), str(run["error"] or ""))))
        self.open_report_file_button.configure(state="normal" if self.current_report_file else "disabled")

    def _authorized_report_file(self, text: str) -> Path | None:
        candidates = re.findall(r"[A-Za-z]:\\[^\n\r\"<>|]+", text)
        roots = [self.settings.data_dir.resolve(), *self.settings.allowed_directories]
        for raw in candidates:
            path = Path(raw.strip(" .'")).resolve()
            if not path.is_file(): continue
            for root in roots:
                try: path.relative_to(root); return path
                except ValueError: continue
        return None

    def open_report_file(self) -> None:
        path = getattr(self, "current_report_file", None)
        if path and path.is_file(): os.startfile(str(path))  # type: ignore[attr-defined]

    def _tasks(self) -> None:
        self._page_header(self.content, "Tarefas", "Planejamento e acompanhamento das tarefas cadastradas"); box = panel(self.content); box.pack(fill="both", expand=True); toolbar = tk.Frame(box, bg=COLORS["panel"]); toolbar.pack(fill="x", padx=10, pady=10)
        NeonButton(toolbar, "＋ NOVA TAREFA", self.add_task_dialog).pack(side="left"); NeonButton(toolbar, "CONCLUIR", self.complete_task, accent=COLORS["green"]).pack(side="left", padx=6); NeonButton(toolbar, "EXCLUIR", self.delete_task, accent=COLORS["danger"]).pack(side="left")
        self.task_tree = ttk.Treeview(box, columns=("title", "due", "priority"), show="headings")
        for col, text, width in (("title", "Tarefa", 550), ("due", "Prazo", 150), ("priority", "Prioridade", 120)): self.task_tree.heading(col, text=text); self.task_tree.column(col, width=width)
        self.task_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10)); self.refresh_tasks()

    def _reminders(self) -> None:
        self._page_header(self.content, "Agenda", "Lembretes locais, recorrências e notificações do Windows")
        box = panel(self.content); box.pack(fill="both", expand=True)
        toolbar = tk.Frame(box, bg=COLORS["panel"]); toolbar.pack(fill="x", padx=10, pady=10)
        NeonButton(toolbar, "＋ NOVO", self.add_reminder_dialog).pack(side="left")
        NeonButton(toolbar, "EDITAR", self.edit_reminder_dialog).pack(side="left", padx=4)
        NeonButton(toolbar, "CONCLUIR", self.complete_reminder, accent=COLORS["green"]).pack(side="left", padx=4)
        NeonButton(toolbar, "ADIAR", self.postpone_reminder_dialog).pack(side="left", padx=4)
        NeonButton(toolbar, "EXCLUIR", self.delete_reminder, accent=COLORS["danger"]).pack(side="left", padx=4)
        self.reminder_filter = tk.StringVar(value=getattr(self, "reminder_filter_name", "today"))
        filters = tk.Frame(box, bg=COLORS["panel"]); filters.pack(fill="x", padx=10, pady=(0, 8))
        for value, label in (("today", "HOJE"), ("upcoming", "PRÓXIMOS"), ("recurring", "RECORRENTES"), ("completed", "CONCLUÍDOS")):
            tk.Radiobutton(filters, text=label, value=value, variable=self.reminder_filter, command=self.refresh_reminders,
                           indicatoron=False, bg=COLORS["panel_alt"], fg=COLORS["text"], selectcolor="#0b4b66",
                           activebackground="#0b4b66", activeforeground=COLORS["cyan"], relief="flat", padx=12, pady=6).pack(side="left", padx=(0, 5))
        self.reminder_tree = ttk.Treeview(box, columns=("title", "when", "recurrence", "status"), show="headings")
        for col, text, width in (("title", "Lembrete", 500), ("when", "Data e horário", 180), ("recurrence", "Repetição", 110), ("status", "Estado", 110)):
            self.reminder_tree.heading(col, text=text); self.reminder_tree.column(col, width=width)
        self.reminder_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10)); self.refresh_reminders()

    def _selected_reminder_id(self) -> int | None:
        if not hasattr(self, "reminder_tree") or not self.reminder_tree.winfo_exists(): return None
        selected = self.reminder_tree.selection()
        if not selected:
            messagebox.showinfo("Agenda", "Selecione um lembrete.", parent=self.root); return None
        return int(selected[0])

    def add_reminder_dialog(self) -> None:
        title = simpledialog.askstring("Novo lembrete", "O que devo lembrar?", parent=self.root)
        if not title: return
        schedule = simpledialog.askstring("Novo lembrete", "Quando? Ex.: amanhã às 14h ou daqui a 30 minutos", parent=self.root)
        if schedule: self._submit_text(f"crie um lembrete para {title.strip()} {schedule.strip()}")

    def edit_reminder_dialog(self) -> None:
        reminder_id = self._selected_reminder_id()
        if reminder_id is None: return
        row = self.db.reminder(reminder_id)
        title = simpledialog.askstring("Editar lembrete", "Texto:", initialvalue=row["title"], parent=self.root)
        if not title: return
        current = datetime.fromisoformat(row["remind_at"]).strftime("%d/%m/%Y às %H:%M")
        schedule = simpledialog.askstring("Editar lembrete", "Nova data e horário:", initialvalue=current, parent=self.root)
        repeat = " todos os dias" if row["recurrence"] == "daily" else " toda semana" if row["recurrence"] == "weekly" else ""
        if schedule: self._submit_text(f"edite o lembrete {reminder_id} para {title.strip()} {schedule.strip()}{repeat}")

    def complete_reminder(self) -> None:
        reminder_id = self._selected_reminder_id()
        if reminder_id is not None:
            self.db.complete_reminder(reminder_id); self.refresh_reminders(); self.scheduler.wake(); self._set_nexus_state("success", "Lembrete concluído")

    def postpone_reminder_dialog(self) -> None:
        reminder_id = self._selected_reminder_id()
        if reminder_id is None: return
        minutes = simpledialog.askinteger("Adiar lembrete", "Adiar por quantos minutos?", initialvalue=10, minvalue=1, maxvalue=10080, parent=self.root)
        if minutes:
            self.db.postpone_reminder(reminder_id, datetime.now() + timedelta(minutes=minutes)); self.refresh_reminders(); self.scheduler.wake(); self._set_nexus_state("success", "Lembrete adiado")

    def delete_reminder(self) -> None:
        reminder_id = self._selected_reminder_id()
        if reminder_id is not None: self.confirm_delete_reminder(reminder_id)

    def confirm_delete_reminder(self, reminder_id: int) -> None:
        row = self.db.reminder(reminder_id)
        if not row: return
        self._set_nexus_state("confirmation", "Confirmar exclusão do lembrete")
        if messagebox.askyesno("Excluir lembrete", f"Excluir definitivamente “{row['title']}”?", parent=self.root):
            self.db.delete_reminder(reminder_id); self._append("assistant", "Lembrete excluído."); self.refresh_reminders(); self._set_nexus_state("success", "Lembrete excluído")
        else: self._set_nexus_state("idle", "Exclusão cancelada")

    def refresh_reminders(self) -> None:
        if not hasattr(self, "reminder_tree") or not self.reminder_tree.winfo_exists(): return
        filter_name = self.reminder_filter.get(); self.reminder_filter_name = filter_name
        self.reminder_tree.delete(*self.reminder_tree.get_children())
        recurrence_names = {"none": "Não", "daily": "Diária", "weekly": "Semanal"}
        for row in self.db.reminders(filter_name):
            when = datetime.fromisoformat(row["remind_at"]).strftime("%d/%m/%Y %H:%M")
            status = "Concluído" if row["completed"] else "Notificado" if row["notified"] else "Agendado"
            self.reminder_tree.insert("", "end", iid=str(row["id"]), values=(row["title"], when, recurrence_names.get(row["recurrence"], row["recurrence"]), status))

    def _memory(self) -> None:
        self._page_header(self.content, "Memória", "Informações autorizadas e armazenadas somente no banco local"); box = panel(self.content); box.pack(fill="both", expand=True); toolbar = tk.Frame(box, bg=COLORS["panel"]); toolbar.pack(fill="x", padx=10, pady=10)
        NeonButton(toolbar, "＋ NOVA MEMÓRIA", self.add_memory_dialog).pack(side="left"); NeonButton(toolbar, "EDITAR", self.edit_memory).pack(side="left", padx=6); NeonButton(toolbar, "EXCLUIR", self.delete_memory, accent=COLORS["danger"]).pack(side="left")
        self.memory_tree = ttk.Treeview(box, columns=("content", "category", "date"), show="headings")
        for col, text, width in (("content", "Informação guardada", 600), ("category", "Categoria", 130), ("date", "Atualizada", 170)): self.memory_tree.heading(col, text=text); self.memory_tree.column(col, width=width)
        self.memory_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10)); self.refresh_memories()

    def _settings(self) -> None:
        self._page_header(self.content, "Configurações", "Provedores, permissões e diretórios autorizados"); wrap = tk.Frame(self.content, bg=COLORS["bg"]); wrap.pack(fill="both", expand=True); wrap.grid_columnconfigure((0, 1), weight=1); wrap.grid_rowconfigure(0, weight=1)
        ai = panel(wrap); ai.grid(row=0, column=0, sticky="nsew", padx=(0, 5)); security = panel(wrap); security.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        section_title(ai, "Provedor de inteligência artificial").pack(fill="x", padx=15, pady=(16, 10))
        self.provider = tk.StringVar(value=self.settings.get("ai_provider")); self.model = tk.StringVar(value=self.settings.get("ollama_model")); self.openai_model = tk.StringVar(value=self.settings.get("openai_model", "gpt-6-luna")); self.share_cloud_memories = tk.BooleanVar(value=self.settings.get("share_memories_with_openai", False))
        current_model = str(self.settings.get("ollama_model", "qwen2.5:0.5b"))
        model_options = tuple(dict.fromkeys((current_model, "qwen3:1.7b", "qwen2.5:0.5b")))
        self._field(ai, "Provedor", self.provider, ("basic", "ollama", "openai")); self.model_combo = self._field(ai, "Modelo Ollama", self.model, model_options); self._field(ai, "Modelo OpenAI (pode gerar custos)", self.openai_model)
        NeonButton(ai, "ATUALIZAR MODELOS OLLAMA", self.refresh_ollama_models).pack(fill="x", padx=15, pady=(6, 2))
        tk.Checkbutton(ai, text="Enviar memórias autorizadas à OpenAI", variable=self.share_cloud_memories, bg=COLORS["panel"], fg=COLORS["text"], activebackground=COLORS["panel"], selectcolor=COLORS["field"]).pack(anchor="w", padx=15, pady=8)
        section_title(ai, "Voz local opcional").pack(fill="x", padx=15, pady=(8, 4))
        self.voice_input_enabled = tk.BooleanVar(value=self.settings.get("voice_input_enabled", False))
        self.voice_output_enabled = tk.BooleanVar(value=self.settings.get("voice_output_enabled", False))
        self.voice_model_path = tk.StringVar(value=self.settings.get("voice_model_path", ""))
        tk.Checkbutton(ai, text="Ativar entrada por microfone", variable=self.voice_input_enabled, bg=COLORS["panel"], fg=COLORS["text"], activebackground=COLORS["panel"], selectcolor=COLORS["field"]).pack(anchor="w", padx=15)
        tk.Checkbutton(ai, text="Falar respostas do James", variable=self.voice_output_enabled, bg=COLORS["panel"], fg=COLORS["text"], activebackground=COLORS["panel"], selectcolor=COLORS["field"]).pack(anchor="w", padx=15)
        self._field(ai, "Pasta do modelo Vosk em português", self.voice_model_path)
        NeonButton(ai, "SELECIONAR MODELO", self.choose_voice_model).pack(fill="x", padx=15, pady=(5, 2))
        NeonButton(ai, "SALVAR CONFIGURAÇÕES", self.save_settings).pack(fill="x", padx=15, pady=10)
        section_title(security, "Permissões de ferramentas").pack(fill="x", padx=15, pady=(16, 6)); self.permission_vars = {}
        labels = {"open_calculator": "Abrir calculadora", "open_notepad": "Abrir Bloco de Notas", "open_browser": "Abrir navegador", "open_directory": "Abrir pastas", "find_files": "Localizar arquivos", "organize_files": "Organizar arquivos", "system_info": "Ler informações do computador", "public_web_navigation": "Navegar em sites públicos", "browser_automation": "Automatizar navegador"}
        for key, label in labels.items():
            var = tk.BooleanVar(value=self.settings.permission(key)); self.permission_vars[key] = var; tk.Checkbutton(security, text=label, variable=var, bg=COLORS["panel"], fg=COLORS["text"], activebackground=COLORS["panel"], selectcolor=COLORS["field"]).pack(anchor="w", padx=15)
        section_title(security, "Pastas autorizadas").pack(fill="x", padx=15, pady=(12, 4)); self.dir_list = tk.Listbox(security, bg=COLORS["field"], fg=COLORS["text"], selectbackground="#0b4b66", relief="flat", height=6); self.dir_list.pack(fill="both", expand=True, padx=15, pady=5); self._reload_directories()
        buttons = tk.Frame(security, bg=COLORS["panel"]); buttons.pack(fill="x", padx=15, pady=8); NeonButton(buttons, "ADICIONAR", self.add_directory).pack(side="left"); NeonButton(buttons, "REMOVER", self.remove_directory).pack(side="left", padx=5)

    def _applications(self) -> None:
        self._page_header(self.content, "Aplicativos do Windows", "Catálogo local, permissões, apelidos e histórico de abertura")
        toolbar = panel(self.content); toolbar.pack(fill="x", pady=(0, 7))
        self.app_search = tk.StringVar(); entry = tk.Entry(toolbar, textvariable=self.app_search, bg=COLORS["field"], fg=COLORS["text"], insertbackground=COLORS["cyan"], relief="flat")
        entry.pack(side="left", fill="x", expand=True, padx=10, pady=9, ipady=6); entry.bind("<KeyRelease>", lambda _e: self.refresh_app_tree())
        NeonButton(toolbar, "ABRIR", self.open_selected_application).pack(side="left", padx=3, pady=7); NeonButton(toolbar, "ATUALIZAR", self.refresh_app_catalog).pack(side="left", padx=3, pady=7); NeonButton(toolbar, "ADICIONAR", self.add_manual_application).pack(side="left", padx=3, pady=7); NeonButton(toolbar, "APELIDO", self.add_application_alias).pack(side="left", padx=3, pady=7); NeonButton(toolbar, "PERMISSÃO", self.manage_application_permission).pack(side="left", padx=3, pady=7); NeonButton(toolbar, "★", self.toggle_application_favorite).pack(side="left", padx=(3, 10), pady=7)
        panes = tk.PanedWindow(self.content, orient="vertical", bg=COLORS["bg"], sashwidth=5, bd=0); panes.pack(fill="both", expand=True)
        catalog = panel(panes); history = panel(panes); panes.add(catalog, stretch="always", minsize=260); panes.add(history, minsize=120)
        self.app_tree = ttk.Treeview(catalog, columns=("name", "type", "source", "permission", "favorite"), show="headings")
        for col, text, width in (("name", "Aplicativo", 360), ("type", "Tipo", 100), ("source", "Fonte", 150), ("permission", "Permissão", 110), ("favorite", "Favorito", 70)): self.app_tree.heading(col, text=text); self.app_tree.column(col, width=width)
        self.app_tree.pack(fill="both", expand=True, padx=8, pady=8); self.app_tree.bind("<Double-1>", lambda _e: self.open_selected_application())
        section_title(history, "Histórico de abertura").pack(fill="x", padx=10, pady=(7, 2)); self.app_history = ttk.Treeview(history, columns=("name", "result", "time"), show="headings", height=4)
        for col, text, width in (("name", "Aplicativo", 350), ("result", "Resultado", 400), ("time", "Horário", 160)): self.app_history.heading(col, text=text); self.app_history.column(col, width=width)
        self.app_history.pack(fill="both", expand=True, padx=8, pady=(0, 8)); self.refresh_app_tree(); self.refresh_app_history()

    def _field(self, parent, label, var, values=None):
        tk.Label(parent, text=label, bg=COLORS["panel"], fg=COLORS["muted"]).pack(anchor="w", padx=15, pady=(5, 2)); widget = ttk.Combobox(parent, textvariable=var, values=values, state="readonly") if values else tk.Entry(parent, textvariable=var, bg=COLORS["field"], fg=COLORS["text"], insertbackground=COLORS["cyan"], relief="flat"); widget.pack(fill="x", padx=15, ipady=5)
        return widget

    def _core_page(self) -> None:
        self._page_header(self.content, "Núcleo NEXUS", "Estado real e identidade visual do assistente"); box = panel(self.content); box.pack(fill="both", expand=True)
        self.nexus_core = HologramCore(box, state=self.nexus_state); self.nexus_core.pack(fill="both", expand=True, padx=30, pady=20)

    def _automations(self) -> None:
        self._page_header(self.content, "NAVEGAÇÃO INTELIGENTE", "Sites, pesquisas e tarefas web supervisionadas")
        toolbar = panel(self.content); toolbar.pack(fill="x", pady=(0, 8))
        NeonButton(toolbar, "YOUTUBE", lambda: self._send_automation("abra o YouTube")).pack(side="left", padx=8, pady=8)
        NeonButton(toolbar, "GOOGLE", lambda: self._send_automation("abra o Google")).pack(side="left", padx=4, pady=8)
        NeonButton(toolbar, "WHATSAPP WEB", lambda: self._send_automation("abra o WhatsApp Web")).pack(side="left", padx=4, pady=8)
        NeonButton(toolbar, "VOLTAR", lambda: self._send_automation("volte para a pesquisa")).pack(side="right", padx=4, pady=8)
        NeonButton(toolbar, "INTERROMPER", self.stop_automation, accent=COLORS["danger"]).pack(side="right", padx=8, pady=8)
        status_box = panel(self.content); status_box.pack(fill="x", pady=(0, 8))
        self.navigation_status = tk.StringVar()
        tk.Label(status_box, textvariable=self.navigation_status, anchor="w", justify="left", bg=COLORS["panel"], fg=COLORS["cyan"], font=(FONT, 9)).pack(fill="x", padx=12, pady=8)
        body = tk.Frame(self.content, bg=COLORS["bg"]); body.pack(fill="both", expand=True)
        left, right = panel(body), panel(body); left.pack(side="left", fill="both", expand=True, padx=(0, 4)); right.pack(side="left", fill="both", expand=True, padx=(4, 0))
        section_title(left, "Plano e execucao").pack(fill="x", padx=12, pady=10)
        self.automation_steps_tree = ttk.Treeview(left, columns=("step", "status", "details"), show="headings")
        for col, title, width in (("step", "Etapa", 260), ("status", "Estado", 90), ("details", "Resultado / erro", 350)):
            self.automation_steps_tree.heading(col, text=title); self.automation_steps_tree.column(col, width=width)
        self.automation_steps_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        section_title(right, "Historico de tarefas").pack(fill="x", padx=12, pady=10)
        self.automation_history_tree = ttk.Treeview(right, columns=("objective", "status", "time"), show="headings")
        for col, title, width in (("objective", "Objetivo", 330), ("status", "Estado", 90), ("time", "Inicio", 135)):
            self.automation_history_tree.heading(col, text=title); self.automation_history_tree.column(col, width=width)
        self.automation_history_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10)); self.refresh_automations()

    def _send_automation(self, text: str) -> None:
        self.entry.delete(0, "end"); self.entry.insert(0, text); self.send()

    def stop_automation(self) -> None:
        response = self.assistant.stop_automation(); self._append("assistant", response.text); self.refresh_automations()

    def refresh_automations(self) -> None:
        if not hasattr(self, "automation_history_tree") or not self.automation_history_tree.winfo_exists(): return
        self.automation_history_tree.delete(*self.automation_history_tree.get_children()); runs = self.db.automation_runs()
        for row in runs: self.automation_history_tree.insert("", "end", iid=str(row["id"]), values=(row["objective"], row["status"], row["started_at"]))
        self.automation_steps_tree.delete(*self.automation_steps_tree.get_children())
        if runs:
            for step in self.db.automation_steps(int(runs[0]["id"])): self.automation_steps_tree.insert("", "end", values=(step["description"], step["status"], step["details"] or ""))
        context = self.assistant.orchestrator.context
        if hasattr(self, "navigation_status"):
            self.navigation_status.set(f"SITE: {context.current_site or '—'}   |   STATUS: {context.status}   |   ETAPA: {context.current_step or '—'}\nOBJETIVO: {context.objective or '—'}   |   RESULTADOS: {len(context.results)}   |   ERRO: {context.error or '—'}")

    def _development(self, page):
        self._page_header(self.content, page, "Módulo previsto no plano de evolução"); box = panel(self.content); box.pack(fill="both", expand=True); tk.Label(box, text="◌", bg=COLORS["panel"], fg=COLORS["cyan"], font=(FONT, 48)).pack(pady=(100, 10)); tk.Label(box, text="EM DESENVOLVIMENTO", bg=COLORS["panel"], fg=COLORS["text"], font=(FONT, 16, "bold")).pack(); tk.Label(box, text="Esta função ainda não executa nenhuma ação.", bg=COLORS["panel"], fg=COLORS["muted"]).pack(pady=8)

    def run(self): self.root.mainloop()
    def _on_close(self):
        try:
            self.scheduler.stop()
            self.voice.close()
            self.assistant.close()
        finally: self.root.destroy()
    def _on_root_destroy(self, event):
        if event.widget is self.root:
            self.scheduler.stop()
    def _tick_clock(self):
        now = datetime.now()
        weekdays = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")
        self.date_label.configure(text=f"{weekdays[now.weekday()].capitalize()}, {now:%d/%m/%Y}")
        self.time_label.configure(text=now.strftime("%H:%M:%S"))
        self.root.after(1000, self._tick_clock)
    def _update_monitor(self):
        try:
            snapshot = self.monitor.snapshot()
            for key, value in snapshot.items():
                if key in self.gauges and self.gauges[key].winfo_exists(): self.gauges[key].set_value(value)
            if hasattr(self, "footer_system") and self.footer_system.winfo_exists():
                provider = str(self.settings.get("ai_provider", "basic")).upper()
                self.footer_system.configure(text=f"CPU {snapshot['CPU']:.0f}%   RAM {snapshot['RAM']:.0f}%   DISCO {snapshot['Disco']:.0f}%   IA {provider}")
            if hasattr(self, "nexus_system"):
                self.nexus_system.set(f"CPU  {snapshot['CPU']:.0f}%\nRAM  {snapshot['RAM']:.0f}%\nDISCO  {snapshot['Disco']:.0f}%")
        except (OSError, AttributeError, tk.TclError): pass
        self.root.after(2500, self._update_monitor)
    def _valid_chat(self):
        try: return self.chat is not None and bool(self.chat.winfo_exists())
        except tk.TclError: return False
    def _render_history(self):
        if not self._valid_chat(): return
        rows = self.db.conversations(100, self.assistant.conversation_id)
        if isinstance(self.chat, ConversationView):
            self.chat.render(rows); return
        self.chat.configure(state="normal"); self.chat.delete("1.0", "end")
        for row in rows:
            label = "VOCÊ" if row["role"] == "user" else "JAMES"; self.chat.insert("end", f"{label}  {str(row['created_at'])[11:16]}\n{row['content']}\n", row["role"])
        self.chat.see("end"); self.chat.configure(state="disabled")
    def _append(self, role, content): self.db.add_conversation(role, content, self.assistant.conversation_id); self._render_history()

    def send(self):
        text = self.entry.get().strip()
        if not text: return
        self.entry.delete(0, "end"); self._submit_text(text)
    def _submit_text(self, text: str):
        self._stream_buffer = ""; self._append("user", text); self._set_nexus_state("processing", "Interpretando solicitação"); threading.Thread(target=self._process_background, args=(text,), daemon=True).start()
    def _process_background(self, text):
        pending: list[str] = []; pending_chars = 0; last_flush = time.monotonic()
        def flush() -> None:
            nonlocal pending_chars, last_flush
            if pending:
                self.responses.put(AssistantResponse("".join(pending), action="stream_delta")); pending.clear(); pending_chars = 0; last_flush = time.monotonic()
        def on_delta(chunk: str) -> None:
            nonlocal pending_chars
            pending.append(chunk); pending_chars += len(chunk)
            if pending_chars >= 64 or time.monotonic() - last_flush >= .06: flush()
        try:
            result = self.assistant.process(text, on_delta=on_delta); flush(); self.responses.put(result)
        except Exception as exc: self.responses.put(AssistantResponse(f"Ocorreu um erro controlado: {exc}"))
    def toggle_voice(self):
        if self.voice.recording:
            self._set_voice_state("Processando")
            self.voice.stop_recording()
            return
        self._set_voice_state("Processando")
        if not self.voice.start_recording():
            self._set_voice_state("Erro", "Não foi possível iniciar o microfone.")
    def cancel_voice(self):
        if self.voice.stop_recording(cancel=True):
            self._set_voice_state("Pronto")
    def _set_voice_state(self, state: str, detail: str = ""):
        self.voice_state = state
        colors = {"Ouvindo": COLORS["cyan"], "Processando": COLORS["yellow"], "Pronto": COLORS["green"], "Erro": COLORS["danger"]}
        symbols = {"Ouvindo": "◉", "Processando": "◌", "Pronto": "●", "Erro": "!"}
        color = colors.get(state, COLORS["muted"])
        label = "ERRO DE VOZ" if state == "Erro" else state.upper()
        self.processing.configure(text=f"{symbols.get(state, '●')} {label}", fg=color)
        if hasattr(self, "voice_button") and self.voice_button.winfo_exists():
            self.voice_button.configure(text="■" if state == "Ouvindo" else "🎙", fg=color)
        if hasattr(self, "voice_hint") and self.voice_hint.winfo_exists():
            suffix = f" — {detail[:65]}" if detail else ""
            self.voice_hint.configure(text=f"🎙 Voz: {state}{suffix}", fg=color)
        if state == "Erro" and detail:
            self.status.configure(text=f"● VOZ · {detail[:70]}", fg=color)
        nexus = {"Processando": "processing", "Erro": "error", "Pronto": "idle", "Ouvindo": "processing"}.get(state, "idle")
        self._set_nexus_state(nexus, detail or label.title())

    def _set_nexus_state(self, state: str, detail: str = "") -> None:
        if state not in {"idle", "processing", "success", "error", "confirmation"}: state = "idle"
        self.nexus_state, self.nexus_detail = state, detail or "Sistema pronto"
        colors = {"idle": COLORS["cyan"], "processing": COLORS["blue"], "success": COLORS["green"],
                  "error": COLORS["danger"], "confirmation": COLORS["yellow"]}
        labels = {"idle": "PRONTO", "processing": "PROCESSANDO", "success": "CONCLUÍDO",
                  "error": "ERRO", "confirmation": "AGUARDANDO CONFIRMAÇÃO"}
        color = colors[state]
        if hasattr(self, "processing") and self.processing.winfo_exists():
            self.processing.configure(text=f"● {labels[state]}", fg=color)
        if hasattr(self, "status") and self.status.winfo_exists():
            self.status.configure(text=f"● NEXUS · {(detail or labels[state])[:62]}", fg=color)
        if hasattr(self, "nexus_core") and self.nexus_core.winfo_exists():
            self.nexus_core.set_state(state)
            self.nexus_core._paint()

    def _response_nexus_state(self, response: AssistantResponse) -> str:
        explicit = {
            "processing": "processing", "confirmation": "confirmation", "confirmed": "confirmation",
            "requested": "idle", "executed": "success", "verified": "success", "error": "error",
        }
        if response.status in explicit:
            return explicit[response.status]
        if response.action in {"confirm_ai_tool", "confirm_application", "confirm_website", "choose_application", "confirm_delete_reminder", "organize", "find"}:
            return "confirmation"
        if response.action in {"refresh_apps", "catalog_refreshed"}: return "processing"
        text = response.text.casefold()
        if any(term in text for term in ("ocorreu um erro", "não foi possível", "não está mais disponível", "falha ao")):
            return "error"
        if response.action == "refresh_automations":
            context = self.assistant.orchestrator.context
            if context.status == "erro": return "error"
            verified_steps = ("página carregada", "vídeo selecionado", "vídeo aberto", "resultado aberto")
            return "success" if any(step in context.current_step.casefold() for step in verified_steps) else "idle"
        if response.action == "refresh_app_view":
            return "success" if "processo verificado" in text else "error" if "não foi possível" in text else "idle"
        if response.action in {"refresh_tasks", "refresh_memories", "refresh_reminders"}: return "success"
        if response.action == "application_not_found": return "error"
        return "idle"

    def _cancel_context_action(self) -> None:
        self.assistant.cancel_pending_actions()
        self._append("assistant", "Ação cancelada. Nada foi alterado ou aberto.")
        self._set_nexus_state("idle", "Ação cancelada")

    def _confirm_memory_delete(self) -> None:
        result = self.assistant.confirm_pending_memory_delete()
        self._append("assistant", result.text)
        self._set_nexus_state(self._response_nexus_state(result), result.text)
        if self.current_page == "memory": self.refresh_memories()
        self._refresh_dashboard_panels()

    def _show_response_feedback(self, response: AssistantResponse) -> None:
        if not self._valid_chat() or not isinstance(self.chat, ConversationView):
            return
        if response.status == "confirmed":
            self.chat.show_feedback("processing")
            return
        actions: tuple[tuple[str, object], ...] = ()
        if response.action == "confirm_ai_tool":
            actions = (("CONFIRMAR", lambda payload=response.payload: self._confirm_ai_tool(payload)),
                       ("CANCELAR", self._cancel_context_action))
        elif response.action == "confirm_application":
            actions = (("CONTINUAR", lambda app_id=str(response.payload): self.confirm_application(app_id)),
                       ("CANCELAR", self._cancel_context_action))
        elif response.action == "confirm_website":
            actions = (("ABRIR SITE", lambda url=str(response.payload): self.confirm_website(url)),
                       ("CANCELAR", self._cancel_context_action))
        elif response.action == "choose_application":
            actions = (("ESCOLHER", lambda matches=response.payload: self.choose_application(matches)),
                       ("CANCELAR", self._cancel_context_action))
        elif response.action == "confirm_delete_memory":
            actions = (("EXCLUIR", self._confirm_memory_delete), ("CANCELAR", self._cancel_context_action))
        elif response.action == "confirm_delete_reminder":
            actions = (("CONTINUAR", lambda reminder_id=int(response.payload): self.confirm_delete_reminder(reminder_id)),
                       ("CANCELAR", self._cancel_context_action))
        typed_actions = tuple((title, callback) for title, callback in actions if callable(callback))
        self.chat.show_feedback(response.status, typed_actions)
    def _poll_voice_events(self):
        try:
            while True:
                event = self.voice_events.get_nowait()
                if event.kind == "transcript":
                    self._set_voice_state("Processando")
                    self._submit_text(event.message)
                elif event.kind == "error":
                    self._set_voice_state("Erro", event.message)
                elif event.kind == "state":
                    self._set_voice_state(event.message)
        except queue.Empty:
            pass
    def _poll_scheduler_events(self):
        try:
            while True:
                event = self.scheduler_events.get_nowait()
                if event.kind == "error":
                    self._set_nexus_state("error", f"Agenda · {event.message}")
                elif event.kind == "notified":
                    self._set_nexus_state("confirmation", "Lembrete aguardando ação")
                else:
                    self._set_nexus_state("idle", "Agenda pronta")
                if self.current_page == "reminders": self.refresh_reminders()
        except queue.Empty:
            pass
    def _poll(self):
        self._poll_voice_events()
        self._poll_scheduler_events()
        try:
            while True:
                response = self.responses.get_nowait()
                if response.action == "stream_delta":
                    self._stream_buffer += response.text
                    if self._valid_chat() and isinstance(self.chat, ConversationView): self.chat.show_stream(self._stream_buffer)
                    self._set_nexus_state("processing", "Gerando resposta")
                    continue
                if response.action == "provider_status":
                    name, connected, detail = response.payload; self.status.configure(text=f"● {str(name).upper()} · {detail}", fg=COLORS["green"] if connected else COLORS["yellow"]); continue
                if response.action == "catalog_refreshed":
                    count, pending = response.payload
                    if self.current_page == "apps": self.refresh_app_tree()
                    self._set_nexus_state("processing" if pending else "idle", "Catálogo de aplicativos atualizado")
                    if pending == "__chatgpt__": self.responses.put(self.assistant.request_chatgpt_after_refresh())
                    elif pending: self.responses.put(self.assistant.request_application(pending))
                    continue
                if response.action == "ollama_models":
                    models = tuple(response.payload or ())
                    if hasattr(self, "model_combo") and self.model_combo.winfo_exists():
                        self.model_combo.configure(values=models or (self.model.get(), "qwen3:1.7b", "qwen2.5:0.5b"))
                    self._set_nexus_state("idle" if models else "error", "Modelos Ollama atualizados" if models else "Ollama indisponível")
                    continue
                self._append("assistant", response.text); self._stream_buffer = ""; self._set_nexus_state(self._response_nexus_state(response), response.text); self.voice.speak(response.text)
                confirmation_actions = {"confirm_ai_tool", "confirm_application", "confirm_website", "choose_application",
                                        "confirm_delete_memory", "confirm_delete_reminder"}
                waiting_in_chat = response.action in confirmation_actions and response.status != "confirmed"
                self._show_response_feedback(response)
                if response.action == "refresh_tasks" and self.current_page == "tasks": self.refresh_tasks()
                elif response.action == "refresh_memories" and self.current_page == "memory": self.refresh_memories()
                elif response.action == "organize": self.organize_dialog()
                elif response.action == "find": self.find_dialog(str(response.payload or ""))
                elif response.action == "confirm_ai_tool" and not waiting_in_chat: self._confirm_ai_tool(response.payload)
                elif response.action == "confirm_application" and not waiting_in_chat: self.confirm_application(str(response.payload))
                elif response.action == "confirm_website" and not waiting_in_chat: self.confirm_website(str(response.payload))
                elif response.action == "choose_application" and not waiting_in_chat: self.choose_application(response.payload)
                elif response.action == "application_not_found": self.application_not_found(str(response.payload or ""))
                elif response.action == "refresh_apps": self.refresh_app_catalog(auto=True, pending=str(response.payload or "") or None)
                elif response.action == "refresh_app_view": self.refresh_app_tree(); self.refresh_app_history()
                elif response.action == "refresh_automations" and self.current_page == "automations": self.refresh_automations()
                elif response.action == "refresh_reminders":
                    if self.current_page == "reminders": self.refresh_reminders()
                    self.scheduler.wake()
                elif response.action == "confirm_delete_memory" and not waiting_in_chat: self._confirm_memory_delete()
                elif response.action == "confirm_delete_reminder" and not waiting_in_chat: self.confirm_delete_reminder(int(response.payload))
                self._refresh_dashboard_panels()
                self._refresh_provider_status()
        except queue.Empty: pass
        self.root.after(100, self._poll)
    def _refresh_provider_status(self): threading.Thread(target=lambda: self.responses.put(AssistantResponse("", action="provider_status", payload=self.assistant.provider_status())), daemon=True).start()

    def refresh_ollama_models(self) -> None:
        self._set_nexus_state("processing", "Consultando modelos Ollama instalados")
        def worker():
            provider = OllamaProvider(str(self.settings.get("ollama_url")), str(self.settings.get("ollama_model")))
            installed = provider.models()
            choices = tuple(dict.fromkeys((*installed, str(self.model.get()), "qwen3:1.7b", "qwen2.5:0.5b")))
            self.responses.put(AssistantResponse("", action="ollama_models", payload=choices if installed else ()))
        threading.Thread(target=worker, daemon=True).start()

    def refresh_tasks(self):
        if not hasattr(self, "task_tree") or not self.task_tree.winfo_exists(): return
        self.task_tree.delete(*self.task_tree.get_children())
        for row in self.db.tasks(): self.task_tree.insert("", "end", iid=str(row["id"]), values=(row["title"], row["due_date"] or "—", row["priority"]))
    def add_task_dialog(self):
        title = simpledialog.askstring("Nova tarefa", "Descrição da tarefa:", parent=self.root)
        if title: self.db.add_task(title.strip()); self._append("assistant", f"Tarefa cadastrada: {title.strip()}"); self.refresh_tasks(); self._set_nexus_state("success", "Tarefa cadastrada")
    def complete_task(self):
        selected = self.task_tree.selection()
        if selected: self.db.complete_task(int(selected[0])); self.refresh_tasks(); self._set_nexus_state("success", "Tarefa concluída")
    def delete_task(self):
        selected = self.task_tree.selection()
        if selected:
            self._set_nexus_state("confirmation", "Confirmar exclusão da tarefa")
            if messagebox.askyesno("Confirmar", "Excluir a tarefa selecionada?", parent=self.root): self.db.delete_task(int(selected[0])); self.refresh_tasks(); self._set_nexus_state("success", "Tarefa excluída")
            else: self._set_nexus_state("idle", "Exclusão cancelada")
    def refresh_memories(self):
        if not hasattr(self, "memory_tree") or not self.memory_tree.winfo_exists(): return
        self.memory_tree.delete(*self.memory_tree.get_children())
        for row in self.db.memories(): self.memory_tree.insert("", "end", iid=str(row["id"]), values=(row["content"], row["category"], row["updated_at"]))
    def add_memory_dialog(self):
        content = simpledialog.askstring("Nova memória", "Informação a guardar:", parent=self.root)
        if content: self.db.add_memory(content.strip()); self._append("assistant", "Informação guardada com sua autorização."); self.refresh_memories(); self._set_nexus_state("success", "Memória armazenada")
    def edit_memory(self):
        selected = self.memory_tree.selection()
        if not selected: return
        current = self.memory_tree.item(selected[0], "values")[0]; content = simpledialog.askstring("Editar memória", "Corrija a informação:", initialvalue=current, parent=self.root)
        if content: self.db.update_memory(int(selected[0]), content.strip()); self.refresh_memories(); self._set_nexus_state("success", "Memória atualizada")
    def delete_memory(self):
        selected = self.memory_tree.selection()
        if selected:
            self._set_nexus_state("confirmation", "Confirmar exclusão da memória")
            if messagebox.askyesno("Confirmar", "Apagar esta memória?", parent=self.root): self.db.delete_memory(int(selected[0])); self.refresh_memories(); self._set_nexus_state("success", "Memória excluída")
            else: self._set_nexus_state("idle", "Exclusão cancelada")

    def save_settings(self):
        self.settings.set("ai_provider", self.provider.get()); self.settings.set("ollama_model", self.model.get().strip()); self.settings.set("openai_model", self.openai_model.get().strip()); self.settings.set("share_memories_with_openai", self.share_cloud_memories.get())
        self.settings.set("voice_input_enabled", self.voice_input_enabled.get()); self.settings.set("voice_output_enabled", self.voice_output_enabled.get()); self.settings.set("voice_model_path", self.voice_model_path.get().strip())
        self.settings.set("permissions", {k: v.get() for k, v in self.permission_vars.items()}); self._refresh_provider_status(); messagebox.showinfo("Configurações", "Configurações salvas.", parent=self.root)
    def choose_voice_model(self):
        path = filedialog.askdirectory(parent=self.root, title="Selecionar pasta do modelo Vosk")
        if path: self.voice_model_path.set(path)
    def add_directory(self):
        path = filedialog.askdirectory(parent=self.root, title="Autorizar pasta")
        if path and path not in self.dir_list.get(0, "end"): self.dir_list.insert("end", path); self._save_directories()
    def remove_directory(self):
        selected = self.dir_list.curselection()
        if selected: self.dir_list.delete(selected[0]); self._save_directories()
    def _save_directories(self): self.settings.set("allowed_directories", list(self.dir_list.get(0, "end")))
    def _reload_directories(self):
        if not hasattr(self, "dir_list") or not self.dir_list.winfo_exists(): return
        self.dir_list.delete(0, "end")
        for path in self.settings.get("allowed_directories", []): self.dir_list.insert("end", path)
    def _choose_authorized(self, title):
        raw = filedialog.askdirectory(parent=self.root, title=title)
        if not raw: return None
        path = Path(raw); allowed, reason = self.policy.validate_directory(path)
        if not allowed: messagebox.showwarning("Acesso não autorizado", reason, parent=self.root); return None
        return path
    def organize_dialog(self):
        allowed, reason = self.policy.require_permission("organize_files")
        if not allowed: messagebox.showwarning("Permissão", reason, parent=self.root); return
        OrganizerDialog(self.root, self.settings, self.db, self._reload_directories)
    def find_dialog(self, initial=""):
        allowed, reason = self.policy.require_permission("find_files")
        if not allowed: messagebox.showwarning("Permissão", reason, parent=self.root); return
        directory = self._choose_authorized("Pesquisar em qual pasta?")
        if not directory: return
        query = initial or simpledialog.askstring("Localizar arquivo", "Parte do nome:", parent=self.root)
        if not query: return
        results = find_files(directory, query); text = "Nenhum arquivo encontrado." if not results else "Arquivos encontrados:\n" + "\n".join(str(p) for p in results); self._append("assistant", text); self.show_page("conversations")
    def _confirm_ai_tool(self, payload):
        if not isinstance(payload, ToolCall): self._append("assistant", "Solicitação inválida; nenhuma ação foi executada."); self._set_nexus_state("error", "Solicitação inválida"); return
        self._set_nexus_state("confirmation", "Ação da IA aguardando autorização")
        if not messagebox.askyesno("Ação solicitada pela IA", f"A IA solicitou: {self.assistant._describe_tool_call(payload)}.\n\nAutorizar?", parent=self.root): self.db.log_action(payload.name, "Recusada pelo usuário", False, False); self._append("assistant", "Ação cancelada."); self._set_nexus_state("idle", "Ação cancelada"); return
        self._set_nexus_state("processing", "Executando ação autorizada")
        result = self.assistant.execute_ai_tool(payload); self._append("assistant", result.text)
        self._set_nexus_state(self._response_nexus_state(result), result.text)
        if result.action == "organize": self.organize_dialog()
        elif result.action == "find": self.find_dialog(str(result.payload or ""))
    def search_conversations(self):
        term = self.search_var.get().strip()
        if not term: return
        matches = [r for r in self.db.conversations(500, self.assistant.conversation_id) if term.casefold() in str(r["content"]).casefold()]; self.show_page("conversations")
        messagebox.showinfo("Pesquisa", f"{len(matches)} mensagem(ns) encontrada(s) para “{term}”." if matches else "Nenhuma conversa encontrada.", parent=self.root)

    def refresh_app_catalog(self, auto: bool = False, pending: str | None = None):
        self._set_nexus_state("processing", "Indexando aplicativos do Windows")
        def worker():
            try:
                records = ApplicationDiscoveryService().discover(); count = self.db.replace_discovered_applications(records)
                self.responses.put(AssistantResponse("", action="catalog_refreshed", payload=(count, pending)))
            except Exception as exc:
                self.responses.put(AssistantResponse(f"Não foi possível atualizar o catálogo: {exc}"))
        threading.Thread(target=worker, daemon=True).start()

    def refresh_app_tree(self):
        if not hasattr(self, "app_tree") or not self.app_tree.winfo_exists(): return
        self.app_tree.delete(*self.app_tree.get_children()); query = normalize_app_name(self.app_search.get()) if hasattr(self, "app_search") else ""
        for app in self.db.applications(query):
            permission = self.db.application_permission(app["id"]) or "perguntar"
            self.app_tree.insert("", "end", iid=app["id"], values=(app["display_name"], app["app_type"], app["discovery_source"], permission, "★" if app["is_favorite"] else ""))

    def refresh_app_history(self):
        if not hasattr(self, "app_history") or not self.app_history.winfo_exists(): return
        self.app_history.delete(*self.app_history.get_children())
        for row in self.db.application_launch_history(): self.app_history.insert("", "end", values=(row["display_name"], "Sucesso" if row["success"] else row["details"], row["opened_at"]))

    def open_selected_application(self):
        selected = self.app_tree.selection()
        if not selected: messagebox.showinfo("Aplicativos", "Selecione um aplicativo.", parent=self.root); return
        self.confirm_application(selected[0])

    def confirm_application(self, app_id: str):
        app = self.db.get_application(app_id)
        if not app: self.assistant.cancel_pending_open(); self._set_nexus_state("error", "Aplicativo indisponível"); messagebox.showwarning("Aplicativo", "O aplicativo não está mais disponível.", parent=self.root); return
        permission = self.db.application_permission(app_id)
        remember = False
        self._set_nexus_state("confirmation", f"Confirmar abertura de {app['display_name']}")
        if permission == "deny": self.assistant.cancel_pending_open(); self._set_nexus_state("error", "Aplicativo bloqueado"); messagebox.showwarning("Bloqueado", "A abertura deste aplicativo foi bloqueada nas permissões.", parent=self.root); return
        if permission == "allow":
            if not messagebox.askyesno("Abrir aplicativo", f"Confirmar a abertura de “{app['display_name']}”?", parent=self.root): self.assistant.cancel_pending_open(); self._set_nexus_state("idle", "Abertura cancelada"); return
        else:
            if not messagebox.askyesno("Autorizar aplicativo", f"Autorizar a abertura de “{app['display_name']}”?\n\nTipo: {app['app_type']}\nFonte: {app['discovery_source']}", parent=self.root): self.assistant.cancel_pending_open(); self._set_nexus_state("idle", "Abertura cancelada"); return
            remember = messagebox.askyesno("Lembrar decisão", "Deseja lembrar esta autorização para as próximas vezes?", parent=self.root)
            self.db.set_application_permission(app_id, "allow")
        self._set_nexus_state("processing", f"Solicitando abertura de {app['display_name']}")
        result = self.assistant.launch_application(app_id); self._append("assistant", result.text); self._set_nexus_state(self._response_nexus_state(result), result.text)
        if permission != "allow" and not remember: self.db.clear_application_permission(app_id)
        self.refresh_app_history(); self.refresh_app_tree()

    def confirm_website(self, url: str):
        if url != "https://chatgpt.com/":
            self.assistant.cancel_pending_open(); self._append("assistant", "Destino Web inválido; nada foi aberto."); self._set_nexus_state("error", "Destino Web inválido"); return
        self._set_nexus_state("confirmation", "Confirmar abertura do ChatGPT Web")
        if not messagebox.askyesno("Abrir site", "O ChatGPT Desktop não foi encontrado. Abrir o ChatGPT no navegador padrão?", parent=self.root):
            self.assistant.cancel_pending_open(); self._append("assistant", "Abertura cancelada."); self._set_nexus_state("idle", "Abertura cancelada"); return
        self._set_nexus_state("processing", "Solicitando abertura ao navegador padrão")
        threading.Thread(target=lambda: self.responses.put(self.assistant.confirm_pending_open()), daemon=True).start()

    def choose_application(self, matches):
        window = tk.Toplevel(self.root); window.title("Escolher aplicativo"); window.geometry("440x330"); window.configure(bg=COLORS["bg"]); window.transient(self.root); window.grab_set()
        tk.Label(window, text="QUAL APLICATIVO DESEJA ABRIR?", bg=COLORS["bg"], fg=COLORS["cyan"], font=(FONT, 11, "bold")).pack(anchor="w", padx=15, pady=15)
        listing = tk.Listbox(window, bg=COLORS["field"], fg=COLORS["text"], selectbackground="#0b4b66", relief="flat")
        listing.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        for match in matches: listing.insert("end", f"{match.display_name}  ({match.score:.0%})")
        def choose():
            selected = listing.curselection()
            if selected: app_id = matches[selected[0]].app_id; window.destroy(); self.confirm_application(app_id)
        NeonButton(window, "CONTINUAR", choose).pack(pady=(0, 15))

    def application_not_found(self, query: str):
        if messagebox.askyesno("Aplicativo não encontrado", f"Não encontrei “{query}”. Deseja cadastrar um executável portátil manualmente?", parent=self.root): self.add_manual_application()

    def add_manual_application(self):
        path = filedialog.askopenfilename(parent=self.root, title="Selecionar aplicativo", filetypes=(("Aplicativo Windows", "*.exe"),))
        if not path: return
        candidate = Path(path).resolve()
        if candidate.suffix.casefold() != ".exe" or not candidate.is_file(): messagebox.showerror("Aplicativo inválido", "Selecione um arquivo .exe existente.", parent=self.root); return
        name = simpledialog.askstring("Nome do aplicativo", "Nome exibido:", initialvalue=candidate.stem, parent=self.root)
        if not name: return
        app_id = make_app_id("portable", str(candidate), name); self.db.add_manual_application({"id": app_id, "display_name": name.strip(), "normalized_name": normalize_app_name(name), "launch_target": str(candidate), "app_user_model_id": None, "app_type": "portable", "discovery_source": "manual", "icon_path": str(candidate)}); self.refresh_app_tree()

    def add_application_alias(self):
        selected = self.app_tree.selection()
        if not selected: messagebox.showinfo("Apelido", "Selecione um aplicativo.", parent=self.root); return
        alias = simpledialog.askstring("Novo apelido", "Como você deseja chamar este aplicativo?", parent=self.root)
        if alias: self.db.set_application_alias(selected[0], alias.strip(), normalize_app_name(alias)); messagebox.showinfo("Apelido", "Apelido salvo.", parent=self.root)

    def toggle_application_favorite(self):
        selected = self.app_tree.selection()
        if not selected: return
        app = self.db.get_application(selected[0]); self.db.set_application_favorite(selected[0], not bool(app["is_favorite"])); self.refresh_app_tree()

    def manage_application_permission(self):
        selected = self.app_tree.selection()
        if not selected: messagebox.showinfo("Permissão", "Selecione um aplicativo.", parent=self.root); return
        app = self.db.get_application(selected[0])
        decision = messagebox.askyesnocancel("Permissão do aplicativo", f"Permitir abrir “{app['display_name']}”?\n\nSim: permitir sempre\nNão: bloquear\nCancelar: manter como está", parent=self.root)
        if decision is None: return
        self.db.set_application_permission(selected[0], "allow" if decision else "deny"); self.refresh_app_tree()
