from __future__ import annotations

import unittest

from tsukasa_bot.services.skill_service import calculate_skill_multiplier, calculate_skill_sum


class SkillServiceTests(unittest.TestCase):
    def test_calculate_skill_sum(self) -> None:
        self.assertEqual(calculate_skill_sum([150, 150, 150, 150, 150]), 750)

    def test_calculate_skill_multiplier(self) -> None:
        self.assertAlmostEqual(calculate_skill_multiplier([150, 150, 150, 150, 150]), 3.7)


if __name__ == "__main__":
    unittest.main()
