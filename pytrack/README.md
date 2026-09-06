# PyTrack 💸

**PyTrack** is a lightweight, zero-dependency command-line expense tracker written in Python. Log your spending, filter it by category or month, and get instant summaries — all from your terminal, with your data stored locally in a simple JSON file. No sign-ups, no cloud, no bloat.

## Features

- ➕ Add expenses with an amount, category, date, and optional note
- 📋 List expenses, filterable by category and/or month
- ❌ Delete expenses by ID
- 📊 View a spending summary grouped by category, optionally scoped to a month
- 💾 Data stored in a human-readable `expenses.json` file — easy to back up, inspect, or version control
- 🐍 Pure Python standard library — no external dependencies required

## Requirements

- Python 3.7+

## Installation

Clone the repository:

```bash
git clone https://github.com/<your-username>/pytrack.git
cd pytrack
```

No `pip install` needed — PyTrack only uses the Python standard library.

## Usage

### Add an expense

```bash
python3 expense_tracker.py add <amount> <category> [-d DATE] [-n NOTE]
```

Example:

```bash
python3 expense_tracker.py add 12.50 food -n "Lunch with friends"
python3 expense_tracker.py add 800 rent -d 2026-09-01
```

### List expenses

```bash
python3 expense_tracker.py list [-c CATEGORY] [-m MONTH]
```

Example:

```bash
python3 expense_tracker.py list
python3 expense_tracker.py list -c food
python3 expense_tracker.py list -m 2026-09
```

### Delete an expense

```bash
python3 expense_tracker.py delete <id>
```

Example:

```bash
python3 expense_tracker.py delete 3
```

### View a summary

```bash
python3 expense_tracker.py summary [-m MONTH]
```

Example:

```bash
python3 expense_tracker.py summary
python3 expense_tracker.py summary -m 2026-09
```

## Example session

```
$ python3 expense_tracker.py add 45 transport -d 2026-09-01 -n "Gas"
Added expense #1: transport - $45.00 on 2026-09-01

$ python3 expense_tracker.py add 800 rent -d 2026-09-01
Added expense #2: rent - $800.00 on 2026-09-01

$ python3 expense_tracker.py summary -m 2026-09
Expense summary for 2026-09:
------------------------------
rent           $800.00
transport      $45.00
------------------------------
Total          $845.00
```

## Data storage

All expenses are stored in `expenses.json` in the project directory. Each entry looks like:

```json
{
  "id": 1,
  "date": "2026-09-01",
  "category": "transport",
  "amount": 45.0,
  "note": "Gas"
}
```

Feel free to back this file up, edit it by hand, or sync it however you like.

## Roadmap ideas

- [ ] Export summaries to CSV
- [ ] Budget limits per category with warnings
- [ ] Simple terminal charts for monthly trends
- [ ] Multi-currency support

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you'd like to change.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
