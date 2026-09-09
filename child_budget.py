"""Editable planning assumptions, never represented as published cost standards."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import date
CATEGORIES = [('housing','Housing'),('taxes','Property taxes'),('utilities','Utilities'),('phone','Phone and internet'),('food','Groceries and household supplies'),('tuition','Tuition'),('childcare','Childcare'),('transport','Transportation'),('insurance','Insurance'),('medical','Medical'),('clothing','Clothing'),('upkeep','Home upkeep'),('debt','Debt payments'),('children','Children’s additional needs'),('holidays','Shabbos, Yom Tov and simchos'),('other','Other necessities')]
COMPONENTS = [r for r in CATEGORIES if r[0] in ('food','tuition','childcare','transport','medical','clothing','children','holidays')]
BANDS = ['0–2','3–5','6–9','10–13','14–17','18–30']
def band(age):
    return next(i for i, top in enumerate((2,5,9,13,17,30)) if age <= top)
def money(value):
    if value in ('',None): return None
    try:
        n=Decimal(str(value))
        if not n.is_finite() or n<0 or n>1000000 or n.as_tuple().exponent < -2: raise ValueError()
        return int(n*100)
    except (ValueError, InvalidOperation):
        raise ValueError('Enter a valid amount with up to two decimal places, no greater than $1,000,000.')
def monthly(amount, period):
    return None if amount is None else int((Decimal(amount)/ (12 if period=='annual' else 1)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
def parse(form, children):
    data={'categories':{},'rates':{},'children':{}}
    for key,_ in CATEGORIES:
        period=form.get('period_'+key,'monthly')
        if period not in ('monthly','annual'): raise ValueError('Invalid budget period.')
        data['categories'][key]={'amount':money(form.get('actual_'+key)), 'period':period}
    for i in range(len(BANDS)):
        data['rates'][str(i)]={key:money(form.get(f'rate_{i}_{key}')) for key,_ in COMPONENTS}
    for child in children:
        dob=form.get(f'dob_{child.id}','').strip()
        age=form.get(f'age_{child.id}',str(child.age))
        if not age.isdecimal() or not 0<=int(age)<=30: raise ValueError('Age must be between 0 and 30.')
        if dob:
            try: born=date.fromisoformat(dob)
            except ValueError: raise ValueError('Enter a valid birth date.')
            today=date.today()
            years=today.year-born.year-((today.month,today.day)<(born.month,born.day))
            if born>today or not 0<=years<=30: raise ValueError('Enter a valid birth date.')
        data['children'][str(child.id)]={'dob':dob,'age':int(age),'amounts':{key:money(form.get(f'child_{child.id}_{key}')) for key,_ in COMPONENTS}}
    return data

def calculate(data, intake, children, fallback_bands=None):
    data=data or {}; intake=intake or {}; child_rows=[]
    estimates={key:0 for key,_ in COMPONENTS}; actual_children={key:0 for key,_ in COMPONENTS}; missing=0
    for child in children:
        saved=data.get('children',{}).get(str(child.id),{})
        dob=saved.get('dob',''); age=child.age
        if dob:
            born=date.fromisoformat(dob); today=date.today()
            age=today.year-born.year-((today.month,today.day)<(born.month,born.day))
        index=band(min(30,age)); parts=[]
        saved_amounts=saved.get('amounts', {})
        rate_values=data.get('rates',{}).get(str(index),{})
        # Controls provide one conservative fallback, in Children’s additional
        # needs only, when this child has no detailed rate or override at all.
        has_detail=any(saved_amounts.get(key) is not None or rate_values.get(key) is not None
                       for key,_ in COMPONENTS)
        fallback=None
        if not has_detail:
            for item in fallback_bands or []:
                if int(item['min_age']) <= age <= int(item['max_age']):
                    fallback=int(item['amount_cents']); break
        for key,label in COMPONENTS:
            override=saved_amounts.get(key)
            rate=rate_values.get(key)
            value=override if override is not None else rate
            if value is None and key == 'children' and fallback is not None:
                value=fallback
            if override is not None: actual_children[key]+=value or 0
            else: estimates[key]+=value or 0
            parts.append(dict(key=key,label=label,amount=value,override=override))
        child_rows.append(dict(child=child,age=age,dob=dob,band=BANDS[index],parts=parts,total=sum(x['amount'] or 0 for x in parts)))
    provider={key:0 for key,_ in CATEGORIES}; known=set(); unclassified=0
    for account in intake.get('accounts',[]):
        treatment=account.get('budget_treatment')
        if treatment not in ('additional','rent','food') or account.get('monthly_bill') is None:
            unclassified+=1; continue
        if treatment!='additional': continue
        key={'utility':'utilities','grocery':'food','mosdos':'tuition'}.get(account.get('kind'),'other')
        known.add(key); provider[key]+=account['monthly_bill']
    rows=[]
    for key,label in CATEGORIES:
        entry=data.get('categories',{}).get(key,{})
        actual=monthly(entry.get('amount'),entry.get('period','monthly'))
        legacy=intake.get({'housing':'rent','food':'food'}.get(key,''))
        # Explicit category totals supersede provider bills and child estimates.
        if actual is not None: value=actual; source='Actual household total'
        elif legacy is not None or key in known: value=(legacy or 0)+provider[key]; source='Saved household bills'
        elif key in estimates and children:
            value=estimates[key] + actual_children[key]; source='Child estimate'
            missing+=sum(part['amount'] is None for child in child_rows for part in child['parts'] if part['key']==key)
        else: value=None; source='Not entered'
        missing+=value is None
        rows.append(dict(key=key,label=label,amount=value,source=source))
    income=sum(intake.get(k) or 0 for k in ('his_income','her_income','other_income'))
    missing+=sum(intake.get(k) is None for k in ('his_income','her_income','other_income'))
    missing+=sum(intake.get(k) not in ('yes','no') for k in ('foodstamps','other_assistance'))
    missing+=int(intake.get('children_count') is not None and intake['children_count']!=len(children))
    missing+=int(intake.get('foodstamps')=='yes' and intake.get('foodstamps_amount') is None)
    if intake.get('other_assistance')=='yes':
        missing+=int(not intake.get('assistance'))
        missing+=sum(r.get('amount') is None for r in intake.get('assistance',[]))
    assistance=sum(r.get('amount') or 0 for r in intake.get('assistance',[]) if intake.get('other_assistance')!='no')
    stamps=(intake.get('foodstamps_amount') or 0) if intake.get('foodstamps')=='yes' else 0
    food=next(r['amount'] or 0 for r in rows if r['key']=='food')
    assistance+=min(stamps,food)
    total=sum(r['amount'] or 0 for r in rows)
    child_keys={key for key,_ in COMPONENTS}
    child_row_keys={row['key'] for row in rows if row['key'] in child_keys and row['source']=='Child estimate'}
    estimated_children=sum(estimates[key] for key in child_row_keys)
    actual_child_amounts=sum(actual_children[key] for key in child_row_keys)
    household_bills=total-estimated_children-actual_child_amounts
    return dict(rows=rows,children=child_rows,costs=total,earnings=income,usable_help=assistance,
                gap=max(0,total-income-assistance),missing=missing+unclassified,
                household_bills=household_bills, child_estimates=estimated_children,
                actual_child_amounts=actual_child_amounts)
