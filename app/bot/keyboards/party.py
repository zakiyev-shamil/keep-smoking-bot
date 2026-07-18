from __future__ import annotations

from math import ceil
from urllib.parse import urlencode
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.event import EventCreateCallback
from app.bot.callbacks.party import (
    PartyCallback,
    PartyMemberAdminCallback,
    PartyMembersCallback,
)
from app.core.enums import EventType, PartyRole
from app.models.party_member import PartyMember


def party_keyboard(party_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for event_type in (
        EventType.SMOKE,
        EventType.LUNCH,
        EventType.CUSTOM,
    ):
        builder.button(
            text=f"{event_type.emoji} {event_type.default_title}",
            callback_data=EventCreateCallback(party_id=party_id, event_type=event_type.value),
        )
    builder.button(
        text="👥 Участники",
        callback_data=PartyMembersCallback(party_id=party_id, page=0),
    )
    builder.button(
        text="🔔 Уведомления",
        callback_data=PartyCallback(action="settings", party_id=party_id),
    )
    builder.button(
        text="📊 Моя статистика",
        callback_data=PartyCallback(action="stats", party_id=party_id),
    )
    builder.button(
        text="🏢 Сменить Party",
        callback_data=PartyCallback(action="switch", party_id=party_id),
    )
    builder.adjust(2, 1, 2, 1, 1)
    return builder.as_markup()


def stats_keyboard(party_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ В Party",
                    callback_data=PartyCallback(action="open", party_id=party_id).pack(),
                )
            ]
        ]
    )


def party_created_keyboard(party_id: UUID, invite_url: str) -> InlineKeyboardMarkup:
    share_url = "https://t.me/share/url?" + urlencode(
        {"url": invite_url, "text": "Присоединяйся к нашей Party"}
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться приглашением", url=share_url)],
            [
                InlineKeyboardButton(
                    text="🏠 Открыть Party",
                    callback_data=PartyCallback(action="open", party_id=party_id).pack(),
                )
            ],
        ]
    )


def members_keyboard(
    *,
    party_id: UUID,
    page: int,
    total: int,
    page_size: int,
    requester_role: PartyRole,
    members: list[PartyMember],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    pages = max(1, ceil(total / page_size))
    if page > 0:
        builder.button(
            text="⬅️",
            callback_data=PartyMembersCallback(party_id=party_id, page=page - 1),
        )
    if page + 1 < pages:
        builder.button(
            text="➡️",
            callback_data=PartyMembersCallback(party_id=party_id, page=page + 1),
        )
    if requester_role == PartyRole.OWNER:
        for member in members:
            if member.role == PartyRole.OWNER:
                continue
            action = "demote" if member.role == PartyRole.ADMIN else "promote"
            icon = "➖🛡" if action == "demote" else "➕🛡"
            builder.row(
                InlineKeyboardButton(
                    text=f"{icon} {member.user.first_name}",
                    callback_data=PartyMemberAdminCallback(
                        action=action, membership_id=member.id
                    ).pack(),
                )
            )
    footer = []
    if requester_role in {PartyRole.OWNER, PartyRole.ADMIN}:
        footer.append(
            InlineKeyboardButton(
                text="🔗 Пригласить",
                callback_data=PartyCallback(action="invite", party_id=party_id).pack(),
            )
        )
    footer.append(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=PartyCallback(action="open", party_id=party_id).pack(),
        )
    )
    builder.row(*footer)
    return builder.as_markup()
