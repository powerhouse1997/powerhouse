import os
import re
import time
import uuid
import psutil
import requests
import redis
import googleapiclient.discovery
import googleapiclient.http
import google_auth_oauthlib.flow
import google.auth.transport.requests
import google.oauth2.credentials
from flask import Flask, request, jsonify
import telebot
from telebot.types import Message
from urllib.parse import quote as url_quote

###############################################################################
# Configuration (Uses Azure Environment Variables)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')  # Set this in Azure App Service
BASE_URL = os.getenv('BASE_URL')  # Set this in Azure App Service
REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6380))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD')

if not TELEGRAM_TOKEN or not BASE_URL:
    raise ValueError("⚠️ Missing TELEGRAM_TOKEN or BASE_URL. Set these in Azure.")

###############################################################################
# Initialize Flask App and Redis Client
app = Flask(__name__)
redis_client = redis.StrictRedis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    ssl=True,
    decode_responses=True
)

###############################################################################
# Initialize Telegram Bot
bot = telebot.TeleBot(TELEGRAM_TOKEN)

###############################################################################
# Google Drive Credentials & Authentication Setup
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDS_FILE = 'credentials.json'  # Ensure this file is uploaded to Azure

def authorize_google_drive():
    creds = None
    if os.path.exists('token.json'):
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

###############################################################################
# Helper Functions

def create_progress_bar(progress, total, length=20):
    completed = int((progress / total) * length)
    return f"[{'█' * completed}{'-' * (length - completed)}] {int((progress / total) * 100)}%"

def download_file(url, chat_id, message_id):
    try:
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        file_name = sanitize_file_name(response.url.split("/")[-1]) or f"file_{uuid.uuid4().hex}.bin"
        
        download_dir = 'downloads'
        os.makedirs(download_dir, exist_ok=True)
        file_path = os.path.join(download_dir, file_name)

        with open(file_path, 'wb') as f:
            downloaded_size = 0
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                downloaded_size += len(chunk)
                progress_bar = create_progress_bar(downloaded_size, total_size)
                bot.edit_message_text(f"📥 Downloading...\n{progress_bar}", chat_id=chat_id, message_id=message_id)

        return file_path
    except Exception as e:
        bot.edit_message_text(f"❌ Download failed: {str(e)}", chat_id=chat_id, message_id=message_id)
        return None

def upload_to_drive(file_path, chat_id, message_id):
    try:
        creds = authorize_google_drive()
        service = googleapiclient.discovery.build('drive', 'v3', credentials=creds)
        file_metadata = {'name': os.path.basename(file_path)}
        media = googleapiclient.http.MediaFileUpload(file_path, resumable=True)

        request = service.files().create(body=file_metadata, media_body=media, fields='id')
        response = None
        total_size = os.path.getsize(file_path)
        uploaded_size = 0

        while not response:
            status, response = request.next_chunk()
            if status:
                uploaded_size = int(status.resumable_progress)
                progress_bar = create_progress_bar(uploaded_size, total_size)
                bot.edit_message_text(f"📤 Uploading to Google Drive...\n{progress_bar}", chat_id=chat_id, message_id=message_id)

        file_id = response.get('id')
        service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
        return f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    except Exception as e:
        bot.edit_message_text(f"❌ Upload failed: {str(e)}", chat_id=chat_id, message_id=message_id)
        return None

def sanitize_file_name(file_name, max_length=50):
    if len(file_name) > max_length:
        base_name, ext = os.path.splitext(file_name)
        file_name = base_name[:max_length] + ext
    return file_name

###############################################################################
# Telegram Handlers

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! Send me a download link, and I'll mirror it for you.")

def is_download_link(text):
    return bool(re.match(r'^(https?://)?(www\.)?([\w\-]+\.)+[a-zA-Z]{2,6}(/[\w\-.~:?#%&/=]*)?$', text))

@bot.message_handler(content_types=['text'])
def handle_text(message: Message):
    if is_download_link(message.text):
        sent_message = bot.reply_to(message, "🛠️ Preparing...")

        try:
            file_path = download_file(message.text, message.chat.id, sent_message.message_id)
            if file_path:
                mirror_link = upload_to_drive(file_path, message.chat.id, sent_message.message_id)
                if mirror_link:
                    bot.edit_message_text(f"✅ Completed!\n🔗 [Mirror Link]({mirror_link})", 
                                          chat_id=message.chat.id, message_id=sent_message.message_id, parse_mode="Markdown")
                else:
                    bot.edit_message_text(f"❌ Upload error.", chat_id=message.chat.id, message_id=sent_message.message_id)
            else:
                bot.edit_message_text(f"❌ Download error.", chat_id=message.chat.id, message_id=sent_message.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {str(e)}", chat_id=message.chat.id, message_id=sent_message.message_id)
    else:
        bot.reply_to(message, "I only accept valid download links.")

###############################################################################
# Flask Routes for Webhook

@app.route('/')
def index():
    return "Bot is running!"

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
    bot.process_new_updates([update])
    return "OK", 200

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    bot.remove_webhook()
    success = bot.set_webhook(url=f"{BASE_URL}/{TELEGRAM_TOKEN}")
    return jsonify({"status": "Webhook set" if success else "Webhook setup failed"})

###############################################################################
# Run the app on Azure
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
