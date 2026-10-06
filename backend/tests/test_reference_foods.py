import logging

import pytest

from app import reference_foods
from app.reference_foods import normalize, search, singular

HEADER = "source_id,name,calories,protein,carbs,fat,fibre\n"


@pytest.fixture
def tables(tmp_path, monkeypatch):
    """Point the module at a temp dir; write tables with write(source, rows)."""
    monkeypatch.setattr(reference_foods, "DATA_DIR", tmp_path)
    reference_foods.clear_cache()

    def write(source: str, rows: list[str]) -> None:
        (tmp_path / f"{source}.csv").write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")
        reference_foods.clear_cache()

    yield write
    reference_foods.clear_cache()


def names(results):
    return [food.name for food in results]


def test_no_tables_means_no_results(tables):
    # PR 1 ships with no data: the endpoint must answer [] rather than fail.
    assert search("apple") == []


def test_the_plain_food_outranks_dishes_that_mention_it(tables):
    tables("usda", [
        '1,"Croissants, apple",254,7.4,26,14,1.5',
        '2,"Apple juice, canned or bottled, unsweetened",46,0.1,11.3,0.1,0.2',
        '3,"Apples, raw, with skin",52,0.3,11.4,0.2,2.4',
        '4,"Strudel, apple",274,3.3,40,11,2.2',
    ])
    assert names(search("apple"))[0] == "Apples, raw, with skin"
    # The plural query meets the same row.
    assert names(search("apples"))[0] == "Apples, raw, with skin"


def test_a_row_with_every_query_word_comes_first(tables):
    tables("usda", [
        '1,"Apples, raw, granny smith, with skin",58,0.4,10.6,0.2,2.8',
        '2,"Asparagus, green, raw",20,2.2,1.8,0.1,2.1',
        '3,"Croissants, apple",254,7.4,26,14,1.5',
    ])
    assert names(search("granny smith apple")) == [
        "Apples, raw, granny smith, with skin", "Croissants, apple",
    ]


def test_with_no_row_holding_every_word_it_falls_back_to_the_last_word(tables):
    tables("usda", [
        '1,"Apples, raw, granny smith, with skin",58,0.4,10.6,0.2,2.8',
        '2,"Asparagus, green, raw",20,2.2,1.8,0.1,2.1',
        '3,"Croissants, apple",254,7.4,26,14,1.5',
    ])
    # No table says "green apple". The food is the last word, so it falls
    # back to "apple" -- never to "green", which would offer asparagus.
    assert names(search("green apple")) == [
        "Apples, raw, granny smith, with skin", "Croissants, apple",
    ]


def test_a_row_with_every_word_outranks_the_fallback(tables):
    tables("usda", [
        '1,"Bread, white",265,9,49,3.2,2.7',
        '2,"Bread, brown, toasted",260,9,45,2,5',
    ])
    # The fallback ("bread") may add rows, but only below the real match.
    assert names(search("brown bread")) == ["Bread, brown, toasted", "Bread, white"]


def test_a_poor_match_on_every_word_does_not_hide_the_plain_food(tables):
    tables("usda", ['1,"Apple, raw",61,0.2,12.7,0.2,2.1'])
    tables("ciqual", [
        '13001,"Pomme cythere or golden apple (local variety), giant, green",32,0.5,6,0.2,2',
    ])
    # The only row with both words is a tropical fruit; the plain apple, found
    # through the fallback, still comes first.
    assert names(search("green apple"))[0] == "Apple, raw"


def test_a_preparation_word_marks_the_plain_food_not_a_longer_name(tables):
    tables("usda", [
        '1,"Rice, fried",174,4,25,6,1',
        '2,"Rice, white, cooked",130,2.7,28,0.3,0.4',
    ])
    assert names(search("rice"))[0] == "Rice, white, cooked"


def test_a_prefix_in_the_first_segment_loses_to_the_whole_word_later(tables):
    tables("usda", [
        '1,"Fried eggplant",218,2,15,16,3',
        '2,"Egg, whole, cooked, fried",196,13.6,0.8,15,0',
    ])
    assert names(search("fried egg"))[0] == "Egg, whole, cooked, fried"


def test_an_alias_finds_the_tables_name_alongside_the_typed_one(tables):
    tables("usda", [
        '1,"Bread, pita",275,9.1,55.7,1.2,2.2',
        '2,"Mung beans, mature seeds, raw",347,23.9,46.3,1.2,16.3',
    ])
    tables("cofid", ['50-1,"Arabic bread, white",270,9,55,1.5,2'])
    # Both the table that uses the typed name and the one that doesn't.
    assert set(names(search("arabic bread"))) == {"Arabic bread, white", "Bread, pita"}
    assert names(search("moong dal")) == ["Mung beans, mature seeds, raw"]


def test_a_whole_word_beats_a_longer_word_starting_with_it(tables):
    tables("usda", [
        '1,"Eggplant, raw",25,1,3,0.2,3',
        '2,"Egg, whole, raw, fresh",143,12.6,0.7,9.5,0',
    ])
    assert names(search("egg")) == ["Egg, whole, raw, fresh", "Eggplant, raw"]
    assert names(search("eggs"))[0] == "Egg, whole, raw, fresh"


def test_the_same_name_in_two_tables_shows_once_from_the_first_source(tables):
    tables("usda", ['1,"Bananas, raw",89,1.1,20.2,0.3,2.6'])
    tables("cofid", [
        'A1,"Bananas, raw",95,1.2,20.3,0.1,1.4',
        'A2,"Bananas, flesh only",81,1.1,20,0.1,1.1',
    ])
    results = search("banana")
    assert [(f.name, f.source) for f in results] == [
        ("Bananas, raw", "usda"),
        ("Bananas, flesh only", "cofid"),
    ]


def test_accents_and_case_do_not_matter(tables):
    tables("ciqual", ['25601,"Crème fraîche, 30% fat",292,2.4,2.9,30,0'])
    assert names(search("CREME fraiche")) == ["Crème fraîche, 30% fat"]


def test_short_tokens_still_search(tables):
    # Below the prefix length the index is skipped, not the search.
    tables("usda", ['1,"Ox, tongue, raw",224,14.9,3.7,16.1,0'])
    assert names(search("ox")) == ["Ox, tongue, raw"]


def test_stopwords_are_not_required_words(tables):
    tables("usda", ['1,"Chicken, rice, and vegetables",120,8,14,3,1'])
    assert names(search("chicken with rice")) == ["Chicken, rice, and vegetables"]


def test_blank_numbers_are_none_and_rows_without_kcal_are_skipped(tables):
    tables("usda", [
        '1,"Tea, brewed",1,0,0.3,,0',
        '2,"Tea, herbal",,0,0.2,0,0',
    ])
    [tea] = search("tea")
    assert tea.name == "Tea, brewed"
    assert tea.fat is None
    assert tea.serving_size == 100


def test_the_limit_holds(tables):
    tables("usda", [f'{i},"Rice, variety {i}",130,2.7,28,0.3,0.4' for i in range(20)])
    assert len(search("rice")) == 8
    assert len(search("rice", limit=3)) == 3


def test_a_query_of_only_punctuation_returns_nothing(tables):
    tables("usda", ['1,"Rice, white, cooked",130,2.7,28,0.3,0.4'])
    assert search("!!! ,,") == []


def test_the_log_line_never_contains_the_query(tables, caplog):
    tables("usda", ['1,"Mangos, raw",60,0.8,13.4,0.4,1.6'])
    with caplog.at_level(logging.INFO, logger="app.reference_foods"):
        search("mango secretquery")
        search("mango")
    assert "secretquery" not in caplog.text
    assert "mango" not in caplog.text.lower()
    assert "Reference search: 1 results, top usda" in caplog.text


@pytest.mark.parametrize(("word", "expected"), [
    ("apples", "apple"), ("peaches", "peach"), ("berries", "berry"),
    ("tomatoes", "tomato"), ("dates", "date"), ("oats", "oat"),
    ("hummus", "hummus"), ("swiss", "swiss"), ("tea", "tea"),
])
def test_singular(word, expected):
    assert singular(word) == expected


def test_normalize_folds_accents_and_punctuation():
    assert normalize("Jalapeño, raw (Fresh)") == "jalapeno raw fresh"


def test_endpoint_requires_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as anonymous:
        assert anonymous.get("/api/foods/reference", params={"q": "apple"}).status_code == 401


def test_endpoint_returns_per_100g_rows_with_their_source(tables, client):
    tables("cofid", ['13-001,"Apples, eating, raw, flesh and skin",51,0.6,11.6,0.5,1.8'])
    response = client.get("/api/foods/reference", params={"q": "apple"})
    assert response.status_code == 200
    assert response.json() == [{
        "name": "Apples, eating, raw, flesh and skin",
        "serving_size": 100.0,
        "calories": 51.0,
        "protein": 0.6,
        "carbs": 11.6,
        "fat": 0.5,
        "source": "cofid",
    }]


def test_a_reference_pick_saved_to_the_library_keeps_its_table(client):
    body = {"name": "Apples, raw, with skin", "serving_size": 100,
            "calories": 52, "protein": 0.3, "carbs": 11.4, "fat": 0.2, "source": "usda"}
    saved = client.post("/api/foods", json=body)
    assert saved.status_code == 201
    assert saved.json()["source"] == "usda"
    # Correcting a number makes the figures the user's own, as for OFF rows.
    edited = client.put(f"/api/foods/{saved.json()['id']}", json={**body, "calories": 60})
    assert edited.json()["source"] == "user"


def test_an_unknown_source_is_still_refused(client):
    body = {"name": "Mystery", "serving_size": 100, "calories": 1, "protein": 0,
            "source": "nutritionix"}
    assert client.post("/api/foods", json=body).status_code == 422


@pytest.mark.parametrize(("path", "expected"), [
    ("/api/foods/reference?q=green%20apple", "/api/foods/reference?q=-"),
    ("/api/foods/lookup?q=oreo&page=2", "/api/foods/lookup?q=-&page=2"),
    ("/api/meals?date=2026-10-06", "/api/meals?date=2026-10-06"),
])
def test_the_access_log_never_contains_search_text(path, expected):
    from app.main import RedactSearchText

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0,
        '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:1", "GET", path, "1.1", 200), None,
    )
    assert RedactSearchText().filter(record) is True
    assert record.getMessage() == f'127.0.0.1:1 - "GET {expected} HTTP/1.1" 200'
