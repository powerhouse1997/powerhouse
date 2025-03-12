#!/bin/bash

# Activate virtual environment (if any)
if [ -d "antenv" ]; then
    source antenv/bin/activate
fi

# Run Gunicorn to serve the bot
gunicorn --bind=0.0.0.0:8000 app:app
