# E3: установка, запуск и состояние сдачи

## Воспроизводимое окружение

Проверяемая конфигурация: Windows x64, Python 3.14.6. `requirements-lock.txt` фиксирует версии рабочего окружения, включая dev и ML, без editable-путей и fastText. Это snapshot с точными версиями, не hash-lock для всех платформ. Другие ОС/Python ещё требуют отдельного прогона; optional fastText не установлен и не проверен.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps .
.\.venv\Scripts\python.exe -m pip check
```

Для разработки вместо последней установки пакета: `pip install --no-deps -e .`. Сборка wheel: `python -m pip wheel . --no-deps --wheel-dir <внешний-каталог>`. Шаблоны JSON включены в wheel через package-data. Исходные данные, модель, SQLite и отчёты не входят в сборку.

## Запуск

```powershell
$env:GRAND_RULES_PATH = 'C:\path\outside\repo\rules.json'
# Только при наличии обученного доверенного артефакта:
# $env:GRAND_MODEL_PATH = 'C:\path\outside\repo\model.joblib'
.\scripts\run.ps1 -Action predict -InputPath C:\path\tickets.jsonl -OutputPath C:\path\predictions.jsonl -Python .\.venv\Scripts\python.exe
.\scripts\run.ps1 -Action serve -Python .\.venv\Scripts\python.exe
```

PowerShell runner отказывается перезаписывать существующий output. API слушает только 127.0.0.1:8000. `GET /health`, `POST /triage`, схема `/docs`. Нет правил — HTTP 503. Полный контракт — `docs/api-contract.md`.

После установки пакета доступен `grand-predict --input <IN> --output <OUT> --rules <rules.json> [--model <model.joblib>]`. Это тот же CLI, что `python -m app.batch`. Используйте новый выходной путь: низкоуровневый batch CLI и Makefile могут перезаписать существующий файл. Результаты держать вне репозитория.

На машине с GNU Make: `make predict IN=/path/input.jsonl OUT=/path/new-output.jsonl RULES=/path/rules.json PYTHON=python`. MODEL — optional аргумент. `make serve` использует переменные окружения GRAND_RULES_PATH/GRAND_MODEL_PATH. Наличие Make не требуется для Windows runner. Совместимость итогового JSON со скрытым тестом ещё должна подтвердиться организатором.

История включается отдельно: batch `--history` либо HTTP `GRAND_HISTORY_PATH` + `X-Ticket-ID`. Optional детектор языка: GRAND_LANGUAGE_MODEL_PATH и extra language; он не включён в проверенную конфигурацию. Без classifier и language model используется эвристический режим с передачей человеку. Цитаты во внешнем формате строковые; `--format internal` сохраняет раздел и хеш.

## Проверки перед сдачей

`python -m pytest -q`, `pip check`, `git diff --check`. Затем API smoke, batch на valid и сравнение числа строк/ошибок. Проверять установленный wheel из каталога вне репозитория, чтобы импорт не подменялся исходниками. Проверка в новом venv на том же компьютере не равнозначна проверке на другой ОС или машине.

## Что ещё требуется для конкурсного результата

Проверка 30.10.2026: wheel установлен в новый venv на том же Windows-компьютере с зафиксированными зависимостями. Импорт из site-packages (вне репозитория), наличие шаблонов, API health/triage, CLI batch и PowerShell runner подтверждены. Оба batch-прогона valid дали 1000 строк, 0 ошибок; pip check не выявил конфликтов. Полный набор — 108 passed, одно прежнее предупреждение Starlette. GNU Make отсутствует, Makefile не запускался; другая машина/ОС не проверялась.

- Заполнить gold B1; обучить и оценить категории/приоритеты, калибровку и языковые срезы.
- Проверить реальный language backend и качество kk/uz; шаблоны утвердить с носителями.
- Заполнить 100 слепых пар D4, разобрать галлюцинации и исправить тексты.
- Разметить пары релевантных правил и близких обращений; семантическая дедупликация пока отсутствует.
- Измерить HTTP p95 и финальную конфигурацию; текущий E2 относится к локальному baseline.
- Интерфейс E1 доступен как локальное демо (см. ui.md); браузерные сценарии ещё требуют ручной проверки. Предложения FAQ E1b не реализованы.

Этот пакет — воспроизводимый технический baseline. Финальные конкурсные метрики, готовность production и полнота интеграции не заявляются. Ни ответы игрокам, ни санкции автоматически не выполняются.

## Запуск без явного пути к правилам

`make predict IN=<вход.jsonl[.gz]> OUT=<выход.jsonl[.gz]>` работает и без `RULES`: правила берутся из `--rules`, затем из `GRAND_RULES_PATH`, затем ищется `rules.json` в текущей папке, `data/`, `handout/` и на уровень выше. Если файла нет, прогон не падает: ответы выдаются без цитат, а в stderr пишется предупреждение. Модель (`MODEL=`) необязательна и в репозиторий не входит: обученные на данных кейса артефакты публиковать нельзя, поэтому по умолчанию работает режим правил.
