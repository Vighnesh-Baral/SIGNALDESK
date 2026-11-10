"""Explicitly approved product-workflow integrations (Jira, Linear, GitHub, Notion).

All adapters support a dry-run preview. Real writes require provider credentials plus
an explicit confirm=true API request. Credentials are read from environment variables.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests

TIMEOUT = 20


class IntegrationNotConfiguredError(RuntimeError):
    pass


class IntegrationProviderError(RuntimeError):
    pass


def integration_status() -> dict[str, dict[str, Any]]:
    return {
        "jira": {"configured": bool(os.getenv("JIRA_BASE_URL") and os.getenv("JIRA_EMAIL") and os.getenv("JIRA_API_TOKEN") and os.getenv("JIRA_PROJECT_KEY")), "required_environment": ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"]},
        "linear": {"configured": bool(os.getenv("LINEAR_API_KEY") and os.getenv("LINEAR_TEAM_ID")), "required_environment": ["LINEAR_API_KEY", "LINEAR_TEAM_ID"]},
        "github": {"configured": bool(os.getenv("GITHUB_TOKEN") and os.getenv("GITHUB_REPOSITORY")), "required_environment": ["GITHUB_TOKEN", "GITHUB_REPOSITORY"], "repository": os.getenv("GITHUB_REPOSITORY", "")},
        "notion": {"configured": bool(os.getenv("NOTION_TOKEN") and (os.getenv("NOTION_PARENT_PAGE_ID") or os.getenv("NOTION_DATABASE_ID"))), "required_environment": ["NOTION_TOKEN", "NOTION_PARENT_PAGE_ID or NOTION_DATABASE_ID"]},
    }


def _document_for_finding(decision_pack: dict, finding_id: str | None = None) -> dict:
    cards = decision_pack.get("documents", [])
    if finding_id:
        match = next((item for item in cards if item.get("finding_id") == finding_id), None)
        if not match:
            raise ValueError("Finding ID was not found in this analysis.")
        return match
    if not cards:
        raise ValueError("No product decision documents are available for this analysis.")
    return cards[0]


def build_provider_preview(provider: str, document: dict) -> dict:
    theme = document["theme"]
    bug = document["bug_report_markdown"]
    prd = document["prd_markdown"]
    if provider == "jira":
        payload = {"fields": {"project": {"key": os.getenv("JIRA_PROJECT_KEY", "PROJECT")}, "summary": f"Investigate customer reports: {theme}"[:250], "issuetype": {"name": os.getenv("JIRA_ISSUE_TYPE", "Task")}, "description": {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": bug[:30000]}]}]}}}
    elif provider == "linear":
        payload = {"query": "mutation IssueCreate($input: IssueCreateInput!) { issueCreate(input: $input) { success issue { id identifier url } } }", "variables": {"input": {"teamId": os.getenv("LINEAR_TEAM_ID", "TEAM_ID"), "title": f"Investigate customer reports: {theme}"[:250], "description": bug[:30000]}}}
    elif provider == "github":
        payload = {"repository": os.getenv("GITHUB_REPOSITORY", "owner/repo"), "title": f"Investigate customer reports: {theme}"[:250], "body": bug[:60000], "labels": ["customer-feedback", "needs-triage"]}
    elif provider == "notion":
        parent_page = os.getenv("NOTION_PARENT_PAGE_ID", "")
        database = os.getenv("NOTION_DATABASE_ID", "")
        title_property = os.getenv("NOTION_TITLE_PROPERTY", "Name" if database else "title")
        parent = {"database_id": database} if database else {"page_id": parent_page or "PARENT_PAGE_ID"}
        payload = {"parent": parent, "properties": {title_property: {"title": [{"text": {"content": f"SIGNALDESK — {theme}"[:2000]}}]}}, "children": [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": prd[:1800]}}]}}]}
    else:
        raise ValueError("Provider must be one of: jira, linear, github, notion.")
    return {"provider": provider, "operation": "create_draft_item", "payload_preview": payload, "requires_user_approval": True, "note": "Preview only. No external item has been created."}


def create_provider_item(provider: str, document: dict) -> dict:
    status = integration_status().get(provider)
    if not status or not status["configured"]:
        raise IntegrationNotConfiguredError(f"{provider.title()} is not configured. Set the required environment variables first.")
    preview = build_provider_preview(provider, document)
    payload = preview["payload_preview"]
    if provider == "jira":
        base = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        response = requests.post(f"{base}/rest/api/3/issue", json=payload, auth=(os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN")), headers={"Accept": "application/json"}, timeout=TIMEOUT)
    elif provider == "linear":
        response = requests.post("https://api.linear.app/graphql", json=payload, headers={"Authorization": os.getenv("LINEAR_API_KEY", ""), "Content-Type": "application/json"}, timeout=TIMEOUT)
    elif provider == "github":
        repository = os.getenv("GITHUB_REPOSITORY", "")
        response = requests.post(f"https://api.github.com/repos/{quote(repository, safe='/')}/issues", json=payload, headers={"Authorization": f"Bearer {os.getenv('GITHUB_TOKEN', '')}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2026-03-10"}, timeout=TIMEOUT)
    else:
        response = requests.post("https://api.notion.com/v1/pages", json=payload, headers={"Authorization": f"Bearer {os.getenv('NOTION_TOKEN', '')}", "Notion-Version": os.getenv("NOTION_VERSION", "2022-06-28"), "Content-Type": "application/json"}, timeout=TIMEOUT)
    response.raise_for_status()
    body = response.json()
    if provider == "linear":
        issue = (body.get("data") or {}).get("issueCreate", {}).get("issue") or {}
        return {"provider": provider, "created": True, "id": issue.get("id"), "identifier": issue.get("identifier"), "url": issue.get("url")}
    return {"provider": provider, "created": True, "id": body.get("id") or body.get("key") or body.get("number"), "url": body.get("url") or body.get("html_url")}
