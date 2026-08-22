#!/usr/bin/env python3
"""Export a redacted, bounded dialogue corpus from one Codex rollout JSONL.

Origin: first-generation Wissam/Codex interaction-continuity recovery on
2026-08-22.
Purpose: retain only visible user/assistant dialogue needed for continuity
analysis while preventing raw rollout payloads, tool arguments, credentials,
and opaque secret-like values from entering downstream model context.

Assumptions and limitations:
- Reads only ``event_msg`` user_message and agent_message records.
- Drops system, developer, tool, reasoning, attachment, image, and audio data.
- Redaction is deliberately aggressive and may remove harmless technical text.
- Output is JSONL and must be a new file. It is still private continuity data.
- This is an intake script, not a production security boundary or Veldream.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any


TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z$"
)
PEM_RE = re.compile(
    r"-----BEGIN [^-\n]+-----.*?-----END [^-\n]+-----", re.DOTALL
)
AUTH_RE = re.compile(
    r"(?i)\b(authorization|proxy-authorization)\s*:\s*[^\s\r\n]+(?:\s+[^\s\r\n]+)?"
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?key|client[_-]?secret|credential|password|"
    r"private[_-]?key|secret|token)\b\s*[:=]\s*([^\s,;]+|\"[^\"]*\"|'[^']*')"
)
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\b")
URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@")
URL_QUERY_RE = re.compile(r"(?i)\b(https?://[^\s?#]+)[?#][^\s]+")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PROTECTED_PATH_RE = re.compile(
    r"(?i)(?:^|[\s'\"])([^\s'\"]*(?:\.env(?:\.[^/\s'\"]+)?|"
    r"credentials?|passwords?|private[_-]?keys?|secrets?|tokens?)[^\s'\"]*)"
)
OPAQUE_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_+/=-]{48,}(?![A-Za-z0-9])")
PRIVATE_KEY_HINT_RE = re.compile(
    r"(?i)\b(private key|client secret|access token|refresh token|bearer token|"
    r"api key|password|credential)\b"
)


def redact(text: str) -> tuple[str, int]:
    replacements = 0

    def sub(pattern: re.Pattern[str], replacement: str, value: str) -> str:
        nonlocal replacements
        value, count = pattern.subn(replacement, value)
        replacements += count
        return value

    text = text.replace("\x00", "")
    text = sub(PEM_RE, "[REDACTED_PRIVATE_MATERIAL]", text)
    text = sub(AUTH_RE, "[REDACTED_AUTHORIZATION]", text)
    text = sub(SENSITIVE_ASSIGNMENT_RE, r"\1=[REDACTED]", text)
    text = sub(JWT_RE, "[REDACTED_TOKEN]", text)
    text = sub(URL_CREDENTIAL_RE, r"\1[REDACTED]@", text)
    text = sub(URL_QUERY_RE, r"\1[REDACTED_QUERY]", text)
    text = sub(EMAIL_RE, "[REDACTED_EMAIL]", text)
    text = sub(PROTECTED_PATH_RE, " [REDACTED_PROTECTED_PATH]", text)
    text = sub(OPAQUE_RE, "[REDACTED_OPAQUE_VALUE]", text)

    safe_lines: list[str] = []
    for line in text.splitlines():
        # Fail closed for likely copied credential material that survived the
        # structured substitutions. Policy discussion remains usable because
        # it normally does not combine a sensitive phrase with a long value.
        if PRIVATE_KEY_HINT_RE.search(line) and OPAQUE_RE.search(line):
            safe_lines.append("[REDACTED_SENSITIVE_LINE]")
            replacements += 1
        else:
            safe_lines.append(line.rstrip())
    return "\n".join(safe_lines).strip(), replacements


def extract_message(event: dict[str, Any]) -> tuple[str, str] | None:
    if event.get("type") != "event_msg":
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    payload_type = payload.get("type")
    if payload_type == "user_message":
        role = "user"
    elif payload_type == "agent_message":
        role = "assistant"
    else:
        return None
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    return role, message


def open_new_output(path: Path):
    if path.suffix != ".jsonl" or path.exists() or path.is_symlink():
        raise SystemExit("output must be a new, non-symlinked .jsonl file")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise SystemExit("output parent must be an existing, non-symlinked directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    return os.fdopen(descriptor, "w", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rollout", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-message-chars", type=int, default=16000)
    args = parser.parse_args()
    if args.max_message_chars < 1000 or args.max_message_chars > 100000:
        raise SystemExit("--max-message-chars must be between 1000 and 100000")

    records = 0
    redactions = 0
    truncations = 0
    parse_errors = 0
    previous_fingerprint: str | None = None

    with args.rollout.open(encoding="utf-8") as source, open_new_output(args.output) as target:
        for line_number, line in enumerate(source, start=1):
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                parse_errors += 1
                continue
            if not isinstance(event, dict):
                parse_errors += 1
                continue
            extracted = extract_message(event)
            if extracted is None:
                continue
            role, raw_message = extracted
            message, count = redact(raw_message)
            redactions += count
            if not message:
                continue
            truncated = len(message) > args.max_message_chars
            if truncated:
                message = message[: args.max_message_chars].rstrip() + "\n[TRUNCATED]"
                truncations += 1
            fingerprint = hashlib.sha256((role + "\0" + message).encode()).hexdigest()
            if fingerprint == previous_fingerprint:
                continue
            previous_fingerprint = fingerprint
            timestamp = event.get("timestamp")
            if not isinstance(timestamp, str) or not TIMESTAMP_RE.fullmatch(timestamp):
                timestamp = None
            record = {
                "schema": "codex-redacted-dialogue.v1",
                "ordinal": records + 1,
                "timestamp": timestamp,
                "role": role,
                "text": message,
                "truncated": truncated,
                "source_line": line_number,
                "content_sha256": fingerprint,
            }
            target.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            records += 1

    print(json.dumps({
        "schema": "codex-redacted-dialogue-export-report.v1",
        "records": records,
        "redactions": redactions,
        "truncations": truncations,
        "parse_errors": parse_errors,
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
