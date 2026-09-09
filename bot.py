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

YEARS_PER_PAGE = 10

IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp"
)


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

def get_year_folders():

    items = get_items(ROOT_FOLDER_ID)

    years = []

    for item in items:

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
# 2 COLUMNS × 5 ROWS
# =========================================================

def build_year_keyboard(page=0):

    years = get_year_folders()

    total_pages = max(
        1,
        (len(years) + YEARS_PER_PAGE - 1)
        // YEARS_PER_PAGE
    )

    if page < 0:
        page = 0

    if page >= total_pages:
        page = total_pages - 1

    start_index = page * YEARS_PER_PAGE

    end_index = start_index + YEARS_PER_PAGE

    page_years = years[
        start_index:end_index
    ]

    keyboard = []

    row = []

    # =====================================================
    # YEAR BUTTONS
    # =====================================================

    for item in page_years:

        row.append(
            InlineKeyboardButton(
                f"📁 {item['name']}",
                callback_data=(
                    f"year:{item['id']}:{page}"
                )
            )
        )

        # 2 buttons per row
        if len(row) == 2:

            keyboard.append(row)

            row = []

    # Remaining button
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

    markup = InlineKeyboardMarkup(keyboard)

    # If current message is a photo,
    # delete it and send a normal year message.
    if query.message.photo:

        await query.message.delete()

        await query.message.chat.send_message(
            "🎵 A2Z Malayalam Songs\n\n"
            "📂 Select a year:",
            reply_markup=markup
        )

    else:

        await query.edit_message_text(
            "🎵 A2Z Malayalam Songs\n\n"
            "📂 Select a year:",
            reply_markup=markup
        )


# =========================================================
# DOWNLOAD DRIVE FILE TO TEMP FILE
# =========================================================

def download_drive_file(
    file_id,
    suffix=""
):

    temp_path = None

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix
    ) as temp:

        temp_path = temp.name

        request = drive.files().get_media(
            fileId=file_id
        )

        downloader = MediaIoBaseDownload(
            temp,
            request
        )

        done = False

        while not done:

            status, done = (
                downloader.next_chunk()
            )

    return temp_path


# =========================================================
# READ INFO.TXT
# =========================================================

def read_info_file(info_file_id):

    temp_path = None

    try:

        temp_path = download_drive_file(
            info_file_id,
            suffix=".txt"
        )

        with open(
            temp_path,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as file:

            text = file.read()

        return text

    except Exception:

        return ""

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
# PARSE INFO.TXT
# =========================================================

def parse_info(text, folder_name):

    data = {
        "album": folder_name,
        "singer": "",
        "music": "",
        "director": "",
        "artists": ""
    }

    for line in text.splitlines():

        line = line.strip()

        if not line or ":" not in line:
            continue

        key, value = line.split(
            ":",
            1
        )

        key = key.strip().lower()

        value = value.strip()

        if key in (
            "album",
            "album name"
        ):
            data["album"] = value

        elif key in (
            "singer",
            "singers"
        ):
            data["singer"] = value

        elif key in (
            "music",
            "music by",
            "music director"
        ):
            data["music"] = value

        elif key in (
            "director",
            "directed by"
        ):
            data["director"] = value

        elif key in (
            "artist",
            "artists",
            "cast"
        ):
            data["artists"] = value

    return data


# =========================================================
# CREATE ALBUM CAPTION
# =========================================================

def create_album_caption(
    info,
    has_image=False
):

    caption = (
        "🎬 <b>Album</b> : "
        + info["album"]
    )

    if info["singer"]:

        caption += (
            "\n🎤 <b>Singer</b> : "
            + info["singer"]
        )

    if info["music"]:

        caption += (
            "\n🎵 <b>Music By</b> : "
            + info["music"]
        )

    if info["director"]:

        caption += (
            "\n🎬 <b>Director</b> : "
            + info["director"]
        )

    if info["artists"]:

        caption += (
            "\n👥 <b>Artists</b> : "
            + info["artists"]
        )

    return caption


# =========================================================
# BUILD ALBUM KEYBOARD
# =========================================================

def build_album_keyboard(
    folders,
    files,
    page
):

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

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# SHOW ALBUM / MOVIE
# =========================================================

async def show_album(
    query,
    folder_id,
    page
):

    items = get_items(folder_id)

    folders = []
    files = []

    image_file = None
    info_file = None

    # =====================================================
    # FIND IMAGE + INFO
    # =====================================================

    for item in items:

        name = item.get(
            "name",
            ""
        ).strip()

        lower_name = name.lower()

        if item.get("mimeType") == FOLDER_MIME:

            folders.append(item)

        else:

            # info.txt
            if lower_name == "info.txt":

                info_file = item

            # Movie image
            elif lower_name.endswith(
                IMAGE_EXTENSIONS
            ):

                if image_file is None:
                    image_file = item

                else:
                    files.append(item)

            else:

                files.append(item)

    # =====================================================
    # SORT
    # =====================================================

    folders.sort(
        key=lambda x: x.get(
            "name",
            ""
        ).lower()
    )

    files.sort(
        key=lambda x: x.get(
            "name",
            ""
        ).lower()
    )

    # =====================================================
    # ALBUM INFO
    # =====================================================

    folder_name = ""

    # Get folder name
    folder_info = drive.files().get(
        fileId=folder_id,
        fields="name"
    ).execute()

    folder_name = folder_info.get(
        "name",
        "Album"
    )

    info_text = ""

    if info_file:

        info_text = read_info_file(
            info_file["id"]
        )

    info = parse_info(
        info_text,
        folder_name
    )

    caption = create_album_caption(
        info
    )

    markup = build_album_keyboard(
        folders,
        files,
        page
    )

    # =====================================================
    # IF IMAGE EXISTS
    # =====================================================

    if image_file:

        temp_path = None

        try:

            image_name = image_file[
                "name"
            ]

            extension = os.path.splitext(
                image_name
            )[1]

            temp_path = download_drive_file(
                image_file["id"],
                suffix=extension
            )

            # Delete old selection message
            try:
                await query.message.delete()
            except Exception:
                pass

            with open(
                temp_path,
                "rb"
            ) as photo:

                await query.message.chat.send_photo(
                    photo=photo,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )

        except Exception as e:

            # If image sending fails,
            # show text instead.
            try:
                await query.message.delete()
            except Exception:
                pass

            await query.message.chat.send_message(
                caption,
                parse_mode="HTML",
                reply_markup=markup
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

    # =====================================================
    # NO IMAGE
    # =====================================================

    else:

        try:

            await query.edit_message_text(
                caption,
                parse_mode="HTML",
                reply_markup=markup
            )

        except Exception:

            await query.message.chat.send_message(
                caption,
                parse_mode="HTML",
                reply_markup=markup
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

    page = int(parts[2])

    await show_album(
        query,
        folder_id,
        page
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

    page = int(parts[2])

    await show_album(
        query,
        folder_id,
        page
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
        # FILE INFORMATION
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

        extension = os.path.splitext(
            file_name
        )[1]

        temp_path = download_drive_file(
            file_id,
            suffix=extension
        )

        # =================================================
        # SEND FILE
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
            + str(e)
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
# PAGE NUMBER
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

    # PAGE
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

    # FOLDER
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
