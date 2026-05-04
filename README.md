# Personal Financial Intelligence System

AI-powered transaction categorization and spending analytics for HDFC and SBI bank statements.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg) ![Flask](https://img.shields.io/badge/Flask-3.0.0-black.svg) ![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## Overview

A local web application that parses HDFC and SBI bank statements and automatically categorizes transactions using entity resolution and pattern matching. Upload a statement and get a breakdown of spending by category, month-over-month trends, anomaly detection, and subscription auditing — all processed on your machine with no data sent externally.

Tested on **1,188 transactions over 12 months** with **100% high-confidence categorization**.

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
- **HDFC Bank** statements in `.xls` (legacy) and `.xlsx` formats
- **SBI Bank** statements — multi-format support with auto-detection
- Auto-detects bank from statement signals before parsing
- Multi-engine fallback: tries `openpyxl`, then `xlrd`, then CSV parsing
- Handles bank-specific header row offsets, separator rows, and multiple column naming conventions

---

## Accuracy

| Transaction Type | Accuracy | Sample Size |
|---|---|---|
| Known platforms (Swiggy, Amazon, Netflix) | 99.2% | 214 |
| Person-to-person transfers | 100% | 609 |
| Local merchants (keyword match) | 89.5% | 118 |
| **Overall (high confidence)** | **100% high-conf** | **941** |

Entity breakdown: 214 platforms, 609 persons, 118 merchants.  
Confidence distribution: **100% high**, 0% medium, 0% low.

---

## Real-World Run Stats

From a 12-month HDFC statement (Jan 2025 – Jan 2026):

| Metric | Value |
|---|---|
| Total transactions parsed | 1,188 |
| Expense transactions | 941 |
| Credit transactions | 247 |
| Total spend | ₹1,89,656 |
| Average monthly spend | ₹15,860 |
| Subscriptions detected | 6 |
| Estimated monthly subscription cost | ₹799 |
| Anomalies flagged | 1 |
| Fastest growing category | Shopping |

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

1. Go to the Upload tab and select your HDFC or SBI Excel statement (`.xls` or `.xlsx`)
2. The system auto-detects the bank from the statement before parsing
3. Processing takes 2–5 seconds for a typical statement
4. The Dashboard tab shows metrics, category breakdown, and collapsible insight sections
5. Click any category in the table or pie chart to view individual transactions
6. Use the inline edit button on any transaction to correct its category — the system updates all transactions from the same entity and saves the mapping to persistent memory

---

## Project Structure

```
Personal-Financial-Intelligence-System/
├── src/
│   ├── bank_statement_parser.py     # HDFC & SBI statement parser, multi-format support
│   ├── bank_detector.py             # Auto-detects bank from statement signals
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
| `/api/upload-excel` | POST | Upload and process HDFC or SBI statement |
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
- Date format edge cases for some regional HDFC/SBI export variants may require manual adjustment

---

## License

MIT License. See [LICENSE](LICENSE) for details.