"""The only module that talks to PostgreSQL."""
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Engine

from rijalmap.config import database_url
from rijalmap.models import Narrator

# number_suspect: the dataset's own hadith_id is shared with other rows AND differs from the hadith number.
# In the files checked so far (Bukhari 1835, 1900) such rows carry a hadith number that does not match
# sunnah.com, although the text and chain in the row agree with each other.
ENTRY_SELECT = """
SELECT e.entry_id, e.source, e.hadith_no, e.chapter, e.text_ar, e.text_en,
       (e.dataset_hadith_id IS NOT NULL
        AND e.hadith_no <> e.dataset_hadith_id::text
        AND EXISTS (SELECT 1 FROM hadith_entries x
                    WHERE x.dataset_hadith_id = e.dataset_hadith_id AND x.entry_id <> e.entry_id)) AS number_suspect
FROM hadith_entries e
"""

SEARCH_SQL = """
SELECT e.entry_id, e.source, e.hadith_no, LEFT(e.text_en, 240) AS snippet,
       ts_rank(to_tsvector('english', coalesce(e.text_en, '')), plainto_tsquery('english', :q)) AS rank
FROM hadith_entries e
WHERE (to_tsvector('english', coalesce(e.text_en, '')) @@ plainto_tsquery('english', :q)
       OR to_tsvector('simple', coalesce(e.text_ar, '')) @@ plainto_tsquery('simple', :q))
  AND (CAST(:source AS TEXT) IS NULL OR e.source = :source)
ORDER BY rank DESC, e.entry_id
LIMIT :limit
"""


class Repository:
    def __init__(self, engine: Engine | None = None):
        self.engine = engine or create_engine(database_url())

    def list_sources(self) -> list[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT DISTINCT source FROM hadith_entries ORDER BY source"))
            return [r[0] for r in rows]

    def get_entries(self, source: str, hadith_no: str) -> list[dict]:
        sql = text(ENTRY_SELECT + " WHERE e.source = :source AND e.hadith_no = :no ORDER BY e.entry_id")
        with self.engine.connect() as conn:
            return [dict(r) for r in conn.execute(sql, {"source": source, "no": str(hadith_no).strip()}).mappings()]

    def get_entry(self, entry_id: int) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(text(ENTRY_SELECT + " WHERE e.entry_id = :id"), {"id": entry_id}).mappings().first()
            return dict(row) if row else None

    def search_text(self, query: str, source: str | None = None, limit: int = 15) -> list[dict]:
        """Full-text search over the English and Arabic hadith text. Finds a hadith whatever its number says."""
        with self.engine.connect() as conn:
            rows = conn.execute(text(SEARCH_SQL), {"q": query, "source": source, "limit": limit}).mappings()
            return [{k: v for k, v in r.items() if k != "rank"} for r in rows]

    def get_chains(self, entry_ids: list[int]) -> dict[int, list[int]]:
        """entry_id -> narrator ids in stored order (nearest the collector first, Companion last)."""
        chains: dict[int, list[int]] = {e: [] for e in entry_ids}
        if not entry_ids:
            return chains
        sql = text("""SELECT entry_id, narrator_id FROM chain_members
                      WHERE entry_id IN :ids ORDER BY entry_id, position""").bindparams(
            bindparam("ids", expanding=True))
        with self.engine.connect() as conn:
            for entry_id, narrator_id in conn.execute(sql, {"ids": list(entry_ids)}):
                chains[entry_id].append(narrator_id)
        return chains

    def get_narrators(self, ids) -> dict[int, Narrator]:
        ids = list(set(ids))
        if not ids:
            return {}
        sql = text("""SELECT narrator_id, name, grade, birth_year_ah, death_year_ah, birth_text, death_text
                      FROM narrators WHERE narrator_id IN :ids""").bindparams(bindparam("ids", expanding=True))
        with self.engine.connect() as conn:
            return {r["narrator_id"]: Narrator(**r) for r in conn.execute(sql, {"ids": ids}).mappings()}

    def recorded_pairs(self, ids) -> set[tuple[int, int]]:
        """All (teacher_id, student_id) pairs recorded in the dictionary among the given narrator ids."""
        ids = list(set(ids))
        if not ids:
            return set()
        sql = text("""SELECT teacher_id, student_id FROM narrator_relations
                      WHERE teacher_id IN :ids AND student_id IN :ids""").bindparams(
            bindparam("ids", expanding=True))
        with self.engine.connect() as conn:
            return {(t, s) for t, s in conn.execute(sql, {"ids": ids})}

    def is_recorded(self, teacher_id: int, student_id: int) -> bool:
        return (teacher_id, student_id) in self.recorded_pairs([teacher_id, student_id])

    def get_relations(self, narrator_id: int, limit: int = 25) -> dict:
        """A narrator's recorded teachers and students (names only), with the total count of each."""
        out = {}
        with self.engine.connect() as conn:
            for key, other, own in (("teachers", "teacher_id", "student_id"), ("students", "student_id", "teacher_id")):
                total = conn.execute(text(f"SELECT COUNT(*) FROM narrator_relations WHERE {own} = :id"),
                                     {"id": narrator_id}).scalar()
                rows = conn.execute(text(f"""SELECT n.narrator_id, n.name FROM narrator_relations r
                                             JOIN narrators n ON n.narrator_id = r.{other}
                                             WHERE r.{own} = :id ORDER BY n.name LIMIT :lim"""),
                                    {"id": narrator_id, "lim": limit}).mappings()
                out[key] = {"total": total, "items": [dict(r) for r in rows]}
        return out
