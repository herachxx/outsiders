"""Interactive local annotation of the private B1 package."""
import argparse
import csv
import json
import os
from pathlib import Path
import tempfile
from typing import get_args

from app.schemas import Category, Language
from scripts.merge_labels import merge_annotations
from scripts.sample_for_labeling import LABEL_FIELDS, private_path


def load_package(folder):
    folder = Path(folder).resolve()
    private_path(folder)
    with (folder / 'manifest.json').open(encoding='utf-8') as stream:
        manifest = json.load(stream)
    with (folder / 'tasks.jsonl').open(encoding='utf-8') as stream:
        tasks = [json.loads(line) for line in stream]
    with (folder / 'labels.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    ids = [item['annotation_id'] for item in tasks]
    if len(ids) != len(set(ids)) or set(ids) != {item['annotation_id'] for item in manifest['items']}:
        raise ValueError('Tasks and manifest do not match')
    if [row['annotation_id'] for row in rows] != ids or any(set(row) != set(LABEL_FIELDS) for row in rows):
        raise ValueError('Labels CSV does not match tasks or expected columns')
    return manifest, tasks, rows


def save_labels(path, rows):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.labels-', suffix='.csv', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=LABEL_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def choose(prompt, options, input_fn=input):
    print(prompt)
    for number, option in enumerate(options, 1):
        print(f'  {number}. {option}')
    while True:
        answer = input_fn('Номер (Enter — пропустить, q — выйти): ').strip()
        if answer.lower() == 'q':
            return 'quit'
        if not answer:
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        print('Выберите номер из списка.')


def annotate(task, row, manifest, annotator, input_fn=input):
    print(f"\n{task['kind']} | {task['annotation_id'][:12]} | вложений: {task.get('images_count', 0)}")
    for field in ('region', 'server_lang', 'rule_refs_raw', 'reported_nick'):
        if task.get(field):
            print(f'{field}: {task[field]}')
    for message in task['messages']:
        print(f"[{message['role']}] {message['text']}")
    status = choose('Решение:', ('labeled', 'needs_adjudication'), input_fn)
    if status in (None, 'quit'):
        return status
    candidate = {**row, 'annotator_id': annotator, 'adjudication_status': status}
    if status == 'labeled':
        fields = (
            ('category', [code for code in get_args(Category) if code.startswith(task['kind'] + '.')]),
            ('priority', ['p0', 'p1', 'p2', 'p3']),
            ('language', list(get_args(Language))),
            ('needs_human', ['true', 'false']),
        )
        for field, options in fields:
            value = choose(field, options, input_fn)
            if value in (None, 'quit'):
                return value
            candidate[field] = value
    # Reuse the same policy validation as the gold merge, including sensitive categories.
    merge_annotations(manifest, [candidate])
    return candidate


def run(folder, annotator, input_fn=input):
    if not annotator.strip():
        raise ValueError('annotator_id is required')
    manifest, tasks, rows = load_package(folder)
    pending = [(task, row) for task, row in zip(tasks, rows) if not row['annotator_id']]
    print(f'Осталось без метки: {len(pending)} из {len(tasks)}. q — выйти; Enter — пропустить.')
    for task, row in pending:
        try:
            candidate = annotate(task, row, manifest, annotator, input_fn)
        except ValueError as exc:
            print(f'Метка отклонена: {exc}. Обращение не сохранено.')
            continue
        if candidate == 'quit':
            break
        if candidate is None:
            continue
        row.update(candidate)
        save_labels(Path(folder) / 'labels.csv', rows)
        print('Сохранено.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--annotator', required=True)
    args = parser.parse_args()
    run(args.package, args.annotator)


if __name__ == '__main__':
    main()
