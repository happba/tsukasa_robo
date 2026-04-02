from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class AlertsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="alerts-start", description="Enable alerting for upcoming schedule slots.")
    async def start_alerts(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        minutes_before: app_commands.Range[int, 1, 180],
    ) -> None:
        self.bot.alert_service.mark_setting(
            guild_id=str(interaction.guild_id),
            channel_id=str(channel.id),
            minutes_before=minutes_before,
            enabled=True,
        )
        self.bot.alert_service.start(self.bot)
        await interaction.response.send_message(
            f"Alerts enabled for {channel.mention} {minutes_before} minutes before each slot.",
        )

    @app_commands.command(name="alerts-stop", description="Disable alerts for this server.")
    async def stop_alerts(self, interaction: discord.Interaction) -> None:
        self.bot.alert_service.mark_setting(
            guild_id=str(interaction.guild_id),
            channel_id=str(interaction.channel_id),
            minutes_before=15,
            enabled=False,
        )
        await interaction.response.send_message("Alerts disabled for this server.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AlertsCog(bot))
