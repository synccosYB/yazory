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
    assert 'data-tree-depth="{{ row.depth }}"' in template
    assert "person_name_values('supporter', row.contact)" in template
    assert "bilingual_name_fields('supporter', edit, 'name')" in template
    assert "person_number('supporter', row.contact)" in template
    assert '.supporter-tree-name[class*="depth-"]:not(.depth-0)' in (root / 'static/style.css').read_text()


def test_supporter_directory_uses_expandable_records_without_table_pagination():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/supporters.html').read_text()
    css = (root / 'static/style.css').read_text()
    assert 'class="supporter-accordion"' in template
    assert 'class="supporter-accordion-item' in template
    assert 'class="supporter-accordion-panel"' in template
    assert 'class="card supporter-list-card foldable-supporter-list"' in template
    assert 'class="supporter-list-summary"' in template
    assert 'class="print-only"' in template
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
    # Case connections are managed from the canonical person profile rather
    # than duplicating a second connection form inside every directory row.
    assert "url_for('edit_supporter_profile', profile_id=profile.id)" in template
    assert 'supporter-directory-connect' not in template


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


def test_network_applicants_and_people_use_matching_accordion_cards():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/directories.html').read_text()
    assert 'class="network-panel network-people-panel network-applicants-panel"' in template
    assert 'data-table-search="network-applicants-{{ institution.id }}"' in template
    assert 'id="network-applicants-{{ institution.id }}"' in template
    assert template.count('<summary class="network-panel-header">') == 2


def test_dashboard_uses_translated_labels_and_links_to_full_lists():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/dashboard.html').read_text()
    assert 'אלע cases' not in template
    assert '_("All cases")' in template
    assert 'class="dashboard-top"' in template
    assert 'my_tasks[:2]' in template
    assert "url_for('families')" in template
    assert 'family_table(' not in template


def test_family_name_and_case_number_link_to_the_same_profile():
    root = Path(__file__).resolve().parents[1]
    macro = (root / 'templates/macros.html').read_text().splitlines()[3]
    canonical_link = "href=\"{{ url_for('family_detail', family_id=f.id) }}\""
    assert macro.count(canonical_link) == 2
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
    assert "editLink.after(contactActions)" in script
    assert "contactActions.querySelector('.supporter-contact-panel')?.append(childForm)" in script
    assert "editCell?.querySelector(':scope > .row-actions > a[" in script
    assert '.padded:has(> details[open])>.table-wrap' in css
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
    assert 'name="home_phone"' in template
    assert 'name="cell_phone"' in template
    assert '.child-records{display:grid;grid-template-columns:repeat(2' in css


def test_supporter_navigation_has_one_global_people_entry_and_family_views():
    root = Path(__file__).resolve().parents[1]
    base = (root / 'templates/base.html').read_text()
    family = (root / 'templates/family.html').read_text()
    directory = (root / 'templates/supporter_directory.html').read_text()
    assert 'href="/supporters">{{ _("Supporters") }}' not in base
    assert "url_for('supporter_directory')" in base
    assert '{{ _("People directory") }}' in base
    assert "url_for('supporter_network', family_id=family.id)" in family
    assert "url_for('case_helper_roster', family_id=family.id)" in family
    assert "aria-label=\"{{ _('Supporter views') }}\"" in family
    assert "Back to supporters" not in directory


def test_case_workspace_matches_approved_structure():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/family.html').read_text()
    css = (root / 'static/style.css').read_text()

    assert 'class="case-workspace-header"' in template
    assert 'class="workspace-tabs case-tabs' in template
    assert 'id="case-overview"' in template
    for anchor in ('household-community', 'circle-of-support', 'case-financials', 'case-documents', 'case-activity'):
        assert f'id="{anchor}"' in template
    for label in ('Overview', 'Household', 'Support', 'Financials', 'Communications', 'Documents', 'Activity'):
        assert "{{ _('"+label+"') }}" in template
    assert 'case-overview-grid' in template
    assert 'case-attention-card' in template
    assert 'case-work-card' in template
    assert 'case-household-summary' in template
    assert 'case-support-summary' in template
    assert 'case-activity-summary' in template
    assert '.case-overview-grid{' in css
    assert '.workspace-tabs{' in css


def test_case_workspace_is_viewport_first_and_switches_panels_in_place():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/family.html').read_text()
    script = (root / 'static/pages.js').read_text()
    css = (root / 'static/style.css').read_text()

    assert 'data-case-tabs' in template
    for panel in ('overview', 'household', 'support', 'financials', 'documents', 'activity'):
        assert f'data-case-panel="{panel}"' in template
        assert f'data-case-tab="{panel}"' in template
    assert "panel.hidden=!active" in script
    assert "history.replaceState" in script
    assert 'body[data-endpoint="family_detail"]{height:100vh;overflow:hidden}' in css
    assert '.case-workspace-panel{flex:1 1 auto;min-height:0;overflow:auto' in css
    assert '.case-workspace-panel[hidden]{display:none!important}' in css


def test_case_workspace_keeps_existing_logo_asset_untouched():
    root = Path(__file__).resolve().parents[1]
    base = (root / 'templates/base.html').read_text()
    assert base.count("filename='yazory-logo-corrected.png'") >= 2


def test_case_workspace_panels_are_siblings_and_abcharity_is_financial_action():
    root = Path(__file__).resolve().parents[1]
    template = (root / 'templates/family.html').read_text()

    financial = template.index('id="case-financials"')
    support = template.index('data-case-panel="support"')
    documents = template.index('id="case-documents"')
    assert support < financial < documents
    assert 'data-panel-href="{{ url_for(\'charity_donations\'' not in template
    financial_chunk = template[financial:documents]
    assert "href=\"{{ url_for(\'charity_donations\', family_id=family.id) }}\"" in financial_chunk
    assert "{{ _('ABCharity donations') }}" in financial_chunk
