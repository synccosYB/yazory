"""Controlled synchronization between the translation registry and Google Sheets.

The application never reads Google at request time.  A maintainer explicitly
pushes newly discovered labels to the review sheet and pulls approved Yiddish
wording into a versioned JSON file before deployment.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path


DEFAULT_SHEET_ID = "1mP1T1v7ExJxN6zzt3A7-qGStNN9DCVOfw8sgju-VlTg"
SHEET_RANGE = "Sheet1!A:J"
OVERRIDES_PATH = Path(__file__).with_name("translation_sheet_overrides.json")
_JINJA_TRANSLATION = re.compile(r"(?:_|translate)\(\s*(['\"])(.*?)\1\s*\)")


def translation_key(source: str, used: set[str]) -> str:
    stem = re.sub(r"[^a-z0-9]+", ".", source.lower()).strip(".") or "text"
    stem = f"ui.{stem[:72].rstrip('.')}"
    candidate = stem
    suffix = 2
    while candidate in used:
        candidate = f"{stem}.{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def discover_sources(root: Path) -> dict[str, str]:
    """Return literal translatable strings and their first source location."""
    found: dict[str, str] = {}
    for path in sorted([*root.glob("*.py"), *root.glob("templates/*.html")]):
        relative = str(path.relative_to(root))
        if path.suffix == ".html":
            for match in _JINJA_TRANSLATION.finditer(path.read_text(encoding="utf-8")):
                found.setdefault(match.group(2), relative)
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name not in {"_", "translate"}:
                continue
            value = node.args[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                found.setdefault(value.value, relative)
    return found


def approved_yiddish(rows: list[list[str]]) -> tuple[dict[str, str], list[tuple[int, str]]]:
    """Select live wording and return Approved proposals needing promotion."""
    output: dict[str, str] = {}
    promotions: list[tuple[int, str]] = []
    for sheet_row, row in enumerate(rows[1:], start=2):
        padded = [*row, *([""] * (10 - len(row)))]
        source, production, proposed, status = padded[1:5]
        status = status.strip().lower()
        if status == "approved" and proposed.strip():
            production = proposed.strip()
            promotions.append((sheet_row, production))
        if status in {"current", "approved"} and source.strip() and production.strip():
            output[source.strip()] = production.strip()
    return output, promotions


def _credentials_info() -> dict:
    raw = os.environ.get("GOOGLE_TRANSLATIONS_CREDENTIALS_JSON", "").strip()
    if raw:
        return json.loads(raw)
    filename = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if filename:
        return json.loads(Path(filename).read_text(encoding="utf-8"))
    raise RuntimeError(
        "Set GOOGLE_TRANSLATIONS_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS "
        "to a service account that can edit the translation Sheet."
    )


def _session():
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_info(
        _credentials_info(), scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return AuthorizedSession(credentials)


def _sheet_id() -> str:
    return os.environ.get("GOOGLE_TRANSLATION_SHEET_ID", DEFAULT_SHEET_ID).strip()


def read_rows() -> list[list[str]]:
    response = _session().get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{_sheet_id()}/values/{SHEET_RANGE}"
    )
    response.raise_for_status()
    return response.json().get("values", [])


def _version() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def push_missing(catalog: dict[str, dict[str, str]], root: Path | None = None) -> int:
    root = root or Path(__file__).parent
    rows = read_rows()
    existing_sources = {row[1].strip() for row in rows[1:] if len(row) > 1 and row[1].strip()}
    used_keys = {row[0].strip() for row in rows[1:] if row and row[0].strip()}
    discovered = discover_sources(root)
    discovered.update({source: "translation registry" for source in catalog})
    today = date.today().isoformat()
    version = _version()
    additions = []
    for source, context in sorted(discovered.items(), key=lambda item: item[0].casefold()):
        if source in existing_sources:
            continue
        yiddish = (catalog.get(source) or {}).get("yi", "").strip()
        additions.append([
            translation_key(source, used_keys), source, yiddish, "",
            "Current" if yiddish else "Needs translation", context,
            today, today if yiddish else "", version if yiddish else "", "Registry sync",
        ])
    if not additions:
        return 0
    session = _session()
    response = session.post(
        f"https://sheets.googleapis.com/v4/spreadsheets/{_sheet_id()}/values/Sheet1!A:J:append",
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json={"majorDimension": "ROWS", "values": additions},
    )
    response.raise_for_status()
    return len(additions)


def pull_approved() -> tuple[int, int]:
    rows = read_rows()
    translations, promotions = approved_yiddish(rows)
    OVERRIDES_PATH.write_text(
        json.dumps(translations, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if promotions:
        today = date.today().isoformat()
        version = _version()
        data = []
        for row_number, wording in promotions:
            data.extend([
                {"range": f"Sheet1!C{row_number}:C{row_number}", "values": [[wording]]},
                {"range": f"Sheet1!D{row_number}:E{row_number}", "values": [["", "Current"]]},
                {"range": f"Sheet1!H{row_number}:I{row_number}", "values": [[today, version]]},
            ])
        response = _session().post(
            f"https://sheets.googleapis.com/v4/spreadsheets/{_sheet_id()}/values:batchUpdate",
            json={"valueInputOption": "USER_ENTERED", "data": data},
        )
        response.raise_for_status()
    return len(translations), len(promotions)

