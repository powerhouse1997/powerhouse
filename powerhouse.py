import os
import re
import time
import uuid
import psutil
import requests
from flask import Flask, request, jsonify
import telebot
from telebot.types import Message
import googleapiclient.discovery
import googleapiclient.http
import google_auth_oauthlib.flow
import google.auth.transport.requests
import google.oauth2.credentials
import redis
from urllib.parse import quote as url_quote

###############################################################################
# Configuration
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_TOKEN'
BASE_URL = os.environ.get('BASE_URL', 'https://your-app-url.com/')
REDIS_HOST = os.getenv('REDIS_HOST', 'your-redis-host')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6380))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', 'your-redis-password')

###############################################################################
# Initialize Flask App and Redis Client
app = Flask(__name__)
redis_client = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=True,  # Ensure SSL is used for secure connection
    decode_responses=True
)

@app.before_request
def before_request_func():
    print("This code runs before each request.")

###############################################################################
# Initialize Telegram Bot
bot = telebot.TeleBot(TELEGRAM_TOKEN)

###############################################################################
# Google Drive Credentials & Authentication Setup
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDS_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')

def authorize_google_drive():
    creds = None
    if os.path.exists('token.json'):
        creds = google.oauth2.credentials.Credentials.from
