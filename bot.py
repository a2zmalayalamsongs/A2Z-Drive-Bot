import os
import tempfile
import json
import html

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

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
ITEMS_PER_PAGE = 10
SONGS_PER_PAGE = 20


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
# DRIVE HELPERS
# =========================================================

def get_items(folder_id):
    items = []
    page_token = None

    query = (
        f"'{folder_id}' in parents "
        "and trashed = false"
    )

    while True:
        response = drive.files().list(
            q=query,
            fields=(
                "nextPageToken,"
                "files(id,name,mimeType,size,modifiedTime,parents)"
            ),
            pageSize=1000,
            pageToken=page_token
        ).execute()

        items.extend(response.get("files", []))

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return items


def get_file(file_id):
    return drive.files().get(
        fileId=file_id,
        fields="id,name,mimeType,size,modifiedTime,parents"
    ).execute()


def get_folder_name(folder_id):
    try:
        return get_file(folder_id).get("name", "Folder")
    except Exception as e:
        print("FOLDER NAME ERROR:", repr(e))
        return "Folder"


def get_parent_folder(folder_id):
    try:
        data = get_file(folder_id)
        parents = data.get("parents", [])
        return parents[0] if parents else None
    except Exception as e:
        print("PARENT ERROR:", repr(e))
        return None


def is_folder(item):
    return item.get("mimeType") == FOLDER_MIME


def is_image(item):
    return item.get("name", "").lower().endswith(IMAGE_EXTENSIONS)


def is_song(item):
    return (
        not is_folder(item)
        and item.get("name", "").lower().endswith(SONG_EXTENSIONS)
    )


# =========================================================
# FIND TOP-LEVEL CATEGORY FOLDERS
#
# Expected Drive:
#
# A2Z Malayalam Songs
# ├── Year Wise
# │   ├── 2028
# │   ├── 2027
# │   ├── 2026
# │   └── ...
# └── Lofi Songs
#     ├── Lofi Song Folder 1
#     └── Lofi Song Folder 2
#
# Fallback: if Year Wise is absent, numeric year folders
# directly under ROOT are also supported.
# =========================================================

def find_top_folder(names):
    wanted = {x.lower() for x in names}

    for item in get_items(ROOT_FOLDER_ID):
        if not is_folder(item):
            continue

        if item.get("name", "").strip().lower() in wanted:
            return item

    return None


def find_year_wise_folder():
    return find_top_folder([
        "year wise",
        "yearwise",
        "years",
        "year"
    ])


def find_lofi_folder():
    return find_top_folder([
        "lofi songs",
        "lofi song",
        "lofi",
        "lofi music"
    ])


# =========================================================
# YEARS
# =========================================================

def get_year_folders():
    year_root = find_year_wise_folder()

    if year_root:
        items = get_items(year_root["id"])
    else:
        # Backward compatibility with old Drive structure
        items = get_items(ROOT_FOLDER_ID)

    years = []

    for item in items:
        if not is_folder(item):
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


def find_year_by_id(year_id):
    for year in get_year_folders():
        if year["id"] == year_id:
            return year
    return None


# =========================================================
# INFO FILE
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
        ) as f:
            return f.read()

    except Exception as e:
        print("INFO ERROR:", repr(e))
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

        elif key in ("music", "music by", "music director"):
            data["music"] = value

        elif key in ("artist", "artists", "cast"):
            data["artists"] = value

        elif key in ("label", "music label"):
            data["label"] = value

        elif key in ("upload by", "uploaded by", "uploader"):
            data["upload_by"] = value

    return data


# =========================================================
# ALBUM DATA
#
# Direct songs are used for the album.
# If an album contains folders, those folders are shown
# instead of silently ignoring them.
# =========================================================

def get_folder_contents(folder_id):
    items = get_items(folder_id)

    folders = []
    songs = []
    images = []
    info_file = None
    other_files = []

    for item in items:
        name = item.get("name", "").strip()
        lower = name.lower()

        if is_folder(item):
            folders.append(item)
        elif lower in INFO_FILES:
            info_file = item
        elif is_image(item):
            images.append(item)
        elif is_song(item):
            songs.append(item)
        else:
            other_files.append(item)

    folders.sort(key=lambda x: x.get("name", "").lower())
    songs.sort(key=lambda x: x.get("name", "").lower())

    return folders, songs, images, info_file, other_files


def get_album_data(folder_id):
    folders, songs, images, info_file, other_files = get_folder_contents(
        folder_id
    )

    folder_name = get_folder_name(folder_id)

    info_text = read_info_file(info_file["id"]) if info_file else ""

    info = parse_info(
        info_text,
        folder_name
    )

    return {
        "id": folder_id,
        "name": folder_name,
        "folders": folders,
        "songs": songs,
        "images": images,
        "info": info,
        "other_files": other_files
    }


def album_caption(album):
    info = album["info"]

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
        + str(len(album["songs"]))
    )

    text += (
        "\n📤 <b>Upload By</b> : "
        + html.escape(
            info["upload_by"] or "A2Z Malayalam Songs"
        )
    )

    return text


def album_card_caption(album):
    info = album["info"]

    return (
        "💿 <b>"
        + html.escape(info["album"])
        + "</b>\n"
        "📅 "
        + html.escape(info["year"] or "N/A")
        + "\n"
        "🎶 Tracks : "
        + str(len(album["songs"]))
        + (
            "\n🏷️ Label : "
            + html.escape(info["label"])
            if info["label"]
            else ""
        )
    )


# =========================================================
# MAIN CATEGORY MENU
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


async def send_categories(chat, old_message=None):
    if old_message:
        try:
            await old_message.delete()
        except Exception:
            pass

    await chat.send_message(
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "📂 <b>Choose a Category:</b>",
        parse_mode="HTML",
        reply_markup=category_keyboard()
    )


# =========================================================
# START
# =========================================================

async def start(update, context):
    context.user_data["search_mode"] = False
    context.user_data["request_mode"] = False

    await send_categories(
        update.message.chat
    )


# =========================================================
# ALL ALBUMS
#
# Albums are collected from:
# Year Wise -> each year -> direct album folders
# =========================================================

def get_all_album_refs():
    refs = []

    for year in get_year_folders():
        try:
            for item in get_items(year["id"]):
                if is_folder(item):
                    refs.append({
                        "id": item["id"],
                        "name": item["name"],
                        "year": year["name"]
                    })
        except Exception as e:
            print("ALBUM YEAR ERROR:", repr(e))

    refs.sort(
        key=lambda x: (
            -int(x["year"]),
            x["name"].lower()
        )
    )

    return refs


def page_buttons(prefix, page, total_pages, back_callback="home"):
    row = []

    if page > 0:
        row.append(
            InlineKeyboardButton(
                "⬅️",
                callback_data=f"{prefix}:{page - 1}"
            )
        )

    row.append(
        InlineKeyboardButton(
            f"{page + 1} / {total_pages}",
            callback_data="nothing"
        )
    )

    if page < total_pages - 1:
        row.append(
            InlineKeyboardButton(
                "➡️",
                callback_data=f"{prefix}:{page + 1}"
            )
        )

    return [
        row,
        [
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data=back_callback
            )
        ]
    ]


async def show_all_albums(chat, page=0, old_message=None):
    try:
        refs = get_all_album_refs()
        total_pages = max(1, (len(refs) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        page = max(0, min(page, total_pages - 1))

        if old_message:
            try:
                await old_message.delete()
            except Exception:
                pass

        if not refs:
            await chat.send_message(
                "💿 <b>Album</b>\n\n❌ Album ഒന്നും കണ്ടെത്തിയില്ല.",
                parse_mode="HTML",
                reply_markup=category_keyboard()
            )
            return

        start = page * ITEMS_PER_PAGE
        page_refs = refs[start:start + ITEMS_PER_PAGE]

        keyboard = []
        for ref in page_refs:
            keyboard.append([
                InlineKeyboardButton(
                    "💿 " + ref["name"],
                    callback_data=f"album:{ref['id']}"
                )
            ])

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                "⬅️ Previous",
                callback_data=f"allalbums:{page - 1}"
            ))
        nav.append(InlineKeyboardButton(
            f"📄 {page + 1} / {total_pages}",
            callback_data="nothing"
        ))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(
                "Next ➡️",
                callback_data=f"allalbums:{page + 1}"
            ))

        keyboard.append(nav)
        keyboard.append([
            InlineKeyboardButton("🏠 Main Menu", callback_data="home")
        ])

        await chat.send_message(
            "💿 <b>Malayalam Albums</b>\n\n"
            "🎬 <b>Select an album:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        print("ALL ALBUMS ERROR:", repr(e))
        await chat.send_message(
            "❌ Album list തുറക്കാൻ കഴിഞ്ഞില്ല.\n\n" + html.escape(str(e)),
            reply_markup=category_keyboard()
        )



async def send_album_card(chat, album):
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "💿 View Album ➡️",
                callback_data=f"album:{album['id']}"
            )
        ]
    ])

    caption = album_card_caption(album)

    poster = (
        album["images"][0]
        if album["images"]
        else None
    )

    if poster:
        temp_path = None

        try:
            ext = os.path.splitext(
                poster["name"]
            )[1]

            temp_path = download_drive_file(
                poster["id"],
                ext
            )

            with open(temp_path, "rb") as photo:
                await chat.send_photo(
                    photo=photo,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=markup
                )

        except Exception as e:
            print("ALBUM CARD POSTER ERROR:", repr(e))

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
# YEAR WISE
# =========================================================

def year_keyboard(page=0):
    years = get_year_folders()

    total_pages = max(
        1,
        (len(years) + YEARS_PER_PAGE - 1)
        // YEARS_PER_PAGE
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
                callback_data=f"year:{year['id']}"
            )
        )

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    nav = []

    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "⬅️ Previous",
                callback_data=f"yearpage:{page - 1}"
            )
        )

    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                "Next ➡️",
                callback_data=f"yearpage:{page + 1}"
            )
        )

    if nav:
        keyboard.append(nav)

    keyboard.append([
        InlineKeyboardButton(
            f"📄 Page {page + 1} / {total_pages}",
            callback_data="nothing"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🏠 Main Menu",
            callback_data="home"
        )
    ])

    return InlineKeyboardMarkup(keyboard)


async def show_years(
    chat,
    page=0,
    old_message=None
):
    if old_message:
        try:
            await old_message.delete()
        except Exception:
            pass

    years = get_year_folders()

    if not years:
        await chat.send_message(
            "📅 <b>Year Wise</b>\n\n"
            "❌ Year folders ഒന്നും കണ്ടെത്തിയില്ല.\n\n"
            "Google Drive-ൽ <b>Year Wise</b> folder-ന്റെ "
            "അകത്ത് 2028, 2027, 2026... folders ഉണ്ടെന്ന് "
            "ഉറപ്പാക്കുക.",
            parse_mode="HTML",
            reply_markup=category_keyboard()
        )
        return

    await chat.send_message(
        "📅 <b>Year Wise</b>\n\n"
        "📂 <b>Select a year:</b>",
        parse_mode="HTML",
        reply_markup=year_keyboard(page)
    )


async def show_year_albums(
    chat,
    year_id,
    page=0,
    old_message=None
):
    try:
        year = find_year_by_id(year_id)

        if not year:
            await chat.send_message(
                "❌ Year കണ്ടെത്താൻ കഴിഞ്ഞില്ല.",
                reply_markup=category_keyboard()
            )
            return

        items = get_items(year_id)

        # Direct folders are the albums.
        albums = [
            x for x in items
            if is_folder(x)
        ]

        albums.sort(
            key=lambda x: x.get("name", "").lower()
        )

        total_pages = max(
            1,
            (len(albums) + ITEMS_PER_PAGE - 1)
            // ITEMS_PER_PAGE
        )

        page = max(
            0,
            min(page, total_pages - 1)
        )

        start = page * ITEMS_PER_PAGE

        page_albums = albums[
            start:start + ITEMS_PER_PAGE
        ]

        if old_message:
            try:
                await old_message.delete()
            except Exception:
                pass

        if not albums:
            await chat.send_message(
                "📅 <b>"
                + html.escape(year["name"])
                + "</b>\n\n"
                "❌ ഈ വർഷത്തിൽ Album ഒന്നും കണ്ടെത്തിയില്ല.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
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
            )
            return

        await chat.send_message(
            "💿 <b>Malayalam Albums</b>\n\n"
            "📅 <b>"
            + html.escape(year["name"])
            + "</b>",
            parse_mode="HTML"
        )

        for folder in page_albums:
            album = get_album_data(
                folder["id"]
            )

            await send_album_card(
                chat,
                album
            )

        nav = []

        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    "⬅️",
                    callback_data=(
                        f"yearalbums:{year_id}:{page - 1}"
                    )
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
                    callback_data=(
                        f"yearalbums:{year_id}:{page + 1}"
                    )
                )
            )

        await chat.send_message(
            "📂 <b>Album Navigation</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                nav,
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
        )

    except Exception as e:
        print("YEAR ALBUM ERROR:", repr(e))

        await chat.send_message(
            "❌ Album list തുറക്കാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(str(e))
        )


# =========================================================
# ALBUM / SUB-FOLDER VIEW
# =========================================================

async def show_folder(
    chat,
    folder_id,
    old_message=None,
    title_prefix="📂"
):
    try:
        album = get_album_data(folder_id)

        if old_message:
            try:
                await old_message.delete()
            except Exception:
                pass

        # If this folder has an Album-Info / poster,
        # show the full album information.
        has_album_info = (
            bool(album["info"]["year"])
            or bool(album["info"]["director"])
            or bool(album["info"]["singer"])
            or bool(album["info"]["music"])
            or bool(album["info"]["artists"])
            or bool(album["info"]["upload_by"])
            or bool(album["images"])
            or bool(album["songs"])
        )

        keyboard = []

        # Sub-folders are shown only when they actually exist.
        for folder in album["folders"]:
            keyboard.append([
                InlineKeyboardButton(
                    "📁 " + folder["name"],
                    callback_data=f"folder:{folder['id']}"
                )
            ])

        for song in album["songs"]:
            keyboard.append([
                InlineKeyboardButton(
                    "🎵 "
                    + song["name"]
                    + " ⬇️",
                    callback_data=f"file:{song['id']}"
                )
            ])

        # Other downloadable files, if present.
        for item in album["other_files"]:
            keyboard.append([
                InlineKeyboardButton(
                    "📄 "
                    + item["name"]
                    + " ⬇️",
                    callback_data=f"file:{item['id']}"
                )
            ])

        parent_id = get_parent_folder(folder_id)

        # Determine a sensible back destination.
        back_callback = "home"

        if parent_id:
            parent_year = find_year_by_id(parent_id)

            if parent_year:
                back_callback = f"year:{parent_id}"

            else:
                parent_name = get_folder_name(parent_id).lower()

                if parent_name in (
                    "lofi",
                    "lofi song",
                    "lofi songs",
                    "lofi music"
                ):
                    back_callback = "cat:lofi"

                else:
                    grandparent = get_parent_folder(parent_id)

                    if grandparent and find_year_by_id(grandparent):
                        back_callback = f"year:{grandparent}"

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

        markup = InlineKeyboardMarkup(keyboard)

        # Full album information when info/poster/songs exist.
        if has_album_info:
            caption = album_caption(album)
        else:
            caption = (
                title_prefix
                + " <b>"
                + html.escape(album["name"])
                + "</b>"
            )

        poster = (
            album["images"][0]
            if album["images"]
            else None
        )

        if poster:
            temp_path = None

            try:
                ext = os.path.splitext(
                    poster["name"]
                )[1]

                temp_path = download_drive_file(
                    poster["id"],
                    ext
                )

                with open(temp_path, "rb") as photo:
                    await chat.send_photo(
                        photo=photo,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=markup
                    )

            except Exception as e:
                print("FOLDER POSTER ERROR:", repr(e))

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

    except Exception as e:
        print("SHOW FOLDER ERROR:", repr(e))

        await chat.send_message(
            "❌ Folder തുറക്കാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(str(e))
        )


# =========================================================
# LOFI
#
# Lofi Songs can be direct MP3s OR sub-folders.
# If sub-folders exist, they are shown.
# =========================================================

def get_lofi_root():
    return find_lofi_folder()


async def show_lofi(
    chat,
    old_message=None
):
    try:
        root = get_lofi_root()

        if old_message:
            try:
                await old_message.delete()
            except Exception:
                pass

        if not root:
            await chat.send_message(
                "🎧 <b>Lofi Songs</b>\n\n"
                "❌ Google Drive-ൽ <b>Lofi Songs</b> "
                "folder കണ്ടെത്തിയില്ല.",
                parse_mode="HTML",
                reply_markup=category_keyboard()
            )
            return

        folders, songs, images, info, other = get_folder_contents(
            root["id"]
        )

        keyboard = []

        # If Lofi has subfolders, show those.
        for folder in folders:
            keyboard.append([
                InlineKeyboardButton(
                    "🎧 " + folder["name"],
                    callback_data=f"folder:{folder['id']}"
                )
            ])

        # Also support direct MP3s in Lofi Songs.
        for song in songs:
            keyboard.append([
                InlineKeyboardButton(
                    "🎧 "
                    + song["name"]
                    + " ⬇️",
                    callback_data=f"file:{song['id']}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="home"
            )
        ])

        await chat.send_message(
            "🎧 <b>Lofi Songs</b>\n\n"
            "🎵 Select a song / folder:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        print("LOFI ERROR:", repr(e))

        await chat.send_message(
            "❌ Lofi Songs load ചെയ്യാൻ കഴിഞ്ഞില്ല.\n\n"
            + html.escape(str(e))
        )


# =========================================================
# LATEST SONGS
# =========================================================

def collect_songs(
    folder_id,
    results,
    visited
):
    if folder_id in visited:
        return

    visited.add(folder_id)

    try:
        for item in get_items(folder_id):
            if is_folder(item):
                collect_songs(
                    item["id"],
                    results,
                    visited
                )
            elif is_song(item):
                results.append(item)

    except Exception as e:
        print("LATEST COLLECT ERROR:", repr(e))


def get_latest_songs():
    results = []
    visited = set()

    collect_songs(
        ROOT_FOLDER_ID,
        results,
        visited
    )

    unique = {}

    for item in results:
        unique[item["id"]] = item

    songs = list(unique.values())

    songs.sort(
        key=lambda x: x.get("modifiedTime", ""),
        reverse=True
    )

    return songs[:200]


async def show_latest(
    chat,
    page=0,
    old_message=None
):
    try:
        songs = get_latest_songs()

        total_pages = max(
            1,
            (len(songs) + SONGS_PER_PAGE - 1)
            // SONGS_PER_PAGE
        )

        page = max(
            0,
            min(page, total_pages - 1)
        )

        start = page * SONGS_PER_PAGE

        page_songs = songs[
            start:start + SONGS_PER_PAGE
        ]

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
        keyboard.append([
            InlineKeyboardButton(
                "🏠 Main Menu",
                callback_data="home"
            )
        ])

        await chat.send_message(
            "🆕 <b>Latest Songs</b>\n\n"
            "പുതിയതായി add ചെയ്ത songs",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        print("LATEST ERROR:", repr(e))

        await chat.send_message(
            "❌ Latest Songs load ചെയ്യാൻ കഴിഞ്ഞില്ല.\n\n"
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
    if folder_id in visited:
        return

    if len(results) >= limit:
        return

    visited.add(folder_id)

    try:
        items = get_items(folder_id)

        needle = search_text.lower().strip()

        for item in items:
            if len(results) >= limit:
                return

            name = item.get("name", "")
            lower = name.lower()

            if is_folder(item):
                if needle in lower:
                    results.append(item)

                search_drive(
                    item["id"],
                    search_text,
                    results,
                    visited,
                    limit
                )

            elif is_song(item):
                if needle in lower:
                    results.append(item)

    except Exception as e:
        print("SEARCH ERROR:", repr(e))


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
            if is_folder(item):
                keyboard.append([
                    InlineKeyboardButton(
                        "📁 " + item["name"],
                        callback_data=f"folder:{item['id']}"
                    )
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton(
                        "🎵 "
                        + item["name"]
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
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        print("PERFORM SEARCH ERROR:", repr(e))

        await message.reply_text(
            "❌ Search failed.\n\n"
            + html.escape(str(e))
        )


async def search_command(update, context):
    context.user_data["search_mode"] = True
    context.user_data["request_mode"] = False

    if context.args:
        text = " ".join(context.args)

        context.user_data["search_mode"] = False

        await perform_search(
            update.message,
            text
        )
        return

    await update.message.reply_text(
        "🔍 <b>Search Songs</b>\n\n"
        "Movie / Song name type ചെയ്ത് അയക്കൂ.\n\n"
        "ഉദാഹരണം: <code>Varnajaalam</code>",
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
        "↩️ <i>ഈ message-ന് Reply ചെയ്താൽ "
        "user-ന് reply പോകും.</i>"
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

        text = (
            update.message.text or ""
        ).strip()

        if text:
            await perform_search(
                update.message,
                text
            )
        else:
            await update.message.reply_text(
                "❌ Search text അയക്കൂ."
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
        user_id_text = (
            original.split(marker, 1)[1]
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

    if category == "albums":
        await show_all_albums(
            query.message.chat,
            0,
            query.message
        )
        return

    if category == "latest":
        await show_latest(
            query.message.chat,
            0,
            query.message
        )
        return

    if category == "years":
        await show_years(
            query.message.chat,
            0,
            query.message
        )
        return

    if category == "lofi":
        await show_lofi(
            query.message.chat,
            query.message
        )
        return

    if category == "search":
        context.user_data["search_mode"] = True
        context.user_data["request_mode"] = False

        await query.message.chat.send_message(
            "🔍 <b>Search Songs</b>\n\n"
            "Movie / Song name type ചെയ്ത് അയക്കൂ.",
            parse_mode="HTML"
        )
        return

    if category == "request":
        context.user_data["request_mode"] = True
        context.user_data["search_mode"] = False

        await query.message.chat.send_message(
            "📩 <b>Song Request</b>\n\n"
            "Movie / Song name type ചെയ്ത് അയക്കൂ.",
            parse_mode="HTML"
        )
        return

    if category == "help":
        await query.message.chat.send_message(
            "🎵 <b>A2Z Malayalam Songs</b>\n\n"
            "💿 Album → എല്ലാ Albums\n"
            "🆕 Latest Songs → പുതിയ Songs\n"
            "📅 Year Wise → Year → Album → Songs\n"
            "🎧 Lofi Songs → Lofi collection\n"
            "🔍 Search Songs → Search\n"
            "📩 Request Song → Admin Request",
            parse_mode="HTML",
            reply_markup=category_keyboard()
        )
        return

    if category == "about":
        await query.message.chat.send_message(
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

    year_id = query.data.split(":", 1)[1]

    await show_year_albums(
        query.message.chat,
        year_id,
        0,
        query.message
    )


async def yearpage_callback(update, context):
    query = update.callback_query
    await query.answer()

    page = int(
        query.data.split(":", 1)[1]
    )

    await show_years(
        query.message.chat,
        page,
        query.message
    )


async def yearalbums_callback(update, context):
    query = update.callback_query
    await query.answer()

    _, year_id, page = query.data.split(":", 2)

    await show_year_albums(
        query.message.chat,
        year_id,
        int(page),
        query.message
    )


# =========================================================
# ALBUM / FOLDER CALLBACKS
# =========================================================

async def album_callback(update, context):
    query = update.callback_query
    await query.answer()

    folder_id = query.data.split(
        ":",
        1
    )[1]

    await show_folder(
        query.message.chat,
        folder_id,
        query.message,
        "💿"
    )


async def folder_callback(update, context):
    query = update.callback_query
    await query.answer()

    folder_id = query.data.split(
        ":",
        1
    )[1]

    await show_folder(
        query.message.chat,
        folder_id,
        query.message,
        "📁"
    )


# =========================================================
# ALL ALBUM PAGINATION
# =========================================================

async def allalbums_callback(update, context):
    query = update.callback_query
    await query.answer()

    page = int(
        query.data.split(":", 1)[1]
    )

    await show_all_albums(
        query.message.chat,
        page,
        query.message
    )


# =========================================================
# LATEST PAGINATION
# =========================================================

async def latestpage_callback(update, context):
    query = update.callback_query
    await query.answer()

    page = int(
        query.data.split(":", 1)[1]
    )

    await show_latest(
        query.message.chat,
        page,
        query.message
    )


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
        info = get_file(file_id)

        file_name = info.get(
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

        with open(temp_path, "rb") as f:
            await query.message.reply_document(
                document=f,
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
# HOME
# =========================================================

async def home_callback(update, context):
    query = update.callback_query
    await query.answer()

    context.user_data["search_mode"] = False
    context.user_data["request_mode"] = False

    await send_categories(
        query.message.chat,
        query.message
    )


# =========================================================
# COMMAND HELP / ABOUT
# =========================================================

async def help_command(update, context):
    await update.message.reply_text(
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


async def about_command(update, context):
    await update.message.reply_text(
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "Malayalam MP3 Songs Collection\n"
        "💿 Albums\n"
        "📅 Year Wise\n"
        "🎧 Lofi Songs\n"
        "🆕 Latest Songs",
        parse_mode="HTML",
        reply_markup=category_keyboard()
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

    app.add_handler(
        CommandHandler(
            "latest",
            lambda update, context: show_latest(
                update.message.chat,
                0
            )
        )
    )

    # Admin reply FIRST
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

    # Albums
    app.add_handler(
        CallbackQueryHandler(
            allalbums_callback,
            pattern=r"^allalbums:\d+$"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            album_callback,
            pattern=r"^album:"
        )
    )

    # Generic subfolders
    app.add_handler(
        CallbackQueryHandler(
            folder_callback,
            pattern=r"^folder:"
        )
    )

    # Latest
    app.add_handler(
        CallbackQueryHandler(
            latestpage_callback,
            pattern=r"^latestpage:\d+$"
        )
    )

    # Download
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
