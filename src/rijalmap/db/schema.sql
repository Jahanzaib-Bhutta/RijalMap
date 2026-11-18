-- RijalMap v2 schema (PostgreSQL). Matches the ER diagram in docs/Task2_Design.tex.
-- Running this file DROPS and recreates all four tables.

DROP TABLE IF EXISTS chain_members CASCADE;
DROP TABLE IF EXISTS hadith_entries CASCADE;
DROP TABLE IF EXISTS narrator_relations CASCADE;
DROP TABLE IF EXISTS narrators CASCADE;

-- One row per dictionary entry (Kaggle: all_rawis). narrator_id = scholar_indx.
CREATE TABLE narrators (
    narrator_id    INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    grade          TEXT,              -- shown for information only, never used for colours
    birth_year_ah  INTEGER,           -- negative = before Hijra (BH); NULL = unknown
    death_year_ah  INTEGER,           -- NULL = unknown
    birth_text     TEXT,              -- original text, shown as evidence
    death_text     TEXT
);

-- Teacher -> student pairs listed in EITHER narrator's entry in the dictionary.
CREATE TABLE narrator_relations (
    teacher_id INTEGER NOT NULL REFERENCES narrators(narrator_id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES narrators(narrator_id) ON DELETE CASCADE,
    PRIMARY KEY (teacher_id, student_id)
);

-- One row per row of the hadith dataset = one chain. Several rows can share (source, hadith_no).
CREATE TABLE hadith_entries (
    entry_id   INTEGER PRIMARY KEY,   -- row number in the Kaggle file (its own hadith_id is NOT unique)
    dataset_hadith_id INTEGER,        -- the Kaggle hadith_id, kept for reference only
    source     TEXT NOT NULL,         -- e.g. 'Sahih Bukhari'
    chapter_no TEXT,
    chapter    TEXT,
    hadith_no  TEXT NOT NULL,         -- text on purpose: the dataset is not always a clean integer
    text_ar    TEXT,
    text_en    TEXT
);

-- The ordered narrator list of one chain. position 1 = nearest the collector, last = the Companion.
-- narrator_id has NO foreign key on purpose: an ID missing from the dictionary must stay in the
-- chain (it becomes a grey "unidentified" link) instead of being silently dropped.
CREATE TABLE chain_members (
    entry_id    INTEGER NOT NULL REFERENCES hadith_entries(entry_id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    narrator_id INTEGER NOT NULL,
    PRIMARY KEY (entry_id, position)
);

-- Indexes live in indexes.sql and are created AFTER the bulk load (much faster than indexing while inserting).
