#!/usr/bin/env python3
"""
Backfill all existing GitHub issues to Notion.
Run this once to sync all existing issues, then the workflows handle ongoing sync.

Usage:
    export NOTION_API_KEY="your-key"
    export NOTION_DATABASE_ID="your-db-id"
    export GITHUB_TOKEN="your-token"
    export GITHUB_REPO_NAME="owner/repo"
    python scripts/backfill_issues_to_notion.py
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from scripts.sync_issue_to_notion import (
    GITHUB_API_BASE,
    get_github_headers,
    get_issue_comments,
    find_existing_page,
    create_notion_page,
    update_notion_page,
    GITHUB_TOKEN,
    GITHUB_REPO_NAME,
)


def get_all_issues(owner: str, repo: str) -> list:
    """Fetch all issues (open and closed) from GitHub."""
    all_issues = []
    page = 1
    per_page = 100

    for state in ["open", "closed"]:
        page = 1
        while True:
            url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"
            params = {
                "state": state,
                "per_page": per_page,
                "page": page,
            }
            resp = requests.get(url, headers=get_github_headers(), params=params)

            if resp.status_code != 200:
                print(f"Error fetching issues: {resp.status_code}")
                break

            issues = resp.json()
            if not issues:
                break

            # Filter out pull requests (they also appear in issues endpoint)
            issues = [i for i in issues if "pull_request" not in i]
            all_issues.extend(issues)

            print(f"Fetched page {page} of {state} issues ({len(issues)} issues)")

            if len(issues) < per_page:
                break
            page += 1

    return all_issues


def backfill():
    """Backfill all existing GitHub issues to Notion."""
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN not set")
        sys.exit(1)

    if not GITHUB_REPO_NAME:
        print("ERROR: GITHUB_REPO_NAME not set")
        sys.exit(1)

    owner, repo_name = GITHUB_REPO_NAME.split("/") if "/" in GITHUB_REPO_NAME else ("", GITHUB_REPO_NAME)

    if not owner:
        print("ERROR: GITHUB_REPO_NAME must be in format 'owner/repo'")
        sys.exit(1)

    print(f"Backfilling issues from {owner}/{repo_name} to Notion...")
    print("-" * 50)

    # Get all issues
    issues = get_all_issues(owner, repo_name)
    print(f"\nFound {len(issues)} issues to sync")
    print("-" * 50)

    created = 0
    updated = 0
    errors = 0

    for issue in issues:
        issue_number = issue["number"]
        issue_title = issue["title"][:50]

        try:
            # Get comments for this issue
            comments = get_issue_comments(owner, repo_name, issue_number)

            # Check if page exists
            existing_page = find_existing_page(issue_number, repo_name)

            if existing_page:
                update_notion_page(existing_page["id"], issue, repo_name, comments)
                updated += 1
                print(f"  Updated: #{issue_number} - {issue_title}...")
            else:
                create_notion_page(issue, repo_name, comments)
                created += 1
                print(f"  Created: #{issue_number} - {issue_title}...")

        except Exception as e:
            errors += 1
            print(f"  ERROR: #{issue_number} - {e}")

    print("-" * 50)
    print(f"Backfill complete!")
    print(f"  Created: {created}")
    print(f"  Updated: {updated}")
    print(f"  Errors: {errors}")


if __name__ == "__main__":
    backfill()
