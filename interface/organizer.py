from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from config.settings import Settings
from memory.database import Database
from security.policy import SecurityPolicy
from tools.file_manager import MovePlan, execute_organization, preview_organization


BG, PANEL, GREEN, TEXT, MUTED = "#080c0e", "#101719", "#37ff8b", "#e7f7ee", "#83968b"


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class OrganizerDialog:
    """Janela supervisionada: selecionar, analisar, prever e somente então confirmar."""

    def __init__(self, parent: tk.Misc, settings: Settings, database: Database,
                 on_directories_changed: Callable[[], None] | None = None):
        self.parent, self.settings, self.db = parent, settings, database
        self.policy = SecurityPolicy(settings)
        self.on_directories_changed = on_directories_changed
        self.directory: Path | None = None
        self.plans: list[MovePlan] = []
        self.work: queue.Queue[tuple[str, object]] = queue.Queue()
        self.window = tk.Toplevel(parent)
        self.window.title("James IA — Organizador de arquivos")
        self.window.geometry("1050x570"); self.window.minsize(850, 480)
        self.window.configure(bg=BG); self.window.transient(parent)
        self._build(); self.window.after(100, self._poll)

    def _build(self) -> None:
        top = ttk.Frame(self.window, padding=12); top.pack(fill="x")
        ttk.Label(top, text="ORGANIZADOR DE ARQUIVOS", style="Title.TLabel").pack(side="left")
        self.folder_label = ttk.Label(top, text="Nenhuma pasta selecionada", foreground=MUTED)
        self.folder_label.pack(side="left", padx=18)
        self.include_subfolders = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text="Incluir subpastas", variable=self.include_subfolders, bg=BG, fg=TEXT,
                       activebackground=BG, activeforeground=GREEN, selectcolor="#17382a").pack(side="right")

        columns = ("name", "extension", "size", "source", "category", "destination")
        self.tree = ttk.Treeview(self.window, columns=columns, show="headings")
        headings = ("Nome", "Extensão", "Tamanho", "Pasta de origem", "Categoria sugerida", "Destino proposto")
        widths = (170, 75, 85, 210, 145, 230)
        for column, heading, width in zip(columns, headings, widths):
            self.tree.heading(column, text=heading); self.tree.column(column, width=width, minwidth=60)
        scroll_y = ttk.Scrollbar(self.window, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(self.window, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.pack(fill="both", expand=True, padx=(12, 28)); scroll_y.place(relx=1, x=-27, y=62, relheight=.72)
        scroll_x.pack(fill="x", padx=12)

        self.summary = ttk.Label(self.window, text="Selecione uma pasta para começar.", foreground=MUTED)
        self.summary.pack(fill="x", padx=12, pady=6)
        buttons = ttk.Frame(self.window, padding=(12, 4, 12, 12)); buttons.pack(fill="x")
        ttk.Button(buttons, text="Selecionar pasta", command=self.select_directory).pack(side="left")
        self.analyze_button = ttk.Button(buttons, text="Analisar arquivos", command=self.analyze, state="disabled")
        self.analyze_button.pack(side="left", padx=5)
        self.preview_button = ttk.Button(buttons, text="Pré-visualizar organização", command=self.show_preview, state="disabled")
        self.preview_button.pack(side="left")
        self.confirm_button = ttk.Button(buttons, text="Confirmar organização", command=self.confirm, state="disabled")
        self.confirm_button.pack(side="left", padx=5)
        ttk.Button(buttons, text="Cancelar", command=self.window.destroy).pack(side="right")

    def select_directory(self) -> None:
        raw = filedialog.askdirectory(parent=self.window, title="Selecione a pasta que deseja organizar")
        if not raw: return
        path = Path(raw)
        try: path = path.expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("Pasta inválida", f"Não foi possível acessar a pasta:\n{exc}", parent=self.window); return
        allowed, reason = self.policy.validate_directory(path)
        if not allowed:
            authorize = messagebox.askyesno(
                "Pasta não autorizada",
                f"{reason}\n\nDeseja autorizar explicitamente esta pasta?\n{path}", parent=self.window)
            if not authorize: return
            directories = list(self.settings.get("allowed_directories", []))
            if str(path) not in directories: directories.append(str(path)); self.settings.set("allowed_directories", directories)
            if self.on_directories_changed: self.on_directories_changed()
        self.directory = path; self.plans = []
        self.folder_label.configure(text=str(path)); self.summary.configure(text="Pasta selecionada. Clique em Analisar arquivos.")
        self.tree.delete(*self.tree.get_children()); self.analyze_button.configure(state="normal")
        self.preview_button.configure(state="disabled"); self.confirm_button.configure(state="disabled")

    def analyze(self) -> None:
        if not self.directory: return
        self._busy(True); self.summary.configure(text="Analisando arquivos sem mover nada...")
        directory, recursive = self.directory, self.include_subfolders.get()
        threading.Thread(target=self._analyze_worker, args=(directory, recursive), daemon=True).start()

    def _analyze_worker(self, directory: Path, recursive: bool) -> None:
        try: self.work.put(("analyzed", preview_organization(directory, recursive)))
        except (OSError, PermissionError) as exc: self.work.put(("error", f"Não foi possível ler a pasta: {exc}"))

    def _fill(self, show_destination: bool) -> None:
        self.tree.delete(*self.tree.get_children())
        for plan in self.plans:
            self.tree.insert("", "end", values=(plan.source.name, plan.extension, format_size(plan.size),
                str(plan.source.parent), plan.category, str(plan.destination) if show_destination else "—"))

    def show_preview(self) -> None:
        self._fill(True); self.confirm_button.configure(state="normal")
        self.summary.configure(text=f"Prévia pronta: {len(self.plans)} arquivo(s). Nada foi movido. Confirme para executar.")

    def confirm(self) -> None:
        if not self.plans: return
        if not messagebox.askyesno("Confirmar organização",
                f"Mover {len(self.plans)} arquivo(s) para as pastas propostas?\n\nNenhum arquivo será apagado ou sobrescrito.", parent=self.window):
            return
        self._busy(True); self.summary.configure(text="Organizando arquivos...")
        threading.Thread(target=self._execute_worker, args=(list(self.plans),), daemon=True).start()

    def _execute_worker(self, plans: list[MovePlan]) -> None:
        try: self.work.put(("completed", execute_organization(plans)))
        except (OSError, PermissionError) as exc: self.work.put(("execution_error", str(exc)))

    def _busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.analyze_button.configure(state=state)
        if busy: self.preview_button.configure(state="disabled"); self.confirm_button.configure(state="disabled")

    def _poll(self) -> None:
        if not self.window.winfo_exists(): return
        try:
            while True:
                event, payload = self.work.get_nowait()
                if event == "analyzed":
                    self.plans = payload  # type: ignore[assignment]
                    self._busy(False); self._fill(False)
                    if self.plans:
                        self.preview_button.configure(state="normal")
                        self.summary.configure(text=f"{len(self.plans)} arquivo(s) encontrado(s). Clique em Pré-visualizar organização.")
                    else:
                        self.summary.configure(text="Nenhum arquivo foi encontrado. A pasta pode estar vazia ou conter apenas subpastas.")
                        messagebox.showinfo("Pasta sem arquivos", "Nenhum arquivo foi encontrado no nível selecionado.", parent=self.window)
                elif event == "completed":
                    count = int(payload); self.db.log_action("organize_files", str(self.directory), True, True)
                    self.plans = []; self._fill(False); self._busy(False)
                    self.summary.configure(text=f"Organização concluída: {count} arquivo(s) movido(s).")
                    messagebox.showinfo("Concluído", f"{count} arquivo(s) foram organizados com segurança.", parent=self.window)
                else:
                    self._busy(False); self.db.log_action("organize_files", str(payload), True, False)
                    messagebox.showerror("Erro", str(payload), parent=self.window)
        except queue.Empty: pass
        self.window.after(100, self._poll)
