"""Validated household budget data. Monetary values are integer cents."""
import json
from decimal import Decimal, InvalidOperation

MONEY_FIELDS = ('rent', 'food', 'his_income', 'her_income', 'other_income', 'foodstamps_amount')

def validate_intake(form):
    def text(key, limit=300):
        value = form.get(key, '').strip()
        if len(value) > limit:
            raise ValueError('Intake text is too long.')
        return value
    def money(value):
        if value in ('', None):
            return None
        try:
            number = Decimal(str(value))
            if not number.is_finite() or number < 0 or number > 1000000 or number.as_tuple().exponent < -2:
                raise ValueError()
            return int(number * 100)
        except (InvalidOperation, ValueError):
            raise ValueError('Enter a valid amount with up to two decimal places, no greater than $1,000,000.')
    data = {k: money(form.get(k, '')) for k in MONEY_FIELDS}
    count = text('children_count')
    if count and (not count.isdecimal() or not 0 <= int(count) <= 50):
        raise ValueError('Number of children must be between 0 and 50.')
    data['children_count'] = int(count) if count else None
    for key in ('his_employment', 'her_employment', 'his_employer', 'her_employer'):
        data[key] = text(key)
    data['foodstamps'] = text('foodstamps')
    if data['foodstamps'] not in ('', 'yes', 'no'):
        raise ValueError('Choose Yes or No for food stamps.')
    if data['foodstamps'] != 'yes':
        data['foodstamps_amount'] = None
    data['other_assistance'] = text('other_assistance')
    if data['other_assistance'] not in ('', 'yes', 'no'):
        raise ValueError('Choose Yes or No for other assistance.')
    for group in ('assistance', 'accounts'):
        try:
            entries = json.loads(form.get(group + '_json', '[]'))
        except (ValueError, TypeError):
            raise ValueError('Invalid account or assistance entry.')
        if not isinstance(entries, list) or len(entries) > 100:
            raise ValueError('Invalid account or assistance entry.')
        result = []
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError('Invalid account or assistance entry.')
            allowed = ('provider', 'amount') if group == 'assistance' else ('kind', 'provider', 'account', 'phone', 'child', 'monthly_bill', 'budget_treatment')
            cleaned = {}
            for key in allowed:
                value = entry.get(key, '')
                if value is None: value = ''
                if not isinstance(value, str) or len(value) > 300:
                    raise ValueError('Invalid account or assistance entry.')
                cleaned[key] = value.strip()
            if not any(cleaned.values()): continue
            if group == 'assistance':
                cleaned['amount'] = money(cleaned['amount'])
            elif cleaned['kind'] not in ('', 'utility', 'grocery', 'mosdos', 'other'):
                raise ValueError('Choose an account type.')
            if group == 'accounts':
                cleaned['monthly_bill'] = money(cleaned['monthly_bill'])
                if cleaned['budget_treatment'] not in ('', 'additional', 'food', 'rent'):
                    raise ValueError('Choose how to count this bill')
            result.append(cleaned)
        if group == 'assistance':
            if data['other_assistance'] == 'no':
                result = []
        data[group] = result
    return data


def intake_for_form(data):
    data = dict(data or {})
    for key in MONEY_FIELDS:
        data[key] = '' if data.get(key) is None else f'{data[key] / 100:.2f}'
    data['accounts'] = [dict(row, monthly_bill='' if row.get('monthly_bill') is None else f"{row['monthly_bill'] / 100:.2f}") for row in data.get('accounts', [])]
    data['assistance'] = [dict(row, amount='' if row.get('amount') is None else f"{row['amount'] / 100:.2f}") for row in data.get('assistance', [])]
    return data
