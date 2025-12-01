#!/usr/bin/env python3
"""
Discover all repos from your GitHub organizations.
Run this to see available repos, then add them to sync_all_repos.py

Usage:
    export GITHUB_TOKEN="your-token"
    python scripts/discover_repos.py
"""

import os
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_API_BASE = "https://api.github.com"

# =============================================================================
# YOUR ORGANIZATIONS - add/remove as needed
# =============================================================================
ORGS = [
    "Akels-Carpet-One",
    "DeliveryKick",
    "VPC-PII",
]
# =============================================================================


def get_github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_org_repos(org_name: str):
    """Get all repos from an organization."""
    all_repos = []
    page = 1

    while True:
        url = f"{GITHUB_API_BASE}/orgs/{org_name}/repos"
        params = {"per_page": 100, "page": page}
        resp = requests.get(url, headers=get_github_headers(), params=params)

        if resp.status_code != 200:
            break

        repos = resp.json()
        if not repos:
            break

        all_repos.extend(repos)
        if len(repos) < 100:
            break
        page += 1

    return all_repos


def get_user_repos():
    """Get user's personal repos."""
    all_repos = []
    page = 1

    while True:
        url = f"{GITHUB_API_BASE}/user/repos"
        params = {"per_page": 100, "page": page, "affiliation": "owner"}
        resp = requests.get(url, headers=get_github_headers(), params=params)

        if resp.status_code != 200:
            break

        repos = resp.json()
        if not repos:
            break

        all_repos.extend(repos)
        if len(repos) < 100:
            break
        page += 1

    return all_repos


def main():
    if not GITHUB_TOKEN:
        print("ERROR: GITHUB_TOKEN not set")
        print("Run: export GITHUB_TOKEN='your-token'")
        return

    print("=" * 60)
    print("🔍 GitHub Repository Discovery")
    print("=" * 60)

    all_repos = []

    # Get repos from configured orgs
    print(f"\n📁 Scanning {len(ORGS)} organizations...")

    for org_name in ORGS:
        repos = get_org_repos(org_name)
        print(f"\n🏢 {org_name} ({len(repos)} repos)")
        print("-" * 40)

        for repo in sorted(repos, key=lambda r: r["name"]):
            full_name = repo["full_name"]
            has_issues = "✓" if repo.get("has_issues") else "✗"
            open_issues = repo.get("open_issues_count", 0)
            print(f"  {has_issues} {full_name} ({open_issues} open issues)")
            all_repos.append(full_name)

    # Get personal repos
    print(f"\n👤 Personal Repos")
    print("-" * 40)
    personal = get_user_repos()
    for repo in sorted(personal, key=lambda r: r["name"]):
        full_name = repo["full_name"]
        has_issues = "✓" if repo.get("has_issues") else "✗"
        open_issues = repo.get("open_issues_count", 0)
        print(f"  {has_issues} {full_name} ({open_issues} open issues)")
        all_repos.append(full_name)

    # Print config snippet
    print("\n" + "=" * 60)
    print("📋 Copy this to sync_all_repos.py REPOS list:")
    print("=" * 60)
    print("\nREPOS = [")
    for repo in all_repos:
        print(f'    "{repo}",')
    print("]")

    print("\n📋 Source mapping template:")
    print("=" * 60)
    print("\nREPO_SOURCE_MAP = {")
    for repo in all_repos:
        repo_name = repo.split("/")[-1]
        print(f'    "{repo_name}": "{repo_name}",')
    print("}")


if __name__ == "__main__":
    main()
