from datetime import datetime
from io import BytesIO

from app_entry_intake import create_app
from app_original import db
from application_intake import AssistanceApplication
from sponsorships import MonthlySponsorship, PAGE_SLOTS


def make_app():
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'sponsor-test', 'DEMO': True})


def csrf(client):
    client.get('/sponsorships')
    with client.session_transaction() as saved:
        return saved['csrf']


def test_workflow_lists_every_page_and_saves_monthly_sponsor():
    app = make_app()
    client = app.test_client()
    month = datetime.now().strftime('%Y-%m')
    page = client.get(f'/sponsorships?month={month}')
    assert page.status_code == 200
    assert page.text.count('/sponsorships/') >= len(PAGE_SLOTS)
    response = client.post('/sponsorships/overview', data={
        'csrf': csrf(client), 'month': month, 'company_name': 'Acme Foods',
        'donor_name': 'Mr. Donor', 'memorial_one': 'פלוני בן פלוני',
        'memorial_two': 'פלונית בת פלוני', 'contact_name': 'Office',
        'contact_phone': '8455551212', 'contact_email': 'office@example.com',
        'amount': '1200.00', 'paid': '600.00', 'status': 'Published', 'notes': 'Test',
        'logo': (BytesIO(b'fake-png-for-test'), 'logo.png'),
    })
    assert response.status_code == 302
    with app.app_context():
        row = db.session.scalar(db.select(MonthlySponsorship))
        assert row.amount_cents == 120000 and row.paid_cents == 60000
    overview = client.get('/')
    assert 'Acme Foods' in overview.text and 'פלוני בן פלוני' in overview.text


def test_online_and_printed_application_sponsors_are_independent():
    app = make_app()
    client = app.test_client()
    month = datetime.now().strftime('%Y-%m')
    with app.app_context():
        online = MonthlySponsorship(month=month, page_key='online_application',
                                    company_name='Online Sponsor', status='Published')
        printed = MonthlySponsorship(month=month, page_key='printed_application',
                                     company_name='Print Sponsor', status='Published')
        application = AssistanceApplication(public_token='public-test-token', status='Sent')
        db.session.add_all([online, printed, application])
        db.session.commit()
        application_id = application.id
    online_page = client.get('/apply/public-test-token')
    printed_page = client.get(f'/applications/{application_id}/print')
    assert 'Online Sponsor' in online_page.text and 'Print Sponsor' not in online_page.text
    assert 'Print Sponsor' in printed_page.text and 'Online Sponsor' not in printed_page.text
    assert 'position:fixed' in client.get('/static/sponsorships.css').text


def test_unpublished_sponsor_is_not_displayed():
    app = make_app()
    client = app.test_client()
    month = datetime.now().strftime('%Y-%m')
    with app.app_context():
        db.session.add(MonthlySponsorship(month=month, page_key='overview',
                                         company_name='Hidden Sponsor', status='Confirmed'))
        db.session.commit()
    assert 'Hidden Sponsor' not in client.get('/').text
