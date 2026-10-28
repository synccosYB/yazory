from datetime import date, datetime

import pytest
from flask import template_rendered
from app_entry import create_app
from app import (db, Family, Contact, Receipt, Audit, CharityCampaign,
                 CharityDonor, CharityDonation, StaffUser, FamilyAssignment)
from werkzeug.security import generate_password_hash


@pytest.fixture
def app(tmp_path, monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'DEMO': True, 'SECRET_KEY': 'report-test',
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "report.db"}'})


def render_context(app, url):
    contexts = []
    def capture(sender, template, context, **extra):
        if template.name == 'family_print.html':
            contexts.append(context)
    with template_rendered.connected_to(capture, app):
        response = app.test_client().get(url)
    assert response.status_code == 200
    return response, contexts[-1]


def seed_payments(app):
    with app.app_context():
        family = db.session.get(Family, 1)
        contact = family.contacts[0]
        contact.status = 'Paid'
        contact.phone = '8455550142'
        db.session.add(Receipt(family_id=1, contact_id=contact.id,
                               amount_cents=4250, received_on=date(2026, 9, 2), reference='MANUAL-42'))
        campaign = CharityCampaign(family_id=1, external_id='campaign', key_env='TEST_KEY',
                                   label='Campaign', currency='USD')
        db.session.add(campaign); db.session.flush()
        donor = CharityDonor(campaign_id=campaign.id, identity='donor', name='Imported donor',
                             email='', phone='', address='', contact_id=contact.id)
        db.session.add(donor); db.session.flush()
        db.session.add(CharityDonation(campaign_id=campaign.id, donor_id=donor.id,
            external_id='IMPORT-500', amount_cents=50000, net_cents=48000,
            donation_time=datetime(2026, 10, 1, 2, 0), anonymous=False,
            subscription=False, team='', notes='Imported payment'))
        db.session.add(Audit(family_id=1, actor='Staff', action='UNIQUE-AUDIT-EVENT'))
        db.session.commit()


def test_report_uses_profile_totals_and_includes_imports(app):
    seed_payments(app)
    response, context = render_context(app, '/families/1/print')
    assert context['funds']['collected'] == 52250
    assert context['funds']['gross_collected'] == 54250
    assert context['funds']['collection_fees'] == 2000
    assert context['received'] == 52250
    assert len(context['payments']) == 2
    assert not context['contact_summary']['unlinked_paid']
    assert 'IMPORT-500' in response.text and 'MANUAL-42' in response.text
    assert 'UNIQUE-AUDIT-EVENT' not in response.text
    assert '$522.50' in app.test_client().get('/families/1').text
    assert 'UNIQUE-AUDIT-EVENT' in app.test_client().get('/families/1/print?include_activity=1').text
    assert 'UNIQUE-AUDIT-EVENT' in app.test_client().get('/families/1/print?section=activity').text


def test_filters_do_not_change_case_totals_and_use_eastern_dates(app):
    seed_payments(app)
    response, context = render_context(app, '/families/1/print?section=donations&q=IMPORT-500&date_from=2026-09-30&date_to=2026-09-30')
    assert context['received'] == 48000
    assert context['funds']['collected'] == 52250
    assert len(context['payments']) == 1
    assert context['payments'][0]['received_on'] == date(2026, 9, 30)
    assert '09/30/2026' in response.text
    assert 'MANUAL-42' not in response.text
    assert not context['contact_summary']['unlinked_paid']  # Checks all dates, not filtered rows.


def test_paid_status_is_not_a_payment_and_zero_is_not_a_pledge(app):
    with app.app_context():
        contact = db.session.get(Family, 1).contacts[0]
        contact.status = 'Paid'; contact.monthly_cents = 50000
        db.session.add(Contact(family_id=1, name='<script>unsafe</script>', relationship='Friend',
                               status='To contact', monthly_cents=0))
        db.session.commit()
    response, context = render_context(app, '/families/1/print')
    assert len(context['contact_summary']['unlinked_paid']) == 1
    assert context['funds']['collected'] == 0
    assert 'Payment records need review' in response.text
    assert 'No amount recorded' in response.text
    assert '<script>unsafe</script>' not in response.text
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in response.text


def test_workflow_pledges_are_authoritative_for_print_and_profile(app, monkeypatch):
    monkeypatch.setitem(app.extensions['workflows'], 'enforced', lambda: True)
    monkeypatch.setitem(app.extensions['workflows'], 'monthly_pledged', lambda fid: 12345)
    monkeypatch.setitem(app.extensions['workflows'], 'financials', lambda fid: {'available': 0})
    response, context = render_context(app, '/families/1/print')
    assert context['pledged'] == 12345
    assert '$123.45' in response.text
    assert '$123.45' in app.test_client().get('/families/1').text


@pytest.mark.parametrize('locale,label,direction', [
    ('en', 'Case contacts', 'ltr'), ('he', 'אנשי קשר בתיק', 'rtl'),
    ('yi', 'קאנטאקטן פון דער משפחה', 'rtl')])
def test_locales_and_bidirectional_values(app, locale, label, direction):
    seed_payments(app)
    client = app.test_client()
    client.get('/language/' + locale)
    page = client.get('/families/1/print').text
    assert f'dir="{direction}"' in page
    assert label in page
    assert '<bdi dir="ltr" class="report-phone">(845) 555-0142</bdi>' in page
    assert 'yazory-logo-corrected.png' in page


def test_family_report_permissions_and_read_only_behavior(app):
    with app.app_context():
        family = Family(name='Other household')
        staff = StaffUser(email='family@example.test', password_hash=generate_password_hash('test-password'), role='family_admin')
        fundraiser = StaffUser(email='fundraiser@example.test', password_hash=generate_password_hash('test-password'), role='fundraiser')
        db.session.add_all([family, staff, fundraiser]); db.session.flush()
        db.session.add(FamilyAssignment(family_id=1, staff_user_id=staff.id))
        db.session.add(FamilyAssignment(family_id=1, staff_user_id=fundraiser.id))
        db.session.commit()
        staff_id, fundraiser_id, other_id = staff.id, fundraiser.id, family.id
        before = (db.session.query(Receipt).count(), db.session.query(Audit).count())
    app.config['DEMO'] = False
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = staff_id
    assert client.get('/families/1/print').status_code == 200
    assert client.get(f'/families/{other_id}/print').status_code == 403
    with client.session_transaction() as session:
        session['user_id'] = fundraiser_id
    assert client.get('/families/1/print').status_code == 403
    with app.app_context():
        assert before == (db.session.query(Receipt).count(), db.session.query(Audit).count())
