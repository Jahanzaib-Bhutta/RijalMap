"""Builds one directed graph (teacher -> student) from ALL chains of a hadith number."""
import networkx as nx

from rijalmap.classifier import LinkClassifier
from rijalmap.models import LinkStatus
from rijalmap.repository import Repository


class HadithNotFound(Exception):
    pass


class IsnadGraphEngine:
    def __init__(self, repo: Repository, classifier: LinkClassifier | None = None):
        self.repo = repo
        self.classifier = classifier or LinkClassifier()
        self.graph = nx.DiGraph()
        self.entries: list[dict] = []
        self.chains: dict[int, list[int]] = {}

    def build_graph(self, source: str, hadith_no: str) -> nx.DiGraph:
        """All chains stored under one book + number, merged into one graph."""
        entries = self.repo.get_entries(source, hadith_no)
        if not entries:
            raise HadithNotFound(f"No hadith '{hadith_no}' found in '{source}'.")
        return self._build(entries)

    def build_graph_for_entry(self, entry_id: int) -> nx.DiGraph:
        """The chain of ONE dataset row (used for text-search results, where the number may be unreliable)."""
        entry = self.repo.get_entry(entry_id)
        if entry is None:
            raise HadithNotFound(f"No hadith entry {entry_id}.")
        return self._build([entry])

    def _build(self, entries: list[dict]) -> nx.DiGraph:
        self.entries = entries
        self.chains = self.repo.get_chains([e["entry_id"] for e in self.entries])

        all_ids = {n for ids in self.chains.values() for n in ids}
        narrators = self.repo.get_narrators(all_ids)
        recorded = self.repo.recorded_pairs(all_ids)

        g = nx.DiGraph()
        for entry_id, ids in self.chains.items():
            for narrator_id in ids:
                if narrator_id not in g:
                    n = narrators.get(narrator_id)
                    g.add_node(narrator_id, identified=n is not None,
                               name=n.name if n else f"Unknown narrator (#{narrator_id})",
                               grade=n.grade if n else None,
                               birth_year_ah=n.birth_year_ah if n else None,
                               death_year_ah=n.death_year_ah if n else None,
                               birth_text=n.birth_text if n else None,
                               death_text=n.death_text if n else None,
                               chains=set())
                g.nodes[narrator_id]["chains"].add(entry_id)
            # stored order is nearest-collector first, so each pair is (student, teacher)
            for student_id, teacher_id in zip(ids, ids[1:]):
                if g.has_edge(teacher_id, student_id):
                    g[teacher_id][student_id]["chains"].add(entry_id)
                    continue
                status, reason = self.classifier.classify(
                    narrators.get(student_id), narrators.get(teacher_id), (teacher_id, student_id) in recorded)
                g.add_edge(teacher_id, student_id, status=status, reason=reason, chains={entry_id})
        self.graph = g
        return g

    def shared_narrators(self) -> list[dict]:
        """Narrators that appear in more than one chain (the bottlenecks that takhrij looks for)."""
        shared = [{"narrator_id": n, "name": d["name"], "chain_count": len(d["chains"])}
                  for n, d in self.graph.nodes(data=True) if len(d["chains"]) > 1]
        return sorted(shared, key=lambda x: (-x["chain_count"], x["name"]))

    def summary(self) -> dict:
        counts = {s.value: 0 for s in LinkStatus}
        for _, _, d in self.graph.edges(data=True):
            counts[d["status"].value] += 1
        return {
            "chains": len(self.entries),
            "chains_without_narrators": sum(1 for ids in self.chains.values() if not ids),
            "narrators": self.graph.number_of_nodes(),
            "links": self.graph.number_of_edges(),
            "links_by_status": counts,
            "shared_narrators": self.shared_narrators(),
            "has_cycle": not nx.is_directed_acyclic_graph(self.graph),
        }

    def export_cytoscape_json(self) -> dict:
        nodes = [{"data": {"id": str(n), **{k: v for k, v in d.items() if k != "chains"},
                           "chain_count": len(d["chains"]), "is_shared": len(d["chains"]) > 1}}
                 for n, d in self.graph.nodes(data=True)]
        edges = [{"data": {"id": f"{u}-{v}", "source": str(u), "target": str(v), "status": d["status"].value,
                           "reason": d["reason"], "chain_count": len(d["chains"])}}
                 for u, v, d in self.graph.edges(data=True)]
        keys = ("entry_id", "source", "hadith_no", "chapter", "text_en", "text_ar", "number_suspect")
        return {"hadith": {"entries": [{k: e[k] for k in keys} for e in self.entries]},
                "summary": self.summary(), "elements": {"nodes": nodes, "edges": edges}}
