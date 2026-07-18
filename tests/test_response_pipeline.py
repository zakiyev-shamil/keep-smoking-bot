from time import monotonic
from types import SimpleNamespace
from uuid import uuid4

from app.bot.handlers import event as event_handlers
from app.core.enums import ResponseType
from app.workers.notifications import NotificationJobType


class RecordingWorker:
    def __init__(self, order):
        self.order = order
        self.calls = []

    async def enqueue(self, job_type, event_id, **kwargs):
        self.order.append(job_type)
        self.calls.append((job_type, event_id, kwargs))


async def test_actor_edit_precedes_status_and_fanout_and_actor_is_excluded(monkeypatch):
    order = []

    async def record_actor_edit(*args, **kwargs):
        order.append("actor_edit")

    monkeypatch.setattr(event_handlers, "show_event", record_actor_edit)
    worker = RecordingWorker(order)
    actor_id = uuid4()
    event_id = uuid4()
    details = SimpleNamespace(
        event=SimpleNamespace(id=event_id),
        response_changed=True,
        poll_changed=False,
        previous_response=ResponseType.LATER,
        current_response=ResponseType.GOING,
    )

    await event_handlers.finish_response_update(
        message=SimpleNamespace(),
        details=details,
        current_user=SimpleNamespace(id=actor_id),
        container=SimpleNamespace(),
        notification_worker=worker,
        db_started_at=monotonic(),
        refresh_needed=True,
    )

    assert order == [
        "actor_edit",
        NotificationJobType.RESPONSE_CHANGED,
        NotificationJobType.EVENT_REFRESH,
    ]
    refresh = worker.calls[-1]
    assert refresh[2]["actor_id"] == actor_id


async def test_first_pass_skips_status_but_still_refreshes(monkeypatch):
    order = []

    async def record_actor_edit(*args, **kwargs):
        order.append("actor_edit")

    monkeypatch.setattr(event_handlers, "show_event", record_actor_edit)
    worker = RecordingWorker(order)
    details = SimpleNamespace(
        event=SimpleNamespace(id=uuid4()),
        response_changed=True,
        poll_changed=False,
        previous_response=None,
        current_response=ResponseType.DECLINED,
    )

    await event_handlers.finish_response_update(
        message=SimpleNamespace(),
        details=details,
        current_user=SimpleNamespace(id=uuid4()),
        container=SimpleNamespace(),
        notification_worker=worker,
        db_started_at=monotonic(),
        refresh_needed=True,
    )

    assert order == ["actor_edit", NotificationJobType.EVENT_REFRESH]
