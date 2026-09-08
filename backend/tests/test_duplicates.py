"""The near-duplicate detector's thresholds, on plain values.

Its own file rather than a section of test_foods.py, for the reason
test_upsert.py and test_calculations.py are their own files: app/duplicates.py
has no database and no request, so its constants can be pushed on directly.
The endpoint that wraps it is tested in test_foods.py.

Every pair below is either a real row or a food someone actually keeps. A
threshold tuned against invented numbers is tuned against nothing.
"""
from app import duplicates
from app.duplicates import (
    LibraryFood,
    find_duplicates,
    looks_like_duplicate,
    name_similarity,
    tokens,
)

# The two rows in the legacy single-user macros.db -- the only real library on
# record, and a duplicate pair at n=2. 120 kcal/100 g against 140.
EGGS_A = LibraryFood(1, "Free range hard boiled eggs", 90, 108, 11.7)
EGGS_B = LibraryFood(2, "Large White Eggs-Hard boiled", 50, 70, 6.0)


def test_the_real_egg_pair_is_reported():
    assert looks_like_duplicate(EGGS_A, EGGS_B)


def test_chicken_breast_and_thigh_are_not_duplicates():
    """The pair a name-only check gets wrong, and why the macro gate exists.

    Their names sit at exactly NAME_SIMILARITY, so the name gate admits them and
    only the calorie comparison separates them. Raising the name threshold until
    it caught this would push it past the egg pair above.
    """
    breast = LibraryFood(1, "Chicken breast", 100, 165, 31)
    thigh = LibraryFood(2, "Chicken thigh", 100, 209, 26)

    assert name_similarity(breast.name, thigh.name) == duplicates.NAME_SIMILARITY
    assert not looks_like_duplicate(breast, thigh)


def test_two_lettuces_are_reported_and_only_the_absolute_floor_catches_them():
    """The case the relative band alone gets wrong.

    12 and 15 kcal per 100 g are 22% apart, which is outside CALORIE_TOLERANCE
    and obviously the same food. Broken on purpose here rather than asserted:
    with the floor removed the pair is rejected, so this test genuinely depends
    on the floor rather than passing for some other reason.
    """
    a = LibraryFood(1, "Iceberg lettuce", 100, 12, 1.4)
    b = LibraryFood(2, "Lettuce, iceberg", 80, 12, 1.0)

    assert looks_like_duplicate(a, b)
    assert not duplicates._close(12, 15, duplicates.CALORIE_TOLERANCE, floor=0)


def test_two_strengths_of_the_same_yoghurt_are_not_duplicates():
    """Different foods that share a name and sit close together.

    59 and 73 kcal per 100 g. This is what fixes CALORIE_FLOOR: at 15 the floor
    governed everything under 75 kcal/100 g and reported this pair, which swept
    in every yoghurt and milk in a library.
    """
    zero = LibraryFood(1, "Greek yogurt 0%", 100, 59, 10)
    two = LibraryFood(2, "Greek yogurt 2%", 100, 73, 9.0)

    assert not looks_like_duplicate(zero, two)


def test_unrelated_foods_share_no_tokens_and_are_not_compared_on_macros():
    oil = LibraryFood(1, "Olive oil", 100, 884, 0)
    rice = LibraryFood(2, "White rice", 100, 130, 2.7)

    assert name_similarity(oil.name, rice.name) == 0
    assert not looks_like_duplicate(oil, rice)


def test_a_plural_and_its_singular_are_one_token():
    assert tokens("Boiled eggs") == tokens("boiled egg")


def test_short_and_numeric_tokens_are_kept():
    """Dropping them is the obvious tidy-up and it would break these.

    The digit is the only thing telling these two names apart, so filtering
    short tokens would score them identical -- which is exactly what the DOM
    harness's own seeded foods look like.
    """
    assert name_similarity("Milk 1%", "Milk 2%") < 1
    assert name_similarity("Snapshot food 0", "Snapshot food 1") < 1


def test_a_name_with_no_letters_or_digits_resembles_nothing():
    """The division-by-zero guard: two empty token sets are not a perfect match."""
    assert name_similarity("---", "???") == 0


def test_pairs_are_never_grouped_transitively():
    """A resembles B and B resembles C, but A and C are not reported.

    The failure this refuses to make: 100 and 118 kcal are within tolerance, and
    so are 118 and 139, but 100 and 139 are not. A transitive grouping would put
    all three in one card and offer to delete rows the user was never shown a
    reason for.
    """
    a = LibraryFood(1, "Rolled oats", 100, 100, 11)
    b = LibraryFood(2, "Rolled oats jumbo", 100, 118, 12)
    c = LibraryFood(3, "Jumbo rolled oats", 100, 139, 13)

    reported = {(pair.a_id, pair.b_id) for pair in find_duplicates([a, b, c])}

    assert (1, 2) in reported
    assert (2, 3) in reported
    assert (1, 3) not in reported


def test_the_result_is_capped_and_keeps_the_most_alike():
    """More pairs than MAX_PAIRS, and the cap must not keep an arbitrary slice.

    Every food here matches every other, so the unbounded answer is far past the
    cap. The one exact-name pair has to survive it.
    """
    foods = [LibraryFood(n, f"Porridge oats {n}", 100, 100, 11) for n in range(12)]
    twin = LibraryFood(99, "Porridge oats 0", 100, 100, 11)

    pairs = find_duplicates([*foods, twin])

    assert len(pairs) == duplicates.MAX_PAIRS
    assert pairs[0].similarity == 1.0
    assert (pairs[0].a_id, pairs[0].b_id) == (0, 99)


def test_ordering_is_stable_across_calls():
    """The panel renders in this order and must not reshuffle between loads."""
    foods = [
        EGGS_A,
        EGGS_B,
        LibraryFood(3, "Boiled eggs", 100, 130, 12.5),
    ]
    assert find_duplicates(foods) == find_duplicates(foods)


def test_an_empty_library_has_no_duplicates():
    assert find_duplicates([]) == []
    assert find_duplicates([EGGS_A]) == []
