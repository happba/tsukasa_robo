from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from tsukasa_bot.services.errors import GoogleWorkspaceError


class GrantAccessModal(discord.ui.Modal, title="Grant Google Sheet Access"):
    email = discord.ui.TextInput(label="Google account email", required=True, max_length=255)

    def __init__(self, cog: "SheetCog", interaction: discord.Interaction) -> None:
        super().__init__()
        self.cog = cog
        self.origin_interaction = interaction

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.handle_grant_access(interaction, self.email.value.strip())


class SheetCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="sheet-create", description="Create the Google Sheet backing this server.")
    async def create_sheet(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        existing = self.bot.metadata_repository.get_guild_sheet(guild_id)
        if existing:
            await interaction.followup.send(
                f"A Google Sheet already exists for this server: {existing['sheet_url']}",
                ephemeral=True,
            )
            return

        created = self.bot.google_workspace.create_guild_spreadsheet(self.bot.app_config.default_sheet_title)
        self.bot.metadata_repository.upsert_guild_sheet(
            guild_id=guild_id,
            spreadsheet_id=created["spreadsheet_id"],
            sheet_url=created["sheet_url"],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await interaction.followup.send(
            f"Google Sheet created successfully.\n{created['sheet_url']}",
            ephemeral=True,
        )

    @app_commands.command(name="sheet-grant-access", description="Grant spreadsheet writer access to an email address.")
    async def grant_access(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(GrantAccessModal(self, interaction))

    async def handle_grant_access(self, interaction: discord.Interaction, email: str) -> None:
        guild_id = str(interaction.guild_id)
        sheet = self.bot.metadata_repository.get_guild_sheet(guild_id)
        if not sheet:
            await interaction.response.send_message(
                "No Google Sheet is configured for this server yet.",
                ephemeral=True,
            )
            return

        try:
            verification = self.bot.google_workspace.grant_spreadsheet_access(sheet["spreadsheet_id"], email)
            self.bot.metadata_repository.add_grant_access_audit(
                guild_id=guild_id,
                spreadsheet_id=sheet["spreadsheet_id"],
                email=email,
                status="success",
                detail=verification["permission_id"],
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        except GoogleWorkspaceError as exc:
            self.bot.metadata_repository.add_grant_access_audit(
                guild_id=guild_id,
                spreadsheet_id=sheet["spreadsheet_id"],
                email=email,
                status="failed",
                detail=str(exc),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(
            f"Granted {verification['role']} access to {verification['email']}.",
            ephemeral=True,
        )

    @app_commands.command(name="sheet-delete", description="Delete this server's Google Sheet.")
    async def delete_sheet(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        sheet = self.bot.metadata_repository.get_guild_sheet(guild_id)
        if not sheet:
            await interaction.followup.send("No Google Sheet is configured for this server yet.", ephemeral=True)
            return

        try:
            self.bot.google_workspace.delete_spreadsheet(sheet["spreadsheet_id"])
        except GoogleWorkspaceError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        self.bot.metadata_repository.delete_guild_sheet(guild_id)
        await interaction.followup.send("The Google Sheet was deleted.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SheetCog(bot))
