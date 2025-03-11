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
TELEGRAM_TOKEN = '6438781804:AAGvcF5pp2gg2Svr5f0kpxvG9ZMoiG1WACc' 
BASE_URL = os.environ.get('BASE_URL', 'https://mirrorbot-d5ewf6egd3a5baby.canadacentral-01.azurewebsites.net/') 
REDIS_HOST = os.getenv('REDIS_HOST', 'powerhouse.redis.cache.windows.net') 
REDIS_PORT = int(os.getenv('REDIS_PORT', 6380)) 
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', 'c3w6mCF18yaVK4UDPs71SCfvWocGeJVKMAzCaA46bvI=')
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
    try:
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        file_name = sanitize_file_name(response.url.split("/")[-1]) or f"file_{uuid.uuid4().hex}.bin"
        
        # Ensure 'downloads' directory exists
        download_dir = 'downloads'
        os.makedirs(download_dir, exist_ok=True)
        
        file_path = os.path.join(download_dir, file_name)

        with open(file_path, 'wb') as f:
            downloaded_size = 0
            for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                f.write(chunk)
                downloaded_size += len(chunk)
                progress_bar = create_progress_bar(downloaded_size, total_size)
                bot.edit_message_text(f"📥 Downloading...\n{progress_bar}", chat_id=chat_id, message_id=message_id)

        return file_path
    except Exception as e:
        print(f"Error downloading file: {str(e)}")
        bot.edit_message_text(f"❌ An error occurred while downloading: {str(e)}", chat_id=chat_id, message_id=message_id)
        return None

# Handles file uploads and displays a live progress bar
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

        # Generate shareable link
        file_id = response.get('id')
        permission = {'type': 'anyone', 'role': 'reader'}
        service.permissions().create(fileId=file_id, body=permission).execute()
        shareable_link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
        return shareable_link
    except Exception as e:
        print(f"Error uploading file: {str(e)}")
        bot.edit_message_text(f"❌ An error occurred while uploading: {str(e)}", chat_id=chat_id, message_id=message_id)
        return None

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

def is_download_link(text):
    url_pattern = re.compile(r'^(https?://)?(www\.)?([a-zA-Z0-9-]{1,63}\.){1,8}[a-zA-Z]{2,6}(/[\w\-.~:?#%&/=]*)?$')
    return re.match(url_pattern, text) is not None

@bot.message_handler(content_types=['text'])
def handle_text(message: Message):
    if is_download_link(message.text):
        sent_message = bot.reply_to(message, "🛠️ **Preparing to process the link...**")

        try:
            # Download file with live progress
            file_path = download_file(message.text, chat_id=message.chat.id, message_id=sent_message.message_id)

            if file_path:
                # Upload file with live progress
                mirror_link = upload_to_drive(file_path, chat_id=message.chat.id, message_id=sent_message.message_id)

                if mirror_link:
                    # Send success message
                    bot.edit_message_text(f"✅ **Task Completed!**\n"
                                          f"👤 User: @{message.from_user.username or 'Unknown'}\n"
                                          f"🔗 Mirror Link: {mirror_link}",
                                          chat_id=message.chat.id, message_id=sent_message.message_id)
                else:
                    bot.edit_message_text(f"❌ An error occurred while uploading the file.", chat_id=message.chat.id, message_id=sent_message.message_id)
            else:
                bot.edit_message_text(f"❌ An error occurred while downloading the file.", chat_id=message.chat.id, message_id=sent_message.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ An error occurred: {str(e)}", chat_id=message.chat.id, message_id=sent_message.message_id)
            print(f"Error processing link: {str(e)}")  # Debug log
    else:
        bot.reply_to(message, "I only respond to valid download links or commands like /start, /help, and /status.")
        print(f"Unsupported message: {message.text}")  # Debug log

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

@app.route('/set_webhook', methods=['GET', 'POST'])
def set_webhook():
    bot.remove_webhook()
    success = bot.set_webhook(url=BASE_URL + TELEGRAM_TOKEN)
    return jsonify({"status": "Webhook set" if success else "Failed to set webhook", "url": BASE_URL + TELEGRAM_TOKEN})

# Removed the before_first_request decorator as it caused an issue

###############################################################################
# Run the app
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
