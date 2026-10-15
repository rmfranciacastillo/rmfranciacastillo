
import json
import math
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


# --------------------------------------------------
# Configuration
# --------------------------------------------------

GITHUB_USER = "rmfranciacastillo"
X_HANDLE = "RenatoFranciaC"

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

ASSETS_DIR = Path(".github/assets")


# --------------------------------------------------
# HTTP utilities
# --------------------------------------------------

def get_json(url, headers=None, params=None):
    """Fetch JSON from an API endpoint."""
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"

    request = urllib.request.Request(
        url,
        headers=headers or {},
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


# --------------------------------------------------
# SVG badge utilities
# --------------------------------------------------

def escape_xml(value):
    """Escape text for safe inclusion in SVG."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def format_number(value):
    """Format a number using compact notation."""
    value = int(value)

    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")

    if value >= 1_000:
        return f"{value / 1_000:.1f}K".replace(".0K", "K")

    return str(value)


def text_width(text, font_size=12):
    """
    Estimate text width using character-specific multipliers.
    This keeps badge dimensions reasonably consistent without
    requiring an external font-measurement library.
    """
    widths = {
        " ": 0.28,
        "i": 0.28,
        "l": 0.28,
        "I": 0.32,
        "j": 0.30,
        "f": 0.35,
        "r": 0.38,
        "t": 0.35,
        "m": 0.85,
        "w": 0.78,
        "M": 0.90,
        "W": 0.95,
        "1": 0.55,
        ".": 0.30,
        ",": 0.30,
        ":": 0.30,
        "-": 0.38,
    }

    units = sum(
        widths.get(char, 0.58 if char.islower() else 0.65)
        for char in str(text)
    )

    return math.ceil(units * font_size)


def create_badge(label, value, output_file):
    """Generate a standalone SVG badge."""
    label = str(label)
    value = str(value)

    font_size = 12
    horizontal_padding = 10
    height = 24

    label_width = text_width(label, font_size)
    value_width = text_width(value, font_size)

    left_width = label_width + horizontal_padding * 2
    right_width = value_width + horizontal_padding * 2
    total_width = left_width + right_width

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg"
    width="{total_width}"
    height="{height}"
    viewBox="0 0 {total_width} {height}"
    role="img"
    aria-label="{escape_xml(label)}: {escape_xml(value)}">
  <title>{escape_xml(label)}: {escape_xml(value)}</title>
  <rect width="{left_width}" height="{height}" rx="4"
        fill="#1e293b"/>
  <rect x="{left_width}" width="{right_width}" height="{height}"
        rx="4" fill="#0891b2"/>
  <rect x="{left_width - 4}" width="8" height="{height}"
        fill="#0891b2"/>
  <g fill="#f8fafc"
     font-family="Verdana, DejaVu Sans, sans-serif"
     font-size="{font_size}"
     text-anchor="middle">
    <text x="{left_width / 2}"
          y="16"
          dominant-baseline="middle">{escape_xml(label)}</text>
    <text x="{left_width + right_width / 2}"
          y="16"
          dominant-baseline="middle"
          font-weight="bold">{escape_xml(value)}</text>
  </g>
</svg>
"""

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(svg, encoding="utf-8")

    print(f"Generated: {output_file}")


# --------------------------------------------------
# YouTube API
# --------------------------------------------------

def youtube_stats():
    """Return subscriber count and total channel views."""
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY is not set")

    if not YOUTUBE_CHANNEL_ID:
        raise RuntimeError("YOUTUBE_CHANNEL_ID is not set")

    
    print("YouTube API key: configured")
    print(f"YouTube channel ID: {YOUTUBE_CHANNEL_ID}")

    data = get_json(
        "https://www.googleapis.com/youtube/v3/channels",
        headers={
            "X-Goog-Api-Key": YOUTUBE_API_KEY,
        },
        params={
            "part": "statistics,snippet",
            "id": YOUTUBE_CHANNEL_ID,
        },
    )

    items = data.get("items", [])

    if not items:
        raise RuntimeError(
            "YouTube API returned no channel. Check YOUTUBE_CHANNEL_ID."
        )

    channel = items[0]
    stats = channel["statistics"]

    channel_name = channel.get("snippet", {}).get("title", "Unknown")

    subscribers = int(stats["subscriberCount"])
    views = int(stats["viewCount"])

    print(f"YouTube channel: {channel_name}")
    print(f"YouTube subscribers: {subscribers}")
    print(f"YouTube views: {views}")

    return subscribers, views


# --------------------------------------------------
# GitHub API
# --------------------------------------------------

def github_stars():
    """Return the total stars across public repositories."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "profile-badges-generator",
    }

    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    total_stars = 0
    page = 1

    while True:
        data = get_json(
            f"https://api.github.com/users/{GITHUB_USER}/repos",
            headers=headers,
            params={
                "per_page": 100,
                "page": page,
                "type": "owner",
            },
        )

        if not data:
            break

        total_stars += sum(
            int(repo.get("stargazers_count", 0))
            for repo in data
        )

        if len(data) < 100:
            break

        page += 1

    print(f"GitHub stars: {total_stars}")

    return total_stars


# --------------------------------------------------
# X / Twitter badge
# --------------------------------------------------

def x_followers():
    """
    X does not provide a public follower-count endpoint that
    this script can call without additional API access.

    Return None so the script does not fabricate a count.
    """
    print(
        "X follower count skipped: configure an X API endpoint "
        "if you want this badge updated automatically."
    )

    return None


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    errors = []

    # YouTube badges
    try:
        subscribers, views = youtube_stats()

        create_badge(
            "YouTube subscribers",
            format_number(subscribers),
            ASSETS_DIR / "youtube-subscribers.svg",
        )

        create_badge(
            "YouTube views",
            format_number(views),
            ASSETS_DIR / "youtube-views.svg",
        )

    except Exception as exc:
        print(
            f"YouTube stats failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        errors.append("YouTube")

    # GitHub badge
    try:
        stars = github_stars()

        create_badge(
            "GitHub stars",
            format_number(stars),
            ASSETS_DIR / "github-stars.svg",
        )

    except Exception as exc:
        print(
            f"GitHub stats failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        errors.append("GitHub")

    # X badge
    followers = x_followers()

    if followers is not None:
        create_badge(
            "X followers",
            format_number(followers),
            ASSETS_DIR / "x-follow.svg",
        )

    if errors:
        print(
            f"Failed sources: {', '.join(errors)}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Profile badges updated successfully.")


if __name__ == "__main__":
    main()
