import sqlite3
from contextlib import closing

import bcrypt

DB_PATH = "users.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash BLOB NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'employee'))
        )"""
    )
    return conn


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


def reset_password(username, new_password):
    """Set a new password for an existing user. Stored hashed, like create_user."""
    username = username.strip().lower()
    if len(new_password) < 6:
        raise ValueError("Password needs 6+ characters.")
    hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt())
    with closing(_connect()) as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (hashed, username),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise ValueError(f"User '{username}' not found.")


def list_usernames():
    """Usernames only, never password hashes."""
    with closing(_connect()) as conn:
        rows = conn.execute("SELECT username FROM users ORDER BY username").fetchall()
    return [r[0] for r in rows]


def verify_user(username, password):
    """Return {'username', 'role'} if the login is correct, otherwise None."""
    username = username.strip().lower()
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None:
        return None
    if bcrypt.checkpw(password.encode("utf-8"), row[1]):
        return {"username": row[0], "role": row[2]}
    return None