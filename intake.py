"""Validated household budget data. Monetary values are integer cents."""
import json
from decimal import Decimal, InvalidOperation

MONEY_FIELDS = ('rent', 'food', 'his_income', 'her_income', 'other_income', 'foodstamps_amount')
TEXT_FIELDS = ('name_en', 'name_yi', 'spouse_en', 'spouse_yi')

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
    for key in TEXT_FIELDS:
        data[key] = text(key, 300 if key == 'street' else 160)
    count = text('children_count')
    if count and (not count.isdecimal() or not 0 <= int(count) <= 50):
        raise ValueError('Number of children must be between 0 and 50.')
    data['children_count'] = int(count) if count else None
    for key in ('his_employment', 'her_employment', 'his_employer', 'her_employer'):
        data[key] = text(key)
    data['foodstamps'] = text('foodstamps')
    if data['foodstamps'] not in ('', 'yes', 'no'):
        raise ValueError('Choose Yes or No for food stamps.')
    if data['foodstamps'] == 'yes' and data['foodstamps_amount'] is None:
        raise ValueError('Enter the monthly food stamp amount.')
    if data['foodstamps'] != 'yes':
        data['foodstamps_amount'] = None
    data['other_assistance'] = text('other_assistance')
    if data['other_assistance'] not in ('', 'yes', 'no'):
        raise ValueError('Choose Yes or No for other assistance.')
    for group in ('children', 'assistance', 'accounts'):
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
            if group == 'children':
                allowed = ('id', 'name_en', 'name_yi', 'age', 'grade', 'school', 'married', 'spouse_en', 'spouse_yi', 'tuition_contact')
            elif group == 'assistance':
                allowed = ('provider', 'amount')
            else:
                allowed = ('kind', 'provider', 'account', 'phone', 'child', 'monthly_bill', 'budget_treatment')
            cleaned = {}
            for key in allowed:
                value = entry.get(key, '')
                if value is None: value = ''
                if not isinstance(value, str) or len(value) > 300:
                    raise ValueError('Invalid account or assistance entry.')
                cleaned[key] = value.strip()
            if not any(cleaned.values()): continue
            if group == 'children':
                if not cleaned['name_en'] and not cleaned['name_yi']:
                    raise ValueError('Enter the child name in English or Yiddish.')
                if not cleaned['age'].isdecimal() or not 0 <= int(cleaned['age']) <= 30:
                    raise ValueError('Age must be between 0 and 30.')
                cleaned['age'] = int(cleaned['age'])
                if cleaned['married'] not in ('yes', 'no'):
                    raise ValueError('Choose whether the child is married.')
                if cleaned['married'] == 'no':
                    cleaned['spouse_en'] = cleaned['spouse_yi'] = ''
                if cleaned['id'] and not cleaned['id'].isdecimal():
                    raise ValueError('Invalid child entry.')
            elif not cleaned['provider']:
                raise ValueError('Enter the provider or organization name.')
            if group == 'assistance':
                cleaned['amount'] = money(cleaned['amount'])
                if cleaned['amount'] is None:
                    raise ValueError('Enter the monthly assistance amount.')
            elif group == 'accounts' and cleaned['kind'] not in ('utility', 'grocery', 'mosdos', 'other'):
                raise ValueError('Choose an account type.')
            if group == 'accounts':
                cleaned['monthly_bill'] = money(cleaned['monthly_bill'])
                if cleaned['budget_treatment'] not in ('', 'additional', 'food', 'rent'):
                    raise ValueError('Choose how to count this bill')
            result.append(cleaned)
        if group == 'assistance':
            if data['other_assistance'] == 'no':
                result = []
            elif data['other_assistance'] == 'yes' and not result:
                raise ValueError('Add the assistance source and monthly amount.')
        data[group] = result
    return data


def intake_for_form(data):
    data = dict(data or {})
    for key in MONEY_FIELDS:
        data[key] = '' if data.get(key) is None else f'{data[key] / 100:.2f}'
    data['accounts'] = [dict(row, monthly_bill='' if row.get('monthly_bill') is None else f"{row['monthly_bill'] / 100:.2f}") for row in data.get('accounts', [])]
    data['assistance'] = [dict(row, amount='' if row.get('amount') is None else f"{row['amount'] / 100:.2f}") for row in data.get('assistance', [])]
    data['children'] = [dict(row, age=str(row.get('age', ''))) for row in data.get('children', [])]
    return data
