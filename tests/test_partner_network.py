import pytest

from app import Askan, Audit, Family, db
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
        'exclusions': 'Household bills', 'communities': 'New York'})
    assert added.status_code == 302

    with app.app_context():
        org = db.session.scalar(db.select(PartnerOrganization).where(
            PartnerOrganization.name == 'Refuah Helpline'))
        family = db.session.scalar(db.select(Family).order_by(Family.id))
        org_id, family_id = org.id, family.id

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


def test_partner_network_is_visible_in_all_locales(client):
    for language in ('en', 'he', 'yi'):
        client.get(f'/language/{language}?next=/partner-network')
        page = client.get('/partner-network')
        assert page.status_code == 200
        assert 'partner-network' in page.text or 'ארג' in page.text
