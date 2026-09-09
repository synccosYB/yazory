from pathlib import Path

import pytest
from flask import session
from app import Family, FamilyPhone, create_app, db


@pytest.fixture
def app(monkeypatch):
    for key in ['APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'test'})


def test_family_form_labels_phone_as_applicant_home_phone():
    template = Path('templates/family_form.html').read_text()
    assert "data-applicant-phone-list" in template
    assert "data-add-phone" in template
    assert 'name="phone"' in template


def test_applicant_home_phone_translations(app):
    from translations import translate

    with app.test_request_context('/'):
        session['language'] = 'yi'
        assert translate('Applicant home phone') == 'היים טעלעפאן פונעם אפליקאנט'
        session['language'] = 'he'
        assert translate('Applicant home phone') == 'טלפון הבית של הפונה'


def test_multiple_applicant_home_phones_are_saved(app):
    client = app.test_client()
    client.get('/families/new')
    with client.session_transaction() as user_session:
        csrf = user_session['csrf']
    response = client.post('/families/new', data={
        'csrf': csrf,
        'name': 'Phone household',
        'phone': ['845-111-1111', '845-222-2222'],
    })
    assert response.status_code == 302
    with app.app_context():
        family = db.session.scalar(db.select(Family).where(Family.name == 'Phone household'))
        assert family.phone == '845-111-1111'
        phones = db.session.scalars(db.select(FamilyPhone).where(
            FamilyPhone.family_id == family.id).order_by(FamilyPhone.id)).all()
        assert [row.phone for row in phones] == ['845-111-1111', '845-222-2222']
