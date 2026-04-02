from __future__ import annotations

from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands


@dataclass(frozen=True)
class HelpSection:
    title: str
    emoji: str
    summary: str
    accent: discord.Color
    commands: list[tuple[str, str]]


HELP_SECTIONS: dict[str, HelpSection] = {
    "overview": HelpSection(
        title="Tsukasa Bot Help",
        emoji="✨",
        summary="Quick access to Google Sheets setup, profile tools, schedule signups, and alerts.",
        accent=discord.Color.gold(),
        commands=[
            ("/help", "Open this interactive help menu."),
            ("/sheet-create", "Create the Google Sheet used by this server."),
            ("/register", "Register or update your Project Sekai profile."),
            ("/schedule-create", "Generate schedule rows for the next 1 to 14 days."),
            ("/isv", "Calculate skill sum and ISV publicly in the channel."),
        ],
    ),
    "profiles": HelpSection(
        title="Profiles",
        emoji="🪪",
        summary="Manage player registration details used by the sheet and schedule tools.",
        accent=discord.Color.blue(),
        commands=[
            ("/register", "Open a modal to register or update nickname, role, power, and 5 skills."),
            ("/rename-profile <nickname>", "Rename your registered nickname across the profile and schedule sheets."),
            ("/isv <leader> <member_1> <member_2> <member_3> <member_4>", "Calculate skill sum, ISV, and in-game bonus."),
        ],
    ),
    "sheets": HelpSection(
        title="Google Sheets",
        emoji="📄",
        summary="Create, share, and remove the spreadsheet connected to this Discord server.",
        accent=discord.Color.green(),
        commands=[
            ("/sheet-create", "Create the server spreadsheet with `profiles` and `schedule` tabs."),
            ("/sheet-grant-access", "Open a modal to grant writer access to a Google account email."),
            ("/sheet-delete", "Delete the linked Google Sheet and clear saved metadata."),
        ],
    ),
    "schedule": HelpSection(
        title="Schedule",
        emoji="📅",
        summary="Generate time slots, join them, leave them, and render the result as an image.",
        accent=discord.Color.orange(),
        commands=[
            ("/schedule-create <days>", "Generate schedule rows for the requested number of upcoming days."),
            ("/schedule-add <time_range> [day_offset]", "Add yourself to a time range. `day_offset` defaults to `t`."),
            ("/schedule-remove <time_range> [day_offset]", "Remove yourself from a time range."),
            ("/schedule-view [day_offset]", "Render one day's schedule as an image."),
        ],
    ),
    "alerts": HelpSection(
        title="Alerts",
        emoji="🔔",
        summary="Configure reminder posts for upcoming schedule slots.",
        accent=discord.Color.red(),
        commands=[
            ("/alerts-start <channel> <minutes_before>", "Enable reminders in a channel before each slot."),
            ("/alerts-stop", "Disable schedule reminders for this server."),
        ],
    ),
}


class HelpCategorySelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label=section.title,
                value=key,
                description=section.summary[:100],
                emoji=section.emoji,
                default=(key == "overview"),
            )
            for key, section in HELP_SECTIONS.items()
        ]
        super().__init__(placeholder="Choose a help category", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, HelpView):
            return

        selected = self.values[0]
        view.selected_key = selected
        for option in self.options:
            option.default = option.value == selected

        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class HelpView(discord.ui.View):
    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=300)
        self.author_id = author_id
        self.selected_key = "overview"
        self.add_item(HelpCategorySelect())

    def build_embed(self) -> discord.Embed:
        section = HELP_SECTIONS[self.selected_key]
        embed = discord.Embed(
            title=f"{section.emoji} {section.title}",
            description=section.summary,
            color=section.accent,
        )
        for command_name, description in section.commands:
            embed.add_field(name=command_name, value=description, inline=False)
        embed.set_footer(text="Use the dropdown to switch sections.")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Open `/help` yourself to browse the menu.",
                ephemeral=True,
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Browse the bot's commands in an interactive menu.")
    async def help_command(self, interaction: discord.Interaction) -> None:
        view = HelpView(interaction.user.id)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
