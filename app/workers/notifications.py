from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from structlog.stdlib import get_logger

from app.core.enums import ResponseType
from app.services.event_view_service import EventViewService
from app.services.notification_service import NotificationService

logger = get_logger(__name__)


class NotificationJobType(StrEnum):
    EVENT_CREATED = "event_created"
    EVENT_STARTED = "event_started"
    EVENT_CANCELLED = "event_cancelled"
    EVENT_REFRESH = "event_refresh"
    RESPONSE_CHANGED = "response_changed"


@dataclass(slots=True)
class NotificationJob:
    type: NotificationJobType
    event_id: UUID
    actor_id: UUID | None = None
    previous_response: ResponseType | None = None
    current_response: ResponseType | None = None


class NotificationJobSink(Protocol):
    async def enqueue(
        self,
        job_type: NotificationJobType,
        event_id: UUID,
        actor_id: UUID | None = None,
        previous_response: ResponseType | None = None,
        current_response: ResponseType | None = None,
    ) -> None: ...


class NotificationWorker:
    def __init__(self, service: NotificationService, event_views: EventViewService) -> None:
        self.service = service
        self.event_views = event_views
        self.queue: asyncio.Queue[NotificationJob | None] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="notification-worker")

    async def enqueue(
        self,
        job_type: NotificationJobType,
        event_id: UUID,
        actor_id: UUID | None = None,
        previous_response: ResponseType | None = None,
        current_response: ResponseType | None = None,
    ) -> None:
        await self.queue.put(
            NotificationJob(
                job_type,
                event_id,
                actor_id,
                previous_response,
                current_response,
            )
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        await self.queue.join()
        await self.queue.put(None)
        await self._task
        self._task = None

    async def _run(self) -> None:
        try:
            for event_id in await self.service.pending_event_ids():
                self.queue.put_nowait(NotificationJob(NotificationJobType.EVENT_CREATED, event_id))
        except Exception:
            logger.exception("notification_recovery_failed")
        while True:
            job = await self.queue.get()
            try:
                if job is None:
                    return
                if job.type == NotificationJobType.EVENT_CREATED:
                    await self.service.broadcast_event(job.event_id)
                elif job.type == NotificationJobType.EVENT_STARTED:
                    await self.service.notify_event_started(job.event_id)
                elif job.type == NotificationJobType.EVENT_CANCELLED:
                    await self.service.notify_event_cancelled(job.event_id)
                elif job.type == NotificationJobType.EVENT_REFRESH:
                    await self.event_views.refresh_event_messages(
                        job.event_id,
                        exclude_user_id=job.actor_id,
                    )
                elif (
                    job.type == NotificationJobType.RESPONSE_CHANGED
                    and job.actor_id
                    and job.current_response
                ):
                    await self.service.notify_response_changed(
                        job.event_id,
                        job.actor_id,
                        job.previous_response,
                        job.current_response,
                    )
            except Exception:
                logger.exception(
                    "notification_job_failed",
                    job_type=job.type.value if job else None,
                    event_id=str(job.event_id) if job else None,
                )
            finally:
                self.queue.task_done()


class InlineNotificationWorker:
    """Executes small notification batches inside a serverless webhook request."""

    def __init__(self, service: NotificationService, event_views: EventViewService) -> None:
        self.service = service
        self.event_views = event_views

    async def enqueue(
        self,
        job_type: NotificationJobType,
        event_id: UUID,
        actor_id: UUID | None = None,
        previous_response: ResponseType | None = None,
        current_response: ResponseType | None = None,
    ) -> None:
        if job_type == NotificationJobType.EVENT_CREATED:
            await self.service.broadcast_event(event_id)
        elif job_type == NotificationJobType.EVENT_STARTED:
            await self.service.notify_event_started(event_id)
        elif job_type == NotificationJobType.EVENT_CANCELLED:
            await self.service.notify_event_cancelled(event_id)
        elif job_type == NotificationJobType.EVENT_REFRESH:
            await self.event_views.refresh_event_messages(
                event_id,
                exclude_user_id=actor_id,
            )
        elif job_type == NotificationJobType.RESPONSE_CHANGED and actor_id and current_response:
            await self.service.notify_response_changed(
                event_id,
                actor_id,
                previous_response,
                current_response,
            )
