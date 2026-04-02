from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from tsukasa_bot.constants import SCHEDULE_ASSIGNMENT_START_COLUMN, SCHEDULE_SHEET_NAME
from tsukasa_bot.repositories.metadata_repository import MetadataRepository
from tsukasa_bot.services.errors import GoogleWorkspaceError
from tsukasa_bot.services.profile_service import ProfileService

if TYPE_CHECKING:
    from tsukasa_bot.services.google_workspace import GoogleWorkspaceService

TIME_ZONES = {
    "EST": ZoneInfo("America/New_York"),
    "CST": ZoneInfo("America/Chicago"),
    "PST": ZoneInfo("America/Los_Angeles"),
    "JST": ZoneInfo("Asia/Tokyo"),
}


@dataclass(frozen=True)
class ParsedOffset:
    label: str
    target_date: datetime


@dataclass(frozen=True)
class ScheduleSlot:
    date_str: str
    time_range: str
    row_index: int
    start_time: datetime
    assignments: list[str]


class ScheduleService:
    def __init__(
        self,
        repository: MetadataRepository,
        google: GoogleWorkspaceService,
        profile_service: ProfileService,
        timezone_name: str,
    ) -> None:
        self.repository = repository
        self.google = google
        self.profile_service = profile_service
        self.primary_tz = ZoneInfo(timezone_name)

    def create_schedule(self, guild_id: str, days: int) -> None:
        if days < 1:
            raise ValueError("Days must be at least 1.")
        sheet = self._get_sheet(guild_id)
        rows = self._build_schedule_rows(days)
        existing_rows = self.google.get_values(sheet["spreadsheet_id"], f"{SCHEDULE_SHEET_NAME}!A2:J")
        if len(existing_rows) > len(rows):
            rows.extend([[""] * 10 for _ in range(len(existing_rows) - len(rows))])
        self.google.update_values(f"{SCHEDULE_SHEET_NAME}!A2:J", rows, sheet["spreadsheet_id"])

    def add_user_to_range(self, guild_id: str, user_id: str, offset: str, time_range: str) -> str:
        return self._update_assignment(guild_id, user_id, offset, time_range, remove=False)

    def add_user_to_slots(self, guild_id: str, user_id: str, offset: str, time_ranges: list[str]) -> str:
        if not time_ranges:
            raise ValueError("Select at least one slot.")
        return self._update_multiple_assignments(guild_id, user_id, offset, time_ranges, remove=False)

    def remove_user_from_range(self, guild_id: str, user_id: str, offset: str, time_range: str) -> str:
        return self._update_assignment(guild_id, user_id, offset, time_range, remove=True)

    def get_slots_for_offset(self, guild_id: str, offset: str) -> tuple[str, list[ScheduleSlot]]:
        sheet = self._get_sheet(guild_id)
        parsed = self.parse_day_offset(offset)
        date_str = parsed.target_date.strftime("%m-%d")
        values = self.google.get_values(sheet["spreadsheet_id"], f"{SCHEDULE_SHEET_NAME}!A:ZZ")
        if len(values) <= 1:
            return date_str, []

        slots: list[ScheduleSlot] = []
        current_date = ""
        for row_index, row in enumerate(values[1:], start=2):
            if row and row[0]:
                current_date = row[0]
            if current_date != date_str or len(row) <= 1:
                continue

            start_hour, end_hour = self.parse_time_range(row[1])
            slot_start = datetime.combine(parsed.target_date.date(), time(hour=start_hour), tzinfo=self.primary_tz)
            assignments = [name for name in row[SCHEDULE_ASSIGNMENT_START_COLUMN:] if name]
            slots.append(
                ScheduleSlot(
                    date_str=date_str,
                    time_range=f"{start_hour:02d}-{end_hour:02d}",
                    row_index=row_index,
                    start_time=slot_start,
                    assignments=assignments,
                )
            )
        return date_str, slots

    def get_schedule_for_offset(self, guild_id: str, offset: str) -> tuple[str, list[list[str]], str]:
        sheet = self._get_sheet(guild_id)
        parsed = self.parse_day_offset(offset)
        date_str = parsed.target_date.strftime("%m-%d")
        all_rows = self.google.get_values(sheet["spreadsheet_id"], f"{SCHEDULE_SHEET_NAME}!A:ZZ")
        if not all_rows:
            return date_str, [], f"{SCHEDULE_SHEET_NAME}!A1:J1"

        selected = [all_rows[0]]
        found = False
        max_width = len(all_rows[0])
        for row in all_rows[1:]:
            row_date = row[0] if row else ""
            if row_date == date_str:
                found = True
            elif found and row_date:
                break
            if found:
                max_width = max(max_width, len(row))
                selected.append(row)

        if len(selected) == 1:
            return date_str, [], f"{SCHEDULE_SHEET_NAME}!A1:J1"

        selected = [row + [""] * (max_width - len(row)) for row in selected]
        start_row = next(index for index, row in enumerate(all_rows, start=1) if row and row[0] == date_str)
        end_row = start_row + len(selected) - 2
        end_column = self._column_letter(max_width)
        return date_str, selected, f"{SCHEDULE_SHEET_NAME}!A1:{end_column}{end_row}"

    def get_upcoming_assignments(self, guild_id: str, minutes_before: int) -> tuple[datetime, list[str]] | None:
        sheet = self._get_sheet(guild_id)
        rows = self.google.get_values(sheet["spreadsheet_id"], f"{SCHEDULE_SHEET_NAME}!A:ZZ")
        if len(rows) <= 1:
            return None

        current_date = ""
        now = datetime.now(self.primary_tz).replace(second=0, microsecond=0)
        nearest_time: datetime | None = None
        nearest_names: list[str] = []

        for row in rows[1:]:
            if len(row) < 2:
                continue
            if row[0]:
                current_date = row[0]
            if not current_date:
                continue
            start_hour, _ = self.parse_time_range(row[1])
            event_time = datetime.strptime(
                f"{now.year}-{current_date} {start_hour:02d}:00",
                "%Y-%m-%d %H:%M",
            ).replace(tzinfo=self.primary_tz)
            if event_time < now:
                continue
            if event_time - timedelta(minutes=minutes_before) <= now:
                names = [name for name in row[SCHEDULE_ASSIGNMENT_START_COLUMN:] if name]
                if names:
                    nearest_time = event_time
                    nearest_names = names
                    break
        if nearest_time is None:
            return None
        return nearest_time, nearest_names

    def parse_day_offset(self, raw_offset: str) -> ParsedOffset:
        if raw_offset == "t":
            return ParsedOffset(label="t", target_date=datetime.now(self.primary_tz))
        if raw_offset.startswith("t+"):
            days = int(raw_offset.split("+", maxsplit=1)[1])
            return ParsedOffset(label=raw_offset, target_date=datetime.now(self.primary_tz) + timedelta(days=days))
        raise ValueError("Day offset must be `t` or `t+N`.")

    def parse_time_range(self, time_range: str) -> tuple[int, int]:
        try:
            start_text, end_text = time_range.split("-", maxsplit=1)
            start_hour = int(start_text)
            end_hour = int(end_text)
        except ValueError as exc:
            raise ValueError("Time range must use `HH-HH` format, for example `18-20`.") from exc

        if not (0 <= start_hour <= 23 and 1 <= end_hour <= 24 and start_hour < end_hour):
            raise ValueError("Time range must use `HH-HH` format, for example `18-20`.")
        return start_hour, end_hour

    def _update_assignment(self, guild_id: str, user_id: str, offset: str, time_range: str, remove: bool) -> str:
        return self._update_multiple_assignments(guild_id, user_id, offset, [time_range], remove)

    def _update_multiple_assignments(
        self,
        guild_id: str,
        user_id: str,
        offset: str,
        time_ranges: list[str],
        remove: bool,
    ) -> str:
        sheet = self._get_sheet(guild_id)
        nickname = self.profile_service.get_registered_name(guild_id, user_id)
        if not nickname:
            raise ValueError("Register your profile first.")

        parsed = self.parse_day_offset(offset)
        date_str = parsed.target_date.strftime("%m-%d")
        values = self.google.get_values(sheet["spreadsheet_id"], f"{SCHEDULE_SHEET_NAME}!A:ZZ")
        updates = []
        seen_ranges: set[str] = set()
        for time_range in time_ranges:
            if time_range in seen_ranges:
                continue
            seen_ranges.add(time_range)

            start_hour, end_hour = self.parse_time_range(time_range)
            start_row_index = self._find_row_index(values, date_str, start_hour)
            if start_row_index is None:
                raise ValueError(f"Time slot {start_hour:02d}-{start_hour + 1:02d} was not found for {date_str}.")

            for row_index in range(start_row_index, start_row_index + (end_hour - start_hour)):
                row = values[row_index - 1] if row_index - 1 < len(values) else []
                assignments = row[SCHEDULE_ASSIGNMENT_START_COLUMN:]

                if remove:
                    if nickname not in assignments:
                        raise ValueError(f"{nickname} is not assigned to one of those slots.")
                    target_column = assignments.index(nickname) + SCHEDULE_ASSIGNMENT_START_COLUMN + 1
                    updates.append(
                        {"range": f"{SCHEDULE_SHEET_NAME}!{self._column_letter(target_column)}{row_index}", "values": [[""]]}
                    )
                else:
                    if nickname in assignments:
                        raise ValueError(f"{nickname} is already assigned to one of those slots.")
                    target_column = self._next_assignment_column(assignments)
                    updates.append(
                        {"range": f"{SCHEDULE_SHEET_NAME}!{self._column_letter(target_column)}{row_index}", "values": [[nickname]]}
                    )

        self.google.batch_update_values(sheet["spreadsheet_id"], updates)
        return date_str

    def _find_row_index(self, values: list[list[str]], date_str: str, start_hour: int) -> int | None:
        current_date = ""
        target_slot = f"{start_hour:02d}-{start_hour + 1 if start_hour + 1 < 24 else 24:02d}"
        for index, row in enumerate(values[1:], start=2):
            if row and row[0]:
                current_date = row[0]
            if current_date == date_str and len(row) > 1 and row[1] == target_slot:
                return index
        return None

    def _build_schedule_rows(self, days: int) -> list[list[str]]:
        rows: list[list[str]] = []
        today = datetime.now(self.primary_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        for day_offset in range(days):
            date_value = (today + timedelta(days=day_offset)).strftime("%m-%d")
            hours = range(18, 24) if day_offset == 0 else range(0, 24)
            for offset_index, hour_value in enumerate(hours):
                start = datetime.combine(today.date(), time(hour=hour_value), tzinfo=self.primary_tz) + timedelta(days=day_offset)
                end = start + timedelta(hours=1)
                row = [
                    date_value if offset_index == 0 else "",
                    self._format_slot(start, TIME_ZONES["EST"]),
                    self._format_slot(start, TIME_ZONES["CST"]),
                    self._format_slot(start, TIME_ZONES["PST"]),
                    self._format_slot(start, TIME_ZONES["JST"]),
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
                rows.append(row)
        return rows

    def _format_slot(self, start: datetime, target_tz: ZoneInfo) -> str:
        localized = start.astimezone(target_tz)
        end = localized + timedelta(hours=1)
        end_hour = "24" if end.hour == 0 else f"{end.hour:02d}"
        return f"{localized.hour:02d}-{end_hour}"

    def _next_assignment_column(self, assignments: list[str]) -> int:
        for offset, value in enumerate(assignments, start=SCHEDULE_ASSIGNMENT_START_COLUMN + 1):
            if value == "":
                return offset
        return SCHEDULE_ASSIGNMENT_START_COLUMN + len(assignments) + 1

    def _column_letter(self, number: int) -> str:
        result = ""
        current = number
        while current > 0:
            current, remainder = divmod(current - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def _get_sheet(self, guild_id: str) -> dict[str, str]:
        sheet = self.repository.get_guild_sheet(guild_id)
        if not sheet:
            raise GoogleWorkspaceError("No Google Sheet is configured for this server yet.")
        return sheet
