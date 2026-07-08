from datetime import date as date_type
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MealCreate(BaseModel):
    date: date_type
    name: str = Field(min_length=1, max_length=200)
    calories: float = Field(ge=0)
    protein: float = Field(ge=0)
    carbs: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)


class Meal(MealCreate):
    model_config = ConfigDict(from_attributes=True)

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
    model_config = ConfigDict(from_attributes=True)

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
    model_config = ConfigDict(from_attributes=True)

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


# NOTE: no numeric Field constraints here — this schema is sent to the LLM as a
# structured-output schema, and Gemini rejects JSON Schema numeric bounds
# (exclusiveMinimum etc.). Values are reviewed by the user before saving anyway.
class AnalyzedItem(BaseModel):
    """One detected food, with macros for the estimated portion eaten."""
    name: str
    portion_grams: float
    calories: float
    protein: float
    carbs: float | None = None
    fat: float | None = None
    confidence: Literal["high", "medium", "low"]


class MacroRange(BaseModel):
    low: float
    estimate: float
    high: float


class MealAnalysis(BaseModel):
    """Provider-neutral result of an AI meal analysis."""
    meal_name: str
    items: list[AnalyzedItem]
    assumptions: list[str]
    calories: MacroRange
    protein: MacroRange
    carbs: MacroRange | None = None
    fat: MacroRange | None = None
    confidence: Literal["high", "medium", "low"]
    explanation: str
    clarifying_question: str | None = None


class MealAnalysisResponse(MealAnalysis):
    analysis_id: int


class AnalysisLink(BaseModel):
    meal_id: int
