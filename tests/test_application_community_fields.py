from pathlib import Path

from flask import Flask

from application_intake import REVIEW_FIELDS, _data_from_form


ROOT = Path(__file__).resolve().parents[1]


COMMUNITY_FIELDS = {
    'mother_in_law_maiden_family', 'in_law_family_network', 'kehillah',
    'family_rav_phone', 'rav_gabbai', 'rav_gabbai_phone',
    'weekday_shul_rav', 'weekday_shul_gabbai', 'weekday_shul_gabbai_phone',
    'shabbos_shul_rav', 'shabbos_shul_gabbai', 'shabbos_shul_gabbai_phone',
}


def test_extended_community_fields_are_saved():
    app = Flask(__name__)
    submitted = {field: f'value for {field}' for field in COMMUNITY_FIELDS}
    with app.test_request_context('/', method='POST', data=submitted):
        saved = _data_from_form({})
    for field, value in submitted.items():
        assert saved[field] == value


def test_same_shul_copies_weekday_contacts_without_duplicate_entry():
    app = Flask(__name__)
    submitted = {
        'same_shul': 'yes', 'weekday_shul': 'Congregation Example',
        'weekday_shul_rav': 'Rabbi Example', 'weekday_shul_gabbai': 'Gabbai Example',
        'weekday_shul_gabbai_phone': '(845) 555-0100',
    }
    with app.test_request_context('/', method='POST', data=submitted):
        saved = _data_from_form({})
    assert saved['same_shul'] is True
    assert saved['shabbos_shul'] == submitted['weekday_shul']
    assert saved['shabbos_shul_rav'] == submitted['weekday_shul_rav']
    assert saved['shabbos_shul_gabbai'] == submitted['weekday_shul_gabbai']
    assert saved['shabbos_shul_gabbai_phone'] == submitted['weekday_shul_gabbai_phone']


def test_extended_community_fields_appear_online_in_review_and_on_print():
    online = (ROOT / 'templates' / 'application_form_public.html').read_text()
    printed = (ROOT / 'templates' / 'application_print.html').read_text()
    review_keys = {key for _label, key in REVIEW_FIELDS}
    for field in COMMUNITY_FIELDS:
        assert f'name="{field}"' in online
        assert f"'{field}'" in printed
        assert field in review_keys
