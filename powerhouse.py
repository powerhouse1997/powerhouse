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

###############################################################################
# Configuration
TELEGRAM_TOKEN = '6438781804:AAGvcF5pp2gg2Svr5f0kpxvG9ZMoiG1WACc'
BASE_URL = os.environ.get('BASE_URL', 'https://mirrorbot-d5ewf6egd3a5baby.canadacentral-01.azurewebsites.net/')
if not BASE_URL.endswith('/'):
    BASE_URL += '/'

###############################################################################
# Initialize Telegram Bot and Flask App
bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

###############################################################################
# Google Drive Credentials & Authentication Setup
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDS_FILE = os.path.join(os.path.dirname(__file__), 'jarvis-400615-5d22aa4feea3.json')

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

# Simulates a dynamic progress bar
def create_progress_bar(progress, total, length=20):
    completed = int((progress / total) * length)
    bar = f"[{'█' * completed}{'-' * (length - completed)}] {int((progress / total) * 100)}%"
    return bar

# Handles file downloads and displays a live progress bar
def download_file(url, chat_id, message_id):
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    file_name = sanitize_file_name(response.url.split("/")[-1]) or f"file_{uuid.uuid4().hex}.bin"
    file_path = os.path.join('downloads', file_name)

    with open(file_path, 'wb') as f:
        downloaded_size = 0
        for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
            f.write(chunk)
            downloaded_size += len(chunk)
            progress_bar = create_progress_bar(downloaded_size, total_size)
            bot.edit_message_text(f"📥 Downloading...\n{progress_bar}", chat_id=chat_id, message_id=message_id)

    return file_path

# Handles file uploads and displays a live progress bar
def upload_to_drive(file_path, chat_id, message_id):
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

    # Generate shareable link
    file_id = response.get('id')
    permission = {'type': 'anyone', 'role': 'reader'}
    service.permissions().create(fileId=file_id, body=permission).execute()
    shareable_link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    return shareable_link

# Sanitizes long file names
def sanitize_file_name(file_name, max_length=50):
    if len(file_name) > max_length:
        base_name, ext = os.path.splitext(file_name)
        file_name = base_name[:max_length] + ext
    return file_name

###############################################################################
# Telegram Handlers

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! Send me a download link or a file, and I'll mirror it for you.")

@bot.message_handler(content_types=['text'])
def handle_text(message: Message):
    if is_download_link(message.text):
        sent_message = bot.reply_to(message, "🛠️ **Preparing to download...**")

        try:
            # Download file with progress bar
            file_path = download_file(message.text, chat_id=message.chat.id, message_id=sent_message.message_id)

            # Upload file with progress bar
            mirror_link = upload_to_drive(file_path, chat_id=message.chat.id, message_id=sent_message.message_id)

            # Completion message
            bot.edit_message_text(f"✅ **Task Completed!**\n"
                                  f"👤 User: @{message.from_user.username or 'Unknown'}\n"
                                  f"🔗 Mirror Link: {mirror_link}",
                                  chat_id=message.chat.id, message_id=sent_message.message_id)
        except Exception as e:
            bot.reply_to(message, f"❌ An error occurred: {str(e)}")
    else:
        bot.reply_to(message, "I only respond to valid download links or commands like /start, /help, and /status.")

###############################################################################
# Flask Routes

@app.route('/')
def index():
    return "Bot is running!"

@app.route('/' + TELEGRAM_TOKEN, methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "OK", 200

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    bot.remove_webhook()
    success = bot.set_webhook(url=BASE_URL + TELEGRAM_TOKEN)
    return jsonify({"status": "Webhook set" if success else "Failed to set webhook"})

@app.before_first_request
def init_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=BASE_URL + TELEGRAM_TOKEN)

###############################################################################
# Run the app
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
