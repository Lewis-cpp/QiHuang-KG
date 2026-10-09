Title: Open Data · 开放数据

URL Source: https://bencaodian.org/en/about/data/

Markdown Content:
Bencao Dian's central position is "a citable bilingual ontology," not "a content site competing for traffic." In the era of large language models, closed reference resources are eventually absorbed silently into training corpora; only data that is openly published, independently verifiable, and reusable by others can become the basis for long-term trust.

We therefore release the complete seed dataset as structured JSON, with schema documentation and SHA-256 checksums, under the CC BY-SA 4.0 license. Anyone may download, redistribute, and rework the data — provided they attribute "Bencaodian Editorial / 本草典编辑部" and release derivative works under the same license.

## Coverage

Bencao Dian is a growing project. Here is the current dataset coverage relative to the traditional canon:

*   **335** of ~530 herbs in the standard materia medica (63%)
*   **208** of 361 standard acupuncture points (58%)
*   **112** of ~300 classical formulas (37%)
*   **80+** diagnostic patterns
*   **50** common conditions
*   **56** herb-drug interactions

Growing steadily — contributions welcome.

## Downloads

Version: `v1` ·

Generated: `2026-04-17T05:37:00.984Z`

[`herbs.json`1.92 MB · 365 entries Herb entries — nature, flavor, channel entry, actions, indications, processing, dosage, contraindications, classical citations, Wikidata cross-references. sha256: 5773a762c92b2ae3ce9bfb7d60d529e636bf86fad0ae165ad825be479f446276](https://bencaodian.org/data/v1/herbs.json)[`formulas.json`393.2 KB · 112 entries Formula entries — sovereign-minister-assistant-courier composition, modifications, treatment principle, source text. sha256: a31a02c6325e744f9722993bec3a942624442e7d1b3830494b05672d5a44b598](https://bencaodian.org/data/v1/formulas.json)[`patterns.json`245.2 KB · 84 entries Pattern entries — cardinal and secondary symptoms, tongue and pulse, etiology, pathomechanism, treatment principle. sha256: 15ec9bf532cc3f67094c2616ed0da503e1b1967c134e307f0265c1fe58ef643f](https://bencaodian.org/data/v1/patterns.json)[`meridians.json`26.9 KB · 14 entries Meridian entries — the twelve regular channels plus the Conception and Governing Vessels. sha256: 0ce0a1845222acbbc83cabda754d67cf3e8d31162cfb5c2aa55908bf7fedbb03](https://bencaodian.org/data/v1/meridians.json)[`acupoints.json`448.3 KB · 208 entries Acupoint entries — location, needling depth and method, special-category memberships, actions, indications. sha256: d78f34e8f1b70e31325aed26b77bc1a6a4a908a0e5b2f4fc60d371866da9016c](https://bencaodian.org/data/v1/acupoints.json)[`classical_texts.json`212.7 KB · 38 entries Classical text entries — author, dynasty, tradition, annotated source passages. sha256: 2cb13eb854092d6861c69794afdfaeb39a7b1ea1afc10ee6dabe6307be500682](https://bencaodian.org/data/v1/classical_texts.json)[`concepts.json`212.9 KB · 15 entries Concept essays — yin-yang, five phases, zang-fu, eight principles, four natures and five flavors, sovereign-minister-assistant-courier hierarchy, and other foundational theory. sha256: 859760906b30e934b2e9493e722499f8c8071bfbb3641e44cd01537f35fca008](https://bencaodian.org/data/v1/concepts.json)[`relationships.json`165.6 KB · 1477 entries The relationship graph — herb_in_formula, formula_treats_pattern, pattern_differential_with, and ten other edge types. sha256: 62169b7458aaab4ad422910af8cc44602a4615652d7083a79b520af6e05c79f9](https://bencaodian.org/data/v1/relationships.json)[`case_records.json`73.5 KB · 28 entries Classical 医案 case records — famous historical cases from Ye Tianshi, Wu Jutong, Shanghan Lun, and other masters. sha256: 36db4ad97f0423c6b2eb1bf249dd18b0a95e79367693a9b79c182161c478c960](https://bencaodian.org/data/v1/case_records.json)[`tongue_states.json`34.4 KB · 25 entries Tongue atlas — tongue body, shape, coating, clinical significance, with hand-authored SVG paths. sha256: d951aabb91def71afd149d150b4afc0de2115818e4eda34dfcc3307d0d2f82a8](https://bencaodian.org/data/v1/tongue_states.json)[`pulses.json`44.6 KB · 28 entries 28 classical pulses — classical descriptions, modern descriptions, and clinical significance. sha256: d88cc419b334320b9cce7319fed8c9e58b50cbeee63ff8f254a886302e97f105](https://bencaodian.org/data/v1/pulses.json)[`symptom_synonyms.json`47.3 KB · 155 entries Symptom synonym ontology — 155 canonical symptoms each with ZH + EN aliases, powering symptom search and pattern differentiation. sha256: d21f7d4a65b4e35f068d7fdc8cbb8906fa552786ff14f256cdb182aa1db531af](https://bencaodian.org/data/v1/symptom_synonyms.json)[`interactions.json`58.2 KB · 56 entries Herb–drug interaction dataset — mechanism, clinical recommendation, and source citation. sha256: c68151aa0218591a78471ec2c8b11e2d2c7707f7a401e1d8b79e528d74285353](https://bencaodian.org/data/v1/interactions.json)[`conditions.json`96.1 KB · 50 entries Modern-condition index — cross-framework lookup from biomedical diagnosis to TCM pattern. sha256: cd69812df45815e51294ab40a32cb05b4d076f08b73acc0d57b3b744a2543d4a](https://bencaodian.org/data/v1/conditions.json)

## Data shape

Each entity class is stored as a JSON array. Every record carries at least `key` (a stable identifier), `slug` (the URL segment), `name_zh`, and `name_pinyin`. Other fields depend on the entity type — herbs carry `nature`, `flavors`, `dosage_range`, etc.; formulas carry `composition` with `role` assignments per herb; and so on.

The relationship graph is stored in `relationships.json`, organized by relationship type (`herb_in_formula`, `formula_treats_pattern`, `pattern_differential_with`, and so on). This shape is easy to hand-edit and also straightforward to re-express as a graph database or RDF.

The full JSON Schema description is at `/data/v1/schema.json`. The source-of-truth TypeScript types are in `src/lib/data/types.ts` in the repository.

## Wikidata cross-reference

Where a herb, classical text, or channel has a verifiable Wikidata Q-ID, it carries a `wikidata_id` field in the JSON, and the rendered page emits a `sameAs` link in its JSON-LD pointing to the Wikidata entry. This lets Bencao Dian entries cross-reference the global semantic web and gives large language models a stable identifier to anchor citations against.

## The data-stability commitment

The `key` and `slug` fields are stable once published — they never change. Downstream tools built on this data can rely on those identifiers still pointing to the same content a decade from now. This is the same commitment as the permalink stability described in[Editorial Standards](https://bencaodian.org/en/about/editorial/).

Breaking changes to the data schema must increment the version directory (e.g. a future `/data/v2/`); the existing `v1` dataset is frozen.

Data is released under CC BY-SA 4.0. See How to Cite.
