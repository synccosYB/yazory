from app_entry import create_app
from datetime import date

from app import ApplicantPayout, Expense, Family, Receipt, db


def test_payout_gate_uses_lower_workflow_balance(monkeypatch, tmp_path):
    from app import CheckBankAccount
    from app_original import encrypt_api_key

    app = create_app({'TESTING': True, 'DEMO': True,
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "payout-gate.sqlite"}'})
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        family.status, family.address = 'Active', '1 Main Street'
        db.session.add(Receipt(contact_id=family.contacts[0].id,
                               family_id=family.id, amount_cents=20_000,
                               received_on=date.today()))
        bank = CheckBankAccount(
            name='Test account', bank_name='Test Bank',
            routing_number_encrypted=encrypt_api_key('021000021', app.config['SECRET_KEY']),
            account_number_encrypted=encrypt_api_key('1234567890', app.config['SECRET_KEY']),
            account_last4='7890', next_check_number='10')
        db.session.add(bank)
        db.session.commit()
        family_id, bank_id = family.id, bank.id

    monkeypatch.setitem(app.extensions['workflows'], 'enforced', lambda: True)
    monkeypatch.setitem(app.extensions['workflows'], 'financials',
                        lambda _fid: {'available': 10_000})
    client = app.test_client()
    page = client.get('/payouts')
    assert '$100.00' in page.text
    with client.session_transaction() as session:
        csrf = session['csrf']
    response = client.post('/payouts/checks', data={
        'csrf': csrf, 'family_id': family_id,
        'check_bank_account_id': bank_id, 'payee_name': 'Test Applicant',
        'amount': '150', 'check_date': '2026-09-23'})
    assert response.status_code == 400
    with app.app_context():
        assert db.session.scalar(db.select(ApplicantPayout)) is None


def test_case_available_balance_counts_all_non_voided_disbursements(tmp_path):
    app = create_app({'TESTING': True, 'DEMO': True,
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "funds.sqlite"}'})
    client = app.test_client()
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        contact = family.contacts[0]
        db.session.add(Receipt(contact_id=contact.id, family_id=family.id,
                               amount_cents=100_000, received_on=date.today()))
        db.session.add(Expense(family_id=family.id, category='Other', payee='Vendor',
                               amount_cents=20_000, month='2026-09', status='Paid'))
        db.session.add(ApplicantPayout(family_id=family.id, method='check',
            amount_cents=30_000, payee_name='Applicant', mailing_address='1 Main St',
            check_number='10', check_date=date.today(), status='created'))
        db.session.add(ApplicantPayout(family_id=family.id, method='check',
            amount_cents=40_000, payee_name='Applicant', mailing_address='1 Main St',
            check_number='11', check_date=date.today(), status='voided'))
        db.session.commit()
        family_id = family.id

    payouts = client.get('/payouts').text
    assert 'Available by case' in payouts
    assert '$1,000.00' in payouts
    assert '$500.00' in payouts
    profile = client.get(f'/families/{family_id}').text
    assert 'Available to give out' in profile
    assert '$500.00' in profile


def test_fundraising_summary_separates_collected_money_from_family_payouts(tmp_path):
    app = create_app({'TESTING': True, 'DEMO': True,
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "fundraising-summary.sqlite"}'})
    client = app.test_client()
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        contact = family.contacts[0]
        db.session.add(Receipt(contact_id=contact.id, family_id=family.id,
                               amount_cents=10_000, received_on=date.today()))
        db.session.add(ApplicantPayout(
            family_id=family.id, method='check', amount_cents=900_000,
            payee_name='Applicant', mailing_address='1 Main St',
            check_number='100', check_date=date.today(), status='created'))
        db.session.add(ApplicantPayout(
            family_id=family.id, method='check', amount_cents=50_000,
            payee_name='Applicant', mailing_address='1 Main St',
            check_number='101', check_date=date.today(), status='voided'))
        db.session.commit()

    page = client.get('/fundraising').text
    assert 'Lifetime collected' in page
    assert 'Lifetime sent to family' in page
    assert 'Available to pay out' in page
    assert '$100.00' in page
    assert '$9,000.00' in page
    assert '$-8,900.00' in page
    assert '$9,500.00' not in page


def test_negative_money_keeps_ltr_order_in_rtl_views(tmp_path):
    app = create_app({'TESTING': True, 'DEMO': True,
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "rtl-funds.sqlite"}'})
    client = app.test_client()
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        db.session.add(ApplicantPayout(
            family_id=family.id, method='check', amount_cents=100,
            payee_name='Applicant', mailing_address='1 Main St',
            check_number='10', check_date=date.today(), status='created'))
        db.session.commit()
        family_id = family.id
    client.get('/language/yi?next=/payouts')
    payouts = client.get('/payouts').text
    assert '<bdi class="money-value" dir="ltr">$-1.00</bdi>' in payouts
    profile = client.get(f'/families/{family_id}').text
    assert '<bdi class="money-value" dir="ltr">$-1.00</bdi>' in profile


def test_organization_report_counts_direct_family_payouts(tmp_path):
    app = create_app({'TESTING': True, 'DEMO': True,
                      'SQLALCHEMY_DATABASE_URI': f'sqlite:///{tmp_path / "org-report.sqlite"}'})
    with app.app_context():
        family = db.session.scalar(db.select(Family))
        db.session.add(ApplicantPayout(
            family_id=family.id, method='check', amount_cents=900_000,
            payee_name='Applicant', mailing_address='1 Main St',
            check_number='100', check_date=date.today(), status='created'))
        db.session.add(ApplicantPayout(
            family_id=family.id, method='check', amount_cents=100_000,
            payee_name='Applicant', mailing_address='1 Main St',
            check_number='101', check_date=date.today(), status='voided'))
        db.session.commit()

        totals = app.extensions['workflows']['financials'](family.id)

    assert totals['assistance'] == 900_000
    assert totals['balance'] == -900_000
    assert totals['available'] == -900_000
