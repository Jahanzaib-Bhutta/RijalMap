"""Decides the colour of one teacher -> student link. Pure logic, no database."""
import re

from rijalmap.models import LinkStatus, Narrator

# The dictionary writes uncertain dates in the text, e.g. "~60 AH", "94 AH or 104 AH", "103 AH or after", ">70 AH".
# The year column keeps only the first number, so the text must be read before calling a link impossible.
APPROX_TOLERANCE_YEARS = 5
_LOWER_BOUND = re.compile(r">|after", re.I)             # "103 AH or after": the real date is LATER
_UPPER_BOUND = re.compile(r"<|before", re.I)            # "<70 AH": the real date is EARLIER
_APPROX = re.compile(r"~|\bor\b|<|>|before|after", re.I)
# NOTE: the same three patterns are written in SQL in diagnostics.STATS_SQL. Keep them identical.


class LinkClassifier:
    """Four checks in a fixed order (see the flowchart in the Task 2 report).

    The colours describe what the DATA records. They never say whether a hadith or a narrator is reliable.
    """

    def dates_contradict(self, student: Narrator, teacher: Narrator) -> bool:
        """True only when both years are known, the teacher died before the student was born, and the
        dates are firm enough to say so:
          - teacher death "or after"/">": he may have lived longer, so no contradiction;
          - student birth "<"/"before": he may have been born earlier, so no contradiction;
          - any other approximate date ("~", "or"): the gap must exceed a tolerance of a few years.
        """
        if teacher.death_year_ah is None or student.birth_year_ah is None:
            return False
        gap = student.birth_year_ah - teacher.death_year_ah
        if gap <= 0:
            return False
        death_text, birth_text = teacher.death_text or "", student.birth_text or ""
        if _LOWER_BOUND.search(death_text) or _UPPER_BOUND.search(birth_text):
            return False
        if _APPROX.search(death_text) or _APPROX.search(birth_text):
            return gap > APPROX_TOLERANCE_YEARS
        return True

    def classify(self, student: Narrator | None, teacher: Narrator | None,
                 recorded: bool) -> tuple[LinkStatus, str]:
        """student/teacher are None when the ID is not in the dictionary. `recorded` = pair is in narrator_relations."""
        if student is None or teacher is None:
            missing = "student" if student is None else "teacher"
            if student is None and teacher is None:
                missing = "student and teacher"
            return (LinkStatus.UNIDENTIFIED,
                    f"The {missing} could not be matched to the dictionary, so this link cannot be checked.")

        if self.dates_contradict(student, teacher):
            gap = student.birth_year_ah - teacher.death_year_ah
            return (LinkStatus.CONTRADICTED,
                    f"{teacher.name} died in {teacher.death_year_ah} AH, but {student.name} was born in "
                    f"{student.birth_year_ah} AH ({gap} years later). Dictionary text: teacher died "
                    f"'{teacher.death_text or '?'}'; student born '{student.birth_text or '?'}'.")

        if recorded:
            return (LinkStatus.RECORDED,
                    "The dictionary lists this teacher-student pair (in either narrator's entry), "
                    "and no recorded date contradicts it.")

        return (LinkStatus.NOT_RECORDED,
                "The dictionary does not list this pair and no recorded date contradicts it. "
                "This does not mean the link is false; it needs checking in a rijal source.")
