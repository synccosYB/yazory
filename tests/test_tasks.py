from werkzeug.security import generate_password_hash

from app import StaffTask, create_app
from app_original import StaffUser, db


def make_app():
    app = create_app({
        'TESTING': True,
        'DEMO': False,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'task-test-secret',
    })
    with app.app_context():
        admin = StaffUser(email='admin@example.test', name='Admin',
                          password_hash=generate_password_hash('password'),
                          role='organization_admin')
        collector = StaffUser(email='collector@example.test', name='Collector',
                              password_hash=generate_password_hash('password'),
                              role='fundraiser')
        outsider = StaffUser(email='outside@example.test', name='Outside',
                             password_hash=generate_password_hash('password'),
                             role='office_employee')
        db.session.add_all([admin, collector, outsider])
        db.session.commit()
    return app


def login(client, email):
    with client.session_transaction() as session:
        session['user_id'] = db.session.scalar(
            db.select(StaffUser.id).where(StaffUser.email == email))
        session['csrf'] = 'test-csrf'


def test_admin_assigns_task_and_subtask_and_assignee_updates_status():
    app = make_app()
    admin_client = app.test_client()
    with app.app_context():
        login(admin_client, 'admin@example.test')
        collector_id = db.session.scalar(
            db.select(StaffUser.id).where(StaffUser.email == 'collector@example.test'))
    response = admin_client.post('/tasks', data={
        'csrf': 'test-csrf', 'title': 'Call five supporters',
        'assigned_to': collector_id, 'priority': 'High', 'due_date': '2026-09-12',
    })
    assert response.status_code == 302
    with app.app_context():
        task = db.session.scalar(db.select(StaffTask).where(
            StaffTask.title == 'Call five supporters'))
        task_id = task.id
        assert task.assignee.email == 'collector@example.test'
    page = admin_client.get(f'/tasks/{task_id}')
    assert page.status_code == 200
    assert b'Add a subtask' in page.data

    response = admin_client.post(f'/tasks/{task_id}/subtasks', data={
        'csrf': 'test-csrf', 'title': 'Prepare call list',
        'assigned_to': collector_id, 'priority': 'Normal', 'due_date': '2026-09-11',
    })
    assert response.status_code == 302
    with app.app_context():
        subtask = db.session.scalar(db.select(StaffTask).where(
            StaffTask.parent_id == task_id))
        subtask_id = subtask.id

    collector_client = app.test_client()
    with app.app_context():
        login(collector_client, 'collector@example.test')
    assert collector_client.get('/tasks').status_code == 200
    assert collector_client.get(f'/tasks/{subtask_id}').status_code == 200
    assert collector_client.post(f'/tasks/{subtask_id}/status', data={
        'csrf': 'test-csrf', 'status': 'Completed'}).status_code == 302
    with app.app_context():
        assert db.session.get(StaffTask, subtask_id).status == 'Completed'


def test_staff_cannot_view_someone_elses_task_or_assign_work():
    app = make_app()
    admin_client = app.test_client()
    with app.app_context():
        login(admin_client, 'admin@example.test')
        collector_id = db.session.scalar(
            db.select(StaffUser.id).where(StaffUser.email == 'collector@example.test'))
    admin_client.post('/tasks', data={
        'csrf': 'test-csrf', 'title': 'Private assignment',
        'assigned_to': collector_id, 'priority': 'Normal',
    })
    with app.app_context():
        task_id = db.session.scalar(db.select(StaffTask.id).where(
            StaffTask.title == 'Private assignment'))
        outsider_id = db.session.scalar(db.select(StaffUser.id).where(
            StaffUser.email == 'outside@example.test'))
    outsider = app.test_client()
    with app.app_context():
        login(outsider, 'outside@example.test')
    assert outsider.get(f'/tasks/{task_id}').status_code == 403
    assert outsider.post('/tasks', data={
        'csrf': 'test-csrf', 'title': 'Unauthorized',
        'assigned_to': outsider_id, 'priority': 'Normal'}).status_code == 403
