from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from tsukasa_bot.services.errors import GoogleWorkspaceError
from tsukasa_bot.services.skill_service import calculate_skill_multiplier, calculate_skill_sum


class RegisterModal(discord.ui.Modal, title="Register Project Sekai Profile"):
    nickname = discord.ui.TextInput(label="Nickname", required=True, max_length=32)
    role = discord.ui.TextInput(label="Role (h or r)", required=True, max_length=1)
    power = discord.ui.TextInput(label="Power", required=True, max_length=12)
    skills = discord.ui.TextInput(
        label="5 skills separated by spaces",
        placeholder="150 150 150 150 150",
        required=True,
        max_length=64,
    )

    def __init__(self, cog: "ProfileCog") -> None:
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            skills = [int(value) for value in self.skills.value.split()]
            if len(skills) != 5:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Enter exactly 5 integer skill values separated by spaces.",
            )
            return

        try:
            result = self.cog.bot.profile_service.register_profile(
                guild_id=str(interaction.guild_id),
                user_id=str(interaction.user.id),
                nickname=self.nickname.value.strip(),
                role=self.role.value.strip(),
                power=self.power.value.strip(),
                skills=skills,
            )
        except (GoogleWorkspaceError, ValueError) as exc:
            await interaction.response.send_message(str(exc))
            return

        verb = "Updated" if result.updated else "Registered"
        await interaction.response.send_message(
            f"{verb} profile for {result.nickname}.\n"
            f"Role: {result.role}\n"
            f"Power: {result.power}\n"
            f"Skill sum: {result.skill_sum}\n"
            f"ISV: {result.skill_multiplier:.2f}",
        )


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="register", description="Register or update your Project Sekai profile.")
    async def register(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RegisterModal(self))

    @app_commands.command(name="rename-profile", description="Rename your registered nickname.")
    async def rename_profile(self, interaction: discord.Interaction, nickname: str) -> None:
        try:
            old_name = self.bot.profile_service.rename_profile(
                guild_id=str(interaction.guild_id),
                user_id=str(interaction.user.id),
                new_nickname=nickname.strip(),
            )
        except (GoogleWorkspaceError, ValueError) as exc:
            await interaction.response.send_message(str(exc))
            return

        await interaction.response.send_message(
            f"Renamed `{old_name}` to `{nickname}`.",
        )

    @app_commands.command(name="isv", description="Calculate the Project Sekai skill sum and multiplier.")
    async def isv(
        self,
        interaction: discord.Interaction,
        leader: int,
        member_1: int,
        member_2: int,
        member_3: int,
        member_4: int,
    ) -> None:
        skills = [leader, member_1, member_2, member_3, member_4]
        total = calculate_skill_sum(skills)
        multiplier = calculate_skill_multiplier(skills)
        await interaction.response.send_message(
            f"Skill sum: {total}\nISV: {multiplier:.2f}\nIn-game bonus: {int((multiplier - 1) * 100)}%",
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfileCog(bot))
