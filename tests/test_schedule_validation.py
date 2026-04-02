from __future__ import annotations

import unittest
from unittest.mock import Mock

from tsukasa_bot.services.schedule_service import ScheduleService


class ScheduleValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ScheduleService(
            repository=Mock(),
            google=Mock(),
            profile_service=Mock(),
            timezone_name="America/Chicago",
        )

    def test_parse_time_range_returns_clear_message_for_invalid_format(self) -> None:
        with self.assertRaisesRegex(ValueError, r"Time range must use `HH-HH` format"):
            self.service.parse_time_range("abc")

    def test_parse_time_range_returns_clear_message_for_invalid_hours(self) -> None:
        with self.assertRaisesRegex(ValueError, r"Time range must use `HH-HH` format"):
            self.service.parse_time_range("24-25")


if __name__ == "__main__":
    unittest.main()
