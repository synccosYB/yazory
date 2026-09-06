"""Current household budget snapshot; all arithmetic uses integer cents."""
TREATMENTS = {'additional': 'Add to monthly expenses', 'food': 'Already included in food',
              'rent': 'Already included in rent'}


def household_report(data):
    b = data or {}
    expenses = [{'label': label, 'amount': b.get(key), 'treatment': 'Add to monthly expenses'}
                for key, label in [('rent', 'Monthly rent or mortgage ($)'), ('food', 'Monthly food costs ($)')]]
    missing = sum(row['amount'] is None for row in expenses)
    for account in b.get('accounts', []):
        amount = account.get('monthly_bill')
        treatment = account.get('budget_treatment', '')
        missing += int(amount is None or treatment not in TREATMENTS)
        expenses.append({'label': account.get('provider', ''), 'amount': amount,
                         'treatment': TREATMENTS.get(treatment, 'Choose how to count this bill')})
    income = [{'label': label, 'amount': b.get(key)} for key, label in [
        ('his_income', 'His monthly income ($)'), ('her_income', 'Her monthly income ($)'),
        ('other_income', 'Other monthly income ($)')]]
    missing += sum(row['amount'] is None for row in income)
    assistance = []
    for flag in ('foodstamps', 'other_assistance'):
        missing += int(b.get(flag) not in ('yes', 'no'))
    if b.get('foodstamps') == 'yes':
        assistance.append({'label': 'Monthly food stamps ($)', 'amount': b.get('foodstamps_amount')})
    if b.get('other_assistance') != 'no':
        assistance.extend({'label': r.get('provider', ''), 'amount': r.get('amount')} for r in b.get('assistance', []))
    missing += sum(row['amount'] is None for row in assistance)
    if b.get('other_assistance') == 'yes' and not b.get('assistance'):
        missing += 1
    costs = sum(r['amount'] or 0 for r in expenses if r['treatment'] == 'Add to monthly expenses')
    earnings = sum(r['amount'] or 0 for r in income)
    help_total = sum(r['amount'] or 0 for r in assistance)
    food_costs = (b.get('food') or 0) + sum(r.get('monthly_bill') or 0 for r in b.get('accounts', [])
                       if r.get('kind') == 'grocery' and r.get('budget_treatment') == 'additional')
    stamps = (b.get('foodstamps_amount') or 0) if b.get('foodstamps') == 'yes' else 0
    usable_help = help_total - stamps + min(stamps, food_costs)
    balance = costs - earnings - usable_help
    return dict(expenses=expenses, income=income, assistance=assistance, costs=costs,
                earnings=earnings, help_total=help_total, usable_help=usable_help,
                income_gap=max(0, costs-earnings), gap=max(0, balance), surplus=max(0, -balance), missing=missing)
