"""Which saved foods look like two rows for the same thing.

The library fills itself up without being asked -- every Open Food Facts pick is
cached, every ticked ingredient is saved, every AI estimate can be saved -- so
the same food arrives more than once under names nobody chose to make match.
`uq_foods_user_lower_name` already blocks the exact case, which means everything
left is a *near* duplicate and has to be judged rather than looked up.

The arithmetic only, on plain values, so every threshold below is reachable from
a test without a fixture -- the same shape `calculations.py` and `banking.py`
have.

**Two gates, and the second one is the whole design.** Names alone are not
enough: "chicken breast" and "chicken thigh" share half their words and are not
the same food, while "Free range hard boiled eggs" and "Large White Eggs-Hard
boiled" share three and are. A name check strict enough to separate the first
pair rejects the second. So a pair has to clear a name check *and* look alike
per 100 g, and the numbers are what carry the cases the names get wrong.

Nothing here deletes anything or decides anything. It answers "these two are
worth a second look", and the UI shows both rows in the same units so the user
can see for themselves.
"""
from collections.abc import Sequence
from typing import NamedTuple


class LibraryFood(NamedTuple):
    """One row, reduced to what a comparison needs.

    Deliberately not the ORM model: this module has no database, and a caller
    holding rows is one `LibraryFood(...)` away from using it.
    """

    id: int
    name: str
    serving_size: float
    calories: float
    protein: float


class DuplicatePair(NamedTuple):
    a_id: int
    b_id: int
    similarity: float


# Dice coefficient over name tokens. 0.5 is where "chicken breast" / "chicken
# thigh" sits exactly, so it is admitted by the name gate and rejected by the
# calorie one -- which is deliberate. Raising this until the names alone
# separated that pair would take the threshold past the egg pair above, and the
# egg pair is the one this feature exists for.
NAME_SIMILARITY = 0.5

# Per-100 g tolerances, each as a relative band with an absolute floor.
#
# ⚠️ The floors are load-bearing, not padding. A purely relative comparison
# explodes near zero: two lettuces at 12 and 15 kcal are "23% apart" and 0.5 g
# against 1.0 g of protein is "67% apart", and both pairs are the same food to
# anyone reading them. The floor is what stops the check being strictest exactly
# where the numbers matter least.
#
# ⚠️ Pick a floor by its CROSSOVER, not by how forgiving it feels. floor divided
# by tolerance is the density below which the floor governs and the percentage
# stops mattering: 8 / 0.20 = 40 kcal per 100 g, which is leafy veg, broths and
# diet drinks -- the foods a percentage genuinely cannot describe. This started
# at 15, whose crossover is 75 kcal, and that swept in every yoghurt and milk in
# a library: "Greek yogurt 0%" and "Greek yogurt 2%" (59 and 73 kcal) came back
# a duplicate pair, which they are not. Found by running the constants against
# real foods before any of this was wired up.
#
# Protein is the looser of the two because it moves most between preparations of
# one food, and calories already carry part of it. Its crossover is
# 2 / 0.35 = 5.7 g per 100 g -- vegetables, fruit and oils.
CALORIE_TOLERANCE = 0.20
CALORIE_FLOOR = 8.0
PROTEIN_TOLERANCE = 0.35
PROTEIN_FLOOR = 2.0

# What one screen can be asked to review. The comparison itself is O(n^2) over
# one user's rows and costs microseconds at any library size that exists; this
# caps what comes *back*, because a wall of pairs is not a review, it is a
# reason to close the tab.
MAX_PAIRS = 20


def tokens(name: str) -> frozenset[str]:
    """A name as a set of comparable words.

    Runs of letters and digits, lowercased, with a crude plural strip so "eggs"
    and "egg" are one token. The stemming is wrong on words like "hummus", and
    that is harmless here: it is wrong *identically on both sides*, and this
    only ever compares one name with another.

    ⚠️ Short tokens are NOT dropped, though dropping them is the obvious tidy-up.
    A number or a one-letter modifier is often the only thing telling two names
    apart -- "Milk 1%" and "Milk 2%", or the snapshot harness's own seeded
    foods -- and filtering them makes those pairs identical.
    """
    words = []
    current: list[str] = []
    for char in name.lower():
        if char.isalnum():
            current.append(char)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return frozenset(
        word[:-1] if len(word) > 3 and word.endswith("s") else word for word in words
    )


def name_similarity(a: str, b: str) -> float:
    """Dice coefficient of the two token sets, 0.0 to 1.0.

    Dice rather than Jaccard because it weights the shared half more kindly, and
    real food names carry a lot of words only one side has -- a brand, a "free
    range", a pack size. Jaccard punishes those twice.
    """
    left, right = tokens(a), tokens(b)
    total = len(left) + len(right)
    # A name with no alphanumerics at all. Comparing it to anything is a
    # division by zero, and it resembles nothing.
    if total == 0:
        return 0.0
    return 2 * len(left & right) / total


def _close(a: float, b: float, tolerance: float, floor: float) -> bool:
    """Are these two within `tolerance` of each other, or inside `floor`?"""
    return abs(a - b) <= max(floor, tolerance * (a + b) / 2)


def _per_100g(food: LibraryFood) -> tuple[float, float]:
    """Calories and protein per 100 g.

    The only units in which two library rows are comparable at all: each is
    stored against its own serving size, so 108 kcal / 90 g and 70 kcal / 50 g
    look further apart than they are and 120 kcal / 100 g against 140 is the
    honest reading of the same two rows.

    serving_size is a divisor and `FoodCreate` constrains it `gt=0`, so it
    cannot be zero here.
    """
    factor = 100 / food.serving_size
    return food.calories * factor, food.protein * factor


def looks_like_duplicate(a: LibraryFood, b: LibraryFood) -> bool:
    """Both gates, in the order that costs least."""
    if name_similarity(a.name, b.name) < NAME_SIMILARITY:
        return False
    a_calories, a_protein = _per_100g(a)
    b_calories, b_protein = _per_100g(b)
    return _close(
        a_calories, b_calories, CALORIE_TOLERANCE, CALORIE_FLOOR
    ) and _close(a_protein, b_protein, PROTEIN_TOLERANCE, PROTEIN_FLOOR)


def find_duplicates(foods: Sequence[LibraryFood]) -> list[DuplicatePair]:
    """Pairs worth a second look, most alike first.

    ⚠️ **Pairs, never clusters.** Grouping transitively -- A resembles B, B
    resembles C, therefore all three are one food -- is exactly where a fuzzy
    matcher goes wrong, and it goes wrong silently: the user is shown a group
    whose ends have nothing to do with each other, with no way to see why. Two
    rows side by side can be judged; a group cannot.

    Ordered by similarity so the cap keeps the best evidence rather than
    whichever rows sorted first, then by id so the answer is stable across
    calls -- the panel is rendered from this order and must not reshuffle
    between loads.
    """
    pairs = [
        DuplicatePair(a.id, b.id, name_similarity(a.name, b.name))
        for index, a in enumerate(foods)
        for b in foods[index + 1 :]
        if looks_like_duplicate(a, b)
    ]
    pairs.sort(key=lambda pair: (-pair.similarity, pair.a_id, pair.b_id))
    return pairs[:MAX_PAIRS]
