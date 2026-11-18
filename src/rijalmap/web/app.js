(() => {
  "use strict";

  const STATUS = {
    recorded: { label: "Recorded", color: "#5e8f63", dash: "solid",
      note: "The dictionary lists this teacher-student pair, and no recorded date contradicts it." },
    contradicted: { label: "Contradicted", color: "#bc4f44", dash: "dashed",
      note: "The recorded dates make this link impossible. This usually means a narrator is missing from the chain, " +
            "or two narrators with the same name were confused. Check the book." },
    not_recorded: { label: "Not found in dataset", color: "#d39a2c", dash: "dashed",
      note: "Manual verification required: this connection is not in the dataset. That does not mean it is false. Check the original sources and the narrators' biographies." },
    unidentified: { label: "Unidentified", color: "#8e8e8e", dash: "dotted",
      note: "A narrator here is not in the dictionary, so nothing can be checked." },
  };
  const ORDER = ["recorded", "not_recorded", "contradicted", "unidentified"];

  const $ = (id) => document.getElementById(id);
  let cy = null;
  let numberView = null, fromEntry = false; // {source, number} of the last number lookup, so a single chain can go "back"

  /* ---------- small helpers ---------- */
  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    for (const c of children) if (c != null) node.append(c);
    return node;
  }
  async function getJson(url) {
    const res = await fetch(url);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = Array.isArray(body.detail) ? "Please check what you typed." : body.detail;
      throw new Error(detail || `Request failed (${res.status})`);
    }
    return body;
  }
  function notice(message, isError = false) {
    const box = $("notice");
    box.hidden = !message;
    box.textContent = message || "";
    box.className = "notice" + (isError ? " error" : "");
  }
  // "Sufyan bin 'Uyaynah سفيان بن عيينة" -> "Sufyan bin 'Uyaynah" (Latin part), falling back to the Arabic name
  function shortName(name) {
    const latin = (name || "").split(/[^\x00-\x7f]/)[0].replace(/[\s(]+$/, "").trim();
    const text = latin || (name || "").trim();
    return text.length > 28 ? text.slice(0, 27) + "…" : text;
  }
  // dictionary dates sometimes carry empty brackets, e.g. "98 AH ()"
  const cleanDate = (t) => (t || "").replace(/\(\s*\)/g, "").replace(/\[\s*\]/g, "").replace(/\s+/g, " ").trim();
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  function swatch(status) {
    const s = STATUS[status];
    return el("span", { class: `swatch ${s.dash}`, style: `border-top-color:${s.color}`, "aria-hidden": "true" });
  }

  /* ---------- graph ---------- */
  function initGraph() {
    cy = cytoscape({
      container: $("cy"), elements: [], wheelSensitivity: 0.3, minZoom: 0.2, maxZoom: 2.5,
      style: [
        { selector: "node", style: {
            label: "data(label)", "text-wrap": "wrap", "text-max-width": 130, "font-size": 11, color: "#2b2b2b",
            "text-valign": "center", "text-halign": "center", shape: "round-rectangle", width: "label", height: "label",
            padding: "9px", "background-color": "#ffffff", "border-width": 1.5, "border-color": "#2b2b2b" } },
        { selector: "node[?is_shared]", style: { "border-width": 3.5, "background-color": "#f1efe8" } },
        { selector: "node[!identified]", style: { "border-style": "dotted", "border-color": "#8e8e8e", color: "#6b6b66" } },
        { selector: "edge", style: {
            "curve-style": "bezier", "target-arrow-shape": "triangle", width: 2.6, "arrow-scale": 1.2,
            label: "data(label)", "font-size": 10, color: "#2b2b2b", "text-background-color": "#fbfbfa",
            "text-background-opacity": 1, "text-background-padding": "2px" } },
        ...ORDER.map((s) => ({ selector: `edge[status = "${s}"]`, style: {
            "line-color": STATUS[s].color, "target-arrow-color": STATUS[s].color, "line-style": STATUS[s].dash } })),
        { selector: ":selected", style: { "overlay-color": "#2f5d8a", "overlay-opacity": 0.14, "overlay-padding": 6 } },
      ],
    });
    cy.on("tap", "edge", (e) => showEdge(e.target));
    cy.on("tap", "node", (e) => showNode(e.target));
    cy.on("tap", (e) => { if (e.target === cy) hideDetail(); });
    window.rijalmapCy = cy; // handy for debugging in the browser console
  }

  function drawGraph(elements) {
    const nodes = elements.nodes.map((n) => ({ group: "nodes", data: { ...n.data, label: shortName(n.data.name) } }));
    const edges = elements.edges.map((e) => ({
      group: "edges", data: { ...e.data, label: e.data.chain_count > 1 ? `${e.data.chain_count} chains` : "" } }));
    cy.elements().remove();
    cy.add([...nodes, ...edges]);
    cy.layout({ name: "breadthfirst", directed: true, roots: cy.nodes().roots(), spacingFactor: 1.2,
                padding: 30, animate: false }).run();
    cy.fit(undefined, 30);
    if (cy.zoom() > 1.3) { cy.zoom(1.3); cy.center(); }
  }

  /* ---------- detail panel ---------- */
  function hideDetail() { $("detail").hidden = true; cy.elements().unselect(); }
  function openDetail(...children) {
    const box = $("detail");
    box.replaceChildren(el("button", { class: "close", "aria-label": "Close", onclick: hideDetail, text: "×" }), ...children.filter(Boolean));
    box.hidden = false;
  }
  function showEdge(edge) {
    const d = edge.data(); const s = STATUS[d.status];
    const teacher = cy.getElementById(d.source).data("name");
    const student = cy.getElementById(d.target).data("name");
    openDetail(
      el("h3", { text: "Link" }),
      el("div", { class: "status-line" }, swatch(d.status), el("span", { text: s.label })),
      el("dl", {},
        el("dt", { text: "Teacher" }), el("dd", { text: shortName(teacher) }),
        el("dt", { text: "Student" }), el("dd", { text: shortName(student) }),
        el("dt", { text: "In chains" }), el("dd", { text: String(d.chain_count) })),
      el("p", { text: d.reason }),
      d.status === "recorded" ? null : el("p", { class: "fine", text: s.note }));
  }
  async function showNode(node) {
    const d = node.data();
    if (!d.identified) {
      return openDetail(el("h3", { text: d.name }),
        el("p", { text: "This narrator ID is not in the dictionary, so there are no dates or teachers to show." }));
    }
    openDetail(el("h3", { text: shortName(d.name) }), el("p", { class: "fine", text: "Loading…" }));
    try {
      const n = await getJson(`/api/narrator/${encodeURIComponent(d.id)}`);
      const list = (rel) => el("ul", { class: "names" },
        ...rel.items.map((x) => el("li", { text: shortName(x.name) })),
        rel.total > rel.items.length ? el("li", { class: "fine", text: `… and ${rel.total - rel.items.length} more` }) : null);
      openDetail(
        el("h3", { text: shortName(n.name) }),
        el("dl", {},
          el("dt", { text: "Born" }), el("dd", { text: cleanDate(n.birth_text) || "not recorded" }),
          el("dt", { text: "Died" }), el("dd", { text: cleanDate(n.death_text) || "not recorded" }),
          el("dt", { text: "Dictionary label" }), el("dd", { text: n.grade || "none" }),
          el("dt", { text: "In chains" }), el("dd", { text: d.chain_count > 1 ? `${d.chain_count} (shared)` : "1" })),
        el("p", { class: "fine", text: "The dictionary label is shown for information only. It never changes a colour." }),
        el("h2", { text: `Recorded teachers (${n.relations.teachers.total})` }), list(n.relations.teachers),
        el("h2", { text: `Recorded students (${n.relations.students.total})` }), list(n.relations.students));
    } catch (err) { openDetail(el("h3", { text: shortName(d.name) }), el("p", { text: err.message })); }
  }

  /* ---------- sidebar ---------- */
  function renderLegend(counts) {
    $("legend").replaceChildren(...ORDER.map((s) => el("li", {}, swatch(s), el("span", { text: STATUS[s].label }),
      el("span", { class: "count", text: counts ? String(counts[s]) : "" }))));
  }
  function renderSummary(data) {
    const { entries } = data.hadith; const s = data.summary; const first = entries[0];
    const box = $("summary-box"); box.hidden = false; box.replaceChildren();
    box.append(el("h2", { text: `${first.source} no. ${first.hadith_no}` }));
    box.append(el("p", { class: "meta",
      text: `${plural(s.chains, "chain")} · ${plural(s.narrators, "narrator")} · ${plural(s.links, "link")}` }));

    if (entries.some((e) => e.number_suspect)) box.append(el("p", { class: "warn",
      text: "The dataset's number for this hadith may not match your book. Check that the text below is the hadith you " +
            "wanted, or search the text instead." }));
    if (entries.length > 1) box.append(el("p", { class: "warn",
      text: `${entries.length} different entries share this number and are drawn together. Use the list below to see one at a time.` }));
    const lc = s.links_by_status;
    if (lc.not_recorded || lc.contradicted) box.append(el("p", { class: "warn",
      text: "Manual verification required. " + (lc.not_recorded ? `${plural(lc.not_recorded, "link")} not found in the dataset. ` : "") +
            (lc.contradicted ? `${plural(lc.contradicted, "link")} with contradicting dates. ` : "") +
            "Check the original hadith sources and narrator biographies. RijalMap does not grade hadith." }));
    if (s.chains_without_narrators) box.append(el("p", { class: "warn",
      text: `${plural(s.chains_without_narrators, "chain")} in the dataset ${s.chains_without_narrators === 1 ? "has" : "have"} no narrator list.` }));
    if (s.has_cycle) box.append(el("p", { class: "warn",
      text: "This graph contains a loop. That usually means one narrator appears twice in the chain data." }));

    if (s.shared_narrators.length) {
      box.append(el("h2", { text: "Narrators in more than one chain" }));
      box.append(el("div", { class: "chips" }, ...s.shared_narrators.slice(0, 10).map((n) =>
        el("button", { class: "chip", title: "Show on the graph", onclick: () => {
          const node = cy.getElementById(String(n.narrator_id)); cy.elements().unselect(); node.select();
          cy.animate({ center: { eles: node }, duration: 250 }); },
          text: `${shortName(n.name)} ×${n.chain_count}` }))));
    }
    box.append(el("hr", { class: "rule" }));

    if (entries.length === 1) {
      box.append(entryText(entries[0], true));
      if (numberView && fromEntry) box.append(el("button", { class: "link", text: "← back to all chains for this number",
        onclick: () => loadNumber(numberView.source, numberView.number) }));
    } else {
      box.append(el("h2", { text: "Entries under this number" }));
      box.append(el("ul", { class: "plain" }, ...entries.map((e) => el("li", { class: "result" },
        el("div", { class: "head", text: `Entry ${e.entry_id}${e.number_suspect ? " (number may be wrong)" : ""}` }),
        el("p", { text: (e.text_en || "").slice(0, 160) }),
        el("button", { class: "link", text: "Show only this chain", onclick: () => loadEntry(e.entry_id) })))));
    }
  }
  function entryText(e, open) {
    return el("details", open ? { open: "" } : {},
      el("summary", { text: "Hadith text" }),
      e.chapter ? el("p", { class: "fine", text: e.chapter }) : null,
      el("p", { class: "text-en", text: e.text_en || "(no English text in the dataset)" }),
      e.text_ar ? el("p", { class: "text-ar", lang: "ar", text: e.text_ar }) : null);
  }
  function counts(data) { return data.summary.links_by_status; }

  /* ---------- loading ---------- */
  function show(data) {
    $("empty").hidden = true; hideDetail(); notice("");
    drawGraph(data.elements); renderSummary(data); renderLegend(counts(data));
  }
  async function loadNumber(source, number) {
    try {
      numberView = { source, number }; fromEntry = false;
      show(await getJson(`/api/graph/${encodeURIComponent(source)}/${encodeURIComponent(number)}`));
    } catch (err) { notice(err.message, true); }
  }
  async function loadEntry(entryId) {
    fromEntry = true;
    try { show(await getJson(`/api/graph/entry/${encodeURIComponent(entryId)}`)); }
    catch (err) { notice(err.message, true); }
  }
  async function runSearch(q) {
    const box = $("results-box"), list = $("results");
    try {
      const data = await getJson(`/api/search?q=${encodeURIComponent(q)}`);
      box.hidden = false; list.replaceChildren();
      if (!data.results.length) { list.append(el("li", { class: "fine", text: "No hadith text matches that." })); return; }
      for (const r of data.results) list.append(el("li", { class: "result" },
        el("div", { class: "head", text: `${r.source} no. ${r.hadith_no}` }),
        el("p", { text: r.snippet || "" }),
        el("button", { class: "link", text: "Show graph", onclick: () => { numberView = null; loadEntry(r.entry_id); } })));
      notice("");
    } catch (err) { notice(err.message, true); }
  }

  /* ---------- start ---------- */
  async function start() {
    initGraph(); renderLegend(null);
    try {
      const { sources } = await getJson("/api/sources");
      $("source").replaceChildren(...sources.map((s) => el("option", { value: s, text: s })));
      const bukhari = sources.find((s) => /bukhari/i.test(s)); if (bukhari) $("source").value = bukhari;
    } catch (err) { notice(`Could not load the book list: ${err.message}`, true); }
    $("number-form").addEventListener("submit", (e) => {
      e.preventDefault(); loadNumber($("source").value, $("number").value.trim()); });
    $("search-form").addEventListener("submit", (e) => { e.preventDefault(); runSearch($("q").value.trim()); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideDetail(); });
  }
  start();
})();
