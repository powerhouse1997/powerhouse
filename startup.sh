#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Start the Flask app
gunicorn -w 4 -b 0.0.0.0:$PORT app:app
