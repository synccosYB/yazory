from pathlib import Path

from app_entry import create_app


def test_communications_mobile_cards_have_localized_field_labels():
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SECRET_KEY': 'screen-contract-test',
    })
    client = app.test_client()

    for language, direction in [('en', 'ltr'), ('he', 'rtl'), ('yi', 'rtl')]:
        client.get(f'/language/{language}?next=/communications')
        page = client.get('/communications').text
        assert f'dir="{direction}"' in page
    # The isolated app has no supporter rows, so verify the repeated accordion
    # source independently. Jinja translates each label in the active request.
    source = (Path(__file__).resolve().parents[1] / 'templates/communications.html').read_text()
    assert 'communication-accordion-item outreach-supporter' in source
    for label in ['Supporter', 'Contact', 'Current step', 'Actions']:
        assert "{{ _('" + label + "') }}" in source


def test_visual_ci_covers_required_layout_modes():
    root = Path(__file__).resolve().parents[1]
    visual_test = (root / 'tests/visual/layout.spec.js').read_text()
    workflow = (root / '.github/workflows/ci.yml').read_text()

    for mode in ('desktop', 'mobile', 'zoom-200'):
        assert mode in visual_test
    for locale in ("'he'", "'yi'"):
        assert locale in visual_test
    assert 'npm run test:visual' in workflow


def test_communications_section_names_are_translated_in_all_locales():
    from translations import CATALOG

    labels = (
        'New applicant messages',
        'Portal messages and direct email replies waiting for staff review.',
        'Applicant communication history',
        'Every portal message and direct applicant email reply.',
        'Supporter communication history',
    )
    assert not [
        label for label in labels
        if label not in CATALOG or not all(CATALOG[label].get(locale) for locale in ('he', 'yi'))
    ]


def test_supporter_tree_names_link_to_profiles_and_table_is_searchable():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/supporter_network.html').read_text()
    assert 'data-table-search="supporter-network-table"' in template
    assert 'id="supporter-network-table"' in template
    assert "url_for('supporter_detail',contact_id=row.contact.id)" in template
    assert "url_for('supporter_detail',contact_id=row.through.id)" in template


def test_supporter_directory_uses_expandable_records_without_table_pagination():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/supporters.html').read_text()
    css = (root / 'static/style.css').read_text()
    assert 'class="supporter-accordion"' in template
    assert 'class="supporter-accordion-item' in template
    assert 'class="supporter-accordion-panel"' in template
    assert 'class="card supporter-list-card foldable-supporter-list"' in template
    assert 'class="supporter-list-summary"' in template
    assert '<table>' not in template
    assert '.supporter-accordion-item>summary' in css
    assert '.supporter-list-summary' in css


def test_imported_people_directory_uses_the_same_foldable_accordion_pattern():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/supporter_directory.html').read_text()
    css = (root / 'static/style.css').read_text()
    assert 'class="card supporter-list-card foldable-supporter-list"' in template
    assert 'class="supporter-accordion supporter-directory-accordion"' in template
    assert 'class="supporter-accordion-item"' in template
    assert 'class="supporter-accordion-panel"' in template
    assert '<table>' not in template
    assert 'supporter-directory-connect' in template
    assert '.supporter-directory-connect' in css


def test_network_people_list_is_compact_searchable_and_not_hierarchy_indented():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/directories.html').read_text()
    script = (root / 'static/pages.js').read_text()
    assert 'class="network-panel network-people-panel"' in template
    assert 'class="network-list network-people-list"' in template
    assert 'data-list-search="network-people-{{ institution.id }}"' in template
    assert 'data-list-item' in template
    assert '.network-people-list{max-height:420px;overflow-y:auto' in template
    assert "{% if kind == 'Yeshivah' %} depth-" in template
    assert "document.querySelectorAll('[data-list-search]')" in script


def test_dashboard_uses_translated_labels_and_keeps_preview_rows_visible():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/dashboard.html').read_text()
    script = (root / 'static/pages.js').read_text()
    assert 'אלע cases' not in template
    assert '_("All cases")' in template
    assert 'class="overview-grid dashboard-overview"' in template
    assert "dashboard-overview table" in script


def test_family_name_is_the_only_profile_link_in_family_table():
    root = Path(__file__).resolve().parents[1]
    macro = (root / 'templates/macros.html').read_text().splitlines()[3]
    assert macro.count('href="/families/{{ f.id }}"') == 1
    assert '_("View →")' not in macro
    assert 'colspan="4"' in macro


def test_family_profile_actions_and_summary_reflow_without_losing_controls():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/family.html').read_text()
    script = (root / 'static/pages.js').read_text()
    css = (root / 'static/style.css').read_text()
    assert "staff_applicant_messages" in template
    assert "family.id }}/edit" in template
    assert "profileStatus.addEventListener('change'" in script
    assert ".profile-sheet-layout{display:flex;flex-direction:column}" in css
    assert ".page-panels{flex-wrap:nowrap;overflow-x:auto" in css


def test_family_supporter_list_groups_tools_and_formats_phone_numbers():
    root = Path(__file__).resolve().parents[1]
    script = (root / 'static/pages.js').read_text()
    css = (root / 'static/style.css').read_text()
    assert "tools.append(count)" in script
    assert "digits?.length===10" in script
    assert "familySupporterTable.classList.add('family-supporters-table')" in script
    assert "editLink.className='supporter-row-edit'" in script
    assert "editCell.remove()" in script
    assert "familyMinimum=table.classList.contains('family-supporters-table')" in script
    assert '.family-supporters-table{table-layout:fixed' in css


def test_children_screen_uses_compact_records_without_losing_edit_forms():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/_children.html').read_text()
    css = (root / 'static/style.css').read_text()
    assert 'class="child-record" data-page-item' in template
    assert 'action="/children/{{ c.id }}"' in template
    assert 'class="add-child-record"' in template
    assert '.child-records{display:grid;grid-template-columns:repeat(2' in css
