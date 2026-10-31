"""Export administrator edits from the local ticket database as a training signal (private, outside Git).

For every ticket whose draft was edited or approved, writes the generated draft, the final draft, the category and
priority the service proposed and the ticket status. Ticket text is included so the file can retrain the classifier
once an administrator also corrects the category; keep it out of the repository and delete it with the data.
"""
import argparse
import json
import os

from app.support.store import TicketStore
from scripts.sample_for_labeling import private_path


def export_edits(store, limit=100000):
    rows = []
    for item in _all(store, limit):
        detail = store.get(item['id'])
        original = detail['result']['draft_reply']['text']
        final = detail['draft_text']
        events = [e['action'] for e in store.audit(item['id'])]
        if final != original or detail['draft_approved'] or 'draft_edited' in events:
            rows.append({'ticket_id': detail['id'], 'kind': detail['request']['kind'],
                         'text': detail['request']['messages'][0]['text'], 'category': detail['result']['category'],
                         'priority': detail['result']['priority'], 'original_draft': original, 'final_draft': final,
                         'edited': final != original, 'approved': detail['draft_approved'], 'status': detail['status']})
    return rows


def _all(store, limit):
    offset, seen = 0, 0
    while seen < limit:
        page = store.list(limit=200, offset=offset)['items']
        if not page:
            return
        yield from page
        seen += len(page)
        offset += len(page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=os.environ.get('GRAND_DB_PATH', 'data/support.sqlite3'))
    parser.add_argument('--output', required=True, help='new private .jsonl file outside the repository')
    args = parser.parse_args()
    target = private_path(args.output)
    if target.exists():
        raise SystemExit('Output already exists; refusing to overwrite')
    rows = export_edits(TicketStore(args.db))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    print(json.dumps({'exported': len(rows)}))


if __name__ == '__main__':
    main()
