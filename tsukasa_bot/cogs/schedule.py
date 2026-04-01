from __future__ import annotations

import os

import discord
from discord import app_commands
from discord.ext import commands

from tsukasa_bot.services.errors import GoogleWorkspaceError


class ScheduleCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="schedule-create", description="Generate the schedule rows in the Google Sheet.")
    async def create_schedule(self, interaction: discord.Interaction, days: app_commands.Range[int, 1, 14]) -> None:
        try:
            self.bot.schedule_service.create_schedule(str(interaction.guild_id), days)
        except (GoogleWorkspaceError, ValueError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(f"Created schedule rows for {days} day(s).", ephemeral=True)

    @app_commands.command(name="schedule-add", description="Add yourself to a time range.")
    async def schedule_add(
        self,
        interaction: discord.Interaction,
        time_range: str,
        day_offset: str = "t",
    ) -> None:
        try:
            date_str = self.bot.schedule_service.add_user_to_range(
                str(interaction.guild_id),
                str(interaction.user.id),
                day_offset,
                time_range,
            )
        except (GoogleWorkspaceError, ValueError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Added you to {time_range} on {date_str}.",
            ephemeral=True,
        )

    @app_commands.command(name="schedule-remove", description="Remove yourself from a time range.")
    async def schedule_remove(
        self,
        interaction: discord.Interaction,
        time_range: str,
        day_offset: str = "t",
    ) -> None:
        try:
            date_str = self.bot.schedule_service.remove_user_from_range(
                str(interaction.guild_id),
                str(interaction.user.id),
                day_offset,
                time_range,
            )
        except (GoogleWorkspaceError, ValueError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Removed you from {time_range} on {date_str}.",
            ephemeral=True,
        )

    @app_commands.command(name="schedule-view", description="Render the daily schedule as an image.")
    async def schedule_view(self, interaction: discord.Interaction, day_offset: str = "t") -> None:
        await interaction.response.defer()
        try:
            date_str, rows, range_name = self.bot.schedule_service.get_schedule_for_offset(
                str(interaction.guild_id),
                day_offset,
            )
            if not rows:
                await interaction.followup.send(f"No schedule exists for {date_str}.", ephemeral=True)
                return
            sheet = self.bot.metadata_repository.get_guild_sheet(str(interaction.guild_id))
            colors = self.bot.google_workspace.get_sheet_formatting(sheet["spreadsheet_id"], range_name)
            image_path = self.bot.image_service.render(rows, colors)
        except (GoogleWorkspaceError, ValueError) as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        try:
            await interaction.followup.send(
                content=f"Schedule for {date_str}",
                file=discord.File(str(image_path)),
            )
        finally:
            if image_path.exists():
                os.remove(image_path)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ScheduleCog(bot))
