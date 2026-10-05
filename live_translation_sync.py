"""Keep approved Yiddish translations fresh in a running deployment.

Each web process polls the Google Sheet in the background. Failures are ignored so
translation infrastructure can never take the application down.
"""

from __future__ import annotations

import logging
import os
import threading
import time

log = logging.getLogger(__name__)


def refresh_once() -> int:
    from translation_sheet import approved_yiddish, read_rows
    import translations

    wording, _ = approved_yiddish(read_rows())
    for source, yiddish in wording.items():
        entry = translations.CATALOG.get(source)
        if entry is not None:
            entry["yi"] = yiddish
        extra = translations._EXTRA.get(source)
        if extra is not None:
            extra["yi"] = yiddish
    return len(wording)


def install(app) -> None:
    """Start one resilient Sheet refresh loop in each production web process."""
    if app.config.get("TESTING"):
        return
    if not (
        os.environ.get("GOOGLE_TRANSLATIONS_CREDENTIALS_JSON", "").strip()
        or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    ):
        app.logger.warning("Live translation refresh disabled: Google credentials are not configured.")
        return

    interval = max(60, int(os.environ.get("TRANSLATION_REFRESH_SECONDS", "300") or "300"))

    def worker():
        while True:
            try:
                count = refresh_once()
                log.info("Refreshed %s Yiddish translations from Google Sheets.", count)
            except Exception:
                log.exception("Could not refresh translations from Google Sheets; keeping current wording.")
            time.sleep(interval)

    threading.Thread(target=worker, name="translation-sheet-refresh", daemon=True).start()
