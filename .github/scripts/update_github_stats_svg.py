#!/usr/bin/env python3
"""Update live GitHub stats in an existing SVG dashboard."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

USERNAME = os.environ.get("GITHUB_USER", "rmfranciacastillo")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
SVG_PATH = Path(os.environ.get("STATS_SVG_PATH", ".github/assets/03.svg"))

CARD_MAP = {
    "stars-card": "stars",
    "contributions-card": "contributions",
    "pull-requests-card": "pull_requests",
    "streak-card": "streak",
}
ET.register_namespace("", "http://www.w3.org/2000/svg")


def api_json(url, method="GET", payload=None, headers=None, use_token=True):
    request_headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-stats-svg-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if TOKEN and use_token:
        request_headers["Authorization"] = f"Bearer {TOKEN}"
    if headers:
        request_headers.update(headers)
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc


def graphql(query, variables):
    data = api_json(
        "https://api.github.com/graphql",
        method="POST",
        payload={"query": query, "variables": variables},
    )
    if data.get("errors"):
        raise RuntimeError("GitHub GraphQL error: " + json.dumps(data["errors"]))
    return data["data"]


def get_star_count():
    # Public endpoint requires no token, avoiding /user/repos permission errors.
    total = 0
    page = 1
    while True:
        repos = api_json(
            f"https://api.github.com/users/{urllib.parse.quote(USERNAME)}/repos"
            f"?per_page=100&page={page}&type=owner",
            use_token=False,
        )
        total += sum(int(repo.get("stargazers_count", 0)) for repo in repos)
        if len(repos) < 100:
            return total
        page += 1


def get_contributions_and_streak():
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=370)
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }
    """
    result = graphql(query, {
        "login": USERNAME,
        "from": start.isoformat().replace("+00:00", "Z"),
        "to": now.isoformat().replace("+00:00", "Z"),
    })
    user = result.get("user")
    if user is None:
        raise RuntimeError(f"GitHub user not found: {USERNAME}")
    calendar = user["contributionsCollection"]["contributionCalendar"]
    contributions = int(calendar["totalContributions"])
    counts = {
        day["date"]: int(day["contributionCount"])
        for week in calendar["weeks"]
        for day in week["contributionDays"]
    }
    current = date.today()
    if counts.get(current.isoformat(), 0) == 0:
        current -= timedelta(days=1)
    streak = 0
    while counts.get(current.isoformat(), 0) > 0:
        streak += 1
        current -= timedelta(days=1)
    return contributions, streak


def get_pull_request_count():
    result = graphql(
        """query($query: String!) {
          search(query: $query, type: ISSUE, first: 1) { issueCount }
        }""",
        {"query": f"author:{USERNAME} is:pr"},
    )
    return int(result["search"]["issueCount"])


def local_name(element):
    return element.tag.rsplit("}", 1)[-1]


def set_value(root, group_id, value):
    group = next(
        (node for node in root.iter()
         if local_name(node) == "g" and node.get("id") == group_id),
        None,
    )
    if group is None:
        raise RuntimeError(
            f"SVG group id={group_id!r} not found. Update the script's card IDs."
        )
    text_node = next(
        (node for node in group.iter()
         if local_name(node) == "text"
         and "value" in node.get("class", "").split()),
        None,
    )
    if text_node is None:
        raise RuntimeError(
            f"No <text class='value'> found in SVG group {group_id!r}. "
            "Update the script selector to match your SVG."
        )
    for child in list(text_node):
        text_node.remove(child)
    text_node.text = str(value)


def main():
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is missing.")
    if not SVG_PATH.is_file():
        raise FileNotFoundError(f"SVG template not found: {SVG_PATH}")

    stars = get_star_count()
    contributions, streak = get_contributions_and_streak()
    pull_requests = get_pull_request_count()

    tree = ET.parse(SVG_PATH)
    root = tree.getroot()
    values = {
        "stars-card": f"{stars:,}",
        "contributions-card": f"{contributions:,}",
        "pull-requests-card": f"{pull_requests:,}",
        "streak-card": f"{streak}d",
    }
    for card_id, value in values.items():
        set_value(root, card_id, value)
    tree.write(SVG_PATH, encoding="UTF-8", xml_declaration=True)
    print(
        f"Updated {SVG_PATH}: stars={stars}, contributions={contributions}, "
        f"pull_requests={pull_requests}, current_streak={streak}d"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Stats SVG update failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)