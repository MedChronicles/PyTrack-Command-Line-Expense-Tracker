<div align="center">

# 💸 PyTrack

**A no-frills, no-dependency expense tracker for your terminal.**

![Python](https://img.shields.io/badge/python-3.7%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)

</div>

---

## Why PyTrack?

Most expense trackers want you to sign up, install an app, or hand your spending data to a third-party server. PyTrack doesn't. It's a single Python file that reads and writes a JSON file on your own machine. That's it. Open a terminal, log an expense, close the terminal — your data never leaves your computer.

## At a glance

| Command   | What it does                                  |
|-----------|------------------------------------------------|
| `add`     | Record a new expense                           |
| `list`    | View expenses, optionally filtered             |
| `delete`  | Remove an expense by its ID                    |
| `summary` | See totals grouped by category                 |

## Getting started

**1. Get the code**

```bash
git clone https://github.com/<your-username>/pytrack.git
cd pytrack
```

**2. Check your Python version**

```bash
python3 --version   # 3.7 or higher required
```

**3. Run it**

```bash
python3 expense_tracker.py add 9.99 coffee -n "Morning latte"
```

That's the whole install process — no `pip install`, no virtual environment required, no config files to set up.

## Command reference

### `add` — record an expense

```bash
python3 expense_tracker.py add AMOUNT CATEGORY [-d DATE] [-n NOTE]
```

| Flag | Meaning | Default |
|------|---------|---------|
| `-d`, `--date` | Date in `YYYY-MM-DD` format | today |
| `-n`, `--note` | Free-text note | empty |

```bash
python3 expense_tracker.py add 65.20 groceries -d 2026-09-03 -n "Weekly shop"
```

### `list` — view expenses

```bash
python3 expense_tracker.py list [-c CATEGORY] [-m MONTH]
```

```bash
python3 expense_tracker.py list -c groceries
python3 expense_tracker.py list -m 2026-09
```

### `delete` — remove an expense

```bash
python3 expense_tracker.py delete ID
```

```bash
python3 expense_tracker.py delete 4
```

### `summary` — see the totals

```bash
python3 expense_tracker.py summary [-m MONTH]
```

```bash
python3 expense_tracker.py summary -m 2026-09
```

```
Expense summary for 2026-09:
------------------------------
rent           $800.00
groceries      $65.20
coffee         $9.99
------------------------------
Total          $875.19
```

## Where your data lives

Everything is saved to `expenses.json`, right next to the script:

```json
[
  {
    "id": 1,
    "date": "2026-09-03",
    "category": "groceries",
    "amount": 65.2,
    "note": "Weekly shop"
  }
]
```

Copy it, version it, edit it in any text editor — it's yours.

## What's next

Ideas that would be fun to add:

- CSV export for spreadsheets
- Per-category budget caps with alerts
- A `--chart` flag for a simple terminal bar chart of monthly totals
- Recurring expense support (rent, subscriptions, etc.)

Contributions and forks are very welcome.

## License

MIT — see [LICENSE](LICENSE).
