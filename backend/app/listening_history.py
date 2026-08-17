from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Literal


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "listening_history.db"
LEGACY_STATE_PATH = DATA_DIR / "listener_state.json"
_schema_lock = Lock()
_initialized_paths: set[Path] = set()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


def initialize_listening_history() -> None:
    database_path = DB_PATH.resolve()
    if database_path in _initialized_paths:
        return
    with _schema_lock:
        if database_path in _initialized_paths:
            return
        with _connect() as connection:
            connection.executescript(
                """
            CREATE TABLE IF NOT EXISTS listening_history_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_track_listening (
                listened_date TEXT NOT NULL,
                recording_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                seconds REAL NOT NULL DEFAULT 0 CHECK (seconds >= 0),
                last_listened_at TEXT NOT NULL,
                PRIMARY KEY (listened_date, recording_id)
            );

            CREATE INDEX IF NOT EXISTS idx_daily_track_date
            ON daily_track_listening (listened_date);

            CREATE INDEX IF NOT EXISTS idx_daily_track_artist
            ON daily_track_listening (artist, listened_date);

            CREATE TABLE IF NOT EXISTS daily_listening_summary (
                listened_date TEXT PRIMARY KEY,
                total_seconds REAL NOT NULL DEFAULT 0 CHECK (total_seconds >= 0),
                track_count INTEGER NOT NULL DEFAULT 0 CHECK (track_count >= 0),
                updated_at TEXT NOT NULL
            );
                """
            )
        migrate_legacy_daily_listening()
        _initialized_paths.add(database_path)


def _refresh_daily_summary(
    connection: sqlite3.Connection,
    listened_date: str,
    updated_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO daily_listening_summary (
            listened_date, total_seconds, track_count, updated_at
        )
        SELECT ?, COALESCE(SUM(seconds), 0), COUNT(*), ?
        FROM daily_track_listening
        WHERE listened_date = ?
        ON CONFLICT(listened_date) DO UPDATE SET
            total_seconds = excluded.total_seconds,
            track_count = excluded.track_count,
            updated_at = excluded.updated_at
        """,
        (listened_date, updated_at, listened_date),
    )


def migrate_legacy_daily_listening() -> dict[str, int | bool]:
    with _connect() as connection:
        marker = connection.execute(
            "SELECT value FROM listening_history_metadata WHERE key = ?",
            ("legacy_daily_listening_v1",),
        ).fetchone()
        if marker:
            return {"migrated": False, "days": 0, "tracks": 0}

        legacy_daily = {}
        if LEGACY_STATE_PATH.exists():
            try:
                legacy_state = json.loads(LEGACY_STATE_PATH.read_text(encoding="utf-8"))
                legacy_daily = legacy_state.get("daily_listening", {})
            except (OSError, json.JSONDecodeError):
                legacy_daily = {}

        migrated_days = 0
        migrated_tracks = 0
        migrated_at = datetime.now().astimezone().isoformat()
        for listened_date, day in legacy_daily.items():
            tracks = day.get("tracks", {}) if isinstance(day, dict) else {}
            for recording_id, track in tracks.items():
                if not isinstance(track, dict):
                    continue
                seconds = max(0.0, float(track.get("seconds", 0.0)))
                if not seconds:
                    continue
                connection.execute(
                    """
                    INSERT INTO daily_track_listening (
                        listened_date, recording_id, title, artist, seconds, last_listened_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(listened_date, recording_id) DO UPDATE SET
                        title = excluded.title,
                        artist = excluded.artist,
                        seconds = excluded.seconds,
                        last_listened_at = excluded.last_listened_at
                    """,
                    (
                        listened_date,
                        recording_id,
                        track.get("title") or "未知歌曲",
                        track.get("artist") or "未知歌手",
                        seconds,
                        track.get("last_listened_at") or migrated_at,
                    ),
                )
                migrated_tracks += 1
            _refresh_daily_summary(connection, listened_date, migrated_at)
            migrated_days += 1

        connection.execute(
            """
            INSERT INTO listening_history_metadata (key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            ("legacy_daily_listening_v1", str(migrated_tracks), migrated_at),
        )
        return {"migrated": True, "days": migrated_days, "tracks": migrated_tracks}


def _format_duration(seconds: float) -> str:
    rounded_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(rounded_seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} 小时 {minutes} 分钟" if minutes else f"{hours} 小时"
    if minutes:
        return f"{minutes} 分钟"
    return f"{remaining_seconds} 秒"


def _listening_local_time(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now().astimezone()
    if value.tzinfo is None:
        return value.astimezone()
    return value


def record_daily_listening(
    recording_id: str,
    title: str,
    artist: str | None,
    listened_seconds: float,
    listened_at: datetime | None = None,
) -> None:
    increment = max(0.0, float(listened_seconds))
    if not increment:
        return
    initialize_listening_history()
    local_time = _listening_local_time(listened_at)
    listened_date = local_time.date().isoformat()
    timestamp = local_time.isoformat()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO daily_track_listening (
                listened_date, recording_id, title, artist, seconds, last_listened_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(listened_date, recording_id) DO UPDATE SET
                title = excluded.title,
                artist = excluded.artist,
                seconds = daily_track_listening.seconds + excluded.seconds,
                last_listened_at = excluded.last_listened_at
            """,
            (
                listened_date,
                recording_id,
                title.strip() or "未知歌曲",
                (artist or "未知歌手").strip() or "未知歌手",
                increment,
                timestamp,
            ),
        )
        _refresh_daily_summary(connection, listened_date, timestamp)


def today_listening_stats(now: datetime | None = None) -> dict:
    local_time = _listening_local_time(now)
    listened_date = local_time.date().isoformat()
    result = query_listening_history(
        start_date=listened_date,
        end_date=listened_date,
        group_by="track",
        top_n=500,
    )
    ranking = [
        {
            "recording_id": item["recording_id"],
            "title": item["title"],
            "artist": item["artist"],
            "seconds": item["seconds"],
            "formatted_duration": item["formatted_duration"],
            "last_listened_at": item["last_listened_at"],
        }
        for item in result["items"]
    ]
    return {
        "date": listened_date,
        "total_seconds": result["total_seconds"],
        "formatted_duration": result["formatted_duration"],
        "track_count": result["track_count"],
        "ranking": ranking,
    }


def _parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    return date.fromisoformat(value)


def resolve_history_period(
    period: Literal[
        "today",
        "yesterday",
        "this_week",
        "last_week",
        "this_month",
        "last_month",
        "this_year",
        "last_year",
        "7d",
        "30d",
        "90d",
        "365d",
        "all",
        "custom",
    ],
    start_date: str | None = None,
    end_date: str | None = None,
    today: date | None = None,
) -> tuple[str, str]:
    current_date = today or datetime.now().astimezone().date()
    if period == "today":
        start = end = current_date
    elif period == "yesterday":
        start = end = current_date - timedelta(days=1)
    elif period == "this_week":
        start = current_date - timedelta(days=current_date.weekday())
        end = current_date
    elif period == "last_week":
        end = current_date - timedelta(days=current_date.weekday() + 1)
        start = end - timedelta(days=6)
    elif period == "this_month":
        start = current_date.replace(day=1)
        end = current_date
    elif period == "last_month":
        end = current_date.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    elif period == "this_year":
        start = current_date.replace(month=1, day=1)
        end = current_date
    elif period == "last_year":
        start = current_date.replace(year=current_date.year - 1, month=1, day=1)
        end = current_date.replace(year=current_date.year - 1, month=12, day=31)
    elif period in {"7d", "30d", "90d", "365d"}:
        days = int(period[:-1])
        end = current_date
        start = end - timedelta(days=days - 1)
    elif period == "all":
        initialize_listening_history()
        with _connect() as connection:
            first = connection.execute(
                "SELECT MIN(listened_date) AS first_date FROM daily_listening_summary"
            ).fetchone()
        start = date.fromisoformat(first["first_date"]) if first and first["first_date"] else current_date
        end = current_date
    else:
        end = _parse_date(end_date, current_date)
        start = _parse_date(start_date, end)
    if start > end:
        raise ValueError("start_date 不能晚于 end_date")
    return start.isoformat(), end.isoformat()


def query_listening_history(
    start_date: str | None = None,
    end_date: str | None = None,
    group_by: Literal["day", "track", "artist"] = "day",
    view: Literal["list", "overview"] = "list",
    top_n: int = 10,
) -> dict:
    initialize_listening_history()
    end = _parse_date(end_date, datetime.now().astimezone().date())
    start = _parse_date(start_date, end - timedelta(days=6))
    if start > end:
        raise ValueError("start_date 不能晚于 end_date")
    start_value, end_value = start.isoformat(), end.isoformat()
    limit = max(1, min(int(top_n), 500))
    with _connect() as connection:
        totals = connection.execute(
            """
            SELECT COALESCE(SUM(total_seconds), 0) AS total_seconds,
                   COALESCE(SUM(track_count), 0) AS track_entries,
                   COUNT(*) AS active_days
            FROM daily_listening_summary
            WHERE listened_date BETWEEN ? AND ?
            """,
            (start_value, end_value),
        ).fetchone()
        unique_tracks = connection.execute(
            """
            SELECT COUNT(DISTINCT recording_id) AS track_count
            FROM daily_track_listening
            WHERE listened_date BETWEEN ? AND ?
            """,
            (start_value, end_value),
        ).fetchone()["track_count"]
        if group_by == "day":
            rows = connection.execute(
                """
                SELECT listened_date, total_seconds, track_count, updated_at
                FROM daily_listening_summary
                WHERE listened_date BETWEEN ? AND ?
                ORDER BY listened_date DESC
                LIMIT ?
                """,
                (start_value, end_value, limit),
            ).fetchall()
            items = [
                {
                    "date": row["listened_date"],
                    "seconds": round(float(row["total_seconds"]), 1),
                    "formatted_duration": _format_duration(row["total_seconds"]),
                    "track_count": int(row["track_count"]),
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]
        elif group_by == "track":
            rows = connection.execute(
                """
                SELECT recording_id, MAX(title) AS title, MAX(artist) AS artist,
                       SUM(seconds) AS seconds, MAX(last_listened_at) AS last_listened_at,
                       COUNT(DISTINCT listened_date) AS active_days
                FROM daily_track_listening
                WHERE listened_date BETWEEN ? AND ?
                GROUP BY recording_id
                ORDER BY seconds DESC, title ASC
                LIMIT ?
                """,
                (start_value, end_value, limit),
            ).fetchall()
            items = [
                {
                    "recording_id": row["recording_id"],
                    "title": row["title"],
                    "artist": row["artist"],
                    "seconds": round(float(row["seconds"]), 1),
                    "formatted_duration": _format_duration(row["seconds"]),
                    "active_days": int(row["active_days"]),
                    "last_listened_at": row["last_listened_at"],
                }
                for row in rows
            ]
        else:
            rows = connection.execute(
                """
                SELECT artist, SUM(seconds) AS seconds,
                       COUNT(DISTINCT recording_id) AS track_count,
                       COUNT(DISTINCT listened_date) AS active_days,
                       MAX(last_listened_at) AS last_listened_at
                FROM daily_track_listening
                WHERE listened_date BETWEEN ? AND ?
                GROUP BY artist
                ORDER BY seconds DESC, artist ASC
                LIMIT ?
                """,
                (start_value, end_value, limit),
            ).fetchall()
            items = [
                {
                    "artist": row["artist"],
                    "seconds": round(float(row["seconds"]), 1),
                    "formatted_duration": _format_duration(row["seconds"]),
                    "track_count": int(row["track_count"]),
                    "active_days": int(row["active_days"]),
                    "last_listened_at": row["last_listened_at"],
                }
                for row in rows
            ]
        overview = None
        if view == "overview":
            daily_rows = connection.execute(
                """
                SELECT listened_date, total_seconds, track_count
                FROM daily_listening_summary
                WHERE listened_date BETWEEN ? AND ?
                ORDER BY listened_date ASC
                """,
                (start_value, end_value),
            ).fetchall()
            top_track_rows = connection.execute(
                """
                SELECT recording_id, MAX(title) AS title, MAX(artist) AS artist,
                       SUM(seconds) AS seconds, COUNT(DISTINCT listened_date) AS active_days
                FROM daily_track_listening
                WHERE listened_date BETWEEN ? AND ?
                GROUP BY recording_id
                ORDER BY seconds DESC, title ASC
                LIMIT ?
                """,
                (start_value, end_value, limit),
            ).fetchall()
            top_artist_rows = connection.execute(
                """
                SELECT artist, SUM(seconds) AS seconds,
                       COUNT(DISTINCT recording_id) AS track_count,
                       COUNT(DISTINCT listened_date) AS active_days
                FROM daily_track_listening
                WHERE listened_date BETWEEN ? AND ?
                GROUP BY artist
                ORDER BY seconds DESC, artist ASC
                LIMIT ?
                """,
                (start_value, end_value, limit),
            ).fetchall()
            period_days = (end - start).days + 1
            previous_end = start - timedelta(days=1)
            previous_start = previous_end - timedelta(days=period_days - 1)
            previous_totals = connection.execute(
                """
                SELECT COALESCE(SUM(total_seconds), 0) AS total_seconds,
                       COUNT(*) AS active_days
                FROM daily_listening_summary
                WHERE listened_date BETWEEN ? AND ?
                """,
                (previous_start.isoformat(), previous_end.isoformat()),
            ).fetchone()
            previous_tracks = connection.execute(
                """
                SELECT COUNT(DISTINCT recording_id) AS track_count
                FROM daily_track_listening
                WHERE listened_date BETWEEN ? AND ?
                """,
                (previous_start.isoformat(), previous_end.isoformat()),
            ).fetchone()["track_count"]

            def change_ratio(current: float, previous: float) -> float | None:
                if previous <= 0:
                    return None
                return round((current - previous) / previous, 4)

            overview = {
                "daily_trend": [
                    {
                        "date": row["listened_date"],
                        "seconds": round(float(row["total_seconds"]), 1),
                        "formatted_duration": _format_duration(row["total_seconds"]),
                        "track_count": int(row["track_count"]),
                    }
                    for row in daily_rows
                ],
                "top_tracks": [
                    {
                        "recording_id": row["recording_id"],
                        "title": row["title"],
                        "artist": row["artist"],
                        "seconds": round(float(row["seconds"]), 1),
                        "formatted_duration": _format_duration(row["seconds"]),
                        "active_days": int(row["active_days"]),
                    }
                    for row in top_track_rows
                ],
                "top_artists": [
                    {
                        "artist": row["artist"],
                        "seconds": round(float(row["seconds"]), 1),
                        "formatted_duration": _format_duration(row["seconds"]),
                        "track_count": int(row["track_count"]),
                        "active_days": int(row["active_days"]),
                    }
                    for row in top_artist_rows
                ],
                "repeat_tracks": [
                    {
                        "recording_id": row["recording_id"],
                        "title": row["title"],
                        "artist": row["artist"],
                        "seconds": round(float(row["seconds"]), 1),
                        "active_days": int(row["active_days"]),
                    }
                    for row in top_track_rows
                    if int(row["active_days"]) >= 2
                ],
                "previous_period": {
                    "start_date": previous_start.isoformat(),
                    "end_date": previous_end.isoformat(),
                    "total_seconds": round(float(previous_totals["total_seconds"]), 1),
                    "active_days": int(previous_totals["active_days"]),
                    "track_count": int(previous_tracks),
                },
                "comparison": {
                    "listening_time_change": change_ratio(
                        float(totals["total_seconds"]),
                        float(previous_totals["total_seconds"]),
                    ),
                    "active_days_change": change_ratio(
                        float(totals["active_days"]),
                        float(previous_totals["active_days"]),
                    ),
                    "track_count_change": change_ratio(
                        float(unique_tracks),
                        float(previous_tracks),
                    ),
                },
            }
    total_seconds = round(float(totals["total_seconds"]), 1)
    response = {
        "start_date": start_value,
        "end_date": end_value,
        "group_by": group_by,
        "view": view,
        "total_seconds": total_seconds,
        "formatted_duration": _format_duration(total_seconds),
        "active_days": int(totals["active_days"]),
        "track_count": int(unique_tracks),
        "track_entries": int(totals["track_entries"]),
        "items": items,
    }
    if overview is not None:
        response["overview"] = overview
    return response
