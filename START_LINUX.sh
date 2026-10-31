#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Требуется Python 3.12+.' >&2; exit 1
fi
if ! python3 -c 'import sys; assert sys.version_info >= (3,12)' >/dev/null 2>&1; then
  echo 'Установите Python 3.12 или новее.' >&2; exit 1
fi
if [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
elif python3 -m scripts.bootstrap_check >/dev/null 2>&1; then
  PY=python3
else
  echo '[1/2] Подготавливаю локальное окружение...'
  python3 -m venv .venv
  PY=.venv/bin/python
fi
if ! "$PY" -m scripts.bootstrap_check >/dev/null 2>&1; then
  package='.'
  if [[ -f private/models/category_model.cbm && -f private/models/classifier_meta.joblib ]]; then
    package='.[ml]'
  fi
  echo '[1/2] Устанавливаю недостающие библиотеки (нужен интернет при первом запуске)...'
  "$PY" -m pip install -e "$package"
  "$PY" -m scripts.bootstrap_check
fi
echo '[2/2] Запуск Grand Mobile Support...'
GRAND_OPEN_BROWSER=1 exec "$PY" -m scripts.launch "$@"
