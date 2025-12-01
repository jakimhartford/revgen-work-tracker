#!/usr/bin/env python3
"""
Central sync script - pulls issues from multiple repos to one Notion database.
Configure REPOS list below with your repositories.

Usage:
    export NOTION_API_KEY="your-key"
    export NOTION_DATABASE_ID="your-db-id"
    export GITHUB_TOKEN="your-token"
    python scripts/sync_all_repos.py
"""

import os
import sys
import requests

# =============================================================================
# CONFIGURE YOUR REPOS HERE
# =============================================================================
# Format: "owner/repo"
REPOS = [
    "jakimhartford/revgen-work-tracker",
    "jakimhartford/sports-betting",
    "Akels-Carpet-One/rfms-api-manager",
    "DeliveryKick/DK-ElasticSearch",
    "DeliveryKick/DKWeb",
    "DeliveryKick/Ordering-Delivery-and-Payment-Backend",
    "DeliveryKick/Restaurant-Repository-Backend",
    "DeliveryKick/UberScraper",
    "DeliveryKick/deliverykick-infrastructure",
    "VPC-PII/vpc",
]

# Map repos to Source values in Notion
REPO_SOURCE_MAP = {
    "revgen-work-tracker": "RevGen",
    "sports-betting": "Sports",
    "rfms-api-manager": "RFMS",
    "DK-ElasticSearch": "DeliveryKick",
    "DKWeb": "DeliveryKick",
    "Ordering-Delivery-and-Payment-Backend": "DeliveryKick",
    "Restaurant-Repository-Backend": "DeliveryKick",
    "UberScraper": "DeliveryKick",
    "deliverykick-infrastructure": "DeliveryKick",
    "vpc": "VPC",
}
# =============================================================================

NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

GITHUB_API_BASE = "https://api.github.com"


def get_github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# =============================================================================
# GitHub Functions
# =============================================================================

def get_all_issues(owner: str, repo: str) -> list:
    """Fetch all issues (open and closed) from a GitHub repo."""
    all_issues = []

    for state in ["open", "closed"]:
        page = 1
        while True:
            url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"
            params = {"state": state, "per_page": 100, "page": page}
            resp = requests.get(url, headers=get_github_headers(), params=params)

            if resp.status_code != 200:
                print(f"  Error fetching {owner}/{repo}: {resp.status_code}")
                break

            issues = resp.json()
            if not issues:
                break

            # Filter out pull requests
            issues = [i for i in issues if "pull_request" not in i]
            all_issues.extend(issues)

            if len(issues) < 100:
                break
            page += 1

    return all_issues


def get_issue_comments(owner: str, repo: str, issue_number: int) -> list:
    """Fetch comments for an issue."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments"
    resp = requests.get(url, headers=get_github_headers())
    if resp.status_code == 200:
        return resp.json()
    return []


# =============================================================================
# Notion Functions
# =============================================================================

def find_existing_page(issue_id: int, repo: str):
    """Find existing Notion page by Issue ID and Repo."""
    url = f"{NOTION_BASE_URL}/databases/{NOTION_DATABASE_ID}/query"
    payload = {
        "filter": {
            "and": [
                {"property": "Issue ID", "rich_text": {"equals": str(issue_id)}},
                {"property": "Repo", "rich_text": {"equals": repo}},
            ]
        }
    }
    resp = requests.post(url, headers=NOTION_HEADERS, json=payload)
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        return results[0] if results else None
    return None


def get_priority_from_labels(labels: list) -> str:
    """Extract priority from GitHub labels."""
    label_names = [l["name"].lower() for l in labels]
    if "high-priority" in label_names or "high" in label_names or "urgent" in label_names:
        return "High"
    if "medium" in label_names or "medium-priority" in label_names:
        return "Medium"
    if "low" in label_names or "low-priority" in label_names:
        return "Low"
    return "Medium"


def map_status(issue_state: str, labels: list) -> str:
    """Map GitHub state + labels to Notion status."""
    if issue_state == "closed":
        return "Done"

    label_names = [l["name"].lower() for l in labels]
    if "blocked" in label_names:
        return "Blocked"
    if "in-progress" in label_names or "in progress" in label_names:
        return "In Progress"
    if "review" in label_names or "under-review" in label_names:
        return "Under Review"

    return "Backlog"


def build_properties(issue: dict, repo_name: str, source: str, comments_count: int = 0) -> dict:
    """Build Notion properties from GitHub issue."""
    labels = issue.get("labels", [])
    milestone = issue.get("milestone")
    assignees = issue.get("assignees", [])

    properties = {
        "Name": {"title": [{"text": {"content": issue["title"]}}]},
        "Issue ID": {"rich_text": [{"text": {"content": str(issue["number"])}}]},
        "Repo": {"rich_text": [{"text": {"content": repo_name}}]},
        "URL": {"url": issue["html_url"]},
        "Status": {"select": {"name": map_status(issue["state"], labels)}},
        "Source": {"select": {"name": source}},
        "Priority": {"select": {"name": get_priority_from_labels(labels)}},
    }

    # Labels
    label_options = [{"name": l["name"]} for l in labels]
    properties["Labels"] = {"multi_select": label_options} if label_options else {"multi_select": []}

    # Milestone
    if milestone:
        properties["Milestone"] = {"select": {"name": milestone["title"]}}
        if milestone.get("due_on"):
            properties["Due Date"] = {"date": {"start": milestone["due_on"][:10]}}

    # Assignee
    if assignees:
        properties["Assignee"] = {"rich_text": [{"text": {"content": ", ".join(a["login"] for a in assignees)}}]}

    # Comments count
    properties["Comments"] = {"number": comments_count}

    return properties


def create_notion_page(issue: dict, repo_name: str, source: str, comments_count: int = 0):
    """Create a Notion page."""
    url = f"{NOTION_BASE_URL}/pages"
    properties = build_properties(issue, repo_name, source, comments_count)

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
    }

    # Add issue body as content
    issue_body = issue.get("body") or ""
    if issue_body:
        truncated = issue_body[:4000]
        chunks = [truncated[i:i+2000] for i in range(0, len(truncated), 2000)]
        payload["children"] = [
            {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": c}}]}}
            for c in chunks
        ]

    resp = requests.post(url, headers=NOTION_HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()


def update_notion_page(page_id: str, issue: dict, repo_name: str, source: str, comments_count: int = 0):
    """Update a Notion page."""
    url = f"{NOTION_BASE_URL}/pages/{page_id}"
    properties = build_properties(issue, repo_name, source, comments_count)
    resp = requests.patch(url, headers=NOTION_HEADERS, json={"properties": properties})
    resp.raise_for_status()
    return resp.json()


# =============================================================================
# Main Sync
# =============================================================================

def sync_repo(owner: str, repo: str):
    """Sync all issues from a single repo."""
    source = REPO_SOURCE_MAP.get(repo, repo)

    print(f"\n📦 Syncing {owner}/{repo} → Source: {source}")
    print("-" * 50)

    issues = get_all_issues(owner, repo)
    print(f"  Found {len(issues)} issues")

    created, updated, errors = 0, 0, 0

    for issue in issues:
        try:
            comments = get_issue_comments(owner, repo, issue["number"])
            existing = find_existing_page(issue["number"], repo)

            if existing:
                update_notion_page(existing["id"], issue, repo, source, len(comments))
                updated += 1
            else:
                create_notion_page(issue, repo, source, len(comments))
                created += 1

            print(f"  {'✓' if existing else '+'} #{issue['number']} {issue['title'][:40]}...")

        except Exception as e:
            errors += 1
            print(f"  ✗ #{issue['number']} Error: {e}")

    print(f"  Summary: {created} created, {updated} updated, {errors} errors")
    return created, updated, errors


def main():
    """Sync all configured repos."""
    if not NOTION_API_KEY or not NOTION_DATABASE_ID or not GITHUB_TOKEN:
        print("ERROR: Missing environment variables")
        print("  Required: NOTION_API_KEY, NOTION_DATABASE_ID, GITHUB_TOKEN")
        sys.exit(1)

    print("=" * 60)
    print("🔄 Central Repo Sync - GitHub → Notion")
    print("=" * 60)
    print(f"Repos to sync: {len(REPOS)}")

    total_created, total_updated, total_errors = 0, 0, 0

    for repo_full in REPOS:
        if "/" not in repo_full:
            print(f"⚠️  Skipping invalid repo format: {repo_full}")
            continue

        owner, repo = repo_full.split("/", 1)
        c, u, e = sync_repo(owner, repo)
        total_created += c
        total_updated += u
        total_errors += e

    print("\n" + "=" * 60)
    print("✅ Sync Complete!")
    print(f"   Total: {total_created} created, {total_updated} updated, {total_errors} errors")
    print("=" * 60)


if __name__ == "__main__":
    main()
