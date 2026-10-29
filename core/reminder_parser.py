from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ReminderCommand:
    action: str
    reminder_id: int | None = None
    title: str | None = None
    remind_at: datetime | None = None
    recurrence: str = "none"
    filter_name: str = "upcoming"
    postpone_minutes: int | None = None
    error: str | None = None


def _plain(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def _identifier(text: str) -> int | None:
    match = re.search(r"\blembrete\s*#?\s*(\d+)\b", _plain(text))
    return int(match.group(1)) if match else None


def _time_from(text: str) -> tuple[int, int] | None:
    patterns = (
        r"\b(?:as|às)\s*(\d{1,2})(?:[:h](\d{2}))?(?:\s*(?:h|horas?))?\b",
        r"\b(\d{1,2}):(\d{2})\b",
        r"\b(\d{1,2})h(\d{2})?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2) or 0)
            if hour > 23 or minute > 59:
                return None
            return hour, minute
    return None


def _schedule(text: str, now: datetime) -> tuple[datetime | None, str, str | None]:
    plain = _plain(text)
    recurrence = "daily" if re.search(r"\b(todos os dias|todo dia|diariamente)\b", plain) else (
        "weekly" if re.search(r"\b(toda semana|semanalmente|toda (?:segunda|terca|quarta|quinta|sexta|sabado|domingo)(?:-feira)?)\b", plain) else "none"
    )
    relative = re.search(r"\bdaqui a\s+(\d+)\s*(minutos?|horas?|dias?)\b", plain)
    if relative:
        amount = int(relative.group(1)); unit = relative.group(2)
        delta = timedelta(minutes=amount) if unit.startswith("minuto") else timedelta(hours=amount) if unit.startswith("hora") else timedelta(days=amount)
        return now + delta, recurrence, None

    clock = _time_from(text)
    date_value = None
    numeric = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", plain)
    if numeric:
        day, month = int(numeric.group(1)), int(numeric.group(2))
        year = int(numeric.group(3)) if numeric.group(3) else now.year
        if year < 100: year += 2000
        try:
            date_value = datetime(year, month, day)
            if not numeric.group(3) and date_value.date() < now.date():
                date_value = date_value.replace(year=year + 1)
        except ValueError:
            return None, recurrence, "A data informada não é válida. Use dia/mês/ano."
    elif "amanha" in plain:
        date_value = now + timedelta(days=1)
    elif re.search(r"\bhoje\b", plain):
        date_value = now
    else:
        weekdays = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}
        weekday_match = re.search(r"\b(?:toda\s+)?(segunda|terca|quarta|quinta|sexta|sabado|domingo)(?:-feira)?\b", plain)
        if weekday_match:
            wanted = weekdays[weekday_match.group(1)]
            days = (wanted - now.weekday()) % 7
            if days == 0 and (not clock or now.time() >= now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0).time()):
                days = 7
            date_value = now + timedelta(days=days)

    if date_value is not None and not clock:
        return None, recurrence, "Informe também o horário do lembrete, por exemplo: amanhã às 14h."
    if date_value is not None and clock:
        result = date_value.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        if result <= now and date_value.date() == now.date():
            return None, recurrence, "Esse horário já passou. Informe um horário futuro."
        return result, recurrence, None
    if recurrence != "none" and clock:
        result = now.replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
        if result <= now: result += timedelta(days=1)
        return result, recurrence, None
    if clock:
        return None, recurrence, "A data ficou ambígua. Informe hoje, amanhã ou uma data no formato dia/mês/ano."
    return None, recurrence, "Informe quando devo lembrar, incluindo data e horário."


def _clean_title(text: str) -> str:
    value = text
    patterns = (
        r"\bdaqui a\s+\d+\s*(?:minutos?|horas?|dias?)\b",
        r"\b(?:todos os dias|todo dia|diariamente|toda semana|semanalmente)\b",
        r"\b(?:hoje|amanhã|amanha)\b",
        r"\b(?:toda\s+)?(?:segunda|terça|terca|quarta|quinta|sexta|sábado|sabado|domingo)(?:-feira)?\b",
        r"\b(?:dia\s+)?\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
        r"\b(?:às|as)\s*\d{1,2}(?:[:h]\d{2})?(?:\s*(?:h|horas?))?\b",
        r"\b\d{1,2}:\d{2}\b",
        r"\b\d{1,2}h\d{0,2}\b",
    )
    for pattern in patterns:
        value = re.sub(pattern, " ", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" .,:;-–")
    value = re.sub(r"^(?:de|para|que)\s+", "", value, flags=re.I)
    return value.strip()


def parse_reminder_command(text: str, now: datetime | None = None) -> ReminderCommand | None:
    now = now or datetime.now()
    plain = _plain(text.strip())
    reminder_id = _identifier(text)

    if re.search(r"\b(exclua|excluir|apague|apagar|remova|remover)\b.*\blembrete\b", plain):
        return ReminderCommand("delete", reminder_id=reminder_id, error=None if reminder_id else "Informe o número do lembrete que deseja excluir.")
    if re.search(r"\b(conclua|concluir|finalize|finalizar|marque)\b.*\blembrete\b", plain):
        return ReminderCommand("complete", reminder_id=reminder_id, error=None if reminder_id else "Informe o número do lembrete que foi concluído.")
    postpone = re.search(r"\b(adie|adiar|postergue|postergar)\b.*\blembrete\b", plain)
    if postpone:
        relative = re.search(r"\bpor\s+(\d+)\s*(minutos?|horas?|dias?)\b", plain)
        if relative:
            amount, unit = int(relative.group(1)), relative.group(2)
            minutes = amount if unit.startswith("minuto") else amount * 60 if unit.startswith("hora") else amount * 1440
            return ReminderCommand("postpone", reminder_id=reminder_id, postpone_minutes=minutes,
                                   error=None if reminder_id else "Informe o número do lembrete que deseja adiar.")
        schedule_text = re.split(r"\bpara\b", text, maxsplit=1, flags=re.I)
        remind_at, _, error = _schedule(schedule_text[-1], now)
        return ReminderCommand("postpone", reminder_id=reminder_id, remind_at=remind_at,
                               error=("Informe o número do lembrete que deseja adiar." if not reminder_id else error))
    edit = re.search(r"\b(edite|editar|altere|alterar)\b.*\blembrete\b", plain)
    if edit:
        remainder = re.split(r"\b(?:para|:)\b", text, maxsplit=1, flags=re.I)
        body = remainder[-1] if len(remainder) > 1 else ""
        has_schedule = bool(re.search(r"\b(hoje|amanha|daqui|todos|todo|diariamente|semanalmente|\d{1,2}[/:h-])\b", _plain(body)))
        remind_at = None; recurrence = "none"; error = None
        if has_schedule:
            remind_at, recurrence, error = _schedule(body, now)
        title = _clean_title(body) or None
        if not reminder_id: error = "Informe o número do lembrete que deseja editar."
        elif not title and not remind_at and not error: error = "Informe o novo texto ou uma nova data para o lembrete."
        return ReminderCommand("edit", reminder_id=reminder_id, title=title, remind_at=remind_at, recurrence=recurrence, error=error)
    if re.search(r"\b(mostre|mostrar|liste|listar|quais|consulte|consultar|ver)\b.*\b(lembretes?|agenda)\b", plain) or plain in ("agenda", "minha agenda"):
        filter_name = "today" if "hoje" in plain else "recurring" if "recorrent" in plain else "completed" if "conclu" in plain else "upcoming"
        return ReminderCommand("list", filter_name=filter_name)

    explicit = bool(re.search(r"\b(crie|criar|adicione|adicionar|agende|agendar|novo|nova)\b.*\blembrete\b", plain))
    natural = bool(re.search(r"\bme lembre\b", plain) and re.search(r"\b(hoje|amanha|daqui a|todos os dias|todo dia|toda semana|semanalmente|\d{1,2}[/:h-])\b", plain))
    scheduled = bool(re.match(r"\s*(agende|agendar|marque)\b", plain) and re.search(r"\b(hoje|amanha|daqui a|todos os dias|todo dia|toda semana|semanalmente|\d{1,2}[/:h-])\b", plain))
    if not explicit and not natural and not scheduled:
        return None
    body = re.sub(r"^(?:crie|criar|adicione|adicionar|agende|agendar|novo|nova)\s+(?:um\s+)?lembrete\s*(?:para|de|que)?\s*", "", text, flags=re.I)
    body = re.sub(r"^me lembre\s*(?:de|que)?\s*", "", body, flags=re.I)
    body = re.sub(r"^(?:agende|agendar|marque)\s+", "", body, flags=re.I)
    remind_at, recurrence, error = _schedule(body, now)
    title = _clean_title(body)
    if not title:
        error = "Informe o que devo lembrar."
    return ReminderCommand("create", title=title or None, remind_at=remind_at, recurrence=recurrence, error=error)
