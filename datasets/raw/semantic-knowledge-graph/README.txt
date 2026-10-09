Dataset Title: A Semantic Knowledge Graph Linking Diseases, Patterns, Symptoms, and Herbs for Traditional Chinese Medicine
Dataset Authors: LI Yuanbai, YANG Yang
Date: 2026-01-06
File Encoding: UTF-8

-------------------------------------------------------------------------
1. DATASET OVERVIEW
-------------------------------------------------------------------------
This dataset constructs a full-semantic Traditional Chinese Medicine (TCM) efficacy knowledge graph. It systematically integrates the "Theory-Method-Formula-Herb" semantic chain. The data is structured as a Property Graph, containing standardized entities (herbs, efficacies, symptoms, patterns, diseases) and their semantic relationships.

Associated Research Articles:
This dataset serves as the foundation for the following research projects:

1. "A Knowledge Graph–Driven Hypergeometric Efficacy Prediction Model (HEPM) for Classical Traditional Chinese Herbal Formulas"
2. "Knowledge Graph–Based Structuring and Explicitation of Therapeutic-Effect Knowledge in Traditional Chinese Medicine"



Total Statistics:
- Nodes: 6,952
- Edges: 16,619 
(Note: All data are explicit knowledge extracted directly from authoritative textbooks.)
-------------------------------------------------------------------------
2. FILE LIST 
-------------------------------------------------------------------------
The dataset consists of the following files:

1. node251228eng.csv ... The entity list containing all TCM concepts.
2. edge251228eng.csv ... The relationship list defining semantic connections.
3. README.txt .......... This documentation file.

-------------------------------------------------------------------------
3. DATA DICTIONARY
-------------------------------------------------------------------------

File 1: node251228eng.csv
Description: Contains unique identifiers and attributes for all entities.
Format: Comma-Separated Values (CSV).

Columns:
-ID            : (String) Unique identifier for the entity (e.g., "Z1", "J721").
- ENGLISHINAME  : (String) Standardized English/Pinyin name of the entity.
- TYPE          : (String) The semantic category of the node.
                  Detailed statistics based on this version:
                  - "effect" (3,420 nodes) ... Efficacy entities.
                  - "Symptom (pattern)" (1,063 nodes) ... Contextualized symptoms linked to specific patterns.
                  - "Symptom name" (995 nodes) ... General symptom terms.
                  - "Chinese herb name" (484 nodes) ... Standard herbal medicine entities.
                  - "Pattern name" (447 nodes) ... Standard TCM syndrome names.
                  - "Disease name" (190 nodes) ... Modern disease classifications.
                  - "Symptom (disease)" (143 nodes) ... Symptoms associated with specific diseases.
                  - "Disease (pattern)" (127 nodes) ... Diseases manifesting as specific patterns.
                  - "Etiology" (41 nodes) ... Pathological causes.
                  - Other minor categories (42 nodes) ... Includes Pattern(pattern), Symptom(symptom), etc.


File 2: edge251228eng.csv
Description: Contains directed relationships between entities.
Format: Comma-Separated Values (CSV).

Columns:
- LID           : (Empty) Legacy ID column, can be ignored.
- source_id     : (String) The unique ID of the source node.
- target_id     : (String) The unique ID of the target node.
- TYPE          : (String) The semantic predicate of the relationship.
                  Detailed statistics based on this version:
                  - "has_effect" (7,944 edges) ... Represents 'Herb -> Efficacy' relations (e.g., Ginseng has effect Tonify Qi).
                  - "manifests_as" (3,478 edges) ... Represents 'Pattern -> Symptom' relations (e.g., Qi deficiency manifests as Fatigue).
                  - "treated_by" (3,048 edges) ... Represents 'Pattern/Symptom -> Efficacy' relations (e.g., Cold pattern is treated by Warming).
                  - "includes" (1,632 edges) ... Represents hierarchical relations (e.g., 'Headache' includes 'Headache due to wind-cold').
                  - "transforms_to" (517 edges) ... Represents pathological evolution (e.g., Qi stagnation transforms into Fire).

-------------------------------------------------------------------------
4. USAGE NOTES 
-------------------------------------------------------------------------
1. Data Integrity: The edge file defines a directed graph. The 'source_id' and 'target_id' correspond strictly to the 'ID' column in the node file.
2. Recommended Tools:
   - Graph Databases: Neo4j (Import using LOAD CSV command).
   - Analysis: Python (Pandas, NetworkX), Gephi.

-------------------------------------------------------------------------
5. LICENSE & CITATION 
-------------------------------------------------------------------------
License: CC-BY 4.0 International

Citation:
1. If the associated Data Paper is NOT yet published, please cite this dataset directly:
   LI Yuanbai, YANG Yang. (2026). A Semantic Knowledge Graph Linking Diseases, Patterns, Symptoms, and Herbs for Traditional Chinese Medicine [Data set]. Zenodo. https://doi.org/10.5281/zenodo.18173424

2. Once the Data Paper is published, please cite the paper instead:
   LI Yuanbai, YANG Yang. "A Semantic Knowledge Graph Linking Diseases, Patterns, Symptoms, and Herbs for Traditional Chinese Medicine". (Manuscript in preparation).


