from __future__ import annotations


def calculate_skill_sum(skill_components: list[int]) -> int:
    return sum(skill_components)


def calculate_skill_multiplier(skill_components: list[int]) -> float:
    leader, member_1, member_2, member_3, member_4 = skill_components
    return 0.01 * ((100 + leader) + (member_1 + member_2 + member_3 + member_4) / 5)

