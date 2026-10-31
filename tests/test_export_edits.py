from app.core import TriageService
from app.rules import RuleIndex
from app.support.store import TicketStore
from scripts.export_edits import export_edits

RULES = {"rules": [{"id": 30, "category": "Общие", "points": [{"ref": "2.1", "text": "Запрещены оскорбления игроков."}]}]}


def test_only_edited_or_approved_drafts_are_exported_with_original_and_final_text(tmp_path):
    store = TicketStore(str(tmp_path / 'support.sqlite3'))
    service = TriageService(RuleIndex.from_data(RULES))
    def create(text):
        request = {'kind': 'complaint', 'messages': [{'role': 'player', 'text': text}], 'images_count': 1}
        ticket, _ = store.create(request, service.triage(request))
        return ticket
    untouched, edited, approved = create('оск родни один'), create('оск родни два два'), create('оск родни три три три')
    store.edit_draft(edited['id'], edited['version'], 'Исправленный текст ответа', 'operator')
    store.approve_draft(approved['id'], approved['version'], 'operator')
    rows = {r['ticket_id']: r for r in export_edits(store)}
    assert set(rows) == {edited['id'], approved['id']}
    assert rows[edited['id']]['final_draft'] == 'Исправленный текст ответа' and rows[edited['id']]['edited']
    assert rows[edited['id']]['original_draft'] != rows[edited['id']]['final_draft']
    assert rows[approved['id']]['approved'] and not rows[approved['id']]['edited']
