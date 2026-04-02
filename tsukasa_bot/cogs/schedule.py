from __future__ import annotations

import os

import discord
from discord import app_commands
from discord.ext import commands

from tsukasa_bot.services.errors import GoogleWorkspaceError
from tsukasa_bot.services.schedule_service import ScheduleSlot


class ScheduleSlotSelect(discord.ui.Select):
    def __init__(self, cog: "ScheduleCog", guild_id: str, user_id: str, day_offset: str, slots: list[ScheduleSlot]) -> None:
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.day_offset = day_offset
        options = []
        for slot in slots[:25]:
            unix_timestamp = int(slot.start_time.timestamp())
            status = f"{len(slot.assignments)} joined" if slot.assignments else "Open"
            options.append(
                discord.SelectOption(
                    label=slot.time_range,
                    value=slot.time_range,
                    description=status,
                )
            )
        super().__init__(
            placeholder="Select one or more slots",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            date_str = self.cog.bot.schedule_service.add_user_to_slots(
                self.guild_id,
                self.user_id,
                self.day_offset,
                list(self.values),
            )
        except (GoogleWorkspaceError, ValueError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        selected = ", ".join(self.values)
        view = self.view
        if isinstance(view, ScheduleSlotPickerView):
            for child in view.children:
                child.disabled = True
        await interaction.response.edit_message(
            content=f"Added you to {selected} on {date_str}.",
            embed=None,
            view=view,
        )


class ScheduleSlotPickerView(discord.ui.View):
    def __init__(self, cog: "ScheduleCog", guild_id: str, user_id: str, day_offset: str, slots: list[ScheduleSlot]) -> None:
        super().__init__(timeout=300)
        self.message: discord.Message | None = None
        self.user_id = int(user_id)
        self.add_item(ScheduleSlotSelect(cog, guild_id, user_id, day_offset, slots))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Open `/schedule-add` yourself to claim slots.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            await self.message.edit(view=self)


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

    def _build_slot_picker_embed(self, date_str: str, slots: list[ScheduleSlot]) -> discord.Embed:
        embed = discord.Embed(
            title=f"Schedule Slots for {date_str}",
            description="Choose one or more slots below to add yourself. Discord will localize the timestamps automatically.",
            color=discord.Color.blurple(),
        )

        lines = []
        for slot in slots:
            unix_timestamp = int(slot.start_time.timestamp())
            joined = ", ".join(slot.assignments) if slot.assignments else "Open"
            lines.append(f"`{slot.time_range}` • <t:{unix_timestamp}:F>\nCurrent: {joined}")

        if lines:
            for index in range(0, len(lines), 5):
                title = "Available Slots" if index == 0 else "More Slots"
                embed.add_field(name=title, value="\n\n".join(lines[index:index + 5]), inline=False)
        else:
            embed.add_field(name="Available Slots", value="No schedule rows exist for that date yet.", inline=False)
        embed.set_footer(text="Select multiple slots from the dropdown.")
        return embed

    @app_commands.command(name="schedule-add", description="Open an interactive slot picker for a specific date.")
    async def schedule_add(
        self,
        interaction: discord.Interaction,
        day_offset: str = "t",
    ) -> None:
        try:
            date_str, slots = self.bot.schedule_service.get_slots_for_offset(str(interaction.guild_id), day_offset)
        except (GoogleWorkspaceError, ValueError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        if not slots:
            await interaction.response.send_message(
                f"No schedule exists for {date_str}. Run `/schedule-create` first.",
                ephemeral=True,
            )
            return

        view = ScheduleSlotPickerView(self, str(interaction.guild_id), str(interaction.user.id), day_offset, slots)
        await interaction.response.send_message(
            embed=self._build_slot_picker_embed(date_str, slots),
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()

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
