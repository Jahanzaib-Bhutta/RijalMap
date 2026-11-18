-- Run by the importer after the data is loaded.
CREATE INDEX idx_entries_source_no  ON hadith_entries (source, hadith_no);
CREATE INDEX idx_entries_dataset_id ON hadith_entries (dataset_hadith_id);
CREATE INDEX idx_members_narrator   ON chain_members (narrator_id);
-- (teacher_id, student_id) is already indexed by the primary key; this one serves "who are X's teachers?"
CREATE INDEX idx_relations_student  ON narrator_relations (student_id);
-- Full-text search over the English text and the Arabic text (repository.search_text uses the same expressions).
CREATE INDEX idx_entries_text_en ON hadith_entries USING GIN (to_tsvector('english', coalesce(text_en, '')));
CREATE INDEX idx_entries_text_ar ON hadith_entries USING GIN (to_tsvector('simple', coalesce(text_ar, '')));
ANALYZE;
