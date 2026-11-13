import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

import bcrypt

DB_PATH = "users.db"

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I, to avoid mix-ups
CODE_LENGTH = 8
CODE_MINUTES = 30
MAX_CODE_TRIES = 5
BAD_CODE_MESSAGE = "Invalid or expired code. Please ask your admin for a new one."

# Columns added after the first version. Older users.db files are upgraded automatically.
NEW_COLUMNS = {
    "active": "INTEGER NOT NULL DEFAULT 1",
    "reset_requested": "INTEGER NOT NULL DEFAULT 0",
    "reset_code_hash": "BLOB",
    "reset_expires": "TEXT",
    "reset_attempts": "INTEGER NOT NULL DEFAULT 0",
}


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'employee')),
            active INTEGER NOT NULL DEFAULT 1,
            reset_requested INTEGER NOT NULL DEFAULT 0,
            reset_code_hash BLOB,
            reset_expires TEXT,
            reset_attempts INTEGER NOT NULL DEFAULT 0
        )"""
    )
    existing = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    for name, definition in NEW_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
    conn.commit()
    return conn


def _clear_code(conn, username):
    conn.execute(
        "UPDATE users SET reset_code_hash = NULL, reset_expires = NULL, "
        "reset_attempts = 0 WHERE username = ?",
        (username,),
    )
    conn.commit()


def create_user(username, password, role):
    """Create a user. The password is stored hashed, never in plain text."""
    username = username.strip().lower()
    if not username or len(password) < 6:
        raise ValueError("Username is required and password needs 6+ characters.")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    try:
        with closing(_connect()) as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, hashed, role),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"Username '{username}' already exists.")


def list_users():
    """Username, role and status for every user. Never returns password hashes."""
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT username, role, active, reset_requested FROM users "
            "ORDER BY role, username"
        ).fetchall()
    return [
        {
            "username": r[0],
            "role": r[1],
            "active": bool(r[2]),
            "reset_requested": bool(r[3]),
        }
        for r in rows
    ]


def get_user(username):
    """Current details of one user, or None if the user does not exist."""
    username = username.strip().lower()
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT username, role, active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None:
        return None
    return {"username": row[0], "role": row[1], "active": bool(row[2])}


def set_active(username, active):
    """Block (active=False) or activate (active=True) a user."""
    username = username.strip().lower()
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT role FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            raise ValueError(f"User '{username}' not found.")
        if not active and row[0] == "admin":
            active_admins = conn.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1"
            ).fetchone()[0]
            if active_admins <= 1:
                raise ValueError("You cannot block the last active admin.")
        conn.execute(
            "UPDATE users SET active = ? WHERE username = ?",
            (1 if active else 0, username),
        )
        conn.commit()


def request_reset(username):
    """Employee asks for a reset. Never reveals whether the username exists."""
    username = username.strip().lower()
    with closing(_connect()) as conn:
        conn.execute(
            "UPDATE users SET reset_requested = 1 WHERE username = ? AND active = 1",
            (username,),
        )
        conn.commit()


def issue_reset_code(username):
    """Admin creates a one-time code (valid 30 minutes). Returned once, stored hashed."""
    username = username.strip().lower()
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    code_hash = bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt())
    expires = (datetime.now(timezone.utc) + timedelta(minutes=CODE_MINUTES)).isoformat()
    with closing(_connect()) as conn:
        cur = conn.execute(
            "UPDATE users SET reset_code_hash = ?, reset_expires = ?, "
            "reset_attempts = 0, reset_requested = 0 "
            "WHERE username = ? AND active = 1",
            (code_hash, expires, username),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError("User not found, or the account is blocked.")
    return f"{code[:4]}-{code[4:]}"


def redeem_reset_code(username, code, new_password):
    """Employee sets a new password using the admin's one-time code."""
    username = username.strip().lower()
    if len(new_password) < 6:
        raise ValueError("Password needs 6+ characters.")
    code = code.replace("-", "").replace(" ", "").upper()

    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT reset_code_hash, reset_expires, reset_attempts "
            "FROM users WHERE username = ? AND active = 1",
            (username,),
        ).fetchone()
        # Same message for every failure, so nobody can probe which usernames exist
        if row is None or row[0] is None or row[1] is None:
            raise ValueError(BAD_CODE_MESSAGE)

        code_hash, expires, attempts = row
        if datetime.now(timezone.utc) > datetime.fromisoformat(expires) or attempts >= MAX_CODE_TRIES:
            _clear_code(conn, username)
            raise ValueError(BAD_CODE_MESSAGE)

        if not bcrypt.checkpw(code.encode("utf-8"), code_hash):
            attempts += 1
            if attempts >= MAX_CODE_TRIES:
                _clear_code(conn, username)
            else:
                conn.execute(
                    "UPDATE users SET reset_attempts = ? WHERE username = ?",
                    (attempts, username),
                )
                conn.commit()
            raise ValueError(BAD_CODE_MESSAGE)

        new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt())
        conn.execute(
            "UPDATE users SET password_hash = ?, reset_code_hash = NULL, "
            "reset_expires = NULL, reset_attempts = 0, reset_requested = 0 "
            "WHERE username = ?",
            (new_hash, username),
        )
        conn.commit()


def verify_user(username, password):
    """Return {'username', 'role', 'active'} if the password is correct, else None."""
    username = username.strip().lower()
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT username, password_hash, role, active FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None:
        return None
    if bcrypt.checkpw(password.encode("utf-8"), row[1]):
        return {"username": row[0], "role": row[2], "active": bool(row[3])}
    return None