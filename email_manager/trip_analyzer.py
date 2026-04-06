"""
Analyze a business trip screenshot with Claude Vision to extract:
- travel dates (departure / return)
- destinations / cities
Then search emails for matching travel-related content.
"""
import base64
import json
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import Optional


TRIP_ANALYSIS_PROMPT = """You are analyzing a business trip document or screenshot.
Extract the following information and return ONLY valid JSON:

{
  "departure_date": "YYYY-MM-DD or null",
  "return_date": "YYYY-MM-DD or null",
  "destinations": ["city1", "city2"],
  "airlines": ["airline1"],
  "flight_numbers": ["CA123"],
  "train_numbers": ["G123"],
  "hotel_names": ["hotel name"],
  "purpose": "brief trip purpose or null"
}

If a field cannot be determined, use null or empty list.
Look for: approval forms, itineraries, booking confirmations, OA system screenshots."""


def analyze_trip_screenshot(image_path: str, ai_client) -> dict:
    """
    Use Claude Vision to extract trip info from an image.
    ai_client is anthropic.Anthropic().
    Returns a dict with trip details.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    suffix = image_path.suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    media_type = media_type_map.get(suffix, "image/png")

    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    response = ai_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    },
                },
                {"type": "text", "text": TRIP_ANALYSIS_PROMPT},
            ],
        }],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
        raw = raw.rstrip("`").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_response": raw, "parse_error": True}


def build_search_params(trip_info: dict, padding_days: int = 3) -> dict:
    """
    Convert extracted trip info into search parameters for IMAP + local index.
    Returns a dict with: since, before, keywords, destinations.
    """
    since = None
    before = None

    if trip_info.get("departure_date"):
        try:
            dep = datetime.strptime(trip_info["departure_date"], "%Y-%m-%d").date()
            since = dep - timedelta(days=padding_days)
        except ValueError:
            pass

    if trip_info.get("return_date"):
        try:
            ret = datetime.strptime(trip_info["return_date"], "%Y-%m-%d").date()
            before = ret + timedelta(days=padding_days)
        except ValueError:
            pass
    elif since:
        before = since + timedelta(days=30)  # default window

    destinations = trip_info.get("destinations", [])
    airlines = trip_info.get("airlines", [])
    flight_numbers = trip_info.get("flight_numbers", [])
    train_numbers = trip_info.get("train_numbers", [])

    # Build keyword list for email subject search
    keywords = []
    keywords.extend(destinations)
    keywords.extend(airlines)
    keywords.extend(flight_numbers)
    keywords.extend(train_numbers)
    keywords.extend(trip_info.get("hotel_names", []))
    # Standard travel keywords
    keywords += ["行程单", "机票", "火车票", "酒店", "boarding pass",
                 "itinerary", "flight", "hotel", "reservation", "报销", "差旅"]

    return {
        "since": since,
        "before": before,
        "keywords": [k for k in keywords if k],
        "destinations": destinations,
    }


def summarize_trip(trip_info: dict) -> str:
    """Human-readable summary of extracted trip info."""
    lines = ["=== 出差信息提取结果 ==="]
    if trip_info.get("departure_date"):
        lines.append(f"出发日期: {trip_info['departure_date']}")
    if trip_info.get("return_date"):
        lines.append(f"返回日期: {trip_info['return_date']}")
    if trip_info.get("destinations"):
        lines.append(f"目的地: {', '.join(trip_info['destinations'])}")
    if trip_info.get("airlines"):
        lines.append(f"航空公司: {', '.join(trip_info['airlines'])}")
    if trip_info.get("flight_numbers"):
        lines.append(f"航班号: {', '.join(trip_info['flight_numbers'])}")
    if trip_info.get("train_numbers"):
        lines.append(f"车次: {', '.join(trip_info['train_numbers'])}")
    if trip_info.get("hotel_names"):
        lines.append(f"酒店: {', '.join(trip_info['hotel_names'])}")
    if trip_info.get("purpose"):
        lines.append(f"出差事由: {trip_info['purpose']}")
    return "\n".join(lines)
