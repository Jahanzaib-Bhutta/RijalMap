"""Shared test database. Needs TEST_DATABASE_URL (a throwaway database: the import DROPS its tables)."""
import os
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

from rijalmap.importer.load import run_import
from rijalmap.repository import Repository

URL = os.getenv("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
FIXTURE = Path(__file__).parent / "fixtures" / "narrators_3_real_rows.csv"


TEXTS = {1: "Narrated Umar: Deeds are judged by intentions", 4: "Narrated Umar: another report about intentions"}


@pytest.fixture(scope="session")
def loaded(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("data")
    narrators = pd.read_csv(FIXTURE, dtype=str)
    fake = pd.DataFrame([
        # TEST narrator A: died 20 AH.  TEST narrator B: born 50 AH (so A -> B is impossible).
        {"scholar_indx": "9001", "name": "TEST narrator A", "grade": "TEST", "death_date_place": "20 AH/641 CE (Medina)"},
        {"scholar_indx": "9002", "name": "TEST narrator B", "grade": "TEST", "birth_date": "['50 AH', '670 CE']",
         "birth_date_place": "50 AH/670 CE (Medina)"},
        {"scholar_indx": "9003", "name": "TEST died 103 or after", "grade": "TEST", "death_date_place": "103 AH or after ()"},
        {"scholar_indx": "9004", "name": "TEST born ~115", "grade": "TEST", "birth_date": "['~115 AH']", "birth_date_place": "~115 AH ()"},
        {"scholar_indx": "9005", "name": "TEST died ~60", "grade": "TEST", "death_date_place": "~60 AH ()"},
        {"scholar_indx": "9006", "name": "TEST born ~62", "grade": "TEST", "birth_date": "['~62 AH']", "birth_date_place": "~62 AH ()"},
        {"scholar_indx": "9007", "name": "TEST died ~60 b", "grade": "TEST", "death_date_place": "~60 AH ()"},
        {"scholar_indx": "9008", "name": "TEST born ~80", "grade": "TEST", "birth_date": "['~80 AH']", "birth_date_place": "~80 AH ()"},
    ])
    pd.concat([narrators, fake], ignore_index=True).to_csv(tmp / "n.csv", index=False)

    rows = [  # hadith_id, source, hadith_no, chain
        (1, "TEST Source", "1", "3, 2, 1"),            # all recorded
        (2, "TEST Source", "2", "9002, 9001, 1"),      # contradicted, then not recorded
        (3, "TEST Source", "3", "777777, 3"),          # unidentified
        (4, "TEST Source", "4", "3, 2, 1"),            # two chains, same hadith number ...
        (5, "TEST Source", "4", "9001, 2, 1"),         # ... sharing narrators 2 and 1
        (6, "TEST Source", "5", ""),                   # entry with no chain
        (7, "TEST Source", "\nGrade", ""),             # junk number, must be skipped
        (8, "TEST Source", "6", "3, 2"),               # two DIFFERENT hadith sharing one dataset id (as in the
        (8, "TEST Source", "7", "3, 1"),               # real file: Bukhari 27 and 1835..): both must be kept
        (9, "TEST Source", "6", "3, 2"),               # exact repeat of number 6: must be dropped
        (10, "TEST Source", "8", "9004, 9003"),        # died "103 or after": not red -> amber
        (11, "TEST Source", "9", "9006, 9005"),        # 2-year gap, approximate dates: not red -> amber
        (12, "TEST Source", "10", "9008, 9007"),       # 20-year gap, approximate dates: red
    ]
    pd.DataFrame([{"hadith_id": i, "source": s, "chapter_no": "1", "chapter": "TEST chapter", "hadith_no": no,
                   "chain_indx": c, "text_ar": "", "text_en": TEXTS.get(i, f"test {i}")} for i, s, no, c in rows]
                 ).to_csv(tmp / "h.csv", index=False)
    if not URL:
        pytest.skip("TEST_DATABASE_URL not set")
    report = run_import(tmp / "n.csv", tmp / "h.csv", url=URL)
    return report, Repository(create_engine(URL))


