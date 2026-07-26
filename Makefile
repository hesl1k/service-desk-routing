.PHONY: test analytics api dashboard load docker clean

test:
	PYTHONPATH=. pytest

analytics:
	PYTHONPATH=. python -m analytics.pipeline --lp-source direct

api:
	PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8002

dashboard:
	streamlit run dashboard/app.py

load:
	PYTHONPATH=. python load_tests/simple_load_runner.py --host http://127.0.0.1:8002 --rps 100 --duration 5 --concurrency 120

docker:
	docker compose up --build

clean:
	rm -rf .pytest_cache data/output/* reports/load_test_results.csv reports/load_test_summary.json reports/load_test_report.md
