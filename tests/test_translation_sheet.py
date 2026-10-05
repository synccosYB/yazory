import json

from translation_sheet import (
    _credentials_info,
    _sheet_range,
    approved_yiddish,
    discover_sources,
    translation_key,
)


def test_only_current_and_approved_wording_reaches_production():
    rows = [
        ['Translation key', 'English source', 'Production Yiddish', 'Proposed Yiddish', 'Status'],
        ['ui.current', 'Current label', 'יעצטיג', '', 'Current'],
        ['ui.draft', 'Draft label', 'אלט', 'נייע פארשלאג', 'Draft'],
        ['ui.approved', 'Approved label', 'אלט', 'באשטעטיגט', 'Approved'],
        ['ui.missing', 'Missing label', '', '', 'Needs translation'],
    ]
    selected, promotions = approved_yiddish(rows)
    assert selected == {'Current label': 'יעצטיג', 'Approved label': 'באשטעטיגט'}
    assert promotions == [(4, 'באשטעטיגט')]


def test_spreadsheet_errors_never_reach_production():
    rows = [
        ['Translation key', 'English source', 'Production Yiddish', 'Proposed Yiddish', 'Status'],
        ['ui.bad-production', 'Name', '#NAME?', '', 'Current'],
        ['ui.bad-proposal', 'Save', 'היט אפ', '#REF!', 'Approved'],
        ['ui.bad-source', '#VALUE!', 'טעקסט', '', 'Current'],
    ]
    selected, promotions = approved_yiddish(rows)
    assert selected == {'Save': 'היט אפ'}
    assert promotions == []


def test_translation_keys_are_stable_and_unique():
    used = {'ui.hello.world'}
    assert translation_key('Hello world!', used) == 'ui.hello.world.2'
    assert translation_key('Hello world!', used) == 'ui.hello.world.3'


def test_discovers_python_and_template_literals(tmp_path):
    (tmp_path / 'page.py').write_text("label = _('Python label')\n", encoding='utf-8')
    templates = tmp_path / 'templates'
    templates.mkdir()
    (templates / 'page.html').write_text("{{ _('Template label') }}", encoding='utf-8')
    assert discover_sources(tmp_path) == {
        'Python label': 'page.py',
        'Template label': 'templates/page.html',
    }


def test_existing_replit_credential_secret_is_supported(monkeypatch):
    monkeypatch.delenv('GOOGLE_TRANSLATIONS_CREDENTIALS_JSON', raising=False)
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
    monkeypatch.setenv('GOOGLE_SERVICE_ACCOUNT_JSON', '{"type":"service_account","project_id":"test"}')
    assert _credentials_info()['project_id'] == 'test'


def test_configured_sheet_tab_is_used(monkeypatch):
    monkeypatch.setenv('TRANSLATION_SHEET_TAB', "Yiddish Review")
    assert _sheet_range('A:J') == "'Yiddish Review'!A:J"


def test_runtime_override_file_is_valid_object():
    payload = json.loads((__import__('pathlib').Path(__file__).parents[1] / 'translation_sheet_overrides.json').read_text())
    assert isinstance(payload, dict)
