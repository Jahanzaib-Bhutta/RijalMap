"""End-to-end: fixture CSVs -> importer -> PostgreSQL -> engine -> Cytoscape JSON.

Needs a throwaway database. Set TEST_DATABASE_URL, e.g.
    postgresql+psycopg2://postgres:PASSWORD@localhost:5432/rijalmap_test
The import DROPS and recreates the four tables, so never point this at your real database.
Without the variable these tests are skipped.

Fixture: narrators 1, 2, 3 are the real first three rows of the Kaggle file. Everything with an id of
9001 or more, and every hadith entry, is a made-up TEST row built to exercise one rule each.
"""
import pytest

from rijalmap.diagnostics import link_status_counts, suspect_numbers
from rijalmap.engine import HadithNotFound, IsnadGraphEngine
from tests.conftest import needs_db

pytestmark = needs_db


def engine_for(repo, no):
    e = IsnadGraphEngine(repo)
    e.build_graph("TEST Source", no)
    return e


def test_import_report(loaded):
    r, _ = loaded
    assert r["narrators_loaded"] == 11
    assert r["hadith_rows_skipped_junk_number"] == 1
    assert r["hadith_entries_loaded"] == 11                       # 13 rows - 1 junk - 1 exact repeat
    assert r["hadith_exact_duplicates_dropped"] == 1
    assert r["hadith_rows_whose_dataset_id_is_reused"] == 2       # the two rows that share id 8
    assert r["hadith_entries_without_chain"] == 1
    assert r["chain_members_id_not_in_dictionary"] == 1          # 777777
    assert r["db_rows_chain_members"] == r["chain_members_loaded"]
    # both directions of the same pair collapse into one row: (1,2) (1,3) (2,3) are the only real pairs
    assert r["relations_loaded"] >= 3


def test_years_parsed_from_text_not_from_numeric_column(loaded):
    _, repo = loaded
    prophet = repo.get_narrators([1])[1]
    assert prophet.birth_year_ah == -53 and prophet.death_year_ah == 11
    assert repo.get_narrators([3])[3].birth_year_ah == -41


def test_all_green_chain(loaded):
    e = engine_for(loaded[1], "1")
    assert [d["status"].value for _, _, d in e.graph.edges(data=True)] == ["recorded", "recorded"]


def test_red_and_amber(loaded):
    e = engine_for(loaded[1], "2")
    assert e.graph[9001][9002]["status"].value == "contradicted"
    assert e.graph[1][9001]["status"].value == "not_recorded"


def test_unidentified_stays_in_graph(loaded):
    e = engine_for(loaded[1], "3")
    assert e.graph[3][777777]["status"].value == "unidentified"
    assert e.graph.nodes[777777]["identified"] is False


def test_two_chains_merge_and_share(loaded):
    e = engine_for(loaded[1], "4")
    assert e.summary()["chains"] == 2
    shared = {s["narrator_id"] for s in e.shared_narrators()}
    assert shared == {1, 2}
    assert e.graph.number_of_edges() == 3        # 1->2 once, 2->3, 2->9001
    assert e.graph[1][2]["chains"] == {4, 5}


def test_entry_without_chain_and_unknown_hadith(loaded):
    e = engine_for(loaded[1], "5")
    assert e.summary()["chains_without_narrators"] == 1 and e.summary()["links"] == 0
    with pytest.raises(HadithNotFound):
        IsnadGraphEngine(loaded[1]).build_graph("TEST Source", "999")


def test_cytoscape_json_shape(loaded):
    out = engine_for(loaded[1], "2").export_cytoscape_json()
    assert {n["data"]["id"] for n in out["elements"]["nodes"]} == {"9002", "9001", "1"}
    statuses = {e["data"]["status"] for e in out["elements"]["edges"]}
    assert statuses == {"contradicted", "not_recorded"}


def test_sql_stats_agree_with_the_engine(loaded):
    """The SQL counts (used for whole-corpus numbers) must match what the Python classifier says link by link."""
    _, repo = loaded
    expected = {"recorded": 0, "not_recorded": 0, "contradicted": 0, "unidentified": 0}
    for no in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]:
        e = engine_for(repo, no)
        for entry_id, ids in e.chains.items():          # per chain, not merged: the SQL counts every chain
            for student, teacher in zip(ids, ids[1:]):
                expected[e.graph[teacher][student]["status"].value] += 1
    table = link_status_counts(repo.engine)
    assert table.loc["TEST Source"].to_dict() == expected
    assert sum(expected.values()) == 14


def test_hadith_sharing_a_dataset_id_are_both_kept(loaded):
    _, repo = loaded
    assert engine_for(repo, "6").summary()["chains"] == 1          # the repeat was dropped, not doubled
    assert engine_for(repo, "7").summary()["links"] == 1           # the second hadith with id 8 is present


def test_uncertain_dates_in_the_graph(loaded):
    _, repo = loaded
    assert engine_for(repo, "8").graph[9003][9004]["status"].value == "not_recorded"
    assert engine_for(repo, "9").graph[9005][9006]["status"].value == "not_recorded"
    assert engine_for(repo, "10").graph[9007][9008]["status"].value == "contradicted"


def test_reused_dataset_id_marks_numbers_as_suspect(loaded):
    """TEST hadith 6 and 7 share dataset id 8, which is neither number, so both are suspect; the rest are not."""
    _, repo = loaded
    df = suspect_numbers(repo.engine)
    flagged = df[df["suspect"]]
    assert sorted(flagged["hadith_no"]) == ["6", "7"]
    assert len(df) == 11
