"""Noisy training labels from the rule point an administrator applied (violation), complaints only.

Used as extra training rows, never as features: the text is the player's message before any admin reply.
Reporters in the B1 holdout are skipped. Only five complaint classes have a usable point, so these rows
cannot teach other/invalid/admin; B1 hand labels must stay in the mix.
"""
from collections import defaultdict
import random
import re

from app.preprocess import normalize, player_text
from app.schemas import TriageRequest
from scripts.sample_for_labeling import digest, read_records

POINTS = {'2.1': 'insult', '2.4': 'insult', '2.6': 'insult', '5.2': 'cheat', '5.3': 'dm', '5.4': 'dm',
          '4.1': 'scam', '4.2': 'scam', '2.3': 'rmt_ads', '4.4': 'rmt_ads'}
SHORT = {'dm': 'dm', 'дм': 'dm', 'db': 'dm', 'дб': 'dm', 'sk': 'dm', 'tk': 'dm'}


def weak_category(violation):
    if not violation:
        return None
    lowered = violation.lower()
    point = re.search(r'(?<![\d.])(\d\.\d)(?![\d.])', lowered)
    if point and point.group(1) in POINTS and 'gz' not in lowered:
        return 'complaint.' + POINTS[point.group(1)]
    short = re.sub(r'[^a-zа-я]', '', lowered)
    return 'complaint.' + SHORT[short] if short in SHORT else None


def load_weak_rows(train_path, cap=400, seed=7, split_seed=42):
    """Up to `cap` rows per class, shuffled with `seed`; B1 holdout reporters excluded."""
    by_class = defaultdict(list)
    for record in read_records(train_path):
        if record.get('kind') != 'complaint' or int(digest(split_seed, record['reporter_hash'])[:8], 16) % 4 == 0:
            continue
        category = weak_category(record.get('violation'))
        if not category:
            continue
        request = TriageRequest.model_validate({k: v for k, v in record.items() if k in TriageRequest.model_fields})
        text = normalize(player_text(request.messages))
        if len(re.findall(r'[а-яёa-z]', text)) >= 3:
            by_class[category].append({'kind': 'complaint', 'category': category, 'text': text,
                                       'reporter_hash': record['reporter_hash'], 'review_status': 'weak'})
    rng = random.Random(seed)
    rows = []
    for category in sorted(by_class):
        rng.shuffle(by_class[category])
        rows += by_class[category][:cap]
    return rows
