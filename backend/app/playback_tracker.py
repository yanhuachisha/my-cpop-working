from __future__ import annotations

import os
import time
from threading import Event, Lock, Thread
from typing import Callable

from app.kugou import get_now_playing
from app.library_import import ensure_library_recording
from app.listener_memory import (
    FeedbackRequest,
    listener_summary,
    record_daily_listening,
    record_feedback,
)


class KugouPlaybackTracker:
    def __init__(
        self,
        threshold_seconds: float | None = None,
        poll_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold_seconds = threshold_seconds or float(
            os.getenv("KUGOU_PLAY_THRESHOLD_SECONDS", "30")
        )
        self.poll_seconds = poll_seconds or float(os.getenv("KUGOU_POLL_SECONDS", "5"))
        self.clock = clock
        self._lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._track_key: str | None = None
        self._track_title: str | None = None
        self._track_artist: str | None = None
        self._recording_id: str | None = None
        self._track_started_at: float | None = None
        self._last_observed_at: float | None = None
        self._counted = False
        self._current: dict[str, object] = {}
        self._last_recorded: dict[str, object] | None = None

    @staticmethod
    def _key(title: str, artist: str | None) -> str:
        return f"{title.strip().casefold()}::{(artist or '').strip().casefold()}"

    def observe(self, snapshot: dict[str, object], now: float | None = None) -> bool:
        observed_at = self.clock() if now is None else now
        title = str(snapshot.get("title") or "").strip()
        artist = str(snapshot.get("artist") or "").strip() or None
        is_playing = bool(snapshot.get("is_playing") and title)

        with self._lock:
            self._current = dict(snapshot)
            if not is_playing:
                self._record_listening_delta(observed_at)
                self._record_departure("pause", observed_at)
                self._track_key = None
                self._track_title = None
                self._track_artist = None
                self._recording_id = None
                self._track_started_at = None
                self._last_observed_at = None
                self._counted = False
                return False

            track_key = self._key(title, artist)
            if track_key != self._track_key:
                self._record_listening_delta(observed_at)
                self._record_departure("skip", observed_at)
                self._track_key = track_key
                self._track_title = title
                self._track_artist = artist
                self._recording_id = ensure_library_recording(title, artist)
                self._track_started_at = observed_at
                self._last_observed_at = observed_at
                self._counted = False
                return False

            self._record_listening_delta(observed_at)

            started_at = self._track_started_at if self._track_started_at is not None else observed_at
            elapsed = observed_at - started_at
            if self._counted or elapsed < self.threshold_seconds:
                return False

            recording_id = self._recording_id or ensure_library_recording(title, artist)
            self._recording_id = recording_id
            summary = record_feedback(FeedbackRequest(
                recording_id=recording_id,
                action="play",
                channel="kugou-auto",
                listened_seconds=elapsed,
            ))
            self._counted = True
            self._last_recorded = {
                "recording_id": recording_id,
                "title": title,
                "artist": artist,
                "total_play_count": summary["total_play_count"],
                "recorded_at": time.time(),
            }
            return True

    def _record_listening_delta(self, observed_at: float) -> None:
        if (
            not self._recording_id
            or not self._track_title
            or self._last_observed_at is None
        ):
            return
        elapsed = max(0.0, observed_at - self._last_observed_at)
        maximum_increment = max(self.poll_seconds * 3, 15.0)
        increment = min(elapsed, maximum_increment)
        self._last_observed_at = observed_at
        if increment <= 0:
            return
        record_daily_listening(
            recording_id=self._recording_id,
            title=self._track_title,
            artist=self._track_artist,
            listened_seconds=increment,
        )

    def _record_departure(self, action: str, observed_at: float) -> None:
        if not self._track_key or self._track_started_at is None or not self._track_title:
            return
        elapsed = max(0.0, observed_at - self._track_started_at)
        if elapsed < min(5.0, self.threshold_seconds):
            return
        recording_id = self._recording_id or ensure_library_recording(
            self._track_title, self._track_artist
        )
        record_feedback(FeedbackRequest(
            recording_id=recording_id,
            action=action,
            channel="kugou-auto",
            listened_seconds=elapsed,
        ))

    def poll_once(self) -> bool:
        return self.observe(get_now_playing())

    def _run(self) -> None:
        while not self._stop_event.wait(self.poll_seconds):
            try:
                self.poll_once()
            except (OSError, RuntimeError, ValueError):
                continue

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._run, name="kugou-playback-tracker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.poll_seconds + 0.5))

    def status(self) -> dict[str, object]:
        with self._lock:
            elapsed = 0.0
            if self._track_started_at is not None:
                elapsed = max(0.0, self.clock() - self._track_started_at)
            return {
                "running": bool(self._thread and self._thread.is_alive()),
                "threshold_seconds": self.threshold_seconds,
                "poll_seconds": self.poll_seconds,
                "current": self._current,
                "current_elapsed_seconds": round(elapsed, 1),
                "current_counted": self._counted,
                "last_recorded": self._last_recorded,
                "total_play_count": listener_summary()["total_play_count"],
            }


playback_tracker = KugouPlaybackTracker()
