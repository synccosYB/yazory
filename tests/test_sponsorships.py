from datetime import datetime
from io import BytesIO
import re

from app_entry_intake import create_app
from app_original import Family, db
from application_intake import AssistanceApplication
from sponsorships import CaseSponsorship, MonthlySponsorship, PAGE_SLOTS


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
        'csrf': csrf(client), 'month': month, 'fund_name': 'קרן Acme', 'company_name': 'Acme Foods',
        'donor_name': 'Mr. Donor', 'memorial_one': 'פלוני בן פלוני',
        'memorial_two': 'פלונית בת פלוני', 'contact_name': 'Office',
        'dedication_one_prefix': 'לע״נ', 'dedication_two_prefix': 'לזכות',
        'memorial_three': 'הצלחה פאר די משפחה', 'dedication_three_prefix': 'לזכות',
        'contact_phone': '8455551212', 'contact_email': 'office@example.com',
        'website_url': 'https://acme.example',
        'amount': '1200.00', 'paid': '600.00', 'status': 'Published', 'notes': 'Test',
        'logo': (BytesIO(b'fake-png-for-test'), 'logo.png'),
    })
    assert response.status_code == 302
    with app.app_context():
        row = db.session.scalar(db.select(MonthlySponsorship))
        assert row.amount_cents == 120000 and row.paid_cents == 60000
    overview = client.get('/')
    assert 'Acme Foods' in overview.text and 'פלוני בן פלוני' in overview.text
    banner = re.search(
        r'<div class="monthly-sponsor-memorial"[^>]*>(.*?)</div>',
        overview.text, re.DOTALL)
    assert banner and 'לע״נ פלוני בן פלוני' in banner.group(1)
    assert 'לזכות פלונית בת פלוני' in banner.group(1)
    assert 'לזכות הצלחה פאר די משפחה' in banner.group(1)
    assert 'href="https://acme.example"' in overview.text
    public_overview = client.get('/about').text
    assert 'Our sponsors' in public_overview
    assert 'לע״נ פלוני בן פלוני' in public_overview
    assert 'לזכות פלונית בת פלוני' in public_overview
    assert 'לזכות הצלחה פאר די משפחה' in public_overview


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


def test_page_sponsor_banner_shows_three_dedications_with_saved_prefixes():
    app = make_app()
    client = app.test_client()
    month = datetime.now().strftime('%Y-%m')
    with app.app_context():
        db.session.add(MonthlySponsorship(
            month=month, page_key='overview', fund_name='קרן Example',
            company_name='Example Company', donor_name='Example Donor',
            memorial_one='ראשון', dedication_one_prefix='לע״נ',
            memorial_two='שני', dedication_two_prefix='לזכות',
            memorial_three='שלישי', dedication_three_prefix='לזכות',
            status='Published', logo_data=b'logo', logo_mime='image/png'))
        db.session.commit()

    page = client.get('/').text
    banner = re.search(
        r'<div class="monthly-sponsor-memorial"[^>]*>(.*?)</div>',
        page, re.DOTALL)
    assert banner
    assert 'לע״נ ראשון' in banner.group(1)
    assert 'לזכות שני' in banner.group(1)
    assert 'לזכות שלישי' in banner.group(1)


def test_unpublished_sponsor_is_not_displayed():
    app = make_app()
    client = app.test_client()
    month = datetime.now().strftime('%Y-%m')
    with app.app_context():
        db.session.add(MonthlySponsorship(month=month, page_key='overview',
                                         company_name='Hidden Sponsor', status='Confirmed'))
        db.session.commit()
    assert 'Hidden Sponsor' not in client.get('/').text


def test_published_sponsor_without_website_still_appears_on_public_pages():
    app = make_app()
    client = app.test_client()
    month = datetime.now().strftime('%Y-%m')
    with app.app_context():
        db.session.add(MonthlySponsorship(
            month=month, page_key='overview', company_name='Existing Sponsor',
            status='Published', logo_data=b'logo', logo_mime='image/png'))
        db.session.commit()
    page = client.get('/about').text
    assert 'Existing Sponsor' in page
    assert 'public-sponsor-logo' in page


def test_public_sponsors_use_bounded_carousel_and_have_directory():
    app = make_app()
    client = app.test_client()
    month = datetime.now().strftime('%Y-%m')
    with app.app_context():
        for index in range(5):
            db.session.add(MonthlySponsorship(
                month=month, page_key=PAGE_SLOTS[index][0],
                company_name=f'Sponsor {index}', donor_name=f'Donor {index}',
                fund_name=f'Fund {index}', status='Published',
                logo_data=b'logo', logo_mime='image/png',
                memorial_one=f'Dedication {index}',
            ))
        db.session.commit()

    home = client.get('/about').text
    assert 'data-sponsor-carousel' in home
    assert 'data-page-size="4"' in home
    assert '/sponsors' in home
    assert 'View dedication' in home

    directory = client.get('/sponsors')
    assert directory.status_code == 200
    assert 'public-sponsor-directory' in directory.text
    assert all(f'Sponsor {index}' in directory.text for index in range(5))


def test_sponsor_can_be_published_without_a_website():
    app = make_app()
    client = app.test_client()
    month = datetime.now().strftime('%Y-%m')
    response = client.post('/sponsorships/overview', data={
        'csrf': csrf(client), 'month': month, 'fund_name': 'קרן Example',
        'company_name': 'Example Company', 'donor_name': 'Example Donor',
        'memorial_one': '', 'memorial_two': '', 'contact_name': '',
        'contact_phone': '', 'contact_email': '', 'website_url': '',
        'amount': '0', 'paid': '0', 'status': 'Published', 'notes': '',
        'logo': (BytesIO(b'logo'), 'logo.png'),
    })
    assert response.status_code == 302


def test_publish_error_names_only_the_missing_sponsor_fields():
    app = make_app()
    client = app.test_client()
    month = datetime.now().strftime('%Y-%m')
    response = client.post('/sponsorships/overview', data={
        'csrf': csrf(client), 'month': month, 'fund_name': 'קרן Example',
        'company_name': '', 'donor_name': 'Example Donor',
        'contact_email': '', 'amount': '0', 'paid': '0',
        'status': 'Published', 'notes': '',
    })
    assert response.status_code == 400
    assert 'Cannot publish this sponsorship. Missing:' in response.text
    assert 'Company name' in response.text
    assert 'Company logo' in response.text
    assert 'Donor name' not in response.text


def test_case_sponsor_is_separate_and_appears_only_on_its_family_pages():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        family = db.session.scalar(db.select(Family).order_by(Family.id))
        family_id = family.id
    response = client.post(f'/families/{family_id}/sponsorship', data={
        'csrf': csrf(client), 'fund_name': 'קרן חסד למשפחה',
        'start_month': datetime.now().strftime('%Y-%m'), 'end_month': '',
        'company_name': 'Case Company', 'donor_name': 'Case Donor',
        'memorial_one': 'ראובן בן יעקב', 'memorial_two': '',
        'contact_name': 'Office', 'contact_phone': '8455551212',
        'contact_email': 'case@example.com', 'amount': '2500', 'paid': '2500',
        'status': 'Published', 'notes': '',
        'logo': (BytesIO(b'case-logo'), 'case.png'),
    })
    assert response.status_code == 302
    with app.app_context():
        row = db.session.scalar(db.select(CaseSponsorship))
        assert row.family_id == family_id and row.balance_cents == 0
        assert row.fund_name == 'קרן חסד למשפחה'
    profile = client.get(f'/families/{family_id}')
    report = client.get(f'/families/{family_id}/print')
    assert 'Case Company' in profile.text and 'קרן חסד למשפחה' in profile.text
    assert 'Case Company' in report.text and 'ראובן בן יעקב' in report.text
    assert 'Case Company' not in client.get('/expenses').text


def test_sent_application_gets_fund_name():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        application = AssistanceApplication(public_token='fund-name-token', status='Sent',
                                            applicant_name='Example Family',
                                            fund_name='קרן משפחת Example')
        db.session.add(application)
        db.session.commit()
        application_id = application.id
    assert 'קרן משפחת Example' in client.get('/apply/fund-name-token').text
    assert 'קרן משפחת Example' in client.get(f'/applications/{application_id}/print').text
    assert 'קרן ____________________' in client.get('/applications/blank/print').text


def test_application_does_not_generate_a_fund_from_applicant_name():
    app = make_app()
    client = app.test_client()
    with app.app_context():
        application = AssistanceApplication(public_token='auto-fund-token', status='Sent')
        db.session.add(application)
        db.session.commit()
    response = client.post('/apply/auto-fund-token', data={
        'csrf': csrf(client), 'applicant_name': 'Auto Family', 'action': 'save',
    })
    assert response.status_code == 200
    with app.app_context():
        saved = db.session.scalar(db.select(AssistanceApplication).where(
            AssistanceApplication.public_token == 'auto-fund-token'))
        assert saved.fund_name == ''
