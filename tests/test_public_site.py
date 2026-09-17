from app_entry import create_app
import pytest
from werkzeug.exceptions import NotFound



@pytest.fixture
def public_app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'test', 'DEMO': False})


def test_database_diagnostic_is_disabled_by_default(public_app):
    with public_app.test_request_context('/admin/db-diagnostic'):
        with pytest.raises(NotFound):
            public_app.view_functions['live_db_diagnostic']()


def test_public_business_pages_are_available_without_login(public_app):
    app = public_app
    client = app.test_client()
    for path in ('/', '/about', '/how-it-works', '/trust', '/apply', '/support',
                 '/privacy', '/terms', '/sms-consent', '/donation-policy'):
        response = client.get(path)
        assert response.status_code == 200
        assert b'Yazory' in response.data


def test_public_pages_support_all_locales(public_app):
    app = public_app
    client = app.test_client()
    expected = {'en': b'Yazory helps cover the financial gap',
                'he': 'יעזורו מסייעת להשלים את החסר'.encode(),
                'yi': 'יעזורו העלפט דעקן דעם חסרון'.encode()}
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
    assert b'info@yaazory.org' in response.data
    assert b'2 Stonegate Dr. Suite 422, Monroe, NY 10950' in response.data
    assert b'href="/login"' in response.data
    assert b'href="/applicant/login"' in response.data
    assert b'href="/donor/login"' in response.data
    assert b'Applicant login' in response.data
    assert b'Donor login' in response.data
    assert b'Staff access' in response.data


def test_public_landing_explains_fund_trust_and_family_privacy(public_app):
    client = public_app.test_client()
    home = client.get('/').text
    trust = client.get('/trust').text
    assert 'dependable payment every two weeks' in home
    assert 'Only actual transaction fees' in home
    assert 'does not deduct an administrative percentage' in trust
    assert 'represented only by that number' in trust


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
        assert 'Synccos Inc.' in page
        assert 'Yazory software platform' in page
