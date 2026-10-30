# Карта проекта

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
├── .gitignore                   исключения данных и окружения
├── app/
│   ├── __init__.py
│   ├── schemas.py               строгие модели входа и двух форматов ответа
│   ├── api.py                   POST /triage; GET /health
│   ├── batch.py                 JSONL/GZ → JSONL, одна строка на входную
│   ├── core.py                  общий TriageService, эвристики, язык, черновик
│   ├── preprocess.py            текст player до первого admin, нормализация
│   ├── classifier.py            TF-IDF + линейная модель, загрузка и прогноз
│   ├── priority.py              приоритет и передача человеку, политика draft
│   ├── rules.py                 индекс правил и составной ключ цитаты
│   └── submission.py            преобразование цитат в строковый формат сдачи
├── scripts/
│   ├── __init__.py
│   ├── inspect_data.py          диагностика данных, правил и taxonomy
│   ├── sample_for_labeling.py   слепая выборка, manifest, пустые метки
│   ├── train.py                 обучение из B1 gold, grouped CV только в train
│   ├── evaluate.py              оценка сервиса: категории, приоритеты, языки
│   └── merge_labels.py          проверка меток, согласие и конфликты
├── configs/
│   └── taxonomy.schema.json     схема внешней taxonomy
├── docs/
│   ├── implementation-plan.md  полный план A–E, критерии, исследования
│   ├── data-contract.md        структура и агрегатная диагностика данных
│   ├── api-contract.md         запросы, форматы ответа, ошибки
│   ├── training.md             обучение B2, артефакты, метрики, подключение
│   └── annotation-guide.md     категории, приоритеты, инструкция B1
└── tests/
    ├── test_core.py            безопасность, правила, API и batch
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
| Цитаты | `rules.py`, таблицы соответствий в `core.py` | `test_core.py` |
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

C1: `app/language.py` — консервативный детектор с LanguageDecision и optional fastText через GRAND_LANGUAGE_MODEL_PATH; `tests/test_language.py`, инструкция `docs/language.md`. Эвристический режим всегда language_uncertain и человек. Реальная модель и качество kk/uz не проверены. Следующий этап C2 — поиск и релевантность правил.

C2 выполнен: `app/facts.py` — claim/reported_player_statement/metadata с исходным полем и offsets, без verified; `tests/test_facts.py`, `docs/facts.md`. В core extracted.claims содержит отдельные утверждения player. Название C2 ранее ошибочно связывалось с retrieval; источник порядка этапов — implementation-plan.md.
