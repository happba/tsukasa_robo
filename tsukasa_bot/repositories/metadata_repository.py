from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class MetadataRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = str(db_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS guild_sheets (
                    guild_id TEXT PRIMARY KEY,
                    spreadsheet_id TEXT NOT NULL,
                    sheet_url TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_profiles (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    nickname TEXT NOT NULL,
                    role TEXT NOT NULL,
                    power TEXT NOT NULL,
                    skill_sum INTEGER NOT NULL,
                    skill_multiplier REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS alert_settings (
                    guild_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    minutes_before INTEGER NOT NULL,
                    enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS grant_access_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    spreadsheet_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def upsert_guild_sheet(
        self,
        guild_id: str,
        spreadsheet_id: str,
        sheet_url: str,
        created_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO guild_sheets (guild_id, spreadsheet_id, sheet_url, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    spreadsheet_id = excluded.spreadsheet_id,
                    sheet_url = excluded.sheet_url,
                    created_at = excluded.created_at
                """,
                (guild_id, spreadsheet_id, sheet_url, created_at),
            )

    def get_guild_sheet(self, guild_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM guild_sheets WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_guild_sheet(self, guild_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM guild_sheets WHERE guild_id = ?", (guild_id,))
            connection.execute("DELETE FROM user_profiles WHERE guild_id = ?", (guild_id,))
            connection.execute("DELETE FROM alert_settings WHERE guild_id = ?", (guild_id,))

    def upsert_user_profile(
        self,
        guild_id: str,
        user_id: str,
        nickname: str,
        role: str,
        power: str,
        skill_sum: int,
        skill_multiplier: float,
        updated_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_profiles (
                    guild_id, user_id, nickname, role, power, skill_sum, skill_multiplier, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    nickname = excluded.nickname,
                    role = excluded.role,
                    power = excluded.power,
                    skill_sum = excluded.skill_sum,
                    skill_multiplier = excluded.skill_multiplier,
                    updated_at = excluded.updated_at
                """,
                (
                    guild_id,
                    user_id,
                    nickname,
                    role,
                    power,
                    skill_sum,
                    skill_multiplier,
                    updated_at,
                ),
            )

    def get_user_profile(self, guild_id: str, user_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM user_profiles WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def update_user_nickname(self, guild_id: str, user_id: str, nickname: str, updated_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE user_profiles
                SET nickname = ?, updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                """,
                (nickname, updated_at, guild_id, user_id),
            )

    def upsert_alert_setting(
        self,
        guild_id: str,
        channel_id: str,
        minutes_before: int,
        enabled: bool,
        updated_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO alert_settings (guild_id, channel_id, minutes_before, enabled, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    minutes_before = excluded.minutes_before,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (guild_id, channel_id, minutes_before, int(enabled), updated_at),
            )

    def get_alert_setting(self, guild_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM alert_settings WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_enabled_alert_settings(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM alert_settings WHERE enabled = 1"
            ).fetchall()
        return [dict(row) for row in rows]

    def disable_alert_setting(self, guild_id: str, updated_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE alert_settings SET enabled = 0, updated_at = ? WHERE guild_id = ?",
                (updated_at, guild_id),
            )

    def add_grant_access_audit(
        self,
        guild_id: str,
        spreadsheet_id: str,
        email: str,
        status: str,
        detail: str | None,
        created_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO grant_access_audit (
                    guild_id, spreadsheet_id, email, status, detail, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (guild_id, spreadsheet_id, email, status, detail, created_at),
            )
