"""Shared bandwidth controls for TelegramBackup.

The limiter is intentionally dependency-free and safe to share between worker
threads.  It uses a token bucket rather than post-upload sleeps, so reads from
both Telegram and Google Drive consume the same global budget.
"""

from __future__ import annotations

import threading
import time
from typing import Optional


class BandwidthLimiter:
    """Thread-safe token bucket with live rate updates and pause support.

    ``limit`` is expressed in bytes per second. A value of 0 means unlimited.
    The bucket is replenished from a monotonic clock and callers block only for
    the amount of time needed to obtain permission for the requested bytes.
    """

    def __init__(self, limit: int = 0, burst_seconds: float = 1.0) -> None:
        self._condition = threading.Condition()
        self._limit = max(0, int(limit or 0))
        self._capacity = max(float(self._limit) * burst_seconds, 64 * 1024)
        self._tokens = self._capacity if self._limit else float("inf")
        self._last = time.monotonic()
        self._paused = False
        self._stopped = False

    @property
    def limit(self) -> int:
        with self._condition:
            return self._limit

    @property
    def paused(self) -> bool:
        with self._condition:
            return self._paused

    def set_limit(self, limit: int) -> None:
        with self._condition:
            self._refill_locked()
            self._limit = max(0, int(limit or 0))
            self._capacity = max(float(self._limit), 64 * 1024)
            self._tokens = self._capacity if self._limit else float("inf")
            self._last = time.monotonic()
            self._condition.notify_all()

    def set_paused(self, paused: bool) -> None:
        with self._condition:
            self._paused = bool(paused)
            self._condition.notify_all()

    def stop(self) -> None:
        with self._condition:
            self._stopped = True
            self._condition.notify_all()

    def reset(self) -> None:
        with self._condition:
            self._stopped = False
            self._last = time.monotonic()
            self._tokens = self._capacity if self._limit else float("inf")
            self._condition.notify_all()

    def _refill_locked(self) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - self._last)
        self._last = now
        if self._limit:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._limit)

    def acquire(self, amount: int, cancel_event: Optional[threading.Event] = None) -> bool:
        """Wait for permission to transfer ``amount`` bytes.

        Requests larger than the bucket capacity are consumed in bounded
        portions. This is important for low limits such as 128 KB/s: a 256 KB
        network read must not wait forever for a bucket that can hold only
        128 KB.
        """
        remaining = max(0, int(amount or 0))
        if remaining == 0:
            return True
        with self._condition:
            while remaining > 0:
                if self._stopped or (cancel_event and cancel_event.is_set()):
                    return False
                if self._paused:
                    self._condition.wait(0.25)
                    continue
                if not self._limit:
                    return True
                self._refill_locked()
                portion = min(remaining, max(1, int(self._capacity)))
                if self._tokens >= portion:
                    self._tokens -= portion
                    remaining -= portion
                    continue
                wait_for = max(0.01, min(0.5, (portion - self._tokens) / self._limit))
                self._condition.wait(wait_for)
        return True


class ThrottledReader:
    """File-like wrapper that charges the limiter for every actual read."""

    def __init__(self, handle, limiter: Optional[BandwidthLimiter], cancel_event=None):
        self._handle = handle
        self._limiter = limiter
        self._cancel_event = cancel_event

    def read(self, size=-1):
        if not self._limiter or size == 0:
            return self._handle.read(size)
        if size is None or size < 0:
            parts=[]
            while True:
                data=self._handle.read(256 * 1024)
                if not data: break
                if not self._limiter.acquire(len(data), self._cancel_event): return b""
                parts.append(data)
            return b"".join(parts)
        data = self._handle.read(min(size, 256 * 1024))
        if data and not self._limiter.acquire(len(data), self._cancel_event): return b""
        return data

    def readline(self, size=-1):
        data = self._handle.readline(size)
        if data and self._limiter and not self._limiter.acquire(len(data), self._cancel_event):
            return b""
        return data

    def seek(self, *args):
        return self._handle.seek(*args)

    def tell(self):
        return self._handle.tell()

    def seekable(self):
        return self._handle.seekable()

    def readable(self):
        return self._handle.readable()

    def fileno(self):
        return self._handle.fileno()

    def close(self):
        return self._handle.close()

    @property
    def name(self):
        return getattr(self._handle, "name", "")

    @name.setter
    def name(self, value):
        # Compatibility with libraries that annotate the upload stream.
        try: self._handle.name = value
        except (AttributeError, TypeError): pass

    @property
    def closed(self):
        return self._handle.closed

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


__all__ = ["BandwidthLimiter", "ThrottledReader"]


if __name__ == "__main__":
    limiter = BandwidthLimiter(128 * 1024)
    started = time.monotonic()
    limiter.acquire(256 * 1024)
    print(f"acquired in {time.monotonic() - started:.2f}s")
