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
    "info.txt",
    "album-info.txt",
    "album info.txt"
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
            "files("
            "id,"
            "name,"
            "mimeType,"
            "size,"
            "modifiedTime"
            ")"
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

    except Exception as e:

        print(
            "FOLDER NAME ERROR:",
            repr(e)
        )

        return "Album"


# =========================================================
# GET PARENT FOLDER
# =========================================================

def get_folder_parent(folder_id):

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

        # Any numeric folder = Year
        if not name.isdigit():

            continue

        years.append({
            "id": item["id"],
            "name": name,
            "year": int(name)
        })

    # Newest → Oldest
    years.sort(
        key=lambda x: x["year"],
        reverse=True
    )

    return years


# =========================================================
# YEAR KEYBOARD
#
# y:FOLDER_ID:PAGE
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

    if page < 0:

        page = 0

    if page >= total_pages:

        page = total_pages - 1

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
                    f"y:"
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

    # =====================================================
    # PAGINATION
    # =====================================================

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
# SEND YEARS
# =========================================================

async def send_years(
    chat,
    page=0
):

    keyboard = build_year_keyboard(
        page
    )

    await chat.send_message(
        "🎵 <b>A2Z Malayalam Songs</b>\n\n"
        "📂 <b>Select a year:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================================================
# SHOW YEARS FROM CALLBACK
#
# Deletes current message first.
#
# Works for both:
# TEXT MESSAGE
# PHOTO MESSAGE
# =========================================================

async def show_years_from_callback(
    query,
    page=0
):

    try:

        await query.message.delete()

    except Exception as e:

        print(
            "DELETE MESSAGE ERROR:",
            repr(e)
        )

    await send_years(
        query.message.chat,
        page
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

    await send_years(
        update.message.chat,
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
        "👥 Artist Information\n\n"
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

            # FOLDER
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

            # INFO
            if lower_name in INFO_FILES:

                continue

            # IMAGE
            if lower_name.endswith(
                IMAGE_EXTENSIONS
            ):

                continue

            # FILE
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
# PERFORM SEARCH
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
                            f"a:"
                            f"{item['id']}:0"
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
                            f"file:"
                            f"{item['id']}"
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

    # SEARCH
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

    # REQUEST
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

        return


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

    # TEXT
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

    # PHOTO
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
                "❌ Photo അയക്കാൻ കഴിഞ്ഞില്ല.\n\n"
                + html.escape(
                    str(e)
                )
            )

        return

    # DOCUMENT
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
                "❌ File അയക്കാൻ കഴിഞ്ഞില്ല.\n\n"
                + html.escape(
                    str(e)
                )
            )

        return

    await message.reply_text(
        "❌ ഈ തരത്തിലുള്ള reply support ചെയ്യുന്നില്ല."
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
            query.data.split(
                ":",
                1
            )[1]
        )

        await query.edit_message_text(
            "🎵 <b>A2Z Malayalam Songs</b>\n\n"
            "📂 <b>Select a year:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                build_year_keyboard(page)
            )
        )

    except Exception as e:

        print(
            "PAGE ERROR:",
            repr(e)
        )


# =========================================================
# BACK TO YEARS
#
# years:PAGE
#
# This works even when current message is a PHOTO.
# =========================================================

async def years_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        page = int(
            query.data.split(
                ":",
                1
            )[1]
        )

        await show_years_from_callback(
            query,
            page
        )

    except Exception as e:

        print(
            "YEARS BACK ERROR:",
            repr(e)
        )

        await query.message.chat.send_message(
            "❌ Years തുറക്കാൻ കഴിഞ്ഞില്ല."
        )


# =========================================================
# FIND YEAR
# =========================================================

def find_year_by_id(
    folder_id
):

    years = get_year_folders()

    for year in years:

        if year["id"] == folder_id:

            return year

    return None


# =========================================================
# YEAR OPEN
#
# y:FOLDER_ID:PAGE
# =========================================================

async def year_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        parts = query.data.split(
            ":",
            2
        )

        folder_id = parts[1]

        page = int(
            parts[2]
        )

        year = find_year_by_id(
            folder_id
        )

        if not year:

            await query.message.chat.send_message(
                "❌ <b>Year കണ്ടെത്താൻ കഴിഞ്ഞില്ല.</b>",
                parse_mode="HTML"
            )

            return

        await show_year_albums(
            query,
            folder_id,
            year["name"],
            page
        )

    except Exception as e:

        print(
            "YEAR ERROR:",
            repr(e)
        )

        await query.message.chat.send_message(
            "❌ <b>Year തുറക്കാൻ കഴിഞ്ഞില്ല.</b>\n\n"
            + html.escape(
                str(e)
            ),
            parse_mode="HTML"
        )


# =========================================================
# SHOW ALBUM LIST INSIDE YEAR
#
# Year → Album
# =========================================================

async def show_year_albums(
    query,
    folder_id,
    year_name,
    page
):

    try:

        items = get_items(
            folder_id
        )

        albums = []
        songs = []

        for item in items:

            mime = item.get(
                "mimeType"
            )

            name = item.get(
                "name",
                ""
            )

            lower = name.lower()

            # FOLDER = ALBUM
            if mime == FOLDER_MIME:

                albums.append(
                    item
                )

                continue

            # INFO
            if lower in INFO_FILES:

                continue

            # POSTER
            if lower.endswith(
                IMAGE_EXTENSIONS
            ):

                continue

            # DIRECT SONG
            songs.append(
                item
            )

        # SORT ALBUMS
        albums.sort(
            key=lambda x:
            x.get(
                "name",
                ""
            ).lower()
        )

        # SORT SONGS
        songs.sort(
            key=lambda x:
            x.get(
                "name",
                ""
            ).lower()
        )

        keyboard = []

        # =================================================
        # ALBUM BUTTONS
        #
        # a:ALBUM_ID:PAGE
        # =================================================

        for album in albums:

            keyboard.append([
                InlineKeyboardButton(
                    "🎬 "
                    + album["name"],
                    callback_data=(
                        f"a:"
                        f"{album['id']}:"
                        f"{page}"
                    )
                )
            ])

        # =================================================
        # DIRECT SONGS
        # =================================================

        for song in songs:

            keyboard.append([
                InlineKeyboardButton(
                    "🎵 "
                    + song["name"]
                    + " ⬇️",
                    callback_data=(
                        f"file:"
                        f"{song['id']}"
                    )
                )
            ])

        # =================================================
        # BACK TO YEARS
        # =================================================

        keyboard.append([
            InlineKeyboardButton(
                "🔙 Back to Years",
                callback_data=(
                    f"years:{page}"
                )
            )
        ])

        markup = InlineKeyboardMarkup(
            keyboard
        )

        # =================================================
        # IMPORTANT
        #
        # If previous message is a PHOTO,
        # edit_message_text will fail.
        #
        # So DELETE + SEND NEW TEXT.
        # =================================================

        try:

            await query.message.delete()

        except Exception as e:

            print(
                "DELETE YEAR ALBUM MESSAGE:",
                repr(e)
            )

        await query.message.chat.send_message(
            "📅 <b>"
            + html.escape(
                str(year_name)
            )
            + "</b>\n\n"
            "🎬 <b>Select an album:</b>",
            parse_mode="HTML",
            reply_markup=markup
        )

    except Exception as e:

        print(
            "SHOW YEAR ALBUM ERROR:",
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
# ALBUM CALLBACK
#
# a:ALBUM_ID:PAGE
# =========================================================

async def album_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        parts = query.data.split(
            ":",
            2
        )

        folder_id = parts[1]

        page = int(
            parts[2]
        )

        await show_album(
            query,
            folder_id,
            page
        )

    except Exception as e:

        print(
            "ALBUM CALLBACK ERROR:",
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
# SHOW ALBUM
#
# Album → Album Info + Songs
# =========================================================

async def show_album(
    query,
    folder_id,
    page
):

    try:

        items = get_items(
            folder_id
        )

        subfolders = []
        songs = []

        image_file = None
        info_file = None

        # =================================================
        # FIND CONTENT
        # =================================================

        for item in items:

            name = item.get(
                "name",
                ""
            ).strip()

            lower_name = name.lower()

            mime = item.get(
                "mimeType"
            )

            # SUB FOLDER
            if mime == FOLDER_MIME:

                subfolders.append(
                    item
                )

                continue

            # INFO FILE
            if lower_name in INFO_FILES:

                info_file = item

                continue

            # POSTER
            if lower_name.endswith(
                IMAGE_EXTENSIONS
            ):

                if image_file is None:

                    image_file = item

                continue

            # SONG
            songs.append(
                item
            )

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
            folder_id
        )

        # =================================================
        # INFO
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

        # =================================================
        # CAPTION
        # =================================================

        caption = create_album_caption(
            info,
            len(songs)
        )

        # =================================================
        # KEYBOARD
        # =================================================

        keyboard = []

        # =================================================
        # SUB FOLDERS
        # =================================================

        for folder in subfolders:

            keyboard.append([
                InlineKeyboardButton(
                    "📁 "
                    + folder["name"],
                    callback_data=(
                        f"a:"
                        f"{folder['id']}:"
                        f"{page}"
                    )
                )
            ])

        # =================================================
        # SONGS
        # =================================================

        for song in songs:

            keyboard.append([
                InlineKeyboardButton(
                    "🎵 "
                    + song["name"]
                    + " ⬇️",
                    callback_data=(
                        f"file:"
                        f"{song['id']}"
                    )
                )
            ])

        # =================================================
        # IMMEDIATE PARENT
        # =================================================

        parent_id = get_folder_parent(
            folder_id
        )

        # =================================================
        # BACK
        #
        # Album Info + Songs
        #          ↓
        #       2026 Album
        #
        # If nested:
        # Album Info
        #     ↓
        # Parent Album
        # =================================================

        if parent_id:

            keyboard.append([
                InlineKeyboardButton(
                    "🔙 Back",
                    callback_data=(
                        f"p:"
                        f"{parent_id}:"
                        f"{page}"
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
                    "🔙 Back",
                    callback_data=(
                        f"years:{page}"
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

                # Delete old Album List message
                try:

                    await query.message.delete()

                except Exception as e:

                    print(
                        "DELETE ALBUM LIST:",
                        repr(e)
                    )

                # Send poster + info + songs
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

            # No poster
            await query.edit_message_text(
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
# PARENT BACK
#
# p:PARENT_ID:PAGE
#
# Album Info + Songs
#       ↓
# Parent Album / Year
# =========================================================

async def parent_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        parts = query.data.split(
            ":",
            2
        )

        parent_id = parts[1]

        page = int(
            parts[2]
        )

        parent_name = get_folder_name(
            parent_id
        )

        # =================================================
        # PARENT IS YEAR
        #
        # Album Info + Songs
        #        ↓
        # 2026 Album List
        # =================================================

        if parent_name.isdigit():

            await show_year_albums(
                query,
                parent_id,
                parent_name,
                page
            )

            return

        # =================================================
        # PARENT IS ANOTHER ALBUM
        #
        # Sub Album → Parent Album
        # =================================================

        await show_album(
            query,
            parent_id,
            page
        )

    except Exception as e:

        print(
            "PARENT BACK ERROR:",
            repr(e)
        )

        await query.message.chat.send_message(
            "❌ <b>Back തുറക്കാൻ കഴിഞ്ഞില്ല.</b>\n\n"
            + html.escape(
                str(e)
            ),
            parse_mode="HTML"
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

    await show_years_from_callback(
        query,
        0
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
            "INFO ERROR:",
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

        "singer": "",

        "music": "",

        "director": "",

        "artists": "",

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

        elif key in (
            "upload by",
            "uploaded by",
            "uploader"
        ):

            data["upload_by"] = value

    return data


# =========================================================
# ALBUM CAPTION
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
# FILE DOWNLOAD CALLBACK
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

        await query.message.chat.send_message(
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

            results.append(
                item
            )

    except Exception as e:

        print(
            "LATEST ERROR:",
            repr(e)
        )


# =========================================================
# LATEST COMMAND
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
                        f"file:"
                        f"{item['id']}"
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
            filters.REPLY
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
    #
    # y:FOLDER_ID:PAGE
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            year_callback,
            pattern=r"^y:"
        )
    )

    # =====================================================
    # ALBUM
    #
    # a:FOLDER_ID:PAGE
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            album_callback,
            pattern=r"^a:"
        )
    )

    # =====================================================
    # PARENT BACK
    #
    # p:PARENT_ID:PAGE
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            parent_callback,
            pattern=r"^p:"
        )
    )

    # =====================================================
    # BACK TO YEARS
    #
    # years:PAGE
    # =====================================================

    app.add_handler(
        CallbackQueryHandler(
            years_callback,
            pattern=r"^years:"
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
