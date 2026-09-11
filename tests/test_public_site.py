import pytest

from app import create_app


@pytest.fixture
def public_app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'test', 'DEMO': False})


def test_public_business_pages_are_available_without_login(public_app):
    app = public_app
    client = app.test_client()
    for path in ('/about', '/privacy', '/terms', '/sms-consent', '/donation-policy'):
        response = client.get(path)
        assert response.status_code == 200
        assert b'Synccos Inc.' in response.data


def test_public_pages_support_all_locales(public_app):
    app = public_app
    client = app.test_client()
    expected = {'en': b'Yazory helps families', 'he': 'יעזורי מסייעת'.encode(),
                'yi': 'יעזורי העלפט משפחות'.encode()}
    for language, text in expected.items():
        client.get(f'/language/{language}?next=/about')
        response = client.get('/about')
        assert response.status_code == 200
        assert text in response.data


def test_public_policy_links_are_present(public_app):
    app = public_app
    response = app.test_client().get('/about')
    for path in (b'/privacy', b'/terms', b'/sms-consent', b'/donation-policy'):
        assert path in response.data
    assert b'support@synccos.com' in response.data


def test_sms_pages_include_carrier_disclosures(public_app):
    client = public_app.test_client()
    consent = client.get('/sms-consent').text
    privacy = client.get('/privacy').text
    terms = client.get('/terms').text
    assert 'Do you agree to receive SMS messages from Yazory?' in consent
    assert 'STOP to opt out' in consent and 'HELP' in consent
    assert 'do not share mobile numbers or SMS consent' in privacy
    assert 'Message and data rates may apply' in terms
    for page in (consent, privacy, terms):
        assert 'Yoel Bochner' in page
        assert 'sole proprietor' in page
        assert 'Yazory software platform' in page
