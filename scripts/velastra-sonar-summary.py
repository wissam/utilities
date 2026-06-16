#!/usr/bin/env python3
"""Export compact SonarQube metrics and issue counts for Velastra projects."""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_HOST = "http://10.0.0.189:9000"
DEFAULT_REPORT_DIR = Path("/tmp/velastra-sonar-scan")
METRICS = [
    "bugs",
    "vulnerabilities",
    "code_smells",
    "coverage",
    "duplicated_lines_density",
    "ncloc",
    "sqale_index",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", default=[], help="Project key to include. Repeatable.")
    parser.add_argument("--include-archived", action="store_true", help="Include archived scan targets from config.")
    parser.add_argument("--config", default=os.environ.get("VELASTRA_SONAR_PROJECTS_FILE", str(default_config())))
    parser.add_argument("--host-url", default=os.environ.get("SONAR_HOST_URL", DEFAULT_HOST))
    parser.add_argument("--report-dir", default=os.environ.get("VELASTRA_SONAR_REPORT_DIR", str(DEFAULT_REPORT_DIR)))
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", help="Write output to this path instead of stdout.")
    return parser.parse_args()


def default_config() -> Path:
    script = Path(__file__).resolve()
    candidates = [
        script.parents[1] / "share" / "velastra-sonar" / "projects.tsv",
        script.parents[1] / "config" / "velastra-sonar-projects.tsv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def env_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def fetch_token() -> str:
    token = env_value("SONAR_TOKEN", "SONARQUBE_TOKEN")
    if token:
        return token

    host = env_value("SONAR_TOKEN_HOST", default="ubuntu@10.0.0.189")
    token_file = env_value("SONAR_TOKEN_FILE", default="/home/ubuntu/sonarqube-credentials.txt")
    ssh_config = env_value("SONAR_TOKEN_SSH_CONFIG", default="/dev/null")
    remote_cmd = "awk -F= '/^scanner_token=/ {print $2; exit}' " + shlex.quote(token_file)
    try:
        return subprocess.check_output(
            ["ssh", "-F", ssh_config, host, remote_cmd],
            stdin=subprocess.DEVNULL,
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        hint = "set SONAR_TOKEN/SONARQUBE_TOKEN or fix SONAR_TOKEN_HOST/SONAR_TOKEN_FILE"
        if detail:
            raise SystemExit(f"failed to fetch SonarQube token over SSH: {detail}; {hint}") from exc
        raise SystemExit(f"failed to fetch SonarQube token over SSH; {hint}") from exc


def auth_header(token: str) -> str:
    return "Basic " + base64.b64encode(f"{token}:".encode("utf-8")).decode("ascii")


def sonar_get(host_url: str, token: str, path: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"{host_url.rstrip('/')}{path}?{query}"
    req = urllib.request.Request(url, headers={"Authorization": auth_header(token), "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"sonarqube request failed: HTTP {exc.code}: {detail}") from exc


def load_projects(config: Path, include_archived: bool, filters: set[str]) -> list[dict[str, str]]:
    projects: list[dict[str, str]] = []
    with config.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.startswith("#")),
            fieldnames=["key", "name", "relative_path", "sources", "tests", "run_go_tests", "archived"],
            delimiter="\t",
        )
        for row in reader:
            if row["archived"].lower() == "true" and not include_archived:
                continue
            if filters and row["key"] not in filters:
                continue
            projects.append(row)
    return projects


def project_measures(host_url: str, token: str, key: str) -> dict[str, str]:
    payload = sonar_get(
        host_url,
        token,
        "/api/measures/component",
        {"component": key, "metricKeys": ",".join(METRICS)},
    )
    return {measure["metric"]: measure.get("value", "") for measure in payload.get("component", {}).get("measures", [])}


def open_issue_count(host_url: str, token: str, key: str) -> int:
    payload = sonar_get(
        host_url,
        token,
        "/api/issues/search",
        {"componentKeys": key, "issueStatuses": "OPEN", "ps": "1"},
    )
    return int(payload.get("paging", {}).get("total", 0))


def collect(args: argparse.Namespace) -> list[dict[str, object]]:
    token = fetch_token()
    projects = load_projects(Path(args.config).expanduser(), args.include_archived, set(args.project))
    rows: list[dict[str, object]] = []
    for project in projects:
        measures = project_measures(args.host_url, token, project["key"])
        rows.append(
            {
                "key": project["key"],
                "name": project["name"],
                "open_issues": open_issue_count(args.host_url, token, project["key"]),
                **{metric: measures.get(metric, "") for metric in METRICS},
            }
        )
    return rows


def markdown(rows: list[dict[str, object]]) -> str:
    lines = [
        "# Velastra SonarQube Summary",
        "",
        "| Project | Issues | Smells | Bugs | Vulns | Coverage | Dup % | ncloc | Debt min |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {key} | {open_issues} | {code_smells} | {bugs} | {vulnerabilities} | "
            "{coverage} | {duplicated_lines_density} | {ncloc} | {sqale_index} |".format(**row)
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    rows = collect(args)
    output = json.dumps(rows, indent=2) + "\n" if args.format == "json" else markdown(rows)
    if args.output:
        path = Path(args.output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
