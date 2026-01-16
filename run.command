#!/bin/bash

# Change to the app directory
cd "$(dirname "$0")"

echo "Starting YouTube Downloader..."
echo ""

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies if needed
echo "Checking dependencies..."
pip install -q -r requirements.txt

echo ""
echo "Starting server at http://127.0.0.1:5001"
echo "Press Ctrl+C to stop the server"
echo ""

# Open browser after a short delay
(sleep 2 && open http://127.0.0.1:5001) &

# Run the Flask app
python app.py
