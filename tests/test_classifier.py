from rijalmap.classifier import LinkClassifier
from rijalmap.models import LinkStatus, Narrator

C = LinkClassifier()
teacher_died_20 = Narrator(1, "Teacher", death_year_ah=20)
student_born_50 = Narrator(2, "Student", birth_year_ah=50)
student_born_10 = Narrator(3, "Student early", birth_year_ah=10)
undated = Narrator(4, "No dates")


def test_unidentified_when_either_side_missing():
    assert C.classify(None, teacher_died_20, True)[0] == LinkStatus.UNIDENTIFIED
    assert C.classify(student_born_50, None, True)[0] == LinkStatus.UNIDENTIFIED
    assert C.classify(None, None, False)[0] == LinkStatus.UNIDENTIFIED


def test_red_only_when_both_dates_known_and_contradict():
    status, reason = C.classify(student_born_50, teacher_died_20, False)
    assert status == LinkStatus.CONTRADICTED and "30 years" in reason


def test_contradiction_beats_a_dictionary_record():
    assert C.classify(student_born_50, teacher_died_20, True)[0] == LinkStatus.CONTRADICTED


def test_no_contradiction_when_dates_overlap_or_unknown():
    assert C.classify(student_born_10, teacher_died_20, True)[0] == LinkStatus.RECORDED
    assert C.classify(undated, teacher_died_20, False)[0] == LinkStatus.NOT_RECORDED
    assert C.classify(student_born_50, undated, True)[0] == LinkStatus.RECORDED


def test_missing_record_is_amber_not_red():
    assert C.classify(student_born_10, teacher_died_20, False)[0] == LinkStatus.NOT_RECORDED


# --- uncertain dates: the strings below are copied from the real dictionary ---
def person(birth=None, death=None, birth_text=None, death_text=None):
    return Narrator(1, "x", birth_year_ah=birth, death_year_ah=death, birth_text=birth_text, death_text=death_text)


def test_firm_dates_still_give_red():
    teacher = person(death=124, death_text="124 AH/741 CE (Medinah)[ Natural ]")      # al-Zuhri
    student = person(birth=142, birth_text="142 AH ()")                                # Yahya ibn Yahya
    assert C.dates_contradict(student, teacher) is True


def test_death_or_after_is_never_red():
    teacher = person(death=103, death_text="103 AH or after ()[ Natural ]")           # may have lived longer
    student = person(birth=115, birth_text="~115 AH/733 CE ()")
    assert C.dates_contradict(student, teacher) is False


def test_small_gap_with_approximate_date_is_not_red():
    teacher = person(death=59, death_text="59 AH/681 CE (Medinah)[ Natural ]")        # Abu Hurairah
    student = person(birth=60, birth_text="~60 AH (Basra)")                            # Qatada: 1 year, approx
    assert C.dates_contradict(student, teacher) is False


def test_large_gap_with_approximate_date_is_red():
    teacher = person(death=74, death_text="74 AH (Medinah)")                           # Salama ibn al-Akwa
    student = person(birth=82, birth_text="~82 AH ()")                                 # Shu'bah: 8 years
    assert C.dates_contradict(student, teacher) is True


def test_birth_upper_bound_is_never_red():
    assert C.dates_contradict(person(birth=70, birth_text="<70 AH"), person(death=60, death_text="60 AH")) is False


def test_red_reason_quotes_the_dictionary_text():
    status, reason = C.classify(person(birth=142, birth_text="142 AH ()"),
                                person(death=124, death_text="124 AH"), False)
    assert status == LinkStatus.CONTRADICTED and "142 AH ()" in reason and "124 AH" in reason
