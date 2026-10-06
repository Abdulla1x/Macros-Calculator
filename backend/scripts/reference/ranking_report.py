"""Does the search put the plain food in the top 3? Run after any table or
ranking change:  venv/bin/python scripts/reference/ranking_report.py

The queries are the owner's real generic foods (his library export,
2026-10-05) plus the searches in his screenshots. Each pattern says what a
"plain generic row" for that query looks like; they were written BEFORE the
first run, and the pass bar agreed with the owner is 90% of queries.

A pattern is a regex matched against the result's name, lowercased.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.reference_foods import search  # noqa: E402

PASS_BAR = 0.90

QUERIES = {
    "apple": r"^apples?, raw",
    "green apple": r"granny smith|^apples?, raw",  # no table says "green apple"
    "banana": r"^bananas?, raw",
    "mango": r"^mango(e?s)?, raw",
    "peach": r"^peach(es)?, raw",
    "lemon": r"^lemons?, raw",
    "sweet potato": r"^sweet ?potato(es)?\b.*(raw|baked|boiled|cooked)",
    "boiled egg": r"egg.*\bboiled\b",
    "fried egg": r"egg.*\bfried\b",
    "raw egg": r"^eggs?, whole, raw",
    "honey": r"^honey\b",
    "white sugar": r"^sugars?, (granulated|white)|^white sugar",
    "frozen strawberries": r"^strawberr.*frozen",
    "greek yogurt": r"yogh?urt, greek|greek.*yogh?urt",
    "milk": r"^milk, (whole|reduced fat|lowfat|fluid|cow)",
    "tea": r"^tea\b",
    "arabic bread": r"pita|arabic",
    "brown bread": r"bread, (whole.?wheat|wheat|brown|wholemeal)|brown bread",
    "ghee": r"ghee",
    "oats": r"^oats?\b|^cereals?, oats",
    "moong dal": r"mung|moong",
    "lentils": r"^lentils?\b.*(raw|cooked|boiled)",
    "rice": r"^rice, white",
    "chicken breast": r"chicken.*breast",
    "beef": r"^beef, ground",
}


def evaluate(verbose: bool = False) -> float:
    """The share of QUERIES whose top 3 holds a row matching its pattern."""
    passed = 0
    for query, pattern in QUERIES.items():
        top = search(query, limit=3)
        hit = any(re.search(pattern, food.name.lower()) for food in top)
        passed += hit
        if verbose:
            print(f"{'PASS' if hit else 'FAIL'}  {query!r}")
            for food in top:
                print(f"        {food.source:6} {food.name[:72]:72} {food.calories:g} kcal")
    rate = passed / len(QUERIES)
    if verbose:
        print(f"\n{passed}/{len(QUERIES)} = {rate:.0%} (bar {PASS_BAR:.0%})")
    return rate


def main() -> int:
    return 0 if evaluate(verbose=True) >= PASS_BAR else 1


if __name__ == "__main__":
    sys.exit(main())
