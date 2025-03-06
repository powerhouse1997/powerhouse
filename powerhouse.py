import telebot
import os
import googleapiclient.discovery
import googleapiclient.http
import google_auth_oauthlib.flow
import google.auth.transport.requests
import google.oauth2.credentials

# Telegram bot token
API_TOKEN = '6438781804:AAGvcF5pp2gg2Svr5f0kpxvG9ZMoiG1WACc'

# Set up the bot
bot = telebot.TeleBot(API_TOKEN)

# Google Drive credentials
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDS_FILE = 'C:\\Users\\IFIG\\Pictures\\Bot\\jarvis-400615-5d22aa4feea3.json'

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

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! Send me a download link or a file, and I'll mirror it for you.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    link = message.text
    bot.reply_to(message, "Mirroring your download link...")
    # Add your code to download the file from the link and upload it to Google Drive here
    # Example: download_file(link) and upload_to_drive(file_path)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    file_path = os.path.join('downloads', message.document.file_name)
    with open(file_path, 'wb') as new_file:
        new_file.write(downloaded_file)
    bot.reply_to(message, "File received. Uploading to Google Drive...")
    # Add your code to upload the file to Google Drive here
    # Example: upload_to_drive(file_path)

def upload_to_drive(file_path):
    creds = authorize_google_drive()
    service = googleapiclient.discovery.build('drive', 'v3', credentials=creds)
    file_metadata = {'name': os.path.basename(file_path)}
    media = googleapiclient.http.MediaFileUpload(file_path, resumable=True)
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

if __name__ == '__main__':
    bot.polling()
