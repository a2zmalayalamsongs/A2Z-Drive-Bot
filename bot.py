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
    MessageHandler,
    filters,
)

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]

ROOT_FOLDER_ID = os.environ["ROOT_FOLDER_ID"]

ADMIN_CHAT_ID = int(
    os.environ["ADMIN_CHAT_ID"]
)

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]


# =========================================================
# GOOGLE DRIVE LOGIN
# =========================================================

credentials = service_account.Credentials.from_service_account_info(
    json.loads(
        os.environ["GOOGLE_CREDENTIALS"]
    ),
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

FOLDER_MIME = (
    "application/vnd.google-apps.folder"
)

YEARS_PER_PAGE = 10

IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp"
)

INFO_FILES = (
    "album-info.txt",
    "album info.txt",
    "info.txt"
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
        fields=(
            "files(id,name,mimeType,size,"
            "modifiedTime)"
        ),
        pageSize=1000
    ).execute()

    return response.get(
        "files",
        []
    )


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

    items = get_items(
        ROOT_FOLDER_ID
    )

    years = []

    for item in items:

        if item.get(
            "mimeType"
        ) != FOLDER_MIME:

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
# 2 × 5
# =========================================================

def build_year_keyboard(page=0):

    years = get_year_folders()

    total_pages = max(
        1,
        (
            len(years)
            + YEARS_PER_PAGE
            - 1
        )
        // YEARS_PER_PAGE
    )

    page = max(
        0,
        min(
            page,
            total_pages - 1
        )
    )

    start = (
        page
        * YEARS_PER_PAGE
    )

    end = (
        start
        + YEARS_PER_PAGE
    )

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
                    f"year:"
                    f"{item['id']}:"
                    f"{page}"
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
                callback_data=(
                    f"page:{page - 1}"
                )
            )
        )

    if page < total_pages - 1:

        navigation.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data=(
                    f"page:{page + 1}"
                )
            )
        )

    if navigation:

        keyboard.append(
            navigation
        )

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

    keyboard = build_year_keyboard(
        page
    )

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

    context.user_data[
        "request_mode"
    ] = False

    await show_years(
        update.message,
        0
    )


# =========================================================
# HELP
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "📂 Browse Songs: /start\n"
        "🔍 Search Songs: /search\n"
        "🆕 Latest Songs: /latest\n"
        "📩 Request a Song: /request\n"
        "ℹ️ About: /about\n"
        "❓ Help: /help"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# =========================================================
# ABOUT
# =========================================================

async def about_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = (
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "🎶 Malayalam Songs Collection\n"
        "📂 Year-wise Albums\n"
        "🖼️ Movie Posters\n"
        "🎤 Singer Information\n"
        "🎵 Music Information\n"
        "🎬 Director Information\n"
        "👥 Artist Information\n\n"
        "📩 Use /request to request a song."
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# =========================================================
# REQUEST
# =========================================================

async def request_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data[
        "request_mode"
    ] = True

    await update.message.reply_text(
        "📩 <b>Song Request</b>\n\n"
        "🎬 Movie / Song name അയക്കൂ.\n"
        "ഞങ്ങൾ request പരിശോധിക്കാം. ❤️",
        parse_mode="HTML"
    )


# =========================================================
# HANDLE REQUEST MESSAGE
# =========================================================

async def request_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.user_data.get(
        "request_mode",
        False
    ):

        return

    context.user_data[
        "request_mode"
    ] = False

    user = update.effective_user

    request_text = (
        update.message.text
        or ""
    ).strip()

    if not request_text:

        await update.message.reply_text(
            "❌ Text ആയി request അയക്കൂ."
        )

        return

    username = (
        f"@{user.username}"
        if user.username
        else "No username"
    )

    first_name = (
        user.first_name
        or "Unknown"
    )

    # =====================================================
    # ADMIN MESSAGE
    # =====================================================

    admin_text = (
        "📩 <b>NEW SONG REQUEST</b>\n\n"

        "👤 <b>User:</b> "
        + html.escape(
            first_name
        )
        + "\n"

        "🔗 <b>Username:</b> "
        + html.escape(
            username
        )
        + "\n"

        "🆔 <b>User ID:</b> "
        + str(user.id)
        + "\n\n"

        "🎬 <b>Request:</b>\n"
        + html.escape(
            request_text
        )
        + "\n\n"

        "↩️ <b>ഈ message-ന് Reply ചെയ്താൽ "
        "reply user-ന് അയക്കും.</b>"
    )

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=admin_text,
        parse_mode="HTML"
    )

    # =====================================================
    # USER CONFIRMATION
    # =====================================================

    await update.message.reply_text(
        "✅ <b>Request അയച്ചു.</b>\n\n"
        "📩 നിങ്ങളുടെ request ലഭിച്ചു.\n"
        "Admin പരിശോധിച്ച് reply നൽകും. ❤️",
        parse_mode="HTML"
    )


# =========================================================
# ADMIN REPLY SYSTEM
# =========================================================

async def admin_reply_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if not message:

        return

    # Only Admin
    if message.chat_id != ADMIN_CHAT_ID:

        return

    # Must be a reply
    if not message.reply_to_message:

        return

    replied_message = (
        message.reply_to_message
    )

    original_text = (
        replied_message.text
        or replied_message.caption
        or ""
    )

    marker = "🆔 <b>User ID:</b>"

    if marker not in original_text:

        return

    try:

        after_marker = (
            original_text.split(
                marker,
                1
            )[1]
        )

        user_id_text = (
            after_marker
            .split("\n", 1)[0]
            .strip()
        )

        user_id = int(
            user_id_text
        )

    except Exception as e:

        print(
            "ADMIN USER ID ERROR:",
            e
        )

        return

    # =====================================================
    # ADMIN REPLY TEXT
    # =====================================================

    reply_text = (
        message.text
        or message.caption
        or ""
    )

    if reply_text:

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "📩 <b>Admin Reply</b>\n\n"
                    + html.escape(
                        reply_text
                    )
                ),
                parse_mode="HTML"
            )

            await message.reply_text(
                "✅ Reply user-ന് അയച്ചു."
            )

        except Exception as e:

            await message.reply_text(
                "❌ Reply അയക്കാൻ കഴിഞ്ഞില്ല.\n\n"
                + str(e)
            )

        return

    # =====================================================
    # PHOTO REPLY
    # =====================================================

    if message.photo:

        try:

            await context.bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=(
                    "📩 <b>Admin Reply</b>"
                    + (
                        "\n\n"
                        + html.escape(
                            message.caption
                            or ""
                        )
                        if message.caption
                        else ""
                    )
                ),
                parse_mode="HTML"
            )

            await message.reply_text(
                "✅ Photo user-ന് അയച്ചു."
            )

        except Exception as e:

            await message.reply_text(
                "❌ Photo അയക്കാൻ കഴിഞ്ഞില്ല.\n\n"
                + str(e)
            )


# =========================================================
# PAGE CALLBACK
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
# READ INFO
# =========================================================

def read_info_file(
    file_id
):

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

        if (
            not line
            or ":" not in line
        ):

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
        + html.escape(
            info["album"]
        )
    )

    if info["year"]:

        text += (
            " • "
            + html.escape(
                info["year"]
            )
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

        items = get_items(
            year_folder_id
        )

        albums = []

        songs = []

        for item in items:

            if item.get(
                "mimeType"
            ) == FOLDER_MIME:

                albums.append(item)

            else:

                songs.append(item)

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

        keyboard = []

        for album in albums:

            keyboard.append([
                InlineKeyboardButton(
                    "🎬 "
                    + album["name"],
                    callback_data=(
                        f"album:"
                        f"{album['id']}:"
                        f"{page}"
                    )
                )
            ])

        for song in songs:

            keyboard.append([
                InlineKeyboardButton(
                    "🎵 "
                    + song.get(
                        "name",
                        "Song"
                    )
                    + " ⬇️",
                    callback_data=(
                        f"file:{song['id']}"
                    )
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🔙 Back to Years",
                callback_data=(
                    f"backyear:{page}"
                )
            )
        ])

        year_name = get_folder_name(
            year_folder_id
        )

        await query.edit_message_text(
            "📅 <b>"
            + html.escape(
                year_name
            )
            + "</b>\n\n"
            "🎬 <b>Select an album:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

    except Exception as e:

        print(
            "YEAR ERROR:",
            repr(e)
        )

        await query.message.reply_text(
            "❌ Year തുറക്കാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(
                str(e)
            )
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

        for item in items:

            name = item.get(
                "name",
                ""
            ).strip()

            lower = name.lower()

            mime = item.get(
                "mimeType"
            )

            if mime == FOLDER_MIME:

                subfolders.append(item)

                continue

            if lower in INFO_FILES:

                info_file = item

                continue

            if lower.endswith(
                IMAGE_EXTENSIONS
            ):

                if image_file is None:

                    image_file = item

                else:

                    songs.append(item)

                continue

            songs.append(item)

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

        album_name = get_folder_name(
            album_folder_id
        )

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

        keyboard = []

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

        for song in songs:

            keyboard.append([
                InlineKeyboardButton(
                    "🎵 "
                    + song.get(
                        "name",
                        "Song"
                    )
                    + " ⬇️",
                    callback_data=(
                        f"file:"
                        f"{song['id']}"
                    )
                )
            ])

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
        # POSTER
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
                    and os.path.exists(
                        temp_path
                    )
                ):

                    try:
                        os.remove(
                            temp_path
                        )
                    except Exception:
                        pass

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
            "❌ Album തുറക്കാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(
                str(e)
            )
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

        try:
            await query.message.delete()
        except Exception:
            pass

        await query.message.chat.send_message(
            "🎵 <b>A2Z Malayalam Songs</b>\n\n"
            "📂 <b>Select a year:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

    except Exception as e:

        print(
            "BACK ERROR:",
            e
        )


# =========================================================
# HOME
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

    try:
        await query.message.delete()
    except Exception:
        pass

    await query.message.chat.send_message(
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "📂 <b>Select a year:</b>",
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
            fields=(
                "id,name,mimeType,size"
            )
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
            + html.escape(
                str(e)
            ),
            parse_mode="HTML"
        )

    finally:

        if (
            temp_path
            and os.path.exists(
                temp_path
            )
        ):

            try:
                os.remove(
                    temp_path
                )
            except Exception:
                pass


# =========================================================
# SEARCH
# =========================================================

def search_drive(
    folder_id,
    search_text,
    results,
    limit=30
):

    if len(results) >= limit:

        return

    items = get_items(
        folder_id
    )

    search_lower = (
        search_text.lower()
    )

    for item in items:

        name = item.get(
            "name",
            ""
        )

        mime = item.get(
            "mimeType"
        )

        if (
            search_lower
            in name.lower()
        ):

            results.append(item)

            if len(results) >= limit:

                return

        if mime == FOLDER_MIME:

            search_drive(
                item["id"],
                search_text,
                results,
                limit
            )

            if len(results) >= limit:

                return


async def search_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if context.args:

        search_text = " ".join(
            context.args
        )

        await perform_search(
            update.message,
            search_text
        )

    else:

        context.user_data[
            "search_mode"
        ] = True

        await update.message.reply_text(
            "🔍 <b>Search Songs</b>\n\n"
            "Movie / Song name type ചെയ്ത് അയക്കൂ.",
            parse_mode="HTML"
        )


async def perform_search(
    message,
    search_text
):

    results = []

    try:

        search_drive(
            ROOT_FOLDER_ID,
            search_text,
            results,
            30
        )

        if not results:

            await message.reply_text(
                "❌ Search result ഒന്നും കണ്ടെത്തിയില്ല."
            )

            return

        keyboard = []

        for item in results:

            if item.get(
                "mimeType"
            ) == FOLDER_MIME:

                keyboard.append([
                    InlineKeyboardButton(
                        "📁 "
                        + item["name"],
                        callback_data=(
                            f"album:"
                            f"{item['id']}:0"
                        )
                    )
                ])

            else:

                keyboard.append([
                    InlineKeyboardButton(
                        "🎵 "
                        + item["name"]
                        + " ⬇️",
                        callback_data=(
                            f"file:"
                            f"{item['id']}"
                        )
                    )
                ])

        await message.reply_text(
            "🔍 <b>Search Results</b>\n\n"
            "Found: "
            + str(len(results)),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

    except Exception as e:

        await message.reply_text(
            "❌ Search failed.\n\n"
            + html.escape(
                str(e)
            )
        )


# =========================================================
# LATEST
# =========================================================

def get_latest_files(
    folder_id,
    results,
    limit=20
):

    items = get_items(
        folder_id
    )

    for item in items:

        if item.get(
            "mimeType"
        ) == FOLDER_MIME:

            get_latest_files(
                item["id"],
                results,
                limit
            )

        else:

            name = item.get(
                "name",
                ""
            ).lower()

            if name.endswith(
                IMAGE_EXTENSIONS
            ):

                continue

            if name in INFO_FILES:

                continue

            results.append(item)

    results.sort(
        key=lambda x:
        x.get(
            "modifiedTime",
            ""
        ),
        reverse=True
    )

    del results[limit:]


async def latest_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        results = []

        get_latest_files(
            ROOT_FOLDER_ID,
            results,
            20
        )

        if not results:

            await update.message.reply_text(
                "❌ Latest songs കണ്ടെത്തിയില്ല."
            )

            return

        keyboard = []

        for item in results:

            keyboard.append([
                InlineKeyboardButton(
                    "🆕 "
                    + item.get(
                        "name",
                        "Song"
                    )
                    + " ⬇️",
                    callback_data=(
                        f"file:"
                        f"{item['id']}"
                    )
                )
            ])

        await update.message.reply_text(
            "🆕 <b>Latest Songs</b>\n\n"
            "Recently added / modified songs:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

    except Exception as e:

        await update.message.reply_text(
            "❌ Latest songs load ചെയ്യാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(
                str(e)
            )
        )


# =========================================================
# SEARCH TEXT HANDLER
# =========================================================

async def search_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.user_data.get(
        "search_mode",
        False
    ):

        return

    context.user_data[
        "search_mode"
    ] = False

    search_text = (
        update.message.text
        or ""
    ).strip()

    if not search_text:

        await update.message.reply_text(
            "❌ Search text അയക്കൂ."
        )

        return

    await perform_search(
        update.message,
        search_text
    )


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

    # =====================================================
    # COMMANDS
    # =====================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        CommandHandler(
            "about",
            about_command
        )
    )

    app.add_handler(
        CommandHandler(
            "request",
            request_command
        )
    )

    app.add_handler(
        CommandHandler(
            "search",
            search_command
        )
    )

    app.add_handler(
        CommandHandler(
            "latest",
            latest_command
        )
    )

    # =====================================================
    # ADMIN REPLY
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.REPLY
            & ~filters.COMMAND,
            admin_reply_handler
        )
    )

    # =====================================================
    # REQUEST MESSAGE
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            request_message
        )
    )

    # =====================================================
    # SEARCH MESSAGE
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            search_message_handler
        )
    )

    # =====================================================
    # PAGE
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
    # ALBUM
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            album_callback,
            pattern=r"^album:"
        )
    )

    # =====================================================
    # BACK
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            backyear_callback,
            pattern=r"^backyear:"
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
    # RUN
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
