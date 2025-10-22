"""Database utilities for the administrative toolkit."""
from __future__ import annotations

import os
import sqlite3
from typing import List, Optional, Tuple

from cryptography.fernet import Fernet

DB_PATH = "quant_users.db"
KEY_PATH = "admin_key.key"


def generate_key() -> bytes:
    """Generate a new encryption key for securing API credentials."""
    return Fernet.generate_key()


def _load_or_create_key() -> bytes:
    """Load the persisted encryption key, creating it if required."""
    if not os.path.exists(KEY_PATH):
        key = generate_key()
        with open(KEY_PATH, "wb") as key_file:
            key_file.write(key)
        return key

    with open(KEY_PATH, "rb") as key_file:
        return key_file.read()


def _get_cipher() -> Fernet:
    return Fernet(_load_or_create_key())


def encrypt_value(value: str) -> bytes:
    """Encrypt a text value using the persisted Fernet key."""
    cipher = _get_cipher()
    return cipher.encrypt(value.encode("utf-8"))


def decrypt_value(value: bytes) -> str:
    """Decrypt an encrypted value using the persisted Fernet key."""
    cipher = _get_cipher()
    return cipher.decrypt(value).decode("utf-8")


def init_db() -> None:
    """Initialise the database and ensure the extended schema exists."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            api_key_encrypted BLOB,
            api_secret_encrypted BLOB,
            create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS allowed_pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE NOT NULL,
            is_enabled INTEGER DEFAULT 1,
            create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fund_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            action TEXT NOT NULL,
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )

    conn.commit()
    conn.close()


def add_allowed_pair(symbol: str) -> bool:
    """Insert a new allowed trading pair if it does not already exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO allowed_pairs (symbol) VALUES (?)",
            (symbol.upper(),),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_allowed_pairs(include_disabled: bool = False) -> List[str]:
    """Return the list of allowed trading pairs."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if include_disabled:
        cursor.execute("SELECT symbol FROM allowed_pairs")
    else:
        cursor.execute("SELECT symbol FROM allowed_pairs WHERE is_enabled=1")
    pairs = [row[0] for row in cursor.fetchall()]
    conn.close()
    return pairs


def toggle_allowed_pair(symbol: str, enabled: bool) -> None:
    """Enable or disable a trading pair."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE allowed_pairs SET is_enabled=? WHERE symbol=?",
        (1 if enabled else 0, symbol.upper()),
    )
    conn.commit()
    conn.close()


def record_fund_allocation(user_id: int, amount: float, action: str) -> None:
    """Record a fund allocation or reclaim action for auditing purposes."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO fund_allocations (user_id, amount, action) VALUES (?, ?, ?)",
        (user_id, amount, action),
    )
    conn.commit()
    conn.close()


def store_user_api_credentials(user_id: int, api_key: str, api_secret: str) -> None:
    """Persist encrypted API credentials for a user account."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET api_key_encrypted=?, api_secret_encrypted=? WHERE id=?",
        (encrypt_value(api_key), encrypt_value(api_secret), user_id),
    )
    conn.commit()
    conn.close()


def get_user_api_credentials(user_id: int) -> Optional[Tuple[str, str]]:
    """Retrieve decrypted API credentials for a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT api_key_encrypted, api_secret_encrypted FROM users WHERE id=?",
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0] or not row[1]:
        return None
    return decrypt_value(row[0]), decrypt_value(row[1])
