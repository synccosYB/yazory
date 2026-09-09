from datetime import date

import pdfplumber
import app_original as core_module

from app import ApplicantPayout, CheckBankAccount, Family, StripeRecipient, create_app, db


def payout_app(tmp_path, name):
    return create_app({'TESTING': True, 'DEMO': True,
                       'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / name}'})


def test_check_create_download_and_status_lifecycle(tmp_path):
    app = payout_app(tmp_path, 'payouts.sqlite')
    client = app.test_client()
    client.get('/payouts')
    with client.session_transaction() as session:
        csrf = session['csrf']
    saved = client.post('/payouts/check-accounts', data={
        'csrf': csrf, 'routing_number': '021000021',
        'account_number': '1234567890', 'account_name': 'Operating',
        'bank_name': 'Test National Bank', 'next_check_number': '00125'}, follow_redirects=True)
    assert saved.status_code == 200
    assert '1234567890' not in saved.text
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        family.status = 'Active'
        family.address, family.city, family.state, family.zip_code = (
            '12 Main Street', 'Monroe', 'NY', '10950')
        db.session.commit()
        family_id = family.id
        bank_account_id = db.session.scalar(db.select(CheckBankAccount.id))

    response = client.post('/payouts/checks', data={
        'csrf': csrf, 'family_id': family_id, 'payee_name': 'Test Applicant',
        'amount': '1234.56', 'check_bank_account_id': bank_account_id,
        'check_date': '2026-09-09', 'memo': 'Family support',
        'recipient_message': 'With best wishes from Yazory.'}, follow_redirects=True)
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
    assert 'Test National Bank' in text
    assert f'Case number: YZ-{family_id:04d}' in text
    assert 'Check sequence for this case: 1' in text
    assert 'With best wishes from Yazory.' in text
    assert 'Family support payout' not in text

    with app.app_context():
        payout = db.session.scalar(db.select(ApplicantPayout))
        assert payout.check_number == '00125'
        assert payout.check_date == date(2026, 9, 9)
        assert payout.check_bank_account_name == 'Operating'
        assert db.session.get(CheckBankAccount, bank_account_id).next_check_number == '00126'
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
        bank = CheckBankAccount(name='Operating', bank_name='Test Bank',
            routing_number_encrypted=core_module.encrypt_api_key('021000021', app.config['SECRET_KEY']),
            account_number_encrypted=core_module.encrypt_api_key('1234567890', app.config['SECRET_KEY']),
            account_last4='7890', next_check_number='10')
        db.session.add(bank)
        db.session.commit()
        bank_account_id = bank.id
    response = client.post('/payouts/checks', data={
        'csrf': csrf, 'family_id': family_id, 'payee_name': 'יואל באכנער',
        'amount': '10', 'check_bank_account_id': bank_account_id, 'check_date': '2026-09-09'})
    assert response.status_code == 400


def test_each_bank_account_has_an_independent_check_sequence(tmp_path):
    app = payout_app(tmp_path, 'multiple-accounts.sqlite')
    client = app.test_client()
    client.get('/payouts')
    with client.session_transaction() as session:
        csrf = session['csrf']
    for name, account in (('Operating', '1234567890'), ('Assistance', '9876543210')):
        response = client.post('/payouts/check-accounts', data={
            'csrf': csrf, 'account_name': name, 'bank_name': f'{name} Bank',
            'routing_number': '021000021', 'account_number': account,
            'next_check_number': '00100'})
        assert response.status_code == 302
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        family.status, family.address = 'Active', '1 Main Street'
        accounts = db.session.scalars(db.select(CheckBankAccount).order_by(CheckBankAccount.id)).all()
        db.session.commit()
        family_id, account_ids = family.id, [row.id for row in accounts]
    for account_id in account_ids:
        response = client.post('/payouts/checks', data={
            'csrf': csrf, 'family_id': family_id, 'check_bank_account_id': account_id,
            'payee_name': 'Test Applicant', 'amount': '10', 'check_date': '2026-09-09'})
        assert response.status_code == 302
    with app.app_context():
        payouts = db.session.scalars(db.select(ApplicantPayout).order_by(ApplicantPayout.id)).all()
        assert [row.check_number for row in payouts] == ['00100', '00100']
        assert [row.next_check_number for row in db.session.scalars(
            db.select(CheckBankAccount).order_by(CheckBankAccount.id)).all()] == ['00101', '00101']
        assert [row.prior_case_check_count for row in payouts] == [0, 1]


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


def test_only_voided_checks_can_be_deleted(tmp_path):
    app = payout_app(tmp_path, 'delete-check.sqlite')
    client = app.test_client()
    client.get('/payouts')
    with client.session_transaction() as session:
        csrf = session['csrf']
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        payout = ApplicantPayout(family_id=family.id, method='check', amount_cents=100,
            payee_name='Test Applicant', mailing_address='1 Main St', check_number='9',
            check_date=date.today(), status='created')
        db.session.add(payout)
        db.session.commit()
        payout_id = payout.id
    assert client.post(f'/payouts/{payout_id}/delete', data={'csrf': csrf}).status_code == 400
    voided = client.post(f'/payouts/{payout_id}/status', data={
        'csrf': csrf, 'status': 'voided'})
    assert voided.status_code == 302
    assert voided.location.endswith('/payouts?panel=3')
    deleted = client.post(f'/payouts/{payout_id}/delete', data={'csrf': csrf})
    assert deleted.status_code == 302
    assert deleted.location.endswith('/payouts?panel=3')
    with app.app_context():
        assert db.session.get(ApplicantPayout, payout_id) is None


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
