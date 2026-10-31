"""One-time setup wizard + safe localhost launcher. No manual env configuration.

Run `python -m scripts.launch` from any directory, in your project's Python venv.
"""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import sys

from app.support.local_config import read_config, write_config

ROOT = Path(__file__).resolve().parent.parent


def prepare(*, reset: bool = False, password: str | None = None, root: Path = ROOT) -> dict:
    if sys.version_info < (3, 12):
        raise RuntimeError('Для проекта необходим Python 3.12 или новее.')
    data = root / 'data'
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    config_path = data / 'operator.json'
    existing = read_config(config_path)
    if config_path.exists() and existing is None:
        raise RuntimeError('Файл data/operator.json повреждён или имеет небезопасные права. Его нужно восстановить из резервной копии; он не будет перезаписан.')
    if not existing or reset:
        print('\nGrand Mobile Support — ' + ('смена пароля' if reset else 'первый запуск'))
        if reset:
            print('Укажите новый пароль (не менее 12 символов).')
        if password is None:
            # Reuse a previously chosen password from the environment, when present.
            # We never print the password or persist its cleartext value.
            password = os.environ.get('GRAND_ADMIN_PASSWORD') or None
        if password is None:
            if reset:
                if not sys.stdin.isatty():
                    raise RuntimeError('Для сброса пароля используйте терминал.')
                password = getpass.getpass('Новый пароль оператора: ')
                confirmation = getpass.getpass('Повторите пароль: ')
                if password != confirmation:
                    raise ValueError('Пароли не совпали. Повторите запуск.')
            else:
                # First run setup happens in /admin/setup instead of in the console.
                # Avoid requiring a TTY for GUI launcher and double-click.
                print('Первый запуск: пароль оператора задаётся на странице в браузере.')
        if password is not None:
            write_config(config_path, password, previous=None if reset else existing)
            print('Пароль сохранён в виде хеша, локальный ключ создан.\n')
    os.environ['GRAND_OPERATOR_CONFIG'] = str(config_path.resolve())
    os.environ.setdefault('GRAND_DB_PATH', str((data / 'support.sqlite3').resolve()))
    os.environ.setdefault('GRAND_UPLOAD_DIR', str((data / 'uploads').resolve()))
    rules = data / 'rules.json'
    if not rules.is_file() and (root / 'private' / 'rules.json').is_file():
        rules = root / 'private' / 'rules.json'
    if not os.environ.get('GRAND_RULES_PATH') and rules.is_file():
        os.environ['GRAND_RULES_PATH'] = str(rules.resolve())
    return read_config(config_path)


def main():
    parser = argparse.ArgumentParser(description='Grand Mobile Support: быстрая локальная установка и запуск')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--reset-password', action='store_true', help='Сменить пароль оператора')
    parser.add_argument('--setup-only', action='store_true', help='Только настроить, без запуска')
    args = parser.parse_args()
    if args.port < 1024 or args.port > 65535:
        parser.error('Порт должен быть от 1024 до 65535')
    try:
        config = prepare(reset=args.reset_password)
    except (ValueError, RuntimeError) as exc:
        print('Ошибка настройки:', exc, file=sys.stderr)
        sys.exit(1)
    if args.setup_only:
        print('Настройка сохранена. Можно запускать приложение.')
        return
    os.chdir(ROOT)
    import socket
    preferred = args.port
    for candidate in range(preferred, min(preferred + 20, 65536)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(('127.0.0.1', candidate))
            except OSError:
                continue
            args.port = candidate
            break
    else:
        print('Не удалось найти свободный локальный порт. Закройте предыдущий запуск.', file=sys.stderr)
        sys.exit(1)
    if args.port != preferred:
        print(f'Порт {preferred} занят; использую {args.port}.')
    print('\n' + '='*55)
    print(' Grand Mobile Support — локальная версия Outsiders')
    print('='*55)
    print(f' Игрок:       http://127.0.0.1:{args.port}/')
    print(f' Оператор:    http://127.0.0.1:{args.port}/admin')
    print(' Остановить:  Ctrl+C')
    if not os.environ.get('GRAND_RULES_PATH'):
        print(' В этой публичной сборке нет приватных правил и весов модели.')
    print(' Не публикуйте этот сервер в интернете без security review.\n', flush=True)
    if os.getenv('GRAND_OPEN_BROWSER') == '1':
        # Open only after the local server is responding.
        import threading
        import urllib.request
        import time
        import webbrowser
        def _open_ready():
            url = f'http://127.0.0.1:{args.port}/admin/setup' if config is None else f'http://127.0.0.1:{args.port}/'
            for _ in range(80):
                try:
                    with urllib.request.urlopen(url, timeout=0.3) as response:
                        if response.status == 200:
                            webbrowser.open(url)
                            return
                except OSError:
                    time.sleep(0.2)
        threading.Thread(target=_open_ready, daemon=True).start()
    import uvicorn
    uvicorn.run('app.api:app', host='127.0.0.1', port=args.port, access_log=False)


if __name__ == '__main__':
    main()
