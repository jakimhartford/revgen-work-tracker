import json
import os
import requests

NOTION_API_KEY = os.environ["NOTION_API_KEY"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
GITHUB_EVENT_PATH = os.environ["GITHUB_EVENT_PATH"]
GITHUB_REPO_NAME = os.environ.get("GITHUB_REPO_NAME", "")

NOTION_BASE_URL = "https://api.notion.com/v1"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def load_github_event():
    with open(GITHUB_EVENT_PATH, "r") as f:
        return json.load(f)


def map_status(issue_state: str) -> str:
    """
    Map GitHub issue state to Notion Status.
    You can tweak this to look at labels, etc.
    """
    if issue_state == "closed":
        return "Done"
    else:
        return "Backlog"


def find_existing_page(issue_id: int, repo: str):
    """
    Query the Notion database for an existing page
    matching Issue ID + Repo.
    """
    url = f"{NOTION_BASE_URL}/databases/{NOTION_DATABASE_ID}/query"
    payload = {
        "filter": {
            "and": [
                {
                    "property": "Issue ID",
                    "rich_text": {
                        "equals": str(issue_id)
                    }
                },
                {
                    "property": "Repo",
                    "rich_text": {
                        "equals": repo
                    }
                },
            ]
        }
    }
    resp = requests.post(url, headers=NOTION_HEADERS, data=json.dumps(payload))
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    return results[0] if results else None


def build_properties(issue, repo_name):
    """
    Build Notion properties payload from GitHub issue.
    Adjust property names/types to match your DB exactly.
    """
    issue_title = issue["title"]
    issue_number = issue["number"]
    issue_url = issue["html_url"]
    issue_state = issue["state"]

    status_value = map_status(issue_state)

    return {
        "Name": {
            "title": [
                {"text": {"content": issue_title}}
            ]
        },
        "Issue ID": {
            "rich_text": [
                {"text": {"content": str(issue_number)}}
            ]
        },
        "Repo": {
            "rich_text": [
                {"text": {"content": repo_name}}
            ]
        },
        "URL": {
            "url": issue_url
        },
        "Status": {
            "select": {"name": status_value}
        },
        "Source": {
            "select": {"name": "RevGen"}
        }
    }


def create_notion_page(issue, repo_name):
    url = f"{NOTION_BASE_URL}/pages"
    properties = build_properties(issue, repo_name)
    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
    }
    resp = requests.post(url, headers=NOTION_HEADERS, data=json.dumps(payload))
    resp.raise_for_status()
    print(f"Created Notion page for issue #{issue['number']}")


def update_notion_page(page_id, issue, repo_name):
    url = f"{NOTION_BASE_URL}/pages/{page_id}"
    properties = build_properties(issue, repo_name)
    payload = {"properties": properties}
    resp = requests.patch(url, headers=NOTION_HEADERS, data=json.dumps(payload))
    resp.raise_for_status()
    print(f"Updated Notion page for issue #{issue['number']}")


def main():
    event = load_github_event()

    action = event.get("action")
    issue = event.get("issue")

    if not issue:
        print("No issue in event payload.")
        return

    repo_name = GITHUB_REPO_NAME.split("/")[-1] or "revgen-work-tracker"

    issue_number = issue["number"]

    # For edited/reopened/closed we update; for opened we create if missing
    existing_page = find_existing_page(issue_number, repo_name)

    if existing_page:
        update_notion_page(existing_page["id"], issue, repo_name)
    else:
        if action in ("opened", "reopened", "edited"):
            create_notion_page(issue, repo_name)
        else:
            print(f"No existing page and action is '{action}', doing nothing.")


if __name__ == "__main__":
    main()