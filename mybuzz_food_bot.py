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
# OPENAI CLIENT
# ============================================================

openai_client = None

if OPENAI_API_KEY:
    openai_client = OpenAI(
        api_key=OPENAI_API_KEY,
        max_retries=0
    )


# ============================================================
# FOOD SEARCH LOCATIONS
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
# FOOD SEARCH QUERIES
# ============================================================

FOOD_QUERIES = [
    "new restaurant",
    "popular restaurant",
    "popular cafe",
    "trending food",
    "hidden gem restaurant",
    "local food",
    "new cafe",
    "popular dessert",
    "popular breakfast",
    "popular dinner"
]


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = str(text)
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def limit_text(text, max_chars):
    text = clean_text(text)

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "..."


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
# POSTED DATABASE
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
            return data.get("posted", [])

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
            "ERROR Missing environment variables: "
            + ", ".join(missing)
        )

        return False

    return True


# ============================================================
# GOOGLE PLACES TEXT SEARCH
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
                response.text[:2000]
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
# PHOTO URL
# ============================================================

def get_photo_url(
    photo_name
):
    if not photo_name:
        return ""

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
            allow_redirects=False
        )

        if response.status_code in (
            301,
            302,
            303,
            307,
            308
        ):
            return response.headers.get(
                "Location",
                ""
            )

        if response.status_code != 200:
            print(
                f"WARNING photo request HTTP "
                f"{response.status_code}"
            )

            return ""

        content_type = (
            response.headers
            .get(
                "Content-Type",
                ""
            )
            .lower()
        )

        if "image/" in content_type:
            print(
                "WARNING Google returned image bytes "
                "instead of redirect."
            )

            return ""

        try:
            data = response.json()

            return data.get(
                "photoUri",
                ""
            )

        except Exception:
            return ""

    except Exception as e:
        print(
            f"WARNING photo request failed: {e}"
        )

        return ""


# ============================================================
# EXTRACT PHOTO
# ============================================================

def extract_photo_url(place):
    photos = place.get(
        "photos",
        []
    )

    if not photos:
        return ""

    first_photo = photos[0]

    photo_name = first_photo.get(
        "name",
        ""
    )

    if not photo_name:
        return ""

    return get_photo_url(
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

    weekday_descriptions = (
        opening.get(
            "weekdayDescriptions",
            []
        )
    )

    if not isinstance(
        weekday_descriptions,
        list
    ):
        return []

    return [
        clean_text(item)
        for item in weekday_descriptions
        if clean_text(item)
    ]


# ============================================================
# PRICE LEVEL
# ============================================================

def price_level_text(price_level):
    mapping = {
        "PRICE_LEVEL_FREE": "Free",
        "PRICE_LEVEL_INEXPENSIVE": "RM10–20",
        "PRICE_LEVEL_MODERATE": "RM20–50",
        "PRICE_LEVEL_EXPENSIVE": "RM50–100",
        "PRICE_LEVEL_VERY_EXPENSIVE": "RM100+"
    }

    return mapping.get(
        price_level,
        "Not available"
    )


# ============================================================
# PLACE ID
# ============================================================

def place_id(place):
    value = clean_text(
        place.get(
            "id",
            ""
        )
    )

    if value:
        return value

    name = clean_text(
        (
            place.get(
                "displayName",
                {}
            )
            or {}
        ).get(
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
    posted_set = set(posted)

    candidates = []

    for place in places:
        pid = place_id(place)

        if pid in posted_set:
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
                f"Skipping without photo: {name}"
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

        candidates.append(
            (
                rating,
                review_count,
                place
            )
        )

    if not candidates:
        print(
            "No suitable food place found."
        )

        return None

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1]
        ),
        reverse=True
    )

    selected = candidates[0][2]

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
# BUILD FOOD DATA
# ============================================================

def build_food_data(place):
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

    primary_type = (
        place.get(
            "primaryTypeDisplayName",
            {}
        )
        or {}
    )

    category = clean_text(
        primary_type.get(
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

    hours = extract_opening_hours(
        place
    )

    photo_url = extract_photo_url(
        place
    )

    return {
        "id": place_id(place),
        "name": name,
        "address": address,
        "rating": rating,
        "review_count": review_count,
        "price_level": price_level_text(
            price_level
        ),
        "category": category,
        "maps_url": maps_url,
        "opening_hours": hours,
        "photo_url": photo_url
    }


# ============================================================
# OPENAI PROMPT
# ============================================================

def build_food_prompt(
    food
):
    hours_text = (
        "\n".join(
            food["opening_hours"]
        )
        if food["opening_hours"]
        else "Not available"
    )

    return f"""
You are a professional Malaysian food editor.

Create a bilingual Malaysian food recommendation for Telegram.

IMPORTANT:
- Use ONLY the factual information supplied below.
- Do not invent dishes, menu items, prices, awards, history or claims.
- Do not invent customer opinions.
- Do not claim that a restaurant is "viral", "trending" or "new" unless the supplied data supports it.
- Google rating and review count must remain exactly as supplied.
- Do not change the restaurant name.
- Do not change the address.
- Do not invent opening hours.
- If information is unavailable, say it is not available.
- Chinese and Malay versions must describe the same facts.

RESTAURANT DATA:

Name:
{food["name"]}

Address:
{food["address"]}

Category:
{food["category"]}

Google Rating:
{food["rating"]}/5

Google Reviews:
{food["review_count"]}

Price:
{food["price_level"]}

Opening Hours:
{hours_text}

TASK:

Create:

1. Chinese headline
2. Malay headline
3. Chinese introduction
4. Malay introduction
5. Recommended reason in Chinese
6. Recommended reason in Malay
7. 2-4 "must try" suggestions ONLY if they can be safely inferred from the restaurant category/name. Otherwise return an empty list.

IMPORTANT FOR "WHY RECOMMENDED":
Only use objective facts:
- Google rating
- number of reviews
- restaurant category
- location
- available factual information

Do NOT make up statements such as:
- "customers love the beef noodles"
- "the signature dish is..."
- "many people say..."
unless such information was provided.

HEADLINE STYLE:
Chinese:
Natural Malaysian Chinese food-media style.
Short and attractive.

Malay:
Natural Malaysian Malay.
Short and attractive.

CHINESE:
Use natural Malaysian Chinese.
Do not use Indonesian Chinese expressions.
Do not write a long article.

MALAY:
Use natural Malaysian Malay.
Do not use Indonesian Malay.
Do not write a long article.

RETURN ONLY VALID JSON:

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
# EXTRACT JSON
# ============================================================

def extract_json(text):
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
        return json.loads(text)

    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")

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

def validate_ai(data):
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
                f"ERROR Missing AI field: {key}"
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
# GENERATE AI CONTENT
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

    print(
        f"OpenAI prompt size: "
        f"{len(prompt)} characters"
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

        if not validate_ai(data):
            print(
                "ERROR AI validation failed."
            )

            return None

        print(
            "AI generation successful."
        )

        return data

    except Exception as e:
        error_text = str(e)

        print(
            f"ERROR OpenAI request failed: "
            f"{error_text}"
        )

        if (
            "insufficient_quota"
            in error_text.lower()
            or
            "credit_balance_exhausted"
            in error_text.lower()
        ):
            print(
                "ERROR OpenAI credits exhausted."
            )

        return None


# ============================================================
# TELEGRAM
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
# BUILD TELEGRAM MESSAGE
# ============================================================

def build_telegram_message(
    food,
    ai
):
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
            "• 暂无足够资料提供具体推荐\n"
            "• Tiada maklumat mencukupi"
        )

    hours = food.get(
        "opening_hours",
        []
    )

    if hours:
        hours_text = "\n".join(
            hours[:7]
        )
    else:
        hours_text = (
            "暂无资料\n"
            "Maklumat tidak tersedia"
        )

    message = (
        "🇲🇾 <b>MYBUZZ FOOD</b>\n\n"

        "🔥 <b>今日美食推荐</b>\n"
        "🔥 <b>Cadangan Makanan Hari Ini</b>\n\n"

        f"🍽️ <b>{food['name']}</b>\n\n"

        f"⭐ Rating: "
        f"{food['rating']:.1f}/5\n"

        f"💬 Reviews: "
        f"{food['review_count']:,}\n"

        f"💰 Price: "
        f"{food['price_level']}\n"

        f"📍 {food['address']}\n\n"

        "🍴 <b>推荐必点</b>\n"
        "🍴 <b>Wajib Cuba</b>\n"
        f"{must_try_text}\n\n"

        "🔥 <b>为什么推荐？</b>\n"
        "🔥 <b>Mengapa Disyorkan?</b>\n\n"

        f"🇨🇳 {clean_text(ai['chinese_why'])}\n\n"

        f"🇲🇾 {clean_text(ai['malay_why'])}\n\n"

        "🇨🇳 <b>中文介绍</b>\n"
        f"{clean_text(ai['chinese_body'])}\n\n"

        "🇲🇾 <b>Bahasa Melayu</b>\n"
        f"{clean_text(ai['malay_body'])}\n\n"

        "🕐 <b>营业时间 / Waktu Operasi</b>\n"
        f"{hours_text}\n\n"

        "📍 <b>地址 / Alamat</b>\n"
        f"{food['address']}\n\n"

        "👉 <b>Google Maps</b>\n"
        f"{food['maps_url']}"
    )

    return message


# ============================================================
# BUILD PLAIN TEXT
# ============================================================

def build_plain_text(
    food,
    ai
):
    must_try = ai.get(
        "must_try",
        []
    )

    if not isinstance(
        must_try,
        list
    ):
        must_try = []

    must_try_text = "\n".join(
        f"• {clean_text(item)}"
        for item in must_try[:4]
        if clean_text(item)
    )

    if not must_try_text:
        must_try_text = (
            "• 暂无足够资料提供具体推荐\n"
            "• Tiada maklumat mencukupi"
        )

    return (
        "🇲🇾 MYBUZZ FOOD\n\n"

        "🔥 今日美食推荐\n"
        "🔥 Cadangan Makanan Hari Ini\n\n"

        f"🍽️ {food['name']}\n\n"

        f"⭐ Rating: {food['rating']:.1f}/5\n"
        f"💬 Reviews: {food['review_count']:,}\n"
        f"💰 Price: {food['price_level']}\n"
        f"📍 {food['address']}\n\n"

        "🍴 推荐必点\n"
        "🍴 Wajib Cuba\n"
        f"{must_try_text}\n\n"

        "🔥 为什么推荐？\n"
        "🔥 Mengapa Disyorkan?\n\n"

        f"🇨🇳 {clean_text(ai['chinese_why'])}\n\n"
        f"🇲🇾 {clean_text(ai['malay_why'])}\n\n"

        "🇨🇳 中文介绍\n"
        f"{clean_text(ai['chinese_body'])}\n\n"

        "🇲🇾 Bahasa Melayu\n"
        f"{clean_text(ai['malay_body'])}\n\n"

        "📍 地址 / Alamat\n"
        f"{food['address']}\n\n"

        "👉 Google Maps\n"
        f"{food['maps_url']}"
    )


# ============================================================
# SEND PHOTO
# ============================================================

def send_telegram_photo(
    photo_url,
    caption
):
    url = telegram_api_url(
        "sendPhoto"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(
            url,
            data=payload,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"Telegram photo HTTP "
            f"{response.status_code}"
        )

        if response.status_code != 200:
            print(
                f"Telegram photo error: "
                f"{response.text[:2000]}"
            )

            return False

        data = response.json()

        return bool(
            data.get("ok")
        )

    except Exception as e:
        print(
            f"ERROR Telegram photo failed: {e}"
        )

        return False


# ============================================================
# SEND TEXT
# ============================================================

def send_telegram_text(
    text
):
    url = telegram_api_url(
        "sendMessage"
    )

    text = text[:TELEGRAM_TEXT_LIMIT]

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        response = requests.post(
            url,
            data=payload,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"Telegram text HTTP "
            f"{response.status_code}"
        )

        if response.status_code != 200:
            print(
                f"Telegram text error: "
                f"{response.text[:2000]}"
            )

            return False

        data = response.json()

        return bool(
            data.get("ok")
        )

    except Exception as e:
        print(
            f"ERROR Telegram text failed: {e}"
        )

        return False


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
    # Select search combination based on run number
    # --------------------------------------------------------

    location_index = (
        (run_count - 1)
        %
        len(SEARCH_LOCATIONS)
    )

    query_index = (
        (run_count - 1)
        %
        len(FOOD_QUERIES)
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

    places = search_places(
        query,
        location
    )

    if not places:
        print(
            "No places returned."
        )

        return

    place = select_place(
        places,
        posted
    )

    if not place:
        return

    food = build_food_data(
        place
    )

    print(
        f"Restaurant: {food['name']}"
    )

    print(
        f"Rating: {food['rating']}"
    )

    print(
        f"Reviews: {food['review_count']}"
    )

    print(
        f"Address: {food['address']}"
    )

    if not food["photo_url"]:
        print(
            "ERROR No usable Google photo."
        )

        return

    ai = generate_ai_content(
        food
    )

    if not ai:
        print(
            "AI failed. Nothing sent."
        )

        return

    telegram_message = (
        build_telegram_message(
            food,
            ai
        )
    )

    plain_text = (
        build_plain_text(
            food,
            ai
        )
    )

    print(
        f"Telegram message length: "
        f"{len(telegram_message)}"
    )

    sent = False

    if len(telegram_message) <= (
        TELEGRAM_CAPTION_LIMIT
    ):
        sent = send_telegram_photo(
            food["photo_url"],
            telegram_message
        )

    else:
        print(
            "Telegram caption too long."
        )

    if not sent:
        print(
            "Sending text message instead..."
        )

        sent = send_telegram_text(
            plain_text
        )

    if not sent:
        print(
            "ERROR Telegram send failed."
        )

        return

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
