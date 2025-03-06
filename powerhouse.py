import os
import re
import time
import shutil  # For calculating storage
import requests  # For downloading files from links
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

# Track bot's status
bot_status = {
    "username": None,
    "task": None,
    "speed": None,
    "total_storage": None,
    "remaining_storage": None,
}

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

def calculate_speed(start_time, file_size):
    elapsed_time = time.time() - start_time
    speed = file_size / elapsed_time  # bytes per second
    return f"{speed / (1024 * 1024):.2f} MB/s"  # Convert to MB/s

def calculate_storage():
    total, used, free = shutil.disk_usage(os.getcwd())
    return {
        "total": f"{total / (1024 * 1024 * 1024):.2f} GB",
        "used": f"{used / (1024 * 1024 * 1024):.2f} GB",
        "free": f"{free / (1024 * 1024 * 1024):.2f} GB",
    }

###############################################################################
# Google Drive Upload Function with Shareable Link
def upload_to_drive(file_path):
    creds = authorize_google_drive()
    service = googleapiclient.discovery.build('drive', 'v3', credentials=creds)
    file_metadata = {'name': os.path.basename(file_path)}
    media = googleapiclient.http.MediaFileUpload(file_path, resumable=True)
    result = service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    # Generate a shareable link
    file_id = result.get('id')
    permission = {'type': 'anyone', 'role': 'reader'}
    service.permissions().create(fileId=file_id, body=permission).execute()
    shareable_link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    return shareable_link

###############################################################################
# Telegram Handlers

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! Send me a download link or a file, and I'll mirror it for you.")

@bot.message_handler(commands=['status'])
def show_status(message):
    storage = calculate_storage()
    bot.reply_to(
        message,
        f"📊 **Bot Status:**\n"
        f"- Current Task: {bot_status['task'] or 'Idle'}\n"
        f"- User: {bot_status['username'] or 'N/A'}\n"
        f"- Speed: {bot_status['speed'] or 'N/A'}\n"
        f"- Total Storage: {storage['total']}\n"
        f"- Used Storage: {storage['used']}\n"
        f"- Free Storage: {storage['free']}"
    )

@bot.message_handler(content_types=['text'])
def handle_text(message: Message):
    if is_download_link(message.text):
        bot_status["username"] = message.from_user.username or "Unknown"
        bot_status["task"] = "Downloading"

        # Stage 1: Download File
        sent_message = bot.reply_to(message, "🛠️ Starting download from link...")
        try:
            start_time = time.time()
            response = requests.get(message.text, stream=True)
            file_size = int(response.headers.get('content-length', 0))
            file_name = message.text.split("/")[-1]
            file_path = os.path.join("downloads", file_name)

            if not os.path.exists("downloads"):
                os.makedirs("downloads")

            with open(file_path, "wb") as file:
                downloaded = 0
                for chunk in response.iter_content(1024):
                    file.write(chunk)
                    downloaded += len(chunk)
                    bot_status["speed"] = calculate_speed(start_time, downloaded)
                    progress = int((downloaded / file_size) * 100)
                    bot.edit_message_text(
                        f"📥 Downloading: {progress}%\nSpeed: {bot_status['speed']}",
                        chat_id=message.chat.id,
                        message_id=sent_message.message_id,
                    )

            # Uploading file to Google Drive
            bot_status["task"] = "Uploading"
            bot.edit_message_text("📤 Uploading to Google Drive...", chat_id=message.chat.id, message_id=sent_message.message_id)
            mirror_link = upload_to_drive(file_path)
            bot_status["task"] = "Idle"
            bot.reply_to(message, f"✅ Upload complete! Here is your mirror link:\n{mirror_link}")
        except Exception as e:
            bot.reply_to(message, f"❌ An error occurred: {str(e)}")
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

    bot.reply_to(message, "📤 Uploading your file to Google Drive...")
    try:
        mirror_link = upload_to_drive(file_path)
        bot.reply_to(message, f"✅ Upload complete! Here is your mirror link:\n{mirror_link}")
    except Exception as e:
        bot.reply_to(message, f"❌ An error occurred while uploading the file: {str(e)}")

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
