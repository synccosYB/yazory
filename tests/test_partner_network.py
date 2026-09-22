import pytest

from app import Askan, Audit, Family, SupporterProfile, db
from app_entry import create_app
from partner_network import (CaseCoordination, OrganizationAskan,
                             PartnerCommunication, PartnerContact,
                             PartnerOrganization)


def post(client, path, data):
    client.get('/')
    with client.session_transaction() as session:
        csrf = session['csrf']
    return client.post(path, data={**data, 'csrf': csrf})


@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH',
                'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
                       'SECRET_KEY': 'test-only'})


@pytest.fixture
def client(app):
    return app.test_client()


def test_partner_data_center_coordination_and_communications(app, client):
    added = post(client, '/partner-network/organizations', {
        'name': 'Refuah Helpline', 'category': 'Medical',
        'phone': '845-555-1000', 'email': 'intake@refuah.example',
        'services': 'Medical guidance and specialist referrals',
        'exclusions': 'Household bills',
        'communities': ['Monsey / Spring Valley', 'New Square'],
        'geographic_area': ['Rockland County', 'New York State']})
    assert added.status_code == 302

    with app.app_context():
        org = db.session.scalar(db.select(PartnerOrganization).where(
            PartnerOrganization.name == 'Refuah Helpline'))
        family = db.session.scalar(db.select(Family).order_by(Family.id))
        org_id, family_id = org.id, family.id
        assert org.communities == 'Monsey / Spring Valley, New Square'
        assert org.geographic_area == 'Rockland County, New York State'

    edit_page = client.get(f'/partner-network/organizations/{org_id}/edit')
    assert edit_page.status_code == 200
    assert b'Edit organization' in edit_page.data
    edited = post(client, f'/partner-network/organizations/{org_id}/edit', {
        'name': 'Refuah Helpline', 'category': 'Medical',
        'phone': '845-555-2000', 'email': 'office@refuah.example',
        'website': 'https://refuah.example',
        'communities': ['Monsey / Spring Valley', 'New Square'],
        'geographic_area': ['Rockland County'],
        'services': 'Medical guidance and case navigation',
        'relationship_status': 'New'})
    assert edited.status_code == 302
    with app.app_context():
        org = db.session.get(PartnerOrganization, org_id)
        assert org.phone == '845-555-2000'
        assert org.email == 'office@refuah.example'
        assert org.services == 'Medical guidance and case navigation'

    assert post(client, f'/partner-network/organizations/{org_id}/contacts', {
        'name': 'Medical Intake', 'title': 'Case coordinator',
        'cell_phone': '845-555-1212', 'email': 'medical@refuah.example',
        'preferred_method': 'SMS', 'is_intake': '1'}).status_code == 302
    assert post(client, f'/partner-network/organizations/{org_id}/askonim', {
        'askan_name': 'Reb Helper', 'askan_phone': '845-555-1313',
        'askan_email': 'helper@example.com', 'role': 'Medical liaison',
        'relationship_type': 'Official role', 'strength': 'Strong'}).status_code == 302

    with app.app_context():
        askan = db.session.scalar(db.select(Askan).where(Askan.name == 'Reb Helper'))
        contact = db.session.scalar(db.select(PartnerContact).where(
            PartnerContact.organization_id == org_id))
        assert db.session.scalar(db.select(OrganizationAskan).where(
            OrganizationAskan.askan_id == askan.id))
        askan_id, contact_id = askan.id, contact.id

    assert post(client, f'/families/{family_id}/coordination', {
        'organization_id': str(org_id), 'need': 'Medical guidance',
        'askan_id': str(askan_id), 'contact_id': str(contact_id),
        'status': 'Introduction needed', 'next_action': 'Make introduction',
        'follow_up_on': '2026-09-25'}).status_code == 302

    assert post(client, f'/partner-network/organizations/{org_id}/message/email', {
        'recipient_key': f'contact:{contact_id}', 'family_id': str(family_id),
        'subject': 'Family referral', 'body': 'Please coordinate this referral.'}).status_code == 302
    assert post(client, f'/partner-network/organizations/{org_id}/message/sms', {
        'recipient_key': f'askan:{askan_id}', 'family_id': str(family_id),
        'body': 'Please call the medical coordinator.'}).status_code == 302

    with app.app_context():
        coordination = db.session.scalar(db.select(CaseCoordination).where(
            CaseCoordination.family_id == family_id))
        messages = db.session.scalars(db.select(PartnerCommunication).order_by(
            PartnerCommunication.id)).all()
        assert coordination.status == 'Introduction needed'
        assert [message.channel for message in messages] == ['email', 'sms']
        assert all(message.family_id == family_id for message in messages)
        assert db.session.scalar(db.select(db.func.count()).select_from(Audit).where(
            Audit.family_id == family_id)) >= 3



def test_new_askan_does_not_match_an_unrelated_blank_email_and_can_be_removed(app, client):
    with app.app_context():
        org = PartnerOrganization(name='Test Partner', category='Other')
        unrelated = Askan(name='Unrelated Askan', phone='845-000-0001', email='')
        db.session.add_all((org, unrelated))
        db.session.commit()
        org_id, unrelated_id = org.id, unrelated.id

    response = post(client, f'/partner-network/organizations/{org_id}/askonim', {
        'askan_name': 'Correct Askan',
        'askan_phone': '845-000-0002',
        'askan_email': '',
        'relationship_type': 'Personal contact'})
    assert response.status_code == 302

    with app.app_context():
        correct = db.session.scalar(db.select(Askan).where(
            Askan.name == 'Correct Askan'))
        link = db.session.scalar(db.select(OrganizationAskan).where(
            OrganizationAskan.organization_id == org_id))
        assert correct is not None
        assert link.askan_id == correct.id
        assert link.askan_id != unrelated_id
        link_id = link.id

    removed = post(
        client,
        f'/partner-network/organizations/{org_id}/askonim/{link_id}/remove',
        {})
    assert removed.status_code == 302

    with app.app_context():
        assert db.session.get(OrganizationAskan, link_id) is None
        assert db.session.get(Askan, unrelated_id) is not None
        assert db.session.scalar(db.select(Askan).where(
            Askan.name == 'Correct Askan')) is not None


def test_organization_contact_can_be_added_to_askan_directory_without_duplicates(app, client):
    with app.app_context():
        org = PartnerOrganization(name='Yom Tov Partner', category='Other')
        contact = PartnerContact(
            organization=org, name='Meir Eli Goldberger',
            title='Community coordinator', cell_phone='845-555-1414',
            email='meir@example.org')
        db.session.add_all((org, contact))
        db.session.commit()
        org_id, contact_id = org.id, contact.id

    path = f'/partner-network/organizations/{org_id}/contacts/{contact_id}/askan'
    assert post(client, path, {}).status_code == 302
    assert post(client, path, {}).status_code == 302

    with app.app_context():
        askonim = db.session.scalars(db.select(Askan).where(
            Askan.name == 'Meir Eli Goldberger')).all()
        assert len(askonim) == 1
        links = db.session.scalars(db.select(OrganizationAskan).where(
            OrganizationAskan.organization_id == org_id,
            OrganizationAskan.askan_id == askonim[0].id)).all()
        assert len(links) == 1
        assert links[0].role == 'Community coordinator'

    page = client.get(f'/partner-network/organizations/{org_id}')
    assert b'Open askan profile' in page.data

def test_standalone_askan_can_be_added_and_filtered_before_any_connection(app, client):
    response = post(client, '/partner-network/askonim', {
        'name': 'Meir Eli Goldberger', 'phone': '845-555-1414',
        'email': 'meir@example.org', 'community': 'Monroe',
        'expertise': 'Yom Tov assistance', 'preferred_method': 'Phone'})
    assert response.status_code == 302

    with app.app_context():
        askan = db.session.scalar(db.select(Askan).where(
            Askan.name == 'Meir Eli Goldberger'))
        assert askan is not None
        assert askan.families == []
        assert askan.organization_links == []
        assert askan.network_profile.expertise == 'Yom Tov assistance'
        shared_person = db.session.scalar(db.select(SupporterProfile).where(
            SupporterProfile.name == 'Meir Eli Goldberger'))
        assert shared_person is not None
        assert shared_person.phone == '845-555-1414'

    page = client.get('/partner-network?askan_connection=unconnected&askan_q=Goldberger')
    assert page.status_code == 200
    assert b'Meir Eli Goldberger' in page.data
    assert b'Not connected yet' in page.data

    duplicate = post(client, '/partner-network/askonim', {
        'name': 'Duplicate', 'phone': '845-555-1414'})
    assert duplicate.status_code == 409


def test_partner_network_is_visible_in_all_locales(client):
    for language in ('en', 'he', 'yi'):
        client.get(f'/language/{language}?next=/partner-network')
        page = client.get('/partner-network')
        assert page.status_code == 200
        assert 'partner-network' in page.text or 'ארג' in page.text


def test_partner_network_metric_cards_open_separate_directory_views_even_when_zero(client):
    page = client.get('/partner-network')

    assert page.status_code == 200
    assert 'href="/partner-network?view=organizations"' in page.text
    assert 'href="/partner-network?view=askonim"' in page.text
    assert 'href="/partner-network?view=followups"' in page.text

    organizations = client.get('/partner-network?view=organizations')
    assert '#coordination-follow-ups,#askonim-directory{display:none}' in organizations.text
    assert 'class="active"' in organizations.text

    askonim = client.get('/partner-network?view=askonim')
    assert '#coordination-follow-ups,#organization-directory' in askonim.text

    followups = client.get('/partner-network?view=followups')
    assert '#organization-directory,#askonim-directory' in followups.text
    assert 'No follow-ups are due.' in followups.text
