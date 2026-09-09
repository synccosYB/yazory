"""Read-only ABCharity imports. Secrets never enter URLs rendered by Yazory."""
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote

import requests
from flask import abort, flash, redirect, render_template, request, url_for, has_request_context, session
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError, OperationalError

LIMIT = 100000
ERROR = 'ABCharity could not be synced. Check the campaign ID, key setting and API response.'
BIDI_CONTROLS = dict.fromkeys(map(ord, '\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069'))


def fetch_donations(key):
    # The supplied key is already percent encoded. Decode once before encoding.
    try:
        response = requests.get('https://abcharity.org/extras/api/donations',
                                params={'id': unquote(key.strip()), 'limit': LIMIT},
                                timeout=(5, 30), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError(ERROR)
        data = response.json()
        if not isinstance(data, dict) or data.get('error') or not isinstance(data.get('donations'), list):
            raise ValueError(ERROR)
        rows = data['donations']
        if int(data['num_results']) != len(rows) or len(rows) >= LIMIT:
            raise ValueError(ERROR)
        return rows
    except (requests.RequestException, ValueError, KeyError, TypeError):
        # Never propagate a requests exception: it can contain the credential URL.
        raise ValueError(ERROR) from None


def normalize(row, campaign_id):
    def text(key, limit, required=False):
        value = row.get(key, '')
        value = '' if value is None else str(value)
        if len(value) > limit or (required and not value.strip()):
            raise ValueError(ERROR)
        return value

    def cents(key):
        try:
            value = Decimal(str(row[key]))
            if not value.is_finite() or abs(value) > 100000000 or value * 100 != (value * 100).to_integral_value():
                raise ValueError(ERROR)
            return int(value * 100)
        except (KeyError, InvalidOperation):
            raise ValueError(ERROR) from None

    def flag(key):
        value = row.get(key)
        if value in (True, 1, '1'): return True
        if value in (False, 0, '0'): return False
        raise ValueError(ERROR)

    if not isinstance(row, dict) or str(row.get('campaign_id')) != campaign_id:
        raise ValueError(ERROR)
    try:
        stamp = datetime.fromtimestamp(int(row['donation_time']), timezone.utc).replace(tzinfo=None)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        raise ValueError(ERROR) from None
    external_id = text('id', 100, True)
    email = text('email', 254).strip().lower()
    phone = text('phone', 100)
    # Never merge by name or phone: households may share both. No email means
    # a distinct donor per receipt until staff explicitly links the supporter.
    identity = 'email:' + email if email else 'receipt:' + external_id
    return dict(external_id=external_id, amount_cents=cents('amount'), net_cents=cents('net'),
                donation_time=stamp, anonymous=flag('anonymous_donation'),
                subscription=flag('is_subscription'), team=text('team', 300), notes=text('notes', 20000)), dict(
                identity=identity, name=text('name', 300), email=email, phone=phone, address=text('address', 5000))


def register_abcharity(app, db, Campaign, Donor, Donation, Family, Contact, Expense,
                      require_capability, require_admin, get_family, audit):
    def sync(campaign):
        key = os.environ.get(campaign.key_env, '')
        if not key:
            raise ValueError(ERROR)
        rows = fetch_donations(key)
        normalized = [normalize(row, campaign.external_id) for row in rows]
        if len({row[0]['external_id'] for row in normalized}) != len(normalized):
            raise ValueError(ERROR)
        db.session.flush()
        added = 0
        # Database uniqueness is the final protection against concurrent imports.
        for receipt, person in normalized:
            donor = db.session.scalar(select(Donor).where(Donor.campaign_id == campaign.id, Donor.identity == person['identity']))
            if donor is None:
                donor = Donor(campaign_id=campaign.id, **person)
                db.session.add(donor)
                db.session.flush()
            else:
                for field, value in person.items():
                    setattr(donor, field, value)
            donation = db.session.scalar(select(Donation).where(Donation.campaign_id == campaign.id, Donation.external_id == receipt['external_id']))
            if donation is None:
                donation = Donation(campaign_id=campaign.id, donor_id=donor.id, **receipt)
                db.session.add(donation)
                added += 1
            else:
                for field, value in receipt.items():
                    setattr(donation, field, value)
                donation.donor_id = donor.id
        campaign.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
        campaign.last_error = None
        if has_request_context():
            audit('Imported ABCharity donations', campaign.family_id)
        else:
            from app import Audit
            db.session.add(Audit(actor='System', action='Imported ABCharity donations', family_id=campaign.family_id))
        db.session.commit()
        return added

    def run_sync(campaign):
        campaign_id = campaign.id
        try:
            sync(campaign)
            return True
        except (ValueError, IntegrityError, OperationalError):
            db.session.rollback()
            campaign = db.session.get(Campaign, campaign_id)
            campaign.last_error = ERROR
            db.session.commit()
            return False

    def assigned_contacts(family_id):
        from app import StaffUser
        user=db.session.get(StaffUser,session.get('user_id'))
        if user and user.role=='fundraiser':
            Link=app.extensions['workflows']['models']['SupporterLink']
            return list(db.session.scalars(select(Link.contact_id).join(Contact,Contact.id==Link.contact_id).where(Link.assigned_to==user.id,Contact.family_id==family_id)))
        return None

    @app.get('/families/<int:family_id>/donations')
    def charity_donations(family_id):
        require_capability(('family_admin', 'fundraiser'))
        family = get_family(family_id)
        campaign = db.session.scalar(select(Campaign).where(Campaign.family_id == family_id))
        page = max(1, request.args.get('page', 1, type=int))
        statement = select(Donation).where(Donation.campaign_id == campaign.id) if campaign else select(Donation).where(False)
        allowed_ids=assigned_contacts(family_id)
        if allowed_ids is not None:statement=statement.join(Donor,Donor.id==Donation.donor_id).where(Donor.contact_id.in_(allowed_ids))
        pagination = db.paginate(statement.order_by(Donation.donation_time.desc(), Donation.id.desc()), page=page, per_page=5, error_out=False)
        totals = db.session.execute(select(func.coalesce(func.sum(Donation.amount_cents), 0), func.coalesce(func.sum(Donation.net_cents), 0)).where(Donation.campaign_id == campaign.id)).one() if campaign else (0, 0)
        if allowed_ids is not None:
            totals=db.session.execute(select(func.coalesce(func.sum(Donation.amount_cents),0),func.coalesce(func.sum(Donation.net_cents),0)).join(Donor,Donor.id==Donation.donor_id).where(Donation.campaign_id==campaign.id,Donor.contact_id.in_(allowed_ids))).one() if campaign else (0,0)
        # Household expenses remain inaccessible to fundraisers.
        from flask import session
        from app import StaffUser
        user = db.session.get(StaffUser, session.get('user_id')) if session.get('user_id') else None
        paid = None
        if campaign and campaign.currency == 'USD' and (app.config['DEMO'] or (user and user.role in ('organization_admin', 'family_admin'))):
            paid = db.session.scalar(select(func.coalesce(func.sum(Expense.amount_cents), 0)).where(Expense.family_id == family_id, Expense.status == 'Paid'))
        contacts = db.session.scalars(select(Contact).where(Contact.family_id == family_id).order_by(Contact.name)).all()
        if allowed_ids is not None:contacts=[c for c in contacts if c.id in allowed_ids]
        return render_template('donations.html', title='ABCharity donations', family=family,
                               campaign=campaign, pagination=pagination, totals=totals, paid=paid, contacts=contacts)

    @app.post('/families/<int:family_id>/campaign')
    def charity_connect(family_id):
        require_admin()
        get_family(family_id)
        if app.config['DEMO']:
            abort(400, 'Live donation imports are unavailable in demo mode.')
        external_id = request.form.get('campaign_id', '').strip()
        # RTL pages can add invisible direction marks when an administrator
        # pastes an ASCII environment-variable name. Ignore those marks while
        # retaining strict validation of the resulting secret name.
        key_env = request.form.get('key_env', '').translate(BIDI_CONTROLS).strip()
        label = request.form.get('label', '').strip()
        currency = request.form.get('currency', '').strip().upper()
        if not re.fullmatch(r'[0-9]{1,100}', external_id) or not re.fullmatch(r'ABCHARITY_KEY_[A-Z0-9_]{1,80}', key_env) or not 1 <= len(label) <= 160 or currency not in ('USD', 'ILS', 'GBP', 'EUR', 'CAD'):
            abort(400, 'Enter a valid campaign ID, name, currency and key setting.')
        campaign = db.session.scalar(select(Campaign).where(Campaign.family_id == family_id))
        if campaign and (campaign.external_id != external_id or campaign.currency != currency):
            abort(400, 'The linked campaign ID and currency cannot be changed.')
        if campaign is None:
            campaign = Campaign(family_id=family_id, external_id=external_id, currency=currency)
            db.session.add(campaign)
        campaign.label, campaign.key_env = label, key_env
        try:
            # Validate credentials and campaign membership before saving anything.
            sync(campaign)
        except (ValueError, IntegrityError, OperationalError):
            db.session.rollback()
            flash(ERROR, 'error')
        else:
            flash('Campaign connected and donations imported.')
        return redirect(url_for('charity_donations', family_id=family_id))

    @app.post('/families/<int:family_id>/donations/sync')
    def charity_sync(family_id):
        require_capability(('family_admin', 'fundraiser'))
        get_family(family_id)
        if app.config['DEMO']:
            abort(400, 'Live donation imports are unavailable in demo mode.')
        campaign = db.session.scalar(select(Campaign).where(Campaign.family_id == family_id))
        if not campaign: abort(404)
        flash('Donations synced.' if run_sync(campaign) else ERROR)
        return redirect(url_for('charity_donations', family_id=family_id))

    @app.post('/families/<int:family_id>/donors/<int:donor_id>/link')
    def charity_link(family_id, donor_id):
        require_capability(('family_admin', 'fundraiser'))
        get_family(family_id)
        donor = db.session.scalar(select(Donor).join(Campaign, Campaign.id == Donor.campaign_id).where(Donor.id == donor_id, Campaign.family_id == family_id))
        if donor is None: abort(404)
        contact_id = request.form.get('contact_id', type=int)
        if contact_id and not db.session.scalar(select(Contact.id).where(Contact.id == contact_id, Contact.family_id == family_id)):
            abort(403)
        allowed_ids=assigned_contacts(family_id)
        if allowed_ids is not None and (donor.contact_id not in allowed_ids or contact_id not in allowed_ids):abort(403)
        donor.contact_id = contact_id
        audit('Linked ABCharity donor to supporter', family_id)
        db.session.commit()
        return redirect(url_for('charity_donations', family_id=family_id))

    @app.cli.command('sync-abcharity')
    def sync_all():
        """Run from the deployment scheduler; returns nonzero on any failure."""
        import click
        if app.config['DEMO']:
            raise click.ClickException('Live imports require authenticated mode.')
        ids = db.session.scalars(select(Campaign.id)).all()
        failures = 0
        for campaign_id in ids:
            if not run_sync(db.session.get(Campaign, campaign_id)):
                failures += 1
        if failures:
            raise click.ClickException(f'{failures} campaign imports failed; see campaign status.')
        click.echo(f'Synced {len(ids)} campaigns.')
