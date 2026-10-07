from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_family_workspace_has_one_children_surface():
    family = (ROOT / "templates" / "family.html").read_text()
    children = (ROOT / "templates" / "_children.html").read_text()
    assert family.count("{% include '_children.html' %}") == 1
    assert "household-child-editor" not in family
    assert "household-children-table" not in family
    assert 'class="card padded household-children-card"' in family
    assert 'href="#add-child-record"' in family
    assert '<h2>{{ _("Children") }}</h2>' in children


def test_family_askan_controls_are_translated():
    translations = (ROOT / "translations.py").read_text()
    for key in ("Additional askanim", "None yet", "Add another askan", "Add askan"):
        assert f"'{key}':" in translations
