#!/bin/bash
# ── Prediction Market Anomaly Detector ──
# Run this once a day to refresh all data.
# From your prediction-anomaly folder, type: bash run_pipeline.sh

echo ""
echo "================================"
echo " Anomaly Detector - Daily Refresh"
echo "================================"
echo ""

cd "$(dirname "$0")"

echo "Step 1/3: Fetching latest trades..."
python3 pipeline/fetch.py

echo ""
echo "Step 2/3: Running anomaly detection..."
python3 pipeline/detect.py

echo ""
echo "Step 3/3: Generating evaluation report..."
python3 pipeline/evaluate.py

echo ""
echo "================================"
echo " Done. Open your dashboard to see results."
echo "================================"
echo ""