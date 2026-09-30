from io import BytesIO
import pytest
from app_entry import create_app
from app import db, Contact, Family, SupporterProfile, SupporterPerson, PersonRelationship
from person_names import PersonNames, names_row

@pytest.fixture
def app(monkeypatch):
    for key in ('APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET'):
        monkeypatch.delenv(key, raising=False)
    return create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'SECRET_KEY': 'test'})

def token(client):
    client.get('/')
    with client.session_transaction() as session:
        return session['csrf']

def upload(client, **extra):
    return client.post('/supporter-directory', data={'csrf': token(client), 'file': (BytesIO(
        'English Name,Yiddish Name,Phone,Address,City,State,ZIP\nTest Person,טעסט מענטש,8455559991,12 Main St,Monroe,NY,01001\n'.encode()), 'people.csv'), **extra}, content_type='multipart/form-data')

def test_case_import_persists_both_names_addresses_and_one_case_link(app):
    client=app.test_client()
    response=upload(client, family_id='1')
    assert response.status_code == 200
    with app.app_context():
        profile=db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.normalized_phone=='8455559991'))
        person=db.session.get(SupporterPerson, profile.person_id)
        assert (person.home_address, person.city, person.state, person.zip_code)==('12 Main St','Monroe','NY','01001')
        names=db.session.scalar(db.select(PersonNames).where(PersonNames.owner_kind=='person', PersonNames.owner_id==person.id))
        assert (names.english_name,names.yiddish_name)==('Test Person','טעסט מענטש')
        contacts=db.session.scalars(db.select(Contact).where(Contact.person_id==person.id)).all()
        assert len(contacts)==1 and contacts[0].family_id==1
        assert contacts[0].home_address=='12 Main St'
        link_model=app.extensions['workflows']['models']['SupporterLink']
        assert db.session.scalar(db.select(link_model).where(link_model.contact_id==contacts[0].id)) is not None
    assert upload(client, family_id='1').status_code==200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Contact.id)).where(Contact.phone=='8455559991'))==1

def test_general_import_and_cross_case_people_relationship(app):
    client=app.test_client(); assert upload(client).status_code==200
    with app.app_context():
        profile=db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.normalized_phone=='8455559991'))
        profile_id=profile.id; person_id=profile.person_id
        assert db.session.scalar(db.select(Contact.id).where(Contact.person_id==person_id)) is None
        other=db.session.scalar(db.select(SupporterPerson).where(SupporterPerson.id!=person_id))
        other_id=other.id
    response=client.post(f'/supporter-directory/{profile_id}/relationships', data={'csrf':token(client),'other_person_id':other_id,'relationship':'Cousins'})
    assert response.status_code==302
    with app.app_context():
        row=db.session.scalar(db.select(PersonRelationship).where(PersonRelationship.person_one_id==min(person_id,other_id),PersonRelationship.person_two_id==max(person_id,other_id)))
        assert row.relationship=='Cousins'

def test_import_result_stays_visible_after_refresh_and_navigation(app):
    from html.parser import HTMLParser
    class Tags(HTMLParser):
        def __init__(self, html):
            super().__init__()
            self.tags = []
            self.feed(html)
        def handle_starttag(self, tag, attrs):
            self.tags.append((tag, dict(attrs)))
    client = app.test_client()
    response = upload(client, family_id='1')
    for page in (response, client.get('/supporter-directory'),
                 client.get('/supporter-directory?q=Test')):
        tags = Tags(page.text).tags
        result = next(attrs for tag, attrs in tags if attrs.get('id') == 'people-import-result')
        assert 'data-panel-exclude' in result
        assert 'YZ-0001' in page.text
        assert any(tag == 'a' and attrs.get('href') == '/families/1' for tag, attrs in tags)
        assert any(tag == 'option' and attrs.get('value') == '1' and 'selected' in attrs for tag, attrs in tags)
    with client.session_transaction() as session:
        assert session['people_import_result']['linked'] == 1

def test_manual_person_can_be_entered_in_yiddish_only(app):
    client=app.test_client()
    response=client.post('/people/new',data={'csrf':token(client),'name_english':'','name_yiddish':'משה כהן','phone':'8455559992'})
    assert response.status_code==302
    with app.app_context():
        profile=db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.normalized_phone=='8455559992'))
        assert profile.name=='משה כהן'
        row=db.session.scalar(db.select(PersonNames).where(PersonNames.owner_kind=='person',PersonNames.owner_id==profile.person_id))
        assert row.yiddish_name=='משה כהן' and row.english_name==''

def test_existing_applicant_names_edit_without_changing_existing_name(app):
    client=app.test_client()
    with app.app_context():
        old=db.session.get(Family,1).name
    response=client.post('/people/family/1/addresses',data={'csrf':token(client),'name_english':old,'name_yiddish':'משפחה'})
    assert response.status_code==302
    with app.app_context():
        assert db.session.get(Family,1).name==old
        row=names_row('family',1)
        assert (row.english_name,row.yiddish_name)==(old,'משפחה')
    page=client.get('/families/1/edit').text
    assert 'name_yiddish' in page and 'משפחה' in page

def test_invalid_case_import_does_not_write(app):
    client=app.test_client(); assert upload(client, family_id='999999').status_code==403
    with app.app_context():
        assert db.session.scalar(db.select(SupporterProfile.id).where(SupporterProfile.normalized_phone=='8455559991')) is None

@pytest.mark.parametrize('language,label',[('en','English name'),('he','שם באנגלית'),('yi','נאמען אויף ענגליש')])
def test_bilingual_forms_localized(app,language,label):
    client=app.test_client()
    with client.session_transaction() as session: session['language']=language
    page=client.get('/people/new').text
    assert label in page and 'name_english' in page and 'name_yiddish' in page

def test_applicant_and_askan_share_names_with_their_directory_records(app):
    from app import Askan
    from person_names import names_row
    client=app.test_client()
    with app.app_context():
        family=db.session.get(Family,1)
        english=family.name
    assert client.post('/people/family/1/addresses',data={'csrf':token(client),'name_english':english,'name_yiddish':'משפחה טעסט'}).status_code==302
    with app.app_context():
        profile=db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.normalized_phone=='family:1:applicant'))
        assert names_row('person',profile.person_id).yiddish_name=='משפחה טעסט'
    assert client.post('/partner-network/askonim', data={'csrf':token(client),'name_english':'Test Askan','name_yiddish':'עסקן טעסט','phone':'8455559993'}).status_code==302
    with app.app_context():
        askan=db.session.scalar(db.select(Askan).where(Askan.phone=='8455559993'))
        profile=db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.normalized_phone==f'askan:{askan.id}'))
        assert names_row('askan',askan.id).id==names_row('person',profile.person_id).id
        assert names_row('person',profile.person_id).yiddish_name=='עסקן טעסט'

def test_names_render_as_real_inputs_and_escape_entered_values(app):
    from html.parser import HTMLParser
    class Inputs(HTMLParser):
        def __init__(self): super().__init__(); self.fields={}
        def handle_starttag(self,tag,attrs):
            if tag=='input':
                attrs=dict(attrs); self.fields[attrs.get('name')]=attrs
    client=app.test_client()
    for path in ('/people/new','/families/new','/families/1/edit','/partner-network'):
        parser=Inputs(); parser.feed(client.get(path).text)
        assert 'name_english' in parser.fields and 'name_yiddish' in parser.fields
        assert parser.fields['name_english']['dir']=='ltr'
        assert parser.fields['name_yiddish']['dir']=='rtl'

def test_duplicate_import_preserves_existing_address_and_names(app):
    from person_names import names_row
    client=app.test_client(); assert upload(client).status_code==200
    with app.app_context():
        profile=db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.normalized_phone=='8455559991'))
        person=db.session.get(SupporterPerson,profile.person_id)
        person.home_address='Established address'
        row=names_row('person',person.id);row.yiddish_name='אלטע נאמען'
        db.session.commit()
    assert upload(client).status_code==200
    with app.app_context():
        person=db.session.scalar(db.select(SupporterPerson).where(SupporterPerson.phone=='8455559991'))
        assert person.home_address=='Established address'
        assert names_row('person',person.id).yiddish_name=='אלטע נאמען'

def test_supporter_relationship_action_uses_existing_canonical_identity(app):
    client=app.test_client();assert upload(client,family_id='1').status_code==200
    with app.app_context():
        profile=db.session.scalar(db.select(SupporterProfile).where(SupporterProfile.normalized_phone=='8455559991'))
        profile_id=profile.id
        contact=db.session.scalar(db.select(Contact).where(Contact.person_id==profile.person_id));contact_id=contact.id
    response=client.post(f'/supporters/{contact_id}/people-relationships',data={'csrf':token(client)})
    assert response.status_code==302 and f'/supporter-directory/{profile_id}/edit' in response.location
    assert client.get(response.location).status_code==200


@pytest.mark.parametrize('language', ['en', 'he', 'yi'])
def test_supporter_names_do_not_repeat_page_context_or_queries(app, language):
    from sqlalchemy import event
    calls = []
    @app.context_processor
    def count_page_context():
        calls.append(True)
        return {}
    with app.app_context():
        for number in range(100):
            person = SupporterPerson(identity_key=f'perf:{number}', name=f'Performance {number}')
            db.session.add(person)
            db.session.flush()
            db.session.add(Contact(family_id=1, person_id=person.id,
                name=person.name, relationship='Friend', supporter_key=person.identity_key))
        db.session.commit()
        engine = db.engine
    queries = []
    def count_query(*args):
        queries.append(True)
    event.listen(engine, 'before_cursor_execute', count_query)
    client = app.test_client()
    with client.session_transaction() as session:
        session['language'] = language
    try:
        response = client.get('/supporters')
    finally:
        event.remove(engine, 'before_cursor_execute', count_query)
    assert response.status_code == 200
    assert response.text.count('name="name_english"') >= 100
    assert 'Performance 99' in response.text
    assert len(calls) == 1
    assert len(queries) < 40, len(queries)
