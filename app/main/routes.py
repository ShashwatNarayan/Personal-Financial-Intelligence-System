import json
import pandas as pd
from flask import render_template, redirect, url_for
from flask_login import login_required, current_user

from app.main import main_bp


@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('landing.html')


@main_bp.route('/dashboard')
@login_required
def dashboard():
    from app.api.routes import get_user_transactions_df

    df = get_user_transactions_df(current_user.id)

    if df.empty:
        return render_template('dashboard/index.html',
            empty=True,
            avg_monthly_spend=0.0,
            total_spent=0.0,
            top_category='N/A',
            top_category_amount=0.0,
            subscription_count=0,
            sub_monthly_cost=0.0,
            subscriptions_json='[]',
            highest_growth_category='N/A',
            highest_growth_pct=0.0,
            highest_growth_amount=0.0,
            transactions=[],
        )

    total_spent = float(df['amount'].sum())

    cat_totals = df.groupby('category')['amount'].sum()
    top_category = cat_totals.idxmax() if not cat_totals.empty else 'N/A'
    top_category_amount = float(cat_totals.get(top_category, 0)) if top_category != 'N/A' else 0.0

    # Average monthly spend
    df_m = df.copy()
    df_m['month'] = df_m['date'].dt.to_period('M')
    monthly_totals = df_m.groupby('month')['amount'].sum()
    avg_monthly_spend = float(monthly_totals.mean()) if len(monthly_totals) > 0 else 0.0

    # Highest growth category (current month vs previous month)
    highest_growth_category = 'N/A'
    highest_growth_pct = 0.0
    highest_growth_amount = 0.0
    months_sorted = sorted(df_m['month'].unique())
    if len(months_sorted) >= 2:
        curr_m, prev_m = months_sorted[-1], months_sorted[-2]
        curr_cat = df_m[df_m['month'] == curr_m].groupby('category')['amount'].sum()
        prev_cat = df_m[df_m['month'] == prev_m].groupby('category')['amount'].sum()
        common = curr_cat.index.intersection(prev_cat.index)
        if not common.empty:
            growth = (curr_cat[common] - prev_cat[common]) / prev_cat[common].abs() * 100
            highest_growth_category = growth.idxmax()
            highest_growth_pct = float(growth.max())
            highest_growth_amount = float(curr_cat.get(highest_growth_category, 0))

    try:
        from app.analytics.subscription_auditor import SubscriptionAuditor
        sub_report = SubscriptionAuditor(df, min_occurrences=3).generate_report()
        subscription_count = sub_report['summary']['total_subscriptions']
        sub_monthly_cost = float(sub_report['summary'].get('total_monthly_cost', 0))
        subscriptions_json = json.dumps(sub_report.get('subscriptions', []))
    except Exception:
        subscription_count = 0
        sub_monthly_cost = 0.0
        subscriptions_json = '[]'

    transactions = df.sort_values('date', ascending=False).head(10).to_dict('records')
    for txn in transactions:
        d = txn.get('date')
        if isinstance(d, pd.Timestamp):
            txn['date'] = d.strftime('%Y-%m-%d')
        elif hasattr(d, 'strftime'):
            txn['date'] = d.strftime('%Y-%m-%d')

    return render_template('dashboard/index.html',
        empty=False,
        avg_monthly_spend=avg_monthly_spend,
        total_spent=total_spent,
        top_category=top_category,
        top_category_amount=top_category_amount,
        subscription_count=subscription_count,
        sub_monthly_cost=sub_monthly_cost,
        subscriptions_json=subscriptions_json,
        highest_growth_category=highest_growth_category,
        highest_growth_pct=highest_growth_pct,
        highest_growth_amount=highest_growth_amount,
        transactions=transactions,
    )


@main_bp.route('/upload')
@login_required
def upload():
    return render_template('dashboard/upload.html')
