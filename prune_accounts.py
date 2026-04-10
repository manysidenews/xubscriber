#!/usr/bin/env python3
"""Remove usernames from a source file when they already exist in an added file."""

from __future__ import annotations

import argparse
from pathlib import Path


def normalize_username(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith("@"):
        value = value[1:]
    return value.lower()


def parse_usernames(path: Path) -> list[str]:
    if not path.exists():
        return []

    usernames: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        username_part = line.split("#", 1)[0].strip()
        normalized = normalize_username(username_part)
        if normalized:
            usernames.append(normalized)

    return usernames


def prune_accounts(source_file: Path, added_file: Path) -> tuple[int, int]:
    added_usernames = set(parse_usernames(added_file))

    if not source_file.exists():
        raise FileNotFoundError(f"Source file not found: {source_file}")

    source_lines = source_file.read_text(encoding="utf-8").splitlines()

    kept_lines: list[str] = []
    removed_count = 0

    for line in source_lines:
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            kept_lines.append(line)
            continue

        username_part = stripped.split("#", 1)[0].strip()
        normalized = normalize_username(username_part)

        if normalized and normalized in added_usernames:
            removed_count += 1
            continue

        kept_lines.append(line)

    source_file.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")
    return removed_count, len(source_lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Remove usernames from the source accounts file when they already "
            "exist in the added accounts file."
        )
    )
    parser.add_argument(
        "--accounts-file",
        default="accounts.txt",
        help='Path to source accounts file (default: "accounts.txt")',
    )
    parser.add_argument(
        "--added-accounts-file",
        default="accounts added.txt",
        help='Path to added accounts file (default: "accounts added.txt")',
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    source_file = Path(args.accounts_file)
    added_file = Path(args.added_accounts_file)

    removed_count, total_lines = prune_accounts(source_file, added_file)

    print(
        f"Done. Removed {removed_count} entr{'y' if removed_count == 1 else 'ies'} "
        f"from {source_file} using {added_file}."
    )
    print(f"Processed {total_lines} line(s) from {source_file}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
