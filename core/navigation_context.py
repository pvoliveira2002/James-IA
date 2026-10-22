from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NavigationItem:
    title: str
    url: str
    snippet: str = ""


@dataclass
class NavigationContext:
    current_site: str = ""
    current_url: str = ""
    objective: str = ""
    current_query: str = ""
    results: list[NavigationItem] = field(default_factory=list)
    page_history: list[str] = field(default_factory=list)
    known_elements: list[str] = field(default_factory=list)
    status: str = "ocioso"
    current_step: str = ""
    error: str = ""

    def begin(self, objective: str, site: str = "") -> None:
        self.objective, self.current_site = objective, site
        self.status, self.current_step, self.error = "executando", "Iniciando", ""

    def update_results(self, query: str, items: list[NavigationItem], url: str) -> None:
        if self.current_url and self.current_url != url: self.page_history.append(self.current_url)
        self.current_query, self.results, self.current_url = query, items[:10], url
        self.known_elements = [item.title for item in self.results]
        self.status, self.current_step = "concluido", "Resultados apresentados"

    def fail(self, error: str) -> None:
        self.status, self.error, self.current_step = "erro", error, "Falha controlada"
