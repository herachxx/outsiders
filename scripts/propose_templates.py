"""Bonus: propose answer templates per cluster of similar tickets, from real administrator replies.

The player texts of a ticket kind are clustered (TF-IDF + MiniBatchKMeans). For each cluster the most frequent
administrator reply, with nicknames, numbers and links replaced by placeholders, is offered as a candidate
template. Nothing is invented: a template exists only if administrators already answered that way, and every
candidate still needs an administrator's approval (`approved: null`). The report is private (outside Git).
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from app.core import TriageService
from app.preprocess import normalize, player_text, before_admin
from app.schemas import TriageRequest
from scripts.sample_for_labeling import private_path, read_records

NICK = re.compile(r'\b[A-Za-zА-Яа-я]+_[A-Za-zА-Яа-я]+\d*\b')
PLACEHOLDERS = re.compile(r'#?<(?:digits|url|email|handle)>|#?\d+')
STOP = set('и в не на я с что а по но у за из к от до или ли да как так для это то же ты он она они мы вы меня мне пж '
           'пожалуйста админ помогите помоги привет здравствуйте тут там очень еще уже'.split())


def reply_template(text):
    """Administrator reply with player-specific parts replaced by placeholders."""
    text = NICK.sub('{nick}', text)
    text = PLACEHOLDERS.sub('{n}', text)
    return re.sub(r'\s+', ' ', text).strip()


def load(path, kind, limit):
    rows = []
    for record in read_records(path):
        if record.get('kind') != kind or len(rows) >= limit:
            continue
        admin = next((m['text'] for m in record['messages'] if m['role'] == 'admin' and m['text'].strip()), None)
        request = TriageRequest.model_validate({k: v for k, v in record.items() if k in TriageRequest.model_fields})
        text = normalize(player_text(before_admin(request.messages)))
        if admin and re.search('[а-яёa-z]{3}', text):
            rows.append((text, admin, record.get('rule_refs_raw') or ''))
    return rows


def propose(rows, kind='report', clusters=12, seed=42, top_replies=3):
    from sklearn.cluster import MiniBatchKMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    if len(rows) < clusters * 5:
        raise ValueError('Too few tickets for this number of clusters')
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=30000, stop_words=sorted(STOP))
    matrix = vectorizer.fit_transform([text for text, _, _ in rows])
    model = MiniBatchKMeans(n_clusters=clusters, random_state=seed, n_init=3, batch_size=2048).fit(matrix)
    terms = vectorizer.get_feature_names_out()
    members = defaultdict(list)
    for index, label in enumerate(model.labels_):
        members[int(label)].append(index)
    output = []
    for label, indexes in sorted(members.items(), key=lambda item: -len(item[1])):
        order = model.cluster_centers_[label].argsort()[::-1][:6]
        categories = Counter(TriageService._category(kind, rows[i][0], rows[i][2]) for i in indexes)
        replies = Counter(reply_template(rows[i][1]) for i in indexes)
        total = sum(replies.values())
        candidates = [{'template': text, 'count': count, 'share': round(count / total, 3)}
                      for text, count in replies.most_common(top_replies)]
        output.append({'cluster': label, 'size': len(indexes), 'share': round(len(indexes) / len(rows), 3),
                       'top_terms': [str(terms[i]) for i in order],
                       'dominant_category': categories.most_common(1)[0][0],
                       'category_share': round(categories.most_common(1)[0][1] / len(indexes), 3),
                       'candidates': candidates, 'approved': None})
    return {'kind': kind, 'tickets': len(rows), 'clusters': output,
            'note': 'Templates come from real administrator replies; each needs approval before use.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train', required=True, help='tickets_train.jsonl[.gz] with administrator replies')
    parser.add_argument('--output', required=True, help='new private JSON report (outside the repository)')
    parser.add_argument('--kind', choices=['report', 'complaint'], default='report')
    parser.add_argument('--clusters', type=int, default=12)
    parser.add_argument('--limit', type=int, default=60000)
    args = parser.parse_args()
    target = private_path(args.output)
    if target.exists():
        raise SystemExit('Output already exists; refusing to overwrite')
    report = propose(load(args.train, args.kind, args.limit), args.kind, args.clusters)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'tickets': report['tickets'], 'clusters': len(report['clusters'])}))


if __name__ == '__main__':
    main()
