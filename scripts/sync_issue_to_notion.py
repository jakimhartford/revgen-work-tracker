import json
import os
import requests

NOTION_API_KEY = os.environ["NOTION_API_KEY"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_EVENT_PATH = os.environ.get("GITHUB_EVENT_PATH", "")
GITHUB_REPO_NAME = os.environ.get("GITHUB_REPO_NAME", "")

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


def load_github_event():
    if GITHUB_EVENT_PATH and os.path.exists(GITHUB_EVENT_PATH):
        with open(GITHUB_EVENT_PATH, "r") as f:
            return json.load(f)
    return {}


# =============================================================================
# Status Mapping
# =============================================================================

GITHUB_TO_NOTION_STATUS = {
    "open": "Backlog",
    "closed": "Done",
}

NOTION_TO_GITHUB_STATUS = {
    "Backlog": "open",
    "In Progress": "open",
    "Blocked": "open",
    "Waiting on Client": "open",
    "Under Review": "open",
    "Done": "closed",
}


def map_status_to_notion(issue_state: str, labels: list = None) -> str:
    """Map GitHub issue state + labels to Notion Status."""
    if issue_state == "closed":
        return "Done"

    if labels:
        label_names = [l["name"].lower() for l in labels]
        if "blocked" in label_names:
            return "Blocked"
        if "in-progress" in label_names or "in progress" in label_names:
            return "In Progress"
        if "review" in label_names or "under-review" in label_names:
            return "Under Review"

    return "Backlog"


def map_status_to_github(notion_status: str) -> str:
    """Map Notion Status to GitHub issue state."""
    return NOTION_TO_GITHUB_STATUS.get(notion_status, "open")


# =============================================================================
# GitHub API Functions
# =============================================================================

def get_issue_comments(owner: str, repo: str, issue_number: int) -> list:
    """Fetch all comments for a GitHub issue."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments"
    resp = requests.get(url, headers=get_github_headers())
    if resp.status_code == 200:
        return resp.json()
    return []


def get_issue_details(owner: str, repo: str, issue_number: int) -> dict:
    """Fetch full issue details from GitHub."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}"
    resp = requests.get(url, headers=get_github_headers())
    if resp.status_code == 200:
        return resp.json()
    return {}


def update_github_issue(owner: str, repo: str, issue_number: int, updates: dict):
    """Update a GitHub issue."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}"
    resp = requests.patch(url, headers=get_github_headers(), json=updates)
    resp.raise_for_status()
    print(f"Updated GitHub issue #{issue_number}")
    return resp.json()


def add_github_comment(owner: str, repo: str, issue_number: int, body: str):
    """Add a comment to a GitHub issue."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{issue_number}/comments"
    resp = requests.post(url, headers=get_github_headers(), json={"body": body})
    resp.raise_for_status()
    print(f"Added comment to GitHub issue #{issue_number}")
    return resp.json()


def close_github_issue(owner: str, repo: str, issue_number: int):
    """Close a GitHub issue."""
    return update_github_issue(owner, repo, issue_number, {"state": "closed"})


def reopen_github_issue(owner: str, repo: str, issue_number: int):
    """Reopen a GitHub issue."""
    return update_github_issue(owner, repo, issue_number, {"state": "open"})


def update_github_labels(owner: str, repo: str, issue_number: int, labels: list):
    """Update labels on a GitHub issue."""
    return update_github_issue(owner, repo, issue_number, {"labels": labels})


# =============================================================================
# Notion API Functions
# =============================================================================

def find_existing_page(issue_id: int, repo: str):
    """Query the Notion database for an existing page matching Issue ID + Repo."""
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
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None


def get_all_notion_pages():
    """Get all pages from the Notion database."""
    url = f"{NOTION_BASE_URL}/databases/{NOTION_DATABASE_ID}/query"
    all_pages = []
    has_more = True
    start_cursor = None

    while has_more:
        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = requests.post(url, headers=NOTION_HEADERS, json=payload)
        resp.raise_for_status()
        data = resp.json()

        all_pages.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return all_pages


def get_notion_page_content(page_id: str) -> list:
    """Get the content blocks of a Notion page."""
    url = f"{NOTION_BASE_URL}/blocks/{page_id}/children"
    resp = requests.get(url, headers=NOTION_HEADERS)
    if resp.status_code == 200:
        return resp.json().get("results", [])
    return []


def build_properties(issue: dict, repo_name: str, comments_count: int = 0) -> dict:
    """Build Notion properties payload from GitHub issue."""
    issue_title = issue["title"]
    issue_number = issue["number"]
    issue_url = issue["html_url"]
    issue_state = issue["state"]
    labels = issue.get("labels", [])
    milestone = issue.get("milestone")

    status_value = map_status_to_notion(issue_state, labels)

    # Build labels multi-select
    label_options = [{"name": label["name"]} for label in labels]

    properties = {
        "Name": {"title": [{"text": {"content": issue_title}}]},
        "Issue ID": {"rich_text": [{"text": {"content": str(issue_number)}}]},
        "Repo": {"rich_text": [{"text": {"content": repo_name}}]},
        "URL": {"url": issue_url},
        "Status": {"select": {"name": status_value}},
        "Source": {"select": {"name": "RevGen"}},
    }

    # Add labels if present
    if label_options:
        properties["Labels"] = {"multi_select": label_options}
    else:
        properties["Labels"] = {"multi_select": []}

    # Add milestone if present
    if milestone:
        properties["Milestone"] = {"select": {"name": milestone["title"]}}

    # Add comments count
    properties["Comments"] = {"number": comments_count}

    return properties


def build_comment_blocks(comments: list) -> list:
    """Build Notion blocks for comments."""
    blocks = []

    if not comments:
        return blocks

    # Add a divider and header
    blocks.append({"object": "block", "type": "divider", "divider": {}})
    blocks.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "Comments"}}]
        }
    })

    for comment in comments:
        author = comment.get("user", {}).get("login", "Unknown")
        created_at = comment.get("created_at", "")[:10]
        body = comment.get("body", "")[:2000]  # Notion has limits

        # Add comment header
        blocks.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"@{author} on {created_at}\n\n{body}"}}
                ],
                "icon": {"emoji": "💬"}
            }
        })

    return blocks


def create_notion_page(issue: dict, repo_name: str, comments: list = None):
    """Create a new Notion page for a GitHub issue."""
    url = f"{NOTION_BASE_URL}/pages"
    comments = comments or []
    properties = build_properties(issue, repo_name, len(comments))

    # Build page content with issue body
    children = []

    # Add issue body as content
    issue_body = issue.get("body") or ""
    if issue_body:
        # Split body into chunks (Notion has 2000 char limit per block)
        chunks = [issue_body[i:i+2000] for i in range(0, len(issue_body), 2000)]
        for chunk in chunks:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": chunk}}]
                }
            })

    # Add comments
    children.extend(build_comment_blocks(comments))

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
        "children": children,
    }

    resp = requests.post(url, headers=NOTION_HEADERS, json=payload)
    resp.raise_for_status()
    print(f"Created Notion page for issue #{issue['number']}")
    return resp.json()


def update_notion_page(page_id: str, issue: dict, repo_name: str, comments: list = None):
    """Update an existing Notion page."""
    url = f"{NOTION_BASE_URL}/pages/{page_id}"
    comments = comments or []
    properties = build_properties(issue, repo_name, len(comments))

    payload = {"properties": properties}
    resp = requests.patch(url, headers=NOTION_HEADERS, json=payload)
    resp.raise_for_status()
    print(f"Updated Notion page for issue #{issue['number']}")
    return resp.json()


def append_notion_comments(page_id: str, comments: list):
    """Append new comments to a Notion page."""
    if not comments:
        return

    url = f"{NOTION_BASE_URL}/blocks/{page_id}/children"
    blocks = build_comment_blocks(comments)

    if blocks:
        payload = {"children": blocks}
        resp = requests.patch(url, headers=NOTION_HEADERS, json=payload)
        resp.raise_for_status()
        print(f"Appended {len(comments)} comments to Notion page")


# =============================================================================
# Sync Functions
# =============================================================================

def sync_github_to_notion():
    """Sync a GitHub issue event to Notion."""
    event = load_github_event()
    action = event.get("action")
    issue = event.get("issue")
    comment = event.get("comment")

    if not issue:
        print("No issue in event payload.")
        return

    # Parse repo info
    full_repo = GITHUB_REPO_NAME
    owner, repo_name = full_repo.split("/") if "/" in full_repo else ("", full_repo)

    issue_number = issue["number"]

    # Fetch comments from GitHub
    comments = []
    if owner and repo_name:
        comments = get_issue_comments(owner, repo_name, issue_number)

    # Find or create Notion page
    existing_page = find_existing_page(issue_number, repo_name)

    if existing_page:
        update_notion_page(existing_page["id"], issue, repo_name, comments)

        # If this is a new comment, append it
        if action == "created" and comment:
            append_notion_comments(existing_page["id"], [comment])
    else:
        if action in ("opened", "reopened", "edited"):
            create_notion_page(issue, repo_name, comments)
        else:
            print(f"No existing page and action is '{action}', skipping.")


def sync_notion_to_github():
    """Sync Notion changes back to GitHub (bidirectional sync)."""
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN not set, skipping Notion → GitHub sync")
        return

    print("Starting Notion → GitHub sync...")
    pages = get_all_notion_pages()

    for page in pages:
        try:
            props = page.get("properties", {})

            # Extract issue info
            issue_id_prop = props.get("Issue ID", {}).get("rich_text", [])
            repo_prop = props.get("Repo", {}).get("rich_text", [])
            status_prop = props.get("Status", {}).get("select", {})
            labels_prop = props.get("Labels", {}).get("multi_select", [])

            if not issue_id_prop or not repo_prop:
                continue

            issue_number = int(issue_id_prop[0]["text"]["content"])
            repo_name = repo_prop[0]["text"]["content"]
            notion_status = status_prop.get("name", "Backlog") if status_prop else "Backlog"
            notion_labels = [l["name"] for l in labels_prop]

            # Determine owner (assumes same owner as current repo)
            owner = GITHUB_REPO_NAME.split("/")[0] if "/" in GITHUB_REPO_NAME else ""
            if not owner:
                continue

            # Fetch current GitHub issue state
            gh_issue = get_issue_details(owner, repo_name, issue_number)
            if not gh_issue:
                continue

            gh_state = gh_issue.get("state", "open")
            gh_labels = [l["name"] for l in gh_issue.get("labels", [])]

            # Determine expected GitHub state from Notion
            expected_gh_state = map_status_to_github(notion_status)

            updates_made = False

            # Sync state changes
            if gh_state != expected_gh_state:
                if expected_gh_state == "closed":
                    close_github_issue(owner, repo_name, issue_number)
                else:
                    reopen_github_issue(owner, repo_name, issue_number)
                updates_made = True

            # Sync label changes
            if set(gh_labels) != set(notion_labels):
                update_github_labels(owner, repo_name, issue_number, notion_labels)
                updates_made = True

            if updates_made:
                print(f"Synced Notion → GitHub for issue #{issue_number}")

        except Exception as e:
            print(f"Error syncing page: {e}")
            continue

    print("Notion → GitHub sync complete.")


# =============================================================================
# Main Entry Points
# =============================================================================

def main():
    """Main entry point for GitHub → Notion sync (triggered by GitHub Actions)."""
    sync_github_to_notion()


def main_bidirectional():
    """Entry point for bidirectional sync (scheduled)."""
    # First sync any pending GitHub changes
    if GITHUB_EVENT_PATH:
        sync_github_to_notion()

    # Then sync Notion changes back to GitHub
    sync_notion_to_github()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--bidirectional":
        main_bidirectional()
    else:
        main()
