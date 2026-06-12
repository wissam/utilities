#!/usr/bin/env python3
"""Rank Linear issues compactly for Codex/operator planning.

Read-only helper. Uses Linear GraphQL directly because the MCP list output can
be too verbose for broad cross-team prioritization.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"


QUERY = """
query RankIssues($first: Int!, $after: String, $filter: IssueFilter) {
  issues(first: $first, after: $after, filter: $filter) {
    nodes {
      identifier
      title
      priority
      state { name type }
      team { key name }
      project { name }
      labels { nodes { name } }
      updatedAt
      url
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


PRIORITY_NAMES = {
    0: "None",
    1: "Urgent",
    2: "High",
    3: "Medium",
    4: "Low",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rank Linear Todo/Backlog issues compactly.")
    parser.add_argument("--team", action="append", default=[], help="Linear team key, repeatable.")
    parser.add_argument("--state", action="append", default=["Todo", "Backlog"], help="State name, repeatable.")
    parser.add_argument("--label", action="append", default=[], help="Required label name, repeatable.")
    parser.add_argument("--project", action="append", default=[], help="Project name filter, repeatable.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum issues to print.")
    parser.add_argument("--page-size", type=int, default=100, help="Linear GraphQL page size.")
    parser.add_argument("--token-file", help="Path to a file containing a Linear API token.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of compact rows.")
    return parser.parse_args()


def token(args: argparse.Namespace) -> str:
    if args.token_file:
        value = Path(args.token_file).expanduser().read_text(encoding="utf-8").strip()
        if value:
            return value
    for name in ("LINEAR_API_KEY", "LINEAR_API_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    token_path = Path.home() / ".config" / "linear" / "token"
    legacy_codex_path = Path.home() / "code" / "agents" / "codex" / "linear-api.txt"
    for path in (token_path, legacy_codex_path):
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
    raise SystemExit("missing Linear token: set LINEAR_API_KEY, LINEAR_API_TOKEN, or ~/.config/linear/token")


def issue_filter(args: argparse.Namespace) -> dict:
    filters: list[dict] = []
    if args.team:
        filters.append({"team": {"key": {"in": args.team}}})
    if args.state:
        filters.append({"state": {"name": {"in": args.state}}})
    for label in args.label:
        filters.append({"labels": {"name": {"eq": label}}})
    if args.project:
        filters.append({"project": {"name": {"in": args.project}}})
    if not filters:
        return {}
    if len(filters) == 1:
        return filters[0]
    return {"and": filters}


def graphql(api_token: str, variables: dict) -> dict:
    body = json.dumps({"query": QUERY, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        LINEAR_GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": api_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"linear graphql failed: HTTP {exc.code}: {detail}") from exc
    if payload.get("errors"):
        raise SystemExit("linear graphql failed: " + json.dumps(payload["errors"], indent=2))
    return payload["data"]


def fetch(args: argparse.Namespace) -> list[dict]:
    api_token = token(args)
    results: list[dict] = []
    after = None
    filt = issue_filter(args)
    while len(results) < args.limit:
        data = graphql(api_token, {"first": args.page_size, "after": after, "filter": filt})
        page = data["issues"]
        results.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return sorted(results, key=sort_key)[: args.limit]


def sort_key(issue: dict) -> tuple:
    priority = issue.get("priority")
    if priority is None or priority == 0:
        priority = 99
    state_name = issue.get("state", {}).get("name", "")
    state_order = {"Todo": 0, "Backlog": 1}.get(state_name, 9)
    return (priority, state_order, issue.get("team", {}).get("key", ""), issue.get("identifier", ""))


def compact(issue: dict, index: int) -> str:
    labels = ",".join(label["name"] for label in issue.get("labels", {}).get("nodes", []))
    project = issue.get("project") or {}
    state = issue.get("state") or {}
    team = issue.get("team") or {}
    priority = PRIORITY_NAMES.get(issue.get("priority"), str(issue.get("priority")))
    return (
        f"{index:02d}. {issue['identifier']} P{issue.get('priority', 0)} {priority} "
        f"{state.get('name', '-')} {team.get('key', '-')} "
        f"[{labels or '-'}] {project.get('name', '-')}: {issue['title']}"
    )


def main() -> int:
    args = parse_args()
    issues = fetch(args)
    if args.json:
        print(json.dumps(issues, indent=2))
        return 0
    for index, issue in enumerate(issues, 1):
        print(compact(issue, index))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
