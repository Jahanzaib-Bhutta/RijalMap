"""Console view of a hadith graph: python -m rijalmap.cli "Sahih Bukhari" 1"""
import sys

from rijalmap.engine import HadithNotFound, IsnadGraphEngine
from rijalmap.repository import Repository

MARK = {"recorded": "GREEN  ", "contradicted": "RED    ", "not_recorded": "AMBER  ", "unidentified": "GREY   "}


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # narrator names contain Arabic; Windows consoles default to cp1252
    if len(argv) != 2:
        print('usage: python -m rijalmap.cli "<source>" <hadith_no>')
        return 2
    engine = IsnadGraphEngine(Repository())
    try:
        engine.build_graph(argv[0], argv[1])
    except HadithNotFound as exc:
        print(exc)
        return 1
    s = engine.summary()
    print(f"{argv[0]} no. {argv[1]}: {s['chains']} chain(s), {s['narrators']} narrators, {s['links']} links")
    texts = {e["entry_id"]: " ".join((e["text_en"] or "").split()) for e in engine.entries}
    for entry_id, ids in engine.chains.items():
        print(f"\nChain (entry {entry_id}), nearest the collector -> Companion:")
        print(f"  Dataset text: {texts.get(entry_id, '')[:110] or '(none)'}")
        for student_id, teacher_id in zip(ids, ids[1:]):
            d = engine.graph[teacher_id][student_id]
            names = engine.graph.nodes
            print(f"  {MARK[d['status'].value]} {names[teacher_id]['name'][:38]:38} -> {names[student_id]['name'][:38]}")
    print("\nLinks by status:", s["links_by_status"])
    print("Shared narrators:", [(x["name"][:30], x["chain_count"]) for x in s["shared_narrators"]] or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
