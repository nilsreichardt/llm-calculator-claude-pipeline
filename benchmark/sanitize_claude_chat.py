#!/usr/bin/env python3
"""Sanitize Claude Code JSONL chat files before sharing them.

The default output is a compact JSONL transcript containing only visible user
and assistant text. Claude Code tool calls, tool results, thinking blocks,
attachments, IDs, cwd/session metadata, usage data, and title bookkeeping are
omitted from the default transcript.

Use ``--mode jsonl`` when you need to preserve the original record shape while
redacting sensitive fields.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


HOME = str(Path.home())

PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)

REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (PRIVATE_KEY_RE, "[REDACTED_PRIVATE_KEY]"),
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{8,}\b"), "sk-[REDACTED]"),
    (re.compile(r"\b(?:claude|anthropic)-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "github_pat_[REDACTED]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "gh_[REDACTED]"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}\b"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"\bssh-(?:rsa|ed25519)\s+[A-Za-z0-9+/=]+(?:\s+\S+)?"), "[REDACTED_SSH_PUBLIC_KEY]"),
]

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Za-z0-9_.-]*(?:api[_-]?key|token|secret|password|passwd|private[_-]?key)"
    r"[A-Za-z0-9_.-]*)\s*([:=])\s*([\"']?)([^\s,\"';}\])]+)\3"
)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
ENV_FILENAME_RE = re.compile(r"(?<![A-Za-z0-9_.-])\.env(?:\.[A-Za-z0-9_.-]+)?(?![A-Za-z0-9_.-])")
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
ISO_TIMESTAMP_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b"
)
LONG_OPAQUE_TOKEN_RE = re.compile(r"\b[A-Za-z0-9+/]{160,}={0,2}\b")

TIMESTAMP_KEYS = {"timestamp", "createdAt", "updatedAt"}
ID_KEYS = {
    "id",
    "uuid",
    "parentUuid",
    "leafUuid",
    "promptId",
    "requestId",
    "sessionId",
    "sourceToolAssistantUUID",
}
DROP_KEYS = {
    "attachment",
    "cwd",
    "diagnostics",
    "entrypoint",
    "gitBranch",
    "permissionMode",
    "stop_details",
    "toolUseResult",
    "usage",
    "userType",
    "version",
}
REDACTED_KEYS = {"signature", "thinking"}
DROP_RECORD_TYPES = {"attachment", "custom-title", "ai-title", "last-prompt", "queue-operation"}
DROP_CONTENT_TYPES = {"thinking", "tool_use", "tool_result"}


def redact_paths(text: str) -> str:
    if HOME:
        text = text.replace(HOME, "~")
    text = re.sub(r"/Users/[^/\"'\s]+", "/Users/[USER]", text)
    text = re.sub(r"/home/[^/\"'\s]+", "/home/[USER]", text)
    text = re.sub(r"/var/folders/[^\"'\s]+", "/var/folders/[REDACTED]", text)
    text = re.sub(r"[A-Za-z]:\\Users\\[^\\\"'\s]+", r"C:\\Users\\[USER]", text)
    return text


def redact_text(text: str, *, keep_timestamps: bool) -> str:
    text = redact_paths(text)
    text = SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)
    for pattern, replacement in REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = IP_RE.sub("[REDACTED_IP]", text)
    text = ENV_FILENAME_RE.sub("[REDACTED_ENV_FILE]", text)
    text = UUID_RE.sub("[REDACTED_ID]", text)
    text = LONG_OPAQUE_TOKEN_RE.sub("[REDACTED_OPAQUE_TOKEN]", text)
    if not keep_timestamps:
        text = ISO_TIMESTAMP_RE.sub("[REDACTED_TIMESTAMP]", text)
    return text


def parse_jsonl(path: Path) -> list[dict[str, Any]] | None:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                return None
            if not isinstance(record, dict):
                raise SystemExit(f"{path}:{line_number}: expected each JSONL record to be an object")
            records.append(record)
    return records


def extract_visible_text(content: Any, *, keep_timestamps: bool) -> str:
    if isinstance(content, str):
        return redact_text(content, keep_timestamps=keep_timestamps).strip()

    pieces: list[str] = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                pieces.append(item["text"])
    return redact_text("\n".join(piece for piece in pieces if piece), keep_timestamps=keep_timestamps).strip()


def transcript_records(
    records: list[dict[str, Any]],
    *,
    keep_timestamps: bool,
    include_tool_results: bool,
) -> list[dict[str, str]]:
    transcript: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for record in records:
        if record.get("type") not in {"user", "assistant"}:
            continue

        message = record.get("message")
        if not isinstance(message, dict):
            continue

        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue

        content = message.get("content")
        if include_tool_results:
            text = redact_text(json.dumps(content, ensure_ascii=False), keep_timestamps=keep_timestamps)
        else:
            text = extract_visible_text(content, keep_timestamps=keep_timestamps)
        if not text:
            continue

        dedupe_key = (role, text)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        item = {"role": role, "content": text}
        if keep_timestamps and isinstance(record.get("timestamp"), str):
            item["timestamp"] = redact_text(record["timestamp"], keep_timestamps=True)
        transcript.append(item)

    return transcript


def sanitize_json(value: Any, *, keep_timestamps: bool) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            clean_key = redact_text(str(key), keep_timestamps=keep_timestamps)
            if key in DROP_KEYS:
                continue
            if key in ID_KEYS:
                sanitized[clean_key] = "[REDACTED_ID]"
            elif key in TIMESTAMP_KEYS and not keep_timestamps:
                sanitized[clean_key] = "[REDACTED_TIMESTAMP]"
            elif key in REDACTED_KEYS:
                sanitized[clean_key] = f"[REDACTED_{key.upper()}]"
            elif key == "content" and isinstance(value.get("type"), str) and value["type"] in DROP_CONTENT_TYPES:
                sanitized[clean_key] = f"[REDACTED_{value['type'].upper()}]"
            else:
                sanitized[clean_key] = sanitize_json(item, keep_timestamps=keep_timestamps)
        return sanitized

    if isinstance(value, list):
        cleaned_items: list[Any] = []
        for item in value:
            if isinstance(item, dict) and item.get("type") in DROP_CONTENT_TYPES:
                cleaned_items.append({"type": item.get("type"), "content": f"[REDACTED_{item.get('type', 'CONTENT').upper()}]"})
            else:
                cleaned_items.append(sanitize_json(item, keep_timestamps=keep_timestamps))
        return cleaned_items

    if isinstance(value, str):
        return redact_text(value, keep_timestamps=keep_timestamps)
    return value


def sanitized_jsonl_records(
    records: list[dict[str, Any]],
    *,
    keep_timestamps: bool,
    keep_metadata_records: bool,
) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for record in records:
        if not keep_metadata_records and record.get("type") in DROP_RECORD_TYPES:
            continue
        sanitized.append(sanitize_json(record, keep_timestamps=keep_timestamps))
    return sanitized


def write_jsonl(records: list[dict[str, Any]], output: Path | None) -> None:
    handle = output.open("w", encoding="utf-8") if output else sys.stdout
    try:
        for record in records:
            print(json.dumps(record, ensure_ascii=False, sort_keys=False), file=handle)
    finally:
        if output:
            handle.close()


def write_text(text: str, output: Path | None) -> None:
    if output:
        output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a privacy-friendlier version of a Claude Code chat file.")
    parser.add_argument("chat_file", type=Path, help="Path to the Claude Code JSONL chat file.")
    parser.add_argument("-o", "--output", type=Path, help="Write sanitized output to this file. Defaults to stdout.")
    parser.add_argument(
        "--mode",
        choices=("transcript", "jsonl"),
        default="transcript",
        help="transcript keeps visible user/assistant text; jsonl preserves redacted records.",
    )
    parser.add_argument(
        "--keep-timestamps",
        action="store_true",
        help="Keep timestamps instead of replacing them with [REDACTED_TIMESTAMP].",
    )
    parser.add_argument(
        "--include-tool-results",
        action="store_true",
        help="Transcript mode only: include sanitized raw message content, including tool results.",
    )
    parser.add_argument(
        "--keep-metadata-records",
        action="store_true",
        help="JSONL mode only: keep redacted attachment/title/queue metadata records.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    chat_file: Path = args.chat_file
    if not chat_file.exists():
        raise SystemExit(f"Input file does not exist: {chat_file}")
    if not chat_file.is_file():
        raise SystemExit(f"Input path is not a file: {chat_file}")

    records = parse_jsonl(chat_file)
    if records is None:
        text = chat_file.read_text(encoding="utf-8")
        write_text(redact_text(text, keep_timestamps=args.keep_timestamps), args.output)
        return 0

    if args.mode == "transcript":
        output_records = transcript_records(
            records,
            keep_timestamps=args.keep_timestamps,
            include_tool_results=args.include_tool_results,
        )
    else:
        output_records = sanitized_jsonl_records(
            records,
            keep_timestamps=args.keep_timestamps,
            keep_metadata_records=args.keep_metadata_records,
        )
    write_jsonl(output_records, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
