# RijalMap

Pick a hadith book and number (or search the hadith text) and see every narrator of that hadith as a teacher -> student graph.
Each link is coloured by what the dataset records. This is a checking aid, not a ruling on narrators or hadith.

| Colour       | Meaning                                                         |
| ------------ | --------------------------------------------------------------- |
| green solid  | recorded in the dictionary, no firm date contradiction          |
| red dashed   | both dates known and firm, teacher died before student was born |
| amber dashed | not recorded in the dictionary (needs checking, not "false")    |
| grey dotted  | a narrator ID is not in the dictionary                          |

## Setup (Windows cmd, from the inner `rijalmap` folder, venv active)

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME (use a NEW database, e.g. `rijalmap_db_v2`).
3. `set PYTHONPATH=src`
4. Import (drops and recreates the tables, takes a few minutes):
   `python -m rijalmap.importer.load data\raw\all_rawis.csv data\raw\all_hadiths_clean.csv`
   (use your real CSV paths; narrators file first, hadith file second). It writes `data\import_report.txt`.

## Run

```
set PYTHONPATH=src
python -m uvicorn rijalmap.api:app --reload
```

Open http://127.0.0.1:8000

Command line version: `python -m rijalmap.cli "Sahih al-Bukhari" 1`

## Diagnostics

`python -m rijalmap.diagnostics stats | contradicted | alignment | numbers | duplicates <hadith.csv>`

## Tests

Use a throwaway database; the tests DROP and recreate tables.

```
set TEST_DATABASE_URL=postgresql+psycopg2://postgres:PASSWORD@localhost:5432/rijalmap_test
python -m pytest -q
```

## Known limits

- Only ~1.6% of narrators have a birth date, so red links are rare by nature; amber means "not recorded", not "wrong".
- Some hadith numbers in the dataset do not match printed books (flagged in the page). Text search opens the exact row.
- Chains can have missing narrators or same-name mix-ups in the dataset; red/amber links expose these.
