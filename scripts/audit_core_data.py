"""Reproduce the architecture's structural data audit and validate its SQLite DDL.

Usage: python3 scripts/audit_core_data.py [--check]
No application database is created and raw data is never modified.
"""

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "datasets/raw/bencaodian"
REPORT = ROOT / "docs/data-profile.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit():
    names = ("herbs", "formulas", "patterns", "classical_texts", "relationships")
    data = {name: json.loads((RAW / f"{name}.json").read_text()) for name in names}
    ids = {}
    for name in names[:-1]:
        rows = data[name]
        ids[name] = {row["key"] for row in rows}
        require(len(ids[name]) == len(rows), f"duplicate keys: {name}")
        require(all(row.get("name_zh", row.get("title_zh")) for row in rows),
                f"missing display names: {name}")

    rel = data["relationships"]
    mappings = {
        "herb_in_formula": ("herb", "herbs", "formula", "formulas"),
        "formula_treats_pattern": ("formula", "formulas", "pattern", "patterns"),
        "formula_cited_in_text": ("formula", "formulas", "text", "classical_texts"),
    }
    for name, (left, left_type, right, right_type) in mappings.items():
        rows = rel[name]
        require(len({(x[left], x[right]) for x in rows}) == len(rows),
                f"duplicate relation pairs: {name}")
        require(all(x[left] in ids[left_type] and x[right] in ids[right_type] for x in rows),
                f"invalid endpoints: {name}")

    composition = {}
    for formula in data["formulas"]:
        require(formula["source_text_key"] in ids["classical_texts"], "invalid formula source")
        for index, item in enumerate(formula["composition"]):
            pair = (formula["key"], item["herb_key"])
            require(pair not in composition, f"duplicate composition: {pair}")
            require(item["herb_key"] in ids["herbs"], f"missing herb: {pair}")
            composition[pair] = {"role": item.get("role"), "dosage": item.get("dosage"),
                                 "path": f"/composition/{index}"}
    from_rel = {(x["formula"], x["herb"]): x for x in rel["herb_in_formula"]}
    conflicts = []
    for pair in sorted(composition.keys() & from_rel.keys()):
        for field in ("role", "dosage"):
            if composition[pair][field] != from_rel[pair].get(field):
                conflicts.append({"formula": pair[0], "herb": pair[1], "field": field,
                                  "composition_value": composition[pair][field],
                                  "relationship_value": from_rel[pair].get(field)})

    formula_sources = {(x["key"], x["source_text_key"]) for x in data["formulas"]}
    citation_sources = {(x["formula"], x["text"]) for x in rel["formula_cited_in_text"]}
    missing, unresolved, herb_sources = [], [], set()
    reference_count = 0
    for herb in data["herbs"]:
        for index, citation in enumerate(herb.get("classical_references", [])):
            reference_count += 1
            issue = {"herb": herb["key"], "field_path": f"/classical_references/{index}",
                     "text_key": citation.get("text_key")}
            if not citation.get("text_key"):
                missing.append(issue)
            elif citation["text_key"] not in ids["classical_texts"]:
                unresolved.append(issue)
            else:
                herb_sources.add((herb["key"], citation["text_key"]))

    edge_counts = {
        "CONTAINS": len(composition.keys() | from_rel.keys()),
        "ASSOCIATED_WITH_PATTERN": len(rel["formula_treats_pattern"]),
        "CITED_IN_formula": len(formula_sources | citation_sources),
        "CITED_IN_herb": len(herb_sources),
    }
    return {
        "audit_version": 1,
        "scope": "Structural audit; not medical verification or an application import.",
        "files": {f"{name}.json": hashlib.sha256((RAW / f"{name}.json").read_bytes()).hexdigest()
                  for name in names},
        "entity_counts": {name: len(data[name]) for name in names[:-1]},
        "review_status": dict(Counter(x.get("verification", {}).get("status", "missing")
                                      for name in names[:-1] for x in data[name])),
        "relationship_object_counts": {name: len(rows) for name, rows in rel.items()},
        "planned_edge_counts": edge_counts,
        "planned_edge_total": sum(edge_counts.values()),
        "composition_only_pairs": sorted(composition.keys() - from_rel.keys()),
        "relationship_only_pairs": sorted(from_rel.keys() - composition.keys()),
        "composition_conflicts": conflicts,
        "additional_formula_citations": sorted(citation_sources - formula_sources),
        "herb_reference_count": reference_count,
        "herb_references_missing_text_key": missing,
        "herb_references_unresolved_text_key": unresolved,
        "classical_passage_count": sum(len(x.get("passages", [])) for x in data["classical_texts"]),
    }


def check_schema():
    with sqlite3.connect(":memory:") as db:
        db.executescript((ROOT / "docs/schema.sql").read_text())
        db.execute("INSERT INTO dataset VALUES ('test','test','v1','local','test','test')")
        for kind in ("formula", "herb", "pattern", "text"):
            db.execute("INSERT INTO source_record VALUES (?,?,?,?,?,?,?)",
                       (kind, "test", "fixture.json", "0" * 64, kind, "/0", "{}"))
            db.execute("INSERT INTO entity VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (kind, "test", kind, kind, kind, kind, None, kind, kind,
                        "{}", kind, "editor-reviewed", "editor_reviewed"))
        db.execute("INSERT INTO edge VALUES ('e','formula','CONTAINS','herb','{}','consistent')")
        db.execute("INSERT INTO edge VALUES ('p','formula','ASSOCIATED_WITH_PATTERN','pattern','{}','consistent')")
        db.execute("INSERT INTO edge VALUES ('c','herb','CITED_IN','text','{}','consistent')")
        db.execute("INSERT INTO evidence VALUES ('ev',NULL,'e','formula','','curated',NULL)")
        invalid = [
            "INSERT INTO edge VALUES ('bad','herb','CONTAINS','formula','{}','consistent')",
            "INSERT INTO edge VALUES ('bad','formula','CONTAINS','missing','{}','consistent')",
            "INSERT INTO edge VALUES ('duplicate','formula','CONTAINS','herb','{}','consistent')",
            "INSERT INTO evidence VALUES ('bad','herb','e','formula','','curated',NULL)",
            "INSERT INTO evidence VALUES ('bad',NULL,'e','formula','','source_quote',NULL)",
            "INSERT INTO evidence VALUES ('bad',NULL,'e','missing','','curated',NULL)",
            "UPDATE entity SET type='text' WHERE id='herb'",
        ]
        for statement in invalid:
            try:
                db.execute(statement)
            except sqlite3.IntegrityError:
                continue
            raise AssertionError(f"Constraint did not reject: {statement}")
        require(not db.execute("PRAGMA foreign_key_check").fetchall(), "foreign key failure")
        require(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "integrity failure")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare with the saved report")
    args = parser.parse_args()
    report = audit()
    # JSON round-trip normalizes tuples before comparing the saved report.
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        require(REPORT.read_text() == payload, "Data profile changed; review before regenerating")
    else:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(payload)
    check_schema()
    print(f"PASS: {sum(report['entity_counts'].values())} entities; "
          f"{report['planned_edge_total']} planned edges; DDL and constraint checks passed")


if __name__ == "__main__":
    main()
