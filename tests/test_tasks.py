from werkzeug.security import generate_password_hash

from app import StaffTask, create_app
from app_original import Contact, Family, FamilyAssignment, StaffUser, db


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


def test_task_filters_and_open_task_ordering():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        login(client, 'admin@example.test')
        admin = db.session.scalar(db.select(StaffUser).where(
            StaffUser.email == 'admin@example.test'))
        collector = db.session.scalar(db.select(StaffUser).where(
            StaffUser.email == 'collector@example.test'))
        db.session.add_all([
            StaffTask(title='Completed item', assigned_to=admin.id,
                      created_by=admin.id, status='Completed', priority='Urgent'),
            StaffTask(title='Normal open item', assigned_to=admin.id,
                      created_by=admin.id, status='To do', priority='Normal'),
            StaffTask(title='Urgent collector item', assigned_to=collector.id,
                      created_by=admin.id, status='To do', priority='Urgent'),
        ])
        db.session.commit()
        collector_id = collector.id

    page = client.get('/tasks')
    assert page.text.index('Urgent collector item') < page.text.index('Normal open item')
    assert page.text.index('Normal open item') < page.text.index('Completed item')

    page = client.get('/tasks?status=Completed')
    assert 'Completed item' in page.text
    assert 'Normal open item' not in page.text

    page = client.get(f'/tasks?assigned_to={collector_id}&priority=Urgent')
    assert 'Urgent collector item' in page.text
    assert 'Completed item' not in page.text


def test_to_contact_automatically_creates_and_completes_one_task():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        login(client, 'admin@example.test')
        collector = db.session.scalar(db.select(StaffUser).where(
            StaffUser.email == 'collector@example.test'))
        family = Family(name='Follow-up family')
        db.session.add(family)
        db.session.flush()
        db.session.add(FamilyAssignment(
            staff_user_id=collector.id, family_id=family.id))
        db.session.commit()
        family_id = family.id
        collector_id = collector.id

    response = client.post(f'/families/{family_id}/contacts', data={
        'csrf': 'test-csrf', 'name': 'New supporter', 'phone': '8455550101',
        'relationship': 'Friend', 'status': 'To contact', 'monthly': '0',
        'pledge_frequency': 'Monthly',
    })
    assert response.status_code == 302
    with app.app_context():
        contact = db.session.scalar(db.select(Contact).where(
            Contact.name == 'New supporter'))
        task = db.session.scalar(db.select(StaffTask).where(
            StaffTask.source_contact_id == contact.id))
        assert task is not None
        assert task.assigned_to == collector_id
        assert task.status == 'To do'
        contact_id = contact.id

    # Saving the same outreach status reopens/reuses the same task.
    assert client.post(f'/contacts/{contact_id}', data={
        'csrf': 'test-csrf', 'status': 'To contact', 'monthly': '0',
        'pledge_frequency': 'Monthly',
    }).status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(StaffTask.id)).where(
            StaffTask.source_contact_id == contact_id)) == 1

    assert client.post(f'/contacts/{contact_id}', data={
        'csrf': 'test-csrf', 'status': 'Contacted', 'monthly': '0',
        'pledge_frequency': 'Monthly',
    }).status_code == 302
    with app.app_context():
        task = db.session.scalar(db.select(StaffTask).where(
            StaffTask.source_contact_id == contact_id))
        assert task.status == 'Completed'
        assert task.completed_at is not None

    assert client.post(f'/contacts/{contact_id}', data={
        'csrf': 'test-csrf', 'status': 'To contact', 'monthly': '0',
        'pledge_frequency': 'Monthly',
    }).status_code == 302
    with app.app_context():
        task_id = db.session.scalar(db.select(StaffTask.id).where(
            StaffTask.source_contact_id == contact_id))
    assert client.post(f'/tasks/{task_id}/status', data={
        'csrf': 'test-csrf', 'status': 'Completed',
    }).status_code == 302
    with app.app_context():
        assert db.session.get(Contact, contact_id).status == 'Contacted'

    assert client.post(f'/contacts/{contact_id}/delete', data={
        'csrf': 'test-csrf',
    }).status_code == 302
    with app.app_context():
        assert db.session.get(StaffTask, task_id) is None
