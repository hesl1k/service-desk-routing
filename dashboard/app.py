from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "output"
METRICS = OUTPUT / "metrics_summary.csv"
TICKETS = OUTPUT / "ticket_results.csv"
ECONOMY = OUTPUT / "economy_summary.json"
LOAD = ROOT / "reports" / "load_test_summary.json"

st.set_page_config(page_title="Service Desk analytics", layout="wide")
st.title("Service Desk: экономика и качество маршрутизации")

if not METRICS.exists():
    st.error("Нет metrics_summary.csv. Сначала запустите analytics.pipeline.")
    st.stop()

metrics = pd.read_csv(METRICS)
tickets = pd.read_csv(TICKETS) if TICKETS.exists() else pd.DataFrame()
economy = json.loads(ECONOMY.read_text(encoding="utf-8")) if ECONOMY.exists() else {}

col1, col2, col3, col4 = st.columns(4)
col1.metric("Общая стоимость baseline", f"{economy.get('baseline_total_cost', 0):.2f}")
col2.metric("Общая стоимость LP", f"{economy.get('lp_total_cost', 0):.2f}")
col3.metric("Экономия", f"{economy.get('total_savings', 0):.2f}", f"{economy.get('overall_savings_percent', 0):.2f}%")
col4.metric("Цель 7%", "достигнута" if economy.get("target_reached") else "не достигнута")

scenarios = metrics["scenario"].drop_duplicates().tolist()
scenario = st.sidebar.selectbox("Сценарий", scenarios)
selected = metrics[metrics["scenario"] == scenario].copy()

st.subheader("Стоимость по выбранному сценарию")
st.bar_chart(selected.set_index("method")[["total_cost", "processing_cost", "penalty_cost"]])

st.subheader("Ключевые показатели")
columns = [
    "method",
    "service_level_percent",
    "l3_escalation_rate_percent",
    "utilization_percent",
    "throughput_per_hour",
    "modeled_afrt_min",
    "modeled_art_min",
    "computation_time_ms",
]
st.dataframe(selected[columns], use_container_width=True, hide_index=True)

st.subheader("Экономия LP по сценариям")
lp_rows = metrics[metrics["method"] == "lp"].set_index("scenario")
st.bar_chart(lp_rows[["savings_percent"]])

st.subheader("Сводная таблица")
st.dataframe(metrics, use_container_width=True, hide_index=True)

if not tickets.empty:
    st.subheader("Результаты по тикетам")
    st.dataframe(tickets[tickets["scenario"] == scenario], use_container_width=True, hide_index=True)

if LOAD.exists():
    load = json.loads(LOAD.read_text(encoding="utf-8"))
    st.subheader("Нагрузочное тестирование API")
    a, b, c, d = st.columns(4)
    a.metric("RPS", load.get("actual_rps", 0))
    b.metric("Ошибки", f"{load.get('error_rate_percent', 0)}%")
    c.metric("p95", f"{load.get('p95_response_ms', 0)} мс")
    d.metric("p99", f"{load.get('p99_response_ms', 0)} мс")
