# Personal Financial Intelligence System — *ArthaLens*

> **Turn a raw bank statement into a categorized, queryable, insight-rich view of your money — in seconds.**

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1-000000?logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)
![Gemini](https://img.shields.io/badge/AI-Gemini%202.5%20Flash-8E75B2?logo=googlegemini&logoColor=white)
![Deploy](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## Live Demo

**Deployment-ready — live demo coming soon.**

---

## Project Overview

**ArthaLens** is a full-stack personal finance platform that ingests raw HDFC and SBI bank statements, automatically categorizes every transaction through a multi-stage intelligence pipeline, and surfaces the results as an interactive analytics dashboard. Beyond static charts, it detects spending anomalies, audits recurring subscriptions, matches reimbursements, and lets users ask plain-English questions ("how much did I spend on food last month?") that are answered by an AI layer with strict guardrails. Crucially, it *learns* — every correction a user makes is remembered and applied to all future transactions from that entity.

It is built for anyone who wants to understand where their money actually goes without manually tagging hundreds of transactions — students, young professionals, and anyone tired of spreadsheet bookkeeping.

---

## Key Features

- **Bank statement parsing (HDFC + SBI)** — Auto-detects the source bank from statement signals, then dispatches to a bank-specific parser. Handles legacy `.xls`, modern `.xlsx`, header-row offsets, separator rows, and differing column naming conventions via a multi-engine fallback (`openpyxl` → `xlrd` → CSV).
- **Smart categorization pipeline (5-step priority system)** — A transaction is resolved through per-user correction memory, a shared (owner-seeded) cross-user memory, entity/platform detection, and keyword matching, with a graceful fallback — each stage carrying a confidence level (`high` / `medium` / `low`). Platform names are matched on whole-word boundaries to avoid false positives (e.g. "VI" no longer matches "VIA").
- **Anomaly detection (z-score based)** — Aggregates spend per category per month and flags statistically significant spikes or drops (configurable z-score threshold, requires ≥ 3 months of history), tagged by severity (`moderate` / `high` / `critical`).
- **Subscription auditing** — Detects recurring debits across monthly / quarterly / yearly cadences — including *intermittent* subscriptions with skipped months — tracks cost trends, and flags "zombie" long-running and high-cost subscriptions.
- **Reimbursement detection** — Matches refund credits back to the original purchase using strict criteria — exact amount (±₹1), same merchant/entity, the debit categorized as *Shopping*, within a 60-day forward window, one-to-one — so reimbursed expenses don't distort your real spend (`net_amount`). Deliberately conservative to avoid false positives from salary, interest, or P2P credits.
- **Feedback memory loop** — User corrections are persisted to a per-user `entity_memory` table and applied across all matching transactions, so the categorizer gets smarter with every edit. Corrections from the designated **owner account** additionally propagate to a shared `global_entity_memory` store that improves categorization for all users.
- **AI-powered natural language query (Gemini + intent routing)** — A keyword pre-classifier routes each question to the cheapest correct handler (subscription / opinion / SQL), minimizing LLM calls. SQL questions are translated to a sandboxed, validated `SELECT` and executed on a read-only database role.
- **Password reset by email** — A secure forgot-password flow (Flask-Mail) using stateless, signed `itsdangerous` tokens (30-minute expiry; no reset-token columns stored in the database).
- **Interactive Plotly dashboard** — Category breakdown rendered as a clickable pie chart with drill-down into individual transactions, plus collapsible trend, anomaly, and subscription panels, inline recategorization, and a responsive dark theme.
- **Deduplication (SHA-256 + MD5)** — A SHA-256 hash of each uploaded file blocks duplicate uploads; an MD5 per-transaction fingerprint enforces row-level uniqueness, so re-uploading an overlapping statement never double-counts.

---

## System Architecture

```
┌──────────┐   ┌─────────┐   ┌──────────────┐   ┌────────┐   ┌──────────┐   ┌────────────┐   ┌────────┐
│  UPLOAD  │──▶│  PARSE  │──▶│  CATEGORIZE  │──▶│ STORE  │──▶│ ANALYZE  │──▶│ VISUALIZE  │──▶│ QUERY  │
└──────────┘   └─────────┘   └──────────────┘   └────────┘   └──────────┘   └────────────┘   └────────┘
  .xls/.xlsx   bank detect    5-step priority    Postgres     anomalies/      Plotly         NL → AI
  + SHA-256    HDFC / SBI     + confidence       (Neon)       subscriptions   dashboard      (Gemini)
  dedup        parser         + MD5 fingerprint               reimbursements  drill-down     intent-routed
```

**Application design.** The backend follows the **Flask application-factory pattern** (`create_app()` in `app/__init__.py`), with functionality split across **blueprints** — `api` (data + processing), `auth` (login/register/reset), `main` (page routes), and `ai` (natural-language query). Cross-cutting concerns (SQLAlchemy, Migrate, Login, Limiter, CSRF, Mail) are registered as extensions on the factory, keeping the app testable and import-cycle-free.

**Split deployment: Render + Neon.** The application server and the database are deliberately separated:

- **Render** hosts the Flask web service (run under **Gunicorn** via `wsgi.py`), handling HTTP, parsing, and analytics compute.
- **Neon** provides serverless **PostgreSQL** as a managed, autoscaling data layer.

This separation of compute and storage means the stateless web tier can restart or scale without touching the data, and Neon's connection pooling and cold-start behavior are handled explicitly in the engine config (`pool_pre_ping`, `pool_recycle=300`, connection + statement timeouts, and TCP keepalives). The AI query path additionally retries once on a dropped connection, so a Neon cold start surfaces as a brief delay rather than an error. The AI engine connects to the *same* Neon database through a **separate read-only role** (`AI_DB_URL`), enforcing least privilege at the database level.

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.11+, Flask 3.1, Flask-SQLAlchemy 3.1, Flask-Migrate 4.1, Flask-Login 0.6, Flask-WTF (CSRF), Flask-Limiter 4.1, Flask-CORS, Flask-Mail |
| **Database** | PostgreSQL (Neon, serverless) via SQLAlchemy 2.0 + `psycopg2-binary` |
| **AI / Data** | Google Gemini 2.5 Flash (`google-generativeai` 0.8), pandas 2.3, NumPy 2.4 |
| **Parsing** | `openpyxl` 3.1, `xlrd` 2.0 (multi-engine Excel fallback) |
| **Frontend** | Server-rendered Jinja2 templates, vanilla JavaScript, Plotly.js, HTML5 / CSS3 (Bootstrap + Tailwind via CDN) |
| **Security** | Werkzeug password hashing (PBKDF2-SHA256), `itsdangerous` tokens, CSRF protection, read-only DB role, rate limiting |
| **Deployment** | Render (Gunicorn 26) + Neon PostgreSQL; Sentry SDK for error monitoring |

---

## Project Structure

```
Personal-Financial-Intelligence-System/
├── app/
│   ├── __init__.py                # App factory: extensions + blueprint registration
│   ├── models.py                  # SQLAlchemy models (6 tables)
│   ├── cli.py                     # Custom CLI commands (deduplicate, clear-data, backfill-global-memory)
│   ├── api/                       # Blueprint: upload, transactions, insights, corrections
│   ├── auth/                      # Blueprint: registration, login, password reset
│   ├── main/                      # Blueprint: landing + dashboard page routes
│   ├── ai/
│   │   └── query_engine.py        # NL → intent routing → SQL/opinion/subscription
│   ├── analytics/
│   │   ├── bank_detector.py       # Auto-detects bank, dispatches to the right parser
│   │   ├── bank_statement_parser.py  # HDFC statement parser (multi-format)
│   │   ├── sbi_parser.py          # SBI statement parser
│   │   ├── categorization.py      # SmartCategorizer — the 5-step priority pipeline
│   │   ├── entity_resolver.py     # Entity extraction + platform/person/merchant typing
│   │   ├── entity_memory.py       # Legacy JSON heuristic cache (dormant — DB memory is canonical)
│   │   ├── anomaly_detector.py    # Z-score anomaly detection per category/month
│   │   ├── subscription_auditor.py# Recurring-payment detection + cost-trend flags
│   │   ├── reimbursement_detector.py # Strict refund-to-purchase matching
│   │   └── temporal_insights.py   # MoM trends, growth, spending acceleration
│   ├── templates/                 # Jinja2 templates (auth, dashboard, legal, base)
│   └── static/                    # CSS, JS, images, legal documents
├── migrations/                    # Alembic migration history (flask db upgrade)
├── data/
│   └── entity_memory.json         # Legacy heuristic cache (no longer written to)
├── config.py                      # Config object (env-driven)
├── flask_app.py                   # Local dev entry point (app.run)
├── wsgi.py                        # Production entry point (gunicorn wsgi:app)
├── Procfile                       # Process definition: web: gunicorn wsgi:app
├── render.yaml                    # Render service + env-var config
├── .python-version                # Pins Python 3.11 on deploy
└── requirements.txt
```

---

## Setup & Installation

### Prerequisites

- Python **3.11+**
- A PostgreSQL database (a free [Neon](https://neon.tech) project works perfectly)
- A free [Google AI Studio](https://aistudio.google.com) API key for Gemini

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

Create a `.env` file in the project root (values shown are placeholders — never commit real secrets):

```env
# Required to boot
DATABASE_URL=postgresql://<user>:<password>@<host>/<db>        # full-access app role
SECRET_KEY=<a-long-random-string>                             # app refuses to start if unset

# Required for the AI query feature
AI_DB_URL=postgresql://<readonly_user>:<password>@<host>/<db>  # read-only role for the AI engine
GEMINI_API_KEY=<your-google-ai-studio-key>

# Required for the password-reset feature
MAIL_USERNAME=<your-smtp-email>
MAIL_PASSWORD=<your-smtp-app-password>

# Optional
OWNER_EMAIL=<account whose corrections seed the shared global memory>
# RECAPTCHA_SITE_KEY / RECAPTCHA_SECRET_KEY  (reCAPTCHA v3 — wired but currently disabled)
```

### 4. Apply database migrations

```bash
flask db upgrade
```

### 5. Run the app

```bash
python flask_app.py
```

Open **http://localhost:5000** in your browser.

> For a production-style run, use the WSGI entry point: `gunicorn wsgi:app`

---

## How It Works — Pipeline Deep Dive

### 1. The 5-step categorization priority

When a transaction is processed, `SmartCategorizer` (`app/analytics/categorization.py`) first resolves the entity (merchant / person / platform), then walks an ordered priority chain and stops at the first confident match — strongest signal first:

1. **Per-user DB entity memory (your corrections)** → If this user has previously corrected this entity and the stored confidence is ≥ 0.9, that category wins with **high** confidence. This is the feedback loop paying off.
2. **Global entity memory (cross-user, owner-seeded)** → A shared store of corrections made by the designated owner account; a hit applies the trusted category with **high** confidence, propagating curation to every user. *(A legacy shared JSON cache also exists here but is disabled for privacy.)*
3. **Entity-based categorization** → The resolver classifies the entity as a *platform* (e.g. Swiggy, Netflix → high confidence), *person* (UPI peer → `Transfer / P2P`, medium), or *merchant*, and maps known platforms directly.
4. **Keyword matching** → A curated category-keyword dictionary (Food & Dining, Transport, Shopping, Utilities, Entertainment, Healthcare, Rent, Education, ATM/Cash) provides a **medium**-confidence fallback.
5. **Default** → Anything unmatched is labelled **Other** at **low** confidence and queued for user review.

User and owner corrections are written back to memory, so the system improves continuously.

### 2. AI query intent routing

Rather than sending every question to the LLM, `query_engine.py` runs a cheap keyword pre-classifier (`_detect_intent`) that routes to the lowest-cost correct handler:

- **`subscription`** → Answered directly by the `SubscriptionAuditor` — **no LLM call**.
- **`opinion`** → Summary statistics (totals, monthly average, top categories) are computed locally, then a **single** Gemini call turns them into a budgeting-aware narrative answer.
- **`sql`** → Gemini translates the question into a PostgreSQL `SELECT`, which is then validated, scoped to the user, executed read-only, and a second Gemini call renders the rows into a friendly answer (with database values sanitized before they reach the prompt).

This keeps the system fast, cheap, and resilient to API rate limits — two of the three intents never touch the LLM quota at all.

### 3. The feedback loop

When a user edits a category in the dashboard:

1. The new category is validated against the allowed category set, then logged to the `corrections` table (audit trail of `old → new`).
2. The mapping is upserted into the per-user `entity_memory` table with elevated confidence.
3. **All** existing transactions from the same entity are re-labelled.
4. Future uploads hit step 1 of the categorization chain and inherit the correction automatically.
5. If the correction comes from the owner account, it is also written to `global_entity_memory`, improving categorization for every user.

The model isn't retrained — it *remembers*, which is faster, fully explainable, and (for individual users) private to that account.

---

## Database Schema

Six tables, user-scoped with cascading deletes and unique constraints for idempotent ingestion:

| Table | Description |
|---|---|
| **`users`** | Account records — email, hashed password, timestamps; root of all per-user data. |
| **`transactions`** | Every parsed transaction — date, entity, amount, category, type, confidence, reimbursement flag, and an MD5 `fingerprint` enforcing per-user row uniqueness. |
| **`entity_memory`** | Per-user learned entity → category mappings with confidence and correction counts (powers step 1 of categorization). |
| **`global_entity_memory`** | Cross-user, owner-seeded entity → category mappings shared across all accounts (powers step 2). |
| **`corrections`** | Immutable audit log of every user recategorization (`old_category → new_category`). |
| **`uploads_log`** | One row per uploaded statement — filename, detected bank, row count, and a SHA-256 `file_hash` that blocks duplicate uploads. |

---

## Security

- **Password hashing** — Credentials are stored as salted Werkzeug hashes (PBKDF2-SHA256); plaintext passwords are never persisted.
- **Fail-fast secrets** — The app refuses to start if `SECRET_KEY` is not set.
- **Read-only AI database role** — The AI query engine connects through a dedicated least-privilege `AI_DB_URL` role, so a generated query physically *cannot* mutate data.
- **Automatic `user_id` injection** — Every AI-generated SQL query is rewritten server-side to force `user_id = <current_user>`, guaranteeing strict data isolation between accounts regardless of what the LLM produces.
- **Validated, sandboxed SQL** — Generated SQL must be a single `SELECT`; dangerous keywords (`DROP / DELETE / INSERT / UPDATE / ALTER / TRUNCATE / GRANT / REVOKE`), set operations (`UNION / EXCEPT / INTERSECT`), stacked statements (`;`), and access to sensitive tables (e.g. `users`) are rejected before execution, and an automatic `LIMIT` caps result size.
- **Prompt-injection mitigation** — Database values are sanitized before being interpolated into LLM prompts, reducing the risk of a crafted merchant name hijacking a response.
- **Input validation** — Category corrections are validated against the allowed category set before storage.
- **Stateless password-reset tokens** — Reset links use signed, expiring `itsdangerous` tokens; no reset secrets are stored in the database.
- **CSRF protection** — All state-changing form submissions are guarded by Flask-WTF CSRF tokens.
- **Rate limiting** — Flask-Limiter throttles authentication and API requests to protect the app and the LLM quota.

---

## AI Attribution

> The frontend UI was designed with AI assistance (**Google Stitch + Claude**). All backend logic, the analytics pipeline, and the system architecture are **original** work.

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
