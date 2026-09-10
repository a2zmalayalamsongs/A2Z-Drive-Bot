import os
import tempfile
import json
import html

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
# GET FOLDER NAME
# =========================================================

def get_folder_name(folder_id):

    try:

        data = drive.files().get(
            fileId=folder_id,
            fields="name"
        ).execute()

        return data.get(
            "name",
            "Album"
        )

    except Exception:

        return "Album"


# =========================================================
# GET YEAR FOLDERS
# =========================================================

def get_year_folders():

    items = get_items(ROOT_FOLDER_ID)

    years = []

    for item in items:

        if item.get("mimeType") != FOLDER_MIME:
            continue

        name = item.get(
            "name",
            ""
        ).strip()

        # Only numeric folders
        if not name.isdigit():
            continue

        years.append({
            "id": item["id"],
            "name": name,
            "year": int(name)
        })

    # Newest → oldest
    years.sort(
        key=lambda x: x["year"],
        reverse=True
    )

    return years


# =========================================================
# YEAR KEYBOARD
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

    start = page * YEARS_PER_PAGE

    end = start + YEARS_PER_PAGE

    page_years = years[start:end]

    keyboard = []

    row = []

    # =====================================================
    # YEARS
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

        if len(row) == 2:

            keyboard.append(row)

            row = []

    if row:
        keyboard.append(row)

    # =====================================================
    # NAVIGATION
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
    # PAGE
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
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "📂 <b>Select a year:</b>"
    )

    markup = InlineKeyboardMarkup(keyboard)

    if edit:

        await message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=markup
        )

    else:

        await message.reply_text(
            text,
            parse_mode="HTML",
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
        page=0
    )


# =========================================================
# YEAR PAGE
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

    text = (
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "📂 <b>Select a year:</b>"
    )

    # If current message is photo,
    # delete and send year list.
    if query.message.photo:

        await query.message.delete()

        await query.message.chat.send_message(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

    else:

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )


# =========================================================
# DOWNLOAD DRIVE FILE
# =========================================================

def download_drive_file(
    file_id,
    suffix=""
):

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
# READ ALBUM-INFO.TXT
# =========================================================

def read_info_file(file_id):

    temp_path = None

    try:

        temp_path = download_drive_file(
            file_id,
            suffix=".txt"
        )

        with open(
            temp_path,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as file:

            return file.read()

    except Exception:

        return ""

    finally:

        if temp_path and os.path.exists(temp_path):

            try:
                os.remove(temp_path)
            except Exception:
                pass


# =========================================================
# PARSE INFO
# =========================================================

def parse_info(
    text,
    default_album
):

    data = {

        "album": default_album,

        "year": "",

        "singer": "",

        "music": "",

        "director": "",

        "artists": ""
    }

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        if ":" not in line:
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
            "year",
            "release year"
        ):

            data["year"] = value

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
# CREATE PROFESSIONAL ALBUM CAPTION
# =========================================================

def create_album_caption(info):

    album = html.escape(
        info["album"]
    )

    text = (
        "🎬 <b>Album</b> : "
        + album
    )

    if info["year"]:

        text += (
            " ("
            + html.escape(info["year"])
            + ")"
        )

    if info["singer"]:

        text += (
            "\n🎤 <b>Singer</b> : "
            + html.escape(
                info["singer"]
            )
        )

    if info["music"]:

        text += (
            "\n🎵 <b>Music By</b> : "
            + html.escape(
                info["music"]
            )
        )

    if info["director"]:

        text += (
            "\n🎬 <b>Director</b> : "
            + html.escape(
                info["director"]
            )
        )

    if info["artists"]:

        text += (
            "\n👥 <b>Artists</b> : "
            + html.escape(
                info["artists"]
            )
        )

    return text


# =========================================================
# BUILD ALBUM KEYBOARD
# =========================================================

def build_album_keyboard(
    folders,
    files,
    parent_id,
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
                    f"folder:"
                    f"{item['id']}:"
                    f"{parent_id}:"
                    f"{page}"
                )
            )
        ])

    # =====================================================
    # SONG FILES
    # =====================================================

    for index, item in enumerate(
        files,
        start=1
    ):

        name = item.get(
            "name",
            "Song"
        )

        button_text = (
            f"🎵 {name}  ⬇️"
        )

        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=(
                    f"file:{item['id']}"
                )
            )
        ])

    # =====================================================
    # BACK
    # =====================================================

    keyboard.append([
        InlineKeyboardButton(
            "🔙 Back",
            callback_data=(
                f"back:{parent_id}:{page}"
            )
        ),

        InlineKeyboardButton(
            "🏠 Main Menu",
            callback_data="home"
        )
    ])

    return InlineKeyboardMarkup(
        keyboard
    )


# =========================================================
# SHOW ALBUM
# =========================================================

async def show_album(
    query,
    folder_id,
    parent_id,
    page
):

    items = get_items(folder_id)

    folders = []

    files = []

    image_file = None

    info_file = None

    # =====================================================
    # FIND FILES
    # =====================================================

    for item in items:

        name = item.get(
            "name",
            ""
        ).strip()

        lower_name = name.lower()

        if item.get(
            "mimeType"
        ) == FOLDER_MIME:

            folders.append(item)

            continue

        # =================================================
        # ALBUM INFO
        # =================================================

        if lower_name in (
            "info.txt",
            "album-info.txt",
            "album info.txt"
        ):

            info_file = item

            continue

        # =================================================
        # POSTER
        # =================================================

        if lower_name.endswith(
            IMAGE_EXTENSIONS
        ):

            if image_file is None:

                image_file = item

            else:

                files.append(item)

            continue

        # =================================================
        # SONG / OTHER FILE
        # =================================================

        files.append(item)

    # =====================================================
    # SORT FOLDERS
    # =====================================================

    folders.sort(
        key=lambda x:
        x.get(
            "name",
            ""
        ).lower()
    )

    # =====================================================
    # SORT FILES
    # =====================================================

    files.sort(
        key=lambda x:
        x.get(
            "name",
            ""
        ).lower()
    )

    # =====================================================
    # FOLDER NAME
    # =====================================================

    folder_name = get_folder_name(
        folder_id
    )

    # =====================================================
    # INFO
    # =====================================================

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

    # =====================================================
    # KEYBOARD
    # =====================================================

    markup = build_album_keyboard(
        folders,
        files,
        parent_id,
        page
    )

    # =====================================================
    # IMAGE
    # =====================================================

    if image_file:

        temp_path = None

        try:

            image_name = image_file.get(
                "name",
                "poster.jpg"
            )

            extension = os.path.splitext(
                image_name
            )[1]

            temp_path = download_drive_file(
                image_file["id"],
                suffix=extension
            )

            # Delete previous message
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

            if temp_path and os.path.exists(
                temp_path
            ):

                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    # =====================================================
    # WITHOUT IMAGE
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

    # Parent of year = ROOT
    parent_id = ROOT_FOLDER_ID

    await show_album(
        query,
        folder_id,
        parent_id,
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

    parent_id = parts[2]

    page = int(parts[3])

    await show_album(
        query,
        folder_id,
        parent_id,
        page
    )


# =========================================================
# BACK BUTTON
# =========================================================

async def back_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    parts = query.data.split(":")

    parent_id = parts[1]

    page = int(parts[2])

    # If parent is ROOT,
    # show year list.
    if parent_id == ROOT_FOLDER_ID:

        keyboard = build_year_keyboard(
            page
        )

        text = (
            "🎵 <b>A2Z Malayalam Songs</b>\n\n"
            "📂 <b>Select a year:</b>"
        )

        try:
            await query.message.delete()
        except Exception:
            pass

        await query.message.chat.send_message(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

        return

    # Otherwise open parent folder
    await show_album(
        query,
        parent_id,
        ROOT_FOLDER_ID,
        page
    )


# =========================================================
# MAIN MENU
# =========================================================

async def home_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    keyboard = build_year_keyboard(
        0
    )

    text = (
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "📂 <b>Select a year:</b>"
    )

    try:

        await query.message.delete()

    except Exception:
        pass

    await query.message.chat.send_message(
        text,
        parse_mode="HTML",
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
        # FILE INFO
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
        # SEND
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
            "❌ <b>Download failed</b>\n\n"
            + html.escape(str(e)),
            parse_mode="HTML"
        )

    finally:

        if temp_path and os.path.exists(
            temp_path
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

    # =====================================================
    # START
    # =====================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # =====================================================
    # YEAR PAGINATION
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            page_callback,
            pattern=r"^page:\d+$"
        )
    )

    # =====================================================
    # YEAR
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            year_callback,
            pattern=r"^year:"
        )
    )

    # =====================================================
    # SUB FOLDER
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            folder_callback,
            pattern=r"^folder:"
        )
    )

    # =====================================================
    # BACK
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            back_callback,
            pattern=r"^back:"
        )
    )

    # =====================================================
    # HOME
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            home_callback,
            pattern=r"^home$"
        )
    )

    # =====================================================
    # FILE
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            file_callback,
            pattern=r"^file:"
        )
    )

    # =====================================================
    # NOTHING
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            nothing_callback,
            pattern=r"^nothing$"
        )
    )

    # =====================================================
    # START BOT
    # =====================================================

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
