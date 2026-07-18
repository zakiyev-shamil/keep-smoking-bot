from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from structlog.stdlib import get_logger

from app.services.notification_service import NotificationService

logger = get_logger(__name__)


class NotificationJobType(StrEnum):
    EVENT_CREATED = "event_created"
    EVENT_STARTED = "event_started"
    EVENT_CANCELLED = "event_cancelled"


@dataclass(slots=True)
class NotificationJob:
    type: NotificationJobType
    event_id: UUID


class NotificationJobSink(Protocol):
    async def enqueue(self, job_type: NotificationJobType, event_id: UUID) -> None: ...


class NotificationWorker:
    def __init__(self, service: NotificationService) -> None:
        self.service = service
        self.queue: asyncio.Queue[NotificationJob | None] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="notification-worker")

    async def enqueue(self, job_type: NotificationJobType, event_id: UUID) -> None:
        await self.queue.put(NotificationJob(job_type, event_id))

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

    def __init__(self, service: NotificationService) -> None:
        self.service = service

    async def enqueue(self, job_type: NotificationJobType, event_id: UUID) -> None:
        if job_type == NotificationJobType.EVENT_CREATED:
            await self.service.broadcast_event(event_id)
        elif job_type == NotificationJobType.EVENT_STARTED:
            await self.service.notify_event_started(event_id)
        elif job_type == NotificationJobType.EVENT_CANCELLED:
            await self.service.notify_event_cancelled(event_id)
