# xubscriber

Bulk-follow a list of X/Twitter accounts using browser automation. No API key required — it drives a real Chrome window the same way you would manually.

## Requirements

- Python 3.10+
- Google Chrome installed on your system
- [Playwright](https://playwright.dev/python/)

```bash
pip install -r requirements.txt
```

## Quick start

### Step 1 — Log in (once)

```bash
python login.py
```

A Chrome window opens. Log in to X/Twitter as you normally would. Once you see your home feed, come back to the terminal and press **ENTER**. Your session is saved to `./browser_profile/` and reused on every future run — you won't need to log in again unless the session expires.

### Step 2 — Create your accounts list

Create a plain text file with one username per line:

```
# comments are ignored
elonmusk
@paulg        # the @ prefix is optional
sama
```

A sample [accounts.txt](accounts.txt) is included.

### Step 3 — Follow

```bash
python follow.py accounts.txt
```

The browser opens, verifies your session, then visits each profile and clicks Follow. Progress is printed live:

```
[*] Loaded 4 account(s) from accounts.txt

  [  1/  4] ✓ @elonmusk — followed
  [  2/  4] ~ @paulg — already_following
  [  3/  4] ✓ @sama — followed
  [  4/  4] ✗ @ghost — not_found

==================================================
SUMMARY
==================================================
  Followed now:        2
  Already following:   1
  Not found:           1
  Failed:              0

[*] Report saved to report.json
```

## Options

### `login.py`

| Flag | Default | Description |
|---|---|---|
| `--profile-dir` | `./browser_profile` | Where to save the browser session |

### `follow.py`

| Flag | Default | Description |
|---|---|---|
| `--delay` | `2.0` | Seconds to wait between page actions. Increase if you hit rate limits. |
| `--report` | `report.json` | Path for the JSON results file |
| `--profile-dir` | `./browser_profile` | Must match the directory used in `login.py` |

## Report format

`report.json` is written at the end of every run:

```json
{
  "followed": ["elonmusk", "sama"],
  "already_following": ["paulg"],
  "not_found": ["ghost"],
  "failed": [
    { "username": "someuser", "status": "failed", "note": "page load timeout" }
  ]
}
```

## Result codes

| Symbol | Status | Meaning |
|---|---|---|
| `✓` | `followed` | Follow button was clicked and confirmed |
| `~` | `already_following` | You were already following, or a follow request is pending |
| `✗` | `not_found` | Account doesn't exist, is suspended, or has been deactivated |
| `!` | `failed` | Something went wrong (timeout, rate limit, UI changed) |

## Debugging failures

When a profile can't be processed, a screenshot is saved to `./screenshots/<username>.png` and the path is noted in the report. Open it to see exactly what the browser saw — usually a rate-limit wall, a CAPTCHA, or an unexpected page layout.

If every account fails, re-run `login.py` to refresh the session.

## Rate limiting

X will throttle you if you follow too many accounts too quickly. Practical tips:

- Use `--delay 3` or higher for large lists
- Split large lists into batches of ~50 and run them across different sessions
- If you hit a wall mid-run, wait a few hours and re-run — already-followed accounts are skipped automatically

## Session expiry

Browser sessions last weeks or months normally. If yours expires, just run `login.py` again. The profile directory is reused, so you only need to log in, not reconfigure anything.

## Files

```
xubscriber/
├── login.py          # Step 1: open browser and log in manually
├── follow.py         # Step 2: follow all accounts in a list
├── accounts.txt      # Your list of usernames (edit this)
├── requirements.txt  # Python dependencies
├── browser_profile/  # Saved Chrome session (created by login.py)
├── screenshots/      # Debug screenshots for failed accounts
└── report.json       # Results of the last run
```
