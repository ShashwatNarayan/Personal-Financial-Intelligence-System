# Personal Financial Intelligence System — *ArthaLens*

> Upload a bank statement. Get every transaction parsed, categorized, and analyzed — without tagging anything by hand.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)
![Deploy](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## Live Demo

**[https://arthalens.onrender.com/](https://arthalens.onrender.com/)**

> Hosted on Render (free tier) + Neon Postgres. Cold starts may add a few seconds on the first load.

<video src="https://github.com/user-attachments/assets/05c76fcc-9a97-4d28-9746-cf8e41d51154" controls width="100%"></video>

---

## Overview

**ArthaLens** ingests raw HDFC and SBI bank statements (Excel), parses them into a
normalized transaction table, and assigns every row a category through a staged
resolution pipeline. On top of that it runs several analytics passes — spending
anomalies, recurring subscriptions, reimbursement matching, month-over-month
trends — and presents the result as an interactive dashboard.

**How categorization works, stated plainly:** it is a **rules-based pipeline with
statistical layers and a user-correction feedback loop**. There is no model
inference in the categorization path. Transactions are resolved by regex-driven
entity extraction against bank-specific narration formats, matched against a
learned merchant→category memory, then against known platforms and a curated
keyword dictionary, with an explicit low-confidence fallback. Corrections a user
makes are persisted and applied to all matching transactions, so the system's
accuracy improves through use rather than retraining.

**Where an LLM is actually used:** one feature — the natural-language query box.
You can ask "how much did I spend on food last month?" and a language model
translates that to SQL, which is validated and executed under constraints before
a second call renders the rows into a sentence. That is the *only* part of the
system that calls a model. Parsing, categorization, anomaly detection,
subscription auditing, and reimbursement matching are all deterministic code.

Built for anyone who wants to see where their money goes without manually tagging
hundreds of rows in a spreadsheet.

---

## Key Features

- **Multi-bank statement parsing (HDFC + SBI).** Auto-detects the source bank by
  scoring signal keywords in the first ~35 rows, then dispatches to a
  bank-specific parser. Handles legacy `.xls`, modern `.xlsx`, shifted header
  rows, separator rows, multiple date formats, and differing column names via a
  multi-engine fallback (`openpyxl` → `xlrd` → CSV).

- **Staged entity resolution and categorization.** Five ordered stages, each
  carrying an explicit confidence level (`high` / `medium` / `low`), stopping at
  the first confident match. Unmatched rows are labelled `Other` at low
  confidence and surfaced in a review queue rather than silently guessed at.

- **Correction feedback loop.** Editing a category writes to a per-user memory
  table, relabels every existing transaction from that entity, and clears the row
  from the review queue. Future uploads of the same entity inherit the correction
  at the first pipeline stage.

- **Anomaly detection (rolling-window z-score).** Aggregates spend per category
  per month and tests *every* month against a rolling 3-month baseline — so
  historical anomalies surface, not just the most recent month. A minimum
  absolute-rupee floor suppresses statistically significant but financially
  trivial blips, and each anomaly is tagged by severity.

- **Subscription auditing.** Detects recurring debits across monthly, quarterly,
  and yearly cadences — including intermittent subscriptions with skipped months
  — tracks cost trends, and flags long-running and high-cost subscriptions.

- **Reimbursement matching.** Matches refund credits back to the original
  purchase on strict criteria: exact amount (±₹1), same entity, the debit
  categorized as *Shopping*, within a 60-day forward window, one-to-one.
  Deliberately conservative — it would rather miss a refund than misreport
  salary or a P2P credit as one.

- **Natural-language query (one feature among several).** A keyword
  pre-classifier routes each question to the cheapest correct handler:
  subscription questions are answered directly from the auditor with **no model
  call**, opinion questions use a single call over aggregate statistics only, and
  data questions go through a validated, sandboxed SQL path. Two of the three
  routes never touch the model quota.

- **Interactive dashboard.** Clickable category donut and monthly trend chart,
  drilling through to a dedicated transactions page with search, filtering,
  sorting, paginated loading, and inline recategorization. Responsive, with a
  dark/light theme.

- **Deduplication at two levels.** A SHA-256 hash of the uploaded file blocks
  duplicate uploads; an MD5 per-transaction fingerprint enforces row-level
  uniqueness, so re-uploading an overlapping statement never double-counts.

---

## System Architecture

```
┌──────────┐   ┌─────────┐   ┌──────────────┐   ┌────────┐   ┌──────────┐   ┌────────────┐   ┌────────┐
│  UPLOAD  │──▶│  PARSE  │──▶│  CATEGORIZE  │──▶│ STORE  │──▶│ ANALYZE  │──▶│ VISUALIZE  │──▶│ QUERY  │
└──────────┘   └─────────┘   └──────────────┘   └────────┘   └──────────┘   └────────────┘   └────────┘
  .xls/.xlsx   bank detect    5-stage rules      Postgres     anomalies /     Plotly          NL → SQL
  + SHA-256    HDFC / SBI     + confidence       (Neon)       subscriptions   dashboard       (validated,
  dedup        parser         + MD5 fingerprint               reimbursements  drill-down       read-only)
```

**Application design.** Flask **application-factory** pattern (`create_app()`),
with functionality split across **blueprints** — `api` (upload, transactions,
analytics), `auth` (login/register/reset), `main` (page routes), and `ai`
(natural-language query). Cross-cutting concerns (SQLAlchemy, Migrate, Login,
Limiter, CSRF, Mail) are registered as extensions on the factory, keeping the app
testable and free of import cycles.

**Split deployment: Render + Neon.** The application server and the database are
deliberately separated. Render hosts the Flask service under Gunicorn; Neon
provides serverless PostgreSQL. The stateless web tier can restart or scale
without touching data. Neon's cold-start behavior is handled explicitly in the
engine config (`pool_pre_ping`, `pool_recycle`, connection and statement
timeouts, TCP keepalives), and the query path retries once on a dropped
connection so a cold start surfaces as a brief delay rather than an error.

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.11+, Flask 3.1, Flask-SQLAlchemy 3.1, Flask-Migrate 4.1, Flask-Login 0.6, Flask-WTF (CSRF), Flask-Limiter 4.1, Flask-CORS, Flask-Mail |
| **Database** | PostgreSQL (Neon, serverless) via SQLAlchemy 2.0 + `psycopg2-binary` |
| **Data** | pandas 2.3, NumPy 2.4, SciPy, scikit-learn |
| **Parsing** | `openpyxl` 3.1, `xlrd` 2.0 (multi-engine Excel fallback) |
| **NL query** | Google Gemini 2.5 Flash — used only for the natural-language query feature |
| **Frontend** | Server-rendered Jinja2, vanilla JavaScript, Plotly.js, HTML5 / CSS3 (Bootstrap + Tailwind) |
| **Deployment** | Render (Gunicorn) + Neon PostgreSQL |

---

## Project Structure

```
Personal-Financial-Intelligence-System/
├── app/
│   ├── __init__.py                # App factory: extensions + blueprint registration
│   ├── models.py                  # SQLAlchemy models
│   ├── cli.py                     # Custom CLI commands
│   ├── api/                       # Blueprint: upload, transactions, insights, corrections
│   ├── auth/                      # Blueprint: registration, login, password reset
│   ├── main/                      # Blueprint: page routes
│   ├── ai/
│   │   └── query_engine.py        # NL → intent routing → SQL / opinion / subscription
│   ├── analytics/
│   │   ├── bank_detector.py       # Auto-detects bank, dispatches to the right parser
│   │   ├── bank_statement_parser.py  # HDFC statement parser (multi-format)
│   │   ├── sbi_parser.py          # SBI statement parser
│   │   ├── categorization.py      # The staged categorization pipeline
│   │   ├── entity_resolver.py     # Entity extraction + platform/person/merchant typing
│   │   ├── anomaly_detector.py    # Rolling-window z-score, per category/month
│   │   ├── subscription_auditor.py# Recurring-payment detection + cost-trend flags
│   │   ├── reimbursement_detector.py # Strict refund-to-purchase matching
│   │   └── temporal_insights.py   # MoM trends, growth, spending acceleration
│   ├── templates/                 # Jinja2 templates
│   └── static/                    # CSS, JS, images
├── migrations/                    # Alembic migration history
├── scripts/                       # One-off maintenance and profiling scripts
├── config.py                      # Config object (env-driven)
├── wsgi.py                        # Production entry point (gunicorn wsgi:app)
├── flask_app.py                   # Local dev entry point
├── Procfile                       # web: gunicorn wsgi:app
├── render.yaml                    # Render service + env-var config
└── requirements.txt
```

---

## Setup & Installation

### Prerequisites

- Python **3.11+**
- A PostgreSQL database (a free [Neon](https://neon.tech) project works well)
- A free [Google AI Studio](https://aistudio.google.com) API key — only needed for the natural-language query feature

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/ShashwatNarayan/Personal-Financial-Intelligence-System.git
cd Personal-Financial-Intelligence-System

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root (placeholders — never commit real secrets):

```env
# Required to boot
DATABASE_URL=postgresql://<user>:<password>@<host>/<db>         # full-access app role
SECRET_KEY=<a-long-random-string>                               # app refuses to start if unset

# Required for the natural-language query feature
AI_DB_URL=postgresql://<readonly_user>:<password>@<host>/<db>   # read-only role
GEMINI_API_KEY=<your-google-ai-studio-key>

# Required for password reset
MAIL_USERNAME=<your-smtp-email>
MAIL_PASSWORD=<your-smtp-app-password>

# Optional
OWNER_EMAIL=<account whose corrections seed the shared category store>
```

### 4. Apply database migrations

```bash
flask db upgrade
```

### 5. Run

```bash
python flask_app.py
```

Open **http://localhost:5000**. For a production-style run: `gunicorn wsgi:app`.

---

## Pipeline Deep Dive

### 1. The categorization stages

A transaction is first resolved to a canonical entity, then walked through an
ordered chain that stops at the first confident match — strongest signal first.

1. **Per-user memory (your corrections).** If this user has previously corrected
   this entity, that category wins at **high** confidence. This is the feedback
   loop paying off.
2. **Shared category store.** A curated cross-user entity→category store,
   seeded from a designated operator account, applied at **high** confidence.
3. **Entity-based resolution.** The resolver types the entity as a *platform*
   (mapped directly to a category, **high**), a *person* (peer transfer,
   **medium**), or a *merchant*.
4. **Keyword matching.** A curated category-keyword dictionary provides a
   **medium**-confidence fallback for noisy narrations.
5. **Default.** Anything unmatched is labelled `Other` at **low** confidence and
   queued for review.

### 2. Query intent routing

Rather than sending every question to a model, a cheap keyword pre-classifier
routes to the lowest-cost correct handler: **subscription** questions are
answered directly by the auditor with no model call; **opinion** questions
compute summary statistics locally and make a single call to turn them into a
narrative; **data** questions are translated to SQL, validated, scoped to the
requesting user, executed against a read-only role, and rendered into a sentence.
Two of the three routes never consume model quota at all.

### 3. The feedback loop

When a user edits a category: the change is validated against the allowed
category set and written to an audit log; the mapping is upserted into per-user
memory at full confidence; every existing transaction from that entity is
relabelled and its confidence raised so it leaves the review queue; and future
uploads hit stage 1 and inherit the correction automatically.

The model isn't retrained — it *remembers*, which is faster, fully explainable,
and (for individual users) private to that account.

---

## Engineering Notes

The parts of this project with a real decision behind them, and the reasoning.

**Per-user memory vs. the shared store — and why person names are excluded from
the latter.** Corrections are written to a per-user table, which is the primary
signal. A separate cross-user store lets curated merchant mappings benefit
everyone, which matters because bank narrations are noisy and the same merchant
appears under different strings across accounts. But the two stores are not
symmetric, and treating them as if they were would be a mistake: peer-to-peer
transfers resolve to **individual people's names**, which are personal data and
carry no useful signal for anyone else — knowing that one user pays a particular
person tells you nothing about another user's transactions. The cross-user store
therefore **excludes the peer-transfer category entirely**, enforced on both the
read path and the write path through a single shared constant so the two rules
cannot drift apart. Excluding them costs nothing in accuracy, because
person-typed entities are already routed correctly by stage 3 of the pipeline;
the only difference is that those rows report `medium` rather than `high`
confidence, which is the more honest value.

**Eliminating an N+1 in the upload path.** The shared store was originally
queried once per transaction row during categorization. On a 958-row statement
that is 958 round trips to a database in another region, and it dominated upload
time. Loading the store **once per upload** into an in-memory dictionary reduced
the categorization stage from **56,854 ms to 339 ms** (959 → 2 queries) and total
upload time from **60,219 ms to 2,523 ms**. The correctness subtlety worth
noting: the stored keys and the resolver's output are cased differently, so both
sides are normalized identically at cache-build and lookup time — a naive
implementation would have silently missed nearly every entry and quietly
re-defaulted those rows to `Other`. A database-level CHECK constraint now
enforces the normalization convention the cache depends on.

**The two bank parsers are genuinely different, not a shared parser with flags.**
HDFC and SBI describe the same transaction in structurally different ways. HDFC
UPI narrations are name-first (`UPI-<merchant>-<vpa>-…`); SBI puts a
direction indicator and reference number before the payee
(`UPI/DR/<ref>/<merchant>/…`), which needs a different regex and a different
capture group. SBI also ships two distinct header layouts (net-banking export vs
emailed statement) with different column names for the same fields. Most
consequentially, **SBI truncates UPI beneficiary names to roughly 8 characters at
the bank's end** — the characters are simply absent from the data, so no parser
can recover them. That is a real-world data-quality constraint with no technical
workaround, and the designed mitigation is the correction feedback loop: the user
fixes a truncated entity once and every future upload inherits it. Card-swipe
(POS) narrations add another shape, where the merchant name sits behind a
variable-length prefix of card number, reference, date, time, and city — anchored
during extraction on the timestamp token, which is the one reliably-formatted
field in that prefix.

---

## Database Schema

Six tables, user-scoped with cascading deletes and unique constraints for
idempotent ingestion.

| Table | Description |
|---|---|
| **`users`** | Account records — email, hashed password, timestamps; root of all per-user data. |
| **`transactions`** | Every parsed transaction — date, entity, amount, category, type, confidence, reimbursement flag, and an MD5 fingerprint enforcing per-user row uniqueness. |
| **`entity_memory`** | Per-user learned entity → category mappings with confidence and correction counts (powers stage 1). |
| **`global_entity_memory`** | Curated cross-user entity → category mappings (powers stage 2). A CHECK constraint keeps every stored name normalized. |
| **`corrections`** | Append-only audit log of every recategorization (`old → new`). |
| **`uploads_log`** | One row per uploaded statement — filename, detected bank, row count, and a SHA-256 hash that blocks duplicate uploads. |

---

## Security

- **Password hashing** — salted Werkzeug hashes (PBKDF2-SHA256); plaintext passwords are never stored.
- **Fail-fast secrets** — the app refuses to start if `SECRET_KEY` is unset.
- **Least-privilege database role for queries** — the natural-language query path connects through a dedicated role holding `SELECT` on the transactions table only, enforced by database grants rather than application logic alone.
- **Constrained SQL** — generated SQL must be a single `SELECT` against an allowlisted table; DML/DDL keywords, set operations, and stacked statements are rejected before execution, the query is rewritten server-side to scope it to the requesting user, and a row limit is applied automatically.
- **Prompt-injection mitigation** — database values are sanitized before being interpolated into prompts, reducing the risk of a crafted merchant name influencing a response.
- **Input validation** — category corrections are validated against the allowed category set before storage.
- **Stateless password-reset tokens** — signed, expiring `itsdangerous` tokens; no reset secrets stored in the database.
- **CSRF protection** — all state-changing submissions carry Flask-WTF CSRF tokens.
- **Rate limiting** — authentication and query endpoints are throttled.
- **Uploaded files are not retained** — statements are parsed from a per-request temporary file that is deleted immediately afterwards.

---

## AI Attribution

> The frontend UI was designed with AI assistance (**Google Stitch + Claude**).
> The backend logic, analytics pipeline, and system architecture are original work.

---

## Legal

A **Privacy Policy** and **Terms of Service** are available in-app at **`/privacy`** and **`/terms`**.

---

## Author

**Shashwat Narayan**
GitHub: [ShashwatNarayan/Personal-Financial-Intelligence-System](https://github.com/ShashwatNarayan/Personal-Financial-Intelligence-System)

---

## License

Released under the **MIT License** — see [LICENSE](LICENSE) for details.
