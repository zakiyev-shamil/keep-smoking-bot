from __future__ import annotations

from app.core.enums import EventStatus, EventType, ResponseType
from app.models.event import Event
from app.models.party_member import PartyMember
from app.models.user import User
from app.services.dto import EventDetails, UserPartyStats


def display_name(user: User) -> str:
    return user.first_name or (f"@{user.username}" if user.username else "Участник")


WELCOME_NO_PARTY = (
    "Привет.\n\n"
    "Этот бот помогает быстро собрать коллег на перекур, обед или своё событие.\n\n"
    "Ты пока не состоишь ни в одной Party."
)
CREATE_PARTY_NAME = "Введите название Party."
INVALID_PARTY_NAME = "Название должно содержать от 1 до 100 символов. Попробуйте ещё раз."
INVALID_INVITATION = "Приглашение недействительно или устарело."
GENERIC_ERROR = "Что-то пошло не так. Попробуйте ещё раз."
HELP = (
    "Office Party помогает позвать коллег на перекур, обед или своё событие.\n\n"
    "Используйте /menu, а дальше — кнопки. Приглашение в Party открывается по ссылке."
)


def party_created(name: str, invite_url: str) -> str:
    return f"🏢 {name} создана.\n\nТеперь пригласи коллег:\n{invite_url}"


def party_joined(name: str, joined: bool) -> str:
    if joined:
        return f"Ты вступил в:\n\n🏢 {name}"
    return f"Ты уже состоишь в {name}."


def party_screen(name: str, members_count: int) -> str:
    return f"🏢 {name}\n\n👥 {members_count} участников\n\nЧто делаем?"


def event_confirmation(event_type, party_name: str, recipients: int) -> str:
    return (
        f"{event_type.emoji} Позвать {party_name}: «{event_type.default_title}»?\n\n"
        f"Получат уведомление: {recipients} человек."
    )


def custom_event_confirmation(title: str, party_name: str, recipients: int) -> str:
    return f"🎮 {title}\n\nПозвать {party_name}?\n\nПолучат уведомление: {recipients} человек."


def event_started_notification(event: Event) -> str:
    return f"{event.type.emoji} Выходим!\n\n{event.party.name} уже собирается."


def event_cancelled_notification(event: Event) -> str:
    return f"{event.type.emoji} Событие «{event.title}» отменено."


def participant_joined_notification(event: Event, user: User, going_count: int) -> str:
    return (
        f"👋 {display_name(user)} теперь идёт\n\n"
        f"{event.type.emoji} {event.title} · {event.party.name}\n"
        f"✅ Всего идут — {going_count}"
    )


def event_details_text(details: EventDetails) -> str:
    event = details.event
    stats = details.stats
    status = {
        EventStatus.ACTIVE: "Собираемся",
        EventStatus.STARTED: "Уже вышли",
        EventStatus.CANCELLED: "Отменено",
        EventStatus.EXPIRED: "Завершено",
    }[event.status]
    going_names = "\n".join(f"• {display_name(user)}" for user in stats.going_users)
    if not going_names:
        going_names = "—"
    return (
        f"{event.type.emoji} {event.title}\n"
        f"{display_name(event.creator)} зовёт {event.party.name}.\n"
        f"Статус: {status}\n\n"
        f"✅ Идут — {stats.going_count}\n"
        f"⏱ Через 5 минут — {stats.later_count}\n"
        f"❌ Пас — {stats.declined_count}\n\n"
        f"Идут:\n{going_names}"
    )


def duplicate_event_text(event: Event, going_count: int) -> str:
    return (
        f"{event.type.emoji} Уже есть активное предложение: «{event.title}».\n\n"
        f"Создал: {display_name(event.creator)}\n"
        f"Идут: {going_count} человек"
    )


def members_text(
    party_name: str, members: list[PartyMember], total: int, page: int, pages: int
) -> str:
    role_icon = {"owner": "👑", "admin": "🛡", "member": "•"}
    lines = [f"{role_icon[member.role.value]} {display_name(member.user)}" for member in members]
    return (
        f"👥 {party_name}\n\n{total} участников\n\n"
        + ("\n".join(lines) if lines else "Участников нет")
        + f"\n\nСтраница {page + 1}/{max(1, pages)}"
    )


def user_party_stats_text(stats: UserPartyStats) -> str:
    by_type = stats.participation_by_type
    return (
        f"📊 Твоя статистика · {stats.party.name}\n\n"
        f"🚬 Выходил курить — {by_type.get(EventType.SMOKE, 0)}\n"
        f"🍔 Ходил обедать — {by_type.get(EventType.LUNCH, 0)}\n"
        f"🎮 Свои события — {by_type.get(EventType.CUSTOM, 0)}\n\n"
        f"📣 Организовал активностей — {stats.created_count}\n\n"
        "Считаются события, где нажали «Выходим», "
        "а твой ответ был «Иду» или «Через 5 минут»."
    )


def response_label(response: ResponseType | None) -> str:
    return {
        ResponseType.GOING: "✅ Ты идёшь",
        ResponseType.LATER: "⏱ Ты будешь через 5 минут",
        ResponseType.DECLINED: "❌ Ты пас",
        None: "",
    }[response]


DOMAIN_MESSAGES = {
    "PartyNotFoundError": "Party не найдена или уже закрыта.",
    "NotPartyMemberError": "Ты не состоишь в этой Party.",
    "PermissionDeniedError": "Недостаточно прав для этого действия.",
    "EventNotFoundError": "Событие не найдено.",
    "EventExpiredError": "Событие уже завершилось.",
    "EventNotActiveError": "Событие уже не активно.",
    "InvalidEventTitleError": "Название события должно содержать от 1 до 100 символов.",
}
