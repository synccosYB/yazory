from supporter_network import supporter_grade


def test_supporter_grade_is_relationship_driven():
    assert supporter_grade('Sibling') == 'A'
    assert supporter_grade("Spouse’s sibling") == 'A'
    assert supporter_grade('Child of sibling') == 'B'
    assert supporter_grade('Nephew') == 'B'
    assert supporter_grade('First cousin') == 'C'
    assert supporter_grade('Second cousin') == 'C'
    assert supporter_grade('Child of first cousin') == 'D'


def test_supporter_grade_other_relationships_and_friends():
    assert supporter_grade('Uncle / aunt') == 'E'
    assert supporter_grade('Other') == 'E'
    assert supporter_grade('Friend') == 'F'
    assert supporter_grade('Shul friend') == 'F'
    assert supporter_grade('Friend from yeshiva/school') == 'F'
