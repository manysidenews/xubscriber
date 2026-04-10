#!/usr/bin/env python3
"""
xubscriber - Follow a list of Twitter/X accounts via UI automation.
Run login.py first to create a saved browser session, then run this.

Usage:
    python follow.py accounts.txt
    python follow.py accounts.txt --delay 2.5   # seconds between actions
    python follow.py accounts.txt --report report.json
"""

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


class Status(str, Enum):
    FOLLOWED = "followed"
    ALREADY_FOLLOWING = "already_following"
    NOT_FOUND = "not_found"
    FAILED = "failed"


@dataclass
class AccountResult:
    username: str
    status: Status
    note: str = ""


@dataclass
class Report:
    followed: list[str] = field(default_factory=list)
    already_following: list[str] = field(default_factory=list)
    not_found: list[str] = field(default_factory=list)
    failed: list[AccountResult] = field(default_factory=list)


PROFILE_URL = "https://x.com/{username}"

CHROME_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
]

# Aria-label patterns — more stable than data-testid across X UI updates
FOLLOW_LABEL    = re.compile(r"^Follow\b", re.IGNORECASE)   # "Follow @user"
FOLLOWING_LABEL = re.compile(r"^Following\b", re.IGNORECASE)  # "Following @user" (hover state)
UNFOLLOW_LABEL  = re.compile(r"^Unfollow\b", re.IGNORECASE)

NOT_FOUND_SELECTOR = '[data-testid="emptyState"]'
USER_NAME_SELECTOR = '[data-testid="UserName"]'
SCREENSHOTS_DIR = Path("./screenshots")


def load_accounts(path: str) -> list[str]:
    accounts = []
    for line in Path(path).read_text().splitlines():
        line = line.strip().lstrip("@")
        if line and not line.startswith("#"):
            accounts.append(line)
    return accounts


def parse_username_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    return stripped.lstrip("@")


def move_processed_accounts(accounts_file: str, added_file: str, report: Report) -> tuple[int, int, int]:
    """
    Move followed and already-following usernames from accounts_file to added_file.

    Returns:
        (removed_count, appended_count, already_present_count)
    """
    ordered_to_move: list[str] = []
    seen: set[str] = set()
    for username in report.followed + report.already_following:
        key = username.lower()
        if key not in seen:
            seen.add(key)
            ordered_to_move.append(username)

    if not ordered_to_move:
        return 0, 0, 0

    move_keys = {u.lower() for u in ordered_to_move}

    source_path = Path(accounts_file)
    source_lines = source_path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept_lines: list[str] = []
    removed_count = 0
    for line in source_lines:
        username = parse_username_line(line)
        if username and username.lower() in move_keys:
            removed_count += 1
            continue
        kept_lines.append(line)
    source_path.write_text("".join(kept_lines), encoding="utf-8")

    target_path = Path(added_file)
    if not target_path.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.touch()
    existing_text = target_path.read_text(encoding="utf-8")
    existing_usernames: set[str] = set()
    for line in existing_text.splitlines():
        username = parse_username_line(line)
        if username:
            existing_usernames.add(username.lower())

    lines_to_append: list[str] = []
    already_present_count = 0
    for username in ordered_to_move:
        key = username.lower()
        if key in existing_usernames:
            already_present_count += 1
            continue
        lines_to_append.append(f"@{username}")
        existing_usernames.add(key)

    appended_count = len(lines_to_append)
    if appended_count:
        with target_path.open("a", encoding="utf-8") as f:
            if existing_text and not existing_text.endswith("\n"):
                f.write("\n")
            f.write("\n".join(lines_to_append))
            f.write("\n")

    return removed_count, appended_count, already_present_count


def prune_accounts_already_added(accounts_file: str, added_file: str) -> int:
    """
    Remove usernames from accounts_file if they already exist in added_file.

    Matching is case-insensitive and ignores an optional leading '@'.
    Returns the number of removed username lines.
    """
    added_path = Path(added_file)
    if not added_path.exists():
        return 0

    added_usernames: set[str] = set()
    for line in added_path.read_text(encoding="utf-8").splitlines():
        username = parse_username_line(line)
        if username:
            added_usernames.add(username.lower())

    if not added_usernames:
        return 0

    source_path = Path(accounts_file)
    source_lines = source_path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept_lines: list[str] = []
    removed_count = 0
    for line in source_lines:
        username = parse_username_line(line)
        if username and username.lower() in added_usernames:
            removed_count += 1
            continue
        kept_lines.append(line)

    if removed_count:
        source_path.write_text("".join(kept_lines), encoding="utf-8")

    return removed_count



def find_button_by_label(page, pattern: re.Pattern):
    """Return the first button whose aria-label matches pattern, or None."""
    for btn in page.query_selector_all("button[aria-label]"):
        label = btn.get_attribute("aria-label") or ""
        if pattern.search(label):
            return btn
    return None


def save_screenshot(page, username: str) -> str:
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    path = str(SCREENSHOTS_DIR / f"{username}.png")
    page.screenshot(path=path)
    return path


def check_and_follow(page, username: str, delay: float) -> AccountResult:
    url = PROFILE_URL.format(username=username)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        time.sleep(delay)

        # Suspended / deactivated URL redirects
        if page.url.startswith("https://x.com/i/") or "account_suspended" in page.url:
            return AccountResult(username, Status.NOT_FOUND, "suspended or redirect")

        # Empty-state element (deactivated / not found)
        if page.query_selector(NOT_FOUND_SELECTOR):
            return AccountResult(username, Status.NOT_FOUND)

        # Wait for the profile header to appear
        try:
            page.wait_for_selector(USER_NAME_SELECTOR, timeout=10_000)
        except PlaywrightTimeoutError:
            body_text = page.inner_text("body").lower()
            if "something went wrong" in body_text or "try again" in body_text:
                return AccountResult(username, Status.FAILED, "page error / rate limit")
            return AccountResult(username, Status.NOT_FOUND, "profile header not found")

        # Already following? (aria-label starts with "Following" or "Unfollow")
        if find_button_by_label(page, FOLLOWING_LABEL) or find_button_by_label(page, UNFOLLOW_LABEL):
            return AccountResult(username, Status.ALREADY_FOLLOWING)

        # Find the Follow button
        follow_btn = find_button_by_label(page, FOLLOW_LABEL)
        if not follow_btn:
            body_text = page.inner_text("body").lower()
            if "pending" in body_text:
                return AccountResult(username, Status.ALREADY_FOLLOWING, "follow request pending")
            screenshot = save_screenshot(page, username)
            return AccountResult(username, Status.FAILED, f"no follow button found (screenshot: {screenshot})")

        follow_btn.click()
        time.sleep(delay)

        # Confirm button switched to Following/Unfollow
        if find_button_by_label(page, FOLLOWING_LABEL) or find_button_by_label(page, UNFOLLOW_LABEL):
            return AccountResult(username, Status.FOLLOWED)

        # Protected accounts show a pending state
        body_text = page.inner_text("body").lower()
        if "pending" in body_text or "request" in body_text:
            return AccountResult(username, Status.FOLLOWED, "follow request sent (protected account)")

        screenshot = save_screenshot(page, username)
        return AccountResult(username, Status.FAILED, f"follow click did not confirm (screenshot: {screenshot})")

    except PlaywrightTimeoutError:
        return AccountResult(username, Status.FAILED, "page load timeout")
    except Exception as exc:  # noqa: BLE001
        return AccountResult(username, Status.FAILED, str(exc))


def print_progress(result: AccountResult, index: int, total: int) -> None:
    icons = {
        Status.FOLLOWED: "✓",
        Status.ALREADY_FOLLOWING: "~",
        Status.NOT_FOUND: "✗",
        Status.FAILED: "!",
    }
    icon = icons[result.status]
    note = f"  ({result.note})" if result.note else ""
    print(f"  [{index:>3}/{total}] {icon} @{result.username} — {result.status.value}{note}")


def build_report(results: list[AccountResult]) -> Report:
    report = Report()
    for r in results:
        if r.status == Status.FOLLOWED:
            report.followed.append(r.username)
        elif r.status == Status.ALREADY_FOLLOWING:
            report.already_following.append(r.username)
        elif r.status == Status.NOT_FOUND:
            report.not_found.append(r.username)
        else:
            report.failed.append(r)
    return report


def print_summary(report: Report, skipped: int = 0) -> None:
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"  Followed now:        {len(report.followed)}")
    print(f"  Already following:   {len(report.already_following)}")
    print(f"  Not found:           {len(report.not_found)}")
    print(f"  Failed:              {len(report.failed)}")
    if skipped:
        print(f"  Skipped (aborted):   {skipped}")

    if report.not_found:
        print("\nNot found:")
        for u in report.not_found:
            print(f"    @{u}")

    if report.failed:
        print("\nFailed:")
        for r in report.failed:
            note = f" — {r.note}" if r.note else ""
            print(f"    @{r.username}{note}")


def save_report(report: Report, path: str, skipped: int = 0) -> None:
    data = {
        "followed": report.followed,
        "already_following": report.already_following,
        "not_found": report.not_found,
        "failed": [asdict(r) for r in report.failed],
    }
    if skipped:
        data["aborted"] = True
        data["skipped"] = skipped
    Path(path).write_text(json.dumps(data, indent=2))
    print(f"\n[*] Report saved to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Follow Twitter/X accounts via UI automation.")
    parser.add_argument("accounts_file", help="Path to a text file with one username per line")
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to wait between page actions (default: 2.0)",
    )
    parser.add_argument(
        "--report",
        default="report.json",
        help="Path to write the JSON report (default: report.json)",
    )
    parser.add_argument(
        "--added-accounts-file",
        default="accounts added.txt",
        help='Path to append followed/already-following usernames (default: "accounts added.txt")',
    )
    parser.add_argument(
        "--profile-dir",
        default="./browser_profile",
        help="Directory for persistent browser profile to preserve login sessions",
    )
    parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=3,
        help="Stop execution after this many consecutive failures (default: 3)",
    )
    args = parser.parse_args()

    pre_removed_count = prune_accounts_already_added(args.accounts_file, args.added_accounts_file)
    if pre_removed_count:
        print(
            f"[*] Removed {pre_removed_count} account(s) from {args.accounts_file} "
            f"because they already exist in {args.added_accounts_file}"
        )

    accounts = load_accounts(args.accounts_file)
    if not accounts:
        if pre_removed_count:
            print("[*] No new accounts left to process after pre-run cleanup.")
            sys.exit(0)
        print("No accounts found in the file.")
        sys.exit(1)

    print(f"[*] Loaded {len(accounts)} account(s) from {args.accounts_file}")
    print(f"[*] Browser profile: {args.profile_dir}")

    profile_dir = Path(args.profile_dir)
    if not profile_dir.exists():
        print(f"[!] No browser profile found at '{profile_dir}'.")
        print("[!] Run 'python login.py' first to create a saved session.")
        sys.exit(1)

    results: list[AccountResult] = []

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 900},
            args=CHROME_ARGS,
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)
        page = context.pages[0] if context.pages else context.new_page()

        # Verify session is still valid
        page.goto("https://x.com/home", wait_until="domcontentloaded")
        time.sleep(2)
        if "login" in page.url or "i/flow" in page.url:
            print("[!] Session expired. Re-run 'python login.py' to log in again.")
            context.close()
            sys.exit(1)

        print(f"\n[*] Starting to follow {len(accounts)} account(s)...\n")

        consecutive_failures = 0
        aborted = False
        for i, username in enumerate(accounts, start=1):
            result = check_and_follow(page, username, args.delay)
            results.append(result)
            print_progress(result, i, len(accounts))

            if result.status == Status.FAILED:
                consecutive_failures += 1
                if consecutive_failures >= args.max_consecutive_failures:
                    print(f"\n[!] {consecutive_failures} consecutive failures — aborting early.")
                    aborted = True
                    break
            else:
                consecutive_failures = 0

            time.sleep(args.delay * 0.5)

        context.close()

    report = build_report(results)
    skipped = len(accounts) - len(results)
    print_summary(report, skipped=skipped if aborted else 0)
    save_report(report, args.report, skipped=skipped if aborted else 0)
    removed_count, appended_count, already_present_count = move_processed_accounts(
        args.accounts_file,
        args.added_accounts_file,
        report,
    )
    print(
        f"[*] Updated account files: removed {removed_count} from {args.accounts_file}, "
        f"appended {appended_count} to {args.added_accounts_file}"
    )
    if already_present_count:
        print(f"[*] Skipped {already_present_count} already present in {args.added_accounts_file}")


if __name__ == "__main__":
    main()
