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

        result = drive.files().get(
            fileId=folder_id,
            fields="name"
        ).execute()

        return result.get(
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

        if not name.isdigit():
            continue

        years.append({
            "id": item["id"],
            "name": name,
            "year": int(name)
        })

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

    page = max(
        0,
        min(
            page,
            total_pages - 1
        )
    )

    start = page * YEARS_PER_PAGE

    end = start + YEARS_PER_PAGE

    page_years = years[
        start:end
    ]

    keyboard = []

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

        if len(row) == 2:

            keyboard.append(row)

            row = []

    if row:
        keyboard.append(row)

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
    page=0
):

    keyboard = build_year_keyboard(page)

    await message.reply_text(
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "📂 <b>Select a year:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
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
        0
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

    try:

        page = int(
            query.data.split(":")[1]
        )

        keyboard = build_year_keyboard(
            page
        )

        await query.edit_message_text(
            "🎵 <b>A2Z Malayalam Songs</b>\n\n"
            "📂 <b>Select a year:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

    except Exception as e:

        print(
            "PAGE ERROR:",
            e
        )

        await query.message.reply_text(
            "❌ Page തുറക്കാൻ കഴിഞ്ഞില്ല."
        )


# =========================================================
# DOWNLOAD FILE
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
# READ ALBUM INFO
# =========================================================

def read_info_file(file_id):

    temp_path = None

    try:

        temp_path = download_drive_file(
            file_id,
            ".txt"
        )

        with open(
            temp_path,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as file:

            return file.read()

    except Exception as e:

        print(
            "INFO FILE ERROR:",
            e
        )

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
# ALBUM CAPTION
# =========================================================

def create_album_caption(info):

    text = (
        "🎬 <b>Album</b> : "
        + html.escape(info["album"])
    )

    if info["year"]:

        text += (
            " • "
            + html.escape(info["year"])
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
# ALBUM KEYBOARD
# =========================================================

def build_album_keyboard(
    albums,
    songs,
    back_page
):

    keyboard = []

    # =====================================================
    # ALBUM / SUB FOLDERS
    # =====================================================

    for album in albums:

        keyboard.append([
            InlineKeyboardButton(
                "🎬 " + album["name"],
                callback_data=(
                    f"album:"
                    f"{album['id']}:"
                    f"{back_page}"
                )
            )
        ])

    # =====================================================
    # SONGS
    # =====================================================

    for song in songs:

        keyboard.append([
            InlineKeyboardButton(
                "🎵 "
                + song.get(
                    "name",
                    "Song"
                )
                + "  ⬇️",
                callback_data=(
                    f"file:{song['id']}"
                )
            )
        ])

    # =====================================================
    # BACK
    # =====================================================

    keyboard.append([
        InlineKeyboardButton(
            "🔙 Back to Years",
            callback_data=(
                f"backyear:{back_page}"
            )
        )
    ])

    return InlineKeyboardMarkup(
        keyboard
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

    try:

        parts = query.data.split(":")

        year_folder_id = parts[1]

        page = int(parts[2])

        # =================================================
        # GET CONTENTS OF YEAR
        # =================================================

        items = get_items(
            year_folder_id
        )

        albums = []

        songs = []

        # =================================================
        # SEPARATE ALBUMS / FILES
        # =================================================

        for item in items:

            if item.get(
                "mimeType"
            ) == FOLDER_MIME:

                albums.append(item)

            else:

                songs.append(item)

        # =================================================
        # SORT
        # =================================================

        albums.sort(
            key=lambda x:
            x.get(
                "name",
                ""
            ).lower()
        )

        songs.sort(
            key=lambda x:
            x.get(
                "name",
                ""
            ).lower()
        )

        # =================================================
        # KEYBOARD
        # =================================================

        keyboard = build_album_keyboard(
            albums,
            songs,
            page
        )

        # =================================================
        # TEXT
        # =================================================

        year_name = get_folder_name(
            year_folder_id
        )

        text = (
            "📅 <b>"
            + html.escape(year_name)
            + "</b>\n\n"
            "🎬 <b>Select an album:</b>"
        )

        # =================================================
        # EDIT MESSAGE
        # =================================================

        if query.message.photo:

            await query.message.delete()

            await query.message.chat.send_message(
                text,
                parse_mode="HTML",
                reply_markup=keyboard
            )

        else:

            await query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=keyboard
            )

    except Exception as e:

        print(
            "YEAR ERROR:",
            repr(e)
        )

        await query.message.reply_text(
            "❌ <b>Year തുറക്കാൻ കഴിഞ്ഞില്ല.</b>\n\n"
            "Error: "
            + html.escape(str(e)),
            parse_mode="HTML"
        )


# =========================================================
# OPEN ALBUM
# =========================================================

async def album_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        parts = query.data.split(":")

        album_folder_id = parts[1]

        page = int(parts[2])

        items = get_items(
            album_folder_id
        )

        songs = []

        subfolders = []

        image_file = None

        info_file = None

        # =================================================
        # FIND EVERYTHING
        # =================================================

        for item in items:

            name = item.get(
                "name",
                ""
            ).strip()

            lower = name.lower()

            mime = item.get(
                "mimeType"
            )

            # ---------------------------------------------
            # SUB FOLDER
            # ---------------------------------------------

            if mime == FOLDER_MIME:

                subfolders.append(item)

                continue

            # ---------------------------------------------
            # ALBUM INFO
            # ---------------------------------------------

            if lower in (
                "album-info.txt",
                "album info.txt",
                "info.txt"
            ):

                info_file = item

                continue

            # ---------------------------------------------
            # POSTER
            # ---------------------------------------------

            if lower.endswith(
                IMAGE_EXTENSIONS
            ):

                if image_file is None:

                    image_file = item

                else:

                    songs.append(item)

                continue

            # ---------------------------------------------
            # SONG
            # ---------------------------------------------

            songs.append(item)

        # =================================================
        # SORT
        # =================================================

        subfolders.sort(
            key=lambda x:
            x.get(
                "name",
                ""
            ).lower()
        )

        songs.sort(
            key=lambda x:
            x.get(
                "name",
                ""
            ).lower()
        )

        # =================================================
        # ALBUM NAME
        # =================================================

        album_name = get_folder_name(
            album_folder_id
        )

        # =================================================
        # READ INFO
        # =================================================

        info_text = ""

        if info_file:

            info_text = read_info_file(
                info_file["id"]
            )

        info = parse_info(
            info_text,
            album_name
        )

        caption = create_album_caption(
            info
        )

        # =================================================
        # KEYBOARD
        # =================================================

        keyboard = []

        # Subfolders
        for folder in subfolders:

            keyboard.append([
                InlineKeyboardButton(
                    "📁 "
                    + folder["name"],
                    callback_data=(
                        f"album:"
                        f"{folder['id']}:"
                        f"{page}"
                    )
                )
            ])

        # Songs
        for song in songs:

            keyboard.append([
                InlineKeyboardButton(
                    "🎵 "
                    + song.get(
                        "name",
                        "Song"
                    )
                    + "  ⬇️",
                    callback_data=(
                        f"file:{song['id']}"
                    )
                )
            ])

        # Back + Home
        keyboard.append([
            InlineKeyboardButton(
                "🔙 Back",
                callback_data=(
                    f"backyear:{page}"
                )
            ),
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="home"
            )
        ])

        markup = InlineKeyboardMarkup(
            keyboard
        )

        # =================================================
        # SEND POSTER
        # =================================================

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
                    extension
                )

                # Remove old message
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

            finally:

                if (
                    temp_path
                    and os.path.exists(temp_path)
                ):

                    try:
                        os.remove(
                            temp_path
                        )
                    except Exception:
                        pass

        # =================================================
        # NO POSTER
        # =================================================

        else:

            await query.edit_message_text(
                caption,
                parse_mode="HTML",
                reply_markup=markup
            )

    except Exception as e:

        print(
            "ALBUM ERROR:",
            repr(e)
        )

        await query.message.reply_text(
            "❌ <b>Album തുറക്കാൻ കഴിഞ്ഞില്ല.</b>\n\n"
            + html.escape(str(e)),
            parse_mode="HTML"
        )


# =========================================================
# BACK TO YEARS
# =========================================================

async def backyear_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        page = int(
            query.data.split(":")[1]
        )

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

    except Exception as e:

        print(
            "BACK YEAR ERROR:",
            e
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

        file_info = drive.files().get(
            fileId=file_id,
            fields="id,name,mimeType,size"
        ).execute()

        file_name = file_info.get(
            "name",
            "download"
        )

        extension = os.path.splitext(
            file_name
        )[1]

        temp_path = download_drive_file(
            file_id,
            extension
        )

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

        if (
            temp_path
            and os.path.exists(temp_path)
        ):

            try:
                os.remove(temp_path)
            except Exception:
                pass


# =========================================================
# NOTHING
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

    # ALBUM
    app.add_handler(
        CallbackQueryHandler(
            album_callback,
            pattern=r"^album:"
        )
    )

    # BACK TO YEARS
    app.add_handler(
        CallbackQueryHandler(
            backyear_callback,
            pattern=r"^backyear:"
        )
    )

    # HOME
    app.add_handler(
        CallbackQueryHandler(
            home_callback,
            pattern=r"^home$"
        )
    )

    # FILE
    app.add_handler(
        CallbackQueryHandler(
            file_callback,
            pattern=r"^file:"
        )
    )

    # NOTHING
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
