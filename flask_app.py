"""
Personal Financial Intelligence System - SIMPLE STABLE VERSION
Core features only: Upload → Parse → Categorize → Display → Drill-down
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import os

from src.bank_statement_parser import HDFCStatementParser, BankStatementValidator
from src.categorization import SmartCategorizer

app = Flask(__name__, template_folder='templates')
CORS(app)

# Global state
current_data = None


# ===== ROUTES =====

@app.route('/')
def landing():
    """Serve the landing page"""
    return render_template('landing.html')

@app.route('/dashboard')
def dashboard():
    """Serve the dashboard"""
    return render_template('dashboard.html')


@app.route('/upload')
def upload_page():
    """Redirect to upload tab in dashboard"""
    return render_template('dashboard.html')


@app.route('/api/upload-excel', methods=['POST'])
def upload_excel():
    """
    Handle HDFC Excel statement upload - SIMPLIFIED VERSION
    """
    global current_data

    try:
        # Validate file upload
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'No file selected'}), 400

        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'status': 'error', 'message': 'Please upload an Excel file'}), 400

        # Save file temporarily
        temp_path = 'temp_upload.xlsx'
        file.save(temp_path)
        print(f"\n📊 Uploaded: {file.filename}")

        # STEP 1: Parse HDFC statement
        print("🔄 Step 1: Parsing Excel...")
        parser = HDFCStatementParser()
        df = parser.parse(temp_path)

        # Validate
        validator = BankStatementValidator()
        if not validator.validate(df):
            return jsonify({
                'status': 'error',
                'message': 'Validation failed: ' + ', '.join(validator.errors)
            }), 400

        # STEP 2: Filter to expenses only
        print("🔄 Step 2: Filtering to debit transactions...")
        df_expenses = df[df['transaction_type'] == 'debit'].copy()
        print(f"   Found {len(df_expenses)} expense transactions")

        # STEP 3: Simple categorization (keyword-based)
        print("🔄 Step 3: Categorizing transactions...")
        categorizer = SmartCategorizer()
        df_expenses = categorizer.categorize_dataframe(df_expenses)
        # Store entity information
        print(f"   Entity resolution:")
        print(f"   - Platforms: {len(df_expenses[df_expenses['entity_type'] == 'platform'])}")
        print(f"   - Persons: {len(df_expenses[df_expenses['entity_type'] == 'person'])}")
        print(f"   - Merchants: {len(df_expenses[df_expenses['entity_type'] == 'merchant'])}")

        # Show confidence stats
        stats = categorizer.get_category_stats(df_expenses)
        print(
            f"   Confidence: High={stats['high_confidence_count']}, "
            f"Med={stats['medium_confidence_count']}, "
            f"Low={stats['low_confidence_count']}"
        )
        # Detect reimbursements
        print("🔄 Detecting reimbursements...")
        from src.reimbursement_detector import ReimbursementDetector

        detector = ReimbursementDetector(df_expenses, window_days=14)
        reimbursement_report = detector.generate_full_report()

        # Update current_data with reimbursement flags
        current_data = detector.df
        df_expenses = current_data

        print(f"   ✅ Reimbursement detection complete:")
        print(f"      Total reimbursed: ₹{reimbursement_report['summary']['total_reimbursed']:,.0f}")
        print(f"      Reimbursed transactions: {reimbursement_report['reimbursements']['reimbursed_transactions']}")
        print(f"      Full: {reimbursement_report['reimbursements']['full_reimbursements']}, "
              f"Partial: {reimbursement_report['reimbursements']['partial_reimbursements']}")

        # Detect anomalies
        print("🔍 Detecting spending anomalies...")
        from src.anomaly_detector import AnomalyDetector

        anomaly_detector = AnomalyDetector(current_data, threshold=2.0, min_months=3)
        anomaly_report = anomaly_detector.generate_report()

        if anomaly_report['summary']['total_anomalies'] > 0:
            print(f"   ⚠️  {anomaly_report['summary']['total_anomalies']} anomalies detected")
        else:
            print("   ✅ No significant anomalies")

        # STEP 4: Store in global state
        current_data = df_expenses
        print(f"   ✅ Stored {len(current_data)} transactions in memory")

        # STEP 5: Calculate summary statistics
        print("🔄 Step 4: Calculating statistics...")

        # Date range
        min_date = df_expenses['date'].min()
        max_date = df_expenses['date'].max()
        days = (max_date - min_date).days + 1
        months = days / 30.44

        # Total spend
        total_spent = current_data['net_amount'].sum()
        avg_monthly = total_spent / months if months > 0 else total_spent

        # Category breakdown
        category_spend = df_expenses.groupby('category')['amount'].sum().sort_values(ascending=False)

        # Fixed vs Variable (simple heuristic)
        fixed_categories = ['Entertainment', 'Utilities', 'Rent', 'Education']
        fixed_total = category_spend[category_spend.index.isin(fixed_categories)].sum()
        variable_total = category_spend[~category_spend.index.isin(fixed_categories)].sum()

        print(f"   💰 Total: ₹{total_spent:,.0f} over {months:.1f} months")
        print(f"   🗓 Average monthly: ₹{avg_monthly:,.0f}")

        # Clean up
        if os.path.exists(temp_path):
            os.remove(temp_path)

        # STEP 6: Return formatted response
        return jsonify({
            'status': 'success',
            'message': f'Processed {len(df_expenses)} transactions over {months:.1f} months',
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
                        'value': 'N/A',
                        'label': 'Month-over-Month',
                        'sublabel': f'{months:.1f} months of data'
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
                    for anom in anomaly_report['anomalies'][:5]  # Top 5
                ] if anomaly_report['summary']['total_anomalies'] > 0 else [],
                'action_items': []  # Simplified: no action items
            }
        })

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

        if os.path.exists('temp_upload.xlsx'):
            os.remove('temp_upload.xlsx')

        return jsonify({
            'status': 'error',
            'message': f'Error processing file: {str(e)}'
        }), 400


@app.route('/api/transactions/classified', methods=['GET'])
def get_transactions():
    """
    Return all transactions for drill-down modal
    """
    global current_data

    if current_data is None or len(current_data) == 0:
        return jsonify({
            'status': 'error',
            'message': 'No data available. Upload a statement first.'
        }), 400

    try:
        transactions = []

        for idx, row in current_data.iterrows():
            transactions.append({
                'txn_id': str(idx),
                'date': str(row['date'])[:10],
                'merchant': str(row.get('entity_name', row.get('merchant', 'Unknown'))),
                'description': str(row.get('description', ''))[:60],
                'amount': float(row['amount']),
                'net_amount': float(row.get('net_amount', row['amount'])),
                'category': str(row['category']),
                'entity_type': str(row.get('entity_type', 'unknown')),
                'confidence_level': str(row.get('confidence_level', 'medium')),  # ← ADD THIS
                'transaction_type': 'debit',
                'confidence': 1.0,
                'is_reimbursement': bool(row.get('is_reimbursed', False)),
                'is_reimbursed': bool(row.get('is_reimbursed', False)),
                'reimbursed_amount': float(row.get('reimbursed_amount', 0)),
                'is_reimbursement_credit': bool(row.get('is_reimbursement_credit', False)),
                'needs_review': False,
            })

        print(f"📤 Returning {len(transactions)} transactions for drill-down")

        return jsonify({
            'status': 'success',
            'transactions': transactions,
            'count': len(transactions)
        })

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500


@app.route('/api/transactions/needs-review', methods=['GET'])
def get_needs_review():
    """Get transactions that need user review (low confidence)"""
    global current_data

    if current_data is None or len(current_data) == 0:
        return jsonify({'status': 'error', 'message': 'No data'}), 400

    try:
        if 'confidence_level' not in current_data.columns:
            return jsonify({
                'status': 'success',
                'transactions': [],
                'count': 0
            })

        # Filter low confidence transactions
        low_conf = current_data[current_data['confidence_level'] == 'low']

        transactions = []
        for idx, row in low_conf.iterrows():
            transactions.append({
                'txn_id': str(idx),
                'date': str(row['date'])[:10],
                'merchant': str(row.get('entity_name', row.get('merchant', 'Unknown'))),
                'description': str(row.get('description', ''))[:60],
                'amount': float(row['amount']),
                'net_amount': float(row.get('net_amount', row['amount'])),
                'category': str(row['category']),
                'entity_type': str(row.get('entity_type', 'unknown')),
                'confidence_level': str(row.get('confidence_level', 'medium')),  # ← ADD THIS
                'transaction_type': 'debit',
                'confidence': 1.0,
                'is_reimbursement': bool(row.get('is_reimbursed', False)),
                'is_reimbursed': bool(row.get('is_reimbursed', False)),
                'reimbursed_amount': float(row.get('reimbursed_amount', 0)),
                'is_reimbursement_credit': bool(row.get('is_reimbursement_credit', False)),
                'needs_review': False,
            })

        print(f"Found {len(transactions)} low-confidence transactions")

        return jsonify({
            'status': 'success',
            'transactions': transactions,
            'count': len(transactions)
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/transactions/correct', methods=['POST'])
def correct_transaction():
    """Handle user correction of transaction category"""
    global current_data

    try:
        data = request.get_json()
        txn_id = data.get('txn_id')
        new_category = data.get('new_category')

        if not txn_id or not new_category:
            return jsonify({'status': 'error', 'message': 'Missing txn_id or new_category'}), 400

        if current_data is None or len(current_data) == 0:
            return jsonify({'status': 'error', 'message': 'No data loaded'}), 400

        # Find transaction
        txn_idx = int(txn_id)
        if txn_idx not in current_data.index:
            return jsonify({'status': 'error', 'message': 'Transaction not found'}), 404

        # Get transaction details
        txn = current_data.loc[txn_idx]
        entity_name = txn.get('entity_name', 'Unknown')
        entity_type = txn.get('entity_type', 'unknown')

        # Update in memory with user source
        from src.entity_memory import EntityMemory
        memory = EntityMemory()
        memory.store(entity_name, new_category, entity_type, source='user')

        # Update current DataFrame
        current_data.loc[txn_idx, 'category'] = new_category

        # Update ALL transactions with same entity
        matching_mask = current_data['entity_name'] == entity_name
        current_data.loc[matching_mask, 'category'] = new_category

        # Recalculate aggregates
        total_spent = current_data['amount'].sum()
        category_spend = current_data.groupby('category')['amount'].sum().sort_values(ascending=False)

        min_date = current_data['date'].min()
        max_date = current_data['date'].max()
        days = (max_date - min_date).days + 1
        months = days / 30.44

        print(f"✅ User correction: {entity_name} → {new_category}")
        print(f"   Updated {matching_mask.sum()} transactions")

        return jsonify({
            'status': 'success',
            'message': f'Updated {entity_name} to {new_category}',
            'updated_count': int(matching_mask.sum()),
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
        print(f"❌ Correction error: {str(e)}")
        import traceback
        traceback.print_exc()

        return jsonify({
            'status': 'error',
            'message': f'Error: {str(e)}'
        }), 500


# ========================================
# ADD TO flask_app.py - After /api/transactions/correct endpoint
# ========================================

@app.route('/api/insights/temporal', methods=['GET'])
def get_temporal_insights():
    """Get time-aware spending insights (MoM, trends, acceleration)"""
    global current_data

    if current_data is None or len(current_data) == 0:
        return jsonify({
            'status': 'error',
            'message': 'No data available. Upload a statement first.'
        }), 400

    try:
        from src.temporal_insights import TemporalInsights

        # Create insights analyzer
        analyzer = TemporalInsights(current_data)

        # Generate full report
        report = analyzer.generate_full_report()

        print(f"\n📈 Temporal Insights Generated:")
        print(f"   Months available: {report['data_quality']['months_available']}")
        print(f"   MoM changes: {len(report['mom_changes'])} categories")
        print(f"   Fastest growing: {report['fastest_growing']['category'] if report['fastest_growing'] else 'None'}")
        print(f"   Acceleration flags: {len(report['acceleration_flags'])} categories")

        return jsonify({
            'status': 'success',
            'insights': report
        })

    except Exception as e:
        print(f"❌ Temporal insights error: {str(e)}")
        import traceback
        traceback.print_exc()

        return jsonify({
            'status': 'error',
            'message': f'Error generating insights: {str(e)}'
        }), 500

@app.route('/api/reimbursements/report', methods=['GET'])
def get_reimbursement_report():
    """Get detailed reimbursement analysis"""
    global current_data

    if current_data is None or len(current_data) == 0:
        return jsonify({'status': 'error', 'message': 'No data'}), 400

    try:
        from src.reimbursement_detector import ReimbursementDetector

        detector = ReimbursementDetector(current_data, window_days=14)
        report = detector.generate_full_report()

        print(f"📊 Reimbursement report generated:")
        print(f"   Gross: ₹{report['summary']['gross_spend']:,.0f}")
        print(f"   Net: ₹{report['summary']['net_spend']:,.0f}")
        print(f"   Reimbursed: ₹{report['summary']['total_reimbursed']:,.0f}")

        return jsonify({
            'status': 'success',
            'report': report
        })

    except Exception as e:
        print(f"❌ Reimbursement error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/anomalies/report', methods=['GET'])
def get_anomaly_report():
    """Get detected spending anomalies"""
    global current_data

    if current_data is None or len(current_data) == 0:
        return jsonify({'status': 'error', 'message': 'No data'}), 400

    try:
        from src.anomaly_detector import AnomalyDetector

        detector = AnomalyDetector(current_data, threshold=2.0, min_months=3)
        report = detector.generate_report()

        print(f"📊 Anomaly report generated:")
        print(f"   Total: {report['summary']['total_anomalies']}")
        print(f"   Critical: {report['summary'].get('critical', 0)}")
        print(f"   High: {report['summary'].get('high', 0)}")

        return jsonify({
            'status': 'success',
            'report': report
        })

    except Exception as e:
        print(f"❌ Anomaly detection error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500
# ===== ERROR HANDLERS =====

@app.errorhandler(404)
def not_found(e):
    return jsonify({'status': 'error', 'message': 'Endpoint not found'}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({'status': 'error', 'message': 'Server error'}), 500


# ===== MAIN =====

if __name__ == '__main__':
    print("=" * 60)
    print("💰 Personal Financial Intelligence System - SIMPLE VERSION")
    print("=" * 60)
    print("🚀 Starting Flask server...")
    print("📊 Dashboard: http://localhost:5000")
    print("=" * 60)
    print("\n✨ Features in this version:")
    print("  ✅ Upload HDFC Excel statements")
    print("  ✅ Automatic categorization (keyword-based)")
    print("  ✅ Monthly spending averages")
    print("  ✅ Fixed vs Variable expenses")
    print("  ✅ Interactive category drill-down")
    print("\n🚫 Removed complex features:")
    print("  ❌ Entity store / memory")
    print("  ❌ Confidence scoring")
    print("  ✅ Reimbursement detection")
    print("  ❌ Human-in-the-loop feedback")
    print("\n💡 Add these back incrementally once this works!\n")
    print("=" * 60)

    # Create folders
    for folder in ['templates', 'data']:
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"✅ Created {folder}/ folder")

    # Run Flask
    app.run(
        debug=True,
        host='localhost',
        port=5000,
        use_reloader=True
    )

