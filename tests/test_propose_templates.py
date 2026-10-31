import json

import pytest

pytest.importorskip('sklearn')
from scripts.propose_templates import load, propose, reply_template  # noqa: E402


def ticket(text, reply, kind='report'):
    return {'kind': kind, 'messages': [{'role': 'player', 'text': text}, {'role': 'admin', 'text': reply}]}


def test_reply_template_removes_player_specific_parts():
    assert reply_template('Приветствую, слежу за игроком Vera_Sadykov[331].') == 'Приветствую, слежу за игроком {nick}[{n}].'
    assert reply_template('Ваша жалоба #<digits> рассмотрена  Egor_Gray58') == 'Ваша жалоба {n} рассмотрена {nick}'


def test_templates_come_from_admin_replies_and_need_approval(tmp_path):
    rows = []
    for i in range(60):
        rows.append(ticket(f'застрял в текстурах помогите вытащить {i}', 'Приветствую, спешу на помощь.'))
        rows.append(ticket(f'как получить права где автошкола {i}', 'Приветствую, автошкола в навигаторе.'))
    path = tmp_path / 'train.jsonl'
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    report = propose(load(path, 'report', 1000), 'report', clusters=2)
    assert report['tickets'] == 120 and len(report['clusters']) == 2
    templates = {c['candidates'][0]['template'] for c in report['clusters']}
    assert templates == {'Приветствую, спешу на помощь.', 'Приветствую, автошкола в навигаторе.'}
    assert all(c['approved'] is None and c['candidates'][0]['share'] == 1.0 for c in report['clusters'])
    with pytest.raises(ValueError):
        propose(load(path, 'report', 1000)[:5], 'report', clusters=12)
