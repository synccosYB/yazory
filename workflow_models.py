"""Additive workflow tables. Existing household and financial rows are preserved."""
from datetime import datetime, timezone


def workflow_models(db):
    if hasattr(db, 'yazory_workflow_models'):
        return db.yazory_workflow_models
    now = lambda: datetime.now(timezone.utc)

    class WorkflowRole(db.Model):
        __table_args__ = (db.UniqueConstraint('user_id', 'role'),)
        id = db.Column(db.Integer, primary_key=True)
        user_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False)
        role = db.Column(db.String(40), nullable=False)

    class StaffAccess(db.Model):
        user_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), primary_key=True)
        active = db.Column(db.Boolean, nullable=False, default=True)

    class WorkItem(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        kind = db.Column(db.String(40), nullable=False, index=True)
        family_id = db.Column(db.Integer, db.ForeignKey('family.id'), index=True)
        title = db.Column(db.String(160), nullable=False)
        owner_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False, index=True)
        created_by = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False)
        due = db.Column(db.Date, nullable=False, index=True)
        priority = db.Column(db.String(20), nullable=False, default='Normal')
        stage = db.Column(db.Integer, nullable=False, default=0)
        disposition = db.Column(db.String(20), nullable=False, default='Open', index=True)
        revision = db.Column(db.Integer, nullable=False, default=1)
        version = db.Column(db.Integer, nullable=False, default=1)
        data = db.Column(db.JSON, nullable=False, default=dict)
        created_at = db.Column(db.DateTime, nullable=False, default=now)
        updated_at = db.Column(db.DateTime, nullable=False, default=now)
        __mapper_args__ = {'version_id_col': version}

    class WorkflowDecision(db.Model):
        __table_args__ = (db.UniqueConstraint('item_id', 'revision', 'stage', 'actor_id', 'action'),)
        id = db.Column(db.Integer, primary_key=True)
        item_id = db.Column(db.Integer, db.ForeignKey('work_item.id'), nullable=False, index=True)
        revision = db.Column(db.Integer, nullable=False)
        stage = db.Column(db.Integer, nullable=False)
        actor_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False)
        role = db.Column(db.String(40), nullable=False)
        action = db.Column(db.String(30), nullable=False)
        note = db.Column(db.Text, nullable=False)
        at = db.Column(db.DateTime, nullable=False, default=now)

    class WorkflowEvent(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        item_id = db.Column(db.Integer, db.ForeignKey('work_item.id'), index=True)
        family_id = db.Column(db.Integer, db.ForeignKey('family.id'), index=True)
        actor_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False)
        action = db.Column(db.String(80), nullable=False)
        detail = db.Column(db.JSON, nullable=False, default=dict)
        at = db.Column(db.DateTime, nullable=False, default=now)

    class WorkflowNotice(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        item_id = db.Column(db.Integer, db.ForeignKey('work_item.id'), nullable=False, index=True)
        user_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False, index=True)
        message = db.Column(db.String(100), nullable=False)
        at = db.Column(db.DateTime, nullable=False, default=now)
        read_at = db.Column(db.DateTime)

    class WorkflowEvidence(db.Model):
        __table_args__ = (db.UniqueConstraint('item_id', 'document_id'),)
        id = db.Column(db.Integer, primary_key=True)
        item_id = db.Column(db.Integer, db.ForeignKey('work_item.id'), nullable=False)
        document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)

    class WorkflowFile(db.Model):
        purpose = db.Column(db.String(30), nullable=False, default='Supporting evidence')
        revision = db.Column(db.Integer, nullable=False, default=1)
        stage = db.Column(db.Integer, nullable=False, default=0)
        id = db.Column(db.Integer, primary_key=True)
        item_id = db.Column(db.Integer, db.ForeignKey('work_item.id'), nullable=False, index=True)
        filename = db.Column(db.String(255), nullable=False)
        content_type = db.Column(db.String(100), nullable=False)
        data = db.Column(db.LargeBinary, nullable=False)
        actor_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False)
        at = db.Column(db.DateTime, nullable=False, default=now)

    class LedgerEntry(db.Model):
        __table_args__ = (db.UniqueConstraint('source_item_id', 'family_id', 'entry_type'),
                         db.UniqueConstraint('external_reference'),)
        id = db.Column(db.Integer, primary_key=True)
        family_id = db.Column(db.Integer, db.ForeignKey('family.id'), nullable=False, index=True)
        source_item_id = db.Column(db.Integer, db.ForeignKey('work_item.id'), nullable=False)
        entry_type = db.Column(db.String(40), nullable=False)
        amount_cents = db.Column(db.BigInteger, nullable=False)
        external_reference = db.Column(db.String(200))
        actor_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False)
        at = db.Column(db.DateTime, nullable=False, default=now)

    class BankMatch(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        ledger_id = db.Column(db.Integer, db.ForeignKey('ledger_entry.id'), nullable=False, unique=True)
        bank_reference = db.Column(db.String(200), nullable=False, unique=True)
        statement_date = db.Column(db.Date, nullable=False)
        actor_id = db.Column(db.Integer, db.ForeignKey('staff_user.id'), nullable=False)
        at = db.Column(db.DateTime, nullable=False, default=now)

    class WorkflowPolicy(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        data = db.Column(db.JSON, nullable=False, default=dict)
        source_item_id = db.Column(db.Integer, db.ForeignKey('work_item.id'), nullable=False)
        at = db.Column(db.DateTime, nullable=False, default=now)

    class SupporterLink(db.Model):
        contact_id = db.Column(db.Integer, db.ForeignKey('contact.id'), primary_key=True)
        parent_id = db.Column(db.Integer, db.ForeignKey('contact.id'))
        side = db.Column(db.String(20), nullable=False)
        relationship = db.Column(db.String(40), nullable=False)
        introduced_by = db.Column(db.String(160), nullable=False, default='')
        assigned_to = db.Column(db.Integer, db.ForeignKey('staff_user.id'))
        permission = db.Column(db.String(30), nullable=False, default='Not requested')
        preference = db.Column(db.String(30), nullable=False, default='')
        verified = db.Column(db.Boolean, nullable=False, default=False)
        public_story = db.Column(db.Text, nullable=False, default='')

    class DocumentControl(db.Model):
        document_id = db.Column(db.Integer, db.ForeignKey('document.id'), primary_key=True)
        privacy = db.Column(db.String(20), nullable=False, default='Household')
        category = db.Column(db.String(40), nullable=False, default='Unclassified')
        previous_id = db.Column(db.Integer, db.ForeignKey('document.id'))
        archived = db.Column(db.Boolean, nullable=False, default=False)

    result = {cls.__name__: cls for cls in (WorkflowRole, StaffAccess, WorkItem, WorkflowDecision,
        WorkflowEvent, WorkflowNotice, WorkflowEvidence, LedgerEntry, BankMatch, WorkflowPolicy,
        SupporterLink, DocumentControl, WorkflowFile)}
    db.yazory_workflow_models = result
    return result
