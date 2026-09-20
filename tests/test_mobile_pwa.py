import json
from pathlib import Path

import pytest

from app_entry_intake import create_app


@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH',
                'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'test-only',
    })


@pytest.fixture
def client(app):
    return app.test_client()


def test_manifest_is_installable_and_branded(client):
    response = client.get('/static/manifest.webmanifest')
    assert response.status_code == 200
    manifest = json.loads(response.get_data(as_text=True))
    assert manifest['name'] == 'Yazory Family Support'
    assert manifest['short_name'] == 'Yazory'
    assert manifest['start_url'] == manifest['scope'] == '/'
    assert manifest['display'] == 'standalone'
    assert {icon['sizes'] for icon in manifest['icons']} >= {'192x192', '512x512'}
    assert client.get('/static/pwa-icon-512.png').status_code == 200


def test_service_worker_has_root_scope_but_only_caches_static_assets(client):
    client.application.config['DEMO'] = False
    response = client.get('/static/service-worker.js')
    assert response.status_code == 200
    assert response.headers['Service-Worker-Allowed'] == '/'
    assert response.headers['Cache-Control'] in {'no-cache', 'no-store'}
    script = response.get_data(as_text=True)
    assert "request.method!=='GET'" in script
    assert "request.mode==='navigate'" in script
    assert "url.pathname.startsWith('/static/')" in script
    assert "caches.match(request)" in script
    assert 'offline' not in script.casefold()


def test_staff_shell_has_accessible_mobile_navigation_and_pwa_metadata(client):
    html = client.get('/login').get_data(as_text=True)
    assert 'rel="manifest"' in html
    assert 'apple-mobile-web-app-capable' in html
    assert 'viewport-fit=cover' in html
    assert 'data-nav-open' in html
    assert 'data-nav-close' in html
    assert 'aria-controls="workspace-navigation"' in html
    assert '/static/mobile-app.js' in html


def test_rtl_staff_shell_keeps_mobile_contract(client):
    with client.session_transaction() as session:
        session['language'] = 'he'
    html = client.get('/login').get_data(as_text=True)
    assert '<html lang="he" dir="rtl">' in html
    assert 'data-nav-open' in html
    assert 'rel="manifest"' in html


def test_standalone_shells_share_pwa_metadata(client):
    for path in ('/', '/about', '/applicant/login', '/donor/login', '/apply'):
        response = client.get(path, follow_redirects=True)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'rel="manifest"' in html, path
        assert 'viewport-fit=cover' in html, path


def test_mobile_accessibility_contracts_are_present():
    css = Path('static/style.css').read_text()
    pages = Path('static/pages.js').read_text()
    assert 'env(safe-area-inset-' in css
    assert 'prefers-reduced-motion:reduce' in css.replace(' ', '')
    assert 'min-height:44px' in css.replace(' ', '')
    assert 'table[data-mobile-cards=true]' in css
    assert "event.key==='Escape'" in pages.replace(' ', '')
    assert "event.key!=='Tab'" in pages.replace(' ', '')
    assert 'sidebar.inert=' in pages
    assert "table.dataset.mobileCards='true'" in pages