"""Generic foods from open national food-composition tables, searched in memory.

WHY THIS EXISTS. Open Food Facts is a packaged-goods database: "green apple"
finds French compotes and "beef" finds stock cubes. A new user has an empty
library, so the lookup is their whole manual-logging experience, and the plain
ingredient is what they need. The national tables have exactly that.

WHY IN MEMORY AND NOT A TABLE. The five tables come to ~25k rows of a name and
five numbers. Held in the process they cost ~10-20 MB and a search costs a few
milliseconds of Python, with no Neon compute per keystroke (Neon compute is
the next free-tier ceiling), no bulk load on deploy, and the same behaviour in
tests, dev and production. They change at most yearly, by re-running a build
script in scripts/reference/ and committing the CSV it writes.

WHY NOT USDA'S SEARCH API. Probed 2026-10-06: its ranking returned croissants
and asparagus for "green apple", each call took ~2 s, and 2 of 6 calls failed
with an HTML 400. Ranking here is ours, and it is tuned against real queries.

THE DATA. One CSV per table in data/reference/, named by its SOURCES key, with
the columns `source_id,name,calories,protein,carbs,fat,fibre`, all per 100 g.
Carbs exclude fibre whatever the table published (see ReferenceFood). A table
whose file is absent is simply not searched, so the app runs with none of them.
"""
import csv
import logging
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .schemas import ReferenceFood

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data" / "reference"

# Search order AND tie-break priority, so an identical name in two tables shows
# the first one's row. USDA first because it is the largest and the most
# complete; CNF last because much of it is copied from USDA anyway.
SOURCES = ("usda", "cofid", "ciqual", "afcd", "cnf")

# Words that would otherwise have to appear in the name: "chicken with rice"
# should not require the literal word "with".
STOPWORDS = frozenset({"a", "an", "and", "in", "of", "on", "the", "with"})

# Rows indexed under the first PREFIX_LEN letters of each of their words. A
# query token shorter than this falls back to scanning every row.
PREFIX_LEN = 3


def normalize(text: str) -> str:
    """Lowercase, accents folded, anything but letters and digits a space.

    Folding is what makes "creme" find Ciqual's "crème" and "jalapeno" find
    "jalapeño" -- people type without accents on a phone."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def singular(word: str) -> str:
    """A small English plural rule, enough for food names.

    Both the query and the name go through it, so "apple" and "apples" meet at
    "apple", "peaches" at "peach", "berries" at "berry" and "tomatoes" at
    "tomato". It only has to agree with itself, not be a real stemmer; "-us"
    and "-ss" are left alone so "hummus" and "swiss" survive."""
    if len(word) <= 3:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("oes", "ches", "shes", "sses", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us")):
        return word[:-1]
    return word


@dataclass(frozen=True, slots=True)
class _Entry:
    food: ReferenceFood
    norm: str  # the whole name, normalized: the cross-table de-dup key
    first: tuple[str, ...]  # words of the first comma segment, "Apples, raw" -> apples
    rest: tuple[str, ...]  # every other word


class _Index:
    def __init__(self, entries: list[_Entry]):
        self.entries = entries
        self.by_prefix: dict[str, list[int]] = {}
        for i, entry in enumerate(entries):
            # Under the singular form too: "fries" is looked up as "fry".
            words = entry.first + entry.rest
            prefixes = {w[:PREFIX_LEN] for w in words} | {singular(w)[:PREFIX_LEN] for w in words}
            for prefix in prefixes:
                self.by_prefix.setdefault(prefix, []).append(i)


_index: _Index | None = None
_lock = threading.Lock()


def _number(value: str) -> float | None:
    value = value.strip()
    return float(value) if value else None


def _read(source: str, path: Path) -> list[_Entry]:
    entries = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            calories, protein = _number(row["calories"]), _number(row["protein"])
            if calories is None or protein is None:
                continue  # the build scripts drop these; this is a guard
            name = row["name"].strip()
            head, _, tail = name.partition(",")
            entries.append(_Entry(
                food=ReferenceFood(
                    name=name,
                    calories=calories,
                    protein=protein,
                    carbs=_number(row["carbs"]),
                    fat=_number(row["fat"]),
                    source=source,
                ),
                norm=normalize(name),
                first=tuple(normalize(head).split()),
                rest=tuple(normalize(tail).split()),
            ))
    return entries


def _load() -> _Index:
    global _index
    with _lock:
        if _index is None:
            started = time.perf_counter()
            entries = []
            for source in SOURCES:
                path = DATA_DIR / f"{source}.csv"
                if path.exists():
                    entries.extend(_read(source, path))
            _index = _Index(entries)
            logger.info(
                "Reference foods loaded: %d rows in %.0f ms",
                len(entries), (time.perf_counter() - started) * 1000,
            )
    return _index


def clear_cache() -> None:
    """Forget the loaded tables; for tests that point DATA_DIR elsewhere."""
    global _index
    with _lock:
        _index = None


def _token_score(token: str, entry: _Entry) -> int:
    """How well one query token matches a row; 0 means not at all.

    A whole word beats a word merely starting with the token ("egg" is a whole
    word of "Egg, whole, raw" but only a prefix of "Eggplant"), and either
    beats the same match after the first comma, which is where tables put
    preparation and qualifiers rather than the food itself."""
    one = singular(token)
    best = 0
    for words, whole, prefix in ((entry.first, 6, 4), (entry.rest, 3, 2)):
        for word in words:
            if singular(word) == one:
                best = max(best, whole)
            elif word.startswith(one):
                best = max(best, prefix)
    return best


def _score(tokens: list[str], entry: _Entry) -> float | None:
    total = 0.0
    for token in tokens:
        points = _token_score(token, entry)
        if points == 0:
            return None  # every word of the query must be in the name
        total += points
    # The first segment IS the query ("Apples, raw" for "apple"), as opposed to
    # merely containing it ("Apple juice, canned"): that is the plain food.
    if {singular(w) for w in entry.first} == {singular(t) for t in tokens}:
        total += 5
    # Shorter names first among equals: "Apples, raw, with skin" over
    # "Apples, raw, with skin, frozen, unsweetened, heated".
    return total - 0.25 * (len(entry.first) + len(entry.rest))


def search(query: str, limit: int = 8) -> list[ReferenceFood]:
    started = time.perf_counter()
    tokens = [t for t in normalize(query).split() if t not in STOPWORDS]
    if not tokens:
        tokens = normalize(query).split()
    if not tokens:
        return []

    index = _load()
    # Candidates from the longest token's prefix: the rarer the prefix, the
    # fewer rows to score. Every hit must contain every token anyway.
    anchor = singular(max(tokens, key=len))
    if len(anchor) >= PREFIX_LEN:
        candidates = (index.entries[i] for i in index.by_prefix.get(anchor[:PREFIX_LEN], ()))
    else:
        candidates = iter(index.entries)

    scored = []
    for entry in candidates:
        score = _score(tokens, entry)
        if score is not None:
            scored.append((-score, len(entry.food.name), SOURCES.index(entry.food.source), entry))
    scored.sort(key=lambda item: item[:3])

    results: list[ReferenceFood] = []
    seen: set[str] = set()
    for *_, entry in scored:
        if entry.norm in seen:
            continue  # the same name in a lower-priority table
        seen.add(entry.norm)
        results.append(entry.food)
        if len(results) == limit:
            break

    # Counts and timing only. The query text is never logged: the line is for
    # measuring how often the tables answer, not for reading what people eat.
    logger.info(
        "Reference search: %d results, top %s, %.0f ms",
        len(results),
        results[0].source if results else "none",
        (time.perf_counter() - started) * 1000,
    )
    return results
