import os
import logging
import pyodbc
import azure.identity
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# Load environment variables
load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Azure SQL Configuration
SQL_SERVER = os.getenv("AZURE_SQL_SERVER")
SQL_DATABASE = os.getenv("AZURE_SQL_DATABASE")

# Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
blob_service_client = BlobServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Azure AD Token for SQL Authentication
try:
    credential = azure.identity.DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/").token
except Exception as e:
    logger.error("Error getting Azure AD token: %s", e)
    exit()

# Connect to Azure SQL Database
try:
    conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER=tcp:{SQL_SERVER},1433;DATABASE={SQL_DATABASE};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    conn = pyodbc.connect(conn_str, attrs_before={"AccessToken": token})
    cursor = conn.cursor()
    logger.info("✅ Connected to Azure SQL Database successfully.")
except Exception as e:
    logger.error("❌ Database connection failed: %s", e)
    exit()

# Create Table (if not exists)
def create_table():
    try:
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'DownloadLinks')
            CREATE TABLE DownloadLinks (
                id INT IDENTITY(1,1) PRIMARY KEY,
                user_id NVARCHAR(255),
                original_link NVARCHAR(MAX),
                fast_link NVARCHAR(MAX),
                created_at DATETIME DEFAULT GETDATE()
            );
        """)
        conn.commit()
        logger.info("✅ Table checked/created successfully.")
    except Exception as e:
        logger.error("❌ Table creation failed: %s", e)

create_table()

# Store a new link
def store_link(user_id, original_link, fast_link):
    try:
        cursor.execute(
            "INSERT INTO DownloadLinks (user_id, original_link, fast_link) VALUES (?, ?, ?)",
            (user_id, original_link, fast_link),
        )
        conn.commit()
        logger.info(f"✅ Link stored successfully for user {user_id}.")
    except Exception as e:
        logger.error("❌ Error storing link: %s", e)

# Retrieve the latest fast link for a user
def get_fast_link(user_id):
    try:
        cursor.execute(
            "SELECT fast_link FROM DownloadLinks WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        row = cursor.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error("❌ Error retrieving link: %s", e)
        return None

# Upload File to Azure Blob Storage
def upload_to_blob(file_path, blob_name):
    try:
        blob_client = blob_service_client.get_blob_client(container="downloads", blob=blob_name)
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        blob_url = blob_client.url
        logger.info(f"✅ File uploaded to Blob Storage: {blob_url}")
        return blob_url
    except Exception as e:
        logger.error("❌ Blob upload failed: %s", e)
        return None

# Telegram Bot Commands
async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Hello! Send me a download link and I'll store it securely.")

async def handle_message(update: Update, context: CallbackContext) -> None:
    user_id = str(update.message.chat_id)
    original_link = update.message.text

    if original_link.startswith("http"):
        fast_link = f"https://cdn.example.com/{original_link.split('/')[-1]}"  # Simulated fast link
        store_link(user_id, original_link, fast_link)

        await update.message.reply_text(f"✅ Your link has been stored! Use this faster link:\n{fast_link}")
    else:
        await update.message.reply_text("❌ Please send a valid download link.")

async def get_last_link(update: Update, context: CallbackContext) -> None:
    user_id = str(update.message.chat_id)
    fast_link = get_fast_link(user_id)

    if fast_link:
        await update.message.reply_text(f"✅ Your last stored fast link:\n{fast_link}")
    else:
        await update.message.reply_text("❌ No stored links found.")

# Set up the bot
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("lastlink", get_last_link))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
