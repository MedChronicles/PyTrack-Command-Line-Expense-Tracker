#!/usr/bin/env python3
"""
PyTrack Pro - an advanced command-line personal finance tracker.

Tracks expenses and income across multiple accounts, supports budgets,
recurring transactions, savings goals, expense splitting between people,
auto-categorization rules, multi-currency amounts, reporting/statistics,
CSV/JSON import-export, backups, and undo/redo. Pure Python standard
library - no external dependencies, no network access, no cloud.
"""

import argparse
import csv
import json
import os
import re
import shlex
import shutil
import statistics
import sys
from collections import defaultdict, Counter
from copy import deepcopy
from datetime import datetime, timedelta

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(APP_DIR, "ptdata.json")
CONFIG_FILE = os.path.join(APP_DIR, "ptconfig.json")
UNDO_FILE = os.path.join(APP_DIR, "ptundo.json")
BACKUP_DIR = os.path.join(APP_DIR, "backups")
SCHEMA_VERSION = 2
MAX_UNDO = 25
VERSION = "2.0.0"

DEFAULT_CONFIG = {
    "currency": "USD", "symbol": "$", "date_format": "%Y-%m-%d",
    "color": True, "decimals": 2, "default_account": None,
    "rates": {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "INR": 83.0,
              "JPY": 149.0, "CAD": 1.36, "AUD": 1.52, "CNY": 7.1},
}

EMPTY_DATA = {
    "version": SCHEMA_VERSION, "expenses": [], "income": [], "accounts": [],
    "budgets": [], "recurring": [], "goals": [], "people": [], "splits": [],
    "rules": [],
}

COLORS = {"red": "\033[31m", "green": "\033[32m", "yellow": "\033[33m",
          "blue": "\033[34m", "cyan": "\033[36m", "magenta": "\033[35m",
          "bold": "\033[1m", "reset": "\033[0m"}


# --------------------------------------------------------------------------
# Formatting / display helpers
# --------------------------------------------------------------------------

def c(text, color, cfg):
    """Wrap text in an ANSI color code if the config has color enabled."""
    if not cfg.get("color"):
        return str(text)
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"


def fmt_money(amount, cfg):
    return f"{cfg['symbol']}{amount:,.{cfg['decimals']}f}"


def print_table(headers, rows, aligns=None):
    if not rows:
        return
    aligns = aligns or ["<"] * len(headers)
    widths = []
    for i, h in enumerate(headers):
        col = [len(str(h))] + [len(str(r[i])) for r in rows]
        widths.append(max(col))

    def fmt_row(vals):
        return "  ".join(f"{str(v):{a}{w}}" for v, a, w in zip(vals, aligns, widths))

    print(fmt_row(headers))
    print("-" * (sum(widths) + 2 * (len(widths) - 1)))
    for r in rows:
        print(fmt_row(r))


def bar_chart(items, width=30):
    items = list(items)
    if not items:
        return
    maxv = max((v for _, v in items), default=0) or 1
    for label, v in items:
        bar = "#" * max(0, int(width * v / maxv))
        print(f"{str(label):<15}{bar} {v:.2f}")


# --------------------------------------------------------------------------
# Storage: config, data, undo/redo
# --------------------------------------------------------------------------

def _atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update(cfg)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    _atomic_write(CONFIG_FILE, cfg)


def load_data():
    if not os.path.exists(DATA_FILE):
        return deepcopy(EMPTY_DATA)
    try:
        with open(DATA_FILE) as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError):
        return deepcopy(EMPTY_DATA)
    if isinstance(raw, list):  # legacy PyTrack v1 format: bare list of expenses
        data = deepcopy(EMPTY_DATA)
        data["expenses"] = raw
        return data
    data = deepcopy(EMPTY_DATA)
    data.update(raw)
    data["version"] = SCHEMA_VERSION
    return data


def save_data(data):
    _atomic_write(DATA_FILE, data)


def _load_undo():
    if not os.path.exists(UNDO_FILE):
        return {"undo": [], "redo": []}
    try:
        with open(UNDO_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"undo": [], "redo": []}


def _save_undo(stacks):
    _atomic_write(UNDO_FILE, stacks)


def push_undo(data):
    """Snapshot current data before a mutation, for later 'undo'."""
    stacks = _load_undo()
    stacks["undo"].append(data)
    stacks["undo"] = stacks["undo"][-MAX_UNDO:]
    stacks["redo"] = []
    _save_undo(stacks)


def cmd_undo(args):
    stacks = _load_undo()
    if not stacks["undo"]:
        print("Nothing to undo.")
        return
    stacks["redo"].append(load_data())
    prev = stacks["undo"].pop()
    save_data(prev)
    _save_undo(stacks)
    print("Undid last change.")


def cmd_redo(args):
    stacks = _load_undo()
    if not stacks["redo"]:
        print("Nothing to redo.")
        return
    stacks["undo"].append(load_data())
    nxt = stacks["redo"].pop()
    save_data(nxt)
    _save_undo(stacks)
    print("Redid last change.")


def next_id(records):
    return max((r["id"] for r in records), default=0) + 1


# --------------------------------------------------------------------------
# Shared utilities
# --------------------------------------------------------------------------

def _parse_date(s, cfg):
    if not s:
        return datetime.now().strftime("%Y-%m-%d")
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        print("Error: date must be in YYYY-MM-DD format.")
        sys.exit(1)


def _in_range(date, frm, to):
    if frm and date < frm:
        return False
    if to and date > to:
        return False
    return True


def convert(amount, frm, to, cfg):
    rates = cfg.get("rates", {})
    r_from = rates.get(frm, 1.0)
    r_to = rates.get(to, 1.0)
    return amount / r_from * r_to


def _find_account(data, name):
    if not name:
        return None
    for a in data["accounts"]:
        if a["name"].lower() == name.lower():
            return a
    print(f"Warning: account '{name}' not found (recorded without a linked balance).")
    return None


def auto_category(note, data):
    if not note:
        return None
    low = note.lower()
    for rule in data["rules"]:
        if rule["keyword"].lower() in low:
            return rule["category"]
    return None


# --------------------------------------------------------------------------
# Expenses
# --------------------------------------------------------------------------

def cmd_add(args):
    cfg = load_config()
    data = load_data()
    push_undo(data)
    try:
        amount = round(float(args.amount), 2)
    except ValueError:
        print("Error: amount must be a number.")
        sys.exit(1)
    date = _parse_date(args.date, cfg)
    category = (args.category or "").strip().lower() or auto_category(args.note, data) or "uncategorized"
    tags = [t.strip().lower() for t in (args.tags or "").split(",") if t.strip()]
    currency = (args.currency or cfg["currency"]).upper()
    account = _find_account(data, args.account) if args.account else None
    expense = {"id": next_id(data["expenses"]), "date": date, "category": category,
               "amount": amount, "currency": currency, "note": args.note or "",
               "tags": tags, "account": args.account or None}
    data["expenses"].append(expense)
    if account:
        account["balance"] = round(account["balance"] - convert(amount, currency, account["currency"], cfg), 2)
    save_data(data)
    print(f"Added expense #{expense['id']}: {category} - {fmt_money(amount, cfg)} on {date}")


def cmd_list(args):
    cfg = load_config()
    data = load_data()
    rows = data["expenses"]
    if args.category:
        rows = [e for e in rows if e["category"] == args.category.strip().lower()]
    if args.month:
        rows = [e for e in rows if e["date"].startswith(args.month)]
    if args.tag:
        rows = [e for e in rows if args.tag.strip().lower() in e.get("tags", [])]
    if args.account:
        rows = [e for e in rows if (e.get("account") or "").lower() == args.account.lower()]
    if args.min is not None:
        rows = [e for e in rows if e["amount"] >= args.min]
    if args.max is not None:
        rows = [e for e in rows if e["amount"] <= args.max]
    if args.frm or args.to:
        rows = [e for e in rows if _in_range(e["date"], args.frm, args.to)]
    if args.text:
        rows = [e for e in rows if re.search(args.text, e.get("note", ""), re.I)]
    if not rows:
        print("No expenses found.")
        return
    sort_key = args.sort if args.sort in ("id", "date", "category", "amount") else "date"
    rows = sorted(rows, key=lambda e: e[sort_key], reverse=args.desc)
    table = [[e["id"], e["date"], e["category"], fmt_money(e["amount"], cfg),
              ",".join(e.get("tags", [])), e.get("account") or "-", e.get("note", "")] for e in rows]
    print_table(["ID", "Date", "Category", "Amount", "Tags", "Account", "Note"],
                table, ["<", "<", "<", ">", "<", "<", "<"])


def cmd_edit(args):
    cfg = load_config()
    data = load_data()
    push_undo(data)
    e = next((x for x in data["expenses"] if x["id"] == args.id), None)
    if not e:
        print(f"No expense found with ID {args.id}.")
        sys.exit(1)
    if args.amount is not None:
        e["amount"] = round(args.amount, 2)
    if args.category:
        e["category"] = args.category.strip().lower()
    if args.date:
        e["date"] = _parse_date(args.date, cfg)
    if args.note is not None:
        e["note"] = args.note
    if args.tags is not None:
        e["tags"] = [t.strip().lower() for t in args.tags.split(",") if t.strip()]
    save_data(data)
    print(f"Updated expense #{args.id}.")


def cmd_delete(args):
    data = load_data()
    push_undo(data)
    before = len(data["expenses"])
    data["expenses"] = [e for e in data["expenses"] if e["id"] != args.id]
    if len(data["expenses"]) == before:
        print(f"No expense found with ID {args.id}.")
        sys.exit(1)
    save_data(data)
    print(f"Deleted expense #{args.id}.")


def cmd_search(args):
    cfg = load_config()
    data = load_data()
    rows = data["expenses"]
    if args.query:
        pattern = re.compile(re.escape(args.query), re.I)
        rows = [e for e in rows if pattern.search(e.get("note", "")) or pattern.search(e["category"])
                or pattern.search(",".join(e.get("tags", [])))]
    if args.min is not None:
        rows = [e for e in rows if e["amount"] >= args.min]
    if args.max is not None:
        rows = [e for e in rows if e["amount"] <= args.max]
    if args.frm or args.to:
        rows = [e for e in rows if _in_range(e["date"], args.frm, args.to)]
    if not rows:
        print("No matches.")
        return
    table = [[e["id"], e["date"], e["category"], fmt_money(e["amount"], cfg), e.get("note", "")]
             for e in sorted(rows, key=lambda e: e["date"])]
    print_table(["ID", "Date", "Category", "Amount", "Note"], table)


def cmd_dupes(args):
    cfg = load_config()
    data = load_data()
    seen = defaultdict(list)
    for e in data["expenses"]:
        seen[(e["date"], e["amount"], e["category"])].append(e["id"])
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    if not dupes:
        print("No potential duplicates found.")
        return
    print("Potential duplicate expenses:")
    for (date, amt, cat), ids in dupes.items():
        print(f"  {date} {cat} {fmt_money(amt, cfg)} -> IDs {ids}")


# --------------------------------------------------------------------------
# Categories & tags
# --------------------------------------------------------------------------

def cmd_category_list(args):
    data = load_data()
    cats = sorted(set(e["category"] for e in data["expenses"]))
    if not cats:
        print("No categories yet.")
        return
    for cat in cats:
        print(cat)


def cmd_category_rename(args):
    data = load_data()
    push_undo(data)
    old, new = args.old.strip().lower(), args.new.strip().lower()
    n = 0
    for e in data["expenses"]:
        if e["category"] == old:
            e["category"] = new
            n += 1
    for b in data["budgets"]:
        if b["category"] == old:
            b["category"] = new
    save_data(data)
    print(f"Renamed category '{old}' to '{new}' on {n} expense(s).")


def cmd_tag_list(args):
    data = load_data()
    tags = sorted(set(t for e in data["expenses"] for t in e.get("tags", [])))
    if not tags:
        print("No tags yet.")
        return
    for t in tags:
        print(t)


def cmd_tag_rename(args):
    data = load_data()
    push_undo(data)
    old, new = args.old.strip().lower(), args.new.strip().lower()
    n = 0
    for e in data["expenses"]:
        if old in e.get("tags", []):
            e["tags"] = [new if t == old else t for t in e["tags"]]
            n += 1
    save_data(data)
    print(f"Renamed tag '{old}' to '{new}' on {n} expense(s).")


# --------------------------------------------------------------------------
# Income
# --------------------------------------------------------------------------

def cmd_income_add(args):
    cfg = load_config()
    data = load_data()
    push_undo(data)
    date = _parse_date(args.date, cfg)
    account = _find_account(data, args.account) if args.account else None
    inc = {"id": next_id(data["income"]), "date": date, "source": args.source,
           "amount": round(args.amount, 2), "currency": (args.currency or cfg["currency"]).upper(),
           "note": args.note or "", "account": args.account or None}
    data["income"].append(inc)
    if account:
        account["balance"] = round(account["balance"] + convert(inc["amount"], inc["currency"], account["currency"], cfg), 2)
    save_data(data)
    print(f"Added income #{inc['id']}: {inc['source']} - {fmt_money(inc['amount'], cfg)} on {date}")


def cmd_income_list(args):
    cfg = load_config()
    data = load_data()
    rows = data["income"]
    if args.month:
        rows = [i for i in rows if i["date"].startswith(args.month)]
    if not rows:
        print("No income found.")
        return
    rows = sorted(rows, key=lambda i: i["date"])
    table = [[i["id"], i["date"], i["source"], fmt_money(i["amount"], cfg),
              i.get("account") or "-", i.get("note", "")] for i in rows]
    print_table(["ID", "Date", "Source", "Amount", "Account", "Note"], table)


def cmd_income_delete(args):
    data = load_data()
    push_undo(data)
    before = len(data["income"])
    data["income"] = [i for i in data["income"] if i["id"] != args.id]
    if len(data["income"]) == before:
        print(f"No income found with ID {args.id}.")
        sys.exit(1)
    save_data(data)
    print(f"Deleted income #{args.id}.")


# --------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------

def cmd_account_add(args):
    cfg = load_config()
    data = load_data()
    push_undo(data)
    if any(a["name"].lower() == args.name.lower() for a in data["accounts"]):
        print(f"Account '{args.name}' already exists.")
        sys.exit(1)
    data["accounts"].append({"id": next_id(data["accounts"]), "name": args.name,
                              "type": args.type or "cash",
                              "currency": (args.currency or cfg["currency"]).upper(),
                              "balance": round(args.balance or 0.0, 2)})
    save_data(data)
    print(f"Account '{args.name}' added.")


def cmd_account_list(args):
    cfg = load_config()
    data = load_data()
    if not data["accounts"]:
        print("No accounts.")
        return
    table = [[a["id"], a["name"], a["type"], a["currency"], fmt_money(a["balance"], cfg)]
              for a in data["accounts"]]
    print_table(["ID", "Name", "Type", "Currency", "Balance"], table)
    net = sum(a["balance"] for a in data["accounts"])
    print(f"\nNet worth (nominal, mixed currencies): {fmt_money(net, cfg)}")


def cmd_account_edit(args):
    data = load_data()
    push_undo(data)
    a = next((x for x in data["accounts"] if x["id"] == args.id), None)
    if not a:
        print("Account not found.")
        sys.exit(1)
    if args.name:
        a["name"] = args.name
    if args.balance is not None:
        a["balance"] = round(args.balance, 2)
    if args.type:
        a["type"] = args.type
    save_data(data)
    print(f"Updated account #{args.id}.")


def cmd_account_delete(args):
    data = load_data()
    push_undo(data)
    before = len(data["accounts"])
    data["accounts"] = [a for a in data["accounts"] if a["id"] != args.id]
    if len(data["accounts"]) == before:
        print("Account not found.")
        sys.exit(1)
    save_data(data)
    print("Account deleted.")


def cmd_account_transfer(args):
    cfg = load_config()
    data = load_data()
    push_undo(data)
    src = _find_account(data, args.frm)
    dst = _find_account(data, args.to)
    if not src or not dst:
        sys.exit(1)
    src["balance"] = round(src["balance"] - args.amount, 2)
    dst["balance"] = round(dst["balance"] + convert(args.amount, src["currency"], dst["currency"], cfg), 2)
    save_data(data)
    print(f"Transferred {fmt_money(args.amount, cfg)} from {src['name']} to {dst['name']}.")


# --------------------------------------------------------------------------
# Budgets
# --------------------------------------------------------------------------

def cmd_budget_set(args):
    cfg = load_config()
    data = load_data()
    push_undo(data)
    cat = args.category.strip().lower()
    b = next((x for x in data["budgets"] if x["category"] == cat and x["period"] == args.period), None)
    if b:
        b["amount"] = round(args.amount, 2)
    else:
        data["budgets"].append({"id": next_id(data["budgets"]), "category": cat,
                                 "amount": round(args.amount, 2), "period": args.period})
    save_data(data)
    print(f"Budget set: {cat} {fmt_money(args.amount, cfg)}/{args.period}.")


def cmd_budget_list(args):
    cfg = load_config()
    data = load_data()
    if not data["budgets"]:
        print("No budgets set.")
        return
    table = [[b["id"], b["category"], b["period"], fmt_money(b["amount"], cfg)] for b in data["budgets"]]
    print_table(["ID", "Category", "Period", "Amount"], table)


def cmd_budget_delete(args):
    data = load_data()
    push_undo(data)
    before = len(data["budgets"])
    data["budgets"] = [b for b in data["budgets"] if b["id"] != args.id]
    if len(data["budgets"]) == before:
        print("Budget not found.")
        sys.exit(1)
    save_data(data)
    print("Budget deleted.")


def cmd_budget_status(args):
    cfg = load_config()
    data = load_data()
    now = datetime.now()
    if not data["budgets"]:
        print("No budgets set.")
        return
    for b in data["budgets"]:
        if getattr(args, "period", None) and b["period"] != args.period:
            continue
        period_key = now.strftime("%Y-%m") if b["period"] == "monthly" else now.strftime("%Y")
        spent = sum(e["amount"] for e in data["expenses"]
                    if e["category"] == b["category"] and e["date"].startswith(period_key))
        pct = (spent / b["amount"] * 100) if b["amount"] else 0
        if pct >= 100:
            flag = c("OVER", "red", cfg)
        elif pct >= 80:
            flag = c("WARN", "yellow", cfg)
        else:
            flag = c("OK", "green", cfg)
        print(f"{b['category']:<15}{fmt_money(spent, cfg):>10} / {fmt_money(b['amount'], cfg):<10} ({pct:5.1f}%) {flag}")


# --------------------------------------------------------------------------
# Recurring transactions
# --------------------------------------------------------------------------

_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
    max_day = 29 if (m == 2 and leap) else _DAYS_IN_MONTH[m - 1]
    return d.replace(year=y, month=m, day=min(d.day, max_day))


def _advance(d, freq):
    if freq == "daily":
        return d + timedelta(days=1)
    if freq == "weekly":
        return d + timedelta(weeks=1)
    if freq == "monthly":
        return _add_months(d, 1)
    if freq == "yearly":
        return _add_months(d, 12)
    return d + timedelta(days=30)


def cmd_recurring_add(args):
    cfg = load_config()
    data = load_data()
    push_undo(data)
    start = _parse_date(args.date, cfg)
    data["recurring"].append({"id": next_id(data["recurring"]), "category": args.category.strip().lower(),
                               "amount": round(args.amount, 2), "note": args.note or "",
                               "account": args.account, "currency": (args.currency or cfg["currency"]).upper(),
                               "frequency": args.frequency, "next_due": start, "end_date": args.end})
    save_data(data)
    print(f"Recurring expense #{data['recurring'][-1]['id']} added ({args.frequency}, next due {start}).")


def cmd_recurring_list(args):
    data = load_data()
    if not data["recurring"]:
        print("No recurring expenses configured.")
        return
    table = [[r["id"], r["category"], r["amount"], r["frequency"], r["next_due"], r.get("end_date") or "-"]
             for r in data["recurring"]]
    print_table(["ID", "Category", "Amount", "Freq", "NextDue", "EndDate"], table)


def cmd_recurring_delete(args):
    data = load_data()
    push_undo(data)
    before = len(data["recurring"])
    data["recurring"] = [r for r in data["recurring"] if r["id"] != args.id]
    if len(data["recurring"]) == before:
        print("Recurring rule not found.")
        sys.exit(1)
    save_data(data)
    print("Recurring rule deleted.")


def cmd_recurring_generate(args):
    data = load_data()
    push_undo(data)
    today = datetime.now().strftime("%Y-%m-%d")
    created = 0
    for r in data["recurring"]:
        due = datetime.strptime(r["next_due"], "%Y-%m-%d")
        end = datetime.strptime(r["end_date"], "%Y-%m-%d") if r.get("end_date") else None
        while due.strftime("%Y-%m-%d") <= today and (not end or due <= end):
            data["expenses"].append({"id": next_id(data["expenses"]), "date": due.strftime("%Y-%m-%d"),
                                      "category": r["category"], "amount": r["amount"], "currency": r["currency"],
                                      "note": (r["note"] + " (recurring)").strip(), "tags": ["recurring"],
                                      "account": r.get("account")})
            created += 1
            due = _advance(due, r["frequency"])
        r["next_due"] = due.strftime("%Y-%m-%d")
    save_data(data)
    print(f"Generated {created} recurring expense(s).")


# --------------------------------------------------------------------------
# Savings goals
# --------------------------------------------------------------------------

def cmd_goal_add(args):
    data = load_data()
    push_undo(data)
    data["goals"].append({"id": next_id(data["goals"]), "name": args.name,
                           "target": round(args.target, 2), "saved": 0.0, "deadline": args.deadline})
    save_data(data)
    print(f"Goal '{args.name}' created (target {args.target}).")


def cmd_goal_contribute(args):
    data = load_data()
    push_undo(data)
    g = next((x for x in data["goals"] if x["id"] == args.id), None)
    if not g:
        print("Goal not found.")
        sys.exit(1)
    g["saved"] = round(g["saved"] + args.amount, 2)
    save_data(data)
    print(f"Added {args.amount} to '{g['name']}'. Now {g['saved']}/{g['target']}.")


def cmd_goal_list(args):
    cfg = load_config()
    data = load_data()
    if not data["goals"]:
        print("No savings goals.")
        return
    for g in data["goals"]:
        pct = min(100.0, (g["saved"] / g["target"] * 100) if g["target"] else 0.0)
        filled = int(pct / 5)
        bar = "#" * filled + "-" * (20 - filled)
        print(f"[{g['id']}] {g['name']:<15}[{bar}] {pct:5.1f}%  "
              f"{fmt_money(g['saved'], cfg)}/{fmt_money(g['target'], cfg)}  due {g.get('deadline') or '-'}")


def cmd_goal_delete(args):
    data = load_data()
    push_undo(data)
    before = len(data["goals"])
    data["goals"] = [g for g in data["goals"] if g["id"] != args.id]
    if len(data["goals"]) == before:
        print("Goal not found.")
        sys.exit(1)
    save_data(data)
    print("Goal deleted.")


# --------------------------------------------------------------------------
# People & split expenses
# --------------------------------------------------------------------------

def cmd_person_add(args):
    data = load_data()
    push_undo(data)
    if any(p["name"].lower() == args.name.lower() for p in data["people"]):
        print("Person already exists.")
        return
    data["people"].append({"id": next_id(data["people"]), "name": args.name})
    save_data(data)
    print(f"Added person '{args.name}'.")


def cmd_person_list(args):
    data = load_data()
    if not data["people"]:
        print("No people recorded.")
        return
    for p in data["people"]:
        print(f"[{p['id']}] {p['name']}")


def cmd_split_add(args):
    cfg = load_config()
    data = load_data()
    push_undo(data)
    participants = [p.strip() for p in args.participants.split(",") if p.strip()]
    if args.payer not in participants:
        participants.append(args.payer)
    share = round(args.amount / len(participants), 2)
    data["splits"].append({"id": next_id(data["splits"]), "date": _parse_date(args.date, cfg),
                            "description": args.description, "amount": round(args.amount, 2),
                            "payer": args.payer, "participants": participants, "share": share})
    save_data(data)
    print(f"Split #{data['splits'][-1]['id']} added: {args.description} "
          f"({fmt_money(share, cfg)} each among {len(participants)}).")


def cmd_split_list(args):
    cfg = load_config()
    data = load_data()
    if not data["splits"]:
        print("No splits recorded.")
        return
    table = [[s["id"], s["date"], s["description"], fmt_money(s["amount"], cfg), s["payer"],
              ",".join(s["participants"])] for s in data["splits"]]
    print_table(["ID", "Date", "Description", "Amount", "Payer", "Participants"], table)


def cmd_split_delete(args):
    data = load_data()
    push_undo(data)
    before = len(data["splits"])
    data["splits"] = [s for s in data["splits"] if s["id"] != args.id]
    if len(data["splits"]) == before:
        print("Split not found.")
        sys.exit(1)
    save_data(data)
    print("Split deleted.")


def cmd_split_settle(args):
    cfg = load_config()
    data = load_data()
    balances = defaultdict(float)
    for s in data["splits"]:
        for p in s["participants"]:
            if p == s["payer"]:
                continue
            balances[p] -= s["share"]
            balances[s["payer"]] += s["share"]
    debtors = sorted([[p, -v] for p, v in balances.items() if v < -0.005], key=lambda x: -x[1])
    creditors = sorted([[p, v] for p, v in balances.items() if v > 0.005], key=lambda x: -x[1])
    if not debtors and not creditors:
        print("Everyone is settled up.")
        return
    i = j = 0
    txns = []
    while i < len(debtors) and j < len(creditors):
        dname, damt = debtors[i]
        cname, camt = creditors[j]
        pay = round(min(damt, camt), 2)
        txns.append((dname, cname, pay))
        debtors[i][1] -= pay
        creditors[j][1] -= pay
        if debtors[i][1] <= 0.005:
            i += 1
        if creditors[j][1] <= 0.005:
            j += 1
    print("Settle-up plan (minimal transactions):")
    for d, cr, amt in txns:
        print(f"  {d} -> {cr}: {fmt_money(amt, cfg)}")


# --------------------------------------------------------------------------
# Auto-categorization rules
# --------------------------------------------------------------------------

def cmd_rule_add(args):
    data = load_data()
    push_undo(data)
    data["rules"].append({"id": next_id(data["rules"]), "keyword": args.keyword,
                           "category": args.category.strip().lower()})
    save_data(data)
    print(f"Rule added: notes containing '{args.keyword}' -> {args.category.strip().lower()}.")


def cmd_rule_list(args):
    data = load_data()
    if not data["rules"]:
        print("No auto-categorization rules.")
        return
    for r in data["rules"]:
        print(f"[{r['id']}] '{r['keyword']}' -> {r['category']}")


def cmd_rule_delete(args):
    data = load_data()
    push_undo(data)
    before = len(data["rules"])
    data["rules"] = [r for r in data["rules"] if r["id"] != args.id]
    if len(data["rules"]) == before:
        print("Rule not found.")
        sys.exit(1)
    save_data(data)
    print("Rule deleted.")


# --------------------------------------------------------------------------
# Summary, stats, comparison, reporting
# --------------------------------------------------------------------------

def cmd_summary(args):
    cfg = load_config()
    data = load_data()
    expenses = data["expenses"]
    if args.month:
        expenses = [e for e in expenses if e["date"].startswith(args.month)]
    if args.year:
        expenses = [e for e in expenses if e["date"].startswith(args.year)]
    if not expenses:
        print("No expenses to summarize.")
        return
    totals = defaultdict(float)
    for e in expenses:
        totals[e["category"]] += e["amount"]
    grand = sum(totals.values())
    label = f" for {args.month or args.year}" if (args.month or args.year) else ""
    print(f"Expense summary{label}:")
    print("-" * 30)
    for cat, tot in sorted(totals.items(), key=lambda x: -x[1]):
        print(f"{cat:<15}{fmt_money(tot, cfg)}")
    print("-" * 30)
    print(f"{'Total':<15}{fmt_money(grand, cfg)}")
    if args.income:
        income = data["income"]
        if args.month:
            income = [i for i in income if i["date"].startswith(args.month)]
        total_income = sum(i["amount"] for i in income)
        print(f"\nIncome: {fmt_money(total_income, cfg)}   Net: {fmt_money(total_income - grand, cfg)}")


def cmd_stats(args):
    cfg = load_config()
    data = load_data()
    amounts = [e["amount"] for e in data["expenses"]]
    if not amounts:
        print("No expenses for stats.")
        return
    print(f"Count:  {len(amounts)}")
    print(f"Total:  {fmt_money(sum(amounts), cfg)}")
    print(f"Mean:   {fmt_money(statistics.mean(amounts), cfg)}")
    print(f"Median: {fmt_money(statistics.median(amounts), cfg)}")
    if len(amounts) > 1:
        print(f"StdDev: {fmt_money(statistics.stdev(amounts), cfg)}")
    print(f"Min:    {fmt_money(min(amounts), cfg)}   Max: {fmt_money(max(amounts), cfg)}")
    monthly = defaultdict(float)
    for e in data["expenses"]:
        monthly[e["date"][:7]] += e["amount"]
    print("\nMonthly trend:")
    bar_chart(sorted(monthly.items()))
    cat_counts = Counter(e["category"] for e in data["expenses"])
    print("\nMost frequent categories:")
    for cat, n in cat_counts.most_common(5):
        print(f"  {cat:<15}{n} expense(s)")


def cmd_compare(args):
    cfg = load_config()
    data = load_data()

    def totals_for(month):
        t = defaultdict(float)
        for e in data["expenses"]:
            if e["date"].startswith(month):
                t[e["category"]] += e["amount"]
        return t

    a, b = totals_for(args.month1), totals_for(args.month2)
    cats = sorted(set(a) | set(b))
    if not cats:
        print("No data for comparison.")
        return
    print(f"{'Category':<15}{args.month1:>12}{args.month2:>12}{'Change':>14}")
    for cat in cats:
        v1, v2 = a.get(cat, 0.0), b.get(cat, 0.0)
        diff = v2 - v1
        marker = c(f"+{diff:.2f}", "red", cfg) if diff > 0 else c(f"{diff:.2f}", "green", cfg)
        print(f"{cat:<15}{v1:>12.2f}{v2:>12.2f}{marker:>22}")


def cmd_report(args):
    cfg = load_config()
    data = load_data()
    period = args.month or args.year or "all time"
    expenses = data["expenses"]
    if args.month:
        expenses = [e for e in expenses if e["date"].startswith(args.month)]
    elif args.year:
        expenses = [e for e in expenses if e["date"].startswith(args.year)]
    print(c(f"=== PyTrack Report: {period} ===", "bold", cfg))
    if not expenses:
        print("No expense data for this period.")
    else:
        total = sum(e["amount"] for e in expenses)
        print(f"\nTotal spent: {fmt_money(total, cfg)} across {len(expenses)} expense(s).")
        by_cat = defaultdict(float)
        for e in expenses:
            by_cat[e["category"]] += e["amount"]
        print("\nTop categories:")
        bar_chart(sorted(by_cat.items(), key=lambda x: -x[1])[:5])
        print("\nLargest expenses:")
        for e in sorted(expenses, key=lambda x: -x["amount"])[:5]:
            print(f"  {e['date']}  {e['category']:<15}{fmt_money(e['amount'], cfg):>10}  {e.get('note', '')}")
    if data["budgets"]:
        print("\nBudget status:")
        cmd_budget_status(argparse.Namespace(period="monthly"))
    if data["goals"]:
        print("\nSavings goals:")
        cmd_goal_list(args)
    if data["accounts"]:
        print("\nAccount balances:")
        net = sum(a["balance"] for a in data["accounts"])
        for a in data["accounts"]:
            print(f"  {a['name']:<15}{fmt_money(a['balance'], cfg)}")
        print(f"  {'Net worth':<15}{fmt_money(net, cfg)}")


# --------------------------------------------------------------------------
# Import / export / backup / validate
# --------------------------------------------------------------------------

def cmd_export(args):
    data = load_data()
    rows = data["expenses"]
    if args.format == "json":
        with open(args.output, "w") as f:
            json.dump(rows, f, indent=2)
    else:
        with open(args.output, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "date", "category", "amount", "currency",
                                               "note", "tags", "account"])
            w.writeheader()
            for e in rows:
                r = dict(e)
                r["tags"] = ",".join(e.get("tags", []))
                w.writerow(r)
    print(f"Exported {len(rows)} expenses to {args.output}.")


def cmd_import(args):
    data = load_data()
    push_undo(data)
    if args.format == "json":
        with open(args.input) as f:
            items = json.load(f)
    else:
        with open(args.input, newline="") as f:
            items = list(csv.DictReader(f))
    added = 0
    for it in items:
        tags = it.get("tags", "") or ""
        tags = tags.split(",") if isinstance(tags, str) else tags
        data["expenses"].append({
            "id": next_id(data["expenses"]), "date": it["date"], "category": it["category"].lower(),
            "amount": round(float(it["amount"]), 2), "currency": it.get("currency", "USD"),
            "note": it.get("note", ""), "tags": [t.strip().lower() for t in tags if t.strip()],
            "account": it.get("account") or None})
        added += 1
    save_data(data)
    print(f"Imported {added} expense(s) from {args.input}.")


def cmd_backup(args):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        print("No data file to back up.")
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUP_DIR, f"ptdata_{stamp}.json")
    shutil.copy2(DATA_FILE, dest)
    print(f"Backed up to {dest}.")


def cmd_restore(args):
    if args.list:
        if not os.path.isdir(BACKUP_DIR) or not os.listdir(BACKUP_DIR):
            print("No backups found.")
            return
        for f in sorted(os.listdir(BACKUP_DIR)):
            print(f)
        return
    if not args.file:
        print("Specify a backup file with --file, or use --list to see options.")
        sys.exit(1)
    src = args.file if os.path.isabs(args.file) else os.path.join(BACKUP_DIR, args.file)
    if not os.path.exists(src):
        print("Backup file not found.")
        sys.exit(1)
    shutil.copy2(src, DATA_FILE)
    print(f"Restored from {src}.")


def cmd_validate(args):
    data = load_data()
    issues = []
    acct_names = {a["name"] for a in data["accounts"]}
    for e in data["expenses"]:
        if e.get("account") and e["account"] not in acct_names:
            issues.append(f"Expense #{e['id']} references unknown account '{e['account']}'.")
        if e["amount"] < 0:
            issues.append(f"Expense #{e['id']} has a negative amount.")
    for b in data["budgets"]:
        if b["amount"] <= 0:
            issues.append(f"Budget #{b['id']} ({b['category']}) has a non-positive amount.")
    person_names = {p["name"] for p in data["people"]}
    for s in data["splits"]:
        for p in s["participants"]:
            if p not in person_names:
                issues.append(f"Split #{s['id']} references unknown person '{p}'.")
    if not issues:
        print("Data looks consistent. No issues found.")
        return
    print(f"Found {len(issues)} issue(s):")
    for i in issues:
        print(f"  - {i}")


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def cmd_config(args):
    cfg = load_config()
    if args.action == "list":
        for k, v in cfg.items():
            print(f"{k} = {v}")
    elif args.action == "get":
        print(cfg.get(args.key, "Not set."))
    elif args.action == "set":
        val = args.value
        if val.lower() in ("true", "false"):
            val = val.lower() == "true"
        elif re.match(r"^-?\d+(\.\d+)?$", val):
            val = float(val) if "." in val else int(val)
        cfg[args.key] = val
        save_config(cfg)
        print(f"Set {args.key} = {val}.")
    elif args.action == "reset":
        save_config(dict(DEFAULT_CONFIG))
        print("Config reset to defaults.")


# --------------------------------------------------------------------------
# Demo data
# --------------------------------------------------------------------------

def cmd_demo(args):
    existing = load_data()
    if (existing["expenses"] or existing["accounts"]) and not args.force:
        print("Data already exists. Use --force to overwrite with demo data.")
        return
    data = deepcopy(EMPTY_DATA)
    data["accounts"] = [
        {"id": 1, "name": "checking", "type": "bank", "currency": "USD", "balance": 2450.00},
        {"id": 2, "name": "savings", "type": "bank", "currency": "USD", "balance": 8000.00},
        {"id": 3, "name": "credit-card", "type": "credit", "currency": "USD", "balance": -320.15},
    ]
    sample = [
        ("2026-07-01", "rent", 1200, "checking", "Monthly rent", "housing"),
        ("2026-07-02", "groceries", 84.32, "checking", "Weekly shop", "food"),
        ("2026-07-04", "transport", 45.00, "checking", "Gas", "car"),
        ("2026-07-06", "subscriptions", 15.99, "credit-card", "Streaming service", "entertainment"),
        ("2026-07-10", "dining", 62.50, "credit-card", "Dinner out", "food"),
        ("2026-07-15", "utilities", 130.00, "checking", "Electric bill", "housing"),
        ("2026-08-01", "rent", 1200, "checking", "Monthly rent", "housing"),
        ("2026-08-03", "groceries", 91.10, "checking", "Weekly shop", "food"),
        ("2026-08-05", "entertainment", 40.00, "credit-card", "Movie night", "fun"),
        ("2026-08-12", "travel", 520.00, "credit-card", "Weekend trip", "fun"),
        ("2026-09-01", "rent", 1200, "checking", "Monthly rent", "housing"),
        ("2026-09-02", "groceries", 76.40, "checking", "Weekly shop", "food"),
        ("2026-09-05", "subscriptions", 15.99, "credit-card", "Streaming service", "entertainment"),
    ]
    for i, (date, cat, amt, acct, note, tag) in enumerate(sample, start=1):
        data["expenses"].append({"id": i, "date": date, "category": cat, "amount": amt, "currency": "USD",
                                  "note": note, "tags": [tag], "account": acct})
    data["income"] = [
        {"id": 1, "date": "2026-07-01", "source": "salary", "amount": 4200.0, "currency": "USD",
         "note": "Monthly pay", "account": "checking"},
        {"id": 2, "date": "2026-08-01", "source": "salary", "amount": 4200.0, "currency": "USD",
         "note": "Monthly pay", "account": "checking"},
        {"id": 3, "date": "2026-09-01", "source": "salary", "amount": 4200.0, "currency": "USD",
         "note": "Monthly pay", "account": "checking"},
    ]
    data["budgets"] = [{"id": 1, "category": "food", "amount": 300.0, "period": "monthly"},
                       {"id": 2, "category": "entertainment", "amount": 100.0, "period": "monthly"}]
    data["goals"] = [{"id": 1, "name": "Emergency fund", "target": 10000.0, "saved": 8000.0,
                      "deadline": "2027-01-01"}]
    data["rules"] = [{"id": 1, "keyword": "netflix", "category": "subscriptions"},
                      {"id": 2, "keyword": "uber", "category": "transport"}]
    data["people"] = [{"id": 1, "name": "alex"}, {"id": 2, "name": "sam"}]
    data["splits"] = [{"id": 1, "date": "2026-08-12", "description": "Weekend trip cabin", "amount": 300.0,
                       "payer": "alex", "participants": ["alex", "sam"], "share": 150.0}]
    save_data(data)
    print("Demo data loaded. Try: report | budget status | goal list | stats | split settle")


# --------------------------------------------------------------------------
# Interactive shell
# --------------------------------------------------------------------------

def cmd_shell(args):
    parser = build_parser()
    print(f"PyTrack Pro v{VERSION} interactive shell. Type 'help' for commands, 'exit' to quit.")
    while True:
        try:
            line = input("pytrack> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("exit", "quit"):
            break
        if line == "help":
            parser.print_help()
            continue
        try:
            ns = parser.parse_args(shlex.split(line))
            ns.func(ns)
        except SystemExit:
            continue
        except Exception as ex:
            print(f"Error: {ex}")


# --------------------------------------------------------------------------
# Argument parser
# --------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(prog="pytrack",
                                      description="PyTrack Pro - an advanced command-line finance tracker.")
    parser.add_argument("--version", action="version", version=f"PyTrack Pro {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    # -- expenses --
    p = sub.add_parser("add", help="Add a new expense")
    p.add_argument("amount")
    p.add_argument("category", nargs="?", default="", help="Category (omit to auto-categorize from note)")
    p.add_argument("-d", "--date")
    p.add_argument("-n", "--note")
    p.add_argument("-t", "--tags", help="Comma-separated tags")
    p.add_argument("-a", "--account")
    p.add_argument("-c", "--currency")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="List expenses")
    p.add_argument("-c", "--category")
    p.add_argument("-m", "--month")
    p.add_argument("-t", "--tag")
    p.add_argument("-a", "--account")
    p.add_argument("--min", type=float)
    p.add_argument("--max", type=float)
    p.add_argument("--from", dest="frm")
    p.add_argument("--to")
    p.add_argument("--text", help="Regex/substring search in note")
    p.add_argument("--sort", default="date", choices=["id", "date", "category", "amount"])
    p.add_argument("--desc", action="store_true", help="Sort descending")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("edit", help="Edit an expense")
    p.add_argument("id", type=int)
    p.add_argument("--amount", type=float)
    p.add_argument("--category")
    p.add_argument("--date")
    p.add_argument("--note")
    p.add_argument("--tags")
    p.set_defaults(func=cmd_edit)

    p = sub.add_parser("delete", help="Delete an expense by ID")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("search", help="Search expenses by text/amount/date")
    p.add_argument("query", nargs="?")
    p.add_argument("--min", type=float)
    p.add_argument("--max", type=float)
    p.add_argument("--from", dest="frm")
    p.add_argument("--to")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("dupes", help="Find potential duplicate expenses")
    p.set_defaults(func=cmd_dupes)

    # -- categories / tags --
    cat_p = sub.add_parser("category", help="Manage categories")
    cat_sub = cat_p.add_subparsers(dest="action", required=True)
    cat_sub.add_parser("list").set_defaults(func=cmd_category_list)
    r = cat_sub.add_parser("rename")
    r.add_argument("old")
    r.add_argument("new")
    r.set_defaults(func=cmd_category_rename)

    tag_p = sub.add_parser("tag", help="Manage tags")
    tag_sub = tag_p.add_subparsers(dest="action", required=True)
    tag_sub.add_parser("list").set_defaults(func=cmd_tag_list)
    r = tag_sub.add_parser("rename")
    r.add_argument("old")
    r.add_argument("new")
    r.set_defaults(func=cmd_tag_rename)

    # -- income --
    inc_p = sub.add_parser("income", help="Manage income")
    inc_sub = inc_p.add_subparsers(dest="action", required=True)
    a = inc_sub.add_parser("add")
    a.add_argument("amount", type=float)
    a.add_argument("source")
    a.add_argument("-d", "--date")
    a.add_argument("-a", "--account")
    a.add_argument("-c", "--currency")
    a.add_argument("-n", "--note")
    a.set_defaults(func=cmd_income_add)
    l = inc_sub.add_parser("list")
    l.add_argument("-m", "--month")
    l.set_defaults(func=cmd_income_list)
    d = inc_sub.add_parser("delete")
    d.add_argument("id", type=int)
    d.set_defaults(func=cmd_income_delete)

    # -- accounts --
    acc_p = sub.add_parser("account", help="Manage accounts")
    acc_sub = acc_p.add_subparsers(dest="action", required=True)
    a = acc_sub.add_parser("add")
    a.add_argument("name")
    a.add_argument("-t", "--type", help="cash/bank/credit/investment")
    a.add_argument("-c", "--currency")
    a.add_argument("-b", "--balance", type=float, default=0.0)
    a.set_defaults(func=cmd_account_add)
    acc_sub.add_parser("list").set_defaults(func=cmd_account_list)
    e = acc_sub.add_parser("edit")
    e.add_argument("id", type=int)
    e.add_argument("--name")
    e.add_argument("--balance", type=float)
    e.add_argument("--type")
    e.set_defaults(func=cmd_account_edit)
    d = acc_sub.add_parser("delete")
    d.add_argument("id", type=int)
    d.set_defaults(func=cmd_account_delete)
    t = acc_sub.add_parser("transfer")
    t.add_argument("frm", help="Source account name")
    t.add_argument("to", help="Destination account name")
    t.add_argument("amount", type=float)
    t.set_defaults(func=cmd_account_transfer)

    # -- budgets --
    bud_p = sub.add_parser("budget", help="Manage budgets")
    bud_sub = bud_p.add_subparsers(dest="action", required=True)
    s = bud_sub.add_parser("set")
    s.add_argument("category")
    s.add_argument("amount", type=float)
    s.add_argument("-p", "--period", default="monthly", choices=["monthly", "yearly"])
    s.set_defaults(func=cmd_budget_set)
    bud_sub.add_parser("list").set_defaults(func=cmd_budget_list)
    d = bud_sub.add_parser("delete")
    d.add_argument("id", type=int)
    d.set_defaults(func=cmd_budget_delete)
    st = bud_sub.add_parser("status")
    st.add_argument("-p", "--period", choices=["monthly", "yearly"])
    st.set_defaults(func=cmd_budget_status)

    # -- recurring --
    rec_p = sub.add_parser("recurring", help="Manage recurring expenses")
    rec_sub = rec_p.add_subparsers(dest="action", required=True)
    a = rec_sub.add_parser("add")
    a.add_argument("category")
    a.add_argument("amount", type=float)
    a.add_argument("-f", "--frequency", default="monthly", choices=["daily", "weekly", "monthly", "yearly"])
    a.add_argument("-d", "--date", help="Start date (default: today)")
    a.add_argument("-e", "--end", help="End date (optional)")
    a.add_argument("-a", "--account")
    a.add_argument("-c", "--currency")
    a.add_argument("-n", "--note")
    a.set_defaults(func=cmd_recurring_add)
    rec_sub.add_parser("list").set_defaults(func=cmd_recurring_list)
    d = rec_sub.add_parser("delete")
    d.add_argument("id", type=int)
    d.set_defaults(func=cmd_recurring_delete)
    rec_sub.add_parser("generate").set_defaults(func=cmd_recurring_generate)

    # -- goals --
    goal_p = sub.add_parser("goal", help="Manage savings goals")
    goal_sub = goal_p.add_subparsers(dest="action", required=True)
    a = goal_sub.add_parser("add")
    a.add_argument("name")
    a.add_argument("target", type=float)
    a.add_argument("-d", "--deadline")
    a.set_defaults(func=cmd_goal_add)
    ct = goal_sub.add_parser("contribute")
    ct.add_argument("id", type=int)
    ct.add_argument("amount", type=float)
    ct.set_defaults(func=cmd_goal_contribute)
    goal_sub.add_parser("list").set_defaults(func=cmd_goal_list)
    d = goal_sub.add_parser("delete")
    d.add_argument("id", type=int)
    d.set_defaults(func=cmd_goal_delete)

    # -- people / splits --
    per_p = sub.add_parser("person", help="Manage people (for split expenses)")
    per_sub = per_p.add_subparsers(dest="action", required=True)
    a = per_sub.add_parser("add")
    a.add_argument("name")
    a.set_defaults(func=cmd_person_add)
    per_sub.add_parser("list").set_defaults(func=cmd_person_list)

    split_p = sub.add_parser("split", help="Manage shared/split expenses")
    split_sub = split_p.add_subparsers(dest="action", required=True)
    a = split_sub.add_parser("add")
    a.add_argument("description")
    a.add_argument("amount", type=float)
    a.add_argument("payer")
    a.add_argument("participants", help="Comma-separated participant names")
    a.add_argument("-d", "--date")
    a.set_defaults(func=cmd_split_add)
    split_sub.add_parser("list").set_defaults(func=cmd_split_list)
    d = split_sub.add_parser("delete")
    d.add_argument("id", type=int)
    d.set_defaults(func=cmd_split_delete)
    split_sub.add_parser("settle").set_defaults(func=cmd_split_settle)

    # -- rules --
    rule_p = sub.add_parser("rule", help="Manage auto-categorization rules")
    rule_sub = rule_p.add_subparsers(dest="action", required=True)
    a = rule_sub.add_parser("add")
    a.add_argument("keyword")
    a.add_argument("category")
    a.set_defaults(func=cmd_rule_add)
    rule_sub.add_parser("list").set_defaults(func=cmd_rule_list)
    d = rule_sub.add_parser("delete")
    d.add_argument("id", type=int)
    d.set_defaults(func=cmd_rule_delete)

    # -- summary / stats / reporting --
    p = sub.add_parser("summary", help="Spending summary by category")
    p.add_argument("-m", "--month")
    p.add_argument("-y", "--year")
    p.add_argument("--income", action="store_true", help="Include income and net total")
    p.set_defaults(func=cmd_summary)

    sub.add_parser("stats", help="Statistical breakdown of spending").set_defaults(func=cmd_stats)

    p = sub.add_parser("compare", help="Compare two months side by side")
    p.add_argument("month1")
    p.add_argument("month2")
    p.set_defaults(func=cmd_compare)

    p = sub.add_parser("report", help="Full financial report")
    p.add_argument("-m", "--month")
    p.add_argument("-y", "--year")
    p.set_defaults(func=cmd_report)

    # -- import / export / backup --
    p = sub.add_parser("export", help="Export expenses to CSV or JSON")
    p.add_argument("output")
    p.add_argument("-f", "--format", default="csv", choices=["csv", "json"])
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("import", help="Import expenses from CSV or JSON")
    p.add_argument("input")
    p.add_argument("-f", "--format", default="csv", choices=["csv", "json"])
    p.set_defaults(func=cmd_import)

    sub.add_parser("backup", help="Back up the data file").set_defaults(func=cmd_backup)
    p = sub.add_parser("restore", help="Restore from a backup")
    p.add_argument("--file")
    p.add_argument("--list", action="store_true")
    p.set_defaults(func=cmd_restore)

    sub.add_parser("validate", help="Check data for integrity issues").set_defaults(func=cmd_validate)
    sub.add_parser("undo", help="Undo the last change").set_defaults(func=cmd_undo)
    sub.add_parser("redo", help="Redo the last undone change").set_defaults(func=cmd_redo)

    # -- config / demo / shell --
    cfg_p = sub.add_parser("config", help="View or change settings")
    cfg_sub = cfg_p.add_subparsers(dest="action", required=True)
    cfg_sub.add_parser("list").set_defaults(func=cmd_config)
    g = cfg_sub.add_parser("get")
    g.add_argument("key")
    g.set_defaults(func=cmd_config)
    s = cfg_sub.add_parser("set")
    s.add_argument("key")
    s.add_argument("value")
    s.set_defaults(func=cmd_config)
    cfg_sub.add_parser("reset").set_defaults(func=cmd_config)

    p = sub.add_parser("demo", help="Load sample demo data")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_demo)

    sub.add_parser("shell", help="Start an interactive shell").set_defaults(func=cmd_shell)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(130)
    except (OSError, ValueError) as ex:
        print(f"Error: {ex}")
        sys.exit(1)


if __name__ == "__main__":
    main()
