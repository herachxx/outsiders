"""Transactional, idempotent history of exact normalized problems; no raw text."""
import hashlib
import json
import sqlite3
import threading

from .preprocess import normalize, player_text

SIMILARITY = 0.7   # share of identical words that makes two messages the same problem


def token_hashes(text):
    """Hashed word set of a message (no text is stored); short fragments yield too little to compare."""
    words = {w for w in text.split() if len(w) > 2}
    return {hashlib.sha1(w.encode()).hexdigest()[:8] for w in words} if len(words) >= 3 else set()


def parse_tokens(stored):
    return set(stored.split()) if stored else set()


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


class History:
    def __init__(self, path=':memory:'):
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.connection.execute('CREATE TABLE IF NOT EXISTS history (id TEXT PRIMARY KEY, ts REAL, problem TEXT, count INTEGER, scope TEXT, tokens TEXT)')
        for column in ('scope', 'tokens'):   # databases created before near-duplicate detection
            try:
                self.connection.execute(f'ALTER TABLE history ADD COLUMN {column} TEXT')
            except sqlite3.OperationalError:
                pass
        self.connection.execute('CREATE INDEX IF NOT EXISTS history_lookup ON history(problem, ts)')
        self.connection.execute('CREATE INDEX IF NOT EXISTS history_scope ON history(scope, ts)')

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
            # Same reporter, kind, region and target within the hour: identical text or a near copy of it.
            scope = hashlib.sha256(json.dumps([request.reporter_hash, request.kind, request.region,
                                               request.reported_hash or request.reported_nick]).encode()).hexdigest()
            tokens = token_hashes(text)
            recent = self.connection.execute('SELECT problem, tokens FROM history WHERE scope=? AND ts>=? AND ts<=?',
                                             (scope, timestamp - 3600, timestamp)).fetchall()
            similar = sum(1 for other_problem, other in recent
                          if other_problem == problem or jaccard(tokens, parse_tokens(other)) >= SIMILARITY)
            count = 1 + similar
            self.connection.execute('INSERT INTO history VALUES (?,?,?,?,?,?)',
                                    (identity, timestamp, problem, count, scope, ' '.join(sorted(tokens))))
            return count

    def close(self):
        self.connection.close()
