from app_entry import create_app


def make_app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL',
                'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({
        'TESTING': True,
        'DEMO': False,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'throttle-tests',
    })


def csrf(client):
    client.get('/login')
    with client.session_transaction() as browser_session:
        return browser_session['csrf']


def test_staff_login_is_durably_throttled(monkeypatch):
    client = make_app(monkeypatch).test_client()
    token = csrf(client)
    for _ in range(8):
        assert client.post('/login', data={
            'csrf': token, 'email': 'missing@example.test', 'password': 'wrong',
        }).status_code == 200
    assert client.post('/login', data={
        'csrf': token, 'email': 'missing@example.test', 'password': 'wrong',
    }).status_code == 429


def test_reset_and_supporter_links_have_separate_limits(monkeypatch):
    client = make_app(monkeypatch).test_client()
    token = csrf(client)
    for path in ('/forgot-password', '/donor/login'):
        for _ in range(3):
            assert client.post(path, data={
                'csrf': token, 'email': 'missing@example.test',
            }).status_code == 302
        assert client.post(path, data={
            'csrf': token, 'email': 'missing@example.test',
        }).status_code == 429
