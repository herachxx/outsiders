import pytest
from app.priority import route


@pytest.mark.parametrize('category', ['report.account', 'report.payment', 'complaint.admin'])
def test_sensitive_categories_always_require_human(category):
    assert route(category, 'Подробности обращения').needs_human


def test_urgent_signal_overrides_wrong_category():
    result = route('report.offtopic', 'Мой аккаунт взломали')
    assert result.priority == 'p0'
    assert result.needs_human


def test_appeal_requires_human_even_with_question_category():
    assert route('report.question', 'Прошу разбанить меня').needs_human


def test_attachments_do_not_change_priority_because_every_complaint_has_them():
    assert route('complaint.insult', 'Оскорбление', has_attachments=True).priority == 'p2'
    assert route('complaint.dm', 'убил', has_attachments=True).priority == 'p2'
    assert route('complaint.invalid', 'жб', has_attachments=True).priority == 'p3'
    assert route('complaint.cheat', 'чит', has_attachments=True).priority == 'p1'
    assert not route('complaint.insult', 'Оскорбление', has_attachments=True).needs_human
    assert route('complaint.admin', 'не согласен', has_attachments=True).needs_human
    assert route('complaint.cheat', 'Прошу разбан', has_attachments=True).needs_human


def test_mechanics_question_stays_low_priority():
    assert route('report.question', 'Где находится магазин?').priority == 'p3'
