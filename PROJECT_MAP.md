# Карта проекта

Подсказки категории из rule_refs_raw: числовые REF_HINTS в core используют границы полного номера; 15.2/5.20/5.2.1 не считаются 5.2. Поле остаётся утверждением игрока, не доказанной цитатой. Проверки — tests/test_rule_hints.py.

Уточнение D2: `app/draft.py` различает географические region-коды cis/uz/kz и явно введённый сервер; для кодов запрашивает сервер во всех четырёх языках. Проверки — `tests/test_draft.py`, контракт и ограничение — `docs/drafts.md`.

Краткая точка входа для продолжения работы. Сверено с кодом 2026-10-30.
Grand Mobile Support Copilot: категория, приоритет, проверяемая цитата и черновик ответа. Стек: Python + FastAPI + Pydantic, опционально scikit-learn. Сейчас эвристики и шаблоны; обучение готово технически, реальные метки ещё нужны.

## Как быстро продолжить

1. Прочитать `AGENTS.md` и эту карту; выполнить `git status --short --branch` и `git log -1 --oneline`.
2. Выбрать нужные файлы по таблице ниже. Для поиска — `rg`, для списка — `rg --files`.
3. Полный план открывать по нужному этапу; не перечитывать весь репозиторий, архив и данные без причины.
4. После изменения структуры или поведения обновить соответствующие строки карты. Код — источник истины.

## Дерево проекта

```text
outsiders/
├── AGENTS.md                    постоянные правила
├── PROJECT_MAP.md               навигация и актуальное состояние
├── README.md                    установка и запуск
├── pyproject.toml               зависимости, пакет, pytest
├── requirements-lock.txt        точные версии проверенного Windows/Python окружения
├── Makefile                     predict/test/serve для GNU Make
├── .gitignore                   исключения данных и окружения
├── app/
│   ├── __init__.py
│   ├── schemas.py               строгие модели входа и двух форматов ответа
│   ├── api.py                   POST /triage; GET /health
│   ├── ui/                      локальная очередь, редактор, сохранение в браузере
│   ├── batch.py                 JSONL/GZ → JSONL, одна строка на входную
│   ├── core.py                  общий TriageService, эвристики, язык, черновик
│   ├── safety.py                финальная проверка шаблона, цитат и fallback
│   ├── history.py               SQLite: приватные ключи, окно 60 минут, идемпотентность
│   ├── dedupe.py                признаки точного повтора и пяти обращений
│   ├── preprocess.py            текст player до первого admin, нормализация
│   ├── classifier.py            TF-IDF + линейная модель, загрузка и прогноз
│   ├── priority.py              приоритет и передача человеку, политика draft
│   ├── rules.py                 индекс правил и составной ключ цитаты
│   └── submission.py            преобразование цитат в строковый формат сдачи
├── scripts/
│   ├── run.ps1                  единый Windows predict/serve/test
│   ├── __init__.py
│   ├── inspect_data.py          диагностика данных, правил и taxonomy
│   ├── sample_for_labeling.py   слепая выборка, manifest, пустые метки
│   ├── label_cli.py             локальная пошаговая ручная разметка B1
│   ├── second_review.py         слепое подмножество для второго разметчика
│   ├── train.py                 обучение из B1 gold, grouped CV только в train
│   ├── benchmark.py             E2: локальный pipeline, p95, ошибки, параллельность
│   ├── evaluate_drafts.py       D4: слепые пары A/B и агрегаты оценок
│   ├── evaluate.py              оценка сервиса: категории, приоритеты, языки
│   └── merge_labels.py          проверка меток, согласие и конфликты
├── configs/
│   └── taxonomy.schema.json     схема внешней taxonomy
├── docs/
│   ├── implementation-plan.md  полный план A–E, критерии, исследования
│   ├── data-contract.md        структура и агрегатная диагностика данных
│   ├── api-contract.md         запросы, форматы ответа, ошибки
│   ├── training.md             обучение B2, артефакты, метрики, подключение
│   ├── history.md              C3: запуск истории, окно времени, ограничения
│   └── annotation-guide.md     категории, приоритеты, инструкция B1
└── tests/
    ├── test_core.py            безопасность, правила, API и batch
    ├── test_ui.py              статика, проверка правок и отсутствие правил
    ├── test_benchmark.py       процентили, ошибки и приватность отчёта
    ├── test_draft_evaluation.py слепой пакет, парность, валидация оценок
    ├── test_safety.py          опасный текст, подмена цитат и генератора
    ├── test_dedupe.py          временные границы, заявители, batch и HTTP
    ├── test_classifier.py      утечки, обучение, артефакты, API и CLI с моделью
    ├── test_contract.py        строгая валидация и формат сдачи
    ├── test_priority.py        маршрутизация чувствительных категорий
    ├── test_data_contract.py   агрегатная диагностика без сырых текстов
    └── test_sampling.py        выборка, разделение групп, проверка меток
```

## Связи и маршруты чтения

```text
HTTP → api ──────┐
                ├→ schemas → core → priority + rules → schemas → submission → JSON
JSONL → batch ──┘

Исходные данные → sample_for_labeling → tasks + manifest + labels.csv
Ручная разметка + manifest → merge_labels → gold + conflicts
tasks + manifest + gold → train → classifier → приватные model.joblib + report.json
core → preprocess → опциональный classifier → защитные правила → priority + rules
```

`submission` применяется только для формата сдачи; internal сохраняет полные цитаты.

| Задача | Читать / менять | Проверять |
|---|---|---|
| Вход, ответ, форматы | `schemas.py`, `submission.py`, `docs/api-contract.md` | `test_contract.py` |
| HTTP или batch | `api.py`, `batch.py`, общий `core.py` | `test_core.py`, `test_contract.py` |
| Категория, язык, черновик | `core.py` | `test_core.py` |
| Обучение и признаки | `preprocess.py`, `classifier.py`, `scripts/train.py`, `docs/training.md` | `test_classifier.py`, `test_core.py` |
| Приоритет и эскалация | `priority.py`, `docs/annotation-guide.md` | `test_priority.py` |
| Цитаты | `rules.py`, `core.py`, `docs/retrieval.md` | `test_rules.py`, `test_core.py` |
| Данные и разметка | скрипты в `scripts/`, data-contract и annotation-guide | `test_data_contract.py`, `test_sampling.py` |

Имена модулей в таблице относятся к `app/`, имена тестов — к `tests/`.

## Состояние и следующий шаг

- Реализованы baseline, диагностика A1, контракт A2, черновая политика A3 и инструменты B1. Подтверждение политики и ручная разметка ещё нужны.
- B1 разделяет выборку по заявителям, скрывает ответы администраторов, проверяет метки и выделяет конфликты. Подготовлен приватный пакет на 800 обращений; это не готовый gold.
- **B2 технически готов**: общий preprocessing, раздельные модели complaint/report, grouped CV против regex/majority, приватные артефакты, API/batch. Проверен на синтетике; пустой реальный gold отклоняется без модели. Реальное обучение и оценка ждут разметки.
- Утечка сообщений player после admin исправлена общим cutoff в сервисе, обучении и выборке B1. Чувствительную эвристическую категорию модель не может понизить.
- **B3 частично готов**: `scripts/evaluate.py` оценивает полный сервис на grouped CV внутри train: accuracy, macro-F1, recall p0/p1, confusion matrix, языковые срезы, сравнение с эвристикой. Калибровка на отдельном разбиении ещё не реализована; для реальных измерений нужны метки. Holdout остаётся нетронутым.
- `confidence=0.0` до калибровки; история недоступна, дубли не определяются. Язык определяется эвристически; релевантность правил ограничена таблицами, ответы шаблонные.
- Далее по плану: B3 калибровка/приоритет; C — языки, правила, дубли; D — генерация, проверки и экспертная оценка; E — интерфейс, измерения и сдача. Конкурсное качество пока не подтверждено.

## Локальные ресурсы вне Git

- Репозиторий: `C:\Users\kulda\Documents\Decentrathon\outsiders`.
- Пакет B1: `C:\Users\kulda\Documents\Decentrathon\private\annotation-b1` (`tasks.jsonl`, `manifest.json`, `labels.csv`).
- Исходный handout: `C:\Users\kulda\Documents\Codex\2026-10-30\files-mentioned-by-the-user-grand\work\handout\handout`.
- Правила передаются через `GRAND_RULES_PATH` для API или `--rules` для batch. Без правил API возвращает 503.
- Данные, метки, модели и предсказания хранить вне репозитория. Для восстановления контекста сначала использовать агрегатный `docs/data-contract.md`, а не сырые тексты.

## Полезные команды (из корня репозитория, PowerShell)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/test_sampling.py -q
.\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m app.batch --help
.\.venv\Scripts\python.exe -m scripts.sample_for_labeling --help
.\.venv\Scripts\python.exe -m scripts.merge_labels --help
.\.venv\Scripts\python.exe -m scripts.train --help
git diff --check
```

Установка и пример batch — в `README.md`; разметка — в `docs/annotation-guide.md`; B2 — в `docs/training.md`. Для полной проверки B2 нужен extra `ml`. Счётчики тестов и историю коммитов здесь не дублируем: проверять командами.

Обновление B3: `app/calibration.py` и `tests/test_calibration.py` — отдельные группы fit/calibration/check внутри train, sigmoid, reliability bins и ECE. `scripts.train --calibrate` создаёт модель с вероятностями категории. При защитной замене категории confidence=0. Реальная калибровка ждёт gold. Следующий технический шаг — независимая оценка калиброванного режима по языкам; текущий evaluate оценивает некалиброванный режим.

Оценка B3: `scripts.evaluate --calibrate` поддерживает вложенное разделение групп, сравнение с некалиброванным сервисом и эвристикой, reliability/ECE по языкам с учётом покрытия. Проверки — `tests/test_evaluate.py`. Следующая независимая техническая задача C1 — полноценное определение языка; реальные метрики B2/B3 ожидают разметки.

C1: `app/language.py` — консервативный детектор с LanguageDecision и optional fastText через GRAND_LANGUAGE_MODEL_PATH; `tests/test_language.py`, инструкция `docs/language.md`. Позже уверенность ограничена ясными случаями (см. docs/language.md); короткие фрагменты, украинский и смешение остаются неуверенными. Реальная модель и качество kk/uz не проверены. Следующий этап C2 — поиск и релевантность правил.

C2 выполнен: `app/facts.py` — claim/reported_player_statement/metadata с исходным полем и offsets, без verified; `tests/test_facts.py`, `docs/facts.md`. В core extracted.claims содержит отдельные утверждения player. Название C2 ранее ошибочно связывалось с retrieval; источник порядка этапов — implementation-plan.md.

C3 частично реализован: точные нормализованные повторы одного заявителя, SQLite для HTTP, хронологический batch, 5 обращений за 60 минут. Включение opt-in, подробности docs/history.md. Семантические пары и precision/recall ожидают разметки. Следующий этап основного пути — D1, индекс и релевантность правил.

D1: `app/rules.py` содержит лексический search, отказ при неоднозначных разделах и validate_citation; `tests/test_rules.py`, `docs/retrieval.md`. Из core удалены фиксированные ref/category и section_id=30. Relevance@k на реальных gold-парах ещё не измерена. Следующий этап D2 — содержательные черновики по типу обращения.

D2: `app/draft.py` и `app/templates/drafts.json` — шаблоны ru/kk/uz/en по типу обращения, дополнительные запросы при отсутствии метаданных, явный язык fallback. `tests/test_draft.py`, `docs/drafts.md`. Носители и администраторы ещё не оценивали тексты. Следующий этап D3 — проверка безопасности ответа.

D3: `app/safety.py`, `tests/test_safety.py`, `docs/safety.md` — строгая схема, проверка цитат/релевантности, соответствие шаблону и нейтральный fallback с человеком. Свободная LLM-генерация не разрешена gate. Следующий этап D4 — подготовка слепой экспертной оценки черновиков.

D4 технически готов: scripts/evaluate_drafts.py, tests/test_draft_evaluation.py, docs/eval-rubric.md. Приватный пакет 100 пар: ../private/draft-review-d4-v1; оценки пустые, candidate эвристический. Исключены holdout-группы B1. Следующий этап — E2, измерение времени и стоимости; экспертная оценка D4 требует людей.

E2: scripts/benchmark.py, tests/test_benchmark.py, docs/performance.md. Выполнен локальный baseline-прогон 1000 valid, 1/5/20 потоков, p95 до 0,54 мс, ошибок 0, человек 100%; отчёт ../private/benchmark-e2-v1.json. HTTP/очередь и раздельное время стадий не измерены. Следующий этап E3 — воспроизводимая сборка и инструкция сдачи; UI E1 пока не реализован.

E3 технически готов: requirements-lock.txt, grand-predict entrypoint, scripts/run.ps1, Makefile, docs/submission.md. Wheel установлен в чистый venv ../private/e3-env; импорт/шаблоны/API smoke, 1000 valid CLI и runner без ошибок. 108 тестов; pip check OK. Make недоступен, другая машина не проверена. Следующий возможный этап — E1, локальный интерфейс администратора; качество всё ещё ждёт разметки и экспертных оценок.

E1: app/ui/index.html, style.css, app.js; POST /draft/check в api.py. Локальная очередь p0–p3, исходник/цитаты/reasons, редактор, localStorage по кнопке, локальная метка эскалации. tests/test_ui.py, docs/ui.md. 111 тестов, JS syntax, wheel assets проверены; браузерная проверка заблокирована средой. Следующий шаг — ручная проверка UI и завершение разметки/оценок; optional E1b (FAQ) ещё нет.

HTTP-дополнение E2: `scripts/benchmark_http.py`, `tests/test_benchmark_http.py`. Локальный HTTP-прогон синтетики 1000 запросов × 1/5/20 потоков; p95 27,4/34,3/79,0 мс без ошибок. Подробности `docs/performance.md`; финальная конфигурация и реальные тексты не измерены.

B1: `scripts/label_cli.py` даёт последовательную ручную разметку приватного пакета с сохранением после каждого решения; метки по-прежнему должны назначить люди. Запуск — `docs/annotation-guide.md`.

B1: `scripts/second_review.py` создаёт воспроизводимый слепой пакет для независимого второго разметчика. Готово 160 задач в `../private/annotation-b1-second-review`; метки обоих разметчиков пусты. Объединять с полным исходным manifest.

B1: `scripts/merge_labels.py` дополнительно записывает приватный `agreement.json`: попарное согласие и невзвешенная Cohen kappa по четырём полям, только общие полные метки. Проверки — `tests/test_annotation_agreement.py`. Реальные оценки ещё отсутствуют.

kk/uz routing: общий `multilingual_sensitive_category` в `app/priority.py` защищает report.account/payment и p0 на ограниченных сигналах потери доступа/оплаты; вызывается core и route. `tests/test_multilingual_routing.py` проверяет ошибочную модель и обычные вопросы. Реальная полнота и проверка носителями ещё нужны.

Этот детектор также покрывает отдельные смешанные kk/uz написания и исключает четыре явные отрицательные формы взлома. Отрицание не понижает уже чувствительную категорию; новая активная проблема в отдельной фразе сохраняет p0. Подробные ограничения — в annotation-guide.

Эвристики категорий (`CATEGORY_PATTERNS` в core.py) дополнены сленгом: «оск», «обзывает», «софт», «убивает», «застрелил». На valid доля `complaint.other` снизилась с 582 до 423 из 1000 (insult 44→176), но это сдвиг без меток, а не рост accuracy. Слабые метки (диагностика, не обучение): пункт из `violation` (2.1/2.4/2.6→insult, 5.2→cheat, 5.3/5.4/DM/DB/SK/TK→dm, 4.1/4.2→scam) покрывает лишь около 11 тыс. из 67 тыс. жалоб train, 97% из них insult, для репортов и классов other/invalid/admin меток нет — поэтому обучать на них модель нельзя. Как проверка recall правил они годятся; слова подбирались на заявителях вне holdout B1. Recall на отложенных: insult 0,72→0,79, dm 0,25→0,44, cheat 0,40→0,53; precision неизвестен. `rule_refs_raw` (поле игрока) используется как подсказка (`REF_HINTS` в core.py) только когда текст не назвал категорию жалобы; на слабых метках отложенных заявителей accuracy 0,76→0,88. Интеграция: `POST /integration/ticket` (api.py) принимает запись Grand Mobile с игнорированием полей исхода, опциональный `GRAND_API_KEY`; тесты `tests/test_integration.py`, описание процесса внедрения — `docs/integration.md`. Модель вызывается только если жалобу не решило конкретное правило (batch с моделью 1000 строк: 3,98→0,94 с).

Порядок выбора категории жалобы с моделью: конкретная эвристика (текст или `rule_refs_raw`) сильнее модели, модель решает остальное. На holdout B1 (метки поставил Claude, `claude_prelabel`, не человек) accuracy 0,77 против 0,61 у эвристик и 0,75 у чистой модели; на слабых метках 0,94. Модель `../private/classifier-claude-v1` обучена на 590 таких метках; на valid она не предсказывает complaint.other и ставит complaint.admin в 23,5% (в разметке 9%) — перепроверить человеком. С моделью batch на 1000 строк: 8,9 с, пик 156 МБ. Жалобы на несогласие с наказанием («не согласен», «варн») оставлены в other: граница с complaint.admin требует решения по taxonomy.

E2: `scripts/benchmark_process.py`, `tests/test_benchmark_process.py` — отдельный batch-процесс, полное время и OS peak RSS. Реальный valid 1000: 1,918 с, 33,25 МБ RAM, ошибок 0; приватный отчёт `../private/benchmark-process-v1.json`. Эвристики/шаблоны, без ML; граница замера описана в docs/performance.md.

Приоритет и человек (исправлено): у каждой жалобы в train есть вложение (лаунчер требует), поэтому правило «вложения → p1» превращало все жалобы в p1; оно удалено. `needs_human` теперь по taxonomy: account, payment, complaint.admin, report.help, апелляции и p0; раньше был у всех жалоб. На holdout B1 (метки Claude): accuracy приоритета 0,30→0,87, macro-F1 0,30→0,85, recall p1 0,88, p3 0,80; p0 в holdout нет. `language_uncertain` всё ещё отправляет человеку любое обращение при эвристическом детекторе.

Соответствие критериям жюри и ограничения оценки — `docs/criteria.md`.
