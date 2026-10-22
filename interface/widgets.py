from __future__ import annotations

import math
import random
import tkinter as tk

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
        text_parts = []; self._message_labels = []
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

    def get(self, _start="1.0", _end="end") -> str:
        return self._plain_text


class HologramCore(tk.Canvas):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLORS["panel"], highlightthickness=0, bd=0, **kwargs)
        self.bind("<Configure>", self._draw)

    def _draw(self, _event=None) -> None:
        self.delete("all")
        width, height = max(self.winfo_width(), 10), max(self.winfo_height(), 10)
        cx, cy = width*.5, height*.48; radius = min(width*.27, height*.39)
        for factor, color, line in ((1.16,"#073c54",1),(1.08,"#08779a",1),(1.0,COLORS["cyan"],2),(.91,"#0a7192",1)):
            r = radius*factor; self.create_oval(cx-r,cy-r,cx+r,cy+r,outline=color,width=line)
        for offset in (-.56,-.3,0,.3,.56):
            yr = radius*math.sqrt(max(.05,1-offset*offset))
            self.create_oval(cx-yr,cy+offset*radius-8,cx+yr,cy+offset*radius+8,outline="#087997")
        for factor in (.35,.68):
            self.create_oval(cx-radius*factor,cy-radius,cx+radius*factor,cy+radius,outline="#08617e")
        self.create_oval(cx-radius*1.35,cy-radius*.32,cx+radius*1.35,cy+radius*.32,outline=COLORS["cyan_dim"],width=2)
        self.create_oval(cx-radius*1.15,cy-radius*.55,cx+radius*1.15,cy+radius*.55,outline=COLORS["green"])
        rng = random.Random(42)
        for _ in range(38):
            angle=rng.random()*math.tau; rr=radius*(.18+rng.random()*.86)
            x,y=cx+math.cos(angle)*rr,cy+math.sin(angle)*rr
            self.create_oval(x-1.5,y-1.5,x+1.5,y+1.5,fill=COLORS["cyan"],outline="")
        self.create_text(cx,cy-2,text="JAMES",fill=COLORS["cyan"],font=(FONT,max(15,int(radius*.17)),"bold"))
        self.create_text(cx,cy+28,text="AI CORE",fill=COLORS["green"],font=(FONT,8,"bold"))


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
