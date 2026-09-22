from pathlib import Path
import tomllib


def test_published_deployment_migrates_database_before_starting_server():
    config = tomllib.loads(Path('.replit').read_text())
    command = config['deployment']['run'][-1]

    migration = 'python -m flask --app app_entry_intake init-db'
    server = "gunicorn --bind 0.0.0.0:${PORT:-5000}"
    assert migration in command
    assert server in command
    assert command.index(migration) < command.index(server)
    assert 'init-db &&' in command
