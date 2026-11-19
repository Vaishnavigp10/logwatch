"""Turns raw log text into LogEntry objects.

Expected line format:
    2026-11-19 10:15:32 INFO web-api 10.0.1.12 GET /cart status=200
"""
import re
from datetime import datetime

from .models import LogEntry

LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\s+"
    r"(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\s+"
    r"(\S+)\s+"
    r"(\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"(.*)$",
    re.IGNORECASE,
)
STATUS_RE = re.compile(r"status[=:\s]*(\d{3})", re.IGNORECASE)
FAILED_LOGIN_WORDS = ("login failed", "failed login", "invalid password", "authentication failed")


def parse_line(line):
    match = LINE_RE.match(line.strip())
    if not match:
        return None
    raw_ts, level, service, ip, message = match.groups()
    try:
        timestamp = datetime.strptime(raw_ts.replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    level = level.upper()
    if level == "WARNING":
        level = "WARN"
    status = STATUS_RE.search(message)
    lowered = message.lower()
    return LogEntry(
        timestamp=timestamp,
        level=level,
        service=service[:50],
        ip=ip,
        message=message[:500],
        status_code=int(status.group(1)) if status else None,
        is_failed_login=any(word in lowered for word in FAILED_LOGIN_WORDS),
    )


def parse_text(text):
    """Returns (entries, skipped_line_count)."""
    entries, skipped = [], 0
    for line in text.splitlines():
        if not line.strip():
            continue
        entry = parse_line(line)
        if entry is None:
            skipped += 1
        else:
            entries.append(entry)
    return entries, skipped


def render_line(entry):
    return (
        f"{entry.timestamp:%Y-%m-%d %H:%M:%S} {entry.level} "
        f"{entry.service} {entry.ip} {entry.message}"
    )
