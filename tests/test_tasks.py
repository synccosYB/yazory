from app_entry import create_app
from datetime import date
from werkzeug.security import generate_password_hash

from app import StaffTask
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


def test_overview_and_navigation_show_only_my_open_tasks():
    app = make_app()
    with app.app_context():
        admin = db.session.scalar(db.select(StaffUser).where(
            StaffUser.email == 'admin@example.test'))
        outsider = db.session.scalar(db.select(StaffUser).where(
            StaffUser.email == 'outside@example.test'))
        db.session.add_all([
            StaffTask(title='My open work', assigned_to=admin.id,
                      created_by=admin.id),
            StaffTask(title='Someone else work', assigned_to=outsider.id,
                      created_by=admin.id),
            StaffTask(title='My finished work', assigned_to=admin.id,
                      created_by=admin.id, status='Completed'),
        ])
        db.session.commit()
        client = app.test_client()
        login(client, 'admin@example.test')
        page = client.get('/')
        assert page.status_code == 200
        assert b'My open work' in page.data
        assert b'Someone else work' not in page.data
        assert b'My finished work' not in page.data
        assert b'My tasks' in page.data and b'All tasks' in page.data
        assert b'Open tasks' in page.data


def test_work_queue_combines_assignments_and_limits_each_staff_view():
    app = make_app()
    with app.app_context():
        admin = db.session.scalar(db.select(StaffUser).where(StaffUser.email == 'admin@example.test'))
        other = db.session.scalar(db.select(StaffUser).where(StaffUser.email == 'outside@example.test'))
        family = Family(name='Queue family')
        db.session.add(family)
        db.session.flush()
        db.session.add(FamilyAssignment(staff_user_id=other.id, family_id=family.id))
        db.session.add_all([
            StaffTask(title='Admin staff task', assigned_to=admin.id, created_by=admin.id),
            StaffTask(title='Other staff task', assigned_to=other.id, created_by=admin.id),
        ])
        Work = app.extensions['workflows']['models']['WorkItem']
        db.session.add_all([
            Work(kind='task', family_id=family.id, title='Admin case work',
                 owner_id=admin.id, created_by=admin.id, due=date.today(), data={}),
            Work(kind='task', family_id=family.id, title='Other case work',
                 owner_id=other.id, created_by=admin.id, due=date.today(), data={}),
        ])
        db.session.commit()
        admin_client = app.test_client()
        login(admin_client, 'admin@example.test')
        mine = admin_client.get('/work-queue').text
        assert 'Admin staff task' in mine and 'Admin case work' in mine
        assert 'Other staff task' not in mine and 'Other case work' not in mine
        all_work = admin_client.get('/work-queue?view=all').text
        assert 'Other staff task' in all_work and 'Other case work' in all_work
        other_client = app.test_client()
        login(other_client, 'outside@example.test')
        mine = other_client.get('/work-queue').text
        assert 'Other staff task' in mine and 'Other case work' in mine
        assert 'Admin staff task' not in mine and 'Admin case work' not in mine
        assert other_client.get('/work-queue?view=all').status_code == 400


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
        'csrf': 'test-csrf', 'status': 'Completed'}).status_code == 400
    with app.app_context():
        assert db.session.get(StaffTask, subtask_id).status == 'To do'
    assert collector_client.post(f'/tasks/{subtask_id}/status', data={
        'csrf': 'test-csrf', 'status': 'Completed',
        'outcome': 'Prepared the call list and sent it to the team.'}).status_code == 302
    with app.app_context():
        assert db.session.get(StaffTask, subtask_id).status == 'Completed'
        assert 'Prepared the call list' in db.session.get(StaffTask, subtask_id).outcome


def test_subtask_assigned_to_another_person_appears_in_their_work_views():
    app = make_app()
    with app.app_context():
        admin = db.session.scalar(db.select(StaffUser).where(
            StaffUser.email == 'admin@example.test'))
        staff = db.session.scalar(db.select(StaffUser).where(
            StaffUser.email == 'outside@example.test'))
        parent = StaffTask(title='Private parent plan', assigned_to=admin.id,
                           created_by=admin.id)
        db.session.add(parent)
        db.session.flush()
        child = StaffTask(title='Prepare documents', parent_id=parent.id,
                          assigned_to=staff.id, created_by=admin.id)
        db.session.add(child)
        db.session.commit()
        parent_id, child_id = parent.id, child.id

        client = app.test_client()
        login(client, 'outside@example.test')
        tasks_page = client.get('/tasks').text
        assert f'href="/tasks/{child_id}"' in tasks_page
        assert 'Prepare documents' in tasks_page
        assert 'Part of' in tasks_page and 'Private parent plan' in tasks_page
        assert f'href="/tasks/{parent_id}"' not in tasks_page
        assert 'Prepare documents' in client.get('/work-queue').text
        assert 'Prepare documents' in client.get('/').text
        detail = client.get(f'/tasks/{child_id}').text
        assert 'Private parent plan' in detail
        assert f'href="/tasks/{parent_id}"' not in detail
        assert client.get(f'/tasks/{parent_id}').status_code == 403

        admin_client = app.test_client()
        login(admin_client, 'admin@example.test')
        assert 'Prepare documents' in admin_client.get('/tasks').text
        assert 'Prepare documents' in admin_client.get('/work-queue?view=all').text


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


def test_tasks_page_is_read_only_and_explicit_repair_backfills_supporters():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        login(client, 'admin@example.test')
        admin = db.session.scalar(db.select(StaffUser).where(
            StaffUser.email == 'admin@example.test'))
        family = Family(name='Existing family')
        db.session.add(family)
        db.session.flush()
        db.session.add(FamilyAssignment(staff_user_id=admin.id, family_id=family.id))
        db.session.add_all([
            Contact(family_id=family.id, name=f'Existing supporter {number}',
                    relationship='Friend', status='To contact')
            for number in range(1, 21)
        ])
        db.session.commit()

    assert client.get('/tasks').status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(StaffTask.id)).where(
            StaffTask.source_contact_id.is_not(None))) == 0
        app.extensions['repair_page_data']()
        assert db.session.scalar(db.select(db.func.count(StaffTask.id)).where(
            StaffTask.source_contact_id.is_not(None))) == 20


def test_tasks_page_bounds_the_initial_result_set():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        login(client, 'admin@example.test')
        admin = db.session.scalar(db.select(StaffUser).where(
            StaffUser.email == 'admin@example.test'))
        db.session.add_all([
            StaffTask(title=f'Bounded task {number}', assigned_to=admin.id,
                      created_by=admin.id)
            for number in range(105)
        ])
        db.session.commit()

    page = client.get('/tasks')
    assert page.status_code == 200
    assert page.text.count('Bounded task ') == 100
    assert 'page=2' in page.text
    assert client.get('/tasks?page=2').text.count('Bounded task ') == 5


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
        'outcome': 'Spoke with supporter.', 'outreach_status': 'Contacted',
    }).status_code == 302
    with app.app_context():
        assert db.session.get(Contact, contact_id).status == 'Contacted'

    assert client.post(f'/contacts/{contact_id}/delete', data={
        'csrf': 'test-csrf',
    }).status_code == 302
    with app.app_context():
        assert db.session.get(StaffTask, task_id) is None


def test_supporter_task_verdict_does_not_claim_an_unanswered_call_was_contacted():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        login(client, 'admin@example.test')
        admin = db.session.scalar(db.select(StaffUser).where(
            StaffUser.email == 'admin@example.test'))
        family = Family(name='Outreach result family')
        db.session.add(family)
        db.session.flush()
        contact = Contact(family_id=family.id, name='Unanswered supporter',
                          relationship='Friend', status='To contact')
        db.session.add(contact)
        db.session.flush()
        task = StaffTask(title='Contact unanswered supporter',
                         source_contact_id=contact.id, family_id=family.id,
                         assigned_to=admin.id, created_by=admin.id)
        db.session.add(task)
        db.session.commit()
        task_id, contact_id = task.id, contact.id

    response = client.post(f'/tasks/{task_id}/status', data={
        'csrf': 'test-csrf', 'status': 'Completed',
        'outcome': 'Called twice; there was no answer.',
        'outreach_status': 'No answer'})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(StaffTask, task_id).status == 'Completed'
        assert db.session.get(StaffTask, task_id).outcome == 'Called twice; there was no answer.'
        assert db.session.get(Contact, contact_id).status == 'No answer'
    page = client.get(f'/tasks/{task_id}').text
    assert 'Called twice; there was no answer.' in page
    assert 'Supporter outreach result' in page
