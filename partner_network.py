"""Partner organization, askan network, case coordination, and communication center."""

import re
from datetime import date, datetime, timezone

import app_original as core
from sqlalchemy import UniqueConstraint, func, or_, select
from twilio_service import deliver_message, normalize_phone


db = core.db

ORGANIZATION_CATEGORIES = (
    'Medical', 'Housing', 'Government benefits', 'Legal', 'Mental health',
    'Education', 'Food assistance', 'Employment', 'Other')
COORDINATION_STATUSES = (
    'Identified', 'Introduction needed', 'Contacted', 'Referral submitted',
    'Accepted', 'Coordinating', 'Waiting', 'Completed', 'Declined')
RELATIONSHIP_TYPES = ('Official role', 'Informal connection', 'Personal contact')
COMMUNITY_OPTIONS = (
    'Kiryas Joel / Monroe', 'Williamsburg', 'Boro Park',
    'Monsey / Spring Valley', 'New Square', 'Lakewood', 'Bloomingburg',
    'Crown Heights', 'Flatbush', 'Five Towns', 'Passaic', 'Other')
GEOGRAPHIC_AREA_OPTIONS = (
    'Orange County', 'Rockland County', 'New York City', 'Long Island',
    'New York State', 'Lakewood / Ocean County', 'North Jersey',
    'New Jersey', 'United States', 'International', 'Other')


class PartnerOrganization(db.Model):
    __tablename__ = 'partner_organization'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True, index=True)
    category = db.Column(db.String(50), nullable=False, index=True)
    phone = db.Column(db.String(80), nullable=False, default='')
    email = db.Column(db.String(254), nullable=False, default='')
    website = db.Column(db.String(300), nullable=False, default='')
    address = db.Column(db.String(300), nullable=False, default='')
    communities = db.Column(db.String(500), nullable=False, default='')
    geographic_area = db.Column(db.String(300), nullable=False, default='')
    services = db.Column(db.Text, nullable=False, default='')
    exclusions = db.Column(db.Text, nullable=False, default='')
    eligibility = db.Column(db.Text, nullable=False, default='')
    referral_method = db.Column(db.Text, nullable=False, default='')
    required_documents = db.Column(db.Text, nullable=False, default='')
    hours = db.Column(db.String(300), nullable=False, default='')
    response_time = db.Column(db.String(160), nullable=False, default='')
    relationship_status = db.Column(db.String(40), nullable=False, default='New')
    owner_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=True, index=True)
    notes = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    owner = db.relationship('StaffUser')
    contacts = db.relationship('PartnerContact', backref='organization', lazy=True,
                               cascade='all, delete-orphan', order_by='PartnerContact.name')
    askan_links = db.relationship('OrganizationAskan', backref='organization', lazy=True,
                                  cascade='all, delete-orphan')


class PartnerContact(db.Model):
    __tablename__ = 'partner_contact'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('partner_organization.id', ondelete='CASCADE'),
                                nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    title = db.Column(db.String(160), nullable=False, default='')
    phone = db.Column(db.String(80), nullable=False, default='')
    cell_phone = db.Column(db.String(80), nullable=False, default='')
    email = db.Column(db.String(254), nullable=False, default='')
    preferred_method = db.Column(db.String(20), nullable=False, default='Phone')
    is_intake = db.Column(db.Boolean, nullable=False, default=False)
    is_emergency = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text, nullable=False, default='')


class AskanNetworkProfile(db.Model):
    __tablename__ = 'askan_network_profile'
    askan_id = db.Column(db.Integer, db.ForeignKey('askan.id', ondelete='CASCADE'), primary_key=True)
    community = db.Column(db.String(160), nullable=False, default='')
    shul = db.Column(db.String(160), nullable=False, default='')
    expertise = db.Column(db.String(500), nullable=False, default='')
    geographic_reach = db.Column(db.String(300), nullable=False, default='')
    languages = db.Column(db.String(160), nullable=False, default='')
    availability = db.Column(db.String(300), nullable=False, default='')
    preferred_method = db.Column(db.String(20), nullable=False, default='Phone')
    notes = db.Column(db.Text, nullable=False, default='')
    askan = db.relationship('Askan', backref=db.backref('network_profile', uselist=False,
                                                       cascade='all, delete-orphan'))


class OrganizationAskan(db.Model):
    __tablename__ = 'organization_askan'
    __table_args__ = (UniqueConstraint('organization_id', 'askan_id', name='uq_organization_askan'),)
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('partner_organization.id', ondelete='CASCADE'),
                                nullable=False, index=True)
    askan_id = db.Column(db.Integer, db.ForeignKey('askan.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    role = db.Column(db.String(160), nullable=False, default='')
    relationship_type = db.Column(db.String(30), nullable=False, default='Informal connection')
    strength = db.Column(db.String(20), nullable=False, default='')
    notes = db.Column(db.Text, nullable=False, default='')
    askan = db.relationship('Askan', backref='organization_links')


class CaseCoordination(db.Model):
    __tablename__ = 'case_coordination'
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id', ondelete='CASCADE'),
                          nullable=False, index=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('partner_organization.id'),
                                nullable=False, index=True)
    askan_id = db.Column(db.Integer, db.ForeignKey('askan.id'), nullable=True, index=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('partner_contact.id'), nullable=True, index=True)
    assigned_to = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=True, index=True)
    need = db.Column(db.String(300), nullable=False)
    responsibility = db.Column(db.String(500), nullable=False, default='')
    status = db.Column(db.String(40), nullable=False, default='Identified', index=True)
    next_action = db.Column(db.String(500), nullable=False, default='')
    follow_up_on = db.Column(db.Date, nullable=True, index=True)
    outcome = db.Column(db.Text, nullable=False, default='')
    notes = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
                           onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    family = db.relationship('Family', backref='partner_coordinations')
    organization = db.relationship('PartnerOrganization', backref='case_coordinations')
    askan = db.relationship('Askan', backref='case_coordinations')
    contact = db.relationship('PartnerContact')
    assignee = db.relationship('StaffUser')


class PartnerCommunication(db.Model):
    __tablename__ = 'partner_communication'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('partner_organization.id'),
                                nullable=False, index=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('partner_contact.id'), nullable=True, index=True)
    askan_id = db.Column(db.Integer, db.ForeignKey('askan.id'), nullable=True, index=True)
    family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=True, index=True)
    coordination_id = db.Column(db.Integer, db.ForeignKey('case_coordination.id'), nullable=True, index=True)
    staff_user_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=True, index=True)
    email_message_id = db.Column(db.Integer, db.ForeignKey('email_message.id'), nullable=True)
    channel = db.Column(db.String(20), nullable=False, index=True)
    direction = db.Column(db.String(20), nullable=False, default='outbound')
    recipient = db.Column(db.String(254), nullable=False)
    subject = db.Column(db.String(300), nullable=False, default='')
    body = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, index=True)
    provider_message_id = db.Column(db.String(200), nullable=False, default='')
    delivery_error = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False,
                           default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
    organization = db.relationship('PartnerOrganization', backref='communications')
    contact = db.relationship('PartnerContact')
    askan = db.relationship('Askan')
    family = db.relationship('Family')
    coordination = db.relationship('CaseCoordination', backref='communications')
    staff_user = db.relationship('StaffUser')
    email_message = db.relationship('EmailMessage')


def install(app):
    def user():
        uid = core.session.get('user_id')
        return db.session.get(core.StaffUser, uid) if uid else None

    def require_network_access():
        current = user()
        if not (app.config.get('DEMO') or current and current.role in (
                'organization_admin', 'family_admin', 'office_employee')):
            core.abort(403)
        return current

    def can_access_family(family_id):
        current = require_network_access()
        if app.config.get('DEMO') or current.role == 'organization_admin':
            return True
        return bool(db.session.scalar(select(core.FamilyAssignment.id).where(
            core.FamilyAssignment.staff_user_id == current.id,
            core.FamilyAssignment.family_id == family_id)))

    def value(name, limit, required=False):
        result = core.request.form.get(name, '').strip()
        if required and not result:
            core.abort(400, f'{name.replace("_", " ").title()} is required.')
        if len(result) > limit:
            core.abort(400, f'{name.replace("_", " ").title()} is too long.')
        return result

    def email_value(name='email'):
        result = value(name, 254).lower()
        if result and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', result):
            core.abort(400, 'Enter a valid email address.')
        return result

    def parsed_date(name):
        raw = value(name, 10)
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            core.abort(400, 'Enter a valid follow-up date.')

    def selected_values(name, allowed, limit):
        """Validate and store an ordered multi-select without changing schema."""
        values = []
        for item in core.request.form.getlist(name):
            item = item.strip()
            if item and item not in allowed:
                core.abort(400, f'Choose a valid {name.replace("_", " ")}.')
            if item and item not in values:
                values.append(item)
        result = ', '.join(values)
        if len(result) > limit:
            core.abort(400, f'{name.replace("_", " ").title()} is too long.')
        return result

    def audit(action, family_id=None):
        current = user()
        db.session.add(core.Audit(actor=current.email if current else 'Demo user',
                                  action=action, family_id=family_id))

    def twilio_service_sid():
        row = db.session.get(core.OrganizationSetting, 'twilio_messaging_service_sid')
        saved = row.value if row and isinstance(row.value, str) else ''
        return app.config.get('TWILIO_MESSAGING_SERVICE_SID', '') or saved

    def recipients(org):
        rows = []
        for contact in org.contacts:
            rows.append(('contact', contact.id, contact.name, contact.email,
                         contact.cell_phone or contact.phone))
        for link in org.askan_links:
            rows.append(('askan', link.askan.id, link.askan.name, link.askan.email,
                         link.askan.phone))
        return rows

    @app.get('/partner-network')
    def partner_network():
        require_network_access()
        query = core.request.args.get('q', '').strip()[:160]
        category = core.request.args.get('category', '').strip()[:50]
        statement = select(PartnerOrganization).order_by(PartnerOrganization.name)
        if query:
            statement = statement.where(or_(
                PartnerOrganization.name.icontains(query, autoescape=True),
                PartnerOrganization.services.icontains(query, autoescape=True),
                PartnerOrganization.communities.icontains(query, autoescape=True)))
        if category in ORGANIZATION_CATEGORIES:
            statement = statement.where(PartnerOrganization.category == category)
        organizations = db.session.scalars(statement).all()
        askonim = db.session.scalars(select(core.Askan).order_by(core.Askan.name)).all()
        due = db.session.scalars(select(CaseCoordination).where(
            CaseCoordination.status.notin_(('Completed', 'Declined')),
            CaseCoordination.follow_up_on.is_not(None),
            CaseCoordination.follow_up_on <= date.today()).order_by(CaseCoordination.follow_up_on)).all()
        due = [row for row in due if can_access_family(row.family_id)]
        return core.render_template('partner_network.html', title='Organizations & Askonim',
                                    organizations=organizations, askonim=askonim, due=due,
                                    query=query, selected_category=category,
                                    categories=ORGANIZATION_CATEGORIES,
                                    community_options=COMMUNITY_OPTIONS,
                                    geographic_area_options=GEOGRAPHIC_AREA_OPTIONS)

    @app.post('/partner-network/organizations')
    def add_partner_organization():
        require_network_access()
        category = value('category', 50, True)
        if category not in ORGANIZATION_CATEGORIES:
            core.abort(400, 'Choose a valid organization category.')
        name = value('name', 160, True)
        if db.session.scalar(select(PartnerOrganization.id).where(
                func.lower(PartnerOrganization.name) == name.lower())):
            core.abort(409, 'This organization is already in the Data Center.')
        org = PartnerOrganization(name=name, category=category,
            phone=value('phone', 80), email=email_value(), website=value('website', 300),
            address=value('address', 300), hours=value('hours', 300),
            response_time=value('response_time', 160),
            communities=selected_values('communities', COMMUNITY_OPTIONS, 500),
            geographic_area=selected_values(
                'geographic_area', GEOGRAPHIC_AREA_OPTIONS, 300),
            services=value('services', 5000), exclusions=value('exclusions', 5000),
            eligibility=value('eligibility', 5000), referral_method=value('referral_method', 5000),
            required_documents=value('required_documents', 5000), notes=value('notes', 10000),
            owner_id=core.request.form.get('owner_id', type=int))
        db.session.add(org)
        audit(f'Added partner organization: {name}')
        db.session.commit()
        core.flash('Organization added.')
        return core.redirect(core.url_for('partner_organization_detail', organization_id=org.id))

    @app.get('/partner-network/organizations/<int:organization_id>')
    def partner_organization_detail(organization_id):
        require_network_access()
        org = db.get_or_404(PartnerOrganization, organization_id)
        askonim = db.session.scalars(select(core.Askan).order_by(core.Askan.name)).all()
        families = db.session.scalars(select(core.Family).order_by(core.Family.name)).all()
        families = [family for family in families if can_access_family(family.id)]
        staff = db.session.scalars(select(core.StaffUser).where(
            core.StaffUser.status == 'active').order_by(core.StaffUser.name)).all()
        history = db.session.scalars(select(PartnerCommunication).where(
            PartnerCommunication.organization_id == org.id).order_by(
                PartnerCommunication.created_at.desc()).limit(200)).all()
        coordinations = [row for row in org.case_coordinations if can_access_family(row.family_id)]
        return core.render_template('partner_organization.html', title=org.name, organization=org,
                                    askonim=askonim, families=families, staff=staff,
                                    coordinations=coordinations, history=history,
                                    recipients=recipients(org), statuses=COORDINATION_STATUSES,
                                    relationship_types=RELATIONSHIP_TYPES)

    @app.post('/partner-network/organizations/<int:organization_id>/contacts')
    def add_partner_contact(organization_id):
        require_network_access()
        org = db.get_or_404(PartnerOrganization, organization_id)
        contact = PartnerContact(organization=org, name=value('name', 160, True),
            title=value('title', 160), phone=value('phone', 80),
            cell_phone=value('cell_phone', 80), email=email_value(),
            preferred_method=value('preferred_method', 20) or 'Phone',
            is_intake=bool(core.request.form.get('is_intake')),
            is_emergency=bool(core.request.form.get('is_emergency')),
            notes=value('notes', 5000))
        db.session.add(contact)
        audit(f'Added contact {contact.name} to {org.name}')
        db.session.commit()
        core.flash('Organization contact added.')
        return core.redirect(core.url_for('partner_organization_detail', organization_id=org.id))

    @app.post('/partner-network/organizations/<int:organization_id>/askonim')
    def connect_organization_askan(organization_id):
        require_network_access()
        org = db.get_or_404(PartnerOrganization, organization_id)
        askan_id = core.request.form.get('askan_id', type=int)
        askan = db.session.get(core.Askan, askan_id) if askan_id else None
        if askan is None:
            name = value('askan_name', 160, True)
            phone, email = value('askan_phone', 80), email_value('askan_email')
            askan = db.session.scalar(select(core.Askan).where(
                or_(core.Askan.phone == phone, core.Askan.email == email))) if (phone or email) else None
            if askan is None:
                askan = core.Askan(name=name, phone=phone, email=email)
                db.session.add(askan)
                db.session.flush()
        existing = db.session.scalar(select(OrganizationAskan).where(
            OrganizationAskan.organization_id == org.id,
            OrganizationAskan.askan_id == askan.id))
        if existing:
            core.abort(409, 'This askan is already connected to the organization.')
        relationship = value('relationship_type', 30) or 'Informal connection'
        if relationship not in RELATIONSHIP_TYPES:
            core.abort(400, 'Choose a valid relationship type.')
        db.session.add(OrganizationAskan(organization=org, askan=askan,
            role=value('role', 160), relationship_type=relationship,
            strength=value('strength', 20), notes=value('notes', 5000)))
        audit(f'Connected askan {askan.name} to {org.name}')
        db.session.commit()
        core.flash('Askan connected to organization.')
        return core.redirect(core.url_for('partner_organization_detail', organization_id=org.id))

    @app.route('/partner-network/askonim/<int:askan_id>', methods=['GET', 'POST'])
    def network_askan_detail(askan_id):
        require_network_access()
        askan = db.get_or_404(core.Askan, askan_id)
        profile = askan.network_profile or AskanNetworkProfile(askan=askan)
        if core.request.method == 'POST':
            profile.community = value('community', 160)
            profile.shul = value('shul', 160)
            profile.expertise = value('expertise', 500)
            profile.geographic_reach = value('geographic_reach', 300)
            profile.languages = value('languages', 160)
            profile.availability = value('availability', 300)
            profile.preferred_method = value('preferred_method', 20) or 'Phone'
            profile.notes = value('notes', 10000)
            askan.phone, askan.email = value('phone', 80), email_value()
            db.session.add(profile)
            audit(f'Updated askan network profile: {askan.name}')
            db.session.commit()
            core.flash('Askan profile saved.')
            return core.redirect(core.url_for('network_askan_detail', askan_id=askan.id))
        coordinations = [row for row in askan.case_coordinations if can_access_family(row.family_id)]
        return core.render_template('network_askan.html', title=askan.name, askan=askan,
                                    profile=profile, coordinations=coordinations)

    @app.get('/families/<int:family_id>/coordination')
    def family_coordination(family_id):
        if not can_access_family(family_id):
            core.abort(403)
        family = db.get_or_404(core.Family, family_id)
        organizations = db.session.scalars(select(PartnerOrganization).order_by(
            PartnerOrganization.name)).all()
        askonim = db.session.scalars(select(core.Askan).order_by(core.Askan.name)).all()
        staff = db.session.scalars(select(core.StaffUser).where(
            core.StaffUser.status == 'active').order_by(core.StaffUser.name)).all()
        rows = db.session.scalars(select(CaseCoordination).where(
            CaseCoordination.family_id == family.id).order_by(
                CaseCoordination.follow_up_on.is_(None), CaseCoordination.follow_up_on,
                CaseCoordination.id.desc())).all()
        return core.render_template('family_coordination.html', title='Partner coordination',
                                    family=family, coordinations=rows,
                                    organizations=organizations, askonim=askonim, staff=staff,
                                    statuses=COORDINATION_STATUSES)

    @app.post('/families/<int:family_id>/coordination')
    def add_case_coordination(family_id):
        if not can_access_family(family_id):
            core.abort(403)
        family = db.get_or_404(core.Family, family_id)
        org = db.get_or_404(PartnerOrganization,
                            core.request.form.get('organization_id', type=int))
        status = value('status', 40) or 'Identified'
        if status not in COORDINATION_STATUSES:
            core.abort(400, 'Choose a valid coordination status.')
        row = CaseCoordination(family=family, organization=org,
            askan_id=core.request.form.get('askan_id', type=int),
            contact_id=core.request.form.get('contact_id', type=int),
            assigned_to=core.request.form.get('assigned_to', type=int),
            need=value('need', 300, True), responsibility=value('responsibility', 500),
            status=status, next_action=value('next_action', 500),
            follow_up_on=parsed_date('follow_up_on'), notes=value('notes', 10000))
        db.session.add(row)
        audit(f'Added partner coordination with {org.name}', family.id)
        db.session.commit()
        core.flash('Coordination record added.')
        return core.redirect(core.url_for('family_coordination', family_id=family.id))

    @app.post('/coordination/<int:coordination_id>')
    def update_case_coordination(coordination_id):
        row = db.get_or_404(CaseCoordination, coordination_id)
        if not can_access_family(row.family_id):
            core.abort(403)
        status = value('status', 40, True)
        if status not in COORDINATION_STATUSES:
            core.abort(400, 'Choose a valid coordination status.')
        row.status, row.next_action = status, value('next_action', 500)
        row.follow_up_on, row.outcome = parsed_date('follow_up_on'), value('outcome', 10000)
        row.notes = value('notes', 10000)
        row.assigned_to = core.request.form.get('assigned_to', type=int)
        audit(f'Updated partner coordination with {row.organization.name}: {status}', row.family_id)
        db.session.commit()
        core.flash('Coordination updated.')
        return core.redirect(core.url_for('family_coordination', family_id=row.family_id))

    @app.post('/partner-network/organizations/<int:organization_id>/message/<channel>')
    def send_partner_message(organization_id, channel):
        current = require_network_access()
        if channel not in ('email', 'sms'):
            core.abort(404)
        org = db.get_or_404(PartnerOrganization, organization_id)
        target_type, _, raw_id = value('recipient_key', 80, True).partition(':')
        try:
            target_id = int(raw_id)
        except ValueError:
            core.abort(400, 'Choose a valid recipient.')
        contact = db.session.get(PartnerContact, target_id) if target_type == 'contact' else None
        askan = db.session.get(core.Askan, target_id) if target_type == 'askan' else None
        if contact and contact.organization_id != org.id:
            core.abort(400, 'Choose a contact from this organization.')
        if askan and not db.session.scalar(select(OrganizationAskan.id).where(
                OrganizationAskan.organization_id == org.id,
                OrganizationAskan.askan_id == askan.id)):
            core.abort(400, 'Choose an askan connected to this organization.')
        if not contact and not askan:
            core.abort(400, 'Choose a valid recipient.')
        family_id = core.request.form.get('family_id', type=int)
        if family_id and not can_access_family(family_id):
            core.abort(403)
        coordination_id = core.request.form.get('coordination_id', type=int)
        if coordination_id:
            coordination = db.get_or_404(CaseCoordination, coordination_id)
            if coordination.organization_id != org.id or (family_id and coordination.family_id != family_id):
                core.abort(400, 'Choose a matching coordination record.')
            family_id = coordination.family_id
        body = value('body', 5000, True)
        subject = value('subject', 300)
        if channel == 'email':
            recipient = (contact.email if contact else askan.email).strip().lower()
            if not recipient:
                core.abort(400, 'This recipient does not have an email address.')
            if not subject:
                core.abort(400, 'Enter an email subject.')
            message = app.extensions['send_email'](
                'partner_organization', recipient, subject, body,
                staff_user_id=current.id if current else None, family_id=family_id,
                reply_to_public=True)
            status, provider_id, error = message.status, message.provider_id, message.error
            email_message_id = message.id
        else:
            recipient = (contact.cell_phone or contact.phone) if contact else askan.phone
            try:
                recipient = normalize_phone(recipient)
            except ValueError as exc:
                core.abort(400, str(exc))
            if app.config.get('TESTING') or app.config.get('DEMO'):
                provider_id, error, status = '', '', 'preview'
            else:
                provider_id, error = deliver_message(
                    app.config.get('TWILIO_ACCOUNT_SID', ''), app.config.get('TWILIO_AUTH_TOKEN', ''),
                    recipient, body, channel='sms', sms_from=app.config.get('TWILIO_SMS_FROM', ''),
                    messaging_service_sid=twilio_service_sid())
                status = 'failed' if error else 'completed'
            email_message_id = None
        db.session.add(PartnerCommunication(
            organization=org, contact=contact, askan=askan, family_id=family_id,
            coordination_id=coordination_id, staff_user_id=current.id if current else None,
            email_message_id=email_message_id, channel=channel, recipient=recipient,
            subject=subject, body=body, status=status, provider_message_id=provider_id or '',
            delivery_error=error or ''))
        audit(f'{"Sent" if status in ("sent", "completed") else "Prepared" if status == "preview" else "Failed"} '
              f'{channel} to {contact.name if contact else askan.name} at {org.name}', family_id)
        db.session.commit()
        core.flash('Message sent.' if status in ('sent', 'completed') else
                   'Message prepared in preview mode.' if status == 'preview' else
                   'Message delivery failed.', 'error' if status not in ('sent', 'completed') else 'message')
        return core.redirect(core.url_for('partner_organization_detail', organization_id=org.id))

    def init_schema():
        db.create_all()

    app.extensions.setdefault('init_db_hooks', []).append(init_schema)
    app.extensions['partner_network_models'] = {
        'PartnerOrganization': PartnerOrganization, 'PartnerContact': PartnerContact,
        'OrganizationAskan': OrganizationAskan, 'AskanNetworkProfile': AskanNetworkProfile,
        'CaseCoordination': CaseCoordination, 'PartnerCommunication': PartnerCommunication}
