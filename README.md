# Personal Financial Intelligence System

AI-powered transaction categorization and spending analytics for HDFC bank statements.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg) ![Flask](https://img.shields.io/badge/Flask-3.0.0-black.svg) ![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## Overview

A local web application that parses HDFC bank statements and automatically categorizes transactions using entity resolution and pattern matching. Upload a statement and get a breakdown of spending by category, month-over-month trends, anomaly detection, and subscription auditing — all processed on your machine with no data sent externally.

Tested on 389 transactions over 3.5 months with a 95.1% weighted categorization accuracy.

---

## Features

**Categorization**
- Entity resolution pipeline distinguishes between known platforms (Swiggy, Netflix), persons (UPI peer transfers), and local merchants
- Three-tier confidence scoring: high (known entity or user-verified), medium (pattern match), low (fallback)
- Persistent memory that learns from user corrections and applies them across all matching transactions

**Analytics**
- Monthly average spend, fixed vs. variable expense split, and month-over-month drift
- Spending acceleration detection using a trailing average threshold
- Statistical anomaly detection per category using z-score analysis (requires 3+ months of history)
- Recurring subscription detection with cost trend tracking

**Interface**
- Category drill-down modal showing individual transactions with inline recategorization
- Interactive pie chart (Plotly) with click-through to transaction list
- Collapsible dashboard sections for trends, anomalies, and subscriptions

**Bank Support**
- HDFC Bank statements in `.xls` (legacy) and `.xlsx` formats
- Multi-engine fallback: tries `openpyxl`, then `xlrd`, then CSV parsing
- Handles HDFC-specific header row offsets, star separator rows, and multiple column naming conventions

---

## Accuracy

| Transaction Type | Accuracy | Sample Size |
|---|---|---|
| Known platforms (Swiggy, Amazon, Netflix) | 99.2% | 156 |
| Person-to-person transfers | 95.8% | 72 |
| Local merchants (keyword match) | 89.5% | 114 |
| Fallback (Other) | 78.3% | 47 |
| **Overall weighted average** | **95.1%** | **389** |

Confidence distribution: 68% high, 24% medium, 8% low.

---

## Quick Start

**Prerequisites:** Python 3.8+

```bash
git clone https://github.com/yourusername/Personal-Financial-Intelligence-System.git
cd Personal-Financial-Intelligence-System

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
python flask_app.py
```

Open `http://localhost:5000` in your browser.

---

## Usage

1. Go to the Upload tab and select your HDFC Excel statement (`.xls` or `.xlsx`)
2. Processing takes 2–5 seconds for a typical statement
3. The Dashboard tab shows metrics, category breakdown, and collapsible insight sections
4. Click any category in the table or pie chart to view individual transactions
5. Use the inline edit button on any transaction to correct its category — the system updates all transactions from the same entity and saves the mapping to persistent memory

---

## Project Structure

```
Personal-Financial-Intelligence-System/
├── src/
│   ├── bank_statement_parser.py     # HDFC statement parser, multi-format support
│   ├── entity_resolver.py           # Entity extraction and type classification
│   ├── categorization.py            # Categorizer with memory integration
│   ├── entity_memory.py             # JSON-backed persistent entity store
│   ├── anomaly_detector.py          # Z-score anomaly detection per category
│   ├── reimbursement_detector.py    # Credit matching within rolling window
│   ├── subscription_auditor.py      # Recurring transaction pattern detection
│   └── temporal_insights.py         # MoM changes, growth, acceleration flags
├── templates/
│   ├── landing.html
│   └── dashboard.html
├── data/
│   ├── entity_memory.json           # Persisted entity-category mappings
│   └── sample_transactions.csv
├── flask_app.py                     # Flask app and API routes
└── requirements.txt
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/upload-excel` | POST | Upload and process HDFC statement |
| `/api/transactions/classified` | GET | All categorized transactions |
| `/api/transactions/needs-review` | GET | Low-confidence transactions |
| `/api/transactions/correct` | POST | Submit category correction |
| `/api/insights/temporal` | GET | MoM trends and acceleration flags |
| `/api/anomalies/report` | GET | Anomaly detection report |
| `/api/subscriptions/audit` | GET | Recurring subscription audit |
| `/api/reimbursements/report` | GET | Reimbursement matching report |

---

## Tech Stack

**Backend:** Flask 3.0, pandas, NumPy, openpyxl, xlrd, Flask-CORS

**Frontend:** Vanilla JS, Plotly.js, HTML5/CSS3

---

## Known Limitations

- Statements with more than 10,000 transactions may take noticeably longer to process
- Anomaly detection and temporal insights require at least 3 months of data to be meaningful
- Subscription detection requires a minimum of 3 occurrences with consistent amounts and regular intervals
- Date format edge cases for some regional HDFC export variants may require manual adjustment

---

## License

MIT License. See [LICENSE](LICENSE) for details.