from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tsukasa_bot.repositories.metadata_repository import MetadataRepository


class MetadataRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "metadata.db"
        self.repository = MetadataRepository(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_persists_guild_sheet_mapping(self) -> None:
        self.repository.upsert_guild_sheet("guild-1", "sheet-1", "https://example.com/1", "now")
        loaded = self.repository.get_guild_sheet("guild-1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["spreadsheet_id"], "sheet-1")

    def test_persists_user_profile(self) -> None:
        self.repository.upsert_user_profile("guild-1", "user-1", "Tsukasa", "h", "33.5", 750, 2.3, "now")
        loaded = self.repository.get_user_profile("guild-1", "user-1")
        self.assertEqual(loaded["nickname"], "Tsukasa")
        self.assertEqual(loaded["skill_sum"], 750)


if __name__ == "__main__":
    unittest.main()

