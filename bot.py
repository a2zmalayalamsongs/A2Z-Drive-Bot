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
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly"
]

FOLDER_MIME = "application/vnd.google-apps.folder"

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
SONG_EXTENSIONS = (
    ".mp3", ".m4a", ".aac", ".wav",
    ".flac", ".ogg", ".opus"
)

INFO_FILES = (
    "info.txt",
    "album-info.txt",
    "album info.txt"
)

YEARS_PER_PAGE = 10
ALBUMS_PER_PAGE = 10
SONGS_PER_PAGE = 20


# =========================================================
# GOOGLE DRIVE
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
# DRIVE HELPERS
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
            "id,name,mimeType,size,modifiedTime,parents"
            ")"
        ),
        pageSize=1000
    ).execute()

    return response.get("files", [])


def get_folder_name(folder_id):
    try:
        result = drive.files().get(
            fileId=folder_id,
            fields="name"
        ).execute()

        return result.get("name", "Folder")

    except Exception as e:
        print("FOLDER NAME ERROR:", repr(e))
        return "Folder"


def get_parent_folder(folder_id):
    try:
        result = drive.files().get(
            fileId=folder_id,
            fields="parents"
        ).execute()

        parents = result.get("parents", [])

        if parents:
            return parents[0]

    except Exception as e:
        print("PARENT ERROR:", repr(e))

    return None


def is_song(item):
    return (
        item.get("mimeType") != FOLDER_MIME
        and item.get("name", "").lower().endswith(SONG_EXTENSIONS)
    )


# =========================================================
# YEAR HELPERS
# =========================================================

def get_year_folders():
    items = get_items(ROOT_FOLDER_ID)
    years = []

    for item in items:
        if item.get("mimeType") != FOLDER_MIME:
            continue

        name = item.get("name", "").strip()

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


def find_year_by_id(folder_id):
    for year in get_year_folders():
        if year["id"] == folder_id:
            return year
    return None


# =========================================================
# INFO / ALBUM DATA
# =========================================================

def download_drive_file(file_id, suffix=""):
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
            _, done = downloader.next_chunk()

    return temp_path


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
        print("INFO FILE ERROR:", repr(e))
        return ""

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def parse_info(text, default_album):
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

        if not line or ":" not in line:
            continue

        key, value = line.split(":", 1)

        key = key.strip().lower()
        value = value.strip()

        if key in ("album", "album name"):
            data["album"] = value

        elif key in ("year", "release year"):
            data["year"] = value

        elif key in ("director", "directed by"):
            data["director"] = value

        elif key in ("singer", "singers"):
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


def get_album_data(folder_id):
    items = get_items(folder_id)

    album_name = get_folder_name(folder_id)

    info_file = None
    poster = None
    songs = []

    # IMPORTANT:
    # Album folders do NOT use sub-folders.
    # Only direct songs inside the album are counted.

    for item in items:
        name = item.get("name", "").strip()
        lower = name.lower()

        if item.get("mimeType") == FOLDER_MIME:
            continue

        if lower in INFO_FILES:
            info_file = item
            continue

        if lower.endswith(IMAGE_EXTENSIONS):
            if poster is None:
                poster = item
            continue

        if lower.endswith(SONG_EXTENSIONS):
            songs.append(item)

    songs.sort(
        key=lambda x: x.get("name", "").lower()
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
        "id": folder_id,
        "name": album_name,
        "info": info,
        "poster": poster,
        "songs": songs
    }


def album_card_caption(album):
    info = album["info"]
    tracks = len(album["songs"])

    return (
        "💿 <b>"
        + html.escape(info["album"])
        + "</b>\n\n"
        "📅 <b>Year</b> : "
        + html.escape(info["year"] or "N/A")
        + "\n"
        "🎶 <b>Tracks</b> : "
        + str(tracks)
        + "\n"
        "🏷️ <b>Label</b> : "
        + html.escape(
            info["label"] or "A2Z Malayalam Songs"
        )
    )


def album_full_caption(album):
    info = album["info"]
    tracks = len(album["songs"])

    text = (
        "🎬 <b>Album</b> : "
        + html.escape(info["album"])
    )

    if info["year"]:
        text += (
            "\n📅 <b>Year</b> : "
            + html.escape(info["year"])
        )

    if info["director"]:
        text += (
            "\n🎬 <b>Director</b> : "
            + html.escape(info["director"])
        )

    if info["singer"]:
        text += (
            "\n🎤 <b>Singer</b> : "
            + html.escape(info["singer"])
        )

    if info["music"]:
        text += (
            "\n🎵 <b>Music By</b> : "
            + html.escape(info["music"])
        )

    if info["artists"]:
        text += (
            "\n👥 <b>Artists</b> : "
            + html.escape(info["artists"])
        )

    text += (
        "\n🎶 <b>Total Tracks</b> : "
        + str(tracks)
    )

    text += (
        "\n📤 <b>Upload By</b> : "
        + html.escape(
            info["upload_by"] or "A2Z Malayalam Songs"
        )
    )

    return text


# =========================================================
# CATEGORY MENU
# =========================================================

def category_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💿 Album",
                callback_data="cat:albums"
            ),
            InlineKeyboardButton(
                "🆕 Latest Songs",
                callback_data="cat:latest"
            )
        ],
        [
            InlineKeyboardButton(
                "📅 Year Wise",
                callback_data="cat:years"
            ),
            InlineKeyboardButton(
                "🎧 Lofi Songs",
                callback_data="cat:lofi"
            )
        ],
        [
            InlineKeyboardButton(
                "🔍 Search Songs",
                callback_data="cat:search"
            ),
            InlineKeyboardButton(
                "📩 Request Song",
                callback_data="cat:request"
            )
        ],
        [
            InlineKeyboardButton(
                "ℹ️ Help",
                callback_data="cat:help"
            ),
            InlineKeyboardButton(
                "⚙️ About",
                callback_data="cat:about"
            )
        ]
    ])


async def send_categories(chat):
    await chat.send_message(
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "📂 <b>Choose a Category:</b>",
        parse_mode="HTML",
        reply_markup=category_keyboard()
    )


# =========================================================
# START / HELP / ABOUT
# =========================================================

async def start(update, context):
    context.user_data["search_mode"] = False
    context.user_data["request_mode"] = False
    await send_categories(update.message.chat)


async def help_command(update, context):
    await update.message.reply_text(
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "💿 Album - എല്ലാ Albums\n"
        "🆕 Latest Songs - പുതിയതായി ചേർത്ത Songs\n"
        "📅 Year Wise - Year → Album → Songs\n"
        "🎧 Lofi Songs - Lofi Songs\n"
        "🔍 Search - Song / Movie Search\n"
        "📩 Request - Song Request\n\n"
        "⬅️ Back / 🏠 Main Menu ഉപയോഗിച്ച് "
        "തിരികെ പോകാം.",
        parse_mode="HTML",
        reply_markup=category_keyboard()
    )


async def about_command(update, context):
    await update.message.reply_text(
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "🎶 Malayalam MP3 Songs\n"
        "💿 Albums\n"
        "📅 Year Wise Collection\n"
        "🎧 Lofi Songs\n"
        "🆕 Latest Songs\n"
        "🔍 Search\n"
        "📩 Song Request",
        parse_mode="HTML",
        reply_markup=category_keyboard()
    )


# =========================================================
# BACK / HOME BUTTON
# =========================================================

def home_button():
    return [
        InlineKeyboardButton(
            "🏠 Main Menu",
            callback_data="home"
        )
    ]


def back_home_keyboard(callback_data):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data=callback_data
            ),
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="home"
            )
        ]
    ])


# =========================================================
# YEAR WISE
# =========================================================

def build_year_keyboard(page=0):
    years = get_year_folders()

    total_pages = max(
        1,
        (
            len(years)
            + YEARS_PER_PAGE
            - 1
        ) // YEARS_PER_PAGE
    )

    page = max(
        0,
        min(page, total_pages - 1)
    )

    start = page * YEARS_PER_PAGE

    page_years = years[
        start:start + YEARS_PER_PAGE
    ]

    keyboard = []
    row = []

    for year in page_years:
        row.append(
            InlineKeyboardButton(
                "📁 " + year["name"],
                callback_data=(
                    f"year:{year['id']}:{page}"
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

    keyboard.append([
        InlineKeyboardButton(
            f"📄 Page {page + 1} / {total_pages}",
            callback_data="nothing"
        )
    ])

    keyboard.append(home_button())

    return InlineKeyboardMarkup(keyboard)


async def show_years(chat, page=0, old_message=None):
    if old_message:
        try:
            await old_message.delete()
        except Exception:
            pass

    await chat.send_message(
        "📅 <b>Year Wise</b>\n\n"
        "📂 <b>Select a year:</b>",
        parse_mode="HTML",
        reply_markup=build_year_keyboard(page)
    )


# =========================================================
# YEAR -> ALBUMS
# =========================================================

def get_albums_in_year(year_id):
    items = get_items(year_id)

    albums = []

    for item in items:
        if item.get("mimeType") == FOLDER_MIME:
            albums.append(item)

    albums.sort(
        key=lambda x: x.get("name", "").lower()
    )

    return albums


def album_list_navigation(year_id, page, total_pages):
    buttons = []

    if page > 0:
        buttons.append(
            InlineKeyboardButton(
                "⬅️",
                callback_data=(
                    f"yearalbums:{year_id}:{page - 1}"
                )
            )
        )

    buttons.append(
        InlineKeyboardButton(
            f"{page + 1} / {total_pages}",
            callback_data="nothing"
        )
    )

    if page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton(
                "➡️",
                callback_data=(
                    f"yearalbums:{year_id}:{page + 1}"
                )
            )
        )

    return InlineKeyboardMarkup([
        buttons,
        [
            InlineKeyboardButton(
                "⬅️ Back to Years",
                callback_data="cat:years"
            ),
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="home"
            )
        ]
    ])


async def show_year_albums(
    chat,
    year_id,
    page=0,
    old_message=None
):
    try:
        albums = get_albums_in_year(year_id)

        total_pages = max(
            1,
            (
                len(albums)
                + ALBUMS_PER_PAGE
                - 1
            ) // ALBUMS_PER_PAGE
        )

        page = max(
            0,
            min(page, total_pages - 1)
        )

        start = page * ALBUMS_PER_PAGE

        page_albums = albums[
            start:start + ALBUMS_PER_PAGE
        ]

        if old_message:
            try:
                await old_message.delete()
            except Exception:
                pass

        year_name = get_folder_name(year_id)

        await chat.send_message(
            "💿 <b>Malayalam Albums</b>\n\n"
            "📅 <b>"
            + html.escape(year_name)
            + "</b>\n"
            "🎬 Select an album:",
            parse_mode="HTML"
        )

        for folder in page_albums:
            album = get_album_data(folder["id"])
            await send_album_card(chat, album)

        await chat.send_message(
            "📂 <b>Album Navigation</b>",
            parse_mode="HTML",
            reply_markup=album_list_navigation(
                year_id,
                page,
                total_pages
            )
        )

    except Exception as e:
        print("YEAR ALBUM ERROR:", repr(e))
        await chat.send_message(
            "❌ Album list തുറക്കാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(str(e))
        )


# =========================================================
# ALL ALBUMS CATEGORY
# =========================================================

def get_all_albums():
    albums = []

    for year in get_year_folders():
        try:
            year_albums = get_albums_in_year(year["id"])

            for folder in year_albums:
                albums.append({
                    "id": folder["id"],
                    "name": folder["name"],
                    "year": year["name"]
                })

        except Exception as e:
            print(
                "ALL ALBUMS YEAR ERROR:",
                repr(e)
            )

    # Newest year first, then album name
    albums.sort(
        key=lambda x: (
            -int(x["year"]),
            x["name"].lower()
        )
    )

    return albums


def all_album_navigation(page, total_pages):
    buttons = []

    if page > 0:
        buttons.append(
            InlineKeyboardButton(
                "⬅️",
                callback_data=f"allalbums:{page - 1}"
            )
        )

    buttons.append(
        InlineKeyboardButton(
            f"{page + 1} / {total_pages}",
            callback_data="nothing"
        )
    )

    if page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton(
                "➡️",
                callback_data=f"allalbums:{page + 1}"
            )
        )

    return InlineKeyboardMarkup([
        buttons,
        home_button()
    ])


async def show_all_albums(
    chat,
    page=0,
    old_message=None
):
    try:
        albums = get_all_albums()

        total_pages = max(
            1,
            (
                len(albums)
                + ALBUMS_PER_PAGE
                - 1
            ) // ALBUMS_PER_PAGE
        )

        page = max(
            0,
            min(page, total_pages - 1)
        )

        start = page * ALBUMS_PER_PAGE

        page_albums = albums[
            start:start + ALBUMS_PER_PAGE
        ]

        if old_message:
            try:
                await old_message.delete()
            except Exception:
                pass

        await chat.send_message(
            "💿 <b>Malayalam Albums</b>\n\n"
            "🎬 All available albums",
            parse_mode="HTML"
        )

        for album_ref in page_albums:
            album = get_album_data(
                album_ref["id"]
            )
            await send_album_card(
                chat,
                album
            )

        await chat.send_message(
            "📂 <b>Album Navigation</b>",
            parse_mode="HTML",
            reply_markup=all_album_navigation(
                page,
                total_pages
            )
        )

    except Exception as e:
        print("ALL ALBUM ERROR:", repr(e))
        await chat.send_message(
            "❌ Albums load ചെയ്യാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(str(e))
        )


# =========================================================
# SEND ALBUM CARD
# =========================================================

async def send_album_card(chat, album):
    caption = album_card_caption(album)

    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💿 View Album ➡️",
                callback_data=f"album:{album['id']}"
            )
        ]
    ])

    poster = album["poster"]

    if poster:
        temp_path = None

        try:
            poster_name = poster.get(
                "name",
                "poster.jpg"
            )

            extension = os.path.splitext(
                poster_name
            )[1]

            temp_path = download_drive_file(
                poster["id"],
                extension
            )

            with open(temp_path, "rb") as photo:
                await chat.send_photo(
                    photo=photo,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )

        except Exception as e:
            print("POSTER SEND ERROR:", repr(e))

            await chat.send_message(
                caption,
                parse_mode="HTML",
                reply_markup=markup
            )

        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    else:
        await chat.send_message(
            caption,
            parse_mode="HTML",
            reply_markup=markup
        )


# =========================================================
# ALBUM -> SONGS
# =========================================================

async def show_album(query, folder_id):
    try:
        album = get_album_data(folder_id)

        caption = album_full_caption(album)

        keyboard = []

        for song in album["songs"]:
            keyboard.append([
                InlineKeyboardButton(
                    "🎵 "
                    + song["name"]
                    + " ⬇️",
                    callback_data=f"file:{song['id']}"
                )
            ])

        parent_id = get_parent_folder(folder_id)

        if parent_id:
            year = find_year_by_id(parent_id)

            if year:
                back_callback = (
                    f"yearalbums:{parent_id}:0"
                )
            else:
                back_callback = "cat:albums"
        else:
            back_callback = "cat:albums"

        keyboard.append([
            InlineKeyboardButton(
                "⬅️ Back",
                callback_data=back_callback
            ),
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="home"
            )
        ])

        try:
            await query.message.delete()
        except Exception:
            pass

        markup = InlineKeyboardMarkup(keyboard)

        poster = album["poster"]

        if poster:
            temp_path = None

            try:
                poster_name = poster.get(
                    "name",
                    "poster.jpg"
                )

                extension = os.path.splitext(
                    poster_name
                )[1]

                temp_path = download_drive_file(
                    poster["id"],
                    extension
                )

                with open(temp_path, "rb") as photo:
                    await query.message.chat.send_photo(
                        photo=photo,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=markup
                    )

            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass

        else:
            await query.message.chat.send_message(
                caption,
                parse_mode="HTML",
                reply_markup=markup
            )

    except Exception as e:
        print("SHOW ALBUM ERROR:", repr(e))

        await query.message.chat.send_message(
            "❌ Album തുറക്കാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(str(e))
        )


# =========================================================
# LOFI FOLDER
# =========================================================

def find_lofi_folder():
    items = get_items(ROOT_FOLDER_ID)

    candidates = (
        "lofi",
        "lofi songs",
        "lofi song",
        "lofi music"
    )

    for item in items:
        if item.get("mimeType") != FOLDER_MIME:
            continue

        name = item.get("name", "").strip().lower()

        if name in candidates:
            return item

    return None


def get_lofi_songs():
    folder = find_lofi_folder()

    if not folder:
        return None, []

    songs = []

    # Lofi category intentionally reads direct songs only.
    # Sub-folders are not needed.
    for item in get_items(folder["id"]):
        if is_song(item):
            songs.append(item)

    songs.sort(
        key=lambda x: (
            x.get("modifiedTime", ""),
            x.get("name", "").lower()
        ),
        reverse=True
    )

    return folder, songs


def lofi_song_keyboard(songs, page=0):
    total_pages = max(
        1,
        (
            len(songs)
            + SONGS_PER_PAGE
            - 1
        ) // SONGS_PER_PAGE
    )

    page = max(
        0,
        min(page, total_pages - 1)
    )

    start = page * SONGS_PER_PAGE

    page_songs = songs[
        start:start + SONGS_PER_PAGE
    ]

    keyboard = []

    for song in page_songs:
        keyboard.append([
            InlineKeyboardButton(
                "🎧 "
                + song["name"]
                + " ⬇️",
                callback_data=f"file:{song['id']}"
            )
        ])

    nav = []

    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "⬅️",
                callback_data=f"lofipage:{page - 1}"
            )
        )

    nav.append(
        InlineKeyboardButton(
            f"{page + 1} / {total_pages}",
            callback_data="nothing"
        )
    )

    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                "➡️",
                callback_data=f"lofipage:{page + 1}"
            )
        )

    keyboard.append(nav)

    keyboard.append(home_button())

    return InlineKeyboardMarkup(keyboard)


async def show_lofi(
    chat,
    page=0,
    old_message=None
):
    try:
        folder, songs = get_lofi_songs()

        if old_message:
            try:
                await old_message.delete()
            except Exception:
                pass

        if not folder:
            await chat.send_message(
                "🎧 <b>Lofi Songs</b>\n\n"
                "❌ Google Drive-ൽ "
                "<b>Lofi</b> folder കണ്ടെത്തിയില്ല.",
                parse_mode="HTML",
                reply_markup=category_keyboard()
            )
            return

        if not songs:
            await chat.send_message(
                "🎧 <b>Lofi Songs</b>\n\n"
                "❌ Lofi songs ഒന്നും കണ്ടെത്തിയില്ല.",
                parse_mode="HTML",
                reply_markup=category_keyboard()
            )
            return

        await chat.send_message(
            "🎧 <b>Lofi Songs</b>\n\n"
            "🎵 Total Songs : "
            + str(len(songs))
            + "\n"
            "⬇️ Download ചെയ്യാൻ song click ചെയ്യുക.",
            parse_mode="HTML"
        )

        await chat.send_message(
            "🎧 <b>Lofi Song List</b>",
            parse_mode="HTML",
            reply_markup=lofi_song_keyboard(
                songs,
                page
            )
        )

    except Exception as e:
        print("LOFI ERROR:", repr(e))

        await chat.send_message(
            "❌ Lofi songs load ചെയ്യാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(str(e))
        )


# =========================================================
# LATEST SONGS
# =========================================================

def collect_all_songs(folder_id, results, visited):
    if folder_id in visited:
        return

    visited.add(folder_id)

    try:
        items = get_items(folder_id)

        for item in items:
            if item.get("mimeType") == FOLDER_MIME:
                collect_all_songs(
                    item["id"],
                    results,
                    visited
                )
                continue

            if is_song(item):
                results.append(item)

    except Exception as e:
        print("COLLECT SONG ERROR:", repr(e))


def get_latest_songs():
    results = []
    visited = set()

    collect_all_songs(
        ROOT_FOLDER_ID,
        results,
        visited
    )

    # Remove duplicates
    unique = {}

    for item in results:
        unique[item["id"]] = item

    results = list(unique.values())

    results.sort(
        key=lambda x: x.get("modifiedTime", ""),
        reverse=True
    )

    return results[:100]


def latest_keyboard(songs, page=0):
    total_pages = max(
        1,
        (
            len(songs)
            + SONGS_PER_PAGE
            - 1
        ) // SONGS_PER_PAGE
    )

    page = max(
        0,
        min(page, total_pages - 1)
    )

    start = page * SONGS_PER_PAGE

    page_songs = songs[
        start:start + SONGS_PER_PAGE
    ]

    keyboard = []

    for song in page_songs:
        keyboard.append([
            InlineKeyboardButton(
                "🆕 "
                + song["name"]
                + " ⬇️",
                callback_data=f"file:{song['id']}"
            )
        ])

    nav = []

    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "⬅️",
                callback_data=f"latestpage:{page - 1}"
            )
        )

    nav.append(
        InlineKeyboardButton(
            f"{page + 1} / {total_pages}",
            callback_data="nothing"
        )
    )

    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                "➡️",
                callback_data=f"latestpage:{page + 1}"
            )
        )

    keyboard.append(nav)
    keyboard.append(home_button())

    return InlineKeyboardMarkup(keyboard)


async def show_latest(
    chat,
    page=0,
    old_message=None
):
    try:
        songs = get_latest_songs()

        if old_message:
            try:
                await old_message.delete()
            except Exception:
                pass

        if not songs:
            await chat.send_message(
                "🆕 <b>Latest Songs</b>\n\n"
                "❌ Songs ഒന്നും കണ്ടെത്തിയില്ല.",
                parse_mode="HTML",
                reply_markup=category_keyboard()
            )
            return

        await chat.send_message(
            "🆕 <b>Latest Songs</b>\n\n"
            "പുതിയതായി Google Drive-ൽ "
            "add ചെയ്ത songs ഇവിടെ കാണിക്കും.",
            parse_mode="HTML"
        )

        await chat.send_message(
            "🎵 <b>Song List</b>",
            parse_mode="HTML",
            reply_markup=latest_keyboard(
                songs,
                page
            )
        )

    except Exception as e:
        print("LATEST ERROR:", repr(e))

        await chat.send_message(
            "❌ Latest songs load ചെയ്യാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(str(e))
        )


# =========================================================
# SEARCH
# =========================================================

def search_drive(
    folder_id,
    search_text,
    results,
    visited,
    limit=50
):
    if len(results) >= limit:
        return

    if folder_id in visited:
        return

    visited.add(folder_id)

    try:
        items = get_items(folder_id)

        search_lower = search_text.lower()

        for item in items:
            if len(results) >= limit:
                return

            name = item.get("name", "")
            lower = name.lower()

            if item.get("mimeType") == FOLDER_MIME:
                if search_lower in lower:
                    results.append(item)

                search_drive(
                    item["id"],
                    search_text,
                    results,
                    visited,
                    limit
                )

                continue

            if lower in INFO_FILES:
                continue

            if lower.endswith(IMAGE_EXTENSIONS):
                continue

            if search_lower in lower:
                results.append(item)

    except Exception as e:
        print("SEARCH DRIVE ERROR:", repr(e))


async def perform_search(message, search_text):
    results = []
    visited = set()

    try:
        status = await message.reply_text(
            "🔍 <b>Searching...</b>\n\n"
            "Please wait ⏳",
            parse_mode="HTML"
        )

        search_drive(
            ROOT_FOLDER_ID,
            search_text,
            results,
            visited
        )

        try:
            await status.delete()
        except Exception:
            pass

        if not results:
            await message.reply_text(
                "❌ <b>No results found</b>\n\n"
                "Search: <b>"
                + html.escape(search_text)
                + "</b>",
                parse_mode="HTML",
                reply_markup=category_keyboard()
            )
            return

        keyboard = []

        for item in results:
            name = item.get("name", "Song")

            if item.get("mimeType") == FOLDER_MIME:
                keyboard.append([
                    InlineKeyboardButton(
                        "💿 " + name,
                        callback_data=f"album:{item['id']}"
                    )
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton(
                        "🎵 "
                        + name
                        + " ⬇️",
                        callback_data=f"file:{item['id']}"
                    )
                ])

        await message.reply_text(
            "🔍 <b>Search Results</b>\n\n"
            "Search: <b>"
            + html.escape(search_text)
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
        print("SEARCH ERROR:", repr(e))

        await message.reply_text(
            "❌ Search failed.\n\n"
            + html.escape(str(e))
        )


async def search_command(update, context):
    context.user_data["search_mode"] = True
    context.user_data["request_mode"] = False

    if context.args:
        search_text = " ".join(context.args)

        context.user_data["search_mode"] = False

        await perform_search(
            update.message,
            search_text
        )
        return

    await update.message.reply_text(
        "🔍 <b>Search Songs</b>\n\n"
        "Movie / Song name type ചെയ്ത് അയക്കൂ.\n\n"
        "ഉദാഹരണം:\n"
        "<code>Varnajaalam</code>",
        parse_mode="HTML"
    )


# =========================================================
# REQUEST
# =========================================================

async def request_command(update, context):
    context.user_data["request_mode"] = True
    context.user_data["search_mode"] = False

    await update.message.reply_text(
        "📩 <b>Song Request</b>\n\n"
        "Movie / Song name type ചെയ്ത് അയക്കൂ.\n\n"
        "ഉദാഹരണം:\n"
        "<code>Manjummel Boys movie songs വേണം</code>",
        parse_mode="HTML"
    )


async def send_request_to_admin(update, context):
    request_text = (
        update.message.text or ""
    ).strip()

    if not request_text:
        await update.message.reply_text(
            "❌ Request text അയക്കൂ."
        )
        return

    user = update.effective_user

    first_name = user.first_name or "Unknown"

    username = (
        "@" + user.username
        if user.username
        else "No username"
    )

    admin_text = (
        "📩 <b>NEW SONG REQUEST</b>\n\n"
        "👤 <b>User:</b> "
        + html.escape(first_name)
        + "\n"
        "🔗 <b>Username:</b> "
        + html.escape(username)
        + "\n"
        "🆔 <b>User ID:</b> "
        + str(user.id)
        + "\n\n"
        "🎬 <b>Request:</b>\n"
        + html.escape(request_text)
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
            "📩 Admin-ന് request ലഭിച്ചു.",
            parse_mode="HTML"
        )

    except Exception as e:
        print("REQUEST ERROR:", repr(e))

        await update.message.reply_text(
            "❌ Request അയക്കാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(str(e))
        )


# =========================================================
# TEXT HANDLER
# =========================================================

async def text_message_handler(update, context):
    if context.user_data.get(
        "search_mode",
        False
    ):
        context.user_data["search_mode"] = False

        search_text = (
            update.message.text or ""
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
        context.user_data["request_mode"] = False

        await send_request_to_admin(
            update,
            context
        )


# =========================================================
# ADMIN REPLY
# =========================================================

async def admin_reply_handler(update, context):
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
            .split("\n", 1)[0]
            .strip()
        )

        user_id = int(user_id_text)

    except Exception:
        await message.reply_text(
            "❌ User ID ശരിയായി കണ്ടെത്താൻ കഴിഞ്ഞില്ല."
        )
        return

    try:
        if message.text:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "📩 <b>Admin Reply</b>\n\n"
                    + html.escape(message.text)
                ),
                parse_mode="HTML"
            )

            await message.reply_text(
                "✅ Reply user-ന് അയച്ചു."
            )
            return

        if message.photo:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption="📩 Admin Reply"
            )

            await message.reply_text(
                "✅ Photo user-ന് അയച്ചു."
            )
            return

        if message.document:
            await context.bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption="📩 Admin Reply"
            )

            await message.reply_text(
                "✅ File user-ന് അയച്ചു."
            )
            return

        await message.reply_text(
            "❌ ഈ reply type support ചെയ്യുന്നില്ല."
        )

    except Exception as e:
        print("ADMIN REPLY ERROR:", repr(e))

        await message.reply_text(
            "❌ User-ന് reply അയക്കാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(str(e))
        )


# =========================================================
# CATEGORY CALLBACK
# =========================================================

async def category_callback(update, context):
    query = update.callback_query
    await query.answer()

    category = query.data.split(":", 1)[1]

    try:
        await query.message.delete()
    except Exception:
        pass

    chat = query.message.chat

    if category == "albums":
        await show_all_albums(chat, 0)
        return

    if category == "latest":
        await show_latest(chat, 0)
        return

    if category == "years":
        await show_years(chat, 0)
        return

    if category == "lofi":
        await show_lofi(chat, 0)
        return

    if category == "search":
        context.user_data["search_mode"] = True
        context.user_data["request_mode"] = False

        await chat.send_message(
            "🔍 <b>Search Songs</b>\n\n"
            "Movie / Song name type ചെയ്ത് അയക്കൂ.",
            parse_mode="HTML"
        )
        return

    if category == "request":
        context.user_data["request_mode"] = True
        context.user_data["search_mode"] = False

        await chat.send_message(
            "📩 <b>Song Request</b>\n\n"
            "Movie / Song name type ചെയ്ത് അയക്കൂ.",
            parse_mode="HTML"
        )
        return

    if category == "help":
        await chat.send_message(
            "🎵 <b>A2Z Malayalam Songs</b>\n\n"
            "💿 Album\n"
            "🆕 Latest Songs\n"
            "📅 Year Wise\n"
            "🎧 Lofi Songs\n"
            "🔍 Search Songs\n"
            "📩 Request Song",
            parse_mode="HTML",
            reply_markup=category_keyboard()
        )
        return

    if category == "about":
        await chat.send_message(
            "🎵 <b>A2Z Malayalam Songs</b>\n\n"
            "Malayalam MP3 Songs Collection",
            parse_mode="HTML",
            reply_markup=category_keyboard()
        )


# =========================================================
# YEAR CALLBACK
# =========================================================

async def year_callback(update, context):
    query = update.callback_query
    await query.answer()

    try:
        _, year_id, page = query.data.split(":", 2)

        if not find_year_by_id(year_id):
            await query.message.chat.send_message(
                "❌ Year കണ്ടെത്താൻ കഴിഞ്ഞില്ല."
            )
            return

        await show_year_albums(
            query.message.chat,
            year_id,
            0,
            query.message
        )

    except Exception as e:
        print("YEAR CALLBACK ERROR:", repr(e))

        await query.message.chat.send_message(
            "❌ Year തുറക്കാൻ കഴിഞ്ഞില്ല."
        )


async def yearpage_callback(update, context):
    query = update.callback_query
    await query.answer()

    try:
        page = int(
            query.data.split(":", 1)[1]
        )

        await show_years(
            query.message.chat,
            page,
            query.message
        )

    except Exception as e:
        print("YEAR PAGE ERROR:", repr(e))


async def yearalbums_callback(update, context):
    query = update.callback_query
    await query.answer()

    try:
        _, year_id, page = query.data.split(":", 2)

        await show_year_albums(
            query.message.chat,
            year_id,
            int(page),
            query.message
        )

    except Exception as e:
        print("YEAR ALBUM PAGE ERROR:", repr(e))


# =========================================================
# ALL ALBUMS CALLBACK
# =========================================================

async def allalbums_callback(update, context):
    query = update.callback_query
    await query.answer()

    try:
        page = int(
            query.data.split(":", 1)[1]
        )

        await show_all_albums(
            query.message.chat,
            page,
            query.message
        )

    except Exception as e:
        print("ALL ALBUM PAGE ERROR:", repr(e))


# =========================================================
# ALBUM CALLBACK
# =========================================================

async def album_callback(update, context):
    query = update.callback_query
    await query.answer()

    try:
        folder_id = query.data.split(
            ":",
            1
        )[1]

        await show_album(
            query,
            folder_id
        )

    except Exception as e:
        print("ALBUM CALLBACK ERROR:", repr(e))


# =========================================================
# LOFI CALLBACKS
# =========================================================

async def lofi_callback(update, context):
    query = update.callback_query
    await query.answer()

    try:
        await show_lofi(
            query.message.chat,
            0,
            query.message
        )
    except Exception as e:
        print("LOFI CALLBACK ERROR:", repr(e))


async def lofipage_callback(update, context):
    query = update.callback_query
    await query.answer()

    try:
        page = int(
            query.data.split(":", 1)[1]
        )

        await show_lofi(
            query.message.chat,
            page,
            query.message
        )

    except Exception as e:
        print("LOFI PAGE ERROR:", repr(e))


# =========================================================
# LATEST CALLBACKS
# =========================================================

async def latest_callback(update, context):
    query = update.callback_query
    await query.answer()

    try:
        await show_latest(
            query.message.chat,
            0,
            query.message
        )
    except Exception as e:
        print("LATEST CALLBACK ERROR:", repr(e))


async def latestpage_callback(update, context):
    query = update.callback_query
    await query.answer()

    try:
        page = int(
            query.data.split(":", 1)[1]
        )

        await show_latest(
            query.message.chat,
            page,
            query.message
        )

    except Exception as e:
        print("LATEST PAGE ERROR:", repr(e))


# =========================================================
# FILE DOWNLOAD
# =========================================================

async def file_callback(update, context):
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

        with open(temp_path, "rb") as file:
            await query.message.reply_document(
                document=file,
                filename=file_name,
                caption="🎵 " + file_name
            )

    except Exception as e:
        print("DOWNLOAD ERROR:", repr(e))

        await query.message.chat.send_message(
            "❌ <b>Download failed</b>\n\n"
            + html.escape(str(e)),
            parse_mode="HTML"
        )

    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


# =========================================================
# HOME CALLBACK
# =========================================================

async def home_callback(update, context):
    query = update.callback_query
    await query.answer()

    context.user_data["search_mode"] = False
    context.user_data["request_mode"] = False

    try:
        await query.message.delete()
    except Exception:
        pass

    await send_categories(
        query.message.chat
    )


# =========================================================
# NOTHING
# =========================================================

async def nothing_callback(update, context):
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

    # Commands
    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        CommandHandler("about", about_command)
    )

    app.add_handler(
        CommandHandler("search", search_command)
    )

    app.add_handler(
        CommandHandler("request", request_command)
    )

    # /latest is also supported
    app.add_handler(
        CommandHandler(
            "latest",
            lambda update, context: show_latest(
                update.message.chat,
                0
            )
        )
    )

    # Admin replies
    app.add_handler(
        MessageHandler(
            filters.Chat(chat_id=ADMIN_CHAT_ID)
            & filters.REPLY
            & ~filters.COMMAND,
            admin_reply_handler
        )
    )

    # Search / Request text
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_message_handler
        )
    )

    # Category
    app.add_handler(
        CallbackQueryHandler(
            category_callback,
            pattern=r"^cat:"
        )
    )

    # Years
    app.add_handler(
        CallbackQueryHandler(
            yearpage_callback,
            pattern=r"^yearpage:\d+$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            year_callback,
            pattern=r"^year:"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            yearalbums_callback,
            pattern=r"^yearalbums:"
        )
    )

    # All Albums
    app.add_handler(
        CallbackQueryHandler(
            allalbums_callback,
            pattern=r"^allalbums:\d+$"
        )
    )

    # Album
    app.add_handler(
        CallbackQueryHandler(
            album_callback,
            pattern=r"^album:"
        )
    )

    # Lofi
    app.add_handler(
        CallbackQueryHandler(
            lofi_callback,
            pattern=r"^lofi$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            lofipage_callback,
            pattern=r"^lofipage:\d+$"
        )
    )

    # Latest
    app.add_handler(
        CallbackQueryHandler(
            latest_callback,
            pattern=r"^latest$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            latestpage_callback,
            pattern=r"^latestpage:\d+$"
        )
    )

    # File
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

    # Nothing
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


if __name__ == "__main__":
    main()
