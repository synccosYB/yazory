import json

from translation_sheet import approved_yiddish, discover_sources, translation_key


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


def test_runtime_override_file_is_valid_object():
    payload = json.loads((__import__('pathlib').Path(__file__).parents[1] / 'translation_sheet_overrides.json').read_text())
    assert isinstance(payload, dict)
