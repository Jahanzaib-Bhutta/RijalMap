"""One-time import: Kaggle CSVs -> PostgreSQL. Also writes an import report.

Usage (from the project root, with the virtual environment active):
    python -m rijalmap.importer.load data/raw/all_rawis.csv data/raw/all_hadiths_clean.csv
"""
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from rijalmap.config import database_url
from rijalmap.importer.parsing import (
    clean_hadith_no,
    has_ce_only,
    parse_death_year,
    parse_hijri_year,
    parse_id_list,
)

DB_DIR = Path(__file__).resolve().parent.parent / "db"
SCHEMA_PATH = DB_DIR / "schema.sql"
INDEXES_PATH = DB_DIR / "indexes.sql"
NARRATOR_COLS = ["scholar_indx", "name", "grade", "birth_date", "birth_date_place",
                 "death_date_place", "death_date_hijri", "teachers_inds", "students_inds"]
HADITH_COLS = ["hadith_id", "source", "chapter_no", "chapter", "hadith_no", "chain_indx", "text_ar", "text_en"]


def _read(path, required):
    df = pd.read_csv(path, dtype=str)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"{path}: missing expected columns {missing}. Found: {list(df.columns)}")
    return df


def build_narrators(df: pd.DataFrame, report: dict) -> pd.DataFrame:
    df = df.copy()
    df["narrator_id"] = df["scholar_indx"].astype(int)
    dupes = int(df["narrator_id"].duplicated().sum())
    df = df.drop_duplicates("narrator_id", keep="first")
    report["narrators_duplicate_ids_dropped"] = dupes

    birth = [parse_hijri_year(b, bp) for b, bp in zip(df["birth_date"], df["birth_date_place"])]
    death = [parse_death_year(dp, dh) for dp, dh in zip(df["death_date_place"], df["death_date_hijri"])]
    report["birth_ce_only_not_converted"] = sum(
        1 for b, bp, y in zip(df["birth_date"], df["birth_date_place"], birth) if y is None and has_ce_only(b, bp))

    out = pd.DataFrame({
        "narrator_id": df["narrator_id"].values,
        "name": df["name"].fillna("").str.strip().values,
        "grade": df["grade"].values,
        "birth_year_ah": pd.array(birth, dtype="Int64"),
        "death_year_ah": pd.array(death, dtype="Int64"),
        "birth_text": df["birth_date_place"].values,
        "death_text": df["death_date_place"].values,
    })
    n = len(out)
    report["narrators_loaded"] = n
    report["narrators_with_birth_year"] = int(out["birth_year_ah"].notna().sum())
    report["narrators_with_death_year"] = int(out["death_year_ah"].notna().sum())
    report["narrators_with_both_years"] = int((out["birth_year_ah"].notna() & out["death_year_ah"].notna()).sum())
    return out


def build_relations(df: pd.DataFrame, known_ids: set, report: dict) -> pd.DataFrame:
    pairs, unknown, self_pairs = set(), 0, 0
    for sid, teachers, students in zip(df["scholar_indx"].astype(int), df["teachers_inds"], df["students_inds"]):
        candidates = [(t, sid) for t in parse_id_list(teachers)] + [(sid, s) for s in parse_id_list(students)]
        for teacher, student in candidates:
            if teacher == student:
                self_pairs += 1
            elif teacher in known_ids and student in known_ids:
                pairs.add((teacher, student))
            else:
                unknown += 1
    report["relations_loaded"] = len(pairs)
    report["relations_dropped_unknown_id"] = unknown
    report["relations_dropped_self_pair"] = self_pairs
    return pd.DataFrame(sorted(pairs), columns=["teacher_id", "student_id"])


def build_hadiths(df: pd.DataFrame, known_ids: set, report: dict):
    df = df.copy()
    # The dataset's hadith_id is NOT unique (e.g. one id is shared by Bukhari 27 and Bukhari 1835-1851, and by
    # Sahih Muslim 1-405), so it cannot be the key. entry_id is the row number in the file instead.
    df["entry_id"] = range(1, len(df) + 1)
    df["hadith_no_clean"] = df["hadith_no"].map(clean_hadith_no)
    junk = df["hadith_no_clean"].isna()
    report["hadith_rows_in_file"] = len(df)
    report["hadith_rows_skipped_junk_number"] = int(junk.sum())
    df = df[~junk].copy()
    report["hadith_rows_whose_dataset_id_is_reused"] = int(df["hadith_id"].duplicated(keep=False).sum())

    # Only an EXACT repeat (same book, same number, same narrator list) is dropped: it adds no new link, and
    # keeping it would make every narrator look "shared by two chains".
    df["chain_key"] = df["chain_indx"].map(lambda c: tuple(parse_id_list(c)))
    exact = df.duplicated(["source", "hadith_no_clean", "chain_key"], keep="first")
    report["hadith_exact_duplicates_dropped"] = int(exact.sum())
    df = df[~exact]

    entries = pd.DataFrame({
        "entry_id": df["entry_id"].values,
        "dataset_hadith_id": pd.to_numeric(df["hadith_id"], errors="coerce").astype("Int64").values,
        "source": df["source"].str.strip().values,
        "chapter_no": df["chapter_no"].values, "chapter": df["chapter"].values,
        "hadith_no": df["hadith_no_clean"].values, "text_ar": df["text_ar"].values, "text_en": df["text_en"].values,
    })
    members, no_chain, unknown_ids, total = [], 0, 0, 0
    for entry_id, chain in zip(df["entry_id"], df["chain_indx"]):
        ids = parse_id_list(chain)
        if not ids:
            no_chain += 1
        for position, narrator_id in enumerate(ids, start=1):
            members.append((entry_id, position, narrator_id))
            total += 1
            unknown_ids += narrator_id not in known_ids
    report["hadith_entries_loaded"] = len(entries)
    report["hadith_entries_without_chain"] = no_chain
    report["chain_members_loaded"] = total
    report["chain_members_id_not_in_dictionary"] = unknown_ids
    report["entries_per_source"] = entries["source"].value_counts().to_dict()
    return entries, pd.DataFrame(members, columns=["entry_id", "position", "narrator_id"])


def format_report(report: dict) -> str:
    lines = ["RijalMap import report", "=" * 24]
    for key, value in report.items():
        if isinstance(value, dict):
            lines.append(f"{key}:")
            lines += [f"    {k}: {v}" for k, v in value.items()]
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def run_import(narrators_csv, hadiths_csv, url=None, report_path=None) -> dict:
    report: dict = {}
    narrators_raw = _read(narrators_csv, NARRATOR_COLS)
    hadiths_raw = _read(hadiths_csv, HADITH_COLS)

    narrators = build_narrators(narrators_raw, report)
    known = set(narrators["narrator_id"])
    relations = build_relations(narrators_raw, known, report)
    entries, members = build_hadiths(hadiths_raw, known, report)

    engine = create_engine(url or database_url())
    with engine.begin() as conn:
        conn.exec_driver_sql(SCHEMA_PATH.read_text(encoding="utf-8"))
        for name, frame in [("narrators", narrators), ("narrator_relations", relations),
                            ("hadith_entries", entries), ("chain_members", members)]:
            frame.to_sql(name, conn, if_exists="append", index=False, method="multi", chunksize=2000)
        conn.exec_driver_sql(INDEXES_PATH.read_text(encoding="utf-8"))
        for table in ("narrators", "narrator_relations", "hadith_entries", "chain_members"):
            report[f"db_rows_{table}"] = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()

    if report_path:
        Path(report_path).write_text(format_report(report), encoding="utf-8")
    return report


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m rijalmap.importer.load <narrators.csv> <hadiths.csv>")
    result = run_import(sys.argv[1], sys.argv[2], report_path="data/import_report.txt")
    print(format_report(result))
    print("\nReport also saved to data/import_report.txt")
