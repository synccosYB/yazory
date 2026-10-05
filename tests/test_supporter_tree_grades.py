from supporter_network import supporter_grade


def test_supporter_grade_follows_tree_depth():
    assert supporter_grade(0) == 'A'
    assert supporter_grade(1) == 'B'
    assert supporter_grade(2) == 'C'
    assert supporter_grade(3) == 'D'


def test_supporter_grade_is_not_relationship_driven():
    # A new independent supporter always starts at A; descendants advance by depth.
    assert supporter_grade(0) == 'A'
    assert supporter_grade(4) == 'E'
