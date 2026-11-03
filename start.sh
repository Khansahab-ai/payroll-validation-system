#!/bin/bash
set -e

echo "=========================================================="
echo " Starting Payroll Validation & Reconciliation System"
echo "=========================================================="

# Check if database exists; if not, generate starter dataset
if [ ! -f "payroll.db" ]; then
    echo "Initializing database with starter dataset and planted anomalies..."
    python -c "from data_generator.generate_all import run_pipeline; run_pipeline(scale='starter', seed=20261022, export_seeds=False)"
fi

echo "Starting FastAPI backend on http://0.0.0.0:8000..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &

# Wait for backend to be ready
sleep 2

echo "Starting Streamlit dashboard on http://0.0.0.0:8501..."
exec streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true

