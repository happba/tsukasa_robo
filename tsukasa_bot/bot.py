from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from tsukasa_bot.config import AppConfig
from tsukasa_bot.repositories.metadata_repository import MetadataRepository
from tsukasa_bot.services.alert_service import AlertService
from tsukasa_bot.services.google_workspace import GoogleWorkspaceService
from tsukasa_bot.services.image_service import ScheduleImageService
from tsukasa_bot.services.profile_service import ProfileService
from tsukasa_bot.services.schedule_service import ScheduleService

LOGGER = logging.getLogger(__name__)


class TsukasaBot(commands.Bot):
    def __init__(self, app_config: AppConfig) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.guild_messages = True
        intents.message_content = True

        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.app_config = app_config
        self.metadata_repository = MetadataRepository(app_config.metadata_db_path)
        self.google_workspace = GoogleWorkspaceService(app_config.google_service_account_file)
        self.profile_service = ProfileService(self.metadata_repository, self.google_workspace)
        self.schedule_service = ScheduleService(
            self.metadata_repository,
            self.google_workspace,
            self.profile_service,
            app_config.timezone_name,
        )
        self.alert_service = AlertService(
            self.metadata_repository,
            self.schedule_service,
            self.profile_service,
        )
        self.image_service = ScheduleImageService(Path("www/fonts/NotoSansSC-Regular.ttf"))

    async def setup_hook(self) -> None:
        self.google_workspace.validate_connectivity()
        for extension in (
            "tsukasa_bot.cogs.help",
            "tsukasa_bot.cogs.sheet",
            "tsukasa_bot.cogs.profile",
            "tsukasa_bot.cogs.schedule",
            "tsukasa_bot.cogs.alerts",
        ):
            await self.load_extension(extension)
        synced = await self.tree.sync()
        LOGGER.info("Synced %s application commands", len(synced))
        if self.metadata_repository.list_enabled_alert_settings():
            self.alert_service.start(self)

    async def on_ready(self) -> None:
        LOGGER.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "unknown")
