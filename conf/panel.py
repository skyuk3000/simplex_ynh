#!/usr/bin/env python3
"""Read and update selected SimpleX configuration options for YunoHost."""
import re
import sys
from pathlib import Path

CONFIG = Path("/etc/opt/simplex/smp-server.ini")
FIELDS = {
    "smp_retention_days": ("STORE_LOG", "expire_messages_days"),
    "smp_stats_enabled": ("STORE_LOG", "log_stats"),
    "smp_operator_name": ("INFORMATION", "operator"),
    "smp_admin_contact": ("INFORMATION", "admin_email"),
}


def locate(lines, section, key):
    start = next((i for i, line in enumerate(lines)
                  if line.strip() == f"[{section}]"), None)
    if start is None:
        raise ValueError(f"Missing section [{section}]")
    end = next((i for i in range(start + 1, len(lines))
                if re.match(r"^\s*\[.*\]", lines[i])), len(lines))
    pat = re.compile(r"^\s*(#\s*)?" + re.escape(key) + r"\s*[:=]\s*(.*)$")
    candidates = [(i, pat.match(lines[i])) for i in range(start + 1, end)
                  if pat.match(lines[i])]
    active = next(((i, match) for i, match in candidates
                   if not match.group(1)), None)
    return start, end, candidates, active


def main():
    action, field, *rest = sys.argv[1:]
    if field not in FIELDS:
        raise ValueError("Unknown field")
    section, key = FIELDS[field]
    lines = CONFIG.read_text().splitlines(keepends=True)
    _, end, candidates, active = locate(lines, section, key)
    if action == "get":
        value = active[1].group(2).strip() if active else ""
        if not value and field == "smp_retention_days":
            value = "21"
        if not value and field == "smp_stats_enabled":
            value = "off"
        print({"on": "1", "off": "0"}.get(value.lower(), value))
        return
    if action != "set" or len(rest) != 1:
        raise ValueError("Expected get FIELD or set FIELD VALUE")
    value = rest[0].strip()
    if field == "smp_retention_days":
        if not value.isdecimal() or not 1 <= int(value) <= 365:
            raise ValueError("Message expiration must be between 1 and 365 days")
    elif field == "smp_stats_enabled":
        if value.lower() not in ("0", "1", "true", "false", "on", "off"):
            raise ValueError("Statistics setting must be boolean")
        value = "on" if value.lower() in ("1", "true", "on") else "off"
    elif field == "smp_operator_name":
        if len(value) > 120 or "\n" in value or "\r" in value:
            raise ValueError("Invalid operator name")
    elif field == "smp_admin_contact":
        if len(value) > 254 or (value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)):
            raise ValueError("Invalid email address")
    replacement = f"{key} = {value}\n" if value else ""
    if active:
        lines[active[0]] = replacement or "# " + lines[active[0]]
    elif candidates and replacement:
        lines[candidates[0][0]] = replacement
    elif replacement:
        lines.insert(end, replacement)
    CONFIG.write_text("".join(lines))


if __name__ == "__main__":
    main()
