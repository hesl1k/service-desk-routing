# Оптимизация маршрутизации Service Desk

<p>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.111%2B-009688" alt="FastAPI">
  <img src="https://img.shields.io/badge/Streamlit-1.36%2B-FF4B4B" alt="Streamlit">
  <img src="https://img.shields.io/badge/MILP-SciPy%20%7C%20PuLP-green" alt="MILP">
  <img src="https://img.shields.io/badge/Docker-compose-2496ED" alt="Docker">
  <img src="https://img.shields.io/badge/tests-9%20passed-brightgreen" alt="Tests">
  <img src="https://img.shields.io/badge/license-MIT-yellow" alt="License">
</p>

MILP-оптимизация маршрутизации тикетов Service Desk. Сравнение LP-решения с baseline-эвристикой, метрики SLA, загрузки и экономии, визуализация в Streamlit, нагрузочное тестирование.

## Что делает система

1. Принимает тикеты и данные сотрудников.
2. Рассчитывает распределение методом целочисленной оптимизации.
3. Сравнивает LP-результат с последовательной baseline-эвристикой.
4. Формирует таблицы стоимости, экономии, SLA, загрузки и производительности.
5. Показывает результаты в Streamlit.
6. Проверяет `POST /route` под нагрузкой.

## Быстрый локальный запуск

Нужен Python 3.11 или новее.

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m analytics.pipeline --lp-source direct
uvicorn app.main:app --host 127.0.0.1 --port 8002
```

В другом терминале:

```bash
streamlit run dashboard/app.py
```

Адреса:

- API: `http://127.0.0.1:8002`
- Swagger: `http://127.0.0.1:8002/docs`
- Dashboard: `http://127.0.0.1:8501`

## Запуск полного контура через Docker

```bash
docker compose up --build
```

Compose последовательно поднимает API, пересчитывает аналитику через API и запускает дашборд.

## Проверка

```bash
pytest
python -m analytics.pipeline --lp-source direct
python load_tests/simple_load_runner.py --host http://127.0.0.1:8002 --rps 20 --duration 10
```

Для Locust:

```bash
locust -f load_tests/locustfile.py --host http://127.0.0.1:8002
```

## Основные результаты

После расчёта создаются:

- `data/output/metrics_summary.csv`
- `data/output/ticket_results.csv`
- `data/output/raw_results.json`
- `data/output/economy_summary.json`
- `reports/load_test_summary.json`
- `reports/load_test_results.csv`
- `reports/load_test_report.md`
- `reports/final_technical_report.md`

## Структура

- `app/` — API, схемы, адаптер и LP-ядро.
- `analytics/` — baseline, метрики и расчётный конвейер.
- `dashboard/` — Streamlit.
- `load_tests/` — Locust и автономный генератор нагрузки.
- `data/scenarios/` — пять согласованных сценариев.
- `tests/` — unit и integration tests.
- `docs/` — контракт и ограничения.
