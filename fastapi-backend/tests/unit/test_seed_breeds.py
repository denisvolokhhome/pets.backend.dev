"""db/seed_breeds.py: adds only breeds missing from the database, so new CSV rows reach seeded DBs."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("seed_breeds", ROOT / "db" / "seed_breeds.py")
seed_breeds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed_breeds)


def test_only_breeds_missing_from_the_database_are_added():
    rows = [{"name": "Beagle", "kind": "dog"}, {"name": "Sokoke", "kind": "cat"}]
    assert seed_breeds.breeds_to_add(rows, existing_names={"Beagle"}) == [("Sokoke", "cat")]


def test_existing_names_match_case_and_whitespace_insensitively():
    rows = [{"name": "  beagle ", "kind": "DOG"}]
    assert seed_breeds.breeds_to_add(rows, existing_names={"Beagle"}) == []


def test_invalid_rows_and_duplicates_within_the_csv_are_skipped():
    rows = [
        {"name": "", "kind": "dog"},
        {"name": "Axolotl", "kind": "fish"},
        {"name": "Toybob", "kind": "cat"},
        {"name": "toybob", "kind": "cat"},
    ]
    assert seed_breeds.breeds_to_add(rows, existing_names=set()) == [("Toybob", "cat")]


def test_breeds_csv_is_valid_and_has_no_duplicate_names():
    rows = seed_breeds.read_rows(ROOT / "db" / "breeds.csv")
    names = [r["name"].strip().casefold() for r in rows]
    assert all(r["kind"].strip().lower() in ("dog", "cat") for r in rows)
    assert len(names) == len(set(names))


def test_breeds_csv_includes_recognized_breeds_added_later():
    names = {r["name"].strip() for r in seed_breeds.read_rows(ROOT / "db" / "breeds.csv")}
    for expected in ("Belgian Laekenois", "American English Coonhound", "American Bully", "Toybob",
                     "Highlander", "Sokoke", "European Burmese"):
        assert expected in names
