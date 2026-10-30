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


def test_attachments_raise_review_priority_without_proving_violation():
    result = route('complaint.insult', 'Оскорбление', has_attachments=True)
    assert result.priority == 'p1'
    assert result.needs_human
    assert 'attachments_require_review' in result.reasons


def test_mechanics_question_stays_low_priority():
    assert route('report.question', 'Где находится магазин?').priority == 'p3'
