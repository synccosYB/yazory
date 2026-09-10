from datetime import date

from app import ApplicantPayout, Expense, Family, Receipt, create_app, db


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
