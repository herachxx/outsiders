"""Administrator decisions on service output; ids and labels only, no ticket text."""
import sqlite3
import threading
import time

ACTIONS = ('approved', 'edited', 'rejected')


class Decisions:
    def __init__(self, path=':memory:'):
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.connection.execute(
            'CREATE TABLE IF NOT EXISTS decisions (ticket_id TEXT PRIMARY KEY, created REAL, system_category TEXT, '
            'system_priority TEXT, handling TEXT, action TEXT, admin_category TEXT, admin_priority TEXT, decided REAL)')

    def propose(self, ticket_id, category, priority, handling):
        """Remember what the service said; re-sending the same ticket keeps an existing decision."""
        with self.lock, self.connection:
            row = self.connection.execute('SELECT action FROM decisions WHERE ticket_id=?', (ticket_id,)).fetchone()
            if row and row[0]:
                return
            self.connection.execute('INSERT OR REPLACE INTO decisions (ticket_id, created, system_category, '
                                    'system_priority, handling) VALUES (?,?,?,?,?)',
                                    (ticket_id, time.time(), category, priority, handling))

    def decide(self, ticket_id, action, category=None, priority=None):
        if action not in ACTIONS:
            raise ValueError('Unknown action')
        if action == 'edited' and not (category or priority):
            raise ValueError('An edit needs a corrected category or priority')
        with self.lock, self.connection:
            row = self.connection.execute('SELECT system_category, system_priority FROM decisions WHERE ticket_id=?',
                                          (ticket_id,)).fetchone()
            if row is None:
                raise KeyError(ticket_id)
            final_category = category or row[0]
            final_priority = priority or row[1]
            self.connection.execute('UPDATE decisions SET action=?, admin_category=?, admin_priority=?, decided=? '
                                    'WHERE ticket_id=?', (action, final_category, final_priority, time.time(), ticket_id))

    def stats(self):
        rows = self.connection.execute('SELECT handling, action, system_category, admin_category, system_priority, '
                                       'admin_priority FROM decisions').fetchall()
        decided = [r for r in rows if r[1]]
        by_handling = {}
        for handling, action, *_ in decided:
            cell = by_handling.setdefault(handling, {'decided': 0, 'approved': 0, 'edited': 0, 'rejected': 0})
            cell['decided'] += 1
            cell[action] += 1
        for cell in by_handling.values():
            cell['approval_rate'] = round(cell['approved'] / cell['decided'], 3)
        category_ok = sum(1 for r in decided if r[2] == r[3])
        priority_ok = sum(1 for r in decided if r[4] == r[5])
        return {'proposed': len(rows), 'decided': len(decided), 'by_handling': by_handling,
                'category_agreement': round(category_ok / len(decided), 3) if decided else None,
                'priority_agreement': round(priority_ok / len(decided), 3) if decided else None}

    def corrections(self):
        """Administrator-corrected labels for retraining (join with ticket text on the Grand side)."""
        return [{'ticket_id': r[0], 'category': r[1], 'priority': r[2]} for r in self.connection.execute(
            "SELECT ticket_id, admin_category, admin_priority FROM decisions WHERE action IN ('approved','edited')")]

    def close(self):
        self.connection.close()
