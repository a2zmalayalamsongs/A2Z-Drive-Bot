import os
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


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]

ROOT_FOLDER_ID = os.environ["ROOT_FOLDER_ID"]

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]

# Google Service Account credentials
credentials = service_account.Credentials.from_service_account_info(
    json.loads(os.environ["GOOGLE_CREDENTIALS"]),
    scopes=SCOPES
)

drive = build(
    "drive",
    "v3",
    credentials=credentials
)


# =========================================================
# GOOGLE DRIVE - GET ITEMS
# =========================================================

def get_items(folder_id):

    query = (
        f"'{folder_id}' in parents "
        "and trashed = false"
    )

    results = drive.files().list(
        q=query,
        fields="files(id,name,mimeType,size)",
        pageSize=1000
    ).execute()

    return results.get("files", [])


# =========================================================
# GET YEAR FOLDERS
# 1980 - 2027 ONLY
# =========================================================

def get_year_folders():

    items = get_items(ROOT_FOLDER_ID)

    years = []

    for item in items:

        if item["mimeType"] != "application/vnd.google-apps.folder":
            continue

        name = item["name"].strip()

        if name.isdigit():

            year = int(name)

            if 1980 <= year <= 2027:

                years.append(item)

    # NEW YEAR FIRST
    years.sort(
        key=lambda x: int(x["name"]),
        reverse=True
    )

    return years


# =========================================================
# YEAR PAGINATION
# 10 YEARS PER PAGE
# =========================================================

YEARS_PER_PAGE = 10


def build_year_keyboard(page=0):

    years = get_year_folders()

    total_pages = (
        (len(years) + YEARS_PER_PAGE - 1)
        // YEARS_PER_PAGE
    )

    if total_pages == 0:
        total_pages = 1

    # Safety
    if page < 0:
        page = 0

    if page >= total_pages:
        page = total_pages - 1

    start = page * YEARS_PER_PAGE
    end = start + YEARS_PER_PAGE

    page_years = years[start:end]

    keyboard = []

    # YEAR BUTTONS
    for item in page_years:

        keyboard.append([
            InlineKeyboardButton(
                "📁 " + item["name"],
                callback_data=f"folder:{item['id']}:{page}"
            )
        ])

    # PAGINATION BUTTONS
    navigation = []

    if page > 0:

        navigation.append(
            InlineKeyboardButton(
                "⬅️ Previous",
                callback_data=f"years:{page - 1}"
            )
        )

    if page < total_pages - 1:

        navigation.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data=f"years:{page + 1}"
            )
        )

    if navigation:
        keyboard.append(navigation)

    # PAGE NUMBER
    keyboard.append([
        InlineKeyboardButton(
            f"📄 Page {page + 1}/{total_pages}",
            callback_data="noop"
        )
    ])

    return keyboard


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    keyboard = build_year_keyboard(0)

    await update.message.reply_text(
        "🎵 A2Z Malayalam Songs\n\n"
        "📂 Select a year:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# YEAR PAGINATION CALLBACK
# =========================================================

async def years_callback(
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
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# NO OP BUTTON
# =========================================================

async def noop_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()


# =========================================================
# OPEN YEAR / FOLDER
# =========================================================

async def folder_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    data = query.data.split(":")

    folder_id = data[1]

    # Root year page from which this folder was opened
    page = int(data[2])

    items = get_items(folder_id)

    keyboard = []

    # -----------------------------------------------------
    # FOLDERS FIRST
    # -----------------------------------------------------

    folders = []

    files = []

    for item in items:

        if item["mimeType"] == "application/vnd.google-apps.folder":
            folders.append(item)

        else:
            files.append(item)

    # Alphabetical
    folders.sort(
        key=lambda x: x["name"].lower()
    )

    files.sort(
        key=lambda x: x["name"].lower()
    )

    # -----------------------------------------------------
    # ALBUM FOLDERS
    # -----------------------------------------------------

    for item in folders:

        keyboard.append([
            InlineKeyboardButton(
                "📁 " + item["name"],
                callback_data=f"folder:{item['id']}:{page}"
            )
        ])

    # -----------------------------------------------------
    # SONG FILES
    # -----------------------------------------------------

    for item in files:

        keyboard.append([
            InlineKeyboardButton(
                "🎵 " + item["name"],
                callback_data=f"file:{item['id']}"
            )
        ])

    # -----------------------------------------------------
    # BACK TO YEAR PAGE
    # -----------------------------------------------------

    keyboard.append([
        InlineKeyboardButton(
            "🔙 Back to Years",
            callback_data=f"years:{page}"
        )
    ])

    await query.edit_message_text(
        "📂 Select:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# FILE DOWNLOAD
# =========================================================

async def file_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer(
        "⏳ Downloading..."
    )

    file_id = query.data.split(":", 1)[1]

    try:

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

                status, done = downloader.next_chunk()

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

            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:

        await query.message.reply_text(
            "❌ Download failed.\n\n"
            f"Error: {e}"
        )


# =========================================================
# BACK TO YEARS
# =========================================================

async def home_callback(
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
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# MAIN
# =========================================================

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
            years_callback,
            pattern=r"^years:\d+$"
        )
    )

    # No-op
    app.add_handler(
        CallbackQueryHandler(
            noop_callback,
            pattern=r"^noop$"
        )
    )

    # Folder
    app.add_handler(
        CallbackQueryHandler(
            folder_callback,
            pattern=r"^folder:"
        )
    )

    # File
    app.add_handler(
        CallbackQueryHandler(
            file_callback,
            pattern=r"^file:"
        )
    )

    # Back
    app.add_handler(
        CallbackQueryHandler(
            home_callback,
            pattern=r"^home:\d+$"
        )
    )

    print("A2Z Malayalam Songs Bot started...")

    # Keep bot running
    app.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
