from __future__ import annotations

import logging

from tsukasa_bot.bot import TsukasaBot
from tsukasa_bot.config import AppConfig


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = AppConfig.from_env()
    bot = TsukasaBot(config)
    bot.run(config.discord_token)


if __name__ == "__main__":
    main()

