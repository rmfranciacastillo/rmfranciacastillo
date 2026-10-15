#!/usr/bin/env python3
"""Update Commit Circuit SVG from GitHub's rolling 365-day contribution totals."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

USERNAME = os.environ.get("GITHUB_USER", "rmfranciacastillo")
# A fine-grained/classic PAT with read:user is required to include private
# contribution counts. GITHUB_TOKEN is only a fallback for public-only data.
CONTRIBUTIONS_TOKEN = os.environ.get("CONTRIBUTIONS_TOKEN", "").strip()
TOKEN = CONTRIBUTIONS_TOKEN or os.environ.get("GITHUB_TOKEN", "").strip()
SVG_PATH = Path(os.environ.get("STATS_SVG_PATH", ".github/assets/04.svg"))
GRAPHQL_URL = "https://api.github.com/graphql"
ET.register_namespace("", "http://www.w3.org/2000/svg")

METRICS = {
    "commits": {"value_id": "commits-value", "bar_id": "commits-bar"},
    "pull_requests": {"value_id": "pull-requests-value", "bar_id": "pull-requests-bar"},
    "issues": {"value_id": "issues-value", "bar_id": "issues-bar"},
    "code_reviews": {"value_id": "code-reviews-value", "bar_id": "code-reviews-bar"},
}
BAR_MAX_WIDTH = 118.0

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      startedAt
      endedAt
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      hasAnyRestrictedContributions
      restrictedContributionsCount
    }
  }
}
"""


def fetch_contributions(start: datetime, end: datetime) -> tuple[dict[str, int], dict[str, object]]:
    """Fetch contribution totals and private-contribution diagnostics."""
    payload = {
        "query": QUERY,
        "variables": {
            "login": USERNAME,
            "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "commit-circuit-stats-updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not connect to GitHub GraphQL API: {exc}") from exc

    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {json.dumps(result['errors'])}")
    user = (result.get("data") or {}).get("user")
    if user is None:
        raise RuntimeError(f"GitHub user {USERNAME!r} was not found or is not accessible.")
    collection = user["contributionsCollection"]
    metrics = {
        "commits": int(collection["totalCommitContributions"]),
        "pull_requests": int(collection["totalPullRequestContributions"]),
        "issues": int(collection["totalIssueContributions"]),
        "code_reviews": int(collection["totalPullRequestReviewContributions"]),
    }
    diagnostics: dict[str, object] = {
        "started_at": collection["startedAt"],
        "ended_at": collection["endedAt"],
        "has_restricted": bool(collection["hasAnyRestrictedContributions"]),
        "restricted_count": int(collection["restrictedContributionsCount"]),
        "private_token_configured": bool(CONTRIBUTIONS_TOKEN),
    }
    return metrics, diagnostics


def local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def find_by_id(root: ET.Element, element_id: str) -> ET.Element:
    node = next((item for item in root.iter() if item.get("id") == element_id), None)
    if node is None:
        raise RuntimeError(f"SVG element id={element_id!r} not found in {SVG_PATH}.")
    return node


def set_text_by_id(root: ET.Element, element_id: str, value: str) -> None:
    node = find_by_id(root, element_id)
    for child in list(node):
        node.remove(child)
    node.text = value


def update_svg(metrics: dict[str, int], diagnostics: dict[str, object]) -> None:
    tree = ET.parse(SVG_PATH)
    root = tree.getroot()
    highest = max(metrics.values(), default=0)
    for name, ids in METRICS.items():
        set_text_by_id(root, ids["value_id"], f"{metrics[name]:,}")
        bar = find_by_id(root, ids["bar_id"])
        width = 0.0 if highest == 0 else BAR_MAX_WIDTH * metrics[name] / highest
        bar.set("width", f"{width:.2f}")

    if not diagnostics["private_token_configured"]:
        status = "PRIVATE COUNTS: ADD CONTRIBUTIONS_TOKEN (read:user)"
        color = "#ffe52d"
    elif diagnostics["has_restricted"]:
        status = f"PRIVATE CONTRIBUTIONS DETECTED: {diagnostics['restricted_count']}+"
        color = "#00dfa8"
    else:
        status = "NO RESTRICTED CONTRIBUTIONS REPORTED*"
        color = "#8fa6bb"
    status_node = find_by_id(root, "contribution-status")
    status_node.text = status
    status_node.set("fill", color)
    tree.write(SVG_PATH, encoding="UTF-8", xml_declaration=True)


def main() -> None:
    if not TOKEN:
        raise RuntimeError("No token found. Set CONTRIBUTIONS_TOKEN or GITHUB_TOKEN.")
    if not SVG_PATH.is_file():
        raise FileNotFoundError(f"SVG template not found: {SVG_PATH}")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365)
    metrics, diagnostics = fetch_contributions(start, end)
    update_svg(metrics, diagnostics)

    print(f"Updated {SVG_PATH}")
    print(f"Requested UTC range: {start:%Y-%m-%dT%H:%M:%SZ} through {end:%Y-%m-%dT%H:%M:%SZ}")
    print(f"GitHub collection range: {diagnostics['started_at']} through {diagnostics['ended_at']}")
    print("Contribution totals: " + ", ".join(f"{key}={value}" for key, value in metrics.items()))
    print(f"Private token configured: {diagnostics['private_token_configured']}")
    print(f"Restricted contributions reported: {diagnostics['has_restricted']}")
    print(f"Restricted contribution count: {diagnostics['restricted_count']}")
    if not diagnostics["private_token_configured"]:
        print("WARNING: Using GITHUB_TOKEN fallback; private contribution counts may be missing.", file=sys.stderr)
    elif not diagnostics["has_restricted"]:
        print("NOTE: No restricted contributions reported. Check GitHub private-contribution visibility settings if this seems wrong.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Commit Circuit update failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
