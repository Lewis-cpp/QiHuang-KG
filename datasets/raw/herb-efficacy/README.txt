# Structured Dataset of Traditional Efficacies for Chinese Herbal Medicines

**DOI:** [10.5281/zenodo.18207410](https://doi.org/10.5281/zenodo.18207410)

## 1. Overview
This dataset provides a comprehensive, **structured table of therapeutic effects (efficacies)** for Traditional Chinese Medicine (TCM) herbs. It transforms natural language descriptions into standardized, computable representations.

**Key Statistics:**
* **Total Entries:** 28,415 rows
* **Explicit Efficacies (Textbook-based):** 7,824 entries
* **Expanded Efficacies (Inferred):** 20,591 entries

## 2. File Information
* **File Name:** `expand251010eng.csv`
* **Format:** `.csv` (UTF-8 encoded)
* **Total Rows:** 28,415

## 3. Data Dictionary

The dataset contains the following fields:

| Column Header | Description |
| :--- | :--- |
| **Chinese Herb Code** | Unique identifier for the herb (e.g., `Z13`). |
| **Chinese Herb Name** | English common name of the herb. |
| **Efficacy ID** | Unique identifier for the efficacy entry. |
| **Efficacy Name** | Standardized therapeutic effect description (e.g., *Treat fatigue (kidney yang deficiency)*). |
| **Efficacy Type** | Classification of the efficacy source (Explicit vs. Expanded). |

## 4. Efficacy Classification (Node Types)

The `Efficacy Type` column classifies the data into two main categories:

### A. Explicit Efficacy Nodes
*(Labeled in file as: **Explicit efficacy nodes**)*
These are the structured therapeutic effects extracted directly from authoritative TCM textbooks (e.g., *Chinese Materia Medica*). They represent the explicit knowledge recorded in literature.

### B. Expanded Efficacy Nodes (Inferred)
*(Labeled in file as: **Rule A/B/C/D Expanded nodes**)*
These are implicit therapeutic effects inferred via a Knowledge Graph reasoning chain (*Etiology → Disease → Pattern → Symptom → Efficacy*).

* **Rule A (Symptom Manifestation):** ~14,900 entries
    * *Logic:* Infers that an herb treating a **Pattern** also treats the **Symptoms** manifested by that pattern.
* **Rule B (Hierarchical Inheritance):** ~4,200 entries
    * *Logic:* Propagates efficacy from a parent concept to its child concepts (e.g., Qi Deficiency → Spleen Qi Deficiency).
* **Rule C (Composite Symptoms):** ~260 entries
    * *Logic:* Inherits efficacies for complex symptoms containing embedded pattern descriptions.
* **Rule D (Pathogenesis Transformation):** ~1,100 entries
    * *Logic:* Extends efficacy along disease evolution pathways (preventive effects).

## 5. Usage
This dataset is suitable for:
* TCM Formula efficacy prediction.
* Knowledge graph construction.
* AI-based TCM reasoning and data mining.

## 6. Citation
Li, Yuanbai, Liu, Fangzhou, Li, Yihao, Du, Yu, Li, Meng, Qin, Qin, Yang, Yang, & Ma, Hongming. (2026). Structured Dataset of Traditional Efficacies for Chinese Herbal Medicines [Data set]. Zenodo. https://doi.org/10.5281/zenodo.18207410

## 7. Contact
For questions, please contact:
LI Yuanbai：liyuanbai126@126.com

