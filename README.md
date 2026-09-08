# PyTrack Pro 💸

**PyTrack Pro** is an advanced, zero-dependency command-line finance tracker written in Python. It goes beyond simple expense logging to cover multi-account balances, budgets, recurring bills, savings goals, shared/split expenses, auto-categorization, multi-currency amounts, reporting, and more — all stored locally, with no sign-ups, no cloud, and no external packages.

## Features

- ➕ **Expenses** — add, edit, delete, list with rich filters (category, month, tag, account, amount range, date range, text search)
- 💰 **Income** — track income separately, see net totals against spending
- 🏦 **Accounts** — multiple cash/bank/credit accounts with balances and transfers between them
- 🌍 **Multi-currency** — per-expense currency with configurable exchange rates
- 📊 **Budgets** — monthly or yearly limits per category with OK/WARN/OVER status
- 🔁 **Recurring expenses** — daily/weekly/monthly/yearly bills that auto-generate when due
- 🎯 **Savings goals** — track progress toward a target with a visual progress bar
- 🤝 **Split expenses** — share costs with other people and get a minimal-transaction settle-up plan
- 🏷️ **Tags & categories** — organize beyond a single category, with bulk rename
- 🤖 **Auto-categorization rules** — assign a category automatically based on keywords in the note
- 🔍 **Search** — regex/substring search across notes, categories, and tags
- 📈 **Reports & stats** — category breakdowns, mean/median/stdev, monthly trend charts, month-vs-month comparison, full financial reports
- 📤 **Import/export** — CSV and JSON
- 💾 **Backup & restore**, plus **undo/redo** for any change
- ✅ **Data validation** — catch broken references or bad data
- ⚙️ **Configurable** — currency symbol, decimal places, color output, exchange rates
- 🖥️ **Interactive shell** — a REPL mode for running commands without retyping `python3 expense_tracker.py` each time
- 🐍 Pure Python standard library — no external dependencies required

## Requirements

- Python 3.7+

## Installation

Clone the repository:

```bash
git clone https://github.com/<your-username>/pytrack.git
cd pytrack
```

No `pip install` needed — PyTrack Pro only uses the Python standard library.

## Quick start

Load some sample data and explore:

```bash
python3 expense_tracker.py demo
python3 expense_tracker.py report
python3 expense_tracker.py budget status
python3 expense_tracker.py stats
```

## Usage

### Expenses

```bash
python3 expense_tracker.py add <amount> [category] [-d DATE] [-n NOTE] [-t TAGS] [-a ACCOUNT] [-c CURRENCY]
python3 expense_tracker.py list [-c CATEGORY] [-m MONTH] [-t TAG] [-a ACCOUNT] [--min N] [--max N] [--from DATE] [--to DATE] [--text PATTERN] [--sort FIELD] [--desc]
python3 expense_tracker.py edit <id> [--amount N] [--category C] [--date D] [--note N] [--tags T]
python3 expense_tracker.py delete <id>
python3 expense_tracker.py search [query] [--min N] [--max N] [--from DATE] [--to DATE]
python3 expense_tracker.py dupes
```

Examples:

```bash
python3 expense_tracker.py add 12.50 food -n "Lunch with friends" -t "work,social"
python3 expense_tracker.py add 9.99 -n "Netflix monthly"          # category auto-assigned via a rule
python3 expense_tracker.py list -m 2026-09 --min 50 --sort amount --desc
python3 expense_tracker.py search "gas" --from 2026-07-01 --to 2026-09-30
```

If you omit the category and a matching auto-categorization rule exists (see `rule add`), PyTrack fills it in for you; otherwise it falls back to `uncategorized`.

### Categories & tags

```bash
python3 expense_tracker.py category list
python3 expense_tracker.py category rename <old> <new>
python3 expense_tracker.py tag list
python3 expense_tracker.py tag rename <old> <new>
```

### Income

```bash
python3 expense_tracker.py income add <amount> <source> [-d DATE] [-a ACCOUNT] [-c CURRENCY] [-n NOTE]
python3 expense_tracker.py income list [-m MONTH]
python3 expense_tracker.py income delete <id>
```

### Accounts

```bash
python3 expense_tracker.py account add <name> [-t TYPE] [-c CURRENCY] [-b BALANCE]
python3 expense_tracker.py account list
python3 expense_tracker.py account edit <id> [--name N] [--balance N] [--type T]
python3 expense_tracker.py account delete <id>
python3 expense_tracker.py account transfer <from> <to> <amount>
```

Linking an expense or income entry to an account (`-a/--account`) automatically adjusts that account's balance.

### Budgets

```bash
python3 expense_tracker.py budget set <category> <amount> [-p monthly|yearly]
python3 expense_tracker.py budget list
python3 expense_tracker.py budget status [-p monthly|yearly]
python3 expense_tracker.py budget delete <id>
```

### Recurring expenses

```bash
python3 expense_tracker.py recurring add <category> <amount> [-f daily|weekly|monthly|yearly] [-d START_DATE] [-e END_DATE] [-a ACCOUNT] [-n NOTE]
python3 expense_tracker.py recurring list
python3 expense_tracker.py recurring generate   # creates any expenses that have come due
python3 expense_tracker.py recurring delete <id>
```

Run `recurring generate` whenever you like (e.g. once a day) — it catches up on every due occurrence since the last run.

### Savings goals

```bash
python3 expense_tracker.py goal add <name> <target> [-d DEADLINE]
python3 expense_tracker.py goal contribute <id> <amount>
python3 expense_tracker.py goal list
python3 expense_tracker.py goal delete <id>
```

### Split / shared expenses

```bash
python3 expense_tracker.py person add <name>
python3 expense_tracker.py person list
python3 expense_tracker.py split add <description> <amount> <payer> <participants> [-d DATE]
python3 expense_tracker.py split list
python3 expense_tracker.py split settle
python3 expense_tracker.py split delete <id>
```

`participants` is a comma-separated list (the payer is added automatically if not included). `split settle` prints the minimum set of payments needed to even everyone out.

### Auto-categorization rules

```bash
python3 expense_tracker.py rule add <keyword> <category>
python3 expense_tracker.py rule list
python3 expense_tracker.py rule delete <id>
```

### Summaries, stats & reports

```bash
python3 expense_tracker.py summary [-m MONTH] [-y YEAR] [--income]
python3 expense_tracker.py stats
python3 expense_tracker.py compare <month1> <month2>
python3 expense_tracker.py report [-m MONTH] [-y YEAR]
```

`report` pulls everything together: totals, top categories, largest expenses, budget status, goal progress, and account balances/net worth in one view.

### Import, export, backup

```bash
python3 expense_tracker.py export <file> [-f csv|json]
python3 expense_tracker.py import <file> [-f csv|json]
python3 expense_tracker.py backup
python3 expense_tracker.py restore --list
python3 expense_tracker.py restore --file <backup_filename>
python3 expense_tracker.py validate
```

### Undo / redo

```bash
python3 expense_tracker.py undo
python3 expense_tracker.py redo
```

Every command that changes your data can be undone (up to the last 25 changes).

### Configuration

```bash
python3 expense_tracker.py config list
python3 expense_tracker.py config get <key>
python3 expense_tracker.py config set <key> <value>
python3 expense_tracker.py config reset
```

Configurable keys include `currency`, `symbol`, `decimals`, `color`, and `rates` (exchange rates used for account transfers and currency conversion).

### Interactive shell

```bash
python3 expense_tracker.py shell
```

Drops you into a `pytrack>` prompt where you can run any of the commands above without the `python3 expense_tracker.py` prefix. Type `exit` or `quit` to leave.

### Demo data

```bash
python3 expense_tracker.py demo          # seeds sample accounts, expenses, budgets, goals, etc.
python3 expense_tracker.py demo --force  # overwrite existing data with the demo set
```

## Example session

```
$ python3 expense_tracker.py demo
Demo data loaded. Try: report | budget status | goal list | stats | split settle

$ python3 expense_tracker.py budget status
food                $167.50 / $300.00    ( 55.8%) OK
entertainment        $40.00 / $100.00    ( 40.0%) OK

$ python3 expense_tracker.py split settle
Settle-up plan (minimal transactions):
  sam -> alex: $150.00
```

## Data storage

All data lives in `ptdata.json` in the project directory (expenses, income, accounts, budgets, recurring rules, goals, people, splits, and categorization rules). Settings live in `ptconfig.json`, and backups go in `backups/`. All files are human-readable JSON — feel free to inspect them, back them up, or version control them.

Older single-list `expenses.json` files from PyTrack v1 are automatically recognized and migrated on first load.

## Roadmap ideas

- [ ] Terminal chart export to image files
- [ ] Encrypted/password-protected local storage
- [ ] Live exchange-rate lookups
- [ ] Web/GUI front end

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you'd like to change.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
