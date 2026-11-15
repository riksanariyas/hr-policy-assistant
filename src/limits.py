import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from src.auth import DB_PATH

USER_DAILY_LIMIT = 5        # questions per employee per day
GLOBAL_DAILY_LIMIT = 50     # questions for everyone together per day
MAX_QUESTION_CHARS = 300

INDIA = timezone(timedelta(hours=5, minutes=30))  # India has no daylight saving

USER_MESSAGE = (
    f"You have used your {USER_DAILY_LIMIT} questions for today. "
    "Your allowance resets at midnight (India time)."
)
GLOBAL_MESSAGE = (
    "The assistant has reached its daily limit for all users. "
    "Please try again tomorrow."
)


def _today():
    return datetime.now(INDIA).strftime("%Y-%m-%d")


def _connect():
    # autocommit mode, so we control transactions ourselves
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS usage (
            day TEXT NOT NULL,
            username TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, username)
        )"""
    )
    return conn


def _counts(conn, day, username):
    row = conn.execute(
        "SELECT count FROM usage WHERE day = ? AND username = ?", (day, username)
    ).fetchone()
    user_count = row[0] if row else 0
    global_count = conn.execute(
        "SELECT COALESCE(SUM(count), 0) FROM usage WHERE day = ?", (day,)
    ).fetchone()[0]
    return user_count, global_count


def remaining(username):
    """Questions this user can still ask today (the smaller of the two limits)."""
    with closing(_connect()) as conn:
        user_count, global_count = _counts(conn, _today(), username)
    return max(0, min(USER_DAILY_LIMIT - user_count, GLOBAL_DAILY_LIMIT - global_count))


def reserve(username):
    """Take one question from the allowance. Returns (allowed, message).

    The check and the count happen in one transaction, so two questions at the
    same moment cannot both slip through.
    """
    day = _today()
    with closing(_connect()) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            user_count, global_count = _counts(conn, day, username)
            if global_count >= GLOBAL_DAILY_LIMIT:
                conn.execute("ROLLBACK")
                return False, GLOBAL_MESSAGE
            if user_count >= USER_DAILY_LIMIT:
                conn.execute("ROLLBACK")
                return False, USER_MESSAGE
            conn.execute(
                "INSERT INTO usage (day, username, count) VALUES (?, ?, 1) "
                "ON CONFLICT(day, username) DO UPDATE SET count = count + 1",
                (day, username),
            )
            conn.execute("COMMIT")
            return True, ""
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise


def refund(username):
    """Give the question back (the model was not used, or the call failed)."""
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE usage SET count = count - 1 "
            "WHERE day = ? AND username = ? AND count > 0",
            (_today(), username),
        )