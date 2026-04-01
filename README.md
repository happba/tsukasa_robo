# tsukasa_robo

Discord bot for Project Sekai event scheduling backed by Google Sheets.

## Features

- Slash commands and modals for registration and sheet access
- Google Sheets and Drive integration through a dedicated service layer
- SQLite metadata storage for guild sheet mappings, profiles, alerts, and access audits
- Schedule signup, removal, rendering, and alerting
- ISV calculator

## Required environment variables

- `DISCORD_TOKEN`
- `GOOGLE_SERVICE_ACCOUNT_FILE`
- `METADATA_DB_PATH` (optional, defaults to `data/tsukasa_robo.db`)
- `BOT_TIMEZONE` (optional, defaults to `America/New_York`)
- `DEFAULT_SHEET_TITLE` (optional)

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m tsukasa_bot
```

## Tests

```bash
python -m unittest discover -s tests
```
