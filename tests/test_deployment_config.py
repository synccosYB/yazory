from pathlib import Path
import runpy
import tomllib

from werkzeug.security import generate_password_hash

from app_entry_intake import create_app


def test_published_deployment_opens_port_without_blocking_on_migrations():
    config = tomllib.loads(Path('.replit').read_text())
    command = config['deployment']['run'][-1]

    server = "gunicorn --bind 0.0.0.0:${PORT:-5000}"
    assert server in command
    assert 'init-db' not in command
    assert 'exec gunicorn' in command


def test_server_has_capacity_for_requests_during_provider_waits():
    settings = runpy.run_path('gunicorn.conf.py')
    assert settings['workers'] >= 2
    assert settings['worker_class'] == 'gthread'
    assert settings['threads'] >= 4
    assert settings['timeout'] >= 60

    config = tomllib.loads(Path('.replit').read_text())
    commands = [config['run'], config['deployment']['run'][-1]]
    commands.extend(task.get('args', '')
                    for workflow in config['workflows']['workflow']
                    for task in workflow['tasks']
                    if task['task'] == 'shell.exec')
    assert all('gunicorn' in command for command in commands)


def test_worker_boot_does_not_connect_to_database(monkeypatch, tmp_path):
    monkeypatch.delenv('APP_ENV', raising=False)
    database_file = tmp_path / 'not-initialized.db'
    create_app({
        'DEMO': False,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{database_file}',
        'ADMIN_EMAIL': 'owner@example.test',
        'ADMIN_PASSWORD_HASH': generate_password_hash('temporary-test-password'),
    })
    assert not database_file.exists()


def test_anonymous_gets_do_not_read_workflow_policy(monkeypatch):
    monkeypatch.delenv('APP_ENV', raising=False)
    app = create_app({
        'TESTING': True, 'DEMO': False,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'test-secret',
    })

    def unexpected_policy_read():
        raise AssertionError('Anonymous GET should not read workflow policy')

    app.extensions['workflows']['enforced'] = unexpected_policy_read
    client = app.test_client()
    assert client.get('/robots.txt').status_code == 200
    assert client.get('/').status_code == 200
