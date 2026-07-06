def scale_macros(
    weight: float,
    serving_size: float,
    per_serving: dict[str, float | None],
) -> dict[str, float | None]:
    """Scale per-serving macro values to the weight actually eaten.

    Keys with None values (untracked macros) stay None.
    """
    if serving_size <= 0:
        raise ValueError("Serving size must be greater than zero")
    if weight < 0:
        raise ValueError("Weight cannot be negative")

    factor = weight / serving_size
    return {
        key: None if value is None else round(value * factor, 2)
        for key, value in per_serving.items()
    }


def total_macros(items: list[dict[str, float | None]]) -> dict[str, float | None]:
    """Sum macros across ingredients. A macro totals to None only if no
    ingredient reported it; otherwise missing values count as 0."""
    keys = ("calories", "protein", "carbs", "fat")
    totals: dict[str, float | None] = {}
    for key in keys:
        values = [item[key] for item in items if item.get(key) is not None]
        totals[key] = round(sum(values), 2) if values else None
    return totals
