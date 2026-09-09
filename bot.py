import os
import io
import tempfile
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.environ["BOT_TOKEN"]

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

ROOT_FOLDER_ID = os.environ["ROOT_FOLDER_ID"]


# =========================
# GOOGLE DRIVE
# =========================

credentials = service_account.Credentials.from_service_account_info(
    json.loads(os.environ["GOOGLE_CREDENTIALS"]),
    scopes=SCOPES
)

drive = build("drive", "v3", credentials=credentials)


# =========================
# GET ITEMS
# =========================

def get_items(folder_id):
    query = (
        f"'{folder_id}' in parents "
        "and trashed = false"
    )

    results = drive.files().list(
        q=query,
        fields="files(id,name,mimeType,size)",
        orderBy="name"
    ).execute()

    return results.get("files", [])


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    items = get_items(ROOT_FOLDER_ID)

    keyboard = []

    for item in items:

        if item["mimeType"] == "application/vnd.google-apps.folder":

            keyboard.append([
                InlineKeyboardButton(
                    "📁 " + item["name"],
                    callback_data="folder:" + item["id"]
                )
            ])

    await update.message.reply_text(
        "🎵 A2Z Malayalam Songs\n\n"
        "📂 Select a year:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# FOLDER NAVIGATION
# =========================

async def folder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    folder_id = query.data.split(":", 1)[1]

    items = get_items(folder_id)

    keyboard = []

    for item in items:

        mime = item["mimeType"]

        if mime == "application/vnd.google-apps.folder":

            keyboard.append([
                InlineKeyboardButton(
                    "📁 " + item["name"],
                    callback_data="folder:" + item["id"]
                )
            ])

        else:

            keyboard.append([
                InlineKeyboardButton(
                    "🎵 " + item["name"],
                    callback_data="file:" + item["id"]
                )
            ])

    keyboard.append([
        InlineKeyboardButton(
            "🔙 Back",
            callback_data="home"
        )
    ])

    await query.edit_message_text(
        "📂 Select:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# FILE DOWNLOAD
# =========================

async def file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer("Downloading...")

    file_id = query.data.split(":", 1)[1]

    file_info = drive.files().get(
        fileId=file_id,
        fields="id,name,mimeType,size"
    ).execute()

    file_name = file_info["name"]

    request = drive.files().get_media(fileId=file_id)

    with tempfile.NamedTemporaryFile(delete=False) as temp:

        temp_path = temp.name

        downloader = MediaIoBaseDownload(
            temp,
            request
        )

        done = False

        while not done:
            _, done = downloader.next_chunk()

    try:

        with open(temp_path, "rb") as f:

            await query.message.reply_document(
                document=f,
                filename=file_name,
                caption="🎵 " + file_name
            )

    finally:

        os.remove(temp_path)


# =========================
# HOME
# =========================

async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    items = get_items(ROOT_FOLDER_ID)

    keyboard = []

    for item in items:

        if item["mimeType"] == "application/vnd.google-apps.folder":

            keyboard.append([
                InlineKeyboardButton(
                    "📁 " + item["name"],
                    callback_data="folder:" + item["id"]
                )
            ])

    await query.edit_message_text(
        "🎵 A2Z Malayalam Songs\n\n"
        "📂 Select a year:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# MAIN
# =========================

def main():

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CallbackQueryHandler(
            folder_callback,
            pattern="^folder:"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            file_callback,
            pattern="^file:"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            home_callback,
            pattern="^home$"
        )
    )

    print("Bot started...")

    app.run_polling()


# =========================
# RUN
# =========================

if __name__ == "__main__":
    main()
