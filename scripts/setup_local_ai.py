"""Verify local Qwen installation; optionally pull *only* on explicit request."""
import argparse
import json
import shutil
import subprocess
import urllib.error
import urllib.request

MODEL = 'qwen2.5:3b-instruct-q4_K_M'


def ready():
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2) as response:
            data=json.load(response)
        return any(model.get('name','').lower()==MODEL.lower() for model in data.get('models',[]))
    except (OSError,ValueError):
        return False


def main():
    parser=argparse.ArgumentParser(description='Проверка полностью локальной Qwen2.5 через Ollama')
    parser.add_argument('--pull',action='store_true',help='Явно разрешить загрузку модели через Ollama')
    opts=parser.parse_args()
    if not shutil.which('ollama'):
        print('Ollama не установлена. Установите приложение с https://ollama.com/download и повторите запуск.')
        return 2
    if ready():
        print('Qwen2.5 3B установлена и доступна локально. Генерация готова.');return 0
    if not opts.pull:
        print('Qwen2.5 3B пока не доступна. Запустите setup_local_ai.py --pull, чтобы загрузить модель.');return 1
    print('Загружаю Qwen2.5 3B в Ollama. Это сетевое скачивание только файла модели.');
    proc=subprocess.run(['ollama','pull',MODEL],check=False)
    if proc.returncode:return proc.returncode
    if ready():print('Локальная модель готова.');return 0
    print('Модель загружена, но Ollama API не отвечает. Запустите Ollama и повторите проверку.')
    return 1

if __name__=='__main__':raise SystemExit(main())
