#!/usr/bin/env python3
"""
PyTrack - A simple command-line expense tracker.

Stores expenses locally in a JSON file and lets you add, list, filter,
delete, and summarize your spending straight from the terminal.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from collections import defaultdict

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expenses.json")


def load_expenses():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_expenses(expenses):
    with open(DATA_FILE, "w") as f:
        json.dump(expenses, f, indent=2)


def next_id(expenses):
    return (max((e["id"] for e in expenses), default=0)) + 1


def cmd_add(args):
    expenses = load_expenses()
    try:
        amount = float(args.amount)
    except ValueError:
        print("Error: amount must be a number.")
        sys.exit(1)

    date = args.date or datetime.now().strftime("%Y-%m-%d")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        print("Error: date must be in YYYY-MM-DD format.")
        sys.exit(1)

    expense = {
        "id": next_id(expenses),
        "date": date,
        "category": args.category.strip().lower(),
        "amount": round(amount, 2),
        "note": args.note or "",
    }
    expenses.append(expense)
    save_expenses(expenses)
    print(f"Added expense #{expense['id']}: {expense['category']} - ${expense['amount']:.2f} on {expense['date']}")


def cmd_list(args):
    expenses = load_expenses()

    if args.category:
        expenses = [e for e in expenses if e["category"] == args.category.strip().lower()]
    if args.month:
        expenses = [e for e in expenses if e["date"].startswith(args.month)]

    if not expenses:
        print("No expenses found.")
        return

    expenses.sort(key=lambda e: e["date"])
    print(f"{'ID':<4}{'Date':<12}{'Category':<15}{'Amount':<10}Note")
    print("-" * 60)
    for e in expenses:
        print(f"{e['id']:<4}{e['date']:<12}{e['category']:<15}${e['amount']:<9.2f}{e['note']}")


def cmd_delete(args):
    expenses = load_expenses()
    remaining = [e for e in expenses if e["id"] != args.id]
    if len(remaining) == len(expenses):
        print(f"No expense found with ID {args.id}.")
        sys.exit(1)
    save_expenses(remaining)
    print(f"Deleted expense #{args.id}.")


def cmd_summary(args):
    expenses = load_expenses()
    if args.month:
        expenses = [e for e in expenses if e["date"].startswith(args.month)]

    if not expenses:
        print("No expenses to summarize.")
        return

    totals = defaultdict(float)
    for e in expenses:
        totals[e["category"]] += e["amount"]

    grand_total = sum(totals.values())
    label = f" for {args.month}" if args.month else ""
    print(f"Expense summary{label}:")
    print("-" * 30)
    for category, total in sorted(totals.items(), key=lambda x: -x[1]):
        print(f"{category:<15}${total:.2f}")
    print("-" * 30)
    print(f"{'Total':<15}${grand_total:.2f}")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="pytrack",
        description="PyTrack - a simple command-line expense tracker.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_p = subparsers.add_parser("add", help="Add a new expense")
    add_p.add_argument("amount", help="Expense amount, e.g. 12.50")
    add_p.add_argument("category", help="Category, e.g. food, transport, rent")
    add_p.add_argument("-d", "--date", help="Date in YYYY-MM-DD format (default: today)")
    add_p.add_argument("-n", "--note", help="Optional note")
    add_p.set_defaults(func=cmd_add)

    list_p = subparsers.add_parser("list", help="List expenses")
    list_p.add_argument("-c", "--category", help="Filter by category")
    list_p.add_argument("-m", "--month", help="Filter by month, e.g. 2026-09")
    list_p.set_defaults(func=cmd_list)

    del_p = subparsers.add_parser("delete", help="Delete an expense by ID")
    del_p.add_argument("id", type=int, help="ID of the expense to delete")
    del_p.set_defaults(func=cmd_delete)

    sum_p = subparsers.add_parser("summary", help="Show spending summary by category")
    sum_p.add_argument("-m", "--month", help="Filter by month, e.g. 2026-09")
    sum_p.set_defaults(func=cmd_summary)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
