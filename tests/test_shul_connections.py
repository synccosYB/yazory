import pytest

from app import (
    FamilyGabbaiConnection,
    FamilyRabbiConnection,
    Institution,
    ShulGabbaiDirectory,
    ShulRabbi,
    create_app,
    db,
)


@pytest.fixture
def app(monkeypatch):
    for key in ['APP_ENV', 'DATABASE_URL', 'ADMIN_EMAIL', 'ADMIN_PASSWORD_HASH', 'SESSION_SECRET']:
        monkeypatch.delenv(key, raising=False)
    return create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'test-only',
    })


@pytest.fixture
def client(app):
    return app.test_client()


def post(client, path, data):
    client.get('/')
    with client.session_transaction() as session:
        csrf = session['csrf']
    return client.post(path, data={**data, 'csrf': csrf})


def add_shuls(app):
    with app.app_context():
        db.session.add_all([
            Institution(kind='Shul', name='Weekday Test Shul', city='Monroe'),
            Institution(kind='Shul', name='Shabbos Test Shul', city='Monroe'),
        ])
        db.session.commit()


def test_applicant_can_inherit_different_rabbis_and_multiple_gabbais_from_two_shuls(app, client):
    add_shuls(app)

    response = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'weekday_shul_rabbi': 'Rabbi Weekday',
        'weekday_shul_rabbi_phone': '845-555-1001',
        'weekday_shul_gabbai_name': ['Gabbai One', 'Gabbai Two'],
        'weekday_shul_gabbai_phone': ['845-555-2001', '845-555-2002'],
        'shabbos_shul': 'Shabbos Test Shul',
        'shabbos_shul_rabbi': 'Rabbi Shabbos',
        'shabbos_shul_rabbi_phone': '845-555-1002',
        'shabbos_shul_gabbai_name': ['Gabbai Three'],
        'shabbos_shul_gabbai_phone': ['845-555-2003'],
    })
    assert response.status_code == 302

    with app.app_context():
        shuls = {
            row.name: row
            for row in db.session.scalars(db.select(Institution).where(
                Institution.kind == 'Shul',
                Institution.name.in_(('Weekday Test Shul', 'Shabbos Test Shul'))
            )).all()
        }
        weekday_rabbi = db.session.get(ShulRabbi, shuls['Weekday Test Shul'].id)
        shabbos_rabbi = db.session.get(ShulRabbi, shuls['Shabbos Test Shul'].id)
        assert (weekday_rabbi.rabbi_name, weekday_rabbi.rabbi_phone) == (
            'Rabbi Weekday', '845-555-1001')
        assert (shabbos_rabbi.rabbi_name, shabbos_rabbi.rabbi_phone) == (
            'Rabbi Shabbos', '845-555-1002')

        family_rabbis = {
            row.role: row.rabbi_name
            for row in db.session.scalars(db.select(FamilyRabbiConnection).where(
                FamilyRabbiConnection.family_id == 1,
                FamilyRabbiConnection.role.in_(('weekday_shul', 'shabbos_shul'))
            )).all()
        }
        assert family_rabbis == {
            'weekday_shul': 'Rabbi Weekday',
            'shabbos_shul': 'Rabbi Shabbos',
        }

        weekday_gabbais = db.session.scalars(db.select(ShulGabbaiDirectory).where(
            ShulGabbaiDirectory.institution_id == shuls['Weekday Test Shul'].id
        ).order_by(ShulGabbaiDirectory.id)).all()
        shabbos_gabbais = db.session.scalars(db.select(ShulGabbaiDirectory).where(
            ShulGabbaiDirectory.institution_id == shuls['Shabbos Test Shul'].id
        ).order_by(ShulGabbaiDirectory.id)).all()
        assert [(row.name, row.phone) for row in weekday_gabbais] == [
            ('Gabbai One', '845-555-2001'),
            ('Gabbai Two', '845-555-2002'),
        ]
        assert [(row.name, row.phone) for row in shabbos_gabbais] == [
            ('Gabbai Three', '845-555-2003'),
        ]

        connections = db.session.scalars(db.select(FamilyGabbaiConnection).where(
            FamilyGabbaiConnection.family_id == 1
        )).all()
        assert sorted(row.role for row in connections) == [
            'shabbos_shul', 'weekday_shul', 'weekday_shul'
        ]


def test_selecting_existing_shul_reuses_its_rabbi_and_all_gabbais_for_each_family_role(app, client):
    add_shuls(app)

    first = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'weekday_shul_rabbi': 'Rabbi Existing',
        'weekday_shul_rabbi_phone': '845-555-3001',
        'weekday_shul_gabbai_name': ['First Gabbai', 'Second Gabbai'],
        'weekday_shul_gabbai_phone': ['845-555-4001', '845-555-4002'],
    })
    assert first.status_code == 302

    # Simulate selecting the already-known shul later. The browser normally fills
    # these fields from the shul directory, but the backend must also preserve the
    # canonical shul assignments when the repeated fields are not resubmitted.
    second = post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'shabbos_shul': 'Weekday Test Shul',
    })
    assert second.status_code == 302

    with app.app_context():
        shul = db.session.scalar(db.select(Institution).where(
            Institution.kind == 'Shul', Institution.name == 'Weekday Test Shul'))
        rabbi = db.session.get(ShulRabbi, shul.id)
        assert rabbi.rabbi_name == 'Rabbi Existing'

        family_rabbis = db.session.scalars(db.select(FamilyRabbiConnection).where(
            FamilyRabbiConnection.family_id == 1,
            FamilyRabbiConnection.role.in_(('weekday_shul', 'shabbos_shul'))
        )).all()
        assert {(row.role, row.rabbi_name) for row in family_rabbis} == {
            ('weekday_shul', 'Rabbi Existing'),
            ('shabbos_shul', 'Rabbi Existing'),
        }

        gabbais = db.session.scalars(db.select(ShulGabbaiDirectory).where(
            ShulGabbaiDirectory.institution_id == shul.id
        ).order_by(ShulGabbaiDirectory.id)).all()
        assert [row.name for row in gabbais] == ['First Gabbai', 'Second Gabbai']

        connections = db.session.scalars(db.select(FamilyGabbaiConnection).where(
            FamilyGabbaiConnection.family_id == 1
        )).all()
        assert sorted((row.role, row.gabbai.name) for row in connections) == [
            ('shabbos_shul', 'First Gabbai'),
            ('shabbos_shul', 'Second Gabbai'),
            ('weekday_shul', 'First Gabbai'),
            ('weekday_shul', 'Second Gabbai'),
        ]


def test_shul_directory_apis_return_saved_rabbi_and_gabbais(app, client):
    add_shuls(app)
    assert post(client, '/families/1/edit', {
        'name': 'Sample family',
        'weekday_shul': 'Weekday Test Shul',
        'weekday_shul_rabbi': 'Rabbi API',
        'weekday_shul_rabbi_phone': '845-555-5001',
        'weekday_shul_gabbai_name': ['API Gabbai'],
        'weekday_shul_gabbai_phone': ['845-555-5002'],
    }).status_code == 302

    rabbis = client.get('/api/shul-rabbis').get_json()
    gabbais = client.get('/api/shul-gabbais').get_json()
    assert rabbis['Weekday Test Shul'] == {
        'name': 'Rabbi API', 'phone': '845-555-5001'}
    assert gabbais['Weekday Test Shul'] == [
        {'name': 'API Gabbai', 'phone': '845-555-5002'}]
