# A Structured Dataset of 174 Classical TCM Formulas

## 1. Dataset Overview
This dataset contains structured data for 174 classical Traditional Chinese Medicine (TCM) formulas. It focuses on the specific composition of each formula, detailing the ingredients, their precise dosages, and their functional roles ("Jun-Chen-Zuo-Shi") within the prescription.

## 2. File Information
- **File Name**: `174 Structured Classical Formulas.csv`
- **Format**: CSV (Comma-Separated Values)
- **Encoding**: UTF-8
- **Total Records**: 1249 rows (representing individual herb entries across 174 formulas)

## 3. Data Dictionary (Column Descriptions)
The dataset consists of the following columns:

| Column Name | Description | Example |
| :--- | :--- | :--- |
| **ID** | Unique identifier for the record/row. | `11` |
| **Formula Name** | The standardized Pinyin name of the TCM formula. | `An Gong Niu Huang Wan` |
| **Herb Name (English)** | The standardized English name of the medicinal herb. | `Coptis rhizome` |
| **Dose** | The numerical value of the dosage for the specific herb. | `30.0` |
| **Unit (English)** | The measurement unit for the dosage. | `g` (gram), `ml` (milliliter) |
| **Role (English)** | The hierarchical role of the herb in the formula based on TCM theory (Monarch, Minister, Assistant, Guide). | `Minister` |

## 4. Usage Notes
- **Empty Values**: Some rows may have empty values in the `Dose` or `Unit` columns. This typically indicates ingredients where specific dosages were not applicable or traditionally specified (e.g., "Gold leaf" or "Honey" as a binder).
- **Roles**: The roles correspond to the traditional "Jun-Chen-Zuo-Shi" theory:
    - **Monarch (Jun)**: The principal drug treating the main cause or symptom.
    - **Minister (Chen)**: Aids the Monarch or treats accompanying symptoms.
    - **Assistant (Zuo)**: Reinforces the effect, treats secondary symptoms, or moderates toxicity.
    - **Guide (Shi)**: Directs the medicine to the affected area or harmonizes the formula.



# 5. Citation
If you use this dataset in your research, please cite it via the following DOI: **[10.5281/zenodo.18222225](https://doi.org/10.5281/zenodo.18222225)**.



## 6.Contact
For questions, please contact:
LI Yuanbai：liyuanbai126@126.com