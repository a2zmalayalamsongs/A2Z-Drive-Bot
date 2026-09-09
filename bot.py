import os
import tempfile
import json

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

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


# =========================================================
# GOOGLE DRIVE LOGIN
# =========================================================

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
# CONSTANTS
# =========================================================

FOLDER_MIME = "application/vnd.google-apps.folder"

# 10 YEARS PER PAGE
YEARS_PER_PAGE = 10


# =========================================================
# GET DRIVE ITEMS
# =========================================================

def get_items(folder_id):

    query = (
        f"'{folder_id}' in parents "
        "and trashed = false"
    )

    response = drive.files().list(
        q=query,
        fields="files(id,name,mimeType,size)",
        pageSize=1000
    ).execute()

    return response.get("files", [])


# =========================================================
# GET YEAR FOLDERS
# =========================================================
#
# Any numeric folder directly inside ROOT_FOLDER_ID
# will be treated as a year.
#
# No minimum / maximum year.
#
# Example:
# 2030
# 2029
# 2028
# ...
# 1980
# 1979
# 1978
#
# New years added to Drive automatically appear.
# =========================================================

def get_year_folders():

    items = get_items(ROOT_FOLDER_ID)

    years = []

    for item in items:

        # Only folders
        if item.get("mimeType") != FOLDER_MIME:
            continue

        name = item.get("name", "").strip()

        # Only numeric folder names
        if not name.isdigit():
            continue

        years.append({
            "id": item["id"],
            "name": name,
            "year": int(name)
        })

    # Newest year first
    years.sort(
        key=lambda x: x["year"],
        reverse=True
    )

    return years


# =========================================================
# BUILD YEAR KEYBOARD
#
# 2 COLUMNS
# 5 ROWS
# = 10 YEARS
# =========================================================

def build_year_keyboard(page=0):

    years = get_year_folders()

    # Total pages
    total_pages = max(
        1,
        (len(years) + YEARS_PER_PAGE - 1)
        // YEARS_PER_PAGE
    )

    # Keep page valid
    if page < 0:
        page = 0

    if page >= total_pages:
        page = total_pages - 1

    # Page start/end
    start_index = page * YEARS_PER_PAGE
    end_index = start_index + YEARS_PER_PAGE

    page_years = years[
        start_index:end_index
    ]

    keyboard = []

    # =====================================================
    # 2 YEAR BUTTONS PER ROW
    # =====================================================

    row = []

    for item in page_years:

        row.append(
            InlineKeyboardButton(
                f"📁 {item['name']}",
                callback_data=(
                    f"year:{item['id']}:{page}"
                )
            )
        )

        # Every 2 buttons = new row
        if len(row) == 2:

            keyboard.append(row)

            row = []

    # If odd number of years on last page
    if row:
        keyboard.append(row)

    # =====================================================
    # PREVIOUS / NEXT
    # =====================================================

    navigation = []

    if page > 0:

        navigation.append(
            InlineKeyboardButton(
                "⬅️ Previous",
                callback_data=f"page:{page - 1}"
            )
        )

    if page < total_pages - 1:

        navigation.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data=f"page:{page + 1}"
            )
        )

    if navigation:

        keyboard.append(navigation)

    # =====================================================
    # PAGE NUMBER
    # =====================================================

    keyboard.append([
        InlineKeyboardButton(
            f"📄 Page {page + 1} / {total_pages}",
            callback_data="nothing"
        )
    ])

    return keyboard


# =========================================================
# SHOW YEARS
# =========================================================

async def show_years(
    message,
    page=0,
    edit=False
):

    keyboard = build_year_keyboard(page)

    text = (
        "🎵 A2Z Malayalam Songs\n\n"
        "📂 Select a year:"
    )

    markup = InlineKeyboardMarkup(keyboard)

    if edit:

        await message.edit_text(
            text,
            reply_markup=markup
        )

    else:

        await message.reply_text(
            text,
            reply_markup=markup
        )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await show_years(
        update.message,
        page=0,
        edit=False
    )


# =========================================================
# YEAR PAGINATION
# =========================================================

async def page_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    page = int(
        query.data.split(":")[1]
    )

    keyboard = build_year_keyboard(page)

    await query.edit_message_text(
        "🎵 A2Z Malayalam Songs\n\n"
        "📂 Select a year:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================================================
# OPEN YEAR
# =========================================================

async def year_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    parts = query.data.split(":")

    folder_id = parts[1]

    # Remember year page
    page = int(parts[2])

    items = get_items(folder_id)

    folders = []
    files = []

    # Separate folders and files
    for item in items:

        if item.get("mimeType") == FOLDER_MIME:

            folders.append(item)

        else:

            files.append(item)

    # Sort album folders
    folders.sort(
        key=lambda x: x.get(
            "name",
            ""
        ).lower()
    )

    # Sort song files
    files.sort(
        key=lambda x: x.get(
            "name",
            ""
        ).lower()
    )

    keyboard = []

    # =====================================================
    # ALBUM / SUB FOLDERS
    # =====================================================

    for item in folders:

        keyboard.append([
            InlineKeyboardButton(
                "📁 " + item["name"],
                callback_data=(
                    f"folder:{item['id']}:{page}"
                )
            )
        ])

    # =====================================================
    # SONG FILES
    # =====================================================

    for item in files:

        keyboard.append([
            InlineKeyboardButton(
                "🎵 " + item["name"],
                callback_data=(
                    f"file:{item['id']}"
                )
            )
        ])

    # =====================================================
    # BACK TO YEARS
    # =====================================================

    keyboard.append([
        InlineKeyboardButton(
            "🔙 Back to Years",
            callback_data=f"page:{page}"
        )
    ])

    await query.edit_message_text(
        "📂 Select:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================================================
# OPEN SUB FOLDER
# =========================================================

async def folder_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    parts = query.data.split(":")

    folder_id = parts[1]

    # Original year page
    page = int(parts[2])

    items = get_items(folder_id)

    folders = []
    files = []

    # Separate folders/files
    for item in items:

        if item.get("mimeType") == FOLDER_MIME:

            folders.append(item)

        else:

            files.append(item)

    # Sort folders
    folders.sort(
        key=lambda x: x.get(
            "name",
            ""
        ).lower()
    )

    # Sort files
    files.sort(
        key=lambda x: x.get(
            "name",
            ""
        ).lower()
    )

    keyboard = []

    # =====================================================
    # SUB FOLDERS
    # =====================================================

    for item in folders:

        keyboard.append([
            InlineKeyboardButton(
                "📁 " + item["name"],
                callback_data=(
                    f"folder:{item['id']}:{page}"
                )
            )
        ])

    # =====================================================
    # FILES / SONGS
    # =====================================================

    for item in files:

        keyboard.append([
            InlineKeyboardButton(
                "🎵 " + item["name"],
                callback_data=(
                    f"file:{item['id']}"
                )
            )
        ])

    # =====================================================
    # BACK TO YEARS
    # =====================================================

    keyboard.append([
        InlineKeyboardButton(
            "🔙 Back to Years",
            callback_data=f"page:{page}"
        )
    ])

    await query.edit_message_text(
        "📂 Select:",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
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

    file_id = query.data.split(
        ":",
        1
    )[1]

    temp_path = None

    try:

        # =================================================
        # GET FILE INFORMATION
        # =================================================

        file_info = drive.files().get(
            fileId=file_id,
            fields="id,name,mimeType,size"
        ).execute()

        file_name = file_info.get(
            "name",
            "download"
        )

        # =================================================
        # DOWNLOAD
        # =================================================

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

                status, done = (
                    downloader.next_chunk()
                )

        # =================================================
        # SEND FILE TO TELEGRAM
        # =================================================

        with open(
            temp_path,
            "rb"
        ) as file:

            await query.message.reply_document(
                document=file,
                filename=file_name,
                caption="🎵 " + file_name
            )

    except Exception as e:

        await query.message.reply_text(
            "❌ Download failed.\n\n"
            f"{str(e)}"
        )

    finally:

        if (
            temp_path
            and os.path.exists(temp_path)
        ):

            try:
                os.remove(temp_path)

            except Exception:
                pass


# =========================================================
# PAGE NUMBER BUTTON
# =========================================================

async def nothing_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.callback_query.answer()


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

    # START
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # YEAR PAGES
    app.add_handler(
        CallbackQueryHandler(
            page_callback,
            pattern=r"^page:\d+$"
        )
    )

    # YEAR
    app.add_handler(
        CallbackQueryHandler(
            year_callback,
            pattern=r"^year:"
        )
    )

    # SUB FOLDER
    app.add_handler(
        CallbackQueryHandler(
            folder_callback,
            pattern=r"^folder:"
        )
    )

    # FILE
    app.add_handler(
        CallbackQueryHandler(
            file_callback,
            pattern=r"^file:"
        )
    )

    # PAGE NUMBER
    app.add_handler(
        CallbackQueryHandler(
            nothing_callback,
            pattern=r"^nothing$"
        )
    )

    # START BOT
    print(
        "A2Z Malayalam Songs Bot started..."
    )

    app.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    main()
