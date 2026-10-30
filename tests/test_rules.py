from app.rules import RuleIndex
from app.core import TriageService


def index(points):
    return RuleIndex.from_data({'rules': [dict(id=section, category='Раздел', points=[dict(ref='8.8', text=text)])
                                         for section, text in points]})


def test_section_is_selected_by_content_not_fixed_number():
    rules = index([(99, 'Запрещено использовать читы.'), (30, 'Определение игровой зоны.')])
    result = TriageService(rules).triage(dict(kind='complaint', rule_refs_raw='8.8, 8.8',
        messages=[dict(role='player', text='Игрок использует читы')]))
    assert len(result['draft_reply']['cited']) == 1
    assert result['draft_reply']['cited'][0]['section_id'] == 99


def test_ambiguous_sections_and_permission_are_not_cited():
    rules = index([(1, 'Запрещены читы.'), (2, 'Запрещены читы на мероприятии.')])
    assert rules.relevant_rule('читы', 'complaint.cheat', '8.8') is None
    assert index([(1, 'Читы не запрещены.')]).search('читы', 'complaint.cheat') == []
    assert index([(1, 'Разрешено использовать читы.')]).search('читы', 'complaint.cheat') == []


def test_changed_rule_and_forged_excerpt_fail_validation():
    old = index([(1, 'Запрещены читы.')])
    citation = old.rules[0].citation()
    assert old.validate_citation(citation)
    assert not index([(1, 'Запрещены оскорбления.')]).validate_citation(citation)
    assert not old.validate_citation({**citation, 'excerpt': 'Выдуманный текст'})
    assert old.relevant_rule('читы', 'complaint.cheat', '9.9') is None
