"""Realistic multilingual scenarios (ru/kk/uz/en, cp1251 look-alikes, slang), adapted from a teammate's suite.

Only invariants that must hold are asserted: language, category, p0 for money/access, human review for sensitive topics.
"""
import pytest

from app.core import TriageService
from app.rules import RuleIndex

SERVICE = TriageService(RuleIndex([]))

# kind, text, images, language, category, priority, needs_human
SCENARIOS = [
    ('report', 'Помогите застрял в текстурах около автобазара, слапните плиз или на спавн киньте', 0, 'ru', 'report.help', 'p2', True),
    ('complaint', 'Игрок Roma_Cheater юзает рванку и аимбот на складе ВЧ, всех разносит софтом, 5.2 ОП', 1, 'ru', 'complaint.cheat', 'p1', True),
    ('complaint', 'ДБ ковшом на спавне Арзамаса игрок Danil_Voron, фрапс с /time прикрепил, накажите его', 2, 'ru', 'complaint.dm', 'p2', True),
    ('complaint', 'НонРП коп повесил 6 звезд без причины и вымогает взятку 50к, уход от рп', 1, 'ru', 'complaint.dm', 'p2', True),
    ('complaint', 'Меня кинули на авторынке, подкинули обмен БМВ М5 на копейку вместо гелика, верните машину', 1, 'ru', 'complaint.scam', 'p1', True),
    ('report', 'Купил донат на боевой пропуск 1500 рублей, деньги с Тинькофф списались а ГК не начислили, чек есть', 1, 'ru', 'report.payment', 'p0', True),
    ('report', 'Взломали мой аккаунт Azamat_Kz, сменили пароль и привязку почты, помогите восстановить доступ', 0, 'ru', 'report.account', 'p0', True),
    ('complaint', 'Администратор посадил меня в деморган на 60 минут за ДМ, хотя там была провокация, пересмотрите вердикт', 0, 'ru', 'complaint.admin', 'p2', True),
    ('report', 'Сәлеметсіз бе! Автосалонда көлік сатып ала алмай жатырмын, ақшам бар бірақ қате шығады, көмектесіңізші', 0, 'kk', None, None, None),
    ('report', '‘јлеметсіз бе! Кљмек керек, ќалай жҧмысќа орналасуѓа болады?', 0, 'kk', None, None, None),
    ('complaint', "Salom aka, o'yinda meni aldab ketishdi, moshinamni tortib oldi, skrin bor, jazolang", 1, 'uz', 'complaint.scam', 'p1', True),
    ('complaint', 'Player BadGuy is speedhacking and trolling players inside the hospital green zone, proof attached', 1, 'en', 'complaint.cheat', 'p1', True),
    ('report', 'Донат не пришел, с карты списали 2000 рублей, чек прикрепил', 1, 'ru', 'report.payment', 'p0', True),
    ('report', 'Снимите бан пожалуйста, бан ошибочный, разбаньте меня', 0, 'ru', None, None, True),
    ('report', 'Меня обманули на авторынке, верните мои 500000 рублей и машину', 0, 'ru', 'report.complaint', None, True),
    ('complaint', 'Серверде читер бар, ақшамды ұрлап кетті, шағым түсіремін дәлел бар', 1, 'kk', 'complaint.cheat', 'p1', True),
    ('report', "Akkaunt buzildi, parol o'zgardi, kira olmayapman", 0, 'uz', 'report.account', 'p0', True),
    ('report', 'Аккаунтым бұзылды, құпиясөз ауысты, кіре алмай жатырмын', 0, 'kk', 'report.account', 'p0', True),
    ('report', 'Донат түспеді, төлем жасадым, ақша келмеді', 0, 'kk', 'report.payment', 'p0', True),
]


@pytest.mark.parametrize('kind,text,images,lang,category,priority,human', SCENARIOS)
def test_realistic_scenarios(kind, text, images, lang, category, priority, human):
    result = SERVICE.triage({'kind': kind, 'images_count': images, 'messages': [{'role': 'player', 'text': text}]})
    assert result['lang'] == lang
    if category:
        assert result['category'] == category
    if priority:
        assert result['priority'] == priority
    if human is not None:
        assert result['needs_human'] is human
    assert result['draft_reply']['text'] and result['draft_reply']['lang'] in ('ru', 'kk', 'uz', 'en')
    assert 'разбан' not in result['draft_reply']['text'].lower()
