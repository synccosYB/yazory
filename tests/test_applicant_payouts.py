from datetime import date

import pdfplumber
import app_original as core_module

from app import ApplicantPayout, Family, StripeRecipient, create_app, db


def payout_app(tmp_path, name):
    return create_app({'TESTING': True, 'DEMO': True,
                       'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / name}'})


def test_check_create_download_and_status_lifecycle(tmp_path):
    app = payout_app(tmp_path, 'payouts.sqlite')
    client = app.test_client()
    client.get('/payouts')
    with client.session_transaction() as session:
        csrf = session['csrf']
    saved = client.post('/payouts/check-settings', data={
        'csrf': csrf, 'routing_number': '021000021',
        'account_number': '1234567890'}, follow_redirects=True)
    assert saved.status_code == 200
    assert '1234567890' not in saved.text
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        family.status = 'Active'
        family.address, family.city, family.state, family.zip_code = (
            '12 Main Street', 'Monroe', 'NY', '10950')
        db.session.commit()
        family_id = family.id

    response = client.post('/payouts/checks', data={
        'csrf': csrf, 'family_id': family_id, 'payee_name': 'Test Applicant',
        'amount': '1234.56', 'check_number': '00125',
        'check_date': '2026-09-09', 'memo': 'Family support'}, follow_redirects=True)
    assert response.status_code == 200
    assert response.mimetype == 'application/pdf'
    pdf_path = tmp_path / 'check.pdf'
    pdf_path.write_bytes(response.data)
    with pdfplumber.open(pdf_path) as pdf:
        text = pdf.pages[0].extract_text()
    assert 'Test Applicant' in text
    assert '$1,234.56' in text
    assert 'One Thousand Two Hundred Thirty-Four and 56/100 Dollars' in text
    assert '021000021' in text
    assert '1234567890' in text
    assert 'Family support payout' not in text

    with app.app_context():
        payout = db.session.scalar(db.select(ApplicantPayout))
        assert payout.check_number == '00125'
        assert payout.check_date == date(2026, 9, 9)
        payout_id = payout.id
    assert client.post(f'/payouts/{payout_id}/status', data={
        'csrf': csrf, 'status': 'mailed'}).status_code == 302
    assert client.post(f'/payouts/{payout_id}/status', data={
        'csrf': csrf, 'status': 'cleared'}).status_code == 302
    with app.app_context():
        payout = db.session.get(ApplicantPayout, payout_id)
        assert payout.status == 'cleared'
        assert payout.mailed_at and payout.cleared_at


def test_payee_must_be_english(tmp_path):
    app = payout_app(tmp_path, 'english.sqlite')
    client = app.test_client()
    client.get('/payouts')
    with client.session_transaction() as session:
        csrf = session['csrf']
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        family.status, family.address = 'Active', '1 Main Street'
        db.session.commit()
        family_id = family.id
    response = client.post('/payouts/checks', data={
        'csrf': csrf, 'family_id': family_id, 'payee_name': 'יואל באכנער',
        'amount': '10', 'check_number': '10', 'check_date': '2026-09-09'})
    assert response.status_code == 400


def test_voided_check_cannot_be_downloaded(tmp_path):
    app = payout_app(tmp_path, 'void.sqlite')
    client = app.test_client()
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        payout = ApplicantPayout(family_id=family.id, method='check', amount_cents=100,
            payee_name='Test Applicant', mailing_address='1 Main St', check_number='9',
            check_date=date.today(), status='voided')
        db.session.add(payout)
        db.session.commit()
        payout_id = payout.id
    assert client.get(f'/payouts/{payout_id}/check.pdf').status_code == 400


def test_direct_stripe_payout_is_recorded(monkeypatch, tmp_path):
    app = create_app({'TESTING': True, 'DEMO': True,
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "stripe.sqlite"}',
                      'STRIPE_SECRET_KEY': 'sk_test_yazory'})
    client = app.test_client()
    client.get('/payouts')
    with client.session_transaction() as session:
        csrf = session['csrf']
    monkeypatch.setattr(core_module, 'create_transfer',
                        lambda *_args: {'id': 'tr_applicant_1'})
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        family.status = 'Active'
        recipient = StripeRecipient(kind='family', recipient_key=str(family.id),
            family_id=family.id, name='Test Applicant', email='test@example.com',
            stripe_account_id='acct_ready', payouts_enabled=True, status='ready')
        db.session.add(recipient)
        db.session.commit()
        family_id, recipient_id = family.id, recipient.id
    response = client.post('/payouts/stripe', data={
        'csrf': csrf, 'family_id': family_id, 'recipient_id': recipient_id,
        'amount': '250.00', 'memo': 'Monthly support'})
    assert response.status_code == 302
    with app.app_context():
        payout = db.session.scalar(db.select(ApplicantPayout))
        assert payout.method == 'stripe'
        assert payout.status == 'sent'
        assert payout.stripe_reference == 'tr_applicant_1'
