from tests.test_tasks import login, make_app
from app_original import Contact, Family, db


def test_one_time_pledge_does_not_inflate_monthly_total_across_case_pages():
    app = make_app()
    with app.app_context():
        family = Family(name='Mixed pledges')
        db.session.add(family)
        db.session.flush()
        db.session.add_all([
            Contact(family_id=family.id, name='Monthly donor',
                    relationship='Friend', status='Pledged',
                    monthly_cents=100, pledge_frequency='Monthly'),
            Contact(family_id=family.id, name='One-time donor',
                    relationship='Friend', status='Pledged',
                    monthly_cents=10000, pledge_frequency='One time'),
        ])
        db.session.commit()
        client = app.test_client()
        login(client, 'admin@example.test')
        profile = client.get(f'/families/{family.id}')
        fundraising = client.get(f'/fundraising/{family.id}')
        assert profile.status_code == fundraising.status_code == 200
        assert 'Monthly pledged</span><strong><bdi class="money-value" dir="ltr">$1.00' in profile.text
        assert 'Monthly pledged: <strong>$1.00' in fundraising.text
        assert 'Monthly pledged: <strong>$101.00' not in fundraising.text
