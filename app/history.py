"""Transactional, idempotent history of exact normalized problems; no raw text."""
import hashlib
import sqlite3
import threading

from .preprocess import normalize, player_text


class History:
    def __init__(self, path=':memory:'):
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.connection.execute('CREATE TABLE IF NOT EXISTS history (id TEXT PRIMARY KEY, ts REAL, problem TEXT, count INTEGER)')
        self.connection.execute('CREATE INDEX IF NOT EXISTS history_lookup ON history(problem, ts)')

    def observe(self, request, ticket_id, timestamp):
        text = normalize(player_text(request.messages))
        if not request.reporter_hash or not request.reporter_hash.strip() or not text or not ticket_id:
            return None
        # Include target and region: identical complaints against different players are different problems.
        import json
        problem = hashlib.sha256(json.dumps([request.reporter_hash, request.kind, request.region,
            request.reported_hash or request.reported_nick, text], ensure_ascii=False).encode()).hexdigest()
        identity = hashlib.sha256(ticket_id.encode()).hexdigest()
        with self.lock, self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            previous = self.connection.execute('SELECT problem, count FROM history WHERE id=?', (identity,)).fetchone()
            if previous:
                if previous[0] != problem:
                    raise ValueError('Ticket identifier reused for a different request')
                return previous[1]
            self.connection.execute('DELETE FROM history WHERE ts < ?', (timestamp - 3600,))
            count = 1 + self.connection.execute('SELECT count(*) FROM history WHERE problem=? AND ts>=? AND ts<=?',
                                                 (problem, timestamp - 3600, timestamp)).fetchone()[0]
            self.connection.execute('INSERT INTO history VALUES (?,?,?,?)', (identity, timestamp, problem, count))
            return count

    def close(self):
        self.connection.close()
