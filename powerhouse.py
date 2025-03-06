import os
from flask import Flask, request
import telebot
import googleapiclient.discovery
import googleapiclient.http
import google_auth_oauthlib.flow
import google.auth.transport.requests
import google.oauth2.credentials

###############################################################################
# Configuration
# Directly using your provided API token. For security, consider using an environment variable instead.
TELEGRAM_TOKEN = '6438781804:AAGvcF5pp2gg2Svr5f0kpxvG9ZMoiG1WACc'

# If BASE_URL is not set in the environment, default to your Azure URL.
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
# Use a relative path so that it works in Azure.
CREDS_FILE = os.path.join(os.path.dirname(__file__), 'jarvis-400615-5d22aa4feea3.json')

def authorize_google_drive():
    """
    Authorizes with Google Drive using InstalledAppFlow.
    In production, consider using a service account to avoid the interactive flow.
    """
    creds = None
    if os.path.exists('token.json'):
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

###############################################################################
# Telegram Handlers

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! Send me a download link or a file, and I'll mirror it for you.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    link = message.text
    bot.reply_to(message, "Mirroring your download link...")
    # TODO: Add code to download the file from the link and then upload it to Google Drive.
    # For example:
    # file_path = download_file(link)
    # upload_to_drive(file_path)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    # Ensure the 'downloads' directory exists.
    if not os.path.exists('downloads'):
        os.makedirs('downloads')
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    file_path = os.path.join('downloads', message.document.file_name)
    with open(file_path, 'wb') as new_file:
        new_file.write(downloaded_file)
    bot.reply_to(message, "File received. Uploading to Google Drive...")
    upload_to_drive(file_path)

def upload_to_drive(file_path):
    """
    Uploads the file specified by file_path to Google Drive.
    """
    creds = authorize_google_drive()
    service = googleapiclient.discovery.build('drive', 'v3', credentials=creds)
    file_metadata = {'name': os.path.basename(file_path)}
    media = googleapiclient.http.MediaFileUpload(file_path, resumable=True)
    result = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return result.get('id')

###############################################################################
# Flask Routes: Telegram Webhook Endpoint

@app.route('/' + TELEGRAM_TOKEN, methods=['POST'])
def webhook():
    """
    Endpoint to receive updates from Telegram via webhook.
    """
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    return "Unsupported Media Type", 415

@app.before_first_request
def init_webhook():
    """
    Set the webhook when the Flask app receives its first request.
    """
    bot.remove_webhook()
    bot.set_webhook(url=BASE_URL + TELEGRAM_TOKEN)

###############################################################################
# For Local Development: Run via Flask's Development Server
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    # Use debug=True for local testing; remove in production.
    app.run(host="0.0.0.0", port=port, debug=True)
