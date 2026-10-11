import asyncio
import logging
import shutil
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any, Literal

from errors import ApiError, envelope

logger = logging.getLogger("uvicorn.error")
type Payload = dict[str, Any]
type Event = tuple[str, Payload]
type Emit = Callable[[str, Payload], None]


@dataclass
class Job:
    image_path: Path
    filename: str
    dpi: float
    params: Payload
    rois: list[Payload]
    preview: bool = False
    id: str = field(default_factory=lambda: str(uuid4()))
    queued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    status: Literal["pending", "processing", "completed", "failed"] = "pending"
    terminal: Event | None = None
    progress: Payload | None = None
    csv: str = ""
    submitted_at: float = field(default_factory=time.monotonic)


type Runner = Callable[[Job, Emit], Awaitable[tuple[Payload, str]]]


class Jobs:
    def __init__(self, runner: Runner, max_depth: int = 10, ttl: float = 300):
        self.runner = runner
        self.max_depth = max_depth
        self.ttl = ttl
        self.waiting: deque[Job] = deque()
        self.running: Job | None = None
        self.jobs: dict[str, Job] = {}
        self.listeners: dict[str, set[asyncio.Queue[Event]]] = defaultdict(set)
        self.expiry: dict[str, asyncio.TimerHandle] = {}
        self.task: asyncio.Task[None] | None = None
        self.uploading = 0
        self.closed = False

    def check_capacity(self) -> None:
        depth = len(self.waiting) + self.uploading
        if self.closed or depth >= self.max_depth:
            raise ApiError("SERVICE_AT_CAPACITY", {"queueDepth": depth, "maxDepth": self.max_depth})

    @contextmanager
    def reserve_upload(self) -> Iterator[None]:
        self.check_capacity()
        self.uploading += 1
        try:
            yield
        finally:
            self.uploading -= 1

    def enqueue(self, job: Job, *, reserved: bool = False) -> int:
        if self.closed:
            raise ApiError("SERVICE_AT_CAPACITY")
        if not reserved:
            self.check_capacity()
        position = len(self.waiting) + bool(self.running)
        self.jobs[job.id] = job
        self.waiting.append(job)
        self.publish(job, "queued", {"queuePosition": position})
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.pump())
        return int(position)

    def publish(self, job: Job, event: str, data: Payload) -> None:
        if event == "progress":
            job.progress = data
        if event in ("completed", "failed"):
            job.terminal = event, data
        for listener in tuple(self.listeners.get(job.id, ())):
            listener.put_nowait((event, data))

    def subscribe(self, job: Job) -> asyncio.Queue[Event]:
        listener: asyncio.Queue[Event] = asyncio.Queue()
        self.listeners[job.id].add(listener)
        if job.terminal is not None:
            listener.put_nowait(job.terminal)
        elif job.id in self.jobs:
            if job.status == "processing":
                listener.put_nowait(("started", {}))
            else:
                position = self.waiting.index(job) + bool(self.running)
                listener.put_nowait(("queued", {"queuePosition": int(position)}))
            if job.progress is not None:
                listener.put_nowait(("progress", job.progress))
        return listener

    def unsubscribe(self, job_id: str, listener: asyncio.Queue[Event]) -> None:
        subscribers = self.listeners.get(job_id)
        if subscribers is not None:
            subscribers.discard(listener)
            if not subscribers:
                del self.listeners[job_id]

    def expire(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)
        self.expiry.pop(job_id, None)

    async def pump(self) -> None:
        while self.waiting:
            job = self.running = self.waiting.popleft()
            started = time.monotonic()
            job.status = "processing"
            self.publish(job, "started", {})
            try:
                result, job.csv = await self.runner(job, lambda event, data: self.publish(job, event, data))
                job.status = "completed"
                self.publish(job, "completed", result)
            except ApiError as error:
                job.status = "failed"
                self.publish(job, "failed", error.envelope)
            except Exception:
                logger.exception("analysis_failed job_id=%s", job.id)
                job.status = "failed"
                self.publish(job, "failed", envelope("INTERNAL_ERROR"))
            finally:
                await asyncio.to_thread(shutil.rmtree, job.image_path.parent, True)
                self.expiry[job.id] = asyncio.get_running_loop().call_later(self.ttl, self.expire, job.id)
                self.running = None
                logger.info("analysis_finished job_id=%s status=%s queue_wait_ms=%.1f duration_ms=%.1f",
                            job.id, job.status, (started - job.submitted_at) * 1000,
                            (time.monotonic() - started) * 1000)

    async def close(self) -> None:
        self.closed = True
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        for job in self.waiting:
            await asyncio.to_thread(shutil.rmtree, job.image_path.parent, True)
        for timer in self.expiry.values():
            timer.cancel()
        self.waiting.clear()
        self.expiry.clear()
        self.jobs.clear()
        self.listeners.clear()


class UploadAllowance:
    def __init__(self, limit: int):
        self.limit = limit
        self.addresses: dict[str, deque[float]] = {}
        self.next_cleanup = time.monotonic() + 60

    def check(self, address: str) -> None:
        now = time.monotonic()
        if now >= self.next_cleanup:
            self.addresses = {ip: times for ip, times in self.addresses.items() if times and times[-1] > now - 3600}
            self.next_cleanup = now + 60
        times = self.addresses.setdefault(address, deque())
        while times and times[0] <= now - 3600:
            times.popleft()
        if len(times) >= self.limit:
            raise ApiError("RATE_LIMITED")
        times.append(now)
