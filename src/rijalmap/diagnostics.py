"""Checks to run after an import.

    python -m rijalmap.diagnostics duplicates data\\raw\\<hadith csv>   (are the dropped rows true duplicates?)
    python -m rijalmap.diagnostics stats                                (how many links of each colour, per book)
    python -m rijalmap.diagnostics contradicted                         (the most frequent red links, with the date text)
    python -m rijalmap.diagnostics alignment                            (do the chains belong to their hadith text?)
    python -m rijalmap.diagnostics numbers                              (which hadith numbers may be mislabelled?)
"""
import re
import sys
from collections import Counter
from difflib import SequenceMatcher

import pandas as pd
from sqlalchemy import create_engine, text

from rijalmap.config import database_url

# Same four rules as LinkClassifier, written in SQL so the whole corpus can be counted in one query.
# Raw string: the \m and \M word boundaries belong to PostgreSQL. Same rules as classifier.dates_contradict.
STATS_SQL = r"""
WITH pairs AS (
    SELECT e.source, a.narrator_id AS student_id, b.narrator_id AS teacher_id
    FROM chain_members a
    JOIN chain_members b ON b.entry_id = a.entry_id AND b.position = a.position + 1
    JOIN hadith_entries e ON e.entry_id = a.entry_id
)
SELECT p.source,
       CASE
         WHEN ns.narrator_id IS NULL OR nt.narrator_id IS NULL THEN 'unidentified'
         WHEN nt.death_year_ah IS NOT NULL AND ns.birth_year_ah IS NOT NULL
              AND ns.birth_year_ah > nt.death_year_ah
              AND COALESCE(nt.death_text, '') !~* '(>|after)'
              AND COALESCE(ns.birth_text, '') !~* '(<|before)'
              AND ns.birth_year_ah - nt.death_year_ah >
                  CASE WHEN COALESCE(nt.death_text, '') ~* '(~|\mor\M|<|>|before|after)'
                         OR COALESCE(ns.birth_text, '') ~* '(~|\mor\M|<|>|before|after)'
                       THEN 5 ELSE 0 END
              THEN 'contradicted'
         WHEN r.teacher_id IS NOT NULL THEN 'recorded'
         ELSE 'not_recorded'
       END AS status,
       COUNT(*) AS links
FROM pairs p
LEFT JOIN narrators ns ON ns.narrator_id = p.student_id
LEFT JOIN narrators nt ON nt.narrator_id = p.teacher_id
LEFT JOIN narrator_relations r ON r.teacher_id = p.teacher_id AND r.student_id = p.student_id
GROUP BY p.source, status
"""
STATUSES = ["recorded", "not_recorded", "contradicted", "unidentified"]


def link_status_counts(engine) -> pd.DataFrame:
    """Rows = source (plus TOTAL), columns = statuses; counts are links summed over every chain."""
    with engine.connect() as conn:
        df = pd.read_sql(text(STATS_SQL), conn)
    table = df.pivot_table(index="source", columns="status", values="links", aggfunc="sum", fill_value=0)
    table = table.reindex(columns=STATUSES, fill_value=0)
    table.loc["TOTAL"] = table.sum()
    return table


CONTRADICTED_SQL = r"""
WITH pairs AS (
    SELECT a.narrator_id AS student_id, b.narrator_id AS teacher_id
    FROM chain_members a
    JOIN chain_members b ON b.entry_id = a.entry_id AND b.position = a.position + 1
)
SELECT LEFT(nt.name, 34) AS teacher, nt.death_year_ah AS died, LEFT(ns.name, 34) AS student,
       ns.birth_year_ah AS born, ns.birth_text AS student_birth_text, nt.death_text AS teacher_death_text,
       COUNT(*) AS times
FROM pairs p
JOIN narrators ns ON ns.narrator_id = p.student_id
JOIN narrators nt ON nt.narrator_id = p.teacher_id
WHERE ns.birth_year_ah > nt.death_year_ah
  AND COALESCE(nt.death_text, '') !~* '(>|after)'
  AND COALESCE(ns.birth_text, '') !~* '(<|before)'
  AND ns.birth_year_ah - nt.death_year_ah >
      CASE WHEN COALESCE(nt.death_text, '') ~* '(~|\mor\M|<|>|before|after)'
             OR COALESCE(ns.birth_text, '') ~* '(~|\mor\M|<|>|before|after)'
           THEN 5 ELSE 0 END
GROUP BY nt.name, nt.death_year_ah, ns.name, ns.birth_year_ah, ns.birth_text, nt.death_text
ORDER BY times DESC
LIMIT 15
"""


def print_contradicted() -> None:
    """The most frequent 'red' links with the ORIGINAL date text, so a wrong date parse is easy to spot."""
    with create_engine(database_url()).connect() as conn:
        df = pd.read_sql(text(CONTRADICTED_SQL), conn)
    pd.set_option("display.width", 250, "display.max_colwidth", 60)
    print(df.to_string(index=False))


ALIGNMENT_SQL = """
SELECT e.source, e.hadith_no, e.entry_id, e.text_en, n.name AS companion
FROM hadith_entries e
JOIN LATERAL (SELECT narrator_id FROM chain_members WHERE entry_id = e.entry_id
              ORDER BY position DESC LIMIT 1) last ON TRUE
LEFT JOIN narrators n ON n.narrator_id = last.narrator_id
"""
_NARRATED = re.compile(r"\s*Narrated\s+(.+?)\s*:", re.I)
_NAME_WORDS = {"ibn": "bin", "b": "bin"}


def _name_tokens(name: str) -> list[str]:
    name = re.sub(r"[`'’‘ʿʾ´\-]", "", name.lower())
    tokens = re.sub(r"[^a-z0-9 ]+", " ", name).split()
    return [_NAME_WORDS.get(t, t) for t in tokens if t != "al"]


def same_person_name(narrated: str, dictionary_name: str, threshold: float = 0.8) -> bool:
    """Fuzzy: does 'Ibn `Abbas' (hadith text) fit 'ibn Abbas ( عبد الله بن العباس' (dictionary)? Noisy by design."""
    if not isinstance(narrated, str) or not isinstance(dictionary_name, str):   # NaN: chain ends in an unknown narrator
        return False
    wanted = _name_tokens(narrated)
    have = _name_tokens(re.split(r"[^\x00-\x7f]", dictionary_name, maxsplit=1)[0])
    if not wanted or not have:
        return False
    # "`Abdullah bin `Umar" is written "ibn Umar" in the dictionary, so also try it without the first name
    variants = [wanted] + ([wanted[1:]] if wanted[:2] == ["abdullah", "bin"] else [])
    for variant in variants:
        for take in (len(variant), len(variant) + 1):
            if SequenceMatcher(None, " ".join(variant), " ".join(have[:take])).ratio() >= threshold:
                return True
    return False


def check_alignment() -> None:
    """Does the Companion named in each hadith's own text match the Companion at the end of its chain?

    A low match rate in a range of hadith numbers means the chains are attached to the wrong hadith there.
    The name matching is fuzzy, so expect some noise everywhere; look for ranges that are far worse than the rest.
    """
    with create_engine(database_url()).connect() as conn:
        df = pd.read_sql(text(ALIGNMENT_SQL), conn)
    df["narrated"] = df["text_en"].map(lambda t: (m.group(1) if (m := _NARRATED.match(str(t or "")[:160])) else None))
    df = df[df["narrated"].notna()].copy()
    df["match"] = [same_person_name(a, b) for a, b in zip(df["narrated"], df["companion"])]
    df["number"] = df["hadith_no"].str.extract(r"(\d+)")[0].astype(float)

    print(f"Hadith whose text starts with 'Narrated X:' : {len(df)}\n")
    print("Match rate by book (Companion in the text = last narrator of the chain):")
    print((df.groupby("source")["match"].agg(["count", "mean"]).assign(mean=lambda d: (d["mean"] * 100).round(1))
           .rename(columns={"count": "checked", "mean": "match_%"})).to_string())
    for source in ("Sahih Bukhari", "Sahih Muslim"):
        part = df[df["source"] == source].copy()
        if part.empty:
            continue
        part["range"] = (part["number"] // 500 * 500).astype(int)
        by = part.groupby("range")["match"].agg(["count", "mean"])
        by["mean"] = (by["mean"] * 100).round(1)
        print(f"\n{source}, by hadith number (blocks of 500):")
        print(by.rename(columns={"count": "checked", "mean": "match_%"}).to_string())
    wrong = df[~df["match"]]
    print("\nExamples of mismatches (every Nth one):")
    step = max(1, len(wrong) // 12)
    for _, r in wrong.iloc[::step].head(12).iterrows():
        print(f"  {r['source']} {r['hadith_no']}: text says '{r['narrated'][:28]}', chain ends with "
              f"'{str(r['companion'])[:34]}'")


# Hypothesis from the Bukhari 1835 / 1900 checks: hadith whose dataset id was reused (and differs from their number)
# carry a wrong hadith_no, while the text and chain in the same row agree with each other.
SUSPECT_SQL = """
WITH reused AS (
    SELECT dataset_hadith_id FROM hadith_entries WHERE dataset_hadith_id IS NOT NULL
    GROUP BY dataset_hadith_id HAVING COUNT(*) > 1)
SELECT e.source, e.hadith_no, e.entry_id,
       (r.dataset_hadith_id IS NOT NULL AND e.hadith_no <> e.dataset_hadith_id::text) AS suspect
FROM hadith_entries e
LEFT JOIN reused r ON r.dataset_hadith_id = e.dataset_hadith_id
"""


def suspect_numbers(engine) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text(SUSPECT_SQL), conn)
    df["number"] = df["hadith_no"].str.extract(r"(\d+)")[0].astype(float)
    return df


def print_numbers() -> None:
    df = suspect_numbers(create_engine(database_url()))
    print("Rows whose hadith number may be wrong (dataset id reused and different from the number):")
    print(df.groupby("source")["suspect"].agg(["sum", "count"]).rename(columns={"sum": "suspect", "count": "all"}).to_string())
    for source in ("Sahih Bukhari", "Sahih Muslim"):
        part = df[df["source"] == source].dropna(subset=["number"]).copy()
        if part.empty:
            continue
        part["range"] = (part["number"] // 500 * 500).astype(int)
        by = part.groupby("range")["suspect"].agg(["sum", "count"])
        by["share_%"] = (by["sum"] / by["count"] * 100).round(1)
        print(f"\n{source}, by hadith number (blocks of 500):")
        print(by.rename(columns={"sum": "suspect", "count": "rows"}).to_string())
    bukhari = df[df["source"] == "Sahih Bukhari"].dropna(subset=["number"])
    bad = sorted(set(bukhari[bukhari["suspect"]]["number"].astype(int)))
    good = sorted(set(bukhari["number"].astype(int)) - set(bad))
    pick = lambda xs, k: [xs[i * (len(xs) - 1) // (k - 1)] for i in range(k)] if len(xs) >= k else xs
    print("\nCheck these on sunnah.com (https://sunnah.com/bukhari:<number>):")
    print("  suspect rows :", pick(bad, 5))
    print("  normal rows  :", pick(good, 5))


def print_stats() -> None:
    table = link_status_counts(create_engine(database_url()))
    total = table.sum(axis=1)
    print(table.to_string())
    print("\nShare of links (%):")
    print((table.div(total, axis=0) * 100).round(1).to_string())


def check_duplicates(path: str) -> None:
    df = pd.read_csv(path, dtype=str)
    dup = df[df.duplicated("hadith_id", keep=False)]
    print(f"{len(dup)} rows share a hadith_id with another row ({dup['hadith_id'].nunique()} different ids).")
    print("\nBy source:")
    print(dup.groupby("source").size().to_string())

    kinds, examples = Counter(), {}
    for hid, g in dup.groupby("hadith_id"):
        if g["source"].nunique() > 1:
            kind = "same id, DIFFERENT BOOKS"
        elif len(g[["hadith_no", "chain_indx"]].drop_duplicates()) == 1:
            kind = "same book, same number, same chain (true duplicate, safe to drop)"
        elif g["hadith_no"].nunique() == 1:
            kind = "same book, same number, DIFFERENT chain (real data would be lost)"
        else:
            kind = "same book, DIFFERENT number (real data would be lost)"
        kinds[kind] += 1
        examples.setdefault(kind, []).append(g)

    print("\nWhat the repeated ids are:")
    for kind, n in kinds.most_common():
        print(f"  {n:5d} ids: {kind}")
    for kind, groups in examples.items():
        print(f"\nExamples - {kind}")
        for g in groups[:2]:
            print(g[["hadith_id", "source", "hadith_no", "chain_indx"]].to_string(index=False))


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.stdout.reconfigure(encoding="utf-8")  # names contain Arabic; Windows consoles default to cp1252
    if args[:1] == ["stats"]:
        print_stats()
    elif args[:1] == ["contradicted"]:
        print_contradicted()
    elif args[:1] == ["alignment"]:
        check_alignment()
    elif args[:1] == ["numbers"]:
        print_numbers()
    elif len(args) == 2 and args[0] == "duplicates":
        check_duplicates(args[1])
    else:
        raise SystemExit(__doc__)
