import os
import tempfile
import json
import html
import time

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

BOT_TOKEN = os.environ["BOT_TOKEN"]
ROOT_FOLDER_ID = os.environ["ROOT_FOLDER_ID"]
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_MIME = "application/vnd.google-apps.folder"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
SONG_EXTENSIONS = (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus")
INFO_FILES = ("info.txt", "album-info.txt", "album info.txt")
YEARS_PER_PAGE = 10
ITEMS_PER_PAGE = 10
SONGS_PER_PAGE = 20
CACHE_TTL = 45
_album_cache = {"time": 0, "data": None}
_latest_cache = {"time": 0, "data": None}
_lofi_cache = {"time": 0, "data": None}

credentials = service_account.Credentials.from_service_account_info(
    json.loads(os.environ["GOOGLE_CREDENTIALS"]), scopes=SCOPES
)
drive = build("drive", "v3", credentials=credentials)


def get_items(folder_id):
    items, token = [], None
    q = f"'{folder_id}' in parents and trashed = false"
    while True:
        r = drive.files().list(
            q=q,
            fields="nextPageToken,files(id,name,mimeType,size,modifiedTime,parents)",
            pageSize=1000,
            pageToken=token,
        ).execute()
        items.extend(r.get("files", []))
        token = r.get("nextPageToken")
        if not token:
            return items


def get_file(file_id):
    return drive.files().get(
        fileId=file_id,
        fields="id,name,mimeType,size,modifiedTime,parents",
    ).execute()


def get_folder_name(folder_id):
    try:
        return get_file(folder_id).get("name", "Folder")
    except Exception:
        return "Folder"


def get_parent_folder(folder_id):
    try:
        p = get_file(folder_id).get("parents", [])
        return p[0] if p else None
    except Exception:
        return None


def is_folder(x):
    return x.get("mimeType") == FOLDER_MIME


def is_image(x):
    return x.get("name", "").lower().endswith(IMAGE_EXTENSIONS)


def is_song(x):
    return (not is_folder(x)) and x.get("name", "").lower().endswith(SONG_EXTENSIONS)


def find_top_folder(names):
    wanted = {n.lower() for n in names}
    for x in get_items(ROOT_FOLDER_ID):
        if is_folder(x) and x.get("name", "").strip().lower() in wanted:
            return x
    return None


def find_year_wise_folder():
    return find_top_folder(["year wise", "yearwise", "years", "year"])


def find_lofi_folder():
    return find_top_folder(["lofi songs", "lofi song", "lofi", "lofi music"])


def get_year_folders():
    root = find_year_wise_folder()
    items = get_items(root["id"]) if root else get_items(ROOT_FOLDER_ID)
    years = []
    for x in items:
        n = x.get("name", "").strip()
        if is_folder(x) and n.isdigit():
            years.append({"id": x["id"], "name": n, "year": int(n)})
    years.sort(key=lambda x: x["year"], reverse=True)
    return years


def find_year_by_id(year_id):
    return next((y for y in get_year_folders() if y["id"] == year_id), None)


def download_drive_file(file_id, suffix=""):
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        req = drive.files().get_media(fileId=file_id)
        dl = MediaIoBaseDownload(f, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
    finally:
        f.close()
    return f.name


def read_info_file(file_id):
    path = None
    try:
        path = download_drive_file(file_id, ".txt")
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        print("INFO ERROR", repr(e))
        return ""
    finally:
        if path and os.path.exists(path):
            os.remove(path)


def parse_info(text, default_album):
    d = {"album": default_album, "year": "", "director": "", "singer": "", "music": "", "artists": "", "label": "", "upload_by": ""}
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip().lower(), v.strip()
        if k in ("album", "album name"): d["album"] = v
        elif k in ("year", "release year"): d["year"] = v
        elif k in ("director", "directed by"): d["director"] = v
        elif k in ("singer", "singers"): d["singer"] = v
        elif k in ("music", "music by", "music director"): d["music"] = v
        elif k in ("artist", "artists", "cast"): d["artists"] = v
        elif k in ("label", "music label"): d["label"] = v
        elif k in ("upload by", "uploaded by", "uploader"): d["upload_by"] = v
    return d


def get_folder_contents(folder_id):
    folders, songs, images, info_file, other = [], [], [], None, []
    for x in get_items(folder_id):
        n = x.get("name", "").strip()
        low = n.lower()
        if is_folder(x): folders.append(x)
        elif low in INFO_FILES: info_file = x
        elif is_image(x): images.append(x)
        elif is_song(x): songs.append(x)
        else: other.append(x)
    folders.sort(key=lambda x: x.get("name", "").lower())
    songs.sort(key=lambda x: x.get("name", "").lower())
    return folders, songs, images, info_file, other


def get_album_data(folder_id):
    folders, songs, images, info_file, other = get_folder_contents(folder_id)
    name = get_folder_name(folder_id)
    info = parse_info(read_info_file(info_file["id"]) if info_file else "", name)
    return {"id": folder_id, "name": name, "folders": folders, "songs": songs, "images": images, "info": info, "other_files": other}


def has_album_content(folder_id):
    _, songs, images, info, _ = get_folder_contents(folder_id)
    return bool(songs or images or info)


def walk_folders(folder_id):
    for x in get_items(folder_id):
        if is_folder(x):
            yield x
            yield from walk_folders(x["id"])


def get_all_album_refs(force=False):
    now = time.time()
    if not force and _album_cache["data"] is not None and now - _album_cache["time"] < CACHE_TTL:
        return _album_cache["data"]

    refs = []
    yw = find_year_wise_folder()
    if yw:
        roots = [x for x in get_items(yw["id"]) if is_folder(x) and x.get("name", "").isdigit()]
    else:
        roots = get_year_folders()

    for year in roots:
        year_id = year["id"]
        for f in walk_folders(year_id):
            if has_album_content(f["id"]):
                refs.append({"id": f["id"], "name": get_folder_name(f["id"])})

    # Also include album-like folders directly under the Lofi category.
    lofi = find_lofi_folder()
    if lofi:
        for f in get_items(lofi["id"]):
            if is_folder(f) and has_album_content(f["id"]):
                refs.append({"id": f["id"], "name": f.get("name", "Album")})

    refs.sort(key=lambda x: x["name"].lower())
    seen = set()
    refs = [r for r in refs if not (r["id"] in seen or seen.add(r["id"]))]
    _album_cache.update({"time": now, "data": refs})
    return refs


def collect_songs(folder_id):
    result = []
    for x in get_items(folder_id):
        if is_song(x):
            result.append(x)
        elif is_folder(x):
            result.extend(collect_songs(x["id"]))
    return result


def get_cached_latest_songs(force=False):
    now = time.time()
    if not force and _latest_cache["data"] is not None and now - _latest_cache["time"] < CACHE_TTL:
        return _latest_cache["data"]
    songs = []
    for y in get_year_folders():
        songs.extend(collect_songs(y["id"]))
    lofi = find_lofi_folder()
    if lofi:
        songs.extend(collect_songs(lofi["id"]))
    seen = set()
    songs = [s for s in songs if not (s["id"] in seen or seen.add(s["id"]))]
    songs.sort(key=lambda x: x.get("modifiedTime", "") or "", reverse=True)
    _latest_cache.update({"time": now, "data": songs})
    return songs


def get_cached_lofi_items(force=False):
    now = time.time()
    if not force and _lofi_cache["data"] is not None and now - _lofi_cache["time"] < CACHE_TTL:
        return _lofi_cache["data"]
    root = find_lofi_folder()
    if not root:
        data = None
    else:
        folders, songs, images, info, other = get_folder_contents(root["id"])
        data = {"root": root, "folders": folders, "songs": songs, "images": images, "info": info, "other": other}
    _lofi_cache.update({"time": now, "data": data})
    return data

def category_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💿 Album", callback_data="cat:albums"), InlineKeyboardButton("🆕 Latest Songs", callback_data="cat:latest")],
        [InlineKeyboardButton("📅 Year Wise", callback_data="cat:years"), InlineKeyboardButton("🎧 Lofi Songs", callback_data="cat:lofi")],
        [InlineKeyboardButton("🔍 Search Songs", callback_data="cat:search"), InlineKeyboardButton("📩 Request Song", callback_data="cat:request")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="cat:help"), InlineKeyboardButton("⚙️ About", callback_data="cat:about")],
    ])


async def send_categories(chat, old_message=None):
    if old_message:
        try: await old_message.delete()
        except Exception: pass
    await chat.send_message("🎵 <b>A2Z Malayalam Songs</b>\n\nMalayalam MP3 Songs Collection\n\n<b>Choose a Category:</b>", parse_mode="HTML", reply_markup=category_keyboard())


async def start(update, context):
    context.user_data.clear()
    await send_categories(update.message.chat)


def album_caption(album):
    i = album["info"]
    t = "🎬 <b>Album</b> : " + html.escape(i["album"])
    for label, key, emoji in [("Year", "year", "📅"), ("Director", "director", "🎬"), ("Singer", "singer", "🎤"), ("Music By", "music", "🎵"), ("Artists", "artists", "👥")]:
        if i[key]: t += f"\n{emoji} <b>{label}</b> : " + html.escape(i[key])
    t += f"\n🎶 <b>Total Tracks</b> : {len(album['songs'])}"
    t += "\n📤 <b>Upload By</b> : " + html.escape(i["upload_by"] or "A2Z Malayalam Songs")
    return t


def album_card_caption(album):
    i = album["info"]
    return f"💿 <b>{html.escape(i['album'])}</b>\n📅 {html.escape(i['year'] or 'N/A')}\n🎶 Tracks : {len(album['songs'])}" + (f"\n🏷️ Label : {html.escape(i['label'])}" if i["label"] else "")


async def show_all_albums(chat, page=0, old_message=None):
    refs = get_all_album_refs()
    total = max(1, (len(refs)+ITEMS_PER_PAGE-1)//ITEMS_PER_PAGE)
    page = max(0, min(page, total-1))
    if old_message:
        try: await old_message.delete()
        except Exception: pass
    buttons = [[InlineKeyboardButton("💿 "+r["name"], callback_data=f"album:{r['id']}")] for r in refs[page*ITEMS_PER_PAGE:(page+1)*ITEMS_PER_PAGE]]
    if not refs:
        buttons = []
    nav=[]
    if page: nav.append(InlineKeyboardButton("⬅️", callback_data=f"allalbums:{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1} / {total}", callback_data="nothing"))
    if page < total-1: nav.append(InlineKeyboardButton("➡️", callback_data=f"allalbums:{page+1}"))
    buttons.append(nav)
    buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="home")])
    await chat.send_message("💿 <b>Malayalam Albums</b>\n\n🎬 <b>Select an album:</b>" if refs else "💿 <b>Malayalam Albums</b>\n\n❌ Album ഒന്നും കണ്ടെത്തിയില്ല.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


def year_keyboard(page=0):
    years=get_year_folders(); total=max(1,(len(years)+YEARS_PER_PAGE-1)//YEARS_PER_PAGE); page=max(0,min(page,total-1))
    part=years[page*YEARS_PER_PAGE:(page+1)*YEARS_PER_PAGE]
    kb=[]; row=[]
    for y in part:
        row.append(InlineKeyboardButton("📁 "+y["name"], callback_data=f"year:{y['id']}"))
        if len(row)==2: kb.append(row); row=[]
    if row: kb.append(row)
    nav=[]
    if page: nav.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"yearpage:{page-1}"))
    if page<total-1: nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"yearpage:{page+1}"))
    if nav: kb.append(nav)
    kb.append([InlineKeyboardButton(f"📄 Page {page+1} / {total}", callback_data="nothing")])
    kb.append([InlineKeyboardButton("🏠 Main Menu", callback_data="home")])
    return InlineKeyboardMarkup(kb)


async def show_years(chat, page=0, old_message=None):
    if old_message:
        try: await old_message.delete()
        except Exception: pass
    await chat.send_message("📅 <b>Year Wise</b>\n\n📂 <b>Select a year:</b>", parse_mode="HTML", reply_markup=year_keyboard(page))


async def show_year_albums(chat, year_id, page=0, old_message=None):
    year=find_year_by_id(year_id)
    if not year:
        await chat.send_message("❌ Year കണ്ടെത്താൻ കഴിഞ്ഞില്ല.", reply_markup=category_keyboard()); return
    albums=[x for x in get_items(year_id) if is_folder(x)]
    albums.sort(key=lambda x:x.get("name","").lower())
    total=max(1,(len(albums)+ITEMS_PER_PAGE-1)//ITEMS_PER_PAGE); page=max(0,min(page,total-1))
    if old_message:
        try: await old_message.delete()
        except Exception: pass
    kb=[[InlineKeyboardButton("💿 "+a["name"], callback_data=f"album:{a['id']}")] for a in albums[page*ITEMS_PER_PAGE:(page+1)*ITEMS_PER_PAGE]]
    nav=[]
    if page: nav.append(InlineKeyboardButton("⬅️",callback_data=f"yearalbums:{year_id}:{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1} / {total}",callback_data="nothing"))
    if page<total-1: nav.append(InlineKeyboardButton("➡️",callback_data=f"yearalbums:{year_id}:{page+1}"))
    if nav: kb.append(nav)
    kb.append([InlineKeyboardButton("⬅️ Back to Years",callback_data="cat:years")])
    kb.append([InlineKeyboardButton("🏠 Main Menu",callback_data="home")])
    await chat.send_message(f"📅 <b>{html.escape(year['name'])}</b>\n\n🎬 <b>Select an album:</b>",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))


async def show_album_or_folder(chat, folder_id, old_message=None):
    data = get_album_data(folder_id)
    if old_message:
        try:
            await old_message.delete()
        except Exception:
            pass

    # A folder that contains child folders is a navigation level.
    # It must NOT be shown as an album info card unless it has no subfolders.
    if data["folders"]:
        kb = [[InlineKeyboardButton("📁 " + f["name"], callback_data=f"folder:{f['id']}")] for f in data["folders"]]
        parent = get_parent_folder(folder_id)
        back = parent_back_callback(parent)
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data=back)])
        kb.append([InlineKeyboardButton("🏠 Main Menu", callback_data="home")])
        await chat.send_message(
            "📁 <b>" + html.escape(data["name"]) + "</b>\n\nSelect a folder:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    await show_folder(chat, folder_id, old_message)


def parent_back_callback(parent):
    if not parent:
        return "home"
    if find_year_by_id(parent):
        return f"year:{parent}"
    p_name = get_folder_name(parent).strip().lower()
    if p_name in {"year wise", "yearwise", "years", "year"}:
        return "cat:years"
    if p_name in {"lofi", "lofi song", "lofi songs", "lofi music"}:
        return "cat:lofi"
    return f"folder:{parent}"


async def show_folder(chat, folder_id, old_message=None):
    data = get_album_data(folder_id)
    if old_message:
        try:
            await old_message.delete()
        except Exception:
            pass

    # If there are child folders, keep this as a navigation page.
    if data["folders"]:
        kb = [[InlineKeyboardButton("📁 " + f["name"], callback_data=f"folder:{f['id']}")] for f in data["folders"]]
        parent = get_parent_folder(folder_id)
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data=parent_back_callback(parent))])
        kb.append([InlineKeyboardButton("🏠 Main Menu", callback_data="home")])
        await chat.send_message(
            "📁 <b>" + html.escape(data["name"]) + "</b>\n\nSelect a folder:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    kb = [[InlineKeyboardButton("🎵 " + s["name"] + " ⬇️", callback_data=f"file:{s['id']}")] for s in data["songs"]]
    for x in data["other_files"]:
        kb.append([InlineKeyboardButton("📄 " + x["name"] + " ⬇️", callback_data=f"file:{x['id']}")])

    parent = get_parent_folder(folder_id)
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data=parent_back_callback(parent))])
    kb.append([InlineKeyboardButton("🏠 Main Menu", callback_data="home")])

    if data["songs"] or data["images"] or data["info"]:
        poster = data["images"][0] if data["images"] else None
        caption = album_caption(data)
        markup = InlineKeyboardMarkup(kb)
        if poster:
            path = None
            try:
                path = download_drive_file(poster["id"], os.path.splitext(poster["name"])[1])
                with open(path, "rb") as f:
                    await chat.send_photo(f, caption=caption, parse_mode="HTML", reply_markup=markup)
            except Exception as e:
                print("POSTER ERROR", repr(e))
                await chat.send_message(caption, parse_mode="HTML", reply_markup=markup)
            finally:
                if path and os.path.exists(path):
                    os.remove(path)
        else:
            await chat.send_message(caption, parse_mode="HTML", reply_markup=markup)
    else:
        await chat.send_message(
            "🎵 <b>" + html.escape(data["name"]) + "</b>\n\n❌ Songs ഒന്നും കണ്ടെത്തിയില്ല.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb)
        )


async def show_lofi(chat, old_message=None):
    data = get_cached_lofi_items()
    if old_message:
        try:
            await old_message.delete()
        except Exception:
            pass
    if not data:
        await chat.send_message(
            "🎧 <b>Lofi Songs</b>\n\n❌ Lofi Songs folder കണ്ടെത്തിയില്ല.",
            parse_mode="HTML",
            reply_markup=category_keyboard()
        )
        return

    # Lofi root can contain album folders. Show album names first.
    if data["folders"]:
        kb = [[InlineKeyboardButton("🎧 " + f["name"], callback_data=f"album:{f['id']}")] for f in data["folders"]]
        kb.append([InlineKeyboardButton("⬅️ Back", callback_data="home")])
        await chat.send_message(
            "🎧 <b>Lofi Songs</b>\n\nSelect an album:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    kb = [[InlineKeyboardButton("🎧 " + s["name"] + " ⬇️", callback_data=f"file:{s['id']}")] for s in data["songs"]]
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="home")])
    await chat.send_message(
        "🎧 <b>Lofi Songs</b>\n\nSelect a song:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def show_latest(chat, page=0, old_message=None):
    songs = get_cached_latest_songs()
    total = max(1, (len(songs) + SONGS_PER_PAGE - 1) // SONGS_PER_PAGE)
    page = max(0, min(page, total - 1))
    if old_message:
        try:
            await old_message.delete()
        except Exception:
            pass
    kb = [[InlineKeyboardButton("🆕 " + s["name"] + " ⬇️", callback_data=f"file:{s['id']}")] for s in songs[page*SONGS_PER_PAGE:(page+1)*SONGS_PER_PAGE]]
    nav = []
    if page:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"latestpage:{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1} / {total}", callback_data="nothing"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"latestpage:{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="home")])
    await chat.send_message(
        "🆕 <b>Latest Songs</b>\n\nപുതിയായി add ചെയ്ത songs:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )


def search_drive(folder_id, text):
    out = []
    q = text.lower().strip()
    for x in get_items(folder_id):
        name = x.get("name", "")
        if q in name.lower():
            out.append(x)
        if is_folder(x):
            out.extend(search_drive(x["id"], text))
    return out


async def perform_search(message, search_text):
    results = search_drive(ROOT_FOLDER_ID, search_text)
    song_results = [x for x in results if is_song(x)]
    folder_results = [x for x in results if is_folder(x)]

    # Exact/partial album match gets album-only results.
    # If no album matches, return song-only results.
    if folder_results:
        kb = [[InlineKeyboardButton("💿 " + f["name"], callback_data=f"album:{f['id']}")] for f in folder_results[:50]]
        title = f"💿 <b>Album Search:</b> {html.escape(search_text)}"
        count_text = f"Found: {len(folder_results)} album(s)"
    else:
        kb = [[InlineKeyboardButton("🎵 " + s["name"] + " ⬇️", callback_data=f"file:{s['id']}")] for s in song_results[:50]]
        title = f"🎵 <b>Song Search:</b> {html.escape(search_text)}"
        count_text = f"Found: {len(song_results)} song(s)"

    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="home")])
    await message.reply_text(
        title + "\n\n" + count_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def search_command(update,context):
    context.user_data["search_mode"]=True; context.user_data["request_mode"]=False
    await update.message.reply_text("🔍 Search Songs\n\nMovie / Song name type ചെയ്യ് അയക്കൂ.")


async def request_command(update,context):
    context.user_data["request_mode"]=True; context.user_data["search_mode"]=False
    await update.message.reply_text("📩 Request Song\n\nഏത് song / album വേണമെന്ന് type ചെയ്യൂ.")


async def send_request_to_admin(update,context,text):
    """Send a song/album request to admin with complete user details.

    The User ID is intentionally kept in a simple, parseable form because
    admin_reply_handler uses it when the admin replies to this message.
    """
    if not ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Admin chat ID set ചെയ്തിട്ടില്ല.")
        return

    user = update.effective_user
    name = html.escape(user.full_name or "N/A")
    username = html.escape(
        f"@{user.username}" if user.username else "N/A"
    )
    request_text = html.escape(text)

    admin_text = (
        "📩 <b>NEW SONG REQUEST</b>\n\n"
        f"👤 <b>User:</b> {name}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"🆔 <b>User ID:</b> {user.id}\n\n"
        f"🎬 <b>Request:</b>\n"
        f"{request_text}\n\n"
        "↩️ ഈ message-ന് Reply ചെയ്താൽ user-ന് reply പോകും."
    )

    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text=admin_text,
        parse_mode="HTML"
    )

    context.user_data["request_mode"] = False
    await update.message.reply_text("✅ Request admin-ന് അയച്ചു.")


async def text_message_handler(update,context):
    if not update.message or not update.message.text: return
    text=update.message.text.strip()
    if context.user_data.get("search_mode"):
        context.user_data["search_mode"]=False; await perform_search(update.message,text)
    elif context.user_data.get("request_mode"):
        await send_request_to_admin(update,context,text)


async def admin_reply_handler(update,context):
    if not update.message.reply_to_message: return
    original=update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
    marker="User ID:"
    if marker not in original: return
    try: uid=int(original.split(marker,1)[1].split()[0])
    except Exception: return
    try: await context.bot.send_message(uid,"📩 <b>Admin Reply</b>\n\n"+html.escape(update.message.text or ""),parse_mode="HTML")
    except Exception as e: print("ADMIN REPLY ERROR",repr(e))


async def category_callback(update,context):
    q=update.callback_query; await q.answer(); cat=q.data.split(":",1)[1]
    context.user_data["search_mode"]=False; context.user_data["request_mode"]=False
    if cat=="albums": await show_all_albums(q.message.chat,0,q.message)
    elif cat=="latest": await show_latest(q.message.chat,0,q.message)
    elif cat=="years": await show_years(q.message.chat,0,q.message)
    elif cat=="lofi": await show_lofi(q.message.chat,q.message)
    elif cat=="search": await search_command_from_callback(q,context)
    elif cat=="request": await request_callback(q,context)
    elif cat=="help": await send_help(q.message.chat,q.message)
    elif cat=="about": await send_about(q.message.chat,q.message)


async def search_command_from_callback(q,context):
    context.user_data["search_mode"]=True
    await q.message.chat.send_message("🔍 Search Songs\n\nMovie / Song name type ചെയ്യ് അയക്കൂ.")


async def request_callback(q,context):
    context.user_data["request_mode"]=True
    await q.message.chat.send_message("📩 Request Song\n\nഏത് song / album വേണമെന്ന് type ചെയ്യൂ.")


async def send_help(chat,old_message=None):
    if old_message:
        try: await old_message.delete()
        except Exception: pass
    await chat.send_message("🎵 <b>A2Z Malayalam Songs</b>\n\n💿 Album\n🆕 Latest Songs\n📅 Year Wise\n🎧 Lofi Songs\n🔍 Search Songs\n📩 Request Song",parse_mode="HTML",reply_markup=category_keyboard())


async def send_about(chat,old_message=None):
    if old_message:
        try: await old_message.delete()
        except Exception: pass
    await chat.send_message("🎵 <b>A2Z Malayalam Songs</b>\n\nMalayalam MP3 Songs Collection\n\nPowered by A2Z Malayalam Songs",parse_mode="HTML",reply_markup=category_keyboard())


async def year_callback(update,context):
    q=update.callback_query; await q.answer(); await show_year_albums(q.message.chat,q.data.split(":",1)[1],0,q.message)

async def yearpage_callback(update,context):
    q=update.callback_query; await q.answer(); await show_years(q.message.chat,int(q.data.split(":",1)[1]),q.message)

async def yearalbums_callback(update,context):
    q=update.callback_query; await q.answer(); _,y,p=q.data.split(":",2); await show_year_albums(q.message.chat,y,int(p),q.message)

async def album_callback(update,context):
    q=update.callback_query; await q.answer(); await show_album_or_folder(q.message.chat,q.data.split(":",1)[1],q.message)

async def folder_callback(update,context):
    q=update.callback_query; await q.answer(); await show_album_or_folder(q.message.chat,q.data.split(":",1)[1],q.message)

async def allalbums_callback(update,context):
    q=update.callback_query; await q.answer(); await show_all_albums(q.message.chat,int(q.data.split(":",1)[1]),q.message)

async def latestpage_callback(update,context):
    q=update.callback_query; await q.answer(); await show_latest(q.message.chat,int(q.data.split(":",1)[1]),q.message)

async def back_callback(update,context):
    q=update.callback_query; await q.answer(); target=q.data.split(":",1)[1]; await show_folder(q.message.chat,target,q.message)

async def file_callback(update,context):
    q=update.callback_query; await q.answer("⏳ Downloading...")
    fid=q.data.split(":",1)[1]; path=None
    try:
        info=get_file(fid); name=info.get("name","download"); path=download_drive_file(fid,os.path.splitext(name)[1])
        with open(path,"rb") as f: await q.message.reply_document(document=f,filename=name,caption="🎵 "+name)
    except Exception as e: await q.message.chat.send_message("❌ Download failed\n"+html.escape(str(e)))
    finally:
        if path and os.path.exists(path): os.remove(path)

async def home_callback(update,context):
    q=update.callback_query; await q.answer(); context.user_data.clear(); await send_categories(q.message.chat,q.message)

async def help_command(update,context): await send_help(update.message.chat)
async def about_command(update,context): await send_about(update.message.chat)
async def nothing_callback(update,context): await update.callback_query.answer()


def main():
    app=Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("help",help_command))
    app.add_handler(CommandHandler("about",about_command))
    app.add_handler(CommandHandler("search",search_command))
    app.add_handler(CommandHandler("request",request_command))
    app.add_handler(CommandHandler("latest",lambda u,c: show_latest(u.message.chat,0)))
    if ADMIN_CHAT_ID:
        app.add_handler(MessageHandler(filters.Chat(chat_id=ADMIN_CHAT_ID)&filters.REPLY&~filters.COMMAND,admin_reply_handler))
    app.add_handler(MessageHandler(filters.TEXT&~filters.COMMAND,text_message_handler))
    app.add_handler(CallbackQueryHandler(category_callback,pattern=r"^cat:"))
    app.add_handler(CallbackQueryHandler(yearpage_callback,pattern=r"^yearpage:\d+$"))
    app.add_handler(CallbackQueryHandler(year_callback,pattern=r"^year:"))
    app.add_handler(CallbackQueryHandler(yearalbums_callback,pattern=r"^yearalbums:"))
    app.add_handler(CallbackQueryHandler(allalbums_callback,pattern=r"^allalbums:\d+$"))
    app.add_handler(CallbackQueryHandler(album_callback,pattern=r"^album:"))
    app.add_handler(CallbackQueryHandler(folder_callback,pattern=r"^folder:"))
    app.add_handler(CallbackQueryHandler(latestpage_callback,pattern=r"^latestpage:\d+$"))
    app.add_handler(CallbackQueryHandler(file_callback,pattern=r"^file:"))
    app.add_handler(CallbackQueryHandler(home_callback,pattern=r"^home$"))
    app.add_handler(CallbackQueryHandler(back_callback,pattern=r"^back:"))
    app.add_handler(CallbackQueryHandler(nothing_callback,pattern=r"^nothing$"))
    print("A2Z Malayalam Songs Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__": main()
