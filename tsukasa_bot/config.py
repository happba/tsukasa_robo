from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    discord_token: str
    google_service_account_file: Path
    metadata_db_path: Path
    timezone_name: str = "America/New_York"
    default_sheet_title: str = "Project Sekai Event Schedule"

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()

        token = os.getenv("DISCORD_TOKEN", "").strip()
        service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        db_path = os.getenv("METADATA_DB_PATH", "data/tsukasa_robo.db").strip()
        timezone_name = os.getenv("BOT_TIMEZONE", "America/New_York").strip()
        default_sheet_title = os.getenv("DEFAULT_SHEET_TITLE", "Project Sekai Event Schedule").strip()

        if not token:
            raise RuntimeError("DISCORD_TOKEN is not configured.")
        if not service_account_file:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE is not configured.")

        service_account_path = Path(service_account_file).expanduser()
        if not service_account_path.exists():
            raise RuntimeError(
                f"GOOGLE_SERVICE_ACCOUNT_FILE does not exist: {service_account_path}"
            )

        metadata_db_path = Path(db_path).expanduser()
        metadata_db_path.parent.mkdir(parents=True, exist_ok=True)

        return cls(
            discord_token=token,
            google_service_account_file=service_account_path,
            metadata_db_path=metadata_db_path,
            timezone_name=timezone_name,
            default_sheet_title=default_sheet_title,
        )

