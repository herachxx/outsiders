"""Shared feature boundary for training and inference; no historical outcomes."""

PREPROCESS_VERSION = 'player-before-admin-v1'


def before_admin(messages):
    for message in messages:
        role = message['role'] if isinstance(message, dict) else message.role
        if role == 'admin':
            break
        yield message


def player_text(messages):
    texts = []
    for message in before_admin(messages):
        role = message['role'] if isinstance(message, dict) else message.role
        if role == 'player':
            texts.append(message['text'] if isinstance(message, dict) else message.text)
    return ' '.join(texts).strip()


def normalize(text):
    return ' '.join(text.casefold().replace('ё', 'е').split())
