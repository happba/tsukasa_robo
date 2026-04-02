from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tsukasa_bot.repositories.metadata_repository import MetadataRepository
from tsukasa_bot.services.schedule_service import ScheduleService


class FakeGoogleWorkspace:
    def __init__(self) -> None:
        self.values: dict[str, list[list[str]]] = {}
        self.batch_updates: list[list[dict[str, object]]] = []

    def get_values(self, spreadsheet_id: str, range_name: str) -> list[list[str]]:
        return self.values.get(range_name, [])

    def update_values(self, range_name: str, values: list[list[object]], spreadsheet_id: str) -> None:
        self.values[range_name] = values

    def batch_update_values(self, spreadsheet_id: str, updates: list[dict[str, object]]) -> None:
        self.batch_updates.append(updates)


class FakeProfileService:
    def __init__(self) -> None:
        self.names = {("guild-1", "user-1"): "Tsukasa"}

    def get_registered_name(self, guild_id: str, user_id: str) -> str | None:
        return self.names.get((guild_id, user_id))


class ScheduleServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = MetadataRepository(Path(self.temp_dir.name) / "metadata.db")
        repository.upsert_guild_sheet("guild-1", "sheet-1", "https://example.com", "now")
        self.google = FakeGoogleWorkspace()
        self.service = ScheduleService(repository, self.google, FakeProfileService(), "America/New_York")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_parse_time_range(self) -> None:
        self.assertEqual(self.service.parse_time_range("18-21"), (18, 21))
        with self.assertRaises(ValueError):
            self.service.parse_time_range("21-18")

    def test_create_schedule_writes_rows(self) -> None:
        self.service.create_schedule("guild-1", 2)
        self.assertTrue(self.google.values["schedule!A2:J"])

    def test_add_user_reuses_first_empty_assignment_cell(self) -> None:
        self.google.values["schedule!A:ZZ"] = [
            ["Date", "EST", "CST", "PST", "JST", "Runner", "P2", "P3", "P4", "P5"],
            ["04-01", "18-19", "17-18", "15-16", "08-09", "Runner1", "A", "", "C", "D", "E"],
        ]
        original_parse = self.service.parse_day_offset
        self.service.parse_day_offset = lambda _: type("Parsed", (), {"label": "t", "target_date": datetime(2026, 4, 1)})()
        try:
            self.service.add_user_to_range("guild-1", "user-1", "t", "18-19")
        finally:
            self.service.parse_day_offset = original_parse
        self.assertEqual(self.google.batch_updates[-1][0]["range"], "schedule!H2")

    def test_add_user_allows_overflow_past_initial_columns(self) -> None:
        self.google.values["schedule!A:ZZ"] = [
            ["Date", "EST", "CST", "PST", "JST", "Runner", "P2", "P3", "P4", "P5"],
            ["04-01", "18-19", "17-18", "15-16", "08-09", "Runner1", "A", "B", "C", "D", "E"],
        ]
        original_parse = self.service.parse_day_offset
        self.service.parse_day_offset = lambda _: type("Parsed", (), {"label": "t", "target_date": datetime(2026, 4, 1)})()
        try:
            self.service.add_user_to_range("guild-1", "user-1", "t", "18-19")
        finally:
            self.service.parse_day_offset = original_parse
        self.assertEqual(self.google.batch_updates[-1][0]["range"], "schedule!L2")

    def test_get_slots_for_offset_returns_slot_metadata(self) -> None:
        self.google.values["schedule!A:ZZ"] = [
            ["Date", "EST", "CST", "PST", "JST", "Runner", "P2", "P3", "P4", "P5"],
            ["04-01", "18-19", "17-18", "15-16", "08-09", "Runner1", "A"],
            ["", "19-20", "18-19", "16-17", "09-10", ""],
            ["04-02", "00-01", "23-24", "21-22", "14-15", ""],
        ]
        original_parse = self.service.parse_day_offset
        self.service.parse_day_offset = lambda _: type("Parsed", (), {"label": "t", "target_date": datetime(2026, 4, 1)})()
        try:
            date_str, slots = self.service.get_slots_for_offset("guild-1", "t")
        finally:
            self.service.parse_day_offset = original_parse

        self.assertEqual(date_str, "04-01")
        self.assertEqual([slot.time_range for slot in slots], ["18-19", "19-20"])
        self.assertEqual(slots[0].assignments, ["A"])

    def test_add_user_to_slots_updates_multiple_ranges(self) -> None:
        self.google.values["schedule!A:ZZ"] = [
            ["Date", "EST", "CST", "PST", "JST", "Runner", "P2", "P3", "P4", "P5"],
            ["04-01", "18-19", "17-18", "15-16", "08-09", ""],
            ["", "19-20", "18-19", "16-17", "09-10", ""],
        ]
        original_parse = self.service.parse_day_offset
        self.service.parse_day_offset = lambda _: type("Parsed", (), {"label": "t", "target_date": datetime(2026, 4, 1)})()
        try:
            self.service.add_user_to_slots("guild-1", "user-1", "t", ["18-19", "19-20"])
        finally:
            self.service.parse_day_offset = original_parse

        self.assertEqual(
            [update["range"] for update in self.google.batch_updates[-1]],
            ["schedule!G2", "schedule!G3"],
        )

    def test_remove_user_clears_exact_existing_cell(self) -> None:
        self.google.values["schedule!A:ZZ"] = [
            ["Date", "EST", "CST", "PST", "JST", "Runner", "P2", "P3", "P4", "P5"],
            ["04-01", "18-19", "17-18", "15-16", "08-09", "Runner1", "A", "Tsukasa", "C"],
        ]
        original_parse = self.service.parse_day_offset
        self.service.parse_day_offset = lambda _: type("Parsed", (), {"label": "t", "target_date": datetime(2026, 4, 1)})()
        try:
            self.service.remove_user_from_range("guild-1", "user-1", "t", "18-19")
        finally:
            self.service.parse_day_offset = original_parse
        self.assertEqual(self.google.batch_updates[-1][0]["range"], "schedule!H2")


if __name__ == "__main__":
    unittest.main()
