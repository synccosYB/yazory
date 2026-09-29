from pathlib import Path
import runpy
import tomllib


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
