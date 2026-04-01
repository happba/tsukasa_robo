from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tsukasa_bot.constants import PROFILE_HEADERS, PROFILE_SHEET_NAME, SCHEDULE_HEADERS, SCHEDULE_SHEET_NAME
from tsukasa_bot.services.errors import GoogleWorkspaceError

LOGGER = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

class GoogleWorkspaceService:
    def __init__(self, service_account_file: Path) -> None:
        credentials = service_account.Credentials.from_service_account_file(
            str(service_account_file),
            scopes=SCOPES,
        )
        self.sheets = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        self.drive = build("drive", "v3", credentials=credentials, cache_discovery=False)

    def validate_connectivity(self) -> None:
        try:
            self.drive.about().get(fields="user").execute()
        except HttpError as exc:
            raise GoogleWorkspaceError(
                "Google API credentials are configured, but the bot could not reach Drive."
            ) from exc

    def create_guild_spreadsheet(self, title: str) -> dict[str, str]:
        spreadsheet = self.sheets.spreadsheets().create(
            body={"properties": {"title": title}},
            fields="spreadsheetId",
        ).execute()
        spreadsheet_id = spreadsheet["spreadsheetId"]

        self.sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {"updateSheetProperties": {"properties": {"sheetId": 0, "title": PROFILE_SHEET_NAME}, "fields": "title"}},
                    {"addSheet": {"properties": {"title": SCHEDULE_SHEET_NAME}}},
                ]
            },
        ).execute()

        self.update_values(f"{PROFILE_SHEET_NAME}!A1:F1", PROFILE_HEADERS, spreadsheet_id)
        self.update_values(f"{SCHEDULE_SHEET_NAME}!A1:J1", SCHEDULE_HEADERS, spreadsheet_id)

        return {
            "spreadsheet_id": spreadsheet_id,
            "sheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
        }

    def delete_spreadsheet(self, spreadsheet_id: str) -> None:
        try:
            self.drive.files().delete(fileId=spreadsheet_id).execute()
        except HttpError as exc:
            raise self._translate_http_error(exc, "delete spreadsheet")

    def grant_spreadsheet_access(self, spreadsheet_id: str, email: str) -> dict[str, str]:
        if not EMAIL_RE.match(email):
            raise GoogleWorkspaceError("The email address format is invalid.")

        try:
            response = self.drive.permissions().create(
                fileId=spreadsheet_id,
                body={"type": "user", "role": "writer", "emailAddress": email},
                sendNotificationEmail=False,
                fields="id,emailAddress,role",
            ).execute()
        except HttpError as exc:
            raise self._translate_http_error(exc, f"grant access to {email}")

        permission_id = response.get("id")
        verification = self.drive.permissions().get(
            fileId=spreadsheet_id,
            permissionId=permission_id,
            fields="id,emailAddress,role",
        ).execute()
        LOGGER.info("Verified Drive permission %s for %s on %s", permission_id, email, spreadsheet_id)
        return {
            "permission_id": verification["id"],
            "email": verification.get("emailAddress", email),
            "role": verification.get("role", "writer"),
        }

    def get_values(self, spreadsheet_id: str, range_name: str) -> list[list[str]]:
        result = self.sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        ).execute()
        return result.get("values", [])

    def update_values(self, range_name: str, values: list[list[Any]], spreadsheet_id: str) -> None:
        self.sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

    def append_values(self, range_name: str, values: list[list[Any]], spreadsheet_id: str) -> None:
        self.sheets.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()

    def batch_update_values(self, spreadsheet_id: str, updates: list[dict[str, Any]]) -> None:
        self.sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()

    def get_sheet_formatting(self, spreadsheet_id: str, range_name: str) -> dict[tuple[int, int], dict[str, tuple[int, int, int]]]:
        result = self.sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(data(rowData(values(userEnteredFormat(backgroundColor,textFormat)))))",
            ranges=[range_name],
        ).execute()

        color_map: dict[tuple[int, int], dict[str, tuple[int, int, int]]] = {}
        sheets = result.get("sheets", [])
        if not sheets:
            return color_map

        for row_index, row in enumerate(sheets[0].get("data", [{}])[0].get("rowData", [])):
            for col_index, cell in enumerate(row.get("values", [])):
                cell_format = cell.get("userEnteredFormat", {})
                background = cell_format.get("backgroundColor", {})
                text = cell_format.get("textFormat", {}).get("foregroundColor", {})
                color_map[(row_index, col_index)] = {
                    "background": self._to_rgb(background, default=255),
                    "text": self._to_rgb(text, default=0),
                }
        return color_map

    def _to_rgb(self, payload: dict[str, float], default: int) -> tuple[int, int, int]:
        return (
            int(payload.get("red", default / 255) * 255),
            int(payload.get("green", default / 255) * 255),
            int(payload.get("blue", default / 255) * 255),
        )

    def _translate_http_error(self, exc: HttpError, action: str) -> GoogleWorkspaceError:
        status_code = getattr(exc.resp, "status", None)
        body = ""
        if hasattr(exc, "content") and exc.content:
            body = exc.content.decode("utf-8", errors="ignore")
        lowered = body.lower()

        if status_code == 404:
            return GoogleWorkspaceError("The Google Sheet does not exist or is no longer accessible.")
        if "already has access" in lowered or "duplicate" in lowered:
            return GoogleWorkspaceError("That email address already has access to this spreadsheet.")
        if "invalid sharing request" in lowered or "cannot share" in lowered:
            return GoogleWorkspaceError(
                "Google rejected the share request. The target account may not be eligible for sharing."
            )
        if status_code == 403:
            return GoogleWorkspaceError("The service account does not have permission to perform that Google Drive action.")
        return GoogleWorkspaceError(f"Google could not {action}.")
