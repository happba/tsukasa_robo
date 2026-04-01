from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord

from tsukasa_bot.repositories.metadata_repository import MetadataRepository
from tsukasa_bot.services.profile_service import ProfileService
from tsukasa_bot.services.schedule_service import ScheduleService

LOGGER = logging.getLogger(__name__)


class AlertService:
    def __init__(
        self,
        repository: MetadataRepository,
        schedule_service: ScheduleService,
        profile_service: ProfileService,
    ) -> None:
        self.repository = repository
        self.schedule_service = schedule_service
        self.profile_service = profile_service
        self._task: asyncio.Task | None = None
        self._sent_keys: set[str] = set()

    def start(self, bot: discord.Client) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._runner(bot))

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _runner(self, bot: discord.Client) -> None:
        while True:
            await self._tick(bot)
            await asyncio.sleep(120)

    async def _tick(self, bot: discord.Client) -> None:
        for setting in self.repository.list_enabled_alert_settings():
            guild_id = setting["guild_id"]
            upcoming = self.schedule_service.get_upcoming_assignments(guild_id, setting["minutes_before"])
            if not upcoming:
                continue
            event_time, names = upcoming
            dedupe_key = f"{guild_id}:{event_time.isoformat()}"
            if dedupe_key in self._sent_keys:
                continue

            channel = bot.get_channel(int(setting["channel_id"]))
            if channel is None:
                LOGGER.warning("Alert channel %s was not found for guild %s", setting["channel_id"], guild_id)
                continue

            mentions = []
            for name in names:
                user_id = self.profile_service.get_user_id_by_name(guild_id, name)
                if user_id:
                    mentions.append(f"<@{user_id}>")
            if mentions:
                await channel.send(
                    f"{' '.join(mentions)} Your scheduled slot starts in {setting['minutes_before']} minutes."
                )
                self._sent_keys.add(dedupe_key)

    def mark_setting(self, guild_id: str, channel_id: str, minutes_before: int, enabled: bool) -> None:
        self.repository.upsert_alert_setting(
            guild_id=guild_id,
            channel_id=channel_id,
            minutes_before=minutes_before,
            enabled=enabled,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

