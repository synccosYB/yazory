"""Native Group MMS conversations, persisted separately from private bulk SMS."""
import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone

from flask import abort, flash, g, jsonify, render_template, request, session, url_for, redirect
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from werkzeug.exceptions import Forbidden, NotFound

import app_original as core
from twilio_service import _request, normalize_phone, validate_webhook_signature

BASE = 'https://conversations.twilio.com/v1'


class TextGroup(core.db.Model):
    id = core.db.Column(core.db.Integer, primary_key=True)
    name = core.db.Column(core.db.String(120), nullable=False)
    family_id = core.db.Column(core.db.Integer, core.db.ForeignKey('family.id'), index=True)
    staff_user_id = core.db.Column(core.db.Integer, core.db.ForeignKey('staff_user.id'))
    fingerprint = core.db.Column(core.db.String(64), unique=True, nullable=False)
    conversation_sid = core.db.Column(core.db.String(34), unique=True)
    sender = core.db.Column(core.db.String(20), nullable=False)
    state = core.db.Column(core.db.String(20), nullable=False, default='initializing')
    error = core.db.Column(core.db.Text, default='', nullable=False)
    created_at = core.db.Column(core.db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    members = core.db.relationship('TextGroupMember', cascade='all, delete-orphan', lazy='selectin')


class TextGroupMember(core.db.Model):
    id = core.db.Column(core.db.Integer, primary_key=True)
    group_id = core.db.Column(core.db.Integer, core.db.ForeignKey('text_group.id'), nullable=False, index=True)
    contact_id = core.db.Column(core.db.Integer, core.db.ForeignKey('contact.id'), nullable=False)
    phone = core.db.Column(core.db.String(20), nullable=False)
    contact = core.db.relationship(core.Contact)
    __table_args__ = (core.db.UniqueConstraint('group_id', 'phone'),)


class TextGroupMessage(core.db.Model):
    id = core.db.Column(core.db.Integer, primary_key=True)
    group_id = core.db.Column(core.db.Integer, core.db.ForeignKey('text_group.id'), nullable=False, index=True)
    group = core.db.relationship(TextGroup)
    provider_sid = core.db.Column(core.db.String(34), unique=True)
    send_key = core.db.Column(core.db.String(64), unique=True)
    author = core.db.Column(core.db.String(160), nullable=False)
    body = core.db.Column(core.db.Text, nullable=False)
    direction = core.db.Column(core.db.String(12), nullable=False)
    status = core.db.Column(core.db.String(20), nullable=False)
    error = core.db.Column(core.db.Text, nullable=False, default='')
    media_count = core.db.Column(core.db.Integer, nullable=False, default=0)
    created_at = core.db.Column(core.db.DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


def create_conversation(account, token, name, sender, phones, unique_name, service_sid=''):
    # The atomic Twilio endpoint validates all participants before creating the thread.
    data = [('FriendlyName', name), ('UniqueName', unique_name)]
    if service_sid:
        data.append(('MessagingServiceSid', service_sid))
    for phone in phones:
        data.append(('Participant', json.dumps({'messaging_binding': {'address': phone}})))
    data.append(('Participant', json.dumps({'messaging_binding': {'projected_address': sender}})))
    return _request('POST', BASE + '/ConversationWithParticipants', account, token, data=data)


def conversation_status(account, token, sid):
    return _request('GET', BASE + '/Conversations/' + sid, account, token)


def attach_webhook(account, token, sid, callback):
    return _request('POST', BASE + '/Conversations/' + sid + '/Webhooks', account, token,
                    data={'Target': 'webhook', 'Configuration.Url': callback,
                          'Configuration.Method': 'post',
                          'Configuration.Filters': 'onMessageAdded'})


def send_message(account, token, sid, sender, body):
    return _request('POST', BASE + '/Conversations/' + sid + '/Messages', account, token,
                    data={'Author': sender, 'Body': body})


def install(app, user_for_request, is_admin, contact_access, mobile, history_row, sign_body, audit):
    app.config.setdefault('TWILIO_GROUP_MMS_FROM', os.getenv('TWILIO_GROUP_MMS_FROM', ''))

    def bad_form(message):
        abort(400, app.jinja_env.globals['_'](message))

    def authorized_user():
        user = user_for_request()
        if not user or user.role not in ('organization_admin', 'family_admin', 'fundraiser'):
            abort(403)
        return user

    def group_access(group_id):
        authorized_user()
        cached = getattr(g, 'authorized_text_groups', {})
        if group_id in cached:
            return cached[group_id]
        group = core.db.get_or_404(TextGroup, group_id)
        # Recheck current permissions, including individual fundraiser assignments.
        for member in group.members:
            contact_access(member.contact_id)
        cached[group_id] = group
        g.authorized_text_groups = cached
        return group

    def preview():
        return app.config['TESTING'] or app.config['DEMO']

    def credentials():
        return app.config['TWILIO_ACCOUNT_SID'], app.config['TWILIO_AUTH_TOKEN']

    def callback_url():
        base = app.config.get('APP_BASE_URL', '').rstrip('/')
        return base + url_for('text_group_webhook') if base else url_for('text_group_webhook', _external=True)

    def prepare(group):
        """Explicit POST-only setup: no repair writes or provider calls in page GETs."""
        if group.state in ('active', 'preview'):
            return True
        if not group.conversation_sid:
            data, error = create_conversation(
                *credentials(), group.name, group.sender,
                [member.phone for member in group.members],
                'yazory-text-' + group.fingerprint,
                app.config.get('TWILIO_MESSAGING_SERVICE_SID', ''))
            if error:
                # A timed-out create may have succeeded. Recover the deterministic
                # UniqueName before allowing another setup attempt.
                recovered, recovery_error = _request(
                    'GET', BASE + '/Conversations/yazory-text-' + group.fingerprint, *credentials())
                if not recovery_error and recovered:
                    data, error = recovered, None
            if error or not data or not re.fullmatch(r'CH[0-9a-fA-F]{32}', data.get('sid', '')):
                group.state, group.error = 'error', error or 'Twilio returned no conversation reference.'
                core.db.session.commit()
                return False
            group.conversation_sid = data['sid']
            # Local active means the archive webhook is installed too.
            group.state = 'initializing'
            # Persist the external reference before attempting webhook setup.
            core.db.session.commit()
        data, error = conversation_status(*credentials(), group.conversation_sid)
        if error:
            group.error = error
            core.db.session.commit()
            return False
        if data.get('state') not in ('active', 'inactive'):
            group.state = data.get('state') or 'initializing'
            group.error = ''
            core.db.session.commit()
            return False
        _, error = attach_webhook(*credentials(), group.conversation_sid, callback_url())
        group.state = 'error' if error else 'active'
        group.error = error or ''
        core.db.session.commit()
        return not error

    @app.route('/communications/text-groups', methods=['GET', 'POST'])
    def text_groups():
        user = authorized_user()
        source = request.form if request.method == 'POST' else request.args
        family_id = source.get('family_id', type=int)
        if request.method == 'POST':
            name = source.get('name', '').strip()
            try:
                ids = list(dict.fromkeys(int(value) for value in source.getlist('contact_ids')))
            except ValueError:
                abort(400)
            if not name or len(name) > 120 or not 2 <= len(ids) <= 9:
                bad_form('Choose 2 to 9 people and enter a group name.')
            contacts = [contact_access(contact_id) for contact_id in ids]
            if family_id and any(contact.family_id != family_id for contact in contacts):
                abort(400)
            try:
                phones = [normalize_phone(mobile(contact)) for contact in contacts]
            except ValueError:
                bad_form('Every member needs a valid mobile number.')
            if any(not phone.startswith('+1') for phone in phones) or len(set(phones)) != len(phones):
                bad_form('Choose distinct US/Canada mobile numbers.')
            configured_sender = app.config.get('TWILIO_GROUP_MMS_FROM') or app.config['TWILIO_SMS_FROM']
            if preview() and not configured_sender:
                configured_sender = '+18455550000'
            try:
                sender = normalize_phone(configured_sender)
            except ValueError:
                flash('Set the Group MMS sender number before creating a shared text group.', 'error')
                return redirect(url_for('text_groups', family_id=family_id))
            if not sender.startswith('+1') or sender[2:5] in ('800', '833', '844', '855', '866', '877', '888') or sender in phones:
                bad_form('Group MMS requires a US/Canada local Twilio number distinct from the members.')
            fingerprint = hashlib.sha256('|'.join(sorted([sender] + phones)).encode()).hexdigest()
            existing = core.db.session.scalar(select(TextGroup).where(TextGroup.fingerprint == fingerprint))
            if existing:
                group_access(existing.id)
                return redirect(url_for('text_group_detail', group_id=existing.id))
            case_ids = {contact.family_id for contact in contacts}
            group = TextGroup(name=name, family_id=family_id or (next(iter(case_ids)) if len(case_ids) == 1 else None), staff_user_id=user.id,
                              fingerprint=fingerprint, sender=sender,
                              state='preview' if preview() else 'initializing')
            group.members = [TextGroupMember(contact_id=c.id, phone=phone)
                             for c, phone in zip(contacts, phones)]
            core.db.session.add(group)
            try:
                core.db.session.commit()
            except IntegrityError:
                core.db.session.rollback()
                existing = core.db.session.scalar(select(TextGroup).where(TextGroup.fingerprint == fingerprint))
                if not existing:
                    raise
                group_access(existing.id)
                return redirect(url_for('text_group_detail', group_id=existing.id))
            if not preview():
                prepare(group)
            audit(f'Created shared text group: {group.name}')
            core.db.session.commit()
            return redirect(url_for('text_group_detail', group_id=group.id))
        query = request.args.get('q', '').strip()[:160]
        statement = select(core.Contact).options(selectinload(core.Contact.family))
        if family_id:
            statement = statement.where(core.Contact.family_id == family_id)
        if query:
            statement = statement.where(core.Contact.name.ilike('%' + query + '%'))
        # Permission scope before the bounded selector so unrelated cases do not consume it.
        if not is_admin(user):
            statement = statement.where(core.Contact.family_id.in_(select(core.FamilyAssignment.family_id).where(
                core.FamilyAssignment.staff_user_id == user.id)))
        if user.role == 'fundraiser' and app.extensions['workflows']['enforced']():
            link = app.extensions['workflows']['models']['SupporterLink']
            statement = statement.where(core.Contact.id.in_(select(link.contact_id).where(link.assigned_to == user.id)))
        contacts = core.db.session.scalars(statement.order_by(core.Contact.name, core.Contact.id).limit(75)).all()
        groups = []
        group_statement = select(TextGroup).options(selectinload(TextGroup.members).selectinload(TextGroupMember.contact)).order_by(TextGroup.id.desc()).limit(50)
        if family_id:
            group_statement = group_statement.where(TextGroup.family_id == family_id)
        if not is_admin(user):
            assigned_contacts = select(core.Contact.id).where(core.Contact.family_id.in_(
                select(core.FamilyAssignment.family_id).where(
                    core.FamilyAssignment.staff_user_id == user.id)))
            group_statement = group_statement.where(
                TextGroup.members.any(TextGroupMember.contact_id.in_(assigned_contacts)))
        for group in core.db.session.scalars(group_statement):
            try:
                group_access(group.id)
            except (Forbidden, NotFound):
                continue
            groups.append(group)
        return render_template('text_groups.html', title='Shared text groups', contacts=contacts,
                               groups=groups, family_id=family_id, query=query, mobile=mobile)

    @app.route('/communications/text-groups/<int:group_id>', methods=['GET', 'POST'])
    def text_group_detail(group_id):
        group = group_access(group_id)
        if request.method == 'POST':
            if request.form.get('action') == 'setup':
                prepare(group)
                return redirect(url_for('text_group_detail', group_id=group.id))
            body = request.form.get('body', '').strip()
            if not body or len(body) > 1600:
                abort(400)
            token = request.form.get('send_key', '')
            expected = session.get('text_group_send:' + str(group.id))
            if not token or not expected or not secrets.compare_digest(token, expected):
                bad_form('Reopen the conversation before sending again.')
            if not prepare(group):
                flash('The text group is not ready. Finish setup and try again.', 'error')
                return redirect(url_for('text_group_detail', group_id=group.id))
            # Preview-created groups must never silently go live after configuration changes.
            if group.state == 'preview' and not preview():
                flash('This is a preview group. Create a new group with a live sender.', 'error')
                return redirect(url_for('text_group_detail', group_id=group.id))
            body = sign_body(body, user_for_request())
            message = TextGroupMessage(group_id=group.id, send_key=token, author=group.sender,
                                       body=body, direction='outbound', status='sending')
            core.db.session.add(message)
            try:
                core.db.session.commit()
            except IntegrityError:
                core.db.session.rollback()
                return redirect(url_for('text_group_detail', group_id=group.id))
            session.pop('text_group_send:' + str(group.id), None)
            if preview():
                message.status = 'preview'
            else:
                result, error = send_message(*credentials(), group.conversation_sid, group.sender, body)
                message.provider_sid = (result or {}).get('sid')
                if not error and not re.fullmatch(r'IM[0-9a-fA-F]{32}', message.provider_sid or ''):
                    error = 'Twilio returned no message reference.'
                message.status = 'failed' if error else 'sent'
                message.error = error or ''
            for member in group.members:
                history_row(member.contact, 'group_mms', group.name, body,
                            status='completed' if message.status == 'sent' else message.status,
                            provider_message_id=message.provider_sid or '', delivery_error=message.error)
            audit(f'Shared text group message: {group.name}; {message.status}')
            core.db.session.commit()
            flash('Message sent.' if message.status == 'sent' else
                  'Message was prepared but not sent because delivery is in preview mode.' if message.status == 'preview' else
                  'Message delivery failed. Open Communication history for the error.',
                  'success' if message.status == 'sent' else 'error')
            return redirect(url_for('text_group_detail', group_id=group.id))
        page = max(request.args.get('page', 1, type=int), 1)
        messages = core.db.session.scalars(select(TextGroupMessage).where(
            TextGroupMessage.group_id == group.id).order_by(TextGroupMessage.id.desc()).offset((page - 1) * 50).limit(51)).all()
        more = len(messages) > 50
        send_key = secrets.token_hex(24)
        session['text_group_send:' + str(group.id)] = send_key
        return render_template('text_group_detail.html', title=group.name, group=group,
                               messages=list(reversed(messages[:50])), page=page, more=more, send_key=send_key)

    @app.post('/twilio/text-groups/webhook')
    def text_group_webhook():
        signature = request.headers.get('X-Twilio-Signature', '')
        path = request.full_path.rstrip('?')
        urls = {request.url, 'https://' + request.host + path}
        if app.config.get('APP_BASE_URL'):
            urls.add(app.config['APP_BASE_URL'].rstrip('/') + path)
        if not any(validate_webhook_signature(app.config['TWILIO_AUTH_TOKEN'], url, request.form, signature) for url in urls):
            abort(403)
        if request.form.get('EventType') != 'onMessageAdded':
            return jsonify(received=True, ignored=True)
        sid = request.form.get('MessageSid', '')
        conversation = request.form.get('ConversationSid', '')
        if not re.fullmatch(r'IM[0-9a-fA-F]{32}', sid) or not re.fullmatch(r'CH[0-9a-fA-F]{32}', conversation):
            abort(400)
        group = core.db.session.scalar(select(TextGroup).where(TextGroup.conversation_sid == conversation))
        if not group:
            return jsonify(received=True, ignored=True)
        if core.db.session.scalar(select(TextGroupMessage.id).where(TextGroupMessage.provider_sid == sid)):
            return jsonify(received=True, duplicate=True)
        author = request.form.get('Author', '')[:160]
        try:
            phone = normalize_phone(author)
        except ValueError:
            phone = ''
        member = next((m for m in group.members if m.phone == phone), None)
        if not member:
            # REST API sends are already stored locally; only member replies belong here.
            return jsonify(received=True, ignored=True)
        body = request.form.get('Body', '')[:32000]
        try:
            media_count = len(json.loads(request.form.get('Media') or '[]'))
        except (ValueError, TypeError):
            media_count = 0
        message = TextGroupMessage(group_id=group.id, provider_sid=sid, author=member.contact.name,
                                   body=body, direction='inbound', status='received', media_count=media_count)
        core.db.session.add(message)
        try:
            core.db.session.flush()
        except IntegrityError:
            core.db.session.rollback()
            return jsonify(received=True, duplicate=True)
        history_row(member.contact, 'group_mms', group.name, body, status='received',
                    provider_message_id=sid, direction='inbound')
        core.db.session.commit()
        # Twilio delivers this reply to the other group participants. Do not re-send it.
        return jsonify(received=True)

    def shared_text_inbox():
        authorized_user()
        messages = core.db.session.scalars(select(TextGroupMessage).options(
            selectinload(TextGroupMessage.group).selectinload(TextGroup.members).selectinload(TextGroupMember.contact)
        ).where(
            TextGroupMessage.direction == 'inbound'
        ).order_by(TextGroupMessage.id.desc()).limit(20)).all()
        visible = []
        for message in messages:
            try:
                group = group_access(message.group_id)
            except (Forbidden, NotFound):
                continue
            visible.append(dict(group=group, message=message))
        return visible

    app.jinja_env.globals['shared_text_inbox'] = shared_text_inbox

    def notifications(user, since):
        if user.role not in ('organization_admin', 'family_admin', 'fundraiser'):
            return []
        items = []
        messages = core.db.session.scalars(select(TextGroupMessage).options(
            selectinload(TextGroupMessage.group).selectinload(TextGroup.members).selectinload(TextGroupMember.contact)
        ).where(
            TextGroupMessage.direction == 'inbound', TextGroupMessage.created_at > since
        ).order_by(TextGroupMessage.id.desc()).limit(50)).all()
        for message in messages:
            try:
                group = group_access(message.group_id)
            except (Forbidden, NotFound):
                continue
            items.append(dict(id=f'text-group-{message.id}', kind='Message',
                              action=f'{group.name}: {message.author}', actor=message.author,
                              at=message.created_at, direct_url=True,
                              url=url_for('text_group_detail', group_id=group.id)))
        return items
    app.extensions.setdefault('notification_item_providers', []).append(notifications)
