from app_entry_intake import create_app
from app_original import Audit, EmailMessage, db
from application_intake import AssistanceApplication


def test_staff_can_email_a_question_to_application_requester():
    app = create_app({
        'TESTING': True, 'DEMO': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'test',
    })
    with app.app_context():
        db.create_all()
        application = AssistanceApplication(
            public_token='requester-question-token', status='Submitted',
            recipient_email='requester@example.test', applicant_name='Bochner', data={})
        db.session.add(application)
        db.session.commit()
        application_id = application.id

    client = app.test_client()
    client.get(f'/applications/{application_id}')
    with client.session_transaction() as session:
        csrf = session['csrf']
    response = client.post(
        f'/applications/{application_id}/question',
        data={'csrf': csrf, 'subject': 'Missing information',
              'message': 'Which shul does the family attend during the week?'},
        follow_redirects=True)

    assert response.status_code == 200
    assert b'Question sent to requester@example.test.' in response.data
    with app.app_context():
        message = db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.kind == 'application_question'))
        assert message.recipient == 'requester@example.test'
        assert message.subject == 'Missing information'
        assert 'Which shul' in message.text_body
        assert 'Application: YA-000001' in message.text_body
        assert message.status == 'preview'
        assert db.session.scalar(db.select(Audit).where(
            Audit.action.contains('Application question sent: YA-000001')))


def test_application_question_requires_subject_and_message():
    app = create_app({
        'TESTING': True, 'DEMO': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'test',
    })
    with app.app_context():
        db.create_all()
        application = AssistanceApplication(
            public_token='blank-question-token', status='Submitted',
            recipient_email='requester@example.test', applicant_name='Bochner', data={})
        db.session.add(application)
        db.session.commit()
        application_id = application.id

    client = app.test_client()
    client.get(f'/applications/{application_id}')
    with client.session_transaction() as session:
        csrf = session['csrf']
    response = client.post(
        f'/applications/{application_id}/question',
        data={'csrf': csrf, 'subject': '', 'message': ''}, follow_redirects=True)

    assert response.status_code == 200
    assert b'Enter a subject and message before sending.' in response.data
    with app.app_context():
        assert db.session.scalar(db.select(EmailMessage).where(
            EmailMessage.kind == 'application_question')) is None
