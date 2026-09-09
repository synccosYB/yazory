"""The 35 agreed operating workflows; step roles are enforced on the server."""
ROLES = {'intake':'Intake administrator','verifier':'Verifier','finance':'Finance administrator',
         'case_admin':'Case administrator','rabbi':'Rabbinical supervisor','executive':'Executive leadership',
         'board':'Board member','compliance':'Compliance administrator','fundraising':'Fundraising administrator',
         'payment_approver':'Payment batch approver','payment_releaser':'Payment releaser',
         'auditor':'Read-only auditor','medical':'Medical-information access'}

# type, label, required; conditional requirements are checked at the relevant stage.
FIELDS = {
 'review_decision':('choice','Review decision',True), 'batch_items':('text','Expense workflow numbers, separated by commas',True), 'summary':('text','Summary',True), 'reason':('text','Reason',True),
 'consent':('check','Family consent recorded',True), 'safe_contact':('text','Safe contact method',True),
 'referrer':('text','Referred by',True), 'relationship':('text','Relationship',True),
 'contact_permission':('check','Permission for supporter outreach',True),
 'verification':('text','Verification findings',True), 'exceptions':('text','Conditions or exceptions',False),
 'approved_categories':('text','Approved expense categories, separated by commas',True), 'support_limit':('money','Monthly assistance limit ($)',True), 'family_contribution':('money','Additional family contribution ($)',True), 'org_cost':('money','Monthly case administration cost ($)',True),
 'fees':('money','Monthly processing fees ($)',True), 'reserve':('money','Monthly reserve ($)',True),
 'start':('date','Start date',True), 'end':('date','End date',True),
 'review_date':('date','Next review date',True), 'privacy':('text','Approved disclosure and privacy rules',True),
 'surplus':('text','Restricted funds and surplus instructions',True),
 'assessment_id':('item','Approved needs assessment',True), 'case_approval_id':('item','Approved case decision',True),
 'plan_id':('item','Approved support plan',True), 'vendor_id':('item','Approved vendor',True),
 'source_id':('item','Original record',True), 'target_family':('family','Destination case',True),
 'amount':('money','Amount ($)',True), 'reference':('text','External transaction reference',True),
 'invoice':('text','Invoice number',True), 'month':('month','Budget month',True),
 'category':('text','Expense category',True), 'payee':('text','Payee',True),
 'expense_type':('choice','Expense classification',True), 'allocation':('text','Allocation method',True),
 'related_party':('check','Related-party payment',False), 'cash':('check','Cash payment',False),
 'direct_family':('check','Direct family payment',False), 'essential':('check','Essential or emergency expense',False),
 'contact_id':('contact','Supporter',True), 'frequency':('choice','Frequency',True),
 'anonymous':('check','Anonymous donation',False), 'receipt_preference':('text','Receipt preference',True),
 'payment_method':('text','Payment method',True), 'restrictions':('text','Donor restrictions',True),
 'follow_up':('date','Follow-up date',True), 'communication':('text','Communication record',True),
 'confirmed':('check','Donor confirmation recorded',True),
 'notification':('text','Notification record',True), 'bank_ref':('text','Bank transaction reference',True),
 'bank_date':('date','Bank statement date',True), 'ledger_id':('integer','Ledger entry number',True),
 'bank_amount':('signed_money','Bank transaction amount ($)',True),
 'legal_name':('text','Legal entity name',True), 'banking':('text','Banking and processor setup references',True),
 'policies':('text','Eligibility, privacy, emergency, restrictions and conflicts policy',True),
 'large_limit':('money','Executive approval threshold ($)',True), 'cash_limit':('money','Cash approval threshold ($)',True),
 'new_role':('choice','New access role',False), 'user_id':('user','Staff member',True), 'training':('text','Identity and training verification',True),
 'handover':('user','Transfer assignments to',True), 'access_change':('choice','Access change',True),
 'conflict_user':('user','Conflicted staff member',True), 'risk':('text','Risk and safeguarding assessment',True),
 'resolution':('text','Resolution and corrective action',True), 'deadline':('date','Documentation deadline',True),
 'documents':('text','Required documents',True), 'dependency_id':('item','Depends on record',False),
 'escalation_user':('user','Escalate to',True), 'document_id':('document','Document',True),
 'document_privacy':('choice','Document privacy',True), 'document_category':('text','Document category',True),
 'previous_document':('document','Previous document version',False), 'period':('month','Reporting month',True),
 'audit_findings':('text','Audit findings and management response',True),
 'donor_authorization':('check','Required donor authorization documented',True),
 'payment_result':('text','Bank or processor result',True), 'receipt':('text','Receipt number',True),
 'disclosure':('text','Approved family story',True), 'monthly_goal':('money','Monthly fundraising goal ($)',True),
 'overall_goal':('money','Overall fundraising goal ($)',True),
}
CHOICES = {'expense_type':['Family assistance','Organization expense'], 'frequency':['Monthly','Weekly','One-time'],
           'new_role':['family_admin','office_employee','fundraiser','organization_admin'], 'access_change':['Deactivate','Role change'], 'document_privacy':['Household','Medical','Finance','Restricted']}


def step(label, role='owner', quorum=1): return (label, role, quorum)
DRAFT=step('Draft'); FIN=step('Finance review','finance'); CASE=step('Case review','case_admin')
TWO=step('Two case administrators','case_admin',2); RABBI=step('Rabbinical review','rabbi')
VERIFY=step('Verification','verifier'); PRIV=step('Privacy review','compliance')
APPROVED=step('Approved'); DONE=step('Completed')

def definition(n,title,group,steps,fields,**kw):
 return dict(number=n,title=title,group=group,steps=[DRAFT]+steps,fields=fields.split(),**kw)

CATALOG={
 'governance':definition(1,'Organization setup and governance','Organization',[FIN,step('Board approval','board'),RABBI,APPROVED], 'legal_name banking policies large_limit cash_limit review_date',org=True),
 'referral':definition(2,'Referral','Cases',[step('Contact attempted'),step('Consent received'),step('Intake scheduled'),DONE], 'referrer relationship reason safe_contact consent'),
 'intake':definition(3,'Intake review','Cases',[step('Family review'),step('Submitted for verification','intake'),DONE], 'summary consent privacy contact_permission',evidence=True),
 'verification':definition(4,'Information verification','Cases',[VERIFY,CASE,DONE], 'verification exceptions verify_income verify_housing verify_tuition verify_utilities verify_assistance verify_family verify_reference verify_vendor',evidence=True),
 'assessment':definition(5,'Needs assessment','Cases',[FIN,RABBI,APPROVED], 'approved_categories support_limit family_contribution org_cost fees reserve start end review_date surplus',evidence=True),
 'case_approval':definition(6,'Case approval','Cases',[VERIFY,FIN,TWO,RABBI,step('Executive review','executive'),APPROVED], 'assessment_id privacy contact_permission surplus exceptions',evidence=True),
 'support_plan':definition(7,'Family-support plan','Cases',[step('Family confirmation'),CASE,FIN,step('Active')], 'case_approval_id summary start end review_date',evidence=True),
 'review':definition(8,'Case review and renewal','Cases',[FIN,CASE,RABBI,DONE], 'plan_id summary resolution review_date review_decision',evidence=True),
 'supporter':definition(9,'Supporter-tree review','Fundraising',[step('Relationship verified','case_admin'),step('Contact permitted','case_admin'),step('Assigned to fundraiser','fundraising'),step('Ready for outreach')], 'contact_id summary'),
 'fundraising_plan':definition(10,'Fundraising-plan approval','Fundraising',[PRIV,CASE,step('Active')], 'plan_id disclosure monthly_goal overall_goal'),
 'outreach':definition(11,'Supporter outreach','Fundraising',[step('Contact attempted'),step('Reached'),step('Follow-up'),DONE], 'contact_id communication follow_up'),
 'pledge':definition(12,'Pledge','Fundraising',[step('Confirmed'),step('Payment setup pending'),step('Active')], 'contact_id amount frequency start end payment_method restrictions anonymous receipt_preference confirmed'),
 'collection':definition(13,'Donation collection','Finance',[step('Payment scheduled'),step('Processing','finance'),step('Collected','finance'),step('Posted','finance'),step('Receipt issued','finance'),step('Reconciled','finance')], 'contact_id amount reference restrictions payment_method receipt_preference',evidence=True),
 'donor_service':definition(14,'Donor service','Fundraising',[step('Assigned'),step('Resolved'),step('Donor notified'),DONE], 'contact_id reason resolution notification'),
 'expense':definition(15,'Expense request','Finance',[step('Submitted'),CASE,FIN,step('Approved'),step('Scheduled','payment_approver'),step('Payment release','payment_releaser'),step('Paid','finance'),step('Reconciled')], 'plan_id vendor_id amount invoice month category expense_type related_party cash direct_family reason',evidence=True),
 'exception_approval':definition(16,'Expense exception approval','Finance',[FIN,TWO,RABBI,step('Executive review','executive'),APPROVED], 'source_id reason',evidence=True),
 'allocation':definition(17,'Organization-expense allocation','Finance',[CASE,FIN,APPROVED], 'source_id allocation amount',evidence=True),
 'vendor':definition(18,'Vendor approval','Finance',[VERIFY,step('Payment details verified','finance'),APPROVED], 'payee banking stripe_account summary',org=True,evidence=False),
 'payment_batch':definition(19,'Payment batch','Finance',[FIN,step('Batch approved','payment_approver'),step('Release recorded','payment_releaser'),DONE], 'summary reference batch_items',org=True,evidence=True),
 'reconciliation':definition(20,'Bank reconciliation','Finance',[FIN,step('Matched','finance'),step('Reconciled')], 'ledger_id bank_ref bank_date bank_amount',evidence=True),
 'refund':definition(21,'Refund or chargeback','Finance',[FIN,TWO,step('Release recorded','payment_releaser'),DONE], 'source_id amount reason reference notification',evidence=True),
 'transfer':definition(22,'Inter-case transfer','Finance',[FIN,RABBI,step('Transfer posted','payment_releaser'),DONE], 'target_family amount reason donor_authorization reference',evidence=True),
 'emergency':definition(23,'Emergency assistance','Oversight',[VERIFY,RABBI,CASE,step('Immediate payment','payment_releaser'),step('Documentation review','compliance'),DONE], 'vendor_id amount reason reference deadline',evidence=True),
 'complaint':definition(24,'Complaint and safeguarding','Oversight',[step('Risk classified','compliance'),step('Investigation','compliance'),step('Decision','executive'),step('Corrective action','compliance'),DONE], 'risk reason resolution',restricted=True),
 'conflict':definition(25,'Conflict of interest','Oversight',[PRIV,step('Recusal recorded','compliance'),DONE], 'conflict_user relationship reason',restricted=True),
 'unusual':definition(26,'Unusual activity','Oversight',[step('Payment held','compliance'),FIN,PRIV,step('Decision','executive'),DONE], 'source_id risk resolution',restricted=True,evidence=True),
 'onboarding':definition(27,'User onboarding','Organization',[VERIFY,step('Training completed','compliance'),step('Access approved','executive'),DONE], 'user_id training',org=True),
 'access_change':definition(28,'Staff departure or role change','Organization',[step('Manager approval','executive'),step('Access reviewed','compliance'),step('Assignments transferred','executive'),DONE], 'user_id access_change new_role handover reason',org=True),
 'task':definition(29,'Task and escalation','Cases',[step('In progress'),step('Waiting on third party'),DONE], 'summary documents dependency_id escalation_user'),
 'document':definition(30,'Document review','Cases',[step('Classified'),PRIV,step('Reviewed','case_admin'),APPROVED], 'document_id document_privacy document_category previous_document',evidence=False),
 'case_report':definition(31,'Per-case transparency report','Reporting',[FIN,TWO,RABBI,DONE], 'period summary',evidence=True),
 'org_report':definition(32,'Organization-wide report','Reporting',[FIN,step('Executive review','executive'),DONE], 'period summary',org=True),
 'audit':definition(33,'Audit','Oversight',[step('Period locked','auditor'),step('Transactions reviewed','auditor'),step('Management response','executive'),step('Corrective action','compliance'),step('Audit closed','auditor'),DONE], 'period audit_findings',org=True),
 'closure':definition(34,'Case closure','Cases',[step('Collections stopping','fundraising'),step('Financial reconciliation','finance'),FIN,TWO,RABBI,step('Closed')], 'reason surplus notification',evidence=True),
 'reopening':definition(35,'Reopening a case','Cases',[VERIFY,FIN,RABBI,step('Reopened')], 'reason assessment_id summary',evidence=True),
}
FINANCIAL = {'expense','emergency','refund','transfer','payment_batch','unusual'}
FUNDRAISER_KINDS={'outreach','pledge','donor_service'}
TERMINAL={'Completed','Approved','Active','Ready for outreach','Reconciled','Closed','Reopened'}

for key,label in [('verify_income','Income verification'),('verify_housing','Housing verification'),('verify_tuition','Tuition verification'),('verify_utilities','Utilities verification'),('verify_assistance','Outside assistance verification'),('verify_family','Household composition verification'),('verify_reference','Community reference verification'),('verify_vendor','Vendor balance verification')]:
    FIELDS[key]=('choice',label,True)
    CHOICES[key]=['Verified','Partially verified','Documentation requested','Unable to verify','Not applicable']
CHOICES['review_decision']=['Continue unchanged','Reassess assistance','Request documents','Pause assistance','Pause fundraising','Begin closure']

FIELDS['stripe_account']=('text','Stripe connected account ID',False)
