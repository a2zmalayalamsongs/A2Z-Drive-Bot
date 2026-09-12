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

ALBUMS_PER_PAGE = 10

IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp"
)

INFO_FILES = (
    "info.txt",
    "album-info.txt",
    "album info.txt"
)

SONG_EXTENSIONS = (
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".flac",
    ".ogg",
    ".opus"
)


# =========================================================
# DRIVE ITEMS
# =========================================================

def get_items(folder_id):

    query = (
        f"'{folder_id}' in parents "
        "and trashed = false"
    )

    response = drive.files().list(
        q=query,
        fields=(
            "files("
            "id,"
            "name,"
            "mimeType,"
            "size,"
            "modifiedTime,"
            "parents"
            ")"
        ),
        pageSize=1000
    ).execute()

    return response.get(
        "files",
        []
    )


# =========================================================
# FOLDER NAME
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
# GET PARENT FOLDER
# =========================================================

def get_parent_folder(folder_id):

    try:

        result = drive.files().get(
            fileId=folder_id,
            fields="parents"
        ).execute()

        parents = result.get(
            "parents",
            []
        )

        if parents:

            return parents[0]

    except Exception as e:

        print(
            "PARENT ERROR:",
            repr(e)
        )

    return None


# =========================================================
# YEARS
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

    page_years = years[
        start:
        start + YEARS_PER_PAGE
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
        "search_mode"
    ] = False

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

        "📂 <b>Browse Songs</b>\n"
        "/start\n\n"

        "🔍 <b>Search Songs</b>\n"
        "/search\n\n"

        "🆕 <b>Latest Songs</b>\n"
        "/latest\n\n"

        "📩 <b>Request a Song</b>\n"
        "/request\n\n"

        "ℹ️ <b>About</b>\n"
        "/about\n\n"

        "❓ <b>Help</b>\n"
        "/help"
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
        "👥 Artist Information\n"
        "⬇️ MP3 Download\n\n"
        "📩 Song request ചെയ്യാൻ "
        "/request ഉപയോഗിക്കുക."
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# =========================================================
# SEARCH COMMAND
# =========================================================

async def search_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data[
        "search_mode"
    ] = True

    context.user_data[
        "request_mode"
    ] = False

    if context.args:

        search_text = " ".join(
            context.args
        )

        context.user_data[
            "search_mode"
        ] = False

        await perform_search(
            update.message,
            search_text
        )

        return

    await update.message.reply_text(
        "🔍 <b>Search Songs</b>\n\n"
        "🎬 Movie / Song name type ചെയ്ത് അയക്കൂ.\n\n"
        "ഉദാഹരണം:\n"
        "<code>Varnajaalam</code>",
        parse_mode="HTML"
    )


# =========================================================
# SEARCH DRIVE
# =========================================================

def search_drive(
    folder_id,
    search_text,
    results,
    visited,
    limit=30
):

    if len(results) >= limit:

        return

    if folder_id in visited:

        return

    visited.add(
        folder_id
    )

    try:

        items = get_items(
            folder_id
        )

        search_lower = (
            search_text.lower()
        )

        for item in items:

            if len(results) >= limit:

                return

            name = item.get(
                "name",
                ""
            )

            lower_name = (
                name.lower()
            )

            mime = item.get(
                "mimeType"
            )

            if mime == FOLDER_MIME:

                if search_lower in lower_name:

                    results.append(
                        item
                    )

                    if len(results) >= limit:

                        return

                search_drive(
                    item["id"],
                    search_text,
                    results,
                    visited,
                    limit
                )

                continue

            if lower_name in INFO_FILES:

                continue

            if lower_name.endswith(
                IMAGE_EXTENSIONS
            ):

                continue

            if search_lower in lower_name:

                results.append(
                    item
                )

    except Exception as e:

        print(
            "SEARCH DRIVE ERROR:",
            repr(e)
        )


# =========================================================
# SEARCH
# =========================================================

async def perform_search(
    message,
    search_text
):

    results = []

    visited = set()

    try:

        status_message = (
            await message.reply_text(
                "🔍 <b>Searching...</b>\n\n"
                "Please wait ⏳",
                parse_mode="HTML"
            )
        )

        search_drive(
            ROOT_FOLDER_ID,
            search_text,
            results,
            visited,
            30
        )

        try:

            await status_message.delete()

        except Exception:

            pass

        if not results:

            await message.reply_text(
                "❌ <b>No results found</b>\n\n"
                "🔍 Search: <b>"
                + html.escape(
                    search_text
                )
                + "</b>",
                parse_mode="HTML"
            )

            return

        keyboard = []

        for item in results:

            name = item.get(
                "name",
                "Song"
            )

            mime = item.get(
                "mimeType"
            )

            if mime == FOLDER_MIME:

                keyboard.append([
                    InlineKeyboardButton(
                        "🎬 " + name,
                        callback_data=(
                            f"album:{item['id']}"
                        )
                    )
                ])

            else:

                keyboard.append([
                    InlineKeyboardButton(
                        "🎵 "
                        + name
                        + " ⬇️",
                        callback_data=(
                            f"file:{item['id']}"
                        )
                    )
                ])

        await message.reply_text(
            "🔍 <b>Search Results</b>\n\n"
            "Search: <b>"
            + html.escape(
                search_text
            )
            + "</b>\n"
            "Found: <b>"
            + str(len(results))
            + "</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            )
        )

    except Exception as e:

        print(
            "SEARCH ERROR:",
            repr(e)
        )

        await message.reply_text(
            "❌ <b>Search failed</b>\n\n"
            + html.escape(
                str(e)
            ),
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

    context.user_data[
        "search_mode"
    ] = False

    await update.message.reply_text(
        "📩 <b>Song Request</b>\n\n"
        "🎬 Movie / Song name type ചെയ്ത് അയക്കൂ.\n\n"
        "ഉദാഹരണം:\n"
        "<code>Manjummel Boys movie songs വേണം</code>",
        parse_mode="HTML"
    )


# =========================================================
# SEND REQUEST TO ADMIN
# =========================================================

async def send_request_to_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    request_text = (
        update.message.text
        or ""
    ).strip()

    if not request_text:

        await update.message.reply_text(
            "❌ Request text അയക്കൂ."
        )

        return

    user = update.effective_user

    first_name = (
        user.first_name
        or "Unknown"
    )

    username = (
        "@"
        + user.username
        if user.username
        else "No username"
    )

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

        "↩️ <i>ഈ message-ന് Reply "
        "ചെയ്താൽ user-ന് reply പോകും.</i>"
    )

    try:

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_text,
            parse_mode="HTML"
        )

        await update.message.reply_text(
            "✅ <b>Request അയച്ചു.</b>\n\n"
            "📩 Admin-ന് നിങ്ങളുടെ request ലഭിച്ചു.\n"
            "Reply ലഭിക്കുമ്പോൾ അറിയിക്കും. ❤️",
            parse_mode="HTML"
        )

    except Exception as e:

        print(
            "REQUEST ERROR:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ Request അയക്കാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(
                str(e)
            ),
            parse_mode="HTML"
        )


# =========================================================
# TEXT HANDLER
# =========================================================

async def text_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if context.user_data.get(
        "search_mode",
        False
    ):

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

        return

    if context.user_data.get(
        "request_mode",
        False
    ):

        context.user_data[
            "request_mode"
        ] = False

        await send_request_to_admin(
            update,
            context
        )


# =========================================================
# ADMIN REPLY
# =========================================================

async def admin_reply_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.message

    if not message:

        return

    if message.chat_id != ADMIN_CHAT_ID:

        return

    if not message.reply_to_message:

        return

    original = (
        message.reply_to_message.text
        or message.reply_to_message.caption
        or ""
    )

    marker = "User ID:"

    if marker not in original:

        await message.reply_text(
            "❌ User ID കണ്ടെത്താൻ കഴിഞ്ഞില്ല."
        )

        return

    try:

        after = original.split(
            marker,
            1
        )[1]

        user_id_text = (
            after
            .split(
                "\n",
                1
            )[0]
            .strip()
        )

        user_id = int(
            user_id_text
        )

    except Exception:

        await message.reply_text(
            "❌ User ID ശരിയായി കണ്ടെത്താൻ കഴിഞ്ഞില്ല."
        )

        return

    if message.text:

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "📩 <b>Admin Reply</b>\n\n"
                    + html.escape(
                        message.text
                    )
                ),
                parse_mode="HTML"
            )

            await message.reply_text(
                "✅ Reply user-ന് അയച്ചു."
            )

        except Exception as e:

            await message.reply_text(
                "❌ User-ന് reply അയക്കാൻ കഴിഞ്ഞില്ല.\n\n"
                + html.escape(
                    str(e)
                )
            )

        return

    if message.photo:

        try:

            await context.bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption="📩 Admin Reply"
            )

            await message.reply_text(
                "✅ Photo user-ന് അയച്ചു."
            )

        except Exception as e:

            await message.reply_text(
                "❌ Photo അയക്കാൻ കഴിഞ്ഞില്ല."
            )

        return

    if message.document:

        try:

            await context.bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption="📩 Admin Reply"
            )

            await message.reply_text(
                "✅ File user-ന് അയച്ചു."
            )

        except Exception as e:

            await message.reply_text(
                "❌ File അയക്കാൻ കഴിഞ്ഞില്ല."
            )

        return


# =========================================================
# YEAR PAGINATION
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
            repr(e)
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
# READ INFO FILE
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

    except Exception as e:

        print(
            "INFO READ ERROR:",
            repr(e)
        )

        return ""

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
# PARSE INFO
# =========================================================

def parse_info(
    text,
    default_album
):

    data = {

        "album": default_album,

        "year": "",

        "director": "",

        "singer": "",

        "music": "",

        "artists": "",

        "label": "",

        "upload_by": ""
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
            "director",
            "directed by"
        ):

            data["director"] = value

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
            "artist",
            "artists",
            "cast"
        ):

            data["artists"] = value

        elif key in (
            "label",
            "music label"
        ):

            data["label"] = value

        elif key in (
            "upload by",
            "uploaded by",
            "uploader"
        ):

            data["upload_by"] = value

    return data


# =========================================================
# GET ALBUM DATA
# =========================================================

def get_album_data(
    folder_id
):

    items = get_items(
        folder_id
    )

    album_name = get_folder_name(
        folder_id
    )

    info_file = None

    image_file = None

    songs = []

    # IMPORTANT:
    # SUB-FOLDERS ARE IGNORED
    # ONLY DIRECT FILES ARE USED

    for item in items:

        name = item.get(
            "name",
            ""
        ).strip()

        lower = name.lower()

        mime = item.get(
            "mimeType"
        )

        # Ignore folders
        if mime == FOLDER_MIME:

            continue

        # Info
        if lower in INFO_FILES:

            info_file = item

            continue

        # Poster
        if lower.endswith(
            IMAGE_EXTENSIONS
        ):

            if image_file is None:

                image_file = item

            continue

        # Only song files
        if lower.endswith(
            SONG_EXTENSIONS
        ):

            songs.append(
                item
            )

    songs.sort(
        key=lambda x:
        x.get(
            "name",
            ""
        ).lower()
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

    return {
        "folder_id": folder_id,
        "album_name": album_name,
        "info": info,
        "poster": image_file,
        "songs": songs
    }


# =========================================================
# ALBUM CARD CAPTION
# =========================================================

def create_album_card_caption(
    info,
    total_tracks
):

    album = html.escape(
        info["album"]
    )

    year = html.escape(
        info["year"]
        or "N/A"
    )

    label = html.escape(
        info["label"]
        or "A2Z Malayalam Songs"
    )

    return (
        "💿 <b>"
        + album
        + "</b>\n\n"

        "📅 <b>Year</b> : "
        + year
        + "\n"

        "🎶 <b>Tracks</b> : "
        + str(total_tracks)
        + "\n"

        "🏷️ <b>Label</b> : "
        + label
    )


# =========================================================
# ALBUM FULL CAPTION
# =========================================================

def create_album_caption(
    info,
    total_tracks
):

    text = (
        "🎬 <b>Album</b> : "
        + html.escape(
            info["album"]
        )
    )

    if info["year"]:

        text += (
            "\n📅 <b>Year</b> : "
            + html.escape(
                info["year"]
            )
        )

    if info["director"]:

        text += (
            "\n🎬 <b>Director</b> : "
            + html.escape(
                info["director"]
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

    if info["artists"]:

        text += (
            "\n👥 <b>Artists</b> : "
            + html.escape(
                info["artists"]
            )
        )

    text += (
        "\n🎶 <b>Total Tracks</b> : "
        + str(total_tracks)
    )

    upload_by = (
        info["upload_by"]
        or "A2Z Malayalam Songs"
    )

    text += (
        "\n📤 <b>Upload By</b> : "
        + html.escape(
            upload_by
        )
    )

    return text


# =========================================================
# SEND ALBUM CARD
# =========================================================

async def send_album_card(
    chat,
    album
):

    info = album["info"]

    songs = album["songs"]

    caption = create_album_card_caption(
        info,
        len(songs)
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💿 View Album ➡️",
                callback_data=(
                    f"album:{album['folder_id']}"
                )
            )
        ]
    ])

    poster = album["poster"]

    if poster:

        temp_path = None

        try:

            image_name = poster.get(
                "name",
                "poster.jpg"
            )

            extension = os.path.splitext(
                image_name
            )[1]

            temp_path = download_drive_file(
                poster["id"],
                extension
            )

            with open(
                temp_path,
                "rb"
            ) as photo:

                await chat.send_photo(
                    photo=photo,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=keyboard
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

        await chat.send_message(
            caption,
            parse_mode="HTML",
            reply_markup=keyboard
        )


# =========================================================
# ALBUM LIST NAVIGATION
# =========================================================

def build_album_navigation(
    page,
    total_pages,
    year_id
):

    keyboard = []

    navigation = []

    if page > 0:

        navigation.append(
            InlineKeyboardButton(
                "⬅️",
                callback_data=(
                    f"albums:{year_id}:{page - 1}"
                )
            )
        )

    navigation.append(
        InlineKeyboardButton(
            f"{page + 1} / {total_pages}",
            callback_data="nothing"
        )
    )

    if page < total_pages - 1:

        navigation.append(
            InlineKeyboardButton(
                "➡️",
                callback_data=(
                    f"albums:{year_id}:{page + 1}"
                )
            )
        )

    keyboard.append(
        navigation
    )

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Back to Years",
            callback_data=(
                f"backyear:{year_id}"
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
# SHOW ALBUM LIST
# =========================================================

async def show_album_list(
    chat,
    year_id,
    page=0,
    old_message=None
):

    try:

        items = get_items(
            year_id
        )

        # ONLY DIRECT FOLDERS = ALBUMS
        albums = []

        for item in items:

            if item.get(
                "mimeType"
            ) != FOLDER_MIME:

                continue

            albums.append(
                item
            )

        albums.sort(
            key=lambda x:
            x.get(
                "name",
                ""
            ).lower()
        )

        total_pages = max(
            1,
            (
                len(albums)
                + ALBUMS_PER_PAGE
                - 1
            )
            // ALBUMS_PER_PAGE
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
            * ALBUMS_PER_PAGE
        )

        page_albums = albums[
            start:
            start + ALBUMS_PER_PAGE
        ]

        # Delete old year message
        if old_message:

            try:

                await old_message.delete()

            except Exception:

                pass

        year_name = get_folder_name(
            year_id
        )

        await chat.send_message(
            "💿 <b>Malayalam Albums</b>\n\n"
            "📅 <b>"
            + html.escape(
                year_name
            )
            + "</b>\n"
            "🎬 Select an album:",
            parse_mode="HTML"
        )

        # Send album cards
        for album_folder in page_albums:

            album = get_album_data(
                album_folder["id"]
            )

            await send_album_card(
                chat,
                album
            )

        # Navigation message
        markup = build_album_navigation(
            page,
            total_pages,
            year_id
        )

        await chat.send_message(
            "📂 <b>Album Navigation</b>",
            parse_mode="HTML",
            reply_markup=markup
        )

    except Exception as e:

        print(
            "ALBUM LIST ERROR:",
            repr(e)
        )

        await chat.send_message(
            "❌ <b>Album list തുറക്കാൻ കഴിഞ്ഞില്ല.</b>\n\n"
            + html.escape(
                str(e)
            ),
            parse_mode="HTML"
        )


# =========================================================
# YEAR CALLBACK
# =========================================================

async def year_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        parts = query.data.split(":")

        year_id = parts[1]

        await show_album_list(
            query.message.chat,
            year_id,
            0,
            query.message
        )

    except Exception as e:

        print(
            "YEAR ERROR:",
            repr(e)
        )

        await query.message.reply_text(
            "❌ <b>Year തുറക്കാൻ കഴിഞ്ഞില്ല.</b>\n\n"
            + html.escape(
                str(e)
            ),
            parse_mode="HTML"
        )


# =========================================================
# ALBUM PAGINATION
# =========================================================

async def albums_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        parts = query.data.split(":")

        year_id = parts[1]

        page = int(
            parts[2]
        )

        await show_album_list(
            query.message.chat,
            year_id,
            page,
            query.message
        )

    except Exception as e:

        print(
            "ALBUM PAGE ERROR:",
            repr(e)
        )

        await query.message.reply_text(
            "❌ Album page തുറക്കാൻ കഴിഞ്ഞില്ല."
        )


# =========================================================
# SHOW ALBUM
# =========================================================

async def show_album(
    query,
    folder_id
):

    try:

        album = get_album_data(
            folder_id
        )

        info = album["info"]

        songs = album["songs"]

        poster = album["poster"]

        caption = create_album_caption(
            info,
            len(songs)
        )

        # =================================================
        # BACK TO IMMEDIATE PARENT
        # =================================================

        parent_id = get_parent_folder(
            folder_id
        )

        keyboard = []

        # SONGS
        for song in songs:

            keyboard.append([
                InlineKeyboardButton(
                    "🎵 "
                    + song["name"]
                    + " ⬇️",
                    callback_data=(
                        f"file:{song['id']}"
                    )
                )
            ])

        # BACK
        if parent_id:

            keyboard.append([
                InlineKeyboardButton(
                    "⬅️ Back",
                    callback_data=(
                        f"backalbum:{parent_id}"
                    )
                ),
                InlineKeyboardButton(
                    "🏠 Main Menu",
                    callback_data="home"
                )
            ])

        else:

            keyboard.append([
                InlineKeyboardButton(
                    "🏠 Main Menu",
                    callback_data="home"
                )
            ])

        markup = InlineKeyboardMarkup(
            keyboard
        )

        # =================================================
        # DELETE CURRENT ALBUM CARD
        # =================================================

        try:

            await query.message.delete()

        except Exception:

            pass

        # =================================================
        # SEND ALBUM DETAILS
        # =================================================

        if poster:

            temp_path = None

            try:

                image_name = poster.get(
                    "name",
                    "poster.jpg"
                )

                extension = os.path.splitext(
                    image_name
                )[1]

                temp_path = download_drive_file(
                    poster["id"],
                    extension
                )

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

            await query.message.chat.send_message(
                caption,
                parse_mode="HTML",
                reply_markup=markup
            )

    except Exception as e:

        print(
            "SHOW ALBUM ERROR:",
            repr(e)
        )

        await query.message.chat.send_message(
            "❌ <b>Album തുറക്കാൻ കഴിഞ്ഞില്ല.</b>\n\n"
            + html.escape(
                str(e)
            ),
            parse_mode="HTML"
        )


# =========================================================
# ALBUM CALLBACK
# =========================================================

async def album_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        folder_id = (
            query.data.split(
                ":",
                1
            )[1]
        )

        await show_album(
            query,
            folder_id
        )

    except Exception as e:

        print(
            "ALBUM CALLBACK ERROR:",
            repr(e)
        )

        await query.message.reply_text(
            "❌ Album തുറക്കാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(
                str(e)
            )
        )


# =========================================================
# BACK TO ALBUM LIST
# =========================================================

async def backalbum_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        parent_id = (
            query.data.split(
                ":",
                1
            )[1]
        )

        # Parent is the YEAR folder
        await show_album_list(
            query.message.chat,
            parent_id,
            0,
            query.message
        )

    except Exception as e:

        print(
            "BACK ALBUM ERROR:",
            repr(e)
        )

        await query.message.chat.send_message(
            "❌ <b>Album list തുറക്കാൻ കഴിഞ്ഞില്ല.</b>\n\n"
            + html.escape(
                str(e)
            ),
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

        # This callback receives YEAR ID
        year_id = (
            query.data.split(
                ":",
                1
            )[1]
        )

        # Get current page of years
        years = get_year_folders()

        year_index = None

        for index, year in enumerate(years):

            if year["id"] == year_id:

                year_index = index

                break

        if year_index is None:

            page = 0

        else:

            page = (
                year_index
                // YEARS_PER_PAGE
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
                build_year_keyboard(
                    page
                )
            )
        )

    except Exception as e:

        print(
            "BACK YEAR ERROR:",
            repr(e)
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

    context.user_data[
        "search_mode"
    ] = False

    context.user_data[
        "request_mode"
    ] = False

    try:

        await query.message.delete()

    except Exception:

        pass

    await query.message.chat.send_message(
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "📂 <b>Select a year:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            build_year_keyboard(0)
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
                "id,"
                "name,"
                "mimeType,"
                "size"
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
                caption=(
                    "🎵 "
                    + file_name
                )
            )

    except Exception as e:

        print(
            "DOWNLOAD ERROR:",
            repr(e)
        )

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
# LATEST SONGS
# =========================================================

def collect_latest_files(
    folder_id,
    results,
    visited,
    limit=20
):

    if len(results) >= limit:

        return

    if folder_id in visited:

        return

    visited.add(
        folder_id
    )

    try:

        items = get_items(
            folder_id
        )

        for item in items:

            if len(results) >= limit:

                return

            name = item.get(
                "name",
                ""
            )

            lower = name.lower()

            mime = item.get(
                "mimeType"
            )

            if mime == FOLDER_MIME:

                collect_latest_files(
                    item["id"],
                    results,
                    visited,
                    limit
                )

                continue

            if lower in INFO_FILES:

                continue

            if lower.endswith(
                IMAGE_EXTENSIONS
            ):

                continue

            if not lower.endswith(
                SONG_EXTENSIONS
            ):

                continue

            results.append(
                item
            )

    except Exception as e:

        print(
            "LATEST ERROR:",
            repr(e)
        )


# =========================================================
# LATEST
# =========================================================

async def latest_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        results = []

        visited = set()

        collect_latest_files(
            ROOT_FOLDER_ID,
            results,
            visited,
            20
        )

        results.sort(
            key=lambda x:
            x.get(
                "modifiedTime",
                ""
            ),
            reverse=True
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
                    + item["name"]
                    + " ⬇️",
                    callback_data=(
                        f"file:{item['id']}"
                    )
                )
            ])

        await update.message.reply_text(
            "🆕 <b>Latest Songs</b>",
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
            ),
            parse_mode="HTML"
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
            "search",
            search_command
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
            "latest",
            latest_command
        )
    )

    # =====================================================
    # ADMIN REPLY
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.Chat(
                chat_id=ADMIN_CHAT_ID
            )
            & filters.REPLY
            & ~filters.COMMAND,
            admin_reply_handler
        )
    )

    # =====================================================
    # SEARCH / REQUEST TEXT
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            text_message_handler
        )
    )

    # =====================================================
    # YEAR PAGE
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
    # ALBUM PAGE
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            albums_callback,
            pattern=r"^albums:"
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
    # BACK TO ALBUM LIST
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            backalbum_callback,
            pattern=r"^backalbum:"
        )
    )

    # =====================================================
    # BACK TO YEARS
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
