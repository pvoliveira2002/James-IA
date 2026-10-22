from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
