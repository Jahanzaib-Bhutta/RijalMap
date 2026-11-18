"""Name matching used by the alignment check. Pairs are typical sunnah.com text vs dictionary names."""
import pytest

from rijalmap.diagnostics import same_person_name


@pytest.mark.parametrize("narrated, dictionary", [
    ("Ibn `Abbas", "ibn Abbas ( عبد الله بن العباس بن عبد المطلب ( رضي الله عنه"),
    ("Abu Huraira", "Abu Hurairah ( أبو هريرة - عبد الرحمن"),
    ("`Aisha", "'Aisha bint Abi Bakr عائشة"),
    ("Anas", "Anas bin Malik ( أنس بن مالك"),
    ("Sa`d bin Abi Waqqas", "Sa'd ibn Abi Waqqas ( سعد بن أبي وقاص"),
    ("`Abdullah bin `Umar", "ibn Umar ( عبد الله بن عمر بن الخطاب"),
    ("Jabir bin `Abdullah", "Jabir ibn 'Abdullah ( جابر"),
    ("Abu Musa", "Abu Musa al-Asha'ari ( أبو موسى"),
])
def test_same_person(narrated, dictionary):
    assert same_person_name(narrated, dictionary)


@pytest.mark.parametrize("narrated, dictionary", [
    ("Ibn `Abbas", "ibn Umar ( عبد الله بن عمر بن الخطاب"),
    ("Anas", "Abu Hurairah ( أبو هريرة"),
    ("`Aisha", "Hafsa bint Umar حفصة"),
    ("Ibn `Umar", None),
    ("Ibn `Umar", float("nan")),      # chain ends in a narrator missing from the dictionary
])
def test_different_person(narrated, dictionary):
    assert not same_person_name(narrated, dictionary)
