"""Parsing tests. The example strings are copied from the real Kaggle files."""
from rijalmap.importer.parsing import (
    clean_hadith_no, has_ce_only, parse_death_year, parse_hijri_year, parse_id_list)


def test_id_lists():
    assert parse_id_list("30418, 20005, 11062, 11213, 11042, 3") == [30418, 20005, 11062, 11213, 11042, 3]
    assert parse_id_list("1") == [1]
    assert parse_id_list("1, 2") == [1, 2]
    assert parse_id_list(float("nan")) == []
    assert parse_id_list(None) == []
    assert parse_id_list("2, 3, others") == [2, 3]


def test_birth_before_hijra_is_negative():
    assert parse_hijri_year("['53 BH', '570 CE']") == -53
    assert parse_hijri_year("['23 BH', '600 CE', '13 R']") == -23      # '13 R' is a day/month, ignored
    assert parse_hijri_year("53 BH/570 CE (9th Rabi' awwal) (Makkah)") == -53


def test_ah_years_are_positive():
    assert parse_hijri_year("['10 AH', '631 CE']") == 10


def test_death_years():
    assert parse_death_year("11 AH/632 CE (12th Rabi' awwal (Medina)[ Natural ]", None) == 11
    assert parse_death_year("23 AH/645 CE (Medinah)[ Martyred  ]", "23.0") == 23
    assert parse_death_year(None, "13.0") == 13           # falls back to the numeric column
    assert parse_death_year("(Medina)", None) is None
    assert parse_death_year(float("nan"), float("nan")) is None


def test_missing_and_ce_only():
    assert parse_hijri_year(None, float("nan"), "unknown") is None
    assert has_ce_only("['570 CE']") is True
    assert has_ce_only("['53 BH', '570 CE']") is False


def test_hadith_numbers():
    assert clean_hadith_no(" 1205 ") == "1205"
    assert clean_hadith_no("\nGrade") is None
    assert clean_hadith_no(float("nan")) is None
