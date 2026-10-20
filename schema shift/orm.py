from __future__ import annotations

import sqlite3
from typing import Any


class SqliteRepository:
    """Small generated-ORM-like repository used by the demo and tests."""

    def __init__(self, db_path: str):
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.connection.close()

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def create_user(self, user_id: str, full_name: str, email: str) -> None:
        self.connection.execute(
            "INSERT INTO users (id, full_name, email, created_at, address_city, address_country, tags) VALUES (?, ?, ?, NULL, NULL, NULL, '[]')",
            (user_id, full_name, email),
        )
        self.connection.commit()

    def update_user_email(self, user_id: str, email: str) -> None:
        self.connection.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))
        self.connection.commit()

    def delete_user(self, user_id: str) -> None:
        self.connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self.connection.commit()
