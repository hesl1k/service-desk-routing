$ErrorActionPreference = "Stop"
python -m analytics.pipeline --lp-source direct
uvicorn app.main:app --host 127.0.0.1 --port 8002
