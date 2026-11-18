"""Small data classes shared by the repository, classifier and engine."""
from dataclasses import dataclass
from enum import Enum


class LinkStatus(str, Enum):
    RECORDED = "recorded"            # green, solid
    CONTRADICTED = "contradicted"    # red, dashed
    NOT_RECORDED = "not_recorded"    # amber, dashed
    UNIDENTIFIED = "unidentified"    # grey, dotted


@dataclass(frozen=True)
class Narrator:
    narrator_id: int
    name: str
    grade: str | None = None
    birth_year_ah: int | None = None
    death_year_ah: int | None = None
    birth_text: str | None = None
    death_text: str | None = None

    def is_dated(self) -> bool:
        return self.birth_year_ah is not None and self.death_year_ah is not None
