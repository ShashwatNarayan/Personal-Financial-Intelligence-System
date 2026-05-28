import hashlib
import os
import pandas as pd
from datetime import datetime

from flask import jsonify, request
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.api import api_bp
from app.analytics.bank_detector import detect_bank, get_parser
from app.analytics.categorization import SmartCategorizer
from app.models import Correction, EntityMemory, Transaction, UploadLog


def compute_fingerprint(user_id, date, description, amount):
    """Stable MD5 hash of (user_id, date, description, amount) for dedup."""
    date_str = str(date)[:10] if date is not None else ''
    desc_str = str(description or '').lower().strip()
    amt_str = f"{float(amount or 0):.2f}"
    key = f"{user_id}|{date_str}|{desc_str}|{amt_str}"
    return hashlib.md5(key.encode('utf-8')).hexdigest()


def get_user_transactions_df(user_id, months=None):
    """
    Single source of truth: load a user's transactions from DB into a DataFrame.
    Returns empty DataFrame with correct columns if no data.
    """
    query = Transaction.query.filter_by(user_id=user_id)
    if months:
        from dateutil.relativedelta import relativedelta
        cutoff = datetime.now() - relativedelta(months=months)
        query = query.filter(Transaction.txn_date >= cutoff)
    rows = query.all()
    if not rows:
        return pd.DataFrame(columns=[
            'id', 'date', 'description', 'merchant', 'entity_name', 'amount',
            'net_amount', 'transaction_type', 'category', 'entity_type',
            'confidence_level', 'is_reimbursed', 'upload_id',
        ])
    return pd.DataFrame([{
        'id': t.id,
        'date': pd.Timestamp(t.txn_date),
        'description': t.description or '',
        'merchant': t.entity_name or '',
        'entity_name': t.entity_name or '',
        'amount': float(t.amount) if t.amount else 0.0,
        'net_amount': float(t.amount) if t.amount else 0.0,
        'transaction_type': t.transaction_type or '',
        'category': t.category or '',
        'entity_type': t.entity_type or '',
        'confidence_level': t.confidence_level or 'medium',
        'is_reimbursed': bool(t.is_reimbursed),
        'upload_id': t.upload_id,
    } for t in rows])


@api_bp.route('/upload-excel', methods=['POST'])
@login_required
def upload_excel():
    try:
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'No file selected'}), 400

        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'status': 'error', 'message': 'Please upload an Excel file'}), 400

        temp_path = 'temp_upload.xlsx'
        file.save(temp_path)
        print(f"\n  Uploaded: {file.filename}")

        # S-0: Duplicate file check (fast path — exact re-upload)
        with open(temp_path, 'rb') as fh:
            file_hash = hashlib.sha256(fh.read()).hexdigest()

        existing_upload = UploadLog.query.filter_by(
            user_id=current_user.id,
            file_hash=file_hash,
        ).first()
        if existing_upload:
            os.remove(temp_path)
            return jsonify({
                'status': 'error',
                'message': (
                    f'This exact file was already uploaded on '
                    f'{existing_upload.uploaded_at.strftime("%d %b %Y")}. '
                    f'No changes made.'
                ),
            }), 409

        # S-1: Detect bank and parse statement
        print("Step 1: Detecting bank and parsing Excel...")
        bank = detect_bank(temp_path)
        print(f"   Bank detected: {bank.upper()}")

        parser, validator = get_parser(bank)
        df = parser.parse(temp_path)

        if not validator.validate(df):
            return jsonify({
                'status': 'error',
                'message': 'Validation failed: ' + ', '.join(validator.errors)
            }), 400

        # S-2: Filter to expenses only
        print("Step 2: Filtering to debit transactions...")
        df_expenses = df[df['transaction_type'] == 'debit'].copy()
        print(f"   Found {len(df_expenses)} expense transactions")

        # S-3: Categorize
        print("Step 3: Categorizing transactions...")
        categorizer = SmartCategorizer(user_id=current_user.id)
        df_expenses = categorizer.categorize_dataframe(df_expenses)
        print(f"   Entity resolution:")
        print(f"   - Platforms: {len(df_expenses[df_expenses['entity_type'] == 'platform'])}")
        print(f"   - Persons: {len(df_expenses[df_expenses['entity_type'] == 'person'])}")
        print(f"   - Merchants: {len(df_expenses[df_expenses['entity_type'] == 'merchant'])}")
        stats = categorizer.get_category_stats(df_expenses)
        print(
            f"   Confidence: High={stats['high_confidence_count']}, "
            f"Med={stats['medium_confidence_count']}, "
            f"Low={stats['low_confidence_count']}"
        )

        # Detect reimbursements
        print("Detecting reimbursements...")
        from app.analytics.reimbursement_detector import ReimbursementDetector
        detector = ReimbursementDetector(df_expenses, window_days=14)
        reimbursement_report = detector.generate_full_report()
        df_expenses = detector.df
        print(f"      Total reimbursed: ₹{reimbursement_report['summary']['total_reimbursed']:,.0f}")
        print(f"      Reimbursed transactions: {reimbursement_report['reimbursements']['reimbursed_transactions']}")
        print(f"      Full: {reimbursement_report['reimbursements']['full_reimbursements']}, "
              f"Partial: {reimbursement_report['reimbursements']['partial_reimbursements']}")

        # Detect anomalies
        print("  Detecting spending anomalies...")
        from app.analytics.anomaly_detector import AnomalyDetector
        anomaly_detector = AnomalyDetector(df_expenses, threshold=2.0, min_months=3)
        anomaly_report = anomaly_detector.generate_report()
        if anomaly_report['summary']['total_anomalies'] > 0:
            print(f"   ⚠️  {anomaly_report['summary']['total_anomalies']} anomalies detected")
        else:
            print("    No significant anomalies")

        # Audit subscriptions
        print("   Auditing recurring subscriptions...")
        from app.analytics.subscription_auditor import SubscriptionAuditor
        sub_auditor = SubscriptionAuditor(df_expenses, min_occurrences=3)
        sub_report = sub_auditor.generate_report()
        if sub_report['summary']['total_subscriptions'] > 0:
            print(f"      {sub_report['summary']['total_subscriptions']} subscriptions detected")
            print(f"      Est. monthly cost: ₹{sub_report['summary']['total_monthly_cost']:,.0f}")
            if sub_report['summary']['increasing_cost'] > 0:
                print(f"      ⚠️  {sub_report['summary']['increasing_cost']} with cost increases")
        else:
            print("    No recurring subscriptions detected")

        # S-4: Persist to database (with row-level deduplication)
        print("Step 4: Saving to database...")

        # Pre-load all fingerprints already stored for this user (one query)
        existing_fps = set(
            fp for (fp,) in db.session.query(Transaction.fingerprint)
            .filter(Transaction.user_id == current_user.id)
            .filter(Transaction.fingerprint.isnot(None))
            .all()
        )

        upload = UploadLog(
            user_id=current_user.id,
            filename=secure_filename(file.filename),
            bank_detected=bank,
            row_count=0,       # updated below once we know how many are new
            file_hash=file_hash,
        )
        db.session.add(upload)
        db.session.flush()  # get upload.id before inserting rows

        new_count = 0
        skipped_count = 0
        for _, row in df_expenses.iterrows():
            fp = compute_fingerprint(
                current_user.id,
                row['date'],
                row.get('description', ''),
                row.get('amount', 0),
            )
            if fp in existing_fps:
                skipped_count += 1
                continue
            existing_fps.add(fp)  # guard against intra-batch duplicates

            txn = Transaction(
                user_id=current_user.id,
                upload_id=upload.id,
                fingerprint=fp,
                txn_date=row['date'],
                description=str(row.get('description', '')),
                entity_name=str(row.get('entity_name', row.get('merchant', ''))),
                amount=float(row.get('amount', 0)),
                transaction_type=str(row.get('transaction_type', 'debit')),
                category=str(row.get('category', 'Other')),
                entity_type=str(row.get('entity_type', '')),
                confidence_level=str(row.get('confidence_level', 'medium')),
                is_reimbursed=bool(row.get('is_reimbursed', False)),
            )
            db.session.add(txn)
            new_count += 1

        upload.row_count = new_count
        db.session.commit()
        print(f"    Saved {new_count} new transactions, skipped {skipped_count} duplicates (upload_id={upload.id})")

        if new_count == 0:
            return jsonify({
                'status': 'info',
                'message': (
                    f'All {skipped_count} transactions in this file already exist in your history. '
                    f'Nothing new was added.'
                ),
                'upload_id': upload.id,
                'new_count': 0,
                'skipped_count': skipped_count,
            }), 200

        # S-5: Calculate summary statistics from in-memory df
        print(" Step 5: Calculating statistics...")
        min_date = df_expenses['date'].min()
        max_date = df_expenses['date'].max()
        days = (max_date - min_date).days + 1
        months = days / 30.44

        spend_col = 'net_amount' if 'net_amount' in df_expenses.columns else 'amount'
        total_spent = df_expenses[spend_col].sum()
        avg_monthly = total_spent / months if months > 0 else total_spent

        # MoM drift
        if len(df_expenses) > 0 and months >= 2:
            df_mom = df_expenses.copy()
            df_mom['year_month'] = df_mom['date'].dt.to_period('M')
            monthly_totals = df_mom.groupby('year_month')['amount'].sum().sort_index()
            if len(monthly_totals) >= 2:
                current_month_spend = monthly_totals.iloc[-1]
                prev_month_spend = monthly_totals.iloc[-2]
                mom_change = current_month_spend - prev_month_spend
                mom_pct = (mom_change / prev_month_spend * 100) if prev_month_spend > 0 else 0
                if mom_pct > 0:
                    mom_drift_value = f"+{mom_pct:.1f}%"
                    mom_trend = f"₹{mom_change:,.0f} higher than last month"
                else:
                    mom_drift_value = f"{mom_pct:.1f}%"
                    mom_trend = f"₹{abs(mom_change):,.0f} lower than last month"
            else:
                mom_drift_value = "N/A"
                mom_trend = "Need 2+ months"
        else:
            mom_drift_value = "N/A"
            mom_trend = "No data"

        category_spend = df_expenses.groupby('category')['amount'].sum().sort_values(ascending=False)
        fixed_categories = ['Entertainment', 'Utilities', 'Rent', 'Education']
        fixed_total = category_spend[category_spend.index.isin(fixed_categories)].sum()
        variable_total = category_spend[~category_spend.index.isin(fixed_categories)].sum()

        print(f"     Total: ₹{total_spent:,.0f} over {months:.1f} months")
        print(f"     Average monthly: ₹{avg_monthly:,.0f}")

        if os.path.exists(temp_path):
            os.remove(temp_path)

        skip_note = f' ({skipped_count} duplicates skipped)' if skipped_count else ''
        return jsonify({
            'status': 'success',
            'message': f'Added {new_count} new transactions over {months:.1f} months{skip_note}',
            'upload_id': upload.id,
            'new_count': new_count,
            'skipped_count': skipped_count,
            'data': {
                'metrics': {
                    'total_monthly_spend': {
                        'value': f"₹{avg_monthly:,.0f}",
                        'label': 'Average Monthly Spend',
                        'sublabel': f"{len(df_expenses)} transactions"
                    },
                    'fixed_expenses': {
                        'value': f"₹{fixed_total / months:,.0f}",
                        'label': 'Fixed Expenses',
                        'sublabel': f"{len([c for c in fixed_categories if c in category_spend])} categories"
                    },
                    'variable_expenses': {
                        'value': f"₹{variable_total / months:,.0f}",
                        'label': 'Variable Expenses',
                        'sublabel': f"{len(category_spend) - len([c for c in fixed_categories if c in category_spend])} categories"
                    },
                    'mom_drift': {
                        'value': mom_drift_value,
                        'label': 'Month-over-Month',
                        'sublabel': mom_trend
                    }
                },
                'category_breakdown': [
                    {
                        'category': cat,
                        'type': 'Fixed' if cat in fixed_categories else 'Variable',
                        'monthly_avg': f"₹{amount / months:,.0f}",
                        'percentage': f"{amount / total_spent * 100:.1f}%"
                    }
                    for cat, amount in category_spend.items()
                ],
                'anomalies': [
                    {
                        'category': anom['category'],
                        'amount': f"₹{anom['current_spend']:,.0f}",
                        'z_score': f"{anom['z_score']:.1f}",
                        'explanation': anom['explanation']
                    }
                    for anom in anomaly_report['anomalies'][:5]
                ] if anomaly_report['summary']['total_anomalies'] > 0 else [],
                'action_items': []
            }
        })

    except Exception as e:
        print(f" Error: {str(e)}")
        import traceback
        traceback.print_exc()
        if os.path.exists('temp_upload.xlsx'):
            os.remove('temp_upload.xlsx')
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Error processing file: {str(e)}'}), 400


@api_bp.route('/transactions/classified', methods=['GET'])
@login_required
def get_transactions():
    df = get_user_transactions_df(current_user.id)
    if df.empty:
        return jsonify({
            'status': 'error',
            'message': 'No data available. Upload a statement first.'
        }), 400

    try:
        transactions = []
        for _, row in df.iterrows():
            transactions.append({
                'txn_id': str(int(row['id'])),
                'date': str(row['date'])[:10],
                'merchant': str(row.get('entity_name', row.get('merchant', 'Unknown'))),
                'description': str(row.get('description', ''))[:60],
                'amount': float(row['amount']),
                'net_amount': float(row.get('net_amount', row['amount'])),
                'category': str(row['category']),
                'entity_type': str(row.get('entity_type', 'unknown')),
                'confidence_level': str(row.get('confidence_level', 'medium')),
                'transaction_type': 'debit',
                'confidence': 1.0,
                'is_reimbursement': bool(row.get('is_reimbursed', False)),
                'is_reimbursed': bool(row.get('is_reimbursed', False)),
                'reimbursed_amount': 0.0,
                'is_reimbursement_credit': False,
                'needs_review': False,
            })

        print(f" Returning {len(transactions)} transactions for drill-down")
        return jsonify({
            'status': 'success',
            'transactions': transactions,
            'count': len(transactions)
        })

    except Exception as e:
        print(f" Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Error: {str(e)}'}), 500


@api_bp.route('/transactions/needs-review', methods=['GET'])
@login_required
def get_needs_review():
    df = get_user_transactions_df(current_user.id)
    if df.empty:
        return jsonify({'status': 'error', 'message': 'No data'}), 400

    try:
        if 'confidence_level' not in df.columns:
            return jsonify({'status': 'success', 'transactions': [], 'count': 0})

        low_conf = df[df['confidence_level'] == 'low']
        transactions = []
        for _, row in low_conf.iterrows():
            transactions.append({
                'txn_id': str(int(row['id'])),
                'date': str(row['date'])[:10],
                'merchant': str(row.get('entity_name', row.get('merchant', 'Unknown'))),
                'description': str(row.get('description', ''))[:60],
                'amount': float(row['amount']),
                'net_amount': float(row.get('net_amount', row['amount'])),
                'category': str(row['category']),
                'entity_type': str(row.get('entity_type', 'unknown')),
                'confidence_level': str(row.get('confidence_level', 'medium')),
                'transaction_type': 'debit',
                'confidence': 1.0,
                'is_reimbursement': bool(row.get('is_reimbursed', False)),
                'is_reimbursed': bool(row.get('is_reimbursed', False)),
                'reimbursed_amount': 0.0,
                'is_reimbursement_credit': False,
                'needs_review': True,
            })

        print(f"Found {len(transactions)} low-confidence transactions")
        return jsonify({
            'status': 'success',
            'transactions': transactions,
            'count': len(transactions)
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@api_bp.route('/transactions/correct', methods=['POST'])
@login_required
def correct_transaction():
    try:
        data = request.get_json()
        # Accept both transaction_id (new) and txn_id (legacy) so existing frontend keeps working
        txn_id = data.get('transaction_id') or data.get('txn_id')
        new_category = data.get('new_category')

        if not txn_id or not new_category:
            return jsonify({'status': 'error', 'message': 'Missing transaction_id or new_category'}), 400

        txn = Transaction.query.filter_by(
            id=int(txn_id),
            user_id=current_user.id,
        ).first_or_404()

        entity_name = txn.entity_name or ''
        entity_type = txn.entity_type or 'unknown'
        old_category = txn.category

        # Log correction for audit trail
        correction = Correction(
            user_id=current_user.id,
            transaction_id=txn.id,
            entity_name=entity_name,
            old_category=old_category,
            new_category=new_category,
        )
        db.session.add(correction)

        # Update ALL transactions for same entity + user
        updated_count = Transaction.query.filter_by(
            user_id=current_user.id,
            entity_name=entity_name,
        ).update({'category': new_category})

        # Upsert EntityMemory row in DB
        # Note: EntityMemory is the SQLAlchemy model; JsonEntityMemory is the JSON-backed class
        mem = EntityMemory.query.filter_by(
            user_id=current_user.id,
            entity_name=entity_name,
        ).first()
        if mem:
            mem.category = new_category
            mem.confidence = 1.0
            mem.correction_count += 1
            mem.updated_at = datetime.utcnow()
        else:
            mem = EntityMemory(
                user_id=current_user.id,
                entity_name=entity_name,
                category=new_category,
                entity_type=entity_type,
                confidence=1.0,
                correction_count=1,
            )
            db.session.add(mem)

        db.session.commit()

        print(f"   User correction: {entity_name} → {new_category}")
        print(f"   Updated {updated_count} transactions")

        # Recalculate aggregates from DB for response
        df = get_user_transactions_df(current_user.id)
        total_spent = df['amount'].sum()
        category_spend = df.groupby('category')['amount'].sum().sort_values(ascending=False)
        min_date = df['date'].min()
        max_date = df['date'].max()
        days = (max_date - min_date).days + 1
        months = days / 30.44

        return jsonify({
            'status': 'success',
            'message': f'Updated {entity_name} to {new_category}',
            'updated_count': updated_count,
            'aggregates': {
                'category_breakdown': [
                    {
                        'category': cat,
                        'monthly_avg': f"₹{amount / months:,.0f}",
                        'percentage': f"{amount / total_spent * 100:.1f}%"
                    }
                    for cat, amount in category_spend.items()
                ]
            }
        })

    except Exception as e:
        db.session.rollback()
        print(f" Correction error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Error: {str(e)}'}), 500


@api_bp.route('/insights/temporal', methods=['GET'])
@login_required
def get_temporal_insights():
    df = get_user_transactions_df(current_user.id)
    if df.empty:
        return jsonify({
            'status': 'error',
            'message': 'No data available. Upload a statement first.'
        }), 400

    try:
        from app.analytics.temporal_insights import TemporalInsights
        analyzer = TemporalInsights(df)
        report = analyzer.generate_full_report()

        print(f"\n Temporal Insights Generated:")
        print(f"   Months available: {report['data_quality']['months_available']}")
        print(f"   MoM changes: {len(report['mom_changes'])} categories")
        print(f"   Fastest growing: {report['fastest_growing']['category'] if report['fastest_growing'] else 'None'}")
        print(f"   Acceleration flags: {len(report['acceleration_flags'])} categories")

        return jsonify({'status': 'success', 'insights': report})

    except Exception as e:
        print(f" Temporal insights error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Error generating insights: {str(e)}'}), 500


@api_bp.route('/reimbursements/report', methods=['GET'])
@login_required
def get_reimbursement_report():
    df = get_user_transactions_df(current_user.id)
    if df.empty:
        return jsonify({'status': 'error', 'message': 'No data'}), 400

    try:
        from app.analytics.reimbursement_detector import ReimbursementDetector
        detector = ReimbursementDetector(df, window_days=14)
        report = detector.generate_full_report()

        print(f"   Reimbursement report generated:")
        print(f"   Gross: ₹{report['summary']['gross_spend']:,.0f}")
        print(f"   Net: ₹{report['summary']['net_spend']:,.0f}")
        print(f"   Reimbursed: ₹{report['summary']['total_reimbursed']:,.0f}")

        return jsonify({'status': 'success', 'report': report})

    except Exception as e:
        print(f"  Reimbursement error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@api_bp.route('/anomalies/report', methods=['GET'])
@login_required
def get_anomaly_report():
    df = get_user_transactions_df(current_user.id)
    if df.empty:
        return jsonify({'status': 'error', 'message': 'No data'}), 400

    try:
        from app.analytics.anomaly_detector import AnomalyDetector
        detector = AnomalyDetector(df, threshold=2.0, min_months=3)
        report = detector.generate_report()

        print(f"   Anomaly report generated:")
        print(f"   Total: {report['summary']['total_anomalies']}")
        print(f"   Critical: {report['summary'].get('critical', 0)}")
        print(f"   High: {report['summary'].get('high', 0)}")

        return jsonify({'status': 'success', 'report': report})

    except Exception as e:
        print(f"  Anomaly detection error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@api_bp.route('/subscriptions/audit', methods=['GET'])
@login_required
def get_subscription_audit():
    df = get_user_transactions_df(current_user.id)
    if df.empty:
        return jsonify({'status': 'error', 'message': 'No data'}), 400

    try:
        from app.analytics.subscription_auditor import SubscriptionAuditor
        auditor = SubscriptionAuditor(df, min_occurrences=3)
        report = auditor.generate_report()

        print(f"   Subscription audit:")
        print(f"   Total: {report['summary']['total_subscriptions']}")
        print(f"   Monthly: ₹{report['summary']['total_monthly_cost']:,.0f}")

        return jsonify({'status': 'success', 'report': report})

    except Exception as e:
        print(f"  Subscription audit error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


@api_bp.route('/corrections/summary', methods=['GET'])
@login_required
def get_corrections_summary():
    """Return a summary of this user's manual corrections — proves the feedback loop is working."""
    try:
        total = Correction.query.filter_by(user_id=current_user.id).count()
        recent = (
            Correction.query
            .filter_by(user_id=current_user.id)
            .order_by(Correction.created_at.desc())
            .limit(20)
            .all()
        )

        return jsonify({
            'status': 'success',
            'total_corrections': total,
            'recent': [
                {
                    'entity_name': c.entity_name,
                    'old_category': c.old_category,
                    'new_category': c.new_category,
                    'created_at': c.created_at.isoformat() if c.created_at else None,
                }
                for c in recent
            ]
        })

    except Exception as e:
        print(f"  Corrections summary error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500
