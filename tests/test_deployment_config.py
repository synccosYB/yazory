from pathlib import Path
import tomllib


def test_published_deployment_opens_port_without_blocking_on_migrations():
    config = tomllib.loads(Path('.replit').read_text())
    command = config['deployment']['run'][-1]

    server = "gunicorn --bind 0.0.0.0:${PORT:-5000}"
    assert server in command
    assert 'init-db' not in command
    assert 'exec gunicorn' in command
