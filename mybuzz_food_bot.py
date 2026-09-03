import os
import re
import json
import hashlib
import requests
from datetime import datetime, timezone
from openai import OpenAI


# ============================================================
# CONFIG
# ============================================================

GOOGLE_PLACES_BASE_URL = "https://places.googleapis.com/v1"

OPENAI_MODEL = "gpt-5.6-luna"

REQUEST_TIMEOUT = 20

MAX_SEARCH_RESULTS = 10
MAX_POSTED = 1000

AI_MAX_COMPLETION_TOKENS = 1200
AI_REASONING_EFFORT = "low"

TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_TEXT_LIMIT = 4000

POSTED_FILE = "posted.json"
STATE_FILE = "bot_state.json"


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

GOOGLE_MAPS_API_KEY = os.getenv(
    "GOOGLE_MAPS_API_KEY",
    ""
).strip()

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    ""
).strip()

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    ""
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    ""
).strip()


# ============================================================
# OPENAI
# ============================================================

openai_client = None

if OPENAI_API_KEY:
    openai_client = OpenAI(
        api_key=OPENAI_API_KEY,
        max_retries=0
    )


# ============================================================
# SEARCH LOCATIONS
# ============================================================

SEARCH_LOCATIONS = [
    "Kuala Lumpur, Malaysia",
    "Petaling Jaya, Selangor, Malaysia",
    "Subang Jaya, Selangor, Malaysia",
    "Shah Alam, Selangor, Malaysia",
    "Johor Bahru, Johor, Malaysia",
    "Penang, Malaysia",
    "Melaka, Malaysia",
    "Ipoh, Perak, Malaysia"
]


# ============================================================
# SEARCH QUERIES
# ============================================================

FOOD_QUERIES = [
    "popular restaurant",
    "popular cafe",
    "local food",
    "hidden gem restaurant",
    "popular breakfast",
    "popular dinner",
    "popular dessert",
    "new cafe",
    "trending restaurant",
    "popular food"
]


# ============================================================
# HELPERS
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = str(text)
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0):
    try:
        return float(value)
    except Exception:
        return default


def hash_text(text):
    return hashlib.sha256(
        clean_text(text).encode("utf-8")
    ).hexdigest()


# ============================================================
# POSTED
# ============================================================

def load_posted():
    if not os.path.exists(POSTED_FILE):
        return []

    try:
        with open(
            POSTED_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            return data.get(
                "posted",
                []
            )

    except Exception as e:
        print(
            f"WARNING failed to load posted.json: {e}"
        )

    return []


def save_posted(posted):
    posted = posted[-MAX_POSTED:]

    try:
        with open(
            POSTED_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                posted,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:
        print(
            f"ERROR saving posted.json: {e}"
        )


# ============================================================
# STATE
# ============================================================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "run_count": 0
        }

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

    except Exception as e:
        print(
            f"WARNING failed to load bot_state.json: {e}"
        )

    return {
        "run_count": 0
    }


def save_state(state):
    try:
        with open(
            STATE_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                state,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:
        print(
            f"WARNING failed to save bot_state.json: {e}"
        )


def increase_run_counter():
    state = load_state()

    state["run_count"] = safe_int(
        state.get(
            "run_count",
            0
        )
    ) + 1

    state["last_run"] = datetime.now(
        timezone.utc
    ).isoformat()

    save_state(state)

    return state["run_count"]


# ============================================================
# CONFIG CHECK
# ============================================================

def check_config():
    missing = []

    if not GOOGLE_MAPS_API_KEY:
        missing.append(
            "GOOGLE_MAPS_API_KEY"
        )

    if not OPENAI_API_KEY:
        missing.append(
            "OPENAI_API_KEY"
        )

    if not TELEGRAM_BOT_TOKEN:
        missing.append(
            "TELEGRAM_BOT_TOKEN"
        )

    if not TELEGRAM_CHAT_ID:
        missing.append(
            "TELEGRAM_CHAT_ID"
        )

    if missing:
        print(
            "ERROR Missing environment variables:"
        )

        for item in missing:
            print(
                f"- {item}"
            )

        return False

    return True


# ============================================================
# GOOGLE PLACES SEARCH
# ============================================================

def search_places(
    query,
    location
):
    url = (
        f"{GOOGLE_PLACES_BASE_URL}"
        "/places:searchText"
    )

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,

        "X-Goog-FieldMask": (
            "places.id,"
            "places.displayName,"
            "places.formattedAddress,"
            "places.googleMapsUri,"
            "places.primaryType,"
            "places.primaryTypeDisplayName,"
            "places.photos,"
            "places.rating,"
            "places.userRatingCount,"
            "places.priceLevel,"
            "places.regularOpeningHours"
        )
    }

    payload = {
        "textQuery": (
            f"{query} in {location}"
        ),
        "languageCode": "en",
        "regionCode": "MY",
        "pageSize": MAX_SEARCH_RESULTS
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"Google Places HTTP "
            f"{response.status_code}"
        )

        if response.status_code != 200:
            print(
                "Google Places error:"
            )

            print(
                response.text[:3000]
            )

            return []

        data = response.json()

        places = data.get(
            "places",
            []
        )

        print(
            f"Google Places returned "
            f"{len(places)} places"
        )

        return places

    except Exception as e:
        print(
            f"ERROR Google Places request failed: {e}"
        )

        return []


# ============================================================
# GOOGLE PHOTO DOWNLOAD
# ============================================================

def download_google_photo(
    photo_name
):
    if not photo_name:
        return None

    url = (
        f"{GOOGLE_PLACES_BASE_URL}/"
        f"{photo_name}/media"
    )

    params = {
        "key": GOOGLE_MAPS_API_KEY,
        "maxWidthPx": 1200,
        "maxHeightPx": 900
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True
        )

        print(
            f"Google Photo HTTP "
            f"{response.status_code}"
        )

        if response.status_code != 200:
            print(
                "Google Photo error:"
            )

            print(
                response.text[:1000]
            )

            return None

        content_type = (
            response.headers
            .get(
                "Content-Type",
                ""
            )
            .lower()
        )

        if not content_type.startswith(
            "image/"
        ):
            print(
                "WARNING Google Photo did not "
                "return an image."
            )

            print(
                f"Content-Type: {content_type}"
            )

            return None

        print(
            f"Photo downloaded: "
            f"{len(response.content)} bytes"
        )

        return response.content

    except Exception as e:
        print(
            f"ERROR Google Photo download failed: {e}"
        )

        return None


# ============================================================
# EXTRACT PHOTO
# ============================================================

def extract_photo_bytes(place):
    photos = place.get(
        "photos",
        []
    )

    if not photos:
        print(
            "No Google Photos found."
        )

        return None

    first_photo = photos[0]

    photo_name = first_photo.get(
        "name",
        ""
    )

    if not photo_name:
        print(
            "Google photo name missing."
        )

        return None

    print(
        f"Google photo: {photo_name}"
    )

    return download_google_photo(
        photo_name
    )


# ============================================================
# OPENING HOURS
# ============================================================

def extract_opening_hours(place):
    opening = place.get(
        "regularOpeningHours",
        {}
    )

    if not isinstance(
        opening,
        dict
    ):
        return []

    descriptions = opening.get(
        "weekdayDescriptions",
        []
    )

    if not isinstance(
        descriptions,
        list
    ):
        return []

    return [
        clean_text(item)
        for item in descriptions
        if clean_text(item)
    ]


# ============================================================
# FORMAT OPENING HOURS
# ============================================================

def format_opening_hours(
    hours
):
    if not hours:
        return (
            "暂无资料 / "
            "Maklumat tidak tersedia"
        )

    day_map = {
        "Monday": "星期一 / Isnin",
        "Tuesday": "星期二 / Selasa",
        "Wednesday": "星期三 / Rabu",
        "Thursday": "星期四 / Khamis",
        "Friday": "星期五 / Jumaat",
        "Saturday": "星期六 / Sabtu",
        "Sunday": "星期日 / Ahad"
    }

    result = []

    for item in hours:
        item = clean_text(item)

        if not item:
            continue

        parts = item.split(
            ":",
            1
        )

        if len(parts) != 2:
            continue

        day = parts[0].strip()
        time_text = parts[1].strip()

        day_name = day_map.get(
            day,
            day
        )

        result.append(
            f"{day_name}: {time_text}"
        )

    if not result:
        return (
            "暂无资料 / "
            "Maklumat tidak tersedia"
        )

    return "\n".join(
        result
    )


# ============================================================
# PRICE
# ============================================================

def price_level_text(
    price_level
):
    mapping = {
        "PRICE_LEVEL_FREE": "Free",
        "PRICE_LEVEL_INEXPENSIVE": "RM10–20",
        "PRICE_LEVEL_MODERATE": "RM20–50",
        "PRICE_LEVEL_EXPENSIVE": "RM50–100",
        "PRICE_LEVEL_VERY_EXPENSIVE": "RM100+"
    }

    return mapping.get(
        price_level,
        "暂无资料"
    )


# ============================================================
# PLACE ID
# ============================================================

def get_place_id(place):
    value = clean_text(
        place.get(
            "id",
            ""
        )
    )

    if value:
        return value

    display_name = (
        place.get(
            "displayName",
            {}
        )
        or {}
    )

    name = clean_text(
        display_name.get(
            "text",
            ""
        )
    )

    address = clean_text(
        place.get(
            "formattedAddress",
            ""
        )
    )

    return hash_text(
        name + address
    )


# ============================================================
# SELECT PLACE
# ============================================================

def select_place(
    places,
    posted
):
    posted_set = set(
        posted
    )

    candidates = []

    for place in places:

        pid = get_place_id(
            place
        )

        if pid in posted_set:
            print(
                "Skipping already posted place."
            )

            continue

        display_name = (
            place.get(
                "displayName",
                {}
            )
            or {}
        )

        name = clean_text(
            display_name.get(
                "text",
                ""
            )
        )

        address = clean_text(
            place.get(
                "formattedAddress",
                ""
            )
        )

        rating = safe_float(
            place.get(
                "rating",
                0
            )
        )

        review_count = safe_int(
            place.get(
                "userRatingCount",
                0
            )
        )

        photos = place.get(
            "photos",
            []
        )

        if not name:
            continue

        if not address:
            continue

        if not photos:
            print(
                f"Skipping without photo: "
                f"{name}"
            )

            continue

        if rating < 4.0:
            print(
                f"Skipping low rating: "
                f"{name} ({rating})"
            )

            continue

        if review_count < 20:
            print(
                f"Skipping low review count: "
                f"{name} ({review_count})"
            )

            continue

        score = (
            rating * 100
            + min(
                review_count,
                5000
            ) / 100
        )

        candidates.append(
            (
                score,
                place
            )
        )

    if not candidates:
        print(
            "No suitable food place found."
        )

        return None

    candidates.sort(
        key=lambda item: item[0],
        reverse=True
    )

    selected = candidates[0][1]

    name = clean_text(
        (
            selected.get(
                "displayName",
                {}
            )
            or {}
        ).get(
            "text",
            ""
        )
    )

    print(
        f"Selected restaurant: {name}"
    )

    return selected


# ============================================================
# FOOD DATA
# ============================================================

def build_food_data(
    place
):
    display_name = (
        place.get(
            "displayName",
            {}
        )
        or {}
    )

    name = clean_text(
        display_name.get(
            "text",
            ""
        )
    )

    address = clean_text(
        place.get(
            "formattedAddress",
            ""
        )
    )

    rating = safe_float(
        place.get(
            "rating",
            0
        )
    )

    review_count = safe_int(
        place.get(
            "userRatingCount",
            0
        )
    )

    price_level = clean_text(
        place.get(
            "priceLevel",
            ""
        )
    )

    primary_type_display = (
        place.get(
            "primaryTypeDisplayName",
            {}
        )
        or {}
    )

    category = clean_text(
        primary_type_display.get(
            "text",
            ""
        )
    )

    maps_url = clean_text(
        place.get(
            "googleMapsUri",
            ""
        )
    )

    opening_hours = (
        extract_opening_hours(
            place
        )
    )

    photo_bytes = (
        extract_photo_bytes(
            place
        )
    )

    return {
        "id": get_place_id(place),
        "name": name,
        "address": address,
        "rating": rating,
        "review_count": review_count,
        "price_level": price_level_text(
            price_level
        ),
        "category": category,
        "maps_url": maps_url,
        "opening_hours": opening_hours,
        "photo_bytes": photo_bytes
    }


# ============================================================
# AI PROMPT
# ============================================================

def build_food_prompt(
    food
):
    return f"""
You are a professional Malaysian food editor.

Create a bilingual Malaysian food recommendation for Telegram.

FACTS:

Restaurant:
{food["name"]}

Address:
{food["address"]}

Category:
{food["category"]}

Google Rating:
{food["rating"]}/5

Google Review Count:
{food["review_count"]}

Price:
{food["price_level"]}

IMPORTANT RULES:

1. Never invent facts.
2. Never invent menu items.
3. Never invent signature dishes.
4. Never invent prices.
5. Never invent opening hours.
6. Never invent awards.
7. Never claim a restaurant is viral or trending unless supplied data proves it.
8. Never change the restaurant name.
9. Never change the rating.
10. Never change the review count.
11. Never change the address.
12. Chinese and Malay must describe the same facts.
13. Use Malaysian Chinese.
14. Use Malaysian Malay, NOT Indonesian Malay.
15. Keep the writing concise and natural.
16. The "why recommended" section must only use factual information.
17. If there is not enough information to recommend specific dishes, return an empty must_try list.

Create:

- Chinese title
- Malay title
- Chinese introduction
- Malay introduction
- Chinese why recommended
- Malay why recommended
- must_try list

The must_try list should only contain dishes if they can be safely inferred from reliable information supplied in the prompt.

Return ONLY valid JSON.

FORMAT:

{{
    "chinese_title": "",
    "malay_title": "",
    "chinese_body": "",
    "malay_body": "",
    "chinese_why": "",
    "malay_why": "",
    "must_try": []
}}
""".strip()


# ============================================================
# JSON EXTRACTION
# ============================================================

def extract_json(
    text
):
    if not text:
        return None

    text = text.strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    try:
        return json.loads(
            text
        )

    except Exception:
        pass

    start = text.find(
        "{"
    )

    end = text.rfind(
        "}"
    )

    if (
        start == -1
        or end == -1
        or end <= start
    ):
        return None

    try:
        return json.loads(
            text[start:end + 1]
        )

    except Exception as e:
        print(
            f"ERROR JSON extraction failed: {e}"
        )

        return None


# ============================================================
# VALIDATE AI
# ============================================================

def validate_ai(
    data
):
    if not isinstance(
        data,
        dict
    ):
        return False

    required = [
        "chinese_title",
        "malay_title",
        "chinese_body",
        "malay_body",
        "chinese_why",
        "malay_why"
    ]

    for key in required:
        value = clean_text(
            data.get(
                key,
                ""
            )
        )

        if not value:
            print(
                f"ERROR Missing AI field: "
                f"{key}"
            )

            return False

    must_try = data.get(
        "must_try",
        []
    )

    if not isinstance(
        must_try,
        list
    ):
        return False

    return True


# ============================================================
# OPENAI
# ============================================================

def generate_ai_content(
    food
):
    if openai_client is None:
        print(
            "ERROR OpenAI client not initialized."
        )

        return None

    prompt = build_food_prompt(
        food
    )

    try:
        response = (
            openai_client
            .chat
            .completions
            .create(
                model=OPENAI_MODEL,

                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],

                max_completion_tokens=(
                    AI_MAX_COMPLETION_TOKENS
                ),

                reasoning_effort=(
                    AI_REASONING_EFFORT
                ),

                response_format={
                    "type": "json_object"
                }
            )
        )

        choice = response.choices[0]

        finish_reason = getattr(
            choice,
            "finish_reason",
            None
        )

        print(
            f"OpenAI finish reason: "
            f"{finish_reason}"
        )

        content = ""

        if choice.message:
            content = (
                choice.message.content
                or ""
            )

        if not content:
            print(
                "ERROR OpenAI returned empty content."
            )

            return None

        if finish_reason in (
            "length",
            "max_tokens"
        ):
            print(
                "ERROR OpenAI output incomplete."
            )

            return None

        data = extract_json(
            content
        )

        if not data:
            print(
                "ERROR Invalid AI JSON."
            )

            return None

        if not validate_ai(
            data
        ):
            print(
                "ERROR AI validation failed."
            )

            return None

        print(
            "AI generation successful."
        )

        return data

    except Exception as e:
        print(
            f"ERROR OpenAI request failed: {e}"
        )

        return None


# ============================================================
# TELEGRAM URL
# ============================================================

def telegram_api_url(
    method
):
    return (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/"
        f"{method}"
    )


# ============================================================
# TELEGRAM PHOTO
# ============================================================

def send_telegram_photo(
    photo_bytes,
    caption,
    maps_url
):
    url = telegram_api_url(
        "sendPhoto"
    )

    caption = caption[
        :TELEGRAM_CAPTION_LIMIT
    ]

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": caption,
        "parse_mode": "HTML"
    }

    if maps_url:
        data["reply_markup"] = json.dumps({
            "inline_keyboard": [
                [
                    {
                        "text": "👉 Google Maps",
                        "url": maps_url
                    }
                ]
            ]
        })

    files = {
        "photo": (
            "restaurant.jpg",
            photo_bytes,
            "image/jpeg"
        )
    }

    try:
        response = requests.post(
            url,
            data=data,
            files=files,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"Telegram photo HTTP "
            f"{response.status_code}"
        )

        if response.status_code != 200:
            print(
                "Telegram photo error:"
            )

            print(
                response.text[:2000]
            )

            return False

        result = response.json()

        return bool(
            result.get("ok")
        )

    except Exception as e:
        print(
            f"ERROR Telegram photo failed: {e}"
        )

        return False


# ============================================================
# TELEGRAM TEXT
# ============================================================

def send_telegram_text(
    text,
    maps_url
):
    url = telegram_api_url(
        "sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text[
            :TELEGRAM_TEXT_LIMIT
        ],
        "parse_mode": "HTML"
    }

    if maps_url:
        data["reply_markup"] = json.dumps({
            "inline_keyboard": [
                [
                    {
                        "text": "👉 Google Maps",
                        "url": maps_url
                    }
                ]
            ]
        })

    try:
        response = requests.post(
            url,
            data=data,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"Telegram text HTTP "
            f"{response.status_code}"
        )

        if response.status_code != 200:
            print(
                response.text[:2000]
            )

            return False

        return bool(
            response.json().get("ok")
        )

    except Exception as e:
        print(
            f"ERROR Telegram text failed: {e}"
        )

        return False


# ============================================================
# CHINESE MESSAGE
# ============================================================

def build_chinese_message(
    food,
    ai
):
    hours_text = format_opening_hours(
        food.get(
            "opening_hours",
            []
        )
    )

    must_try = ai.get(
        "must_try",
        []
    )

    if not isinstance(
        must_try,
        list
    ):
        must_try = []

    must_try = [
        clean_text(item)
        for item in must_try
        if clean_text(item)
    ][:4]

    if must_try:
        must_try_text = "\n".join(
            f"• {item}"
            for item in must_try
        )
    else:
        must_try_text = (
            "• 暂无足够资料提供具体推荐"
        )

    return (
        "🇲🇾 <b>MYBUZZ FOOD</b>\n\n"

        "🔥 <b>今日美食推荐</b>\n\n"

        f"🍽️ <b>{food['name']}</b>\n\n"

        f"⭐ Rating: "
        f"{food['rating']:.1f}/5\n"

        f"💬 Reviews: "
        f"{food['review_count']:,}\n"

        f"💰 人均："
        f"{food['price_level']}\n"

        f"📍 {food['address']}\n\n"

        "🍴 <b>推荐必点</b>\n"
        f"{must_try_text}\n\n"

        "🔥 <b>为什么推荐？</b>\n\n"

        f"{clean_text(ai['chinese_why'])}\n\n"

        "🇨🇳 <b>中文介绍</b>\n\n"

        f"{clean_text(ai['chinese_body'])}\n\n"

        "🕐 <b>营业时间</b>\n"

        f"{hours_text}"
    )


# ============================================================
# MALAY MESSAGE
# ============================================================

def build_malay_message(
    food,
    ai
):
    hours_text = format_opening_hours(
        food.get(
            "opening_hours",
            []
        )
    )

    must_try = ai.get(
        "must_try",
        []
    )

    if not isinstance(
        must_try,
        list
    ):
        must_try = []

    must_try = [
        clean_text(item)
        for item in must_try
        if clean_text(item)
    ][:4]

    if must_try:
        must_try_text = "\n".join(
            f"• {item}"
            for item in must_try
        )
    else:
        must_try_text = (
            "• Tiada maklumat mencukupi"
        )

    return (
        "🇲🇾 <b>MYBUZZ FOOD</b>\n\n"

        "🔥 <b>Cadangan Makanan Hari Ini</b>\n\n"

        f"🍽️ <b>{food['name']}</b>\n\n"

        f"⭐ Rating: "
        f"{food['rating']:.1f}/5\n"

        f"💬 Reviews: "
        f"{food['review_count']:,}\n"

        f"💰 Harga: "
        f"{food['price_level']}\n"

        f"📍 {food['address']}\n\n"

        "🍴 <b>Wajib Cuba</b>\n"
        f"{must_try_text}\n\n"

        "🔥 <b>Mengapa Disyorkan?</b>\n\n"

        f"{clean_text(ai['malay_why'])}\n\n"

        "🇲🇾 <b>Bahasa Melayu</b>\n\n"

        f"{clean_text(ai['malay_body'])}\n\n"

        "🕐 <b>Waktu Operasi</b>\n"

        f"{hours_text}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("MYBUZZ FOOD BOT")
    print("=" * 60)

    run_count = increase_run_counter()

    print(
        f"Run #{run_count}"
    )

    if not check_config():
        return

    posted = load_posted()

    print(
        f"Posted database: "
        f"{len(posted)} records"
    )

    # --------------------------------------------------------
    # SEARCH ROTATION
    # --------------------------------------------------------

    location_index = (
        (run_count - 1)
        % len(SEARCH_LOCATIONS)
    )

    query_index = (
        (run_count - 1)
        % len(FOOD_QUERIES)
    )

    location = SEARCH_LOCATIONS[
        location_index
    ]

    query = FOOD_QUERIES[
        query_index
    ]

    print(
        f"Food search: {query}"
    )

    print(
        f"Location: {location}"
    )

    # --------------------------------------------------------
    # SEARCH GOOGLE
    # --------------------------------------------------------

    places = search_places(
        query,
        location
    )

    if not places:
        print(
            "No places returned."
        )

        return

    # --------------------------------------------------------
    # SELECT
    # --------------------------------------------------------

    place = select_place(
        places,
        posted
    )

    if not place:
        return

    # --------------------------------------------------------
    # BUILD DATA
    # --------------------------------------------------------

    food = build_food_data(
        place
    )

    print(
        f"Restaurant: "
        f"{food['name']}"
    )

    print(
        f"Rating: "
        f"{food['rating']}"
    )

    print(
        f"Reviews: "
        f"{food['review_count']}"
    )

    print(
        f"Price: "
        f"{food['price_level']}"
    )

    print(
        f"Address: "
        f"{food['address']}"
    )

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

    photo_bytes = food.get(
        "photo_bytes"
    )

    if not photo_bytes:
        print(
            "ERROR No usable restaurant photo."
        )

        return

    # --------------------------------------------------------
    # AI
    # --------------------------------------------------------

    ai = generate_ai_content(
        food
    )

    if not ai:
        print(
            "AI failed."
        )

        return

    # --------------------------------------------------------
    # CHINESE
    # --------------------------------------------------------

    chinese_message = (
        build_chinese_message(
            food,
            ai
        )
    )

    print(
        f"Chinese message length: "
        f"{len(chinese_message)}"
    )

    sent_chinese = send_telegram_photo(
        photo_bytes,
        chinese_message,
        food["maps_url"]
    )

    if not sent_chinese:
        print(
            "ERROR Chinese message failed."
        )

        return

    print(
        "Chinese message sent."
    )

    # --------------------------------------------------------
    # MALAY
    # --------------------------------------------------------

    malay_message = (
        build_malay_message(
            food,
            ai
        )
    )

    print(
        f"Malay message length: "
        f"{len(malay_message)}"
    )

    sent_malay = send_telegram_text(
        malay_message,
        food["maps_url"]
    )

    if not sent_malay:
        print(
            "ERROR Malay message failed."
        )

        return

    print(
        "Malay message sent."
    )

    # --------------------------------------------------------
    # SAVE POSTED
    # --------------------------------------------------------

    posted.append(
        food["id"]
    )

    save_posted(
        posted
    )

    print(
        "Food post successful."
    )

    print("=" * 60)
    print("MYBUZZ FOOD BOT FINISHED")
    print("=" * 60)


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    main()
