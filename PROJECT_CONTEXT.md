# PROJECT_CONTEXT.md

> Single-source onboarding document for ArthaLens. A new session reading only
> this file should understand the entire project. Everything here was written
> by reading the actual source, not assumptions. Last regenerated: 2026-06-09.
> Updated 2026-06-10: reimbursement matcher v4 (strict exact-match), cross-user
> GlobalEntityMemory (owner-seeded Stage 2b) + backfill CLI, AI prompt-injection
> sanitization, correction-route category validation, `OWNER_EMAIL` env var,
> migration head → `463ffe6f87a6`, and the "Vi"/`VIA` whole-word
> categorization fix.
> Updated 2026-06-11: Neon cold-start resilience on the AI read-only engine
> (keepalives/connect_timeout + `execute_query` retry), Privacy/Terms updated
> for GlobalEntityMemory + read-only AI DB, and a pre-deployment checklist
> (see §14). Deployment is the immediate next step.
> Updated 2026-06-13: **SBI ingestion overhaul** — Email-Statement header format
> (Format 4: `Date | Details`), two-pattern UPI entity resolution (SBI
> `UPI/DR|CR|DRC/<rrn>/<merchant>` vs HDFC name-first `UPI-<merchant>-…`),
> single-word P2P recovery + VPA-based merchant/person disambiguation, SBI
> transaction-prefix classification (SWEEP kept as **Internal Transfer**, CEMTEX
> dropped), non-UPI prefix routing (ATM / DIRECT DR / credit-card), and
> **internal-transfer exclusion from spend at all three layers** (dashboard,
> analytics routes, AI query engine) via `entity_type != 'internal'`. See **§18**.
> Updated 2026-06-14: **Deployed live at https://arthalens.onrender.com/**.
> `render.yaml` buildCommand now automates `flask db upgrade` (no longer a manual
> post-deploy step). `Procfile` added (`web: gunicorn wsgi:app`) — resolves
> pre-deploy checklist item #2. `postgres://`→`postgresql://` normalization added
> to `config.py` — resolves checklist item #5. `OWNER_EMAIL` env var value in
> `render.yaml` updated from placeholder `snn@example.com` to the real owner email.
> Updated 2026-06-15: **Dashboard Recent-Transactions UX** (`newDashboard.html`,
> frontend-only). (1) Clicking a point on the Monthly Spending Trend chart now
> filters Recent Transactions to that month via a `plotly_click` handler →
> `_activeMonthFilter` (`YYYY-MM`), a dismissible 📅 month pill
> (`#month-filter-pill` + `clearMonthFilter()`), and a smooth scroll to the table.
> The handler slices the clicked x to 7 chars (`String(rawX).slice(0,7)`) so a
> whole month matches even when Plotly returns a full date; the trend xaxis is now
> `type:'date'` with `tickformat:'%b %Y'`. (2) The "All Transactions" sort-toggle
> button was replaced with a **Sort By** `<select id="sort-select">` (Date/Amount,
> asc/desc) — `sortAscending`/`allTransactionsClick()`/`sort-arrow-icon` removed,
> `applyFilter()` now sorts off the dropdown. See §11.
> Updated 2026-06-15: **Transactions page split.** Zone 5 (the Recent Transactions
> table) was moved out of `newDashboard.html` into a dedicated **`/transactions`**
> page (`main.transactions` → `dashboard/transactions.html`, self-contained
> standalone template with its own CSS vars / theme init / navbar / JS). The new
> page supports search, category filter, sort, Load-More paging, and inline category
> edit (`POST /api/transactions/correct`), and pre-filters from URL params
> (`?month=YYYY-MM` or `?category=...`) with a dismissible filter banner +
> `clearAllFilters()`. Cross-links from the dashboard donut and trend charts now do
> `window.location.href` redirects to `/transactions?...` instead of in-page DOM
> filtering/scroll. The dashboard's `renderTransactions`/`applyFilter`/
> `filterTransactions`/`loadMoreTransactions`/`setMonthFilter`/`clearMonthFilter`/
> `openEdit` and the `_activeMonthFilter`/`currentOffset`/`pageSize` vars were
> removed; `_allTransactions` + the donut/KPI wiring stay. See §11.
> Updated 2026-06-15: **Anomaly detector → rolling-window z-score.** The detector
> (`anomaly_detector.py`) previously tested only the **single most-recent month**
> per category against **all** prior months, so (a) historical anomalies were never
> detected and (b) a long history inflated the baseline std and suppressed detection
> over time — the dashboard showed "No anomalies detected" despite 27 months of data.
> `detect_anomalies()` now iterates **every** month from index 3 onward, using a
> **rolling 3-month prior window** (`ROLLING_WINDOW = 3`) as the baseline, and emits
> one anomaly per flagged month (all distinct months kept, sorted by `abs(z)` desc).
> New per-anomaly fields: `actual_spend`/`expected_spend` (replacing
> `current_spend`/`baseline_mean`/`baseline_std`/`deviation_percent`); `category`,
> `month`, `z_score`, `anomaly_type`, `severity`, `explanation` unchanged, so
> `generate_report()` still returns `{summary, anomalies, metadata}` and the frontend
> needed no structural change. A **`MIN_ABSOLUTE_DIFF = 1000`** (₹) guard now skips
> statistically significant but financially trivial anomalies (`|actual − baseline_mean|
> < ₹1000`). Threshold was tuned **2.0 → 1.8 → 2.5** across iterations; final value is
> **`threshold=2.5`** on **both** `AnomalyDetector` instances (the `/api/anomalies/report`
> route and the upload-pipeline instance at ~`routes.py:208`). Frontend `renderAlerts()`
> in `newDashboard.html` now shows the top **5** anomalies (`.slice(0,5)`, was 8).
> Net effect on the seeded 2,202-row / 27-month dataset: **0 → 17** anomalies
> (33 at 1.8 with no guard → 17 after the 2.5 threshold + ₹1000 guard). See §16b.
> Updated 2026-06-20: **Upload categorization N+1 fix + global-memory normalization
> constraint.** (1) `SmartCategorizer` now **preloads the full `GlobalEntityMemory`
> table once** into a dict at init (new `_load_global_cache()`, mirroring the per-user
> `_load_db_cache()`) instead of `get_global_category()` issuing one DB query per
> transaction row. On a 958-debit-row statement the `categorize_dataframe` upload
> stage dropped **56,854.8 ms → 338.6 ms** (queries **959 → 2**) and total upload
> **60,218.7 ms → 2,523.4 ms**. Dict keys + lookups are `.lower().strip()`-normalized
> to preserve the original case-insensitive match (verified 1,228 lookups, 100% parity
> with the old per-row SQL; falsy guard kept). App-code change confined to
> `app/analytics/categorization.py`. (2) New migration **`38608c90f036`** adds a CHECK
> constraint `entity_name = lower(trim(entity_name))` on `global_entity_memory`,
> codifying the normalize-before-insert convention both writers already follow.
> Migration head → `38608c90f036`. See **§19**.

---

## 1. Project Overview

**ArthaLens** (internal name: *Personal Financial Intelligence System*) is a
single-user-per-account personal finance analytics web app. A user uploads an
HDFC or SBI bank statement (Excel), and the app parses it, categorizes every
transaction with a rule-based ML-style pipeline, detects reimbursements,
anomalies, and recurring subscriptions, and exposes a dashboard plus a natural
language AI query feature.

- **Built by:** Shashwat Narayan (solo developer), Hyderabad, Telangana, India.
- **Status:** Feature-complete. **Deployed and live at https://arthalens.onrender.com/**.
  Pre-deployment checklist completed (2026-06-11, see §14); two previously-failing
  items (Procfile, `postgres://` normalization) were fixed post-checklist and are
  now PASS. `render.yaml` + `.python-version` + `Procfile` present.
- **GitHub repo:** `https://github.com/ShashwatNarayan/Personal-Financial-Intelligence-System.git`

### Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask 3.1.3 (app-factory + blueprints) |
| WSGI server | Gunicorn 26 (`gunicorn wsgi:app`) |
| ORM / migrations | Flask-SQLAlchemy 3.1.1 + SQLAlchemy 2.0.48, Flask-Migrate 4.1 (Alembic) |
| Database | PostgreSQL via **Neon** (`psycopg2-binary`) |
| Auth | Flask-Login (session cookie) + Flask-WTF forms |
| AI | Google Gemini (`google-generativeai` 0.8.6, model `gemini-2.5-flash`) |
| Email | Flask-Mail (Gmail SMTP) for password reset |
| Data | pandas 2.3, numpy 2.4, scikit-learn 1.8, scipy 1.17, openpyxl, xlrd |
| Frontend | Server-rendered Jinja2 + vanilla JS. Bootstrap 5 (legal/about), Tailwind Play CDN (dashboard), Plotly charts. No React. |
| Rate limiting | Flask-Limiter (login/reset) + custom in-memory limiter (AI) |
| Error tracking | sentry-sdk present in requirements |

### Deployment
- **Render** (web service, US region for compute) + **Neon** Postgres (Singapore, AWS ap-southeast-1).
- `render.yaml` pins region `singapore`, plan `free`.
- Free tier constraints: cold starts, ephemeral filesystem (writes lost on redeploy), Gemini free-tier quotas, Render log retention ~7–30 days.

---

## 2. Architecture

### App factory (`app/__init__.py`)
`create_app(config_object='config.Config')`:
1. `Flask(__name__, template_folder='templates')`, loads config from `config.Config`.
2. Sets `MAX_CONTENT_LENGTH = 10 * 1024 * 1024` (10 MB upload cap — **H3**).
3. Overrides `SQLALCHEMY_ENGINE_OPTIONS` with:
   ```python
   {'pool_pre_ping': True, 'pool_size': 5, 'pool_recycle': 300,
    'connect_args': {'connect_timeout': 10, 'options': '-c statement_timeout=30000'}}
   ```
4. Initializes extensions: `CORS(app)`, `db`, `migrate`, `login_manager`, `limiter`, `csrf`, `mail`.
5. `login_manager.login_view = 'auth.login'`, `login_message_category = 'warning'`, registers `user_loader` (loads `User` by int id).
6. Registers blueprints: `api_bp`, `auth_bp`, `main_bp`, `ai_bp`.
7. Registers CLI commands: `deduplicate_cmd`, `clear_data_cmd`, `backfill_global_memory_cmd` (from `app/cli.py`).
8. Registers JSON error handlers for 404, 413 (file too large), 500.

### Extensions (module-level singletons in `app/__init__.py`)
```python
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day"])
csrf = CSRFProtect()
mail = Mail()
```

### Blueprints

| Blueprint | url_prefix | File | Purpose |
|---|---|---|---|
| `main_bp` | (none) | `app/main/routes.py` | Page routes (landing, dashboard, upload, about, legal) |
| `auth_bp` | `/auth` | `app/auth/routes.py` | Register, login, logout, password reset |
| `api_bp` | `/api` | `app/api/routes.py` | JSON API (upload, transactions, analytics) |
| `ai_bp` | `/api/ai` | `app/ai/routes.py` | AI natural-language query |

### Entry points
- **`wsgi.py`** — `from app import create_app; app = create_app()`. Production entry: `gunicorn wsgi:app`.
- **`flask_app.py`** — dev only. Forces UTF-8 stdout/stderr (Windows ₹ symbol fix), then `app.run(debug=True, host='localhost', port=5000, use_reloader=True)`. **Never used in production** (gunicorn imports `wsgi:app`, which never calls `app.run()`).

### Request lifecycle — a typical upload
1. `POST /api/upload-excel` (multipart, `@login_required`, CSRF-protected).
2. File saved to a per-request `tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)`.
3. SHA-256 file hash computed; duplicate upload (same user + hash) → HTTP 409.
4. `detect_bank()` reads first ~35 rows, scores HDFC vs SBI signals → routes to parser.
5. Parser produces a normalized DataFrame `df` (debit + credit rows).
6. `df_expenses = df[df['transaction_type'] == 'debit']` (credits dropped from storage); SmartCategorizer categorizes `df_expenses` (adds `category`/`entity_name`/`entity_type`).
7. **ReimbursementDetector (v4 strict) runs on `pd.concat([df_expenses, credits])`** — categorized debits + raw credits, so the matcher can read the debit `category` (Shopping-only rule) while still seeing credits.
8. Reimbursement flags (`is_reimbursed`, `reimbursed_amount`, `net_amount`) merged back into `df_expenses` by index.
9. AnomalyDetector + SubscriptionAuditor run on `df_expenses`.
10. Dedup by fingerprint, bulk insert `Transaction` rows, create `UploadLog`, seed `EntityMemory`.
11. JSON response with metrics, category breakdown, anomalies.
12. `finally:` deletes the temp file.

---

## 3. Database Schema

6 tables. **There are NO `reset_token` columns** — password reset uses
stateless itsdangerous tokens (see §10). **There are NO `net_amount` /
`reimbursed_amount` columns** — those are computed at load/serialization time;
only `is_reimbursed` (boolean) is persisted. Credits are not stored at all.

Source of truth: `app/models.py`. Migration head: `38608c90f036_add_check_constraint_normalizing_global_`
(parent `463ffe6f87a6_add_global_entity_memory_table`, grandparent `d5dcf2c09ef5_initial_schema`).
The head migration adds a CHECK constraint only — no model/column change (see §3
`global_entity_memory`, §19.2).

### `users` (model `User`, extends `UserMixin`)
| Column | Type | Constraints |
|---|---|---|
| id | Integer | PK |
| email | String(255) | unique, not null |
| password_hash | String(255) | not null (Werkzeug hash) |
| created_at | DateTime | default `utcnow` |
| last_login_at | DateTime | nullable |

Relationships (all `cascade='all, delete-orphan'`, `lazy='dynamic'`):
`entity_memory`, `transactions`, `corrections`, `uploads`.
Methods: `set_password`, `check_password`, `get_reset_token()`, `verify_reset_token()` (static).

### `transactions` (model `Transaction`)
| Column | Type | Constraints |
|---|---|---|
| id | Integer | PK |
| user_id | Integer | FK `users.id` ON DELETE CASCADE, not null |
| upload_id | Integer | FK `uploads_log.id` ON DELETE CASCADE, not null |
| txn_date | Date | not null |
| description | Text | |
| entity_name | String(255) | |
| amount | Numeric(12,2) | |
| transaction_type | String(10) | `'debit'` / `'credit'` (in practice only `'debit'` stored) |
| category | String(100) | |
| entity_type | String(50) | merchant / person / platform |
| confidence_level | String(20) | high / medium / low |
| is_reimbursed | Boolean | default False |
| fingerprint | String(32) | nullable (MD5 dedup hash) |

Indexes/constraints: `Index('ix_transactions_user_date', user_id, txn_date)`,
`UniqueConstraint(user_id, fingerprint)`. Relationship: `corrections`.

### `entity_memory` (model `EntityMemory`)
| Column | Type | Constraints |
|---|---|---|
| id | Integer | PK |
| user_id | Integer | FK `users.id` CASCADE, not null |
| entity_name | String(255) | not null |
| category | String(100) | not null |
| entity_type | String(50) | nullable |
| confidence | Float | default 1.0 |
| correction_count | Integer | default 0 |
| created_at | DateTime | default `utcnow` |
| updated_at | DateTime | default `utcnow`, onupdate `utcnow` |

Constraint: `UniqueConstraint(user_id, entity_name)`. This is the **canonical
learned-category store** (per-user merchant→category memory).

### `uploads_log` (model `UploadLog`)
| Column | Type | Constraints |
|---|---|---|
| id | Integer | PK |
| user_id | Integer | FK `users.id` CASCADE, not null |
| filename | String(255) | |
| bank_detected | String(50) | |
| row_count | Integer | |
| uploaded_at | DateTime | default `utcnow` |
| file_hash | String(64) | nullable (SHA-256) |

Constraint: `UniqueConstraint(user_id, file_hash)` (duplicate-upload guard).
Relationship: `transactions`.

### `corrections` (model `Correction`)
| Column | Type | Constraints |
|---|---|---|
| id | Integer | PK |
| user_id | Integer | FK `users.id` CASCADE, not null |
| transaction_id | Integer | FK `transactions.id` CASCADE, not null |
| entity_name | String(255) | |
| old_category | String(100) | |
| new_category | String(100) | |
| created_at | DateTime | default `utcnow` |

Audit trail of every manual category correction.

### `global_entity_memory` (model `GlobalEntityMemory`) — cross-user, owner-seeded
| Column | Type | Constraints |
|---|---|---|
| id | Integer | PK |
| entity_name | String(200) | **unique**, not null (stored lowercased/stripped); **CHECK `entity_name = lower(trim(entity_name))`** — constraint `ck_global_entity_name_normalized`, migration `38608c90f036` (§19.2) |
| category | String(50) | not null |
| contributed_by_user_id | Integer | FK `users.id` ON DELETE **SET NULL**, nullable |
| updated_at | DateTime | default `utcnow`, onupdate `utcnow` |

Cross-user shared merchant→category store. **Only the owner account (gated by
`OWNER_EMAIL`, set in `render.yaml` to `shashwatn2802@gmail.com`) writes to it**; every user reads it at
Stage 2b of categorization. Added in migration `463ffe6f87a6`. Seeded once via the
`flask backfill-global-memory` CLI command (614 rows from the owner's per-user
`EntityMemory`). See §7, §15. **Privacy note:** because the owner's `EntityMemory`
is ~70% `Transfer / P2P`, this table contains real person names that propagate to
all users.

---

## 4. All API Routes

### `app/api/routes.py` (prefix `/api`, all `@login_required`)

| Method | Path | Does | Request | Response |
|---|---|---|---|---|
| POST | `/api/upload-excel` | Full upload pipeline (parse→reimburse→categorize→anomaly→subscription→save) | multipart file `file` | `{status, message, upload_id, new_count, skipped_count, data:{metrics, category_breakdown, anomalies, action_items}}`; 409 on duplicate file; 400 if no debits |
| GET | `/api/transactions/classified` | All user transactions for drill-down, with subscription flagging | — | `{status, transactions:[{txn_id,date,merchant,description,amount,net_amount,category,entity_type,confidence_level,transaction_type,is_reimbursed,reimbursed_amount,is_subscription,...}], count}` |
| GET | `/api/transactions/needs-review` | Low-confidence transactions only | — | same row shape, `needs_review:true`; `count` |
| POST | `/api/transactions/correct` | Recategorize an entity; **validates `new_category` against the 12-value `VALID_CATEGORIES` enum (400 if invalid)**; updates all matching txns + upserts per-user `EntityMemory` + logs `Correction`; **if corrector is the owner (`OWNER_EMAIL`), also upserts `GlobalEntityMemory`** | JSON `{transaction_id\|txn_id, new_category}` | `{status, message, updated_count, aggregates:{category_breakdown}}`; 400 invalid category |
| GET | `/api/insights/temporal` | MoM changes, fastest-growing, acceleration flags, monthly totals | — | `{status, insights:{data_quality, mom_changes, fastest_growing, acceleration_flags, monthly_totals}}` |
| GET | `/api/reimbursements/report` | Reimbursement summary from stored data | — | `{status, report:{summary:{gross_spend,net_spend,total_reimbursed}, reimbursements:{...}, config, matched_pairs}}` |
| GET | `/api/anomalies/report` | Rolling-window z-score category anomalies (every month vs prior-3-month baseline; `threshold=2.5` + ₹1000 min-abs-diff guard — see §16b) | — | `{status, report:{summary, anomalies, metadata}}` |
| GET | `/api/subscriptions/audit` | Recurring subscription detection | — | `{status, report:{summary, subscriptions, metadata}}` |
| GET | `/api/corrections/summary` | Feedback-loop proof: correction counts + recent | — | `{status, total_corrections, recent:[{entity_name,old_category,new_category,created_at}]}` |

### `app/ai/routes.py` (prefix `/api/ai`)

| Method | Path | Auth | Does | Request | Response |
|---|---|---|---|---|---|
| POST | `/api/ai/query` | `@login_required` | NL query → intent routing → answer | JSON `{question}` (≤500 chars) | `{status, answer, row_count, sql?}` (sql only in debug); 400 invalid; 429 rate limited |

AI rate limit: custom in-memory sliding window, **10 requests / 60s per user_id**
(`_rate_store` deque). Returns 429 when exceeded.

---

## 5. Auth Routes (`app/auth/routes.py`, prefix `/auth`)

| Method | Path | Does | Rate limit | Form |
|---|---|---|---|---|
| GET/POST | `/auth/register` | Create account, auto-login, redirect to upload | none | `RegisterForm` |
| GET/POST | `/auth/login` | Authenticate, set `last_login_at` | **5/min on POST** | `LoginForm` |
| GET/POST | `/auth/reset_password` | Request reset link (emails token); always shows same message (no user enumeration) | **5/min on POST** | `ResetPasswordRequestForm` |
| GET/POST | `/auth/reset_password/<token>` | Validate token, set new password | none | `ResetPasswordForm` |
| POST | `/auth/logout` | Log out | none (`@login_required`) | — |

Forms (`app/auth/forms.py`, all FlaskForm/CSRF):
- `LoginForm`: email (Email), password, submit.
- `RegisterForm`: email, password (min 8), confirm_password (EqualTo).
- `ResetPasswordRequestForm`: email, submit.
- `ResetPasswordForm`: password (min 8), confirm_password (EqualTo), submit.

`_verify_recaptcha(token=None)` is called on login/register POST but **currently
returns `True` immediately** (reCAPTCHA disabled — keys not configured; original
body commented out).

### Main page routes (`app/main/routes.py`, no prefix)
| Method | Path | Renders |
|---|---|---|
| GET | `/` | `landing.html` (or redirect to `/dashboard` if authenticated) |
| GET | `/dashboard` | `dashboard/newDashboard.html` (`@login_required`) |
| GET | `/transactions` | Dedicated transactions page — `dashboard/transactions.html` (`@login_required`) |
| GET | `/upload` | `dashboard/upload.html` (`@login_required`) |
| GET | `/about` | `about.html` |
| GET | `/privacy` | `legal/privacy.html` |
| GET | `/terms` | `legal/terms.html` |

---

## 6. Analytics Pipeline — Upload Flow

Step by step inside `upload_excel()` (`app/api/routes.py`):

1. **Temp save + hash** — file → `tempfile.NamedTemporaryFile`; SHA-256 hash computed (read in binary). Duplicate (user+hash in `uploads_log`) → **409**.
2. **Bank detection** — `detect_bank(temp_path)` reads first 35 rows, scores SBI vs HDFC signal keywords, returns `'sbi'` / `'hdfc'` / `'unknown'` (unknown → HDFC parser).
3. **Parsing** — `get_parser(bank)` returns `(parser, validator)`. Parser loads Excel (tries `openpyxl`/`xlrd`, CSV fallback for HDFC), finds the header row, maps columns to `[date, description, merchant, amount, transaction_type, balance]`, parses dates (many formats), computes `transaction_type = 'credit' if credit>0 else 'debit'`, extracts merchant via regex. `validator.validate(df)` → 400 on failure.
4. **Debit filter** — `df_expenses = df[df['transaction_type'] == 'debit'].copy()`. 400 if empty. **Credits are intentionally excluded from DB storage (Option B).**
5. **5-stage categorization** — `SmartCategorizer(user_id).categorize_dataframe(df_expenses)` adds `category, entity_name, entity_type, confidence_level` (see §7, includes Stage 2b global lookup).
6. **Reimbursement detection (v4 strict) + merge** — runs on `pd.concat([df_expenses, credits])` (categorized debits + raw credit rows) so the Shopping-only, same-entity, exact-amount matcher can read the debit `category` while still seeing credits. It sets `is_reimbursed`/`reimbursed_amount`/`net_amount` on its copy; those debit-row flags are then reindexed back onto `df_expenses` by index (unmatched `net_amount` filled with `amount`). See §16.
7. **Anomaly detection** — defensive `if 'net_amount' not in df_expenses.columns: df_expenses['net_amount'] = df_expenses['amount']`, then `AnomalyDetector(df_expenses, threshold=2.5, min_months=3)` (rolling 3-month-window z-score + ₹1000 min-abs-diff guard — see §16b).
8. **Subscription audit** — `SubscriptionAuditor(df_expenses, min_occurrences=3)`.
9. **DB save loop** — preload existing fingerprints (one query); for each row compute `compute_fingerprint(user_id, date, description, amount)` (MD5); skip duplicates; build dict list; `db.session.bulk_insert_mappings(Transaction, ...)`. `is_reimbursed` read from row.
10. **UploadLog** — created (filename via `secure_filename`, bank, file_hash), `row_count` set to new count after insert.
11. **EntityMemory seeding** — bulk upsert of new entity→category mappings for future uploads.
12. **Stats** — computes monthly averages, fixed vs variable category split, MoM drift, anomalies for the JSON response.

---

## 7. Categorization Pipeline Detail

`SmartCategorizer.categorize_transaction(merchant, description)` →
`(category, entity_name, entity_type, confidence_level)`.

| Stage | Logic | Confidence assigned |
|---|---|---|
| **1. Entity resolution** | `EntityResolver.resolve(description, merchant)` → `(entity_name, entity_type)`. Parses UPI/POS/NEFT patterns, known platforms, human-name detection. `entity_type` ∈ {platform, person, merchant, unknown}. **Platform matching is whole-word** (`re.search(rf'\b{re.escape(platform)}\b', …)`) at all 3 sites in `entity_resolver.py` — fixed 2026-06-10 so short tokens like `'VI'` no longer match inside `'VIA'` (see §15). | (no category yet) |
| **2. DB entity memory** | If `user_id` set, look up `entity_name` in per-user `EntityMemory` cache (loaded once at init). If found and `confidence >= 0.9` → return that category. | **high** |
| **2b. Global entity memory** | `get_global_category(entity_name)` — case-insensitive lookup in the cross-user `GlobalEntityMemory` table, served from a **dict preloaded once per `SmartCategorizer`** (`.lower().strip()`-keyed; previously one DB query per row — see §19.1). Runs for **all** users (ungated). If a row exists → return that category. This is how the owner's corrections propagate to everyone. | **high** |
| **3. JSON shared memory** | **H5-DISABLED** — `self.memory = None`; all `self.memory.*` calls commented out (the old *file-based* global JSON cache; superseded by the DB-backed Stage 2b above). | n/a |
| **4. Entity-based category** | `EntityResolver.categorize_by_entity(entity_name, entity_type)`. Persons → `Transfer / P2P`; platforms mapped to category sets; merchants by keyword. | platform → **high**, else **medium** |
| **5. Keyword matching** | Substring match of `"{merchant} {description}".lower()` against `category_keywords` dict (Food & Dining, Transport, Shopping, Utilities, Entertainment, Healthcare, Rent, Education, ATM / Cash). Substring matching is intentional for noisy bank strings; the one exception is the Utilities `vi` token, which was changed to `'vodafone vi'` + `' vi '` (space-padded) so it only matches standalone, not inside `'VIA'`/`'INVOICE'` (2026-06-10, see §15). | **medium** |
| **Fallthrough** | No match. | `Other`, **low** |

> **Quirk:** `categorize_by_entity` can return `'Investment'` (Groww/Zerodha/
> Upstox/Angelone/Kite) — a category that is **not** in the dashboard's
> `CAT_COLORS`/`CAT_ICONS` maps, so such rows fall back to the `Other` color/icon
> in the UI while keeping the `Investment` label.

`categorize_dataframe(df)` iterates rows and appends the four columns in place
(preserves index — important for the reimbursement merge).

---

## 8. AI Query Engine (`app/ai/query_engine.py`)

Model: **`gemini-2.5-flash`** (free tier). Two lazy singletons: read-only SQL
engine (`AI_DB_URL`) and the configured Gemini client (`GEMINI_API_KEY`). Both
raise `RuntimeError` if their env var is missing (lazy, only when AI is used).

### Read-only engine resilience — Neon cold start (2026-06-11)
`get_ro_engine()` now mirrors the main engine's connection hardening:
`pool_pre_ping=True`, `pool_recycle=300`, `pool_size=2`, and `connect_args` with
`connect_timeout=10`, `options='-c statement_timeout=30000'`, plus TCP keepalives
(`keepalives=1`, `keepalives_idle=30`, `keepalives_interval=10`, `keepalives_count=5`).
On top of that, **`execute_query()` retries once** on `sqlalchemy.exc.OperationalError`
(1s sleep, then re-raise on the 2nd failure) — because Neon's serverless Postgres
auto-suspends and the *first* request after suspend can hit a reset connection
(`SSL SYSCALL error: Connection reset by peer`) that `pool_pre_ping` alone doesn't
fully cover. (Engine is a lazy singleton — a server restart is needed to pick up
the config.)

### Intent detection — `_detect_intent(question)` (pure keyword match, no LLM)
Returns one of three intents:
- **`subscription`** — keywords: `subscription(s)`, `recurring`, `monthly services`, `subscription spend`, `streaming`, etc.
- **`opinion`** — large keyword set: `what do you think`, `how am i doing`, `am i overspending`, `budget`, `advice`, `save money`, `reasonable`, `for a student`, etc.
- **`sql`** — default (anything else).

### Handlers
- **subscription** (`_handle_subscription_question`) — **no LLM call.** Loads txns, runs `SubscriptionAuditor`, returns a formatted list (`₹X/month` + up to 8 subs).
- **opinion** (`_handle_opinion_question`) — **single Gemini call.** Pulls *aggregated* summary only (total spend, ~months, avg monthly, top-3 category totals — **no individual transactions**), passes to Gemini for a 3–4 sentence narrative.
- **sql** (`run_query_pipeline`) — full NL→SQL→execute→answer:
  1. `generate_sql(question)` — Gemini Call 1; returns raw SELECT or literal `INVALID`.
  2. `validate_sql(sql)` — see below.
  3. `inject_user_id(sql, user_id)` — see below.
  4. `execute_query(sql)` — runs on the read-only engine.
  5. `generate_answer(question, rows, sql)` — Gemini Call 2; ≤20 rows previewed; **each row value is run through `_sanitize_for_prompt()` before interpolation** (prompt-injection defense, see below); 1–3 sentence answer, Indian Rupee formatting; never mentions SQL.

### `_sanitize_for_prompt(value)` — Call-2 prompt-injection defense (added 2026-06-10)
Module-level helper applied to every DB cell before it enters the `generate_answer`
prompt (raw `entity_name`/`description` from uploads are user-controlled). It
truncates values >200 chars and regex-replaces (case-insensitive) instruction-like
patterns with `[FILTERED]`: `ignore (previous|prior|above) instructions`,
`forget (previous|prior|above)`, `you are now`, `new instructions:`, `system:`,
`assistant:`, `<system>`, `<prompt>`. **Denylist — mitigation, not a guarantee**
(novel phrasings can slip through; impact is bounded since Call 2 only returns text,
no downstream tool/SQL execution).

### `validate_sql(sql)` — blocks
- empty or `INVALID`.
- **semicolons** (stacked statements).
- anything not starting with `SELECT` (allows leading `(`).
- **`FORBIDDEN_KEYWORDS`** = `DROP, DELETE, INSERT, UPDATE, CREATE, ALTER, TRUNCATE, GRANT, REVOKE, UNION, EXCEPT, INTERSECT`.
- **`FORBIDDEN_TABLES`** = `users, entity_memory, corrections, uploads, uploads_log` (word-boundary match) → only `transactions` is queryable.

### `inject_user_id(sql, user_id)`
Forces `user_id = {int}` onto the query (replaces an existing `user_id=...`, or
prepends into `WHERE`, or inserts a `WHERE` before GROUP/ORDER/HAVING/LIMIT or at
end). Adds `LIMIT 500` if none. **Post-injection scan**: if `UNION|EXCEPT|
INTERSECT` survives, raises `ValueError` (defense against a set-op smuggling a
second unfiltered query past the single-clause rewrite). `user_id` is always cast
to `int` — no injection risk.

### `SCHEMA_CONTEXT` shown to Gemini
Describes only the `transactions` table (id, user_id, txn_date, entity_name,
category, amount, net_amount, entity_type, confidence_level, transaction_type,
is_reimbursed), the 11 categories, and rules (raw SELECT only, ILIKE for names,
`DATE_TRUNC` for months, no `user_id`/`LIMIT` — injected automatically, return
`INVALID` if unanswerable).

### Route-level (`app/ai/routes.py`)
Rate limit 10/60s per user; question required and ≤500 chars; `sql` field
stripped from response unless `current_app.debug`.

---

## 9. Security Architecture

| ID | Measure | Where / detail |
|---|---|---|
| **C1** | SQL set-ops blocked (`UNION/EXCEPT/INTERSECT` in `FORBIDDEN_KEYWORDS`); semicolons blocked; **post-injection scan** re-checks for set-ops after `inject_user_id` and raises | `query_engine.py` `validate_sql`, `inject_user_id` |
| **C3** | **Prompt-injection sanitization** of DB rows before Gemini Call 2 (`_sanitize_for_prompt` — truncate + denylist `[FILTERED]`). Denylist, so mitigation not guarantee | `query_engine.py` `generate_answer` |
| **C4** | **Category enum validation** — `/transactions/correct` rejects any `new_category` not in `VALID_CATEGORIES` (400). Stops arbitrary text being stored as a category and reaching the opinion prompt / global memory | `api/routes.py` `correct_transaction` |
| **C2** | Production runs `gunicorn wsgi:app` (debug off). `debug=True` only in `flask_app.py`, which prod never executes | `wsgi.py`, `flask_app.py`, `render.yaml` |
| **H1** | `SECRET_KEY` fail-fast — `config.py` prints FATAL + `sys.exit(1)` if unset | `config.py` |
| **H2** | Per-request `tempfile.NamedTemporaryFile` for uploads; deleted in `finally` and on error | `api/routes.py` `upload_excel` |
| **H3** | `MAX_CONTENT_LENGTH = 10 MB`; 413 handler returns JSON | `app/__init__.py` |
| **H5** | *File-based* JSON entity memory disabled — `SmartCategorizer.memory = None`, all `self.memory.*` commented out. ⚠️ **Superseded:** a DB-backed cross-user store (`GlobalEntityMemory`, Stage 2b) was since **re-introduced** (owner-seeded). So the original "no cross-user category sharing" property **no longer holds** — see §3, §7, §15 | `categorization.py`, `models.py` |
| — | **Read-only DB role for AI** — AI queries run on a separate engine backed by `AI_DB_URL` (intended read-only role); cannot mutate data | `query_engine.py` `get_ro_engine` |
| — | **CSRF** — `CSRFProtect` global; all forms include `csrf_token`; JS API calls send `X-CSRFToken` | `app/__init__.py`, templates |
| — | **Password hashing** — Werkzeug `generate_password_hash` / `check_password_hash` (no plaintext) | `models.py` |
| — | **Login rate limiting** — 5/min on POST `/auth/login` and `/auth/reset_password`; global default 200/day | `auth/routes.py`, `app/__init__.py` |
| — | **No user enumeration on reset** — reset-request always flashes the same message regardless of whether the email exists | `auth/routes.py` |
| — | **reCAPTCHA v3** — code present (config keys, template hooks commented out, `_verify_recaptcha`) but **currently disabled**: `_verify_recaptcha` returns `True` immediately. Re-enable by removing the early return and configuring keys | `auth/routes.py`, `config.py` |

---

## 10. Password Reset Flow

- **Stateless tokens** — `User.get_reset_token()` uses
  `itsdangerous.URLSafeTimedSerializer(SECRET_KEY)` with salt `'password-reset'`.
  `User.verify_reset_token(token, max_age=1800)` decodes and returns the user, or
  `None` on bad/expired token. **30-minute TTL.**
- **No DB columns** — nothing stored server-side; token validity is cryptographic.
  (This is why there are no `reset_token` columns and the reset migration was a no-op.)
- **Routes** — `GET/POST /auth/reset_password` (request form, emails link) and
  `GET/POST /auth/reset_password/<token>` (set new password).
- **Email** — Flask-Mail `Message` via Gmail SMTP; link built with
  `url_for('auth.reset_password', token=..., _external=True)`. Subject
  "ArthaLens — Reset Your Password".
- **Env vars required:** `MAIL_USERNAME`, `MAIL_PASSWORD` (Gmail app password).
  `MAIL_SERVER`/`MAIL_PORT`/`MAIL_USE_TLS` default to `smtp.gmail.com` / 587 / true.
- **Templates:** `auth/reset_password_request.html` (request form) and
  `auth/reset_password.html` (new-password form). *(There is no
  `forgot_password.html`.)*

---

## 11. Frontend Templates

> Auth, landing, and dashboard templates are **standalone full HTML** (they do
> NOT extend `base.html`). Legal + about pages **do** extend `base.html`.
> Shared theme: dark background `#0d0f0d`, card `#131a13`, lime-green accent
> `#4ade80`, with a light-mode toggle persisted in `localStorage`
> (`arthalens-theme`). Category icons use lime stroke `#a3e635`.

| Template | Page | Key behaviour |
|---|---|---|
| `landing.html` | Public landing (`/`) | Hero, 6 feature cards (inline stroke SVG icons), "How It Works" 3 steps (with "processed and deleted immediately" privacy note under step 01), stats strip (`5-Stage Categorization Pipeline`, `HDFC + SBI`, `5 Analytics Engines`, `0 Manual Entry`). Theme toggle. Background uses static `notes.png`-style assets; logo via `url_for('static',...)`. |
| `auth/login.html` | `/auth/login` | Standalone. Currency-notes background (`images/notes.png`), glass card with drop shadow. Forgot-password link → `auth.reset_password_request`. reCAPTCHA script/hidden input **removed/commented (disabled)**; plain native form submit. |
| `auth/register.html` | `/auth/register` | Same styling as login; required Terms/Privacy consent checkbox; reCAPTCHA disabled. |
| `auth/reset_password_request.html` | `/auth/reset_password` | Email entry form, matches auth styling. |
| `auth/reset_password.html` | `/auth/reset_password/<token>` | New-password + confirm form. |
| `dashboard/newDashboard.html` | `/dashboard` (live) | The real dashboard. Tailwind CDN + Plotly + custom dark CSS. KPIs derived client-side from `/api/transactions/classified` + `/api/subscriptions/audit`. Plotly donut (category) + trend charts. Transaction table built in JS: `catPill()` renders a category pill **with a lime SVG icon** (flex, nowrap); subscription rows show a **red pill `.sub-badge`** (`#dc2626`, fully rounded). Inline category edit → `POST /api/transactions/correct`. Subscriptions modal. Review/needs-review flow reuses `catPill()`. **Recent-Transactions controls (2026-06-15):** category filter (`cat-filter`), search (`txn-search`), and a **Sort By** dropdown (`sort-select`: `date_desc`/`date_asc`/`amount_desc`/`amount_asc`) — all flow through `applyFilter()`. Clicking a **trend-chart** point sets `_activeMonthFilter` (`YYYY-MM`), shows a dismissible 📅 pill (`#month-filter-pill`, cleared by `clearMonthFilter()`), and `applyFilter()` adds `t.date.startsWith(_activeMonthFilter)`. Donut-slice click still drives `cat-filter`. |
| `dashboard/upload.html` | `/upload` | Drag-drop upload UI → `POST /api/upload-excel`. |
| `dashboard/index.html`, `newDashboard.html` (top-level), `dashboard.html` | legacy | Older dashboards not wired to the live route. |
| `base.html` | shared shell | Bootstrap 5 CDN + Plotly CDN; used by legal/about pages. |
| `legal/privacy.html`, `legal/terms.html` | `/privacy`, `/terms` | Dark-themed legal docs (extend base.html). |
| `about.html` | `/about` | About page. |

Dashboard JS hits: `/api/transactions/classified`, `/api/transactions/needs-review`,
`/api/transactions/correct`, `/api/subscriptions/audit`, `/api/insights/temporal`,
`/api/reimbursements/report`, `/api/anomalies/report`.

---

## 12. Legal Pages

### `privacy.html` (Privacy Policy — DPDP Act 2023 + IT Act 2000 framing)
- **Account data stored:** email, password **hash only** (never plaintext), created/last-login timestamps. No name/phone/address/ID collected.
- **Financial data stored:** per transaction — date, description (≤200 chars), merchant/payee, amount, type, category, merchant-type, confidence, reimbursement status; plus SHA-256 file hash, original filename, and correction history.
- **Uploaded bank statement file:** *"Deleted immediately after parsing (within seconds). Not stored permanently."*
- **Logs** may incidentally contain transaction data / filenames (which may contain account numbers).
- **Gemini disclosure (§5):** specific data queries send the question + up to 20 transaction rows; opinion queries send aggregated summary only; subscription queries send **nothing** to Google. Critical free-tier disclosure: prompts/responses **may be used by Google to improve models and may be human-reviewed**.
- **Shared category learning (§4, added 2026-06-11):** discloses that category corrections made by the **operator/owner account** are saved to a shared store that can influence categorization for **all** users (your own corrections stay private); states it may expand to all users in future, with policy update first. Matches the owner-seeded `GlobalEntityMemory` code.
- **Read-only AI DB (§5, added 2026-06-11):** discloses that AI queries run through a separate **read-only** database connection — the AI can only read, never modify/add/delete. (§9 Data Security already listed the read-only role.)
- **Third parties:** Neon (Singapore), Render (US), Google Gemini (US/global), Google Fonts / Plotly / Bootstrap / Tailwind CDNs.
- **User rights:** access, correction, erasure, grievance, withdraw consent, nominate. Email to exercise; deletion within 7 business days (no self-service delete button yet).
- Known limitation noted: session cookies not flagged `Secure`.

### `terms.html` (Terms of Service)
- States the platform parses HDFC/SBI statements, categorizes, provides insights + AI query.
- Explicitly: **does NOT** access bank accounts, make transactions, give regulated financial advice, or **store the original bank statement file** ("deleted after parsing").
- Not financial/investment/tax advice; "as is"; liability capped at ₹0 (free service); governed by Indian law, Hyderabad jurisdiction.
- AI consent section mirrors the privacy Gemini disclosure; also (2026-06-11) discloses the **read-only AI DB connection** (§7) and **operator-seeded shared category learning** (§8).

---

## 13. Environment Variables

| Variable | Where used | Required? | If missing | Example |
|---|---|---|---|---|
| `SECRET_KEY` | `config.py` (sessions, CSRF, reset tokens) | **Yes** | **Fail-fast** `sys.exit(1)` at startup | `a-long-random-hex` |
| `DATABASE_URL` | `config.py` → `SQLALCHEMY_DATABASE_URI` | **Yes** | App boots but all DB ops fail (no fail-fast) | `postgresql://user:pass@host/db` |
| `AI_DB_URL` | `query_engine.get_ro_engine` (read-only role) | For AI | `RuntimeError` when AI query used (lazy) | `postgresql://ro_user:pass@host/db` |
| `GEMINI_API_KEY` | `query_engine._get_model` | For AI | `RuntimeError` when AI query used (lazy) | `AIza...` |
| `MAIL_USERNAME` | `config.py`, reset email sender | For reset | Reset email fails to send | `you@gmail.com` |
| `MAIL_PASSWORD` | `config.py` (SMTP auth) | For reset | SMTP auth fails | Gmail app password |
| `MAIL_SERVER` | `config.py` | Optional | defaults `smtp.gmail.com` | `smtp.gmail.com` |
| `MAIL_PORT` | `config.py` | Optional | defaults `587` | `587` |
| `MAIL_USE_TLS` | `config.py` | Optional | defaults `true` | `true` |
| `RECAPTCHA_SITE_KEY` | `config.py`, templates | Optional (unused — disabled) | nothing (reCAPTCHA off) | `6Lc...` |
| `RECAPTCHA_SECRET_KEY` | `config.py`, `_verify_recaptcha` | Optional (unused — disabled) | nothing (reCAPTCHA off) | `6Lc...` |
| `OWNER_EMAIL` | `api/routes.py` `_owner_email()` (read at request time) + `cli.py` backfill | Optional | **no global-memory writes happen** (safe no-op default) | `shashwatn2802@gmail.com` (set in `render.yaml`) |
| `FLASK_ENV` / `SENTRY_DSN` | environment / Sentry | Optional | no Sentry / default env | — |

---

## 14. Deployment

### `render.yaml`
```yaml
services:
  - type: web
    name: arthalens
    runtime: python
    region: singapore
    plan: free
    buildCommand: pip install -r requirements.txt && FLASK_APP=wsgi:app flask db upgrade
    startCommand: gunicorn wsgi:app
    envVars:   # all sync:false (set in dashboard) EXCEPT OWNER_EMAIL (literal value)
      - SECRET_KEY, DATABASE_URL, AI_DB_URL, GEMINI_API_KEY,
        MAIL_USERNAME, MAIL_PASSWORD, RECAPTCHA_SITE_KEY, RECAPTCHA_SECRET_KEY
      - OWNER_EMAIL: shashwatn2802@gmail.com   # has `value:` (not sync:false)
```
- **`.python-version`** = `3.11.9` (pins Python on Render).
- **Build:** `pip install -r requirements.txt`.
- **Start:** `gunicorn wsgi:app`.
- **DB migration is now automated** — the `buildCommand` in `render.yaml` runs `flask db upgrade` as part of the build step, so the schema is applied automatically on every deploy. **No manual post-deploy migration step is required.** Optionally, run **`flask backfill-global-memory`** once manually to (re-)seed `GlobalEntityMemory` from the owner's per-user corrections.
- **Neon connection pooling** (`app/__init__.py`): `pool_pre_ping=True` (handles Neon cold-start drops), `pool_size=5`, `pool_recycle=300` (aligns with Neon idle timeout), `connect_timeout=10`, `statement_timeout=30000`.

> **Caveat:** `.python-version` pins 3.11.9, but the local dev venv compiled
> bytecode as CPython 3.14 — pinned deps may resolve different wheels on Render
> than were tested locally. Smoke-test on 3.11 before relying on it.

### Pre-deployment checklist (run 2026-06-11) — 7 PASS / 1 PARTIAL / 1 caveat / 2 FAIL

| # | Check | Result |
|---|---|---|
| 1 | `requirements.txt` has all key deps | ✅ PASS (13/13) |
| 2 | `Procfile` present | ✅ PASS — **Procfile added** post-checklist (`web: gunicorn wsgi:app`) |
| 3 | All env vars referenced in `config.py` | ⚠️ PARTIAL — `AI_DB_URL` & `GEMINI_API_KEY` read in `query_engine.py`, not `config.py` |
| 4 | `SECRET_KEY` fail-fast | ⚠️ PASS w/ caveat — fails fast via `sys.exit(1)`, not `RuntimeError` |
| 5 | `DATABASE_URL` handles `postgres://`→`postgresql://` | ✅ PASS — **normalization added** post-checklist in `config.py` (`_db_url.replace('postgres://', 'postgresql://', 1)`) |
| 6 | Static via `url_for` | ✅ PASS |
| 7 | No `debug=True` in prod path | ✅ PASS (gunicorn `wsgi:app`) |
| 8 | `migrations/` ≥1 revision | ✅ PASS (3 revisions; folder gitignored — H6) |
| 9 | `.gitignore` has `.env` | ✅ PASS |
| 10 | `pool_pre_ping` + `connect_timeout` on both engines | ✅ PASS |

**Both previously-failing items were fixed post-checklist.** The remaining PARTIAL (item 3) does not block operation — `AI_DB_URL` and `GEMINI_API_KEY` are lazily validated at the point of use in `query_engine.py`, and either failure raises a `RuntimeError` with a clear message.

---

## 15. Known Decisions & Tech Debt

- **itsdangerous over DB columns for reset tokens** — chosen for stateless, zero-migration password reset; 30-min TTL is cryptographic. No `reset_token` columns; the "reset" migration was intentionally a no-op.
- **Reimbursement "Option B"** — detector runs on the **full df** (so credits can match debits), but **credits are NOT persisted** to the DB; only debit rows + their `is_reimbursed` flag are stored. Keeps the schema debit-centric.
- **reCAPTCHA disabled** — v3 integration is fully coded but `_verify_recaptcha` returns `True` and template hooks are commented out, because site/secret keys aren't configured yet.
- **H5: file-based JSON entity memory disabled** — the global `data/entity_memory.json` cache is off (`self.memory = None`); the JSON-backed `EntityMemory` class in `app/analytics/entity_memory.py` is dormant. ⚠️ **However, cross-user category sharing was deliberately RE-INTRODUCED** in a different form — see the GlobalEntityMemory decision below — so H5's original privacy property no longer holds.
- **Cross-user GlobalEntityMemory (owner-seeded) — reverses H5's isolation, by request (2026-06-10).** A new `global_entity_memory` table + Stage 2b lookup propagate one account's corrections to **all** users. Gated to **owner-only writes** via `OWNER_EMAIL` (set to `shashwatn2802@gmail.com` in `render.yaml`); everyone reads. `_owner_email()` reads the env at **request time** (not import time) after an import-order bug froze it to `''`. **Accepted privacy tradeoff:** the owner's corrections include person names (`entity_type == 'person'` → `Transfer / P2P`), which now appear in a cross-tenant table; ~70% of the 614 backfilled rows are P2P. A `person`-exclusion filter was offered but not applied.
- **Global-memory backfill** — `flask backfill-global-memory` (in `cli.py`, registered in `__init__.py`) one-time-seeded 614 rows from the owner's per-user `EntityMemory` into `GlobalEntityMemory` (the owner's 60 historical corrections predated the global-write code, so the table was empty until backfilled). Upsert-based, so idempotent.
- **AI prompt-injection sanitization (C3) is a denylist** — `_sanitize_for_prompt` filters known instruction phrases; novel phrasings can slip through. Bounded impact (Call 2 returns text only).
- **`VALID_CATEGORIES` duplicated** — the 12-value enum lives inline in `api/routes.py` (`correct_transaction`) and overlaps the categorizer's `category_keywords` keys in `categorization.py` (plus `Investment` from the resolver). Currently consistent but duplicated; a shared constant would prevent drift.
- **H6: migrations gitignored** — `.gitignore` contains `/migrations/`, so the migrations directory (incl. `d5dcf2c09ef5_initial_schema` and `463ffe6f87a6_add_global_entity_memory_table`) is **not version-controlled**. A fresh clone must regenerate or otherwise obtain migrations.
- **`google-generativeai` EOL** — the package emits a deprecation `FutureWarning` (support ended); migration to the `google.genai` SDK is pending.
- **No native mobile app** — PWA path identified for future; currently responsive web only.
- **Unverified accuracy claim removed** — the old "85–92% categorization accuracy" stat was removed from the landing page stats strip (replaced with "5-Stage Categorization Pipeline"). *Note: the phrase still appears in the Smart Categorization feature-card description copy and could be cleaned up.*
- **Credit Card Payment category deliberately excluded** — not part of the taxonomy. (Category lists are not fully unified: the correction enum `VALID_CATEGORIES` has **12** incl. `Investment`; the AI `SCHEMA_CONTEXT` lists **11** (no `Investment`); Stage-5 `category_keywords` has fewer still.)
- **Reimbursement matcher evolution** — v3 was amount-proximity (5% band, person-credit guard). v2 hardening (5%→2%, ₹25k credit cap, salary-keyword guard) was **superseded** by **v4 (strict exact-match, 2026-06-10)**: see §16. v4 dropped `_TOLERANCE_PCT`, `_is_person_credit`, the salary-keyword set, and the `RETAIL_REFUND_MAX` cap entirely, replacing them with exact-amount + same-entity + Shopping-only matching.
- **v4 reimbursement precision/recall tradeoff** — requiring same-entity + exact amount + `category == 'Shopping'` is deliberately conservative: it eliminates the salary/interest/P2P false positives but **misses** refunds that return under a different name or for non-Shopping debits. The Shopping gate depends on the detector receiving **categorized** debits (wired via `pd.concat([df_expenses, credits])` in `api/routes.py`); on the raw uncategorized `df` it would match nothing.
- **Neon cold-start resilience on the AI engine (2026-06-11)** — `get_ro_engine()` gained `connect_args` (connect_timeout + TCP keepalives) and `pool_size` 3→2; `execute_query()` now retries once on `OperationalError` after a 1s sleep. Addresses `SSL SYSCALL error: Connection reset by peer` on the first AI query after Neon auto-suspend. The engine is a lazy singleton, so a **server restart is required** to apply. See §8.
- **Privacy/Terms updated for two architectural facts (2026-06-11)** — Privacy §4 + a new "Shared category learning" note and Terms §8 now disclose the **operator-seeded `GlobalEntityMemory`** cross-user propagation (with "may expand" clause); Privacy §5 + Terms §7 now state AI queries use a **read-only DB connection**. Wording matches the owner-gated code (not "any user"). "Last updated: June 2026" date on the pages was left unchanged.
- **"Vi" false-positive categorization fix (2026-06-10)** — descriptions like `"…YATRA FLIGHT VIA SMART"` were mis-resolved to entity `'Vi'` (Vodafone Idea) → `Utilities`, because `'VI'` substring-matched `'VIA'`. Two fixes: (1) `entity_resolver.py` — **all 3** platform checks (`name_upper`, `text_upper`, and the UPI payment-app `actual_merchant` sub-branch) switched from `platform in X` to whole-word `re.search(rf'\b{re.escape(platform)}\b', X)`; (2) `categorization.py` — the Utilities keyword `'vi'` replaced with `'vodafone vi'` + space-padded `' vi '` so it only matches standalone (not inside `VIA`/`INVOICE`/`AVIA`). Other Stage-5 keywords keep intentional substring matching. With the fix, the example now falls through to the Stage-5 `'flight'` keyword → correctly **Transport**. Legit standalone `"VI"` (e.g. `UPI-VI-RECHARGE`) still resolves to the telecom platform.
- **Latent items:** `get_user_transactions_df` uses `t.transaction_type or ''` (a NULL type would silently drop a row from detection); `/transactions/classified` and `/needs-review` hardcode `'transaction_type': 'debit'` in their serialized output. Credits receive no `entity_type` at detector time (v4 no longer relies on it). The `_owner_email()` gate writes nothing if `OWNER_EMAIL` is unset.

---

## 16. Reimbursement Detection Logic (`app/analytics/reimbursement_detector.py`)

**Algorithm — v4 (strict exact-match, 2026-06-10).** Deliberately conservative:
trades recall for precision after the earlier amount-proximity matcher produced
salary/interest/P2P false positives.

1. Normalize: parse dates, `amount = |numeric|`, ensure `transaction_type`,
   init `net_amount`/`is_reimbursed`/`is_reimbursement_credit`/`reimbursed_amount`.
2. Split into debits and credits. If either side is empty → no matches.
3. For each debit (sorted by date), it must pass **ALL**:
   - **`category == 'Shopping'`** (else `continue` — refunds = retail returns), **and**
   - the credit is unmatched (one-to-one), **and**
   - credit date within **60-day forward** window, **and**
   - **`|credit.amount − debit.amount| ≤ ₹1`** (`_HIGH_CONF_RUPEES`) — exact, **and**
   - **same entity** — `_normalize_entity(credit) == _normalize_entity(debit)`
     (module helper: lowercased/stripped first non-empty of
     `entity_name`/`merchant`/`description`).
4. Pick the **closest credit in time**; mark debit `is_reimbursed=True`,
   `reimbursed_amount=credit`, `net_amount=max(debit−credit, 0)`, credit
   `is_reimbursement_credit=True`.
5. Confidence: `high` if within ₹1, else `medium` (in practice always `high`,
   since the amount mask already requires ≤₹1).

**Window:** forward only, `window_days=60`. No backward window.

**Constants:** `_HIGH_CONF_RUPEES = 1.0` (exact-amount tolerance). `_TOLERANCE_PCT`
was **removed**. `_MAX_DEBIT_AMOUNT = 100_000` is retained but **no longer used**
by the matcher (the strict rule supersedes the large-debit guard).

**Removed in v4:** `_TOLERANCE_PCT` (percentage band), `_is_person_credit` +
its salary-keyword set, and the `RETAIL_REFUND_MAX` ₹25k credit cap in
`api/routes.py`. These are all obsolete under exact-amount + same-entity matching.

**Category dependency (important):** the Shopping gate needs a `category` column on
the debit rows. The detector is therefore fed `pd.concat([df_expenses, credits])`
in `api/routes.py` — the **categorized** debits plus raw credit rows — not the raw
parser `df`. On the raw `df` (no `category`) the matcher would skip every debit.

**Why credits aren't stored (Option B):** the upload flow filters to debits
before persistence; the detector runs on the full df *before* that filter and
only the resulting debit flags are saved. Keeps the DB debit-centric and avoids
displaying refund credits as spend.

**Limitation:** transactions uploaded **before** this fix won't have
`is_reimbursed` set (the detector then ran on debits-only and matched nothing).
**A re-upload is required** for old data to show reimbursements. The
`/reimbursements/report` route recomputes from stored data, but since credits
are not stored, it can only reflect flags already persisted at upload time.

---

## 16b. Anomaly Detection Logic (`app/analytics/anomaly_detector.py`)

**Algorithm — rolling-window z-score (rewritten 2026-06-15).** Detects spending
anomalies at the **category × month** level on monthly-summed `net_amount`
(reimbursed rows contribute `net_amount = 0`).

1. `_prepare_data()` buckets transactions by `(category, year_month)` and sums
   `net_amount` → `self.monthly` (`category`, `year_month`, `spend`).
2. For each category, sort its months ascending and **iterate every month from
   index `ROLLING_WINDOW` (3) onward**. Each tested month's baseline is the
   **immediately-preceding 3 months** (`cat_data.iloc[max(0,i-3):i]['spend']`).
3. Per tested month, skip if baseline `< 2` points or `baseline_std == 0`;
   compute `z = (spend − baseline_mean) / baseline_std`.
4. **`MIN_ABSOLUTE_DIFF = 1000` (₹) guard** — skip if
   `|spend − baseline_mean| < ₹1000` (drops statistically significant but
   financially trivial swings, e.g. ₹50 → ₹120).
5. Flag if `|z| >= threshold`. **`threshold = 2.5`** (set by both callers).
   `anomaly_type = 'spike'` if `z > 0` else `'drop'`. Severity: `critical` ≥3.0,
   `high` ≥2.5, `moderate` ≥1.8 (moderate unreachable at the current 2.5 threshold).
6. All flagged months are kept (a category can have several distinct events);
   final list sorted by `abs(z)` descending.

**Per-anomaly fields:** `category`, `month`, `actual_spend`, `expected_spend`,
`z_score`, `anomaly_type`, `severity`, `explanation` (the explanation string
embeds the month + 3-month avg + `z=`). `generate_report()` returns the unchanged
shape `{summary, anomalies, metadata}`; `get_summary()` reads
`category`/`anomaly_type`/`severity`.

**Why the rewrite:** the previous version tested only the **last** month vs **all**
history, so historical anomalies were invisible and a growing baseline std
suppressed detection — the dashboard read "No anomalies detected" on a 27-month
dataset. The rolling window evaluates the full history with a stable local baseline.

**Tuning history:** `threshold` went `2.0 → 1.8 → 2.5`; the `₹1000` guard was added
last. Both `AnomalyDetector` call sites use `threshold=2.5, min_months=3`:
`/api/anomalies/report` and the upload pipeline (`api/routes.py:208`). Frontend
`renderAlerts()` shows the **top 5** by severity (`.slice(0,5)`).

**Reference result (seeded 2,202-row / 27-month dataset):** **17** anomalies
(14 spikes / 3 drops; 15 critical, 2 high). At `threshold=1.8` with no guard the
same data yields 33; raising to 2.5 removes 10, and the ₹1000 guard removes 6 more.

**Dead code:** the old `_generate_explanation()` and `_get_severity()` helper
methods remain but are no longer called (explanation + severity are now inlined in
the loop).

---

## 17. Category System

11 categories. Keywords drive Stage-5 matching (`categorization.py
category_keywords`); the dashboard maps each to a color (`CAT_COLORS`) and a lime
stroke SVG icon (`CAT_ICONS`) in `dashboard/newDashboard.html`.

| Category | Sample keywords | Dashboard icon (Feather-style, `viewBox 0 0 24 24`, stroke `#a3e635`) |
|---|---|---|
| Food & Dining | swiggy, zomato, dominos, restaurant, cafe, biryani, dhaba, bakery, mess… | takeaway coffee cup (`coffee`) |
| Shopping | amazon, flipkart, myntra, ajio, mall, dmart, reliance, nykaa, meesho… | shopping bag (`shopping-bag`) |
| Transport | uber, ola, rapido, cab, petrol, fuel, metro, irctc, indigo, redbus… | truck (`truck`) |
| Utilities | electricity, water, gas, airtel, jio, broadband, recharge, bescom… | lightning bolt (`zap`) |
| Entertainment | netflix, spotify, prime, hotstar, pvr, bookmyshow, steam, concert… | film strip (`film`) |
| Healthcare | hospital, clinic, doctor, pharmacy, apollo, medplus, 1mg, diagnostic… | pulse / activity line (`activity`) |
| Transfer / P2P | (assigned to `entity_type == 'person'`) | exchange / two-way arrows (`repeat`) |
| Rent | rent, lease, housing, apartment, pg, hostel, landlord, society… | house (`home`) |
| Education | school, college, tuition, byju, unacademy, udemy, coaching, institute… | graduation cap / book |
| ATM / Cash | atm, cash withdrawal, cdm | credit card (`credit-card`) |
| Other | (fallthrough, low confidence) | help circle with filled dot (`r="0.5" fill="#a3e635"`) |

> The `Other` icon uses a small **filled** circle for the bottom dot (a `<line>`
> rendered inconsistently at small sizes). The Transfer/P2P icon was corrected
> from a dollar-sign glyph to the exchange-arrows glyph.
>
> **Note:** `EntityResolver.categorize_by_entity` can also emit `Investment`
> (Groww/Zerodha/etc.), and it is the **12th** accepted value in the correction
> route's `VALID_CATEGORIES` enum — but it has no entry in `CAT_COLORS`/`CAT_ICONS`,
> so it renders with the `Other` fallback styling. (The dashboard table above lists
> the 11 icon-mapped categories; the AI `SCHEMA_CONTEXT` also lists 11, omitting
> `Investment`.)

---

## 18. SBI Multi-Format Parsing, VPA Resolution & Internal-Transfer Handling (2026-06-13)

This session hardened SBI ingestion end-to-end. Changes are confined to
`app/analytics/sbi_parser.py`, `app/analytics/entity_resolver.py`,
`app/api/routes.py`, `app/ai/query_engine.py`, and
`templates/dashboard/newDashboard.html`. `categorization.py` and the HDFC parser
were **not** changed; the HDFC path is structurally unaffected throughout.

### 18.1 SBI parser — two header formats (`sbi_parser.py`)
SBI exports now parse in two layouts:
- **Net Banking / YONO:** `Txn Date | … | Description | Ref No./Cheque No. | Debit | Credit | Balance`.
- **Email Statement (NEW — "Format 4"):** `Date | Details | Ref No/Cheque No | Debit | Credit | Balance`.

`find_header_row()` now also accepts a cell that is exactly `"DATE"` (alongside
`TXN DATE`/`TRANSACTION DATE`) and exactly `"DETAILS"` (alongside
`DESCRIPTION`/`NARRATION`); exact-match guards keep metadata rows like
`"Date of Statement : …"` from false-triggering. `COLUMN_MAPPINGS` gained a 4th
entry mapping `Date→date, Details→description, Ref No/Cheque No→reference,
Debit→debit, Credit→credit, Balance→balance`. Date format `DD/MM/YYYY` was
already covered. (Detection in `bank_detector.py` already scored these as SBI.)

### 18.2 Entity resolver — two UPI patterns (`entity_resolver.py`)
The single loose `upi_pattern` (which captured the `DR`/`CR` indicator as the
"merchant" → `"Dr"` for almost every SBI row) was replaced by two:
- **`upi_sbi_pattern`** = `UPI[/-](?:CR|DR|DRC)[/-]\d+[/-]([A-Z][A-Z0-9\s\.\-]{2,30}?)(?:[/-]|$)`
  — consumes the indicator + RRN, then captures the real payee (SBI).
- **`upi_hdfc_pattern`** = `UPI[-/]([A-Z][A-Z\s\.\-]{2,29}?)[-@]` — name-first (HDFC).

`resolve()` tries **SBI first, then HDFC** (`from_sbi = upi_sbi_pattern matched`).
This fixed both the SBI `"Dr"` bug and a regression where the single broken
pattern mis-grabbed HDFC names (e.g. `Ishan Ghosh`→`Unknown`, `Kiit Hospitality`→`Upi`).
Verified against 20 real HDFC UPI rows: 0 regressions.

### 18.3 SBI single-word P2P recovery (`entity_resolver.py`)
**Root constraint:** SBI hard-truncates the UPI payee-name field to **~8 chars**
at source (see §18.7). Many names collapse to a single token (`SHASHWAT`,
`CHAURASI`), which fails `is_human_name()`'s **≥2-word** gate, so they were typed
`merchant` → `categorize_by_entity` returns nothing → Stage-5 no keyword →
**`Other`**. (Multi-word truncations like `B SWAMY` already worked.)

Fix: in the SBI-format branch, a **single-word** name that is not a payment app
or known platform resolves to **`entity_type='person'`** (→ `Transfer / P2P`).
Cross-tab evidence: of 275 `merchant→Other` rows, **274 were single-word**, and
**all** `person`-typed rows were multi-word. Simulation: ~**234 of 274** previously-
`Other` rows recover to `person` (the rest are genuine non-persons / VPA-overridden
to merchant — see §18.4). HDFC is untouched: `upi_sbi_pattern` never matches HDFC
strings, so `from_sbi` is always False there (HDFC `Ishan Ghosh` etc. still `person`
via `is_human_name`).

### 18.4 VPA-based merchant/person disambiguation (`entity_resolver.py` + `sbi_parser.py`)
The VPA (6th segment of the SBI narration: `UPI/DR/<rrn>/<name>/<bank>/<VPA>/<type>`)
is the strongest secondary signal after the (truncated) name.
- `sbi_parser._extract_merchants()` now extracts a **`vpa`** column (regex
  `vpa_pattern`) plus a `txn_prefix` column; `vpa` is added to the parser's
  output `final_cols`.
- `resolve(description, merchant=None, vpa=None)` **self-extracts the VPA** from
  the description when none is passed — important because `categorization.py`
  (unchanged) calls `resolve(description, merchant)` without a `vpa`, so the
  signal still works end-to-end.
- **`_classify_vpa(vpa) → 'merchant' | 'person' | None`:**
  - **Processor/QR aggregators → `None`** (no signal): `paytmqr`, `bharatpe`,
    `pinelabs`, `phonepe`, `gpay`, `amazonpay`, `razorpay`, `billdesk`.
  - **Business keyword → `merchant`**: `store, mart, shop, hotel, cafe, foods,
    pay, qr, pos`.
  - **Structural heuristic:** dotted handle with numeric/short (≤2-char) suffix
    → `merchant` (`toyworld.6`, `isthara.p`, `indigo2.pa`); dotted with longer
    alpha suffix → `person` (`piyush.kha`); no dot → `person` (`shashwatn2`).
- In the single-word SBI branch (§18.3), `_classify_vpa()=='merchant'` **overrides**
  the person default → `merchant`; otherwise the person default holds.
- **Known false-positive risk:** `pay`/`qr` correctly flag merchant *collection*
  handles (Paytm soundbox, getepay, vyapar) but can sweep bare `paytm-NN` personal
  handles to merchant; trailing-dot handles (`lakshmi.`) yield an empty suffix →
  merchant. Minor; left as-is.

### 18.5 SBI transaction-prefix classification (`sbi_parser.py`)
New `_classify_txn_prefix()` adds a **`txn_prefix`** column from the leading token:
`SWEEP`, `ATM`, `INB`, `DIRECT_DR`, `CEMTEX`, `UPI_DR`, `UPI_CR`, else `OTHER`
(`SWEEP`/`ATM`/`INB`/`DIRECT`/`CEMTEX` matched by `startswith` before the
`UPI/DR`/`UPI/CR` substring checks, so `CEMTEX … UPI/DRC` is correctly `CEMTEX`).
`_remove_internal_rows()` now drops **only `CEMTEX`** (UPI reversals/refunds —
credits, not real debits). **`SWEEP` rows are KEPT** so the stored debit total
reconciles with the bank statement (see §18.8).

### 18.6 Non-UPI SBI routing in `resolve()` (`entity_resolver.py`)
Before UPI matching, the description prefix is routed (returns are 2-tuples;
`resolve()` signature stays `(entity_name, entity_type)` — the caller is unchanged):
- `startswith('SWEEP')` → `('Internal Transfer', 'internal')`
- `startswith('ATM')` → `('ATM Withdrawal', 'atm')` — Stage-5 keyword `atm` → `ATM / Cash`
- `startswith('DIRECT DR'|'DIRECT DEBIT')` → `('Direct Debit', 'direct_debit')`
- contains `'HDFC BANK CREDIT CARD'` or `'INB HDFC'` → `('HDFC Credit Card', 'merchant')`
- contains `'SBICARD'`/`'SBI CARD'` → `('SBI Card', 'merchant')`

### 18.7 Known SBI limitation — bank-side name truncation (~8 chars)
**SBI hard-truncates UPI beneficiary names to ~8 characters in the narration
field.** This is a bank-side constraint with **no technical workaround** — the
characters are simply absent from the data the regex receives (`avg entity_name
length on a real SBI upload ≈ 7.8 chars`; the resolver's `{2,30}` cap is never
the limiter). `"Shashwat Narayan"` arrives as `SHASHWAT`.
**Impact:** first-upload categorization accuracy for truncated merchants is low
(~60–70%). **Architectural mitigation:** the per-user **EntityMemory** feedback
loop (§3, §7 Stage 2) — the user corrects an entity once and the corrected
category fires on all future uploads of that entity (and, owner-seeded, the
cross-user `GlobalEntityMemory` at Stage 2b). *Interview framing:* a real-world
data-quality constraint was identified, and the system's existing feedback loop
is the designed mitigation rather than a brittle parser hack.

### 18.8 SWEEP / statement reconciliation & internal-transfer exclusion
**Problem found:** the dashboard showed ~₹34 L spend while the statement's
bottom-line total debit was ~₹44 L — the ~₹10 L gap was SBI **auto-sweep FD
movements** (`SWEEP TFR DR`), which are debits in the ledger total but **not real
spend**. They had been dropped entirely, breaking reconciliation.

**Resolution:** SWEEP rows are now **kept** and tagged `entity_name='Internal
Transfer'`, `entity_type='internal'` (their category still resolves to `Other`
via the categorizer, which was not changed). The dashboard total reconciles with
the statement, while spend analytics **exclude** them. The exclusion is applied
at **all three layers** via an `entity_type != 'internal'` filter:
1. **Dashboard** (`newDashboard.html`): `_spendTransactions = _allTransactions.filter(t => t.entity_type !== 'internal')`
   feeds `renderKpis` + `renderCategoryDonut`; the transaction **list** and date
   range still use `_allTransactions` (internal rows stay visible as "Internal
   Transfer"); a subtle reconciliation note (`Excl. ₹X internal transfers`) sits
   under the Avg-Monthly-Spend KPI.
2. **Analytics routes** (`api/routes.py`): the shared helper
   `get_user_transactions_df(user_id, months=None, exclude_internal=False)` gained
   the flag; passed `True` by `/insights/temporal`, `/reimbursements/report`,
   `/anomalies/report`, `/subscriptions/audit`, and the post-correction
   aggregate in `/transactions/correct`. **`/transactions/classified` and
   `/transactions/needs-review` keep the default `False`** (lists must show
   internal rows).
3. **AI query engine** (`query_engine.py`): `inject_user_id()` appends
   `AND entity_type != 'internal'` alongside the `user_id = {uid}` filter in all
   four injection branches (after `validate_sql`, before the set-op guard); the
   direct-fetch subscription/opinion handlers add
   `.filter(Transaction.entity_type != 'internal')`.

**Caveats / tech debt:**
- **`DIRECT DR` (12 rows) and credit-card rows still land in `Other`.** Routing
  them to a `Finance` category would need `categorization.py` changes (no
  `Finance` category exists today; "Credit Card Payment" is deliberately excluded
  from the taxonomy — §15). They are at least labeled `Direct Debit` /
  `HDFC Credit Card` / `SBI Card`.
- **NULL-safety:** the filter `entity_type != 'internal'` would also drop rows
  where `entity_type IS NULL` (SQL three-valued logic). There are **0** such rows
  today, so it is safe; **if NULL `entity_type` rows are ever introduced, switch
  to `Transaction.entity_type.is_distinct_from('internal')`** (and the equivalent
  `OR entity_type IS NULL` in the AI SQL injection) to avoid silently dropping
  them from analytics.
- **Effect is upload-time:** rows stored before this session carry no
  `entity_type='internal'`; a **re-upload** is required for SWEEP rows to be
  tagged and for the reconciliation/exclusion to take effect.

---

## 19. Upload Categorization N+1 Fix & Global-Memory Normalization Constraint (2026-06-20)

Two changes this session: a performance fix (app code, confined to
`app/analytics/categorization.py`) and a schema guarantee (a new migration).
Both were diagnosed and accuracy-reviewed before implementation —
`PERF_DIAGNOSIS.md` and `ACCURACY_IMPACT_REVIEW.md` in the repo root.

### 19.1 GlobalEntityMemory preload — eliminates the per-row N+1 (`categorization.py`)
**Problem:** `get_global_category(entity_name)` (Stage 2b, §7) ran **one DB query
per transaction row** during upload — `SELECT … WHERE lower(entity_name) =
lower(:name)` against `GlobalEntityMemory`. On a 958-debit-row statement that is
958 queries, each paying the ~52 ms Neon-Singapore round-trip, so categorization
dominated the upload (~50 s of the ~60 s total). (Diagnosis: `PERF_DIAGNOSIS.md`.)

**Fix:** `SmartCategorizer.__init__` now calls a new **`_load_global_cache()`**
that loads the **entire** `GlobalEntityMemory` table once into
`self._global_cache` — mirroring the existing per-user `_load_db_cache()`.
`get_global_category()` reads that dict instead of querying. The load is
**unfiltered** (the table is cross-user — no `user_id` scoping, no limit, no
pagination). Stages 1, 2, 4, 5 are untouched; the return contract is unchanged
(category string or `None`, confidence stays `high` on a hit).

**Normalization (correctness-critical):** stored keys are already lowercase (both
writers normalize — §3/§15), but `EntityResolver` hands Stage 2b a **Title-cased**
name (e.g. `"Swiggy"`). So the cache is keyed
`{ r.entity_name.lower().strip(): r.category }` and looked up with
`self._global_cache.get(entity_name.lower().strip())`, preserving the original
case-insensitive match; the `if not entity_name: return None` guard is retained.
A naive `{r.entity_name: r.category}` keyed on the raw stored name with a
Title-cased lookup would have silently missed nearly every entry and re-defaulted
those rows to `Other` — the specific risk called out in `ACCURACY_IMPACT_REVIEW.md`.

**Verified:** for all 614 current rows, both the exact stored name and its
`.title()` variant (1,228 lookups total) returned identical results via the new
dict and the old per-row SQL; absent-name and falsy-input behavior unchanged.

**Measured (958-debit-row HDFC statement, `scripts/perf_probe.py`):**

| Metric | Before | After |
|---|---|---|
| `categorize_dataframe` stage | 56,854.8 ms | 338.6 ms |
| Queries in that stage | 959 | 2 (1 user-memory + 1 global preload) |
| Total upload | 60,218.7 ms | 2,523.4 ms |

**Lifecycle / race note:** the cache lives on the `SmartCategorizer` instance
(one per upload request), so each upload takes a single fresh snapshot at start.
A GlobalEntityMemory write landing mid-upload (owner correction via
`/transactions/correct`) is not seen by the rest of that upload — a negligible
widening of an already non-deterministic race, and arguably more consistent
(one upload = one snapshot).

### 19.2 CHECK constraint on `global_entity_memory.entity_name` (migration `38608c90f036`)
Adds a DB-level CHECK **`ck_global_entity_name_normalized`** enforcing
`entity_name = lower(trim(entity_name))`, turning the normalize-before-insert
convention (already followed by both writers — `/transactions/correct` and the
`backfill-global-memory` CLI, §3/§15) into a schema-level guarantee. This is the
DB-side counterpart to §19.1's normalization assumption: it stops a future writer
from inserting a mixed-case key that the preloaded dict would then fail to match.

- **Migration:** `migrations/versions/38608c90f036_add_check_constraint_normalizing_global_.py`,
  revises `463ffe6f87a6`. New **migration head → `38608c90f036`**.
- `upgrade()` = `op.create_check_constraint(...)`; `downgrade()` =
  `op.drop_constraint(..., type_='check')`. **Additive only** — no data change,
  no table rewrite.
- **Verified:** 0 pre-existing violating rows; the constraint rejects a
  non-normalized test insert (`IntegrityError`, rolled back — nothing committed);
  an upgrade → downgrade → upgrade round-trip confirms reversibility.
- **Deploy:** rides the normal path — `render.yaml`'s `buildCommand` already runs
  `flask db upgrade` on deploy (§14), so it applies automatically on the next
  deploy with no manual step.

---

*End of PROJECT_CONTEXT.md*
