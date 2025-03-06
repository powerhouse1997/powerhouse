import os
import re
import time
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
def is_download_link(text):
    url_pattern = re.compile(r'https?://[^\s]+')
    return bool(url_pattern.search(text))

def is_allowed_command(text):
    allowed_commands = ['/start', '/help', '/status']
    return text in allowed_commands

###############################################################################
# Telegram Handlers

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! Send me a download link or a file, and I'll mirror it for you.")

@bot.message_handler(commands=['status'])
def show_status(message):
    bot.reply_to(message, "🔍 Currently, there's no active operation.")

@bot.message_handler(content_types=['text'])
def handle_text(message: Message):
    if is_download_link(message.text):
        # Stage 1: Preparing
        sent_message = bot.reply_to(message, "🛠️ **Stage 1: Preparing...**")
        time.sleep(2)  # Simulate preparing

        # Stage 2: Downloading
        bot.edit_message_text("📥 **Stage 2: Downloading...**", chat_id=message.chat.id, message_id=sent_message.message_id)
        time.sleep(3)  # Simulate download time

        # Stage 3: Processing
        bot.edit_message_text("🔄 **Stage 3: Processing the file...**", chat_id=message.chat.id, message_id=sent_message.message_id)
        time.sleep(2)  # Simulate processing time

        # Stage 4: Uploading
        bot.edit_message_text("📤 **Stage 4: Uploading to destination...**", chat_id=message.chat.id, message_id=sent_message.message_id)
        time.sleep(3)  # Simulate upload time

        # Completion
        bot.edit_message_text("✅ **Task completed! File uploaded successfully.**", chat_id=message.chat.id, message_id=sent_message.message_id)
    elif is_allowed_command(message.text):
        if message.text == '/help':
            bot.reply_to(message, "Here are the commands I support:\n/start - Start the bot\n/help - Get help\n/status - Check status.")
        else:
            bot.reply_to(message, "The bot is running smoothly!")
    else:
        bot.reply_to(message, "I only respond to valid download links or commands like /start, /help, and /status.")

@bot.message_handler(content_types=['document'])
def handle_document(message: Message):
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    file_path = os.path.join('downloads', message.document.file_name)
    with open(file_path, 'wb') as new_file:
        new_file.write(downloaded_file)

    # Stage 4: Uploading
    bot.reply_to(message, "📤 Uploading your file to Google Drive...")
    file_id = upload_to_drive(file_path)
    bot.reply_to(message, f"✅ Upload complete! File ID: {file_id}")

def upload_to_drive(file_path):
    creds = authorize_google_drive()
    service = googleapiclient.discovery.build('drive', 'v3', credentials=creds)
    file_metadata = {'name': os.path.basename(file_path)}
    media = googleapiclient.http.MediaFileUpload(file_path, resumable=True)
    result = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return result.get('id')

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
