from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from tsukasa_bot.constants import PROFILE_SHEET_NAME, SCHEDULE_SHEET_NAME
from tsukasa_bot.repositories.metadata_repository import MetadataRepository
from tsukasa_bot.services.errors import GoogleWorkspaceError
from tsukasa_bot.services.skill_service import calculate_skill_multiplier, calculate_skill_sum

if TYPE_CHECKING:
    from tsukasa_bot.services.google_workspace import GoogleWorkspaceService


@dataclass
class RegistrationResult:
    nickname: str
    role: str
    power: str
    skill_sum: int
    skill_multiplier: float
    updated: bool


class ProfileService:
    def __init__(self, repository: MetadataRepository, google: GoogleWorkspaceService) -> None:
        self.repository = repository
        self.google = google

    def register_profile(
        self,
        guild_id: str,
        user_id: str,
        nickname: str,
        role: str,
        power: str,
        skills: list[int],
    ) -> RegistrationResult:
        sheet = self.repository.get_guild_sheet(guild_id)
        if not sheet:
            raise GoogleWorkspaceError("No Google Sheet is configured for this server yet.")

        normalized_role = role.lower()
        if normalized_role not in {"h", "r"}:
            raise ValueError("Role must be `h` for helper or `r` for runner.")

        skill_sum = calculate_skill_sum(skills)
        skill_multiplier = calculate_skill_multiplier(skills)
        timestamp = self._now()

        existing_profile = self.repository.get_user_profile(guild_id, user_id)
        old_name = existing_profile["nickname"] if existing_profile else nickname

        sheet_rows = self.google.get_values(sheet["spreadsheet_id"], f"{PROFILE_SHEET_NAME}!A2:F")
        row_index = None
        for index, row in enumerate(sheet_rows, start=2):
            if row and row[0] == user_id:
                row_index = index
                break

        payload = [[user_id, nickname, normalized_role, power, skill_sum, round(skill_multiplier, 2)]]
        if row_index is None:
            self.google.append_values(f"{PROFILE_SHEET_NAME}!A2:F", payload, sheet["spreadsheet_id"])
            updated = False
        else:
            self.google.update_values(f"{PROFILE_SHEET_NAME}!A{row_index}:F{row_index}", payload, sheet["spreadsheet_id"])
            updated = True

        if old_name != nickname:
            self.rename_profile(guild_id, user_id, nickname, update_repository=False)

        self.repository.upsert_user_profile(
            guild_id=guild_id,
            user_id=user_id,
            nickname=nickname,
            role=normalized_role,
            power=power,
            skill_sum=skill_sum,
            skill_multiplier=skill_multiplier,
            updated_at=timestamp,
        )

        return RegistrationResult(
            nickname=nickname,
            role=normalized_role,
            power=power,
            skill_sum=skill_sum,
            skill_multiplier=skill_multiplier,
            updated=updated,
        )

    def rename_profile(
        self,
        guild_id: str,
        user_id: str,
        new_nickname: str,
        update_repository: bool = True,
    ) -> str:
        sheet = self.repository.get_guild_sheet(guild_id)
        if not sheet:
            raise GoogleWorkspaceError("No Google Sheet is configured for this server yet.")

        profile = self.repository.get_user_profile(guild_id, user_id)
        if not profile:
            raise ValueError("Register your profile first before renaming it.")

        old_name = profile["nickname"]
        spreadsheet_id = sheet["spreadsheet_id"]
        self._replace_name_in_sheet(spreadsheet_id, PROFILE_SHEET_NAME, old_name, new_nickname)
        self._replace_name_in_sheet(spreadsheet_id, SCHEDULE_SHEET_NAME, old_name, new_nickname)

        if update_repository:
            self.repository.update_user_nickname(guild_id, user_id, new_nickname, self._now())
        return old_name

    def get_registered_name(self, guild_id: str, user_id: str) -> str | None:
        profile = self.repository.get_user_profile(guild_id, user_id)
        return profile["nickname"] if profile else None

    def get_user_id_by_name(self, guild_id: str, nickname: str) -> str | None:
        sheet = self.repository.get_guild_sheet(guild_id)
        if not sheet:
            return None
        rows = self.google.get_values(sheet["spreadsheet_id"], f"{PROFILE_SHEET_NAME}!A2:B")
        for row in rows:
            if len(row) >= 2 and row[1] == nickname:
                return row[0]
        return None

    def _replace_name_in_sheet(self, spreadsheet_id: str, sheet_name: str, old_name: str, new_name: str) -> None:
        values = self.google.get_values(spreadsheet_id, f"{sheet_name}!A:Z")
        updates = []
        for row_index, row in enumerate(values, start=1):
            for col_index, cell_value in enumerate(row, start=1):
                if cell_value == old_name:
                    column_letter = self._column_letter(col_index)
                    updates.append(
                        {"range": f"{sheet_name}!{column_letter}{row_index}", "values": [[new_name]]}
                    )
        if updates:
            self.google.batch_update_values(spreadsheet_id, updates)

    def _column_letter(self, number: int) -> str:
        result = ""
        current = number
        while current > 0:
            current, remainder = divmod(current - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
