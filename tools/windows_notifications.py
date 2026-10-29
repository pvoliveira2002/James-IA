from __future__ import annotations

from typing import Callable, Mapping, Any


class WindowsReminderNotifier:
    """Notificação nativa opcional; callbacks executam apenas ações registradas."""

    def __init__(self, module_loader=__import__):
        self._module_loader = module_loader
        self._toaster = None
        self._active: dict[str, Any] = {}

    def _components(self):
        try:
            module = self._module_loader("windows_toasts", fromlist=["*"])
        except (ImportError, OSError) as exc:
            raise RuntimeError("Notificações do Windows indisponíveis. Instale windows-toasts.") from exc
        if self._toaster is None:
            self._toaster = module.InteractableWindowsToaster("James IA")
        return module

    def show(self, reminder: Mapping[str, Any], on_snooze: Callable[[], None],
             on_complete: Callable[[], None], on_error: Callable[[str], None]) -> bool:
        try:
            module = self._components()
            toast = module.Toast(["Lembrete do James", str(reminder["title"])])
            toast.AddAction(module.ToastButton("Adiar 10 min", "snooze"))
            toast.AddAction(module.ToastButton("Concluir", "complete"))
            key = str(getattr(toast, "tag", reminder["id"]))

            def cleanup() -> None:
                self._active.pop(key, None)

            def activated(event) -> None:
                argument = str(getattr(event, "arguments", ""))
                if argument == "snooze": on_snooze()
                elif argument == "complete": on_complete()
                cleanup()

            def failed(event) -> None:
                on_error(f"A notificação do Windows falhou: {getattr(event, 'error_code', 'erro desconhecido')}")
                cleanup()

            toast.on_activated = activated
            toast.on_failed = failed
            toast.on_dismissed = lambda _event: cleanup()
            self._active[key] = toast
            self._toaster.show_toast(toast)
            return True
        except Exception as exc:
            on_error(str(exc))
            return False
