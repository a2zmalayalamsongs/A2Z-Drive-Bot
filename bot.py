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
# YEAR PAGINATION
# =========================

YEARS_PER_PAGE = 10


def get_year_folders():

    items = get_items(ROOT_FOLDER_ID)

    folders = []

    for item in items:

        if item["mimeType"] == "application/vnd.google-apps.folder":

            name = item["name"].strip()

            # Only numeric year folders
            try:
                year = int(name)

                if 1980 <= year <= 2027:
                    folders.append(item)

            except ValueError:
                pass

    # Newest year first
    folders.sort(
        key=lambda x: int(x["name"].strip()),
        reverse=True
    )

    return folders


def build_year_keyboard(page=0):

    folders = get_year_folders()

    total_pages = (
        (len(folders) + YEARS_PER_PAGE - 1)
        // YEARS_PER_PAGE
    )

    if total_pages == 0:
        return InlineKeyboardMarkup([])

    # Safety
    if page < 0:
        page = 0

    if page >= total_pages:
        page = total_pages - 1

    start_index = page * YEARS_PER_PAGE
    end_index = start_index + YEARS_PER_PAGE

    page_folders = folders[start_index:end_index]

    keyboard = []

    for item in page_folders:

        keyboard.append([
            InlineKeyboardButton(
                "📁 " + item["name"],
                callback_data="folder:" + item["id"]
            )
        ])

    # Pagination buttons
    navigation = []

    if page > 0:

        navigation.append(
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data=f"yearpage:{page - 1}"
            )
        )

    if page < total_pages - 1:

        navigation.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data=f"yearpage:{page + 1}"
            )
        )

    if navigation:
        keyboard.append(navigation)

    # Page number
    keyboard.append([
        InlineKeyboardButton(
            f"📄 Page {page + 1}/{total_pages}",
            callback_data="nop"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


# =========================
# START
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = build_year_keyboard(0)

    await update.message.reply_text(
        "🎵 A2Z Malayalam Songs\n\n"
        "📂 Select a year:",
        reply_markup=keyboard
    )


# =========================
# YEAR PAGINATION CALLBACK
# =========================

async def yearpage_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    page = int(
        query.data.split(":", 1)[1]
    )

    keyboard = build_year_keyboard(page)

    await query.edit_message_text(
        "🎵 A2Z Malayalam Songs\n\n"
        "📂 Select a year:",
        reply_markup=keyboard
    )


# =========================
# EMPTY BUTTON
# =========================

async def nop_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()


# =========================
# FOLDER NAVIGATION
# =========================

async def folder_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

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

async def file_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer(
        "Downloading..."
    )

    file_id = query.data.split(":", 1)[1]

    file_info = drive.files().get(
        fileId=file_id,
        fields="id,name,mimeType,size"
    ).execute()

    file_name = file_info["name"]

    request = drive.files().get_media(
        fileId=file_id
    )

    with tempfile.NamedTemporaryFile(
        delete=False
    ) as temp:

        temp_path = temp.name

        downloader = MediaIoBaseDownload(
            temp,
            request
        )

        done = False

        while not done:

            _, done = downloader.next_chunk()

    try:

        with open(
            temp_path,
            "rb"
        ) as f:

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

async def home_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    keyboard = build_year_keyboard(0)

    await query.edit_message_text(
        "🎵 A2Z Malayalam Songs\n\n"
        "📂 Select a year:",
        reply_markup=keyboard
    )


# =========================
# MAIN
# =========================

def main():

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # /start
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # Year pagination
    app.add_handler(
        CallbackQueryHandler(
            yearpage_callback,
            pattern=r"^yearpage:"
        )
    )

    # Page number button
    app.add_handler(
        CallbackQueryHandler(
            nop_callback,
            pattern=r"^nop$"
        )
    )

    # Folder
    app.add_handler(
        CallbackQueryHandler(
            folder_callback,
            pattern=r"^folder:"
        )
    )

    # File download
    app.add_handler(
        CallbackQueryHandler(
            file_callback,
            pattern=r"^file:"
        )
    )

    # Home
    app.add_handler(
        CallbackQueryHandler(
            home_callback,
            pattern=r"^home$"
        )
    )

    print("Bot started...")

    app.run_polling()


# =========================
# RUN
# =========================

if __name__ == "__main__":
    main()
