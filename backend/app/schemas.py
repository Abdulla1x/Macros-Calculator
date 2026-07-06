from datetime import date as date_type
from typing import Literal

from pydantic import BaseModel, Field


class MealCreate(BaseModel):
    date: date_type
    name: str = Field(min_length=1, max_length=200)
    calories: float = Field(ge=0)
    protein: float = Field(ge=0)
    carbs: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)


class Meal(MealCreate):
    id: int


class FoodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    serving_size: float = Field(gt=0, description="grams per serving")
    calories: float = Field(ge=0)
    protein: float = Field(ge=0)
    carbs: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)
    source: Literal["user", "openfoodfacts"] = "user"


class Food(FoodCreate):
    id: int


class OFFProduct(BaseModel):
    """A normalized Open Food Facts search result (macros per serving_size grams)."""
    name: str
    brand: str | None = None
    serving_size: float
    calories: float
    protein: float
    carbs: float | None = None
    fat: float | None = None
    source: Literal["openfoodfacts"] = "openfoodfacts"


class Settings(BaseModel):
    calorie_goal: float = Field(gt=0)
    protein_goal: float = Field(gt=0)
    carbs_goal: float = Field(gt=0)
    fat_goal: float = Field(gt=0)
    track_carbs: bool
    track_fat: bool


class DayTotals(BaseModel):
    date: date_type
    calories: float
    protein: float
    carbs: float | None = None
    fat: float | None = None


class AnalyticsSummary(BaseModel):
    days: list[DayTotals]
    totals: dict[str, float]
    averages: dict[str, float]


class ImportResult(BaseModel):
    inserted: int
    skipped_duplicates: int
    skipped_invalid: int
