from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from time import monotonic
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.stdlib import get_logger

from app.bot.keyboards.event import event_response_keyboard, event_summary_keyboard
from app.bot.texts.ru import (
    event_cancelled_notification,
    event_details_text,
    event_started_notification,
    response_changed_notification,
)
from app.core.config import Settings
from app.core.enums import EventStatus, NotificationStatus, ResponseType
from app.core.exceptions import EventNotFoundError
from app.core.time import ensure_utc, utc_now
from app.models.event import Event
from app.models.notification_settings import UserNotificationSettings
from app.models.user import User
from app.repositories.events import EventRepository
from app.repositories.notifications import EVENT_SETTING_COLUMNS, NotificationRepository
from app.repositories.responses import EventResponseRepository
from app.services.dto import EventPoll, NotificationBatchResult
from app.services.event_service import EventService

logger = get_logger(__name__)


class AsyncRateLimiter:
    def __init__(self, rate_per_second: int) -> None:
        self.interval = 1 / rate_per_second
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = monotonic()
            scheduled = max(now, self._next_at)
            self._next_at = scheduled + self.interval
            delay = scheduled - now
        if delay > 0:
            await asyncio.sleep(delay)


class NotificationService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        bot: Bot,
        settings: Settings,
        rate_limiter: AsyncRateLimiter | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.bot = bot
        self.settings = settings
        self.rate_limiter = rate_limiter or AsyncRateLimiter(settings.notification_rate_per_second)

    @staticmethod
    def _is_quiet(notification_settings: UserNotificationSettings | None, now: datetime) -> bool:
        if (
            notification_settings is None
            or not notification_settings.quiet_hours_enabled
            or notification_settings.quiet_from is None
            or notification_settings.quiet_to is None
        ):
            return False
        try:
            timezone = ZoneInfo(notification_settings.timezone)
        except ZoneInfoNotFoundError:
            timezone = ZoneInfo("UTC")
        local_time = now.astimezone(timezone).time().replace(tzinfo=None)
        quiet_from = notification_settings.quiet_from
        quiet_to = notification_settings.quiet_to
        if quiet_from <= quiet_to:
            return quiet_from <= local_time < quiet_to
        return local_time >= quiet_from or local_time < quiet_to

    async def get_eligible_recipients(
        self,
        *,
        party_id: UUID,
        creator_id: UUID,
        event_type,
        phase: str = "preview",
        event_id: UUID | None = None,
    ) -> list[User]:
        async with self.session_factory() as session:
            rows = await NotificationRepository(session).party_candidates(party_id)
            users, reasons = self._filter_recipients(
                rows=rows,
                creator_id=creator_id,
                event_type=event_type,
                now=utc_now(),
            )
        logger.info(
            "notification_eligibility_resolved",
            phase=phase,
            event_id=str(event_id) if event_id else None,
            party_id=str(party_id),
            event_type=event_type.value,
            **reasons,
        )
        return users

    def _filter_recipients(
        self,
        *,
        rows: list[tuple[User, UserNotificationSettings | None]],
        creator_id: UUID,
        event_type,
        now: datetime,
    ) -> tuple[list[User], dict[str, int]]:
        reasons = {
            "candidates": len(rows),
            "creator_excluded": 0,
            "inactive_excluded": 0,
            "bot_unavailable_excluded": 0,
            "all_disabled_excluded": 0,
            "event_type_disabled_excluded": 0,
            "quiet_hours_excluded": 0,
            "eligible": 0,
        }
        users: list[User] = []
        event_setting = EVENT_SETTING_COLUMNS[event_type].key
        for user, notification_settings in rows:
            if user.id == creator_id:
                reasons["creator_excluded"] += 1
            elif not user.is_active:
                reasons["inactive_excluded"] += 1
            elif not user.bot_accessible:
                reasons["bot_unavailable_excluded"] += 1
            elif (
                notification_settings is not None
                and not notification_settings.notifications_enabled
            ):
                reasons["all_disabled_excluded"] += 1
            elif notification_settings is not None and not getattr(
                notification_settings, event_setting
            ):
                reasons["event_type_disabled_excluded"] += 1
            elif self._is_quiet(notification_settings, now):
                reasons["quiet_hours_excluded"] += 1
            else:
                users.append(user)
                reasons["eligible"] += 1
        return users, reasons

    async def count_eligible_recipients(
        self, *, party_id: UUID, creator_id: UUID, event_type
    ) -> int:
        return len(
            await self.get_eligible_recipients(
                party_id=party_id,
                creator_id=creator_id,
                event_type=event_type,
            )
        )

    async def pending_event_ids(self) -> list[UUID]:
        async with self.session_factory() as session:
            return await NotificationRepository(session).pending_event_ids()

    async def broadcast_event(self, event_id: UUID) -> NotificationBatchResult:
        async with self.session_factory() as session:
            events = EventRepository(session)
            event = await events.get(event_id, with_relations=True)
            if event is None:
                raise EventNotFoundError
            if event.status != EventStatus.ACTIVE or ensure_utc(event.expires_at) <= utc_now():
                logger.info(
                    "notification_batch_skipped",
                    event_id=str(event_id),
                    event_status=event.status.value,
                    reason="event_not_active",
                )
                return NotificationBatchResult(total=0, sent=0, failed=0, blocked=0)
            repository = NotificationRepository(session)
            rows = await repository.party_candidates(event.party_id)
            users, reasons = self._filter_recipients(
                rows=rows,
                creator_id=event.creator_id,
                event_type=event.type,
                now=utc_now(),
            )
            logger.info(
                "notification_eligibility_resolved",
                phase="broadcast",
                event_id=str(event.id),
                party_id=str(event.party_id),
                event_type=event.type.value,
                **reasons,
            )
            await repository.seed(event.id, [user.id for user in users])
            await session.commit()
            claimed_ids = set(
                await repository.claim_recipients(
                    event.id,
                    [user.id for user in users],
                )
            )
            await session.commit()
            users = [user for user in users if user.id in claimed_ids]
            details = await EventService(session, self.settings).get_event_details(
                event.id,
                event.creator_id,
            )
            invitation = event_details_text(details)

        counters = {"sent": 0, "failed": 0, "blocked": 0}

        async def send(user: User) -> None:
            status, message_id, error_code = await self._send_invitation(
                user,
                event,
                invitation,
                details.poll,
            )
            counters[status.value] += 1
            await self._mark_delivery(
                event_id=event.id,
                user=user,
                status=status,
                message_id=message_id,
                error_code=error_code,
            )
            logger.info(
                "notification_delivery_completed",
                event_id=str(event.id),
                recipient_id=str(user.id),
                status=status.value,
                error_code=error_code,
            )

        await self._run_controlled(users, send)
        result = NotificationBatchResult(
            total=len(users),
            sent=counters["sent"],
            failed=counters["failed"],
            blocked=counters["blocked"],
        )
        logger.info(
            "notification_batch_completed",
            event_id=str(event_id),
            total=result.total,
            sent=result.sent,
            failed=result.failed,
            blocked=result.blocked,
        )
        return result

    async def _send_invitation(
        self,
        user: User,
        event: Event,
        text: str,
        poll: EventPoll | None,
    ) -> tuple[NotificationStatus, int | None, str | None]:
        try:
            await self.rate_limiter.acquire()
            message = await self.bot.send_message(
                user.telegram_user_id,
                text,
                reply_markup=event_response_keyboard(event.id, poll=poll),
            )
            return NotificationStatus.SENT, message.message_id, None
        except TelegramRetryAfter as exc:
            await asyncio.sleep(max(0, exc.retry_after))
            try:
                await self.rate_limiter.acquire()
                message = await self.bot.send_message(
                    user.telegram_user_id,
                    text,
                    reply_markup=event_response_keyboard(event.id, poll=poll),
                )
                return NotificationStatus.SENT, message.message_id, None
            except TelegramForbiddenError:
                return NotificationStatus.BLOCKED, None, "forbidden"
            except TelegramAPIError as retry_exc:
                return (
                    NotificationStatus.FAILED,
                    None,
                    type(retry_exc).__name__.lower(),
                )
        except TelegramForbiddenError:
            return NotificationStatus.BLOCKED, None, "forbidden"
        except TelegramBadRequest:
            return NotificationStatus.FAILED, None, "bad_request"
        except TelegramAPIError as exc:
            return NotificationStatus.FAILED, None, type(exc).__name__.lower()

    async def _mark_delivery(
        self,
        *,
        event_id: UUID,
        user: User,
        status: NotificationStatus,
        message_id: int | None,
        error_code: str | None,
    ) -> None:
        async with self.session_factory() as session:
            await NotificationRepository(session).mark(
                event_id=event_id,
                recipient_id=user.id,
                status=status,
                telegram_message_id=message_id,
                error_code=error_code,
                sent_at=utc_now() if status == NotificationStatus.SENT else None,
            )
            if status == NotificationStatus.BLOCKED:
                persisted_user = await session.get(User, user.id)
                if persisted_user is not None:
                    persisted_user.bot_accessible = False
            await session.commit()

    async def notify_event_started(self, event_id: UUID) -> NotificationBatchResult:
        if not self.settings.notify_on_event_started:
            return NotificationBatchResult(total=0, sent=0, failed=0, blocked=0)
        return await self._notify_interested(
            event_id,
            event_started_notification,
            settings_field="event_started_enabled",
        )

    async def notify_event_cancelled(self, event_id: UUID) -> NotificationBatchResult:
        if not self.settings.notify_on_event_cancelled:
            return NotificationBatchResult(total=0, sent=0, failed=0, blocked=0)
        return await self._notify_interested(
            event_id,
            event_cancelled_notification,
            settings_field="event_cancelled_enabled",
        )

    async def notify_response_changed(
        self,
        event_id: UUID,
        actor_id: UUID,
        previous_response: ResponseType | None,
        current_response: ResponseType,
    ) -> NotificationBatchResult:
        if previous_response == current_response or (
            previous_response is None and current_response == ResponseType.DECLINED
        ):
            return NotificationBatchResult(total=0, sent=0, failed=0, blocked=0)
        async with self.session_factory() as session:
            event = await EventRepository(session).get(event_id, with_relations=True)
            actor = await session.get(User, actor_id)
            if (
                event is None
                or actor is None
                or event.status != EventStatus.ACTIVE
                or ensure_utc(event.expires_at) <= utc_now()
            ):
                return NotificationBatchResult(total=0, sent=0, failed=0, blocked=0)
            responses = EventResponseRepository(session)
            recipient_ids = set(await responses.interested_user_ids(event_id))
            recipient_ids.add(event.creator_id)
            actor_was_candidate = actor_id in recipient_ids
            recipient_ids.discard(actor_id)
            rows = await NotificationRepository(session).users_by_ids(list(recipient_ids))
            now = utc_now()
            event_setting = EVENT_SETTING_COLUMNS[event.type].key
            users: list[User] = []
            reasons = {
                "candidates": len(rows),
                "actor_excluded": int(actor_was_candidate),
                "global_disabled_excluded": 0,
                "event_type_disabled_excluded": 0,
                "quiet_hours_excluded": 0,
                "eligible": 0,
            }
            for user, notification_settings in rows:
                if (
                    notification_settings is not None
                    and not notification_settings.notifications_enabled
                ):
                    reasons["global_disabled_excluded"] += 1
                elif (
                    user.id != event.creator_id
                    and notification_settings is not None
                    and not getattr(notification_settings, event_setting)
                ):
                    reasons["event_type_disabled_excluded"] += 1
                elif self._is_quiet(notification_settings, now):
                    reasons["quiet_hours_excluded"] += 1
                else:
                    users.append(user)
                    reasons["eligible"] += 1
            text = response_changed_notification(actor, current_response)
            keyboard = event_summary_keyboard(event.id, event.party_id)
            logger.info(
                "response_changed_notification_resolved",
                event_id=str(event.id),
                actor_id=str(actor_id),
                previous_response=previous_response.value if previous_response else None,
                current_response=current_response.value,
                **reasons,
            )

        return await self._send_followup_batch(
            event_id=event_id,
            users=users,
            text=text,
            reply_markup=keyboard,
            disable_notification=True,
            notification_kind="response_changed",
        )

    async def _notify_interested(
        self,
        event_id: UUID,
        text_factory: Callable[[Event], str],
        *,
        settings_field: str,
    ) -> NotificationBatchResult:
        async with self.session_factory() as session:
            event = await EventRepository(session).get(event_id, with_relations=True)
            if event is None:
                raise EventNotFoundError
            ids = await EventResponseRepository(session).interested_user_ids(event_id)
            rows = await NotificationRepository(session).users_by_ids(ids)
            now = utc_now()
            users = [
                user
                for user, notification_settings in rows
                if user.id != event.creator_id
                and (
                    notification_settings is None
                    or (
                        notification_settings.notifications_enabled
                        and getattr(notification_settings, settings_field)
                    )
                )
                and not self._is_quiet(notification_settings, now)
            ]
            text = text_factory(event)
            keyboard = event_summary_keyboard(event.id, event.party_id)

        return await self._send_followup_batch(
            event_id=event_id,
            users=users,
            text=text,
            reply_markup=keyboard,
            disable_notification=False,
            notification_kind=settings_field,
        )

    async def _send_followup_batch(
        self,
        *,
        event_id: UUID,
        users: list[User],
        text: str,
        reply_markup,
        disable_notification: bool,
        notification_kind: str,
    ) -> NotificationBatchResult:
        counters = {"sent": 0, "failed": 0, "blocked": 0}

        async def send(user: User) -> None:
            try:
                await self.rate_limiter.acquire()
                await self.bot.send_message(
                    user.telegram_user_id,
                    text,
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                )
                counters["sent"] += 1
            except TelegramForbiddenError:
                counters["blocked"] += 1
                async with self.session_factory() as session:
                    persisted = await session.get(User, user.id)
                    if persisted is not None:
                        persisted.bot_accessible = False
                    await session.commit()
            except TelegramRetryAfter as exc:
                await asyncio.sleep(max(0, exc.retry_after))
                try:
                    await self.rate_limiter.acquire()
                    await self.bot.send_message(
                        user.telegram_user_id,
                        text,
                        reply_markup=reply_markup,
                        disable_notification=disable_notification,
                    )
                    counters["sent"] += 1
                except TelegramAPIError:
                    counters["failed"] += 1
            except TelegramAPIError:
                counters["failed"] += 1

        await self._run_controlled(users, send)
        result = NotificationBatchResult(
            total=len(users),
            sent=counters["sent"],
            failed=counters["failed"],
            blocked=counters["blocked"],
        )
        logger.info(
            "notification_followup_batch_completed",
            event_id=str(event_id),
            notification_kind=notification_kind,
            silent=disable_notification,
            total=result.total,
            sent=result.sent,
            failed=result.failed,
            blocked=result.blocked,
        )
        return result

    async def _run_controlled(
        self, users: list[User], callback: Callable[[User], Awaitable[None]]
    ) -> None:
        queue: asyncio.Queue[User | None] = asyncio.Queue()
        for user in users:
            queue.put_nowait(user)

        async def worker() -> None:
            while True:
                user = await queue.get()
                try:
                    if user is None:
                        return
                    await callback(user)
                except Exception:
                    logger.exception("notification_recipient_unexpected_error")
                finally:
                    queue.task_done()

        worker_count = min(self.settings.notification_concurrency, max(1, len(users)))
        tasks = [asyncio.create_task(worker()) for _ in range(worker_count)]
        await queue.join()
        for _ in tasks:
            queue.put_nowait(None)
        await asyncio.gather(*tasks)
