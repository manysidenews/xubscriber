#!/usr/bin/env python3
"""
Step 1: Open browser and log in to X/Twitter manually.
The session is saved to ./browser_profile so follow.py can reuse it.

Usage:
    python login.py
    python login.py --profile-dir ./browser_profile
"""

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


CHROME_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Open browser for manual X/Twitter login.")
    parser.add_argument(
        "--profile-dir",
        default="./browser_profile",
        help="Directory to save the browser session (default: ./browser_profile)",
    )
    args = parser.parse_args()

    profile_dir = Path(args.profile_dir)
    print(f"[*] Browser profile: {profile_dir}")
    print("[*] Opening browser — please log in to X/Twitter.")
    print("[*] When you see your home feed, come back here and press ENTER to save and close.\n")

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 900},
            args=CHROME_ARGS,
        )
        # Remove the navigator.webdriver flag that Twitter checks
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://x.com/login", wait_until="domcontentloaded")

        input("Press ENTER once you are logged in and see your home feed: ")
        time.sleep(1)
        context.close()

    print("[*] Session saved. You can now run: python follow.py accounts.txt")


if __name__ == "__main__":
    main()
