from __future__ import annotations

import math
from time import monotonic
from uuid import UUID

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from structlog.stdlib import get_logger

from app.bot.callbacks.event import (
    CustomEventCallback,
    EventActionCallback,
    EventConfirmCallback,
    EventCreateCallback,
    LunchPollCallback,
    PollVoteCallback,
    expand_uuid,
)
from app.bot.keyboards.common import cancel_fsm_keyboard, menu_keyboard
from app.bot.keyboards.event import (
    cancel_event_keyboard,
    custom_confirmation_keyboard,
    duplicate_event_keyboard,
    event_confirmation_keyboard,
    event_details_keyboard,
    lunch_poll_confirmation_keyboard,
    lunch_setup_keyboard,
)
from app.bot.states.event import CustomEventState, LunchPollState
from app.bot.texts.ru import (
    custom_event_confirmation,
    duplicate_event_text,
    event_confirmation,
    event_details_text,
    lunch_poll_preview,
)
from app.bot.utils import edit_or_answer
from app.core.enums import EventStatus, EventType, PartyRole, ResponseType
from app.core.exceptions import (
    CooldownActiveError,
    EventAlreadyExistsError,
    InvalidEventTitleError,
    InvalidPollOptionError,
    InvalidPollOptionsError,
)
from app.models.user import User
from app.services.container import RequestServices, ServiceContainer
from app.services.dto import EventDetails
from app.workers.notifications import NotificationJobSink, NotificationJobType

router = Router(name="event")
logger = get_logger(__name__)


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
        poll=details.poll,
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


async def finish_response_update(
    *,
    message: Message,
    details: EventDetails,
    current_user: User,
    container: ServiceContainer,
    notification_worker: NotificationJobSink,
    db_started_at: float,
    refresh_needed: bool,
) -> None:
    db_ms = (monotonic() - db_started_at) * 1000
    actor_started_at = monotonic()
    await show_event(message, details, current_user, container)
    actor_edit_ms = (monotonic() - actor_started_at) * 1000

    status_notification_ms = 0.0
    meaningful_response_change = details.response_changed and not (
        details.previous_response is None and details.current_response == ResponseType.DECLINED
    )
    if meaningful_response_change and details.current_response is not None:
        status_started_at = monotonic()
        await notification_worker.enqueue(
            NotificationJobType.RESPONSE_CHANGED,
            details.event.id,
            actor_id=current_user.id,
            previous_response=details.previous_response,
            current_response=details.current_response,
        )
        status_notification_ms = (monotonic() - status_started_at) * 1000

    invitation_refresh_ms = 0.0
    if refresh_needed:
        refresh_started_at = monotonic()
        await notification_worker.enqueue(
            NotificationJobType.EVENT_REFRESH,
            details.event.id,
            actor_id=current_user.id,
        )
        invitation_refresh_ms = (monotonic() - refresh_started_at) * 1000

    logger.info(
        "event_response_pipeline_timing",
        event_id=str(details.event.id),
        actor_id=str(current_user.id),
        db_ms=round(db_ms, 2),
        actor_edit_ms=round(actor_edit_ms, 2),
        status_notification_ms=round(status_notification_ms, 2),
        invitation_refresh_ms=round(invitation_refresh_ms, 2),
        response_changed=details.response_changed,
        poll_changed=details.poll_changed,
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
    if event_type == EventType.LUNCH:
        await state.clear()
        if callback.message:
            await edit_or_answer(
                callback.message,
                "🍔 Как позвать коллег на обед?",
                lunch_setup_keyboard(party.id),
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


@router.callback_query(LunchPollCallback.filter())
async def lunch_poll_action(
    callback: CallbackQuery,
    callback_data: LunchPollCallback,
    state: FSMContext,
    current_user: User,
    services: RequestServices,
    container: ServiceContainer,
    notification_worker: NotificationJobSink,
) -> None:
    if callback_data.action in {"add", "edit"}:
        await services.parties.get_party_for_member(callback_data.party_id, current_user.id)
        await state.set_state(LunchPollState.waiting_for_options)
        await state.update_data(party_id=str(callback_data.party_id))
        if callback.message:
            await edit_or_answer(
                callback.message,
                "Введи 2–6 вариантов одной строкой через два пробела "
                "или каждый с новой строки.\n\nПлов  Пицца  Бургеры",
                cancel_fsm_keyboard(),
            )
        return
    if callback_data.action != "send":
        return
    data = await state.get_data()
    party_id = data.get("party_id")
    options = data.get("poll_options")
    if party_id != str(callback_data.party_id) or not isinstance(options, list):
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
            EventType.LUNCH,
            poll_options=options,
        )
    except EventAlreadyExistsError as exc:
        await state.clear()
        await notification_worker.enqueue(NotificationJobType.EVENT_CREATED, exc.event_id)
        if callback.message:
            await show_duplicate(callback.message, exc.event_id, current_user, services)
        return
    except CooldownActiveError as exc:
        minutes = max(1, math.ceil(exc.retry_after_seconds / 60))
        if callback.message:
            await callback.message.answer(
                f"Следующий обед можно создать через {minutes} мин.",
                reply_markup=menu_keyboard(),
            )
        return
    await state.clear()
    await notification_worker.enqueue(NotificationJobType.EVENT_CREATED, event.id)
    details = await services.events.get_event_details(event.id, current_user.id)
    if callback.message:
        await show_event(callback.message, details, current_user, container)


@router.message(LunchPollState.waiting_for_options)
async def lunch_poll_options(
    message: Message,
    state: FSMContext,
    current_user: User,
    services: RequestServices,
    container: ServiceContainer,
) -> None:
    try:
        options = services.events.parse_poll_options(message.text or "")
    except InvalidPollOptionsError as exc:
        await message.answer(
            str(exc),
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
    party, _ = await services.parties.get_party_for_member(UUID(party_id), current_user.id)
    recipients = await container.notifications.count_eligible_recipients(
        party_id=party.id,
        creator_id=current_user.id,
        event_type=EventType.LUNCH,
    )
    await state.set_state(LunchPollState.confirming)
    await state.update_data(poll_options=options)
    await message.answer(
        lunch_poll_preview(options, party.name, recipients),
        reply_markup=lunch_poll_confirmation_keyboard(party.id),
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
        db_started_at = monotonic()
        details = await services.events.respond(
            callback_data.event_id,
            current_user.id,
            ResponseType(action),
        )
        await finish_response_update(
            message=callback.message,
            details=details,
            current_user=current_user,
            container=container,
            notification_worker=notification_worker,
            db_started_at=db_started_at,
            refresh_needed=details.response_changed,
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


@router.callback_query(PollVoteCallback.filter())
async def poll_vote(
    callback: CallbackQuery,
    callback_data: PollVoteCallback,
    current_user: User,
    services: RequestServices,
    container: ServiceContainer,
    notification_worker: NotificationJobSink,
) -> None:
    if not callback.message:
        return
    try:
        event_id = expand_uuid(callback_data.event_id)
        option_id = (
            None if callback_data.option_id == "none" else expand_uuid(callback_data.option_id)
        )
    except (ValueError, TypeError) as exc:
        raise InvalidPollOptionError from exc
    db_started_at = monotonic()
    details = await services.events.vote_poll(event_id, current_user.id, option_id)
    await finish_response_update(
        message=callback.message,
        details=details,
        current_user=current_user,
        container=container,
        notification_worker=notification_worker,
        db_started_at=db_started_at,
        refresh_needed=details.response_changed or details.poll_changed,
    )
