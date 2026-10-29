from __future__ import annotations

import math
import random
import tkinter as tk
from collections.abc import Callable

from interface.theme import COLORS, FONT


def panel(parent, **kwargs) -> tk.Frame:
    return tk.Frame(parent, bg=COLORS["panel"], highlightbackground=COLORS["border_soft"],
                    highlightcolor=COLORS["cyan"], highlightthickness=1, bd=0, **kwargs)


def section_title(parent, text: str) -> tk.Label:
    return tk.Label(parent, text=text.upper(), bg=COLORS["panel"], fg=COLORS["cyan"],
                    font=(FONT, 9, "bold"), anchor="w")


class NeonButton(tk.Button):
    def __init__(self, parent, text: str, command=None, accent: str | None = None, **kwargs):
        color = accent or COLORS["cyan"]
        super().__init__(parent, text=text, command=command, bg=COLORS["panel_alt"], fg=COLORS["text"],
            activebackground="#0b3b50", activeforeground=color, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=COLORS["border_soft"],
            font=(FONT, 9), cursor="hand2", padx=10, pady=7, **kwargs)
        self._accent = color
        self._hover_level = 0
        self._hover_job = None
        self.bind("<Enter>", self._hover_on, add="+")
        self.bind("<Leave>", self._hover_off, add="+")
        self.bind("<Destroy>", self._hover_destroy, add="+")

    def _hover_on(self, _event=None) -> None:
        self._animate_hover(4)

    def _hover_off(self, _event=None) -> None:
        self._animate_hover(0)

    @staticmethod
    def _blend(first: str, second: str, amount: float) -> str:
        a = tuple(int(first[i:i+2], 16) for i in (1, 3, 5)); b = tuple(int(second[i:i+2], 16) for i in (1, 3, 5))
        return "#" + "".join(f"{round(x + (y-x)*amount):02x}" for x, y in zip(a, b))

    def _animate_hover(self, target: int) -> None:
        if self._hover_job:
            try: self.after_cancel(self._hover_job)
            except tk.TclError: pass
        direction = 1 if target > self._hover_level else -1
        if self._hover_level == target: return
        self._hover_level += direction
        ratio = self._hover_level / 4
        self.configure(bg=self._blend(COLORS["panel_alt"], "#0a3044", ratio),
                       fg=self._accent if ratio >= .5 else COLORS["text"],
                       highlightbackground=self._blend(COLORS["border_soft"], self._accent, ratio))
        self._hover_job = self.after(22, lambda: self._animate_hover(target)) if self._hover_level != target else None

    def _hover_destroy(self, event) -> None:
        if event.widget is self and self._hover_job:
            try: self.after_cancel(self._hover_job)
            except tk.TclError: pass
            self._hover_job = None


class ConversationView(tk.Frame):
    """Chat leve com balões, alinhamento por autor e rolagem que respeita leitura antiga."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLORS["field"], **kwargs)
        self.canvas = tk.Canvas(self, bg=COLORS["field"], highlightthickness=0, bd=0)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview,
                                      bg=COLORS["panel_alt"], troughcolor=COLORS["field"], relief="flat")
        self.messages = tk.Frame(self.canvas, bg=COLORS["field"])
        self.window = self.canvas.create_window((0, 0), window=self.messages, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True); self.scrollbar.pack(side="right", fill="y")
        self.messages.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.bind_all("<MouseWheel>", self._wheel, add="+")
        self._plain_text = ""; self._message_labels: list[tk.Label] = []
        self._stream_label: tk.Label | None = None
        self._feedback_frame: tk.Frame | None = None

    def _resize(self, event) -> None:
        should_follow = self.canvas.yview()[1] >= .97
        self.canvas.itemconfigure(self.window, width=event.width)
        wrap = max(220, event.width - 175)
        for label in self._message_labels: label.configure(wraplength=wrap)
        self.messages.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if should_follow:
            self.canvas.yview_moveto(1.0)

    def _wheel(self, event) -> str | None:
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget is self:
                self.canvas.yview_scroll(int(-event.delta / 120), "units")
                return "break"
            widget = getattr(widget, "master", None)
        return None

    def render(self, rows) -> None:
        should_follow = self.canvas.yview()[1] >= .97 or not self.messages.winfo_children()
        for child in self.messages.winfo_children(): child.destroy()
        text_parts = []; self._message_labels = []; self._stream_label = None; self._feedback_frame = None
        for row in rows:
            role, content, created = str(row["role"]), str(row["content"]), str(row["created_at"])[11:16]
            text_parts.append(f"{role}: {content}")
            line = tk.Frame(self.messages, bg=COLORS["field"]); line.pack(fill="x", padx=14, pady=5)
            side = "right" if role == "user" else "left"
            bubble_color = "#10384c" if role == "user" else COLORS["panel_alt"]
            accent = COLORS["cyan"] if role == "user" else COLORS["green"]
            bubble = tk.Frame(line, bg=bubble_color, highlightbackground=COLORS["border_soft"], highlightthickness=1)
            bubble.pack(side=side, padx=(70, 0) if side == "right" else (0, 70))
            tk.Label(bubble, text=("VOCÊ" if role == "user" else "JAMES") + f"  {created}",
                     bg=bubble_color, fg=accent, font=(FONT, 7, "bold"), anchor="w").pack(fill="x", padx=11, pady=(7, 1))
            label = tk.Label(bubble, text=content, justify="left", anchor="w", wraplength=max(220, self.canvas.winfo_width() - 175),
                             bg=bubble_color, fg=COLORS["text"], font=(FONT, 10))
            label.pack(fill="x", padx=11, pady=(1, 8)); self._message_labels.append(label)
        self._plain_text = "\n".join(text_parts)
        self.update_idletasks()
        if should_follow: self.canvas.yview_moveto(1.0)

    def show_stream(self, text: str) -> None:
        if self._stream_label is not None and self._stream_label.winfo_exists():
            self._stream_label.configure(text=text)
        else:
            line = tk.Frame(self.messages, bg=COLORS["field"]); line.pack(fill="x", padx=14, pady=5)
            bubble = tk.Frame(line, bg=COLORS["panel_alt"], highlightbackground=COLORS["blue"], highlightthickness=1)
            bubble.pack(side="left", padx=(0, 70))
            tk.Label(bubble, text="JAMES  ·  RESPONDENDO", bg=COLORS["panel_alt"], fg=COLORS["blue"],
                     font=(FONT, 7, "bold"), anchor="w").pack(fill="x", padx=11, pady=(7, 1))
            self._stream_label = tk.Label(
                bubble, text=text, justify="left", anchor="w",
                wraplength=max(220, self.canvas.winfo_width() - 175),
                bg=COLORS["panel_alt"], fg=COLORS["text"], font=(FONT, 10),
            )
            self._stream_label.pack(fill="x", padx=11, pady=(1, 8)); self._message_labels.append(self._stream_label)
        self.messages.update_idletasks(); self.canvas.configure(scrollregion=self.canvas.bbox("all")); self.canvas.yview_moveto(1.0)

    def show_feedback(self, status: str,
                      actions: tuple[tuple[str, Callable[[], None]], ...] = ()) -> None:
        labels = {
            "processing": ("PROCESSANDO", COLORS["blue"]),
            "confirmation": ("AGUARDANDO CONFIRMAÇÃO", COLORS["yellow"]),
            "requested": ("SOLICITADA · NÃO VERIFICADA", COLORS["cyan"]),
            "executed": ("EXECUTADA", COLORS["green"]),
            "verified": ("CONCLUÍDA · VERIFICADA", COLORS["green"]),
            "error": ("ERRO", COLORS["danger"]),
        }
        if status not in labels and not actions:
            return
        if self._feedback_frame is not None and self._feedback_frame.winfo_exists():
            self._feedback_frame.destroy()
        caption, color = labels.get(status, ("AÇÃO DISPONÍVEL", COLORS["cyan"]))
        frame = tk.Frame(self.messages, bg=COLORS["field"])
        frame.pack(fill="x", padx=15, pady=(0, 7)); self._feedback_frame = frame
        content = tk.Frame(frame, bg=COLORS["panel_alt"], highlightbackground=color, highlightthickness=1)
        content.pack(side="left", padx=(0, 70))
        tk.Label(content, text=f"● {caption}", bg=COLORS["panel_alt"], fg=color,
                 font=(FONT, 7, "bold")).pack(side="left", padx=9, pady=6)
        for title, command in actions:
            tk.Button(content, text=title, command=command, bg=COLORS["field"], fg=COLORS["text"],
                      activebackground="#0b3b50", activeforeground=color, relief="flat",
                      font=(FONT, 7, "bold"), cursor="hand2", padx=8, pady=3).pack(side="left", padx=(0, 6), pady=4)
        self.messages.update_idletasks(); self.canvas.configure(scrollregion=self.canvas.bbox("all")); self.canvas.yview_moveto(1.0)

    def get(self, _start="1.0", _end="end") -> str:
        return self._plain_text


class HologramCore(tk.Canvas):
    """Núcleo 2.5D leve: itens Canvas reutilizados e animação ligada ao estado real."""

    STATES = {
        "idle": ("#22d9ff", "PRONTO"),
        "processing": ("#287dff", "PROCESSANDO"),
        "success": ("#20e7a7", "CONCLUÍDO"),
        "error": ("#ff5368", "ERRO"),
        "confirmation": ("#ffb63d", "AGUARDANDO CONFIRMAÇÃO"),
    }

    def __init__(self, parent, state: str = "idle", **kwargs):
        super().__init__(parent, bg=kwargs.pop("bg", COLORS["panel"]), highlightthickness=0, bd=0, **kwargs)
        self.state = state if state in self.STATES else "idle"
        self.phase = 0.0
        self._geometry = (0, 0)
        self._destroyed = False
        rng = random.Random(30)
        self._particle_data = [(rng.random() * math.tau, .24 + rng.random() * .84,
                                .15 + rng.random() * .45, 1 + rng.randrange(2)) for _ in range(34)]
        self._glow: list[int] = []; self._latitude: list[int] = []
        self._longitude: list[int] = []; self._orbits: list[int] = []
        self._particles: list[int] = []
        self.bind("<Configure>", self._rebuild, add="+")
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.after_idle(self._tick)

    def set_state(self, state: str) -> None:
        aliases = {"ready": "idle", "waiting": "confirmation", "confirm": "confirmation",
                   "completed": "success", "verified": "success"}
        state = aliases.get(state, state)
        if state not in self.STATES: state = "idle"
        self.state = state
        self._paint()

    def _on_destroy(self, event) -> None:
        if event.widget is self: self._destroyed = True

    @staticmethod
    def _mix(first: str, second: str, amount: float) -> str:
        a = tuple(int(first[i:i+2], 16) for i in (1, 3, 5)); b = tuple(int(second[i:i+2], 16) for i in (1, 3, 5))
        return "#" + "".join(f"{round(x + (y-x)*amount):02x}" for x, y in zip(a, b))

    def _rebuild(self, _event=None) -> None:
        width, height = max(self.winfo_width(), 20), max(self.winfo_height(), 20)
        if (width, height) == self._geometry: return
        self._geometry = (width, height); self.delete("all")
        self._glow = [self.create_oval(0, 0, 1, 1, width=0) for _ in range(14)]
        self._latitude = [self.create_oval(0, 0, 1, 1, fill="", width=1) for _ in range(5)]
        self._longitude = [self.create_oval(0, 0, 1, 1, fill="", width=1) for _ in range(3)]
        self._orbits = [self.create_arc(0, 0, 1, 1, style="arc", width=2, extent=235) for _ in range(3)]
        self._particles = [self.create_oval(0, 0, 2, 2, width=0) for _ in self._particle_data]
        self._title = self.create_text(0, 0, text="JAMES", font=(FONT, 20, "bold"))
        self._subtitle = self.create_text(0, 0, text="NEXUS CORE 3.1", font=(FONT, 7, "bold"))
        self._state_text = self.create_text(0, 0, font=(FONT, 7, "bold"))
        self._paint()

    def _paint(self) -> None:
        if not self._glow or self._destroyed: return
        width, height = self._geometry; cx, cy = width * .5, height * .45
        base = min(width * .23, height * .31); color, caption = self.STATES[self.state]
        speed = {"idle": .018, "processing": .075, "success": .045, "error": .10, "confirmation": .035}[self.state]
        amplitude = {"idle": .012, "processing": .035, "success": .065, "error": .04, "confirmation": .024}[self.state]
        radius = base * (1 + math.sin(self.phase * 1.7) * amplitude)
        for index, item in enumerate(self._glow):
            factor = 1.16 - index * .073
            r = radius * factor
            strength = .08 + index * .052
            fill = self._mix(COLORS["panel"], color, min(.78, strength))
            if index > 10: fill = self._mix(color, COLORS["white"], (index-10) * .16)
            self.coords(item, cx-r, cy-r, cx+r, cy+r); self.itemconfigure(item, fill=fill, outline="")
        for index, item in enumerate(self._latitude):
            offset = (-.58, -.30, 0, .30, .58)[index]
            horizontal = radius * math.sqrt(max(.06, 1-offset*offset))
            vertical = max(3, radius * .075)
            self.coords(item, cx-horizontal, cy+offset*radius-vertical, cx+horizontal, cy+offset*radius+vertical)
            self.itemconfigure(item, outline=self._mix(COLORS["panel"], color, .65))
        for index, item in enumerate(self._longitude):
            scale = (.28, .58, .88)[index]
            self.coords(item, cx-radius*scale, cy-radius, cx+radius*scale, cy+radius)
            self.itemconfigure(item, outline=self._mix(COLORS["panel"], color, .55))
        for index, item in enumerate(self._orbits):
            orbit_x = radius * (1.28 + index*.15); orbit_y = radius * (.35 + index*.14)
            self.coords(item, cx-orbit_x, cy-orbit_y, cx+orbit_x, cy+orbit_y)
            self.itemconfigure(item, outline=self._mix(COLORS["panel"], color, .72),
                               start=(self.phase * (34 + index*13) + index*90) % 360)
        for item, (angle, distance, particle_speed, size) in zip(self._particles, self._particle_data):
            theta = angle + self.phase * particle_speed
            depth = .44 + .56 * ((math.sin(theta)+1)/2)
            x = cx + math.cos(theta) * radius * distance
            y = cy + math.sin(theta) * radius * distance * .72
            point = size * depth
            self.coords(item, x-point, y-point, x+point, y+point)
            self.itemconfigure(item, fill=self._mix(COLORS["panel"], color, .55 + depth*.38))
        title_size = max(13, int(radius * .17))
        self.coords(self._title, cx, cy-2); self.itemconfigure(self._title, fill=COLORS["white"], font=(FONT, title_size, "bold"))
        self.coords(self._subtitle, cx, cy+radius*.24); self.itemconfigure(self._subtitle, fill=color)
        self.coords(self._state_text, cx, cy+radius*1.43); self.itemconfigure(self._state_text, text=f"●  {caption}", fill=color)
        self.phase = (self.phase + speed) % math.tau

    def _tick(self) -> None:
        if self._destroyed: return
        try:
            if self.winfo_exists(): self._paint()
            visible = bool(self.winfo_viewable())
            delay = 55 if visible and self.state != "idle" else 120 if visible else 350
            self.after(delay, self._tick)
        except tk.TclError:
            self._destroyed = True


class Gauge(tk.Canvas):
    def __init__(self, parent, label: str, color: str, **kwargs):
        super().__init__(parent,width=96,height=84,bg=COLORS["panel"],highlightthickness=0,**kwargs)
        self.label,self.color=label,color; self.set_value(0)

    def set_value(self, value: float) -> None:
        self.delete("all"); value=max(0,min(100,value))
        self.create_arc(12,5,84,77,start=45,extent=270,style="arc",outline="#153849",width=7)
        self.create_arc(12,5,84,77,start=45,extent=270*value/100,style="arc",outline=self.color,width=7)
        self.create_text(48,35,text=f"{value:.0f}%",fill=COLORS["text"],font=(FONT,11,"bold"))
        self.create_text(48,57,text=self.label,fill=COLORS["muted"],font=(FONT,8))
