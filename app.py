from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext

TOKEN = "6438781804:AAGvcF5pp2gg2Svr5f0kpxvG9ZMoiG1WACc"

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Hello! I'm your bot.")

async def help_command(update: Update, context: CallbackContext):
    await update.message.reply_text("Available commands:\n/start - Start the bot\n/help - Get help")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
