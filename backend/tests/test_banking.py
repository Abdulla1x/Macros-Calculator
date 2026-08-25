from datetime import date, timedelta

import pytest

from app.banking import (
    KIND_COMPENSATING,
    KIND_PLANNED,
    MAX_DAY_DELTA_KCAL,
    MAX_PLAN_DAYS,
    DayGoals,
    PlanEntry,
    apply_delta,
    check_floor,
    macro_kcal,
    split_delta,
    validate_plan,
)
from app.calculations import (
    FAT_FRACTION_OF_CALORIES,
    KCAL_PER_G_CARB,
    KCAL_PER_G_FAT,
    MIN_TARGET_FRACTION_OF_TDEE,
    MIN_TARGET_KCAL,
)

TODAY = date(2026, 8, 25)

# 2000 kcal split the way macro_targets would for an 80 kg person, so the
# fixture is internally consistent and a test that breaks that can be seen to.
GOALS = DayGoals(calories=2000.0, protein=144.0, carbs=200.0, fat=56.0)


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def refusals(**overrides):
    """validate_plan with a valid planned group as the baseline."""
    kwargs = dict(
        entries=[
            PlanEntry(day(2), 400.0),
            PlanEntry(day(3), -200.0),
            PlanEntry(day(4), -200.0),
        ],
        kind=KIND_PLANNED,
        event_date=day(2),
        today=TODAY,
        goals=GOALS,
        sex="male",
        tdee=2400.0,
    )
    kwargs.update(overrides)
    return validate_plan(kwargs.pop("entries"), **kwargs).refusals


# --- split_delta -------------------------------------------------------------


@pytest.mark.parametrize(
    "total,days",
    [(100, 3), (-100, 3), (0, 4), (1, 7), (-1, 7), (2500, 14), (-2500, 13), (7, 1)],
)
def test_split_sums_to_exactly_the_whole(total, days):
    parts = split_delta(total, days)
    assert len(parts) == days
    assert sum(parts) == total


def test_split_carries_the_sign_rather_than_flooring_it():
    # Python's floor division rounds toward negative infinity: -100 // 3 is -34,
    # and three of those is -102. The magnitude-then-sign route is what stops
    # a shave being 2 kcal deeper than the user asked for.
    assert split_delta(-100, 3) == [-34.0, -33.0, -33.0]
    assert split_delta(100, 3) == [34.0, 33.0, 33.0]


def test_split_gives_the_remainder_to_the_earliest_days():
    assert split_delta(10, 4) == [3.0, 3.0, 2.0, 2.0]


def test_split_refuses_zero_days():
    with pytest.raises(ValueError):
        split_delta(100, 0)


# --- apply_delta -------------------------------------------------------------


def test_protein_never_moves():
    for delta in (-800.0, -1.0, 0.0, 1.0, 800.0):
        assert apply_delta(GOALS, delta).protein == GOALS.protein


def test_carbs_and_fat_absorb_on_the_same_split_macro_targets_uses():
    adjusted = apply_delta(GOALS, 400.0)

    assert adjusted.calories == 2400.0
    # Fat takes a quarter of the moved calories, carbohydrate the rest.
    assert adjusted.fat == pytest.approx(
        GOALS.fat + (FAT_FRACTION_OF_CALORIES * 400.0) / KCAL_PER_G_FAT
    )
    assert adjusted.carbs == pytest.approx(
        GOALS.carbs + ((1 - FAT_FRACTION_OF_CALORIES) * 400.0) / KCAL_PER_G_CARB
    )
    # And the macros still account for the calories they were given.
    assert macro_kcal(adjusted) - macro_kcal(GOALS) == pytest.approx(400.0)


def test_the_delta_is_additive_and_does_not_rewrite_a_manual_split():
    # Goals set by hand need not add up to the calorie goal -- the four columns
    # are independent when targets_auto is off. Recomputing carbs as "whatever
    # is left" would silently replace the user's split with a different one.
    lopsided = DayGoals(calories=2000.0, protein=150.0, carbs=100.0, fat=50.0)
    assert macro_kcal(lopsided) != lopsided.calories

    adjusted = apply_delta(lopsided, -200.0)
    assert adjusted.carbs == pytest.approx(100.0 - 150.0 / KCAL_PER_G_CARB)
    assert adjusted.fat == pytest.approx(50.0 - 50.0 / KCAL_PER_G_FAT)
    # The gap the fixture started with is carried, not quietly closed.
    assert macro_kcal(adjusted) != adjusted.calories


def test_macros_floor_at_zero_rather_than_going_negative():
    thin = DayGoals(calories=900.0, protein=140.0, carbs=10.0, fat=4.0)
    adjusted = apply_delta(thin, -800.0)
    assert adjusted.carbs == 0.0
    assert adjusted.fat == 0.0
    assert adjusted.calories == 100.0


# --- check_floor -------------------------------------------------------------


def test_the_proportional_floor_binds_for_a_large_expenditure():
    floor, unchecked = check_floor(3200.0, "male", 3200.0)
    assert floor == 3200.0 * MIN_TARGET_FRACTION_OF_TDEE
    assert floor > MIN_TARGET_KCAL["male"]
    assert unchecked is None


def test_the_absolute_floor_binds_for_a_small_expenditure():
    floor, unchecked = check_floor(1400.0, "female", 1400.0)
    assert floor == MIN_TARGET_KCAL["female"]
    assert unchecked is None


def test_without_a_tdee_only_the_absolute_floor_is_checked_and_it_says_so():
    floor, unchecked = check_floor(2000.0, "male", None)
    assert floor == MIN_TARGET_KCAL["male"]
    assert unchecked is not None
    assert "expenditure" in unchecked


def test_without_a_sex_it_falls_back_to_the_lower_absolute_floor():
    # The same fallback target_calories takes for an unrecognised sex: a floor
    # too permissive for this person still beats no floor at all.
    floor, _ = check_floor(2000.0, None, None)
    assert floor == min(MIN_TARGET_KCAL.values())


# --- validate_plan: the shared rules ----------------------------------------


def test_a_balanced_planned_group_is_allowed():
    assert refusals() == []


def test_a_past_day_cannot_be_adjusted_and_the_refusal_names_it():
    said = refusals(
        entries=[PlanEntry(day(-1), 600.0), PlanEntry(day(3), -600.0)],
        event_date=day(-1),
    )
    assert any(day(-1).isoformat() in r and "already happened" in r for r in said)


def test_today_itself_can_be_adjusted():
    assert refusals(
        entries=[PlanEntry(day(0), 200.0), PlanEntry(day(1), -200.0)],
        event_date=day(0),
    ) == []


def test_a_plan_longer_than_the_cap_is_refused():
    entries = [PlanEntry(day(1), 1500.0)]
    entries += [PlanEntry(day(2 + i), -100.0) for i in range(MAX_PLAN_DAYS)]
    said = refusals(entries=entries, event_date=day(1))
    assert any(str(MAX_PLAN_DAYS) in r for r in said)


def test_an_oversized_single_day_is_refused_and_the_refusal_names_the_day():
    over = MAX_DAY_DELTA_KCAL + 100
    said = refusals(
        entries=[PlanEntry(day(1), over), PlanEntry(day(2), -over)],
        event_date=day(1),
        tdee=None,
        sex=None,
    )
    assert any(day(1).isoformat() in r for r in said)


def test_a_repeated_day_inside_one_plan_is_refused():
    said = refusals(
        entries=[PlanEntry(day(1), 600.0), PlanEntry(day(2), -300.0),
                 PlanEntry(day(2), -300.0)],
        event_date=day(1),
    )
    assert any(day(2).isoformat() in r and "twice" in r for r in said)


def test_an_empty_plan_is_refused():
    assert refusals(entries=[]) != []


def test_a_day_shaved_below_the_floor_is_refused_naming_the_day_and_the_floor():
    # A 2400 TDEE puts the proportional floor at 1800, so a 2000 goal has
    # exactly 200 kcal a day of shaving room: -200 lands on the floor and is
    # allowed, -400 goes through it.
    assert refusals(
        entries=[PlanEntry(day(1), 400.0), PlanEntry(day(2), -200.0),
                 PlanEntry(day(3), -200.0)],
        event_date=day(1),
    ) == []

    said = refusals(
        entries=[PlanEntry(day(1), 800.0), PlanEntry(day(2), -400.0),
                 PlanEntry(day(3), -400.0)],
        event_date=day(1),
    )
    assert len(said) == 2
    assert any(day(2).isoformat() in r for r in said)
    assert any(day(3).isoformat() in r for r in said)
    assert all(str(round(2400.0 * MIN_TARGET_FRACTION_OF_TDEE)) in r for r in said)


def test_every_breaching_day_is_reported_not_just_the_first():
    # A plan is validated as a set: reporting one day at a time would send the
    # user round the loop once per day.
    said = refusals(
        entries=[PlanEntry(day(1), 2400.0)] +
                [PlanEntry(day(2 + i), -600.0) for i in range(4)],
        event_date=day(1),
    )
    assert len(said) == 4


def test_an_unknown_kind_is_a_programmer_error():
    with pytest.raises(ValueError):
        validate_plan(
            [PlanEntry(day(1), 0.0)], kind="sideways", event_date=day(1),
            today=TODAY, goals=GOALS, sex="male", tdee=2400.0,
        )


# --- validate_plan: the two sum rules, which are not one rule ----------------


def test_planned_days_must_sum_to_zero():
    said = refusals(
        entries=[PlanEntry(day(2), 600.0), PlanEntry(day(3), -300.0)],
        event_date=day(2),
    )
    assert any("do not balance" in r for r in said)


def test_a_planned_group_must_contain_the_day_it_is_planning_for():
    said = refusals(
        entries=[PlanEntry(day(3), -300.0), PlanEntry(day(4), 300.0)],
        event_date=day(2),
    )
    assert any(day(2).isoformat() in r and "not one of" in r for r in said)


def test_compensating_days_sum_to_the_negation_of_the_surplus():
    # 600 eaten over on Sunday, shaved 200 a day across the next three.
    assert refusals(
        entries=[PlanEntry(day(1), -200.0), PlanEntry(day(2), -200.0),
                 PlanEntry(day(3), -200.0)],
        kind=KIND_COMPENSATING,
        event_date=day(-1),
        surplus_kcal=600.0,
    ) == []


def test_compensating_the_other_direction_when_a_bulk_day_ran_under():
    assert refusals(
        entries=[PlanEntry(day(1), 250.0), PlanEntry(day(2), 250.0)],
        kind=KIND_COMPENSATING,
        event_date=day(-2),
        surplus_kcal=-500.0,
    ) == []


def test_compensating_days_that_do_not_offset_the_surplus_are_refused():
    said = refusals(
        entries=[PlanEntry(day(1), -100.0), PlanEntry(day(2), -100.0)],
        kind=KIND_COMPENSATING,
        event_date=day(-1),
        surplus_kcal=600.0,
    )
    assert any("does not offset" in r for r in said)


def test_a_compensating_group_must_not_contain_its_own_event_day():
    # The other side of this ledger is the meals already logged on the event
    # day, not a row. A row there would read as a target change on a day that
    # is already finished.
    said = refusals(
        entries=[PlanEntry(day(0), -300.0), PlanEntry(day(1), -300.0)],
        kind=KIND_COMPENSATING,
        event_date=day(0),
        surplus_kcal=600.0,
    )
    assert any(day(0).isoformat() in r and "cannot also be" in r for r in said)


def test_the_event_day_of_a_compensating_plan_may_be_today():
    # The most common real case: dinner already blew today, shave from tomorrow.
    assert refusals(
        entries=[PlanEntry(day(1), -200.0), PlanEntry(day(2), -200.0),
                 PlanEntry(day(3), -200.0)],
        kind=KIND_COMPENSATING,
        event_date=day(0),
        surplus_kcal=600.0,
    ) == []


def test_a_future_event_day_cannot_be_compensated_for():
    said = refusals(
        entries=[PlanEntry(day(3), -600.0)],
        kind=KIND_COMPENSATING,
        event_date=day(2),
        surplus_kcal=600.0,
    )
    assert any("has not happened yet" in r for r in said)


def test_compensating_days_must_all_move_the_same_way():
    said = refusals(
        entries=[PlanEntry(day(1), -800.0), PlanEntry(day(2), 200.0)],
        kind=KIND_COMPENSATING,
        event_date=day(-1),
        surplus_kcal=600.0,
    )
    assert any("every day the same way" in r for r in said)


def test_a_compensating_plan_without_a_surplus_is_a_programmer_error():
    with pytest.raises(ValueError):
        validate_plan(
            [PlanEntry(day(1), -600.0)], kind=KIND_COMPENSATING,
            event_date=day(-1), today=TODAY, goals=GOALS, sex="male", tdee=2400.0,
        )


# --- the incomplete-profile path --------------------------------------------


def test_an_incomplete_profile_still_gets_the_absolute_floor_and_is_told_so():
    check = validate_plan(
        [PlanEntry(day(1), 900.0), PlanEntry(day(2), -900.0)],
        kind=KIND_PLANNED, event_date=day(1), today=TODAY,
        goals=GOALS, sex=None, tdee=None,
    )
    # 2000 - 900 = 1100, under the 1200 fallback floor, so it is still caught.
    assert check.refusals
    assert check.unchecked is not None


def test_the_unchecked_note_is_not_itself_a_refusal():
    check = validate_plan(
        [PlanEntry(day(1), 400.0), PlanEntry(day(2), -400.0)],
        kind=KIND_PLANNED, event_date=day(1), today=TODAY,
        goals=GOALS, sex=None, tdee=None,
    )
    assert check.refusals == []
    assert check.unchecked is not None


def test_the_proportional_floor_is_what_binds_and_it_binds_hard():
    """How much room a plan actually has, written down because it surprises.

    On a normal cut -- 2400 kcal expenditure, a 2000 kcal goal -- the floor
    sits at 1800, leaving 200 kcal a day. That is the constraint users will
    meet, not the 3000 kcal per-day cap, and it is why every floor refusal ends
    by telling them to spread wider rather than just saying no.
    """
    floor, _ = check_floor(2000.0, "male", 2400.0)
    assert 2000.0 - floor == 200.0

    # 600 kcal over three days fits exactly; over two it does not.
    assert refusals(
        entries=[PlanEntry(day(i), -200.0) for i in (1, 2, 3)],
        kind=KIND_COMPENSATING, event_date=day(-1), surplus_kcal=600.0,
    ) == []
    assert refusals(
        entries=[PlanEntry(day(i), -300.0) for i in (1, 2)],
        kind=KIND_COMPENSATING, event_date=day(-1), surplus_kcal=600.0,
    ) != []
