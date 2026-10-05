import sys
import types

import live_translation_sync


def test_refresh_once_updates_catalog_and_extra(monkeypatch):
    fake_sheet = types.SimpleNamespace(
        read_rows=lambda: [["header"]],
        approved_yiddish=lambda rows: ({"Hello": "שלום", "Extra": "אידיש"}, []),
    )
    fake_translations = types.SimpleNamespace(
        CATALOG={"Hello": {"yi": "old"}, "Extra": {"yi": "old"}},
        _EXTRA={"Extra": {"yi": "old"}},
    )
    monkeypatch.setitem(sys.modules, "translation_sheet", fake_sheet)
    monkeypatch.setitem(sys.modules, "translations", fake_translations)

    assert live_translation_sync.refresh_once() == 2
    assert fake_translations.CATALOG["Hello"]["yi"] == "שלום"
    assert fake_translations.CATALOG["Extra"]["yi"] == "אידיש"
    assert fake_translations._EXTRA["Extra"]["yi"] == "אידיש"


def test_install_does_not_start_thread_during_tests(monkeypatch):
    started = []
    monkeypatch.setattr(live_translation_sync.threading.Thread, "start", lambda self: started.append(True))
    app = types.SimpleNamespace(
        config={"TESTING": True},
        logger=types.SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    live_translation_sync.install(app)

    assert started == []
