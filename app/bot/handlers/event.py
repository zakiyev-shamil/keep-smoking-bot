from __future__ import annotations

import math

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks.event import (
    CustomEventCallback,
    EventActionCallback,
    EventConfirmCallback,
    EventCreateCallback,
)
from app.bot.keyboards.common import cancel_fsm_keyboard, menu_keyboard
from app.bot.keyboards.event import (
    cancel_event_keyboard,
    custom_confirmation_keyboard,
    duplicate_event_keyboard,
    event_confirmation_keyboard,
    event_details_keyboard,
)
from app.bot.states.event import CustomEventState
from app.bot.texts.ru import (
    custom_event_confirmation,
    duplicate_event_text,
    event_confirmation,
    event_details_text,
)
from app.bot.utils import edit_or_answer
from app.core.enums import EventStatus, EventType, PartyRole, ResponseType
from app.core.exceptions import (
    CooldownActiveError,
    EventAlreadyExistsError,
    InvalidEventTitleError,
)
from app.models.user import User
from app.services.container import RequestServices, ServiceContainer
from app.services.dto import EventDetails
from app.workers.notifications import NotificationJobSink, NotificationJobType

router = Router(name="event")


def details_keyboard(details: EventDetails, current_user: User):
    event = details.event
    is_active = event.status == EventStatus.ACTIVE
    can_start = is_active and event.creator_id == current_user.id
    can_cancel = is_active and (
        event.creator_id == current_user.id
        or details.requester_membership.role in {PartyRole.OWNER, PartyRole.ADMIN}
    )
    return event_details_keyboard(
        event_id=event.id,
        party_id=event.party_id,
        selected=details.requester_response,
        is_active=is_active,
        can_respond=event.creator_id != current_user.id,
        can_start=can_start,
        can_cancel=can_cancel,
    )


async def show_event(
    message: Message,
    details: EventDetails,
    current_user: User,
    container: ServiceContainer,
) -> Message:
    rendered = await edit_or_answer(
        message,
        event_details_text(details),
        details_keyboard(details, current_user),
    )
    if details.event.creator_id == current_user.id:
        await container.event_views.register_creator_message(
            event_id=details.event.id,
            creator_id=current_user.id,
            chat_id=rendered.chat.id,
            message_id=rendered.message_id,
        )
    return rendered


async def show_duplicate(
    message: Message,
    event_id,
    current_user: User,
    services: RequestServices,
) -> None:
    details = await services.events.get_event_details(event_id, current_user.id)
    await edit_or_answer(
        message,
        duplicate_event_text(details.event, details.stats.going_count),
        duplicate_event_keyboard(details.event.id),
    )


@router.callback_query(EventCreateCallback.filter())
async def preview_event(
    callback: CallbackQuery,
    callback_data: EventCreateCallback,
    current_user: User,
    services: RequestServices,
    container: ServiceContainer,
    state: FSMContext,
) -> None:
    event_type = EventType(callback_data.event_type)
    party, _ = await services.parties.get_party_for_member(callback_data.party_id, current_user.id)
    existing = await services.events.find_active_event(party.id, event_type)
    if existing is not None:
        if callback.message:
            await show_duplicate(callback.message, existing.id, current_user, services)
        return
    if event_type == EventType.CUSTOM:
        await state.set_state(CustomEventState.waiting_for_title)
        await state.update_data(party_id=str(party.id))
        if callback.message:
            await edit_or_answer(
                callback.message,
                "Что за событие?\n\nНазвание — от 1 до 100 символов.",
                cancel_fsm_keyboard(),
            )
        return
    recipients = await container.notifications.count_eligible_recipients(
        party_id=party.id,
        creator_id=current_user.id,
        event_type=event_type,
    )
    if callback.message:
        await edit_or_answer(
            callback.message,
            event_confirmation(event_type, party.name, recipients),
            event_confirmation_keyboard(party.id, event_type),
        )


@router.message(CustomEventState.waiting_for_title)
async def custom_event_title(
    message: Message,
    state: FSMContext,
    current_user: User,
    services: RequestServices,
    container: ServiceContainer,
) -> None:
    try:
        title = services.events.normalize_title(message.text or "")
    except InvalidEventTitleError:
        await message.answer(
            "Название должно содержать от 1 до 100 символов.",
            reply_markup=cancel_fsm_keyboard(),
        )
        return
    data = await state.get_data()
    party_id = data.get("party_id")
    if not party_id:
        await state.clear()
        await message.answer(
            "Сценарий устарел. Открой меню и попробуй ещё раз.",
            reply_markup=menu_keyboard(),
        )
        return
    from uuid import UUID

    party, _ = await services.parties.get_party_for_member(UUID(party_id), current_user.id)
    recipients = await container.notifications.count_eligible_recipients(
        party_id=party.id,
        creator_id=current_user.id,
        event_type=EventType.CUSTOM,
    )
    await state.set_state(CustomEventState.confirming)
    await state.update_data(title=title)
    await message.answer(
        custom_event_confirmation(title, party.name, recipients),
        reply_markup=custom_confirmation_keyboard(party.id),
    )


@router.callback_query(CustomEventCallback.filter())
async def custom_event_action(
    callback: CallbackQuery,
    callback_data: CustomEventCallback,
    state: FSMContext,
    current_user: User,
    services: RequestServices,
    container: ServiceContainer,
    notification_worker: NotificationJobSink,
) -> None:
    if callback_data.action == "edit":
        await state.set_state(CustomEventState.waiting_for_title)
        if callback.message:
            await edit_or_answer(
                callback.message,
                "Что за событие?\n\nНазвание — от 1 до 100 символов.",
                cancel_fsm_keyboard(),
            )
        return
    data = await state.get_data()
    title = data.get("title")
    party_id = data.get("party_id")
    if not title or not party_id or str(callback_data.party_id) != party_id:
        await state.clear()
        if callback.message:
            await callback.message.answer(
                "Сценарий устарел. Попробуй ещё раз.",
                reply_markup=menu_keyboard(),
            )
        return
    try:
        event = await services.events.create_event(
            callback_data.party_id,
            current_user.id,
            EventType.CUSTOM,
            title=title,
        )
    except EventAlreadyExistsError as exc:
        await state.clear()
        await notification_worker.enqueue(NotificationJobType.EVENT_CREATED, exc.event_id)
        if callback.message:
            await show_duplicate(callback.message, exc.event_id, current_user, services)
        return
    await state.clear()
    await notification_worker.enqueue(NotificationJobType.EVENT_CREATED, event.id)
    details = await services.events.get_event_details(event.id, current_user.id)
    if callback.message:
        await show_event(callback.message, details, current_user, container)


@router.callback_query(EventConfirmCallback.filter())
async def confirm_event(
    callback: CallbackQuery,
    callback_data: EventConfirmCallback,
    current_user: User,
    services: RequestServices,
    container: ServiceContainer,
    notification_worker: NotificationJobSink,
) -> None:
    event_type = EventType(callback_data.event_type)
    try:
        event = await services.events.create_event(
            callback_data.party_id,
            current_user.id,
            event_type,
        )
    except EventAlreadyExistsError as exc:
        await notification_worker.enqueue(NotificationJobType.EVENT_CREATED, exc.event_id)
        if callback.message:
            await show_duplicate(callback.message, exc.event_id, current_user, services)
        return
    except CooldownActiveError as exc:
        minutes = max(1, math.ceil(exc.retry_after_seconds / 60))
        if callback.message:
            await callback.message.answer(
                f"Следующее такое событие можно создать через {minutes} мин.",
                reply_markup=menu_keyboard(),
            )
        return
    await notification_worker.enqueue(NotificationJobType.EVENT_CREATED, event.id)
    details = await services.events.get_event_details(event.id, current_user.id)
    if callback.message:
        await show_event(callback.message, details, current_user, container)


@router.callback_query(EventActionCallback.filter())
async def event_action(
    callback: CallbackQuery,
    callback_data: EventActionCallback,
    current_user: User,
    services: RequestServices,
    container: ServiceContainer,
    notification_worker: NotificationJobSink,
) -> None:
    if not callback.message:
        return
    action = callback_data.action
    if action in {item.value for item in ResponseType}:
        details = await services.events.respond(
            callback_data.event_id,
            current_user.id,
            ResponseType(action),
        )
        await show_event(callback.message, details, current_user, container)
        if details.response_changed:
            await notification_worker.enqueue(
                NotificationJobType.EVENT_REFRESH,
                details.event.id,
            )
        if details.became_going:
            await notification_worker.enqueue(
                NotificationJobType.PARTICIPANT_JOINED,
                details.event.id,
                current_user.id,
            )
        return
    if action == "view":
        details = await services.events.get_event_details(callback_data.event_id, current_user.id)
        await show_event(callback.message, details, current_user, container)
        return
    if action == "start":
        transition = await services.events.start_event(callback_data.event_id, current_user.id)
        if transition.changed:
            await notification_worker.enqueue(
                NotificationJobType.EVENT_STARTED, transition.event.id
            )
            await notification_worker.enqueue(
                NotificationJobType.EVENT_REFRESH, transition.event.id
            )
        details = await services.events.get_event_details(transition.event.id, current_user.id)
        await show_event(callback.message, details, current_user, container)
        return
    if action == "cancel":
        await edit_or_answer(
            callback.message,
            "Отменить событие?",
            cancel_event_keyboard(callback_data.event_id),
        )
        return
    if action == "cancel_confirm":
        transition = await services.events.cancel_event(callback_data.event_id, current_user.id)
        if transition.changed:
            await notification_worker.enqueue(
                NotificationJobType.EVENT_CANCELLED, transition.event.id
            )
            await notification_worker.enqueue(
                NotificationJobType.EVENT_REFRESH, transition.event.id
            )
        details = await services.events.get_event_details(transition.event.id, current_user.id)
        await show_event(callback.message, details, current_user, container)
