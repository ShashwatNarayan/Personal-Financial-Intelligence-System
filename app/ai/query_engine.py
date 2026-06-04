import os
import re

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions
from sqlalchemy import create_engine, text

# ── Lazy singletons ──────────────────────────────────────────────────────────
_ro_engine = None
_gemini_configured = False

_GEMINI_MODEL = 'gemini-2.5-flash'  # free tier (gemini-1.5-flash retired; 2.0-flash has no free quota on this key)

FORBIDDEN_KEYWORDS = {
    'DROP', 'DELETE', 'INSERT', 'UPDATE', 'CREATE',
    'ALTER', 'TRUNCATE', 'GRANT', 'REVOKE',
}
FORBIDDEN_TABLES = {
    'users', 'entity_memory', 'corrections', 'uploads', 'uploads_log',
}

SCHEMA_CONTEXT = """
You are a SQL expert for a personal finance app. Generate a single PostgreSQL SELECT query.

Schema:
  Table: transactions
  Columns:
    id               INTEGER  (primary key)
    user_id          INTEGER  (do NOT hardcode — it will be injected automatically)
    txn_date         DATE     (format YYYY-MM-DD; use txn_date, not date)
    entity_name      TEXT     (merchant / payee name)
    category         TEXT     (see categories below)
    amount           NUMERIC  (INR, always positive for debits)
    net_amount       NUMERIC  (amount after reimbursements)
    entity_type      TEXT     (merchant | person | platform)
    confidence_level TEXT     (high | medium | low)
    transaction_type TEXT     (debit | credit)
    is_reimbursed    BOOLEAN

  Categories: Food & Dining, Shopping, Transport, Utilities, Entertainment,
              Healthcare, Transfer / P2P, Rent, Education, ATM / Cash, Other

Rules:
  - Return ONLY a raw SQL SELECT statement — no markdown fences, no explanation
  - Use ILIKE for name/merchant searches (e.g. entity_name ILIKE '%swiggy%')
  - Use SUM(amount) for totals, AVG(amount) for averages
  - Use DATE_TRUNC('month', txn_date) for monthly grouping
  - Filter dates with txn_date (e.g. txn_date >= '2024-01-01')
  - Do NOT include WHERE user_id = ... — it is injected automatically
  - Do NOT include a LIMIT clause — it is added automatically
  - If the question cannot be answered from this schema, return exactly: INVALID
""".strip()


def get_ro_engine():
    """Lazy singleton read-only SQLAlchemy engine backed by AI_DB_URL."""
    global _ro_engine
    if _ro_engine is None:
        url = os.environ.get('AI_DB_URL')
        if not url:
            raise RuntimeError('AI_DB_URL environment variable is not set')
        _ro_engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=3,
            pool_recycle=300,
        )
    return _ro_engine


def _get_model() -> genai.GenerativeModel:
    """Configure the Gemini client once and return a model instance."""
    global _gemini_configured
    if not _gemini_configured:
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise RuntimeError(
                'GEMINI_API_KEY environment variable is not set. '
                'Get a free key at aistudio.google.com'
            )
        genai.configure(api_key=api_key)
        _gemini_configured = True
    return genai.GenerativeModel(_GEMINI_MODEL)


def _detect_intent(question: str) -> str:
    """
    Pure keyword match — no LLM call.
    Returns: 'subscription' | 'opinion' | 'sql'
    """
    q = question.lower()

    subscription_keywords = [
        'subscription', 'subscriptions', 'recurring', 'monthly services',
        'how much on subscriptions', 'subscription spend', 'streaming'
    ]

    opinion_keywords = [
        'what do you think', 'what do u think', 'opinion', 'how am i doing',
        'how are my finances', 'am i overspending', 'am i spending too much',
        'how is my spending', 'review my spending', 'analyse my spending',
        'analyze my spending', 'good or bad', 'should i cut', 'advice',
        'suggest', 'recommendation', 'what do you feel', 'wat do u think',
        'wat do you think',
        'things of', 'think of', 'is it fine', 'is this fine', 'too much',
        'too little', 'college student', 'for a student', 'for my age',
        'reasonable', 'is this normal', 'is it normal', 'normal spending',
        'rate my', 'evaluate my', 'how does my', 'how am i', 'how are my',
        'is my spending', 'spending habit', 'spending pattern', 'financial health',
        'doing well', 'doing good', 'saving enough', 'spend too', 'overspend',
        'where am i', 'what should', 'cut down', 'reduce spending', 'improve',
        'manage', 'budget', 'budgeting', 'how do i', 'how should i',
        'shall i', 'how much shall', 'what amount', 'tips', 'advice on',
        'help me', 'guide me', 'saving', 'save money', 'cut back',
        'financial plan', 'monthly budget', 'set a budget', 'allocate',
        'where should', 'what can i', 'how can i', 'could manage',
        'could i reduce', 'should i reduce', 'priority', 'necessities',
        'discretionary', 'essential', 'non essential'
    ]

    if any(k in q for k in subscription_keywords):
        return 'subscription'
    if any(k in q for k in opinion_keywords):
        return 'opinion'
    return 'sql'


def _handle_subscription_question(user_id: int, db_session) -> str:
    """Runs SubscriptionAuditor and returns a formatted answer. No LLM call needed."""
    try:
        from app.models import Transaction
        import pandas as pd

        txns = Transaction.query.filter_by(user_id=user_id).all()
        if not txns:
            return "No transaction data found to detect subscriptions."

        rows = [{
            'date': t.txn_date,
            'entity_name': t.entity_name,
            'amount': float(t.amount),
            'category': t.category,
            'transaction_type': t.transaction_type,
            'entity_type': t.entity_type,
        } for t in txns]
        df = pd.DataFrame(rows)

        from app.analytics.subscription_auditor import SubscriptionAuditor
        auditor = SubscriptionAuditor(df, min_occurrences=3)
        report = auditor.generate_report()

        subs = report.get('subscriptions', [])
        total_monthly = report['summary'].get('total_monthly_cost', 0)

        if not subs:
            return "No recurring subscriptions detected in your transaction history."

        lines = [f"You spend approximately ₹{total_monthly:,.0f}/month on subscriptions:"]
        for s in subs[:8]:  # cap at 8 to keep answer readable
            lines.append(f"• {s['entity']} — ₹{s['avg_amount']:,.0f} ({s['frequency']})")

        return "\n".join(lines)

    except Exception as e:
        return f"Could not compute subscription data: {str(e)}"


def _handle_opinion_question(question: str, user_id: int, gemini_model) -> str:
    """Pulls summary stats from DB, passes to LLM for narrative answer. One LLM call."""
    try:
        from app.models import Transaction
        import pandas as pd

        txns = Transaction.query.filter_by(
            user_id=user_id, transaction_type='debit'
        ).all()

        if not txns:
            return "No transaction data found to analyse."

        rows = [{
            'date': t.txn_date,
            'amount': float(t.amount),
            'category': t.category,
        } for t in txns]
        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])

        # Build summary stats
        total_spend = df['amount'].sum()
        months = max(((df['date'].max() - df['date'].min()).days / 30), 1)
        avg_monthly = total_spend / months
        top_categories = (
            df.groupby('category')['amount'].sum()
            .sort_values(ascending=False)
            .head(3)
        )
        top_cat_str = ', '.join(
            f"{cat} (₹{amt:,.0f})" for cat, amt in top_categories.items()
        )

        summary = (
            f"Total spend: ₹{total_spend:,.0f} over ~{months:.0f} months. "
            f"Avg monthly: ₹{avg_monthly:,.0f}. "
            f"Top 3 categories: {top_cat_str}."
        )

        prompt = (
            f"You are a personal finance assistant. "
            f"Based on this spending summary: {summary}\n\n"
            f"User asked: {question}\n\n"
            f"The user may be asking a follow-up question. Answer it using the spending summary provided. If they ask about budgeting or how to manage spending, give a specific suggested monthly budget breakdown based on their actual category totals. Use Indian Rupee formatting. Keep it to 3-4 sentences. Do not mention SQL or databases. "
        )

        response = gemini_model.generate_content(prompt)
        return response.text.strip()

    except google_exceptions.ResourceExhausted:
        return "Daily AI query limit reached. Try again tomorrow."

    except Exception as e:
        return f"Could not generate spending analysis: {str(e)}"


def generate_sql(question: str) -> str:
    """LLM Call 1 — converts a natural language question to a SQL SELECT.
    Returns the raw SQL string, or the literal string 'INVALID'."""
    model = _get_model()
    response = model.generate_content(SCHEMA_CONTEXT + "\n\n" + question)
    return response.text.strip()


def validate_sql(sql: str) -> tuple[bool, str]:
    """Returns (is_valid, reason).
    Blocks non-SELECT, dangerous DML/DDL keywords, and forbidden table access."""
    if not sql or sql.upper() == 'INVALID':
        return False, 'Question cannot be answered from transaction data'

    # Must start with SELECT (allow leading whitespace or a single open-paren for subqueries)
    cleaned = sql.strip().lstrip('(').lstrip()
    if not cleaned.upper().startswith('SELECT'):
        return False, 'Only SELECT queries are permitted'

    # Forbidden DML / DDL keywords
    tokens = set(re.findall(r'\b([A-Z_]+)\b', sql.upper()))
    hit = tokens & FORBIDDEN_KEYWORDS
    if hit:
        return False, f'Query contains forbidden operation: {", ".join(sorted(hit))}'

    # Forbidden tables — word-boundary match to avoid false positives
    for table in FORBIDDEN_TABLES:
        if re.search(rf'\b{re.escape(table)}\b', sql, re.IGNORECASE):
            return False, f'Access to table "{table}" is not permitted'

    return True, ''


def inject_user_id(sql: str, user_id: int) -> str:
    """Guarantee data isolation by forcing user_id = {uid} onto every query.
    user_id is always an int literal — no SQL injection risk.
    Also adds LIMIT 500 if the query has none."""
    uid = int(user_id)
    sql = sql.strip().rstrip(';').strip()

    # Replace an existing (possibly wrong) user_id filter
    if re.search(r'\buser_id\s*=\s*\S+', sql, re.IGNORECASE):
        sql = re.sub(
            r'\buser_id\s*=\s*\S+',
            f'user_id = {uid}',
            sql, count=1, flags=re.IGNORECASE,
        )
    elif re.search(r'\bWHERE\b', sql, re.IGNORECASE):
        # Prepend as first condition in the existing WHERE clause
        sql = re.sub(
            r'\bWHERE\b',
            f'WHERE user_id = {uid} AND',
            sql, count=1, flags=re.IGNORECASE,
        )
    else:
        # No WHERE at all — insert before GROUP BY / ORDER BY / HAVING / LIMIT or at end
        m = re.search(r'\b(GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT)\b', sql, re.IGNORECASE)
        if m:
            pos = m.start()
            sql = sql[:pos].rstrip() + f' WHERE user_id = {uid} ' + sql[pos:]
        else:
            sql = sql + f' WHERE user_id = {uid}'

    if not re.search(r'\bLIMIT\b', sql, re.IGNORECASE):
        sql += ' LIMIT 500'

    return sql


def execute_query(sql: str) -> list[dict]:
    """Run SQL on the read-only engine. Returns a list of row dicts."""
    engine = get_ro_engine()
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        return [dict(zip(columns, row)) for row in result.fetchall()]


def generate_answer(question: str, query_result: list[dict], sql: str) -> str:
    """LLM Call 2 — converts raw query rows into a friendly 1-3 sentence answer."""
    rows_preview = query_result[:20]
    result_text = '\n'.join(str(r) for r in rows_preview)
    if len(query_result) > 20:
        result_text += f'\n... ({len(query_result)} rows total)'

    system = (
        'You are a friendly personal finance assistant. '
        'Given a user question and the raw database result, write a concise 1-3 sentence answer. '
        'Format Indian Rupee amounts as ₹X,XX,XXX (Indian numbering system). '
        'Be specific — use the actual numbers from the result. '
        'Never mention SQL, databases, or technical details.'
    )
    user_content = (
        f'Question: {question}\n\n'
        f'Result ({len(query_result)} rows):\n{result_text}'
    )

    model = _get_model()
    response = model.generate_content(system + "\n\n" + user_content)
    return response.text.strip()


def run_query_pipeline(question: str, user_id: int) -> dict:
    """Main entry point for the /api/ai/query route.

    Runs the keyword intent pre-check first, then dispatches:
      - 'subscription' / 'opinion' → dedicated handlers (no SQL path)
      - 'sql'                      → the existing NL→SQL→answer pipeline, unchanged

    Returns a dict mirroring the route's previous inline response:
      success: {'status': 'success', 'answer': ..., 'row_count': N, 'sql': <sql|None>}
      error:   {'status': 'error', 'message': ...}
    The route decides the HTTP status code and whether to expose 'sql'.
    """
    intent = _detect_intent(question)

    if intent == 'subscription':
        from app import db
        answer = _handle_subscription_question(user_id, db.session)
        return {'status': 'success', 'answer': answer, 'row_count': 0, 'sql': None}

    if intent == 'opinion':
        answer = _handle_opinion_question(question, user_id, _get_model())
        return {'status': 'success', 'answer': answer, 'row_count': 0, 'sql': None}

    # intent == 'sql' — existing pipeline, unchanged
    try:
        raw_sql = generate_sql(question)

        is_valid, reason = validate_sql(raw_sql)
        if not is_valid:
            return {'status': 'error', 'message': reason}

        safe_sql = inject_user_id(raw_sql, user_id)
        rows = execute_query(safe_sql)
        answer = generate_answer(question, rows, safe_sql)

        return {'status': 'success', 'answer': answer, 'row_count': len(rows), 'sql': safe_sql}

    except google_exceptions.ResourceExhausted:
        return {
            'status': 'error',
            'message': "Daily AI query limit reached. Try again tomorrow — or ask about subscriptions/spending overview which don't use the AI quota."
        }
