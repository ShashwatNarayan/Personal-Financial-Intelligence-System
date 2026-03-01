"""
Reimbursement detection for transaction data.

Expected input columns:
- date
- amount
Optional columns:
- transaction_type (debit/credit)
- description / merchant / entity_name
"""

import pandas as pd


class ReimbursementDetector:
    """Detect reimbursements and compute net spend."""

    def __init__(self, df, window_days=14):
        self.window_days = int(window_days)
        self.df = df.copy()
        self._prepare_data()

    def _prepare_data(self):
        """Normalize schema and initialize reimbursement columns."""
        if 'date' in self.df.columns and not pd.api.types.is_datetime64_any_dtype(self.df['date']):
            self.df['date'] = pd.to_datetime(self.df['date'], errors='coerce')

        if 'amount' in self.df.columns:
            self.df['amount'] = pd.to_numeric(self.df['amount'], errors='coerce').fillna(0.0)
            # Keep spend amounts positive for consistent net calculations.
            self.df['amount'] = self.df['amount'].abs()
        else:
            self.df['amount'] = 0.0

        if 'transaction_type' not in self.df.columns:
            # Upload flow currently passes only debits.
            self.df['transaction_type'] = 'debit'

        if 'net_amount' not in self.df.columns:
            self.df['net_amount'] = self.df['amount'].astype(float)
        else:
            self.df['net_amount'] = pd.to_numeric(self.df['net_amount'], errors='coerce').fillna(self.df['amount'])

        if 'is_reimbursed' not in self.df.columns:
            self.df['is_reimbursed'] = False

        if 'reimbursed_amount' not in self.df.columns:
            self.df['reimbursed_amount'] = 0.0
        else:
            self.df['reimbursed_amount'] = pd.to_numeric(self.df['reimbursed_amount'], errors='coerce').fillna(0.0)

        if 'is_reimbursement_credit' not in self.df.columns:
            self.df['is_reimbursement_credit'] = False

    def _detect_reimbursements(self):
        """
        Match future credits against debits in a rolling window.
        If no credits are present (current upload flow), this becomes a no-op.
        """
        if self.df.empty:
            return

        debits_mask = self.df['transaction_type'].astype(str).str.lower() == 'debit'
        credits_mask = self.df['transaction_type'].astype(str).str.lower() == 'credit'

        if not credits_mask.any() or not debits_mask.any():
            # Keep net_amount aligned even when no matches are possible.
            self.df.loc[debits_mask, 'net_amount'] = self.df.loc[debits_mask, 'amount']
            return

        credits = self.df.loc[credits_mask, ['date', 'amount']].copy().sort_values('date')
        debits = self.df.loc[debits_mask, ['date', 'amount']].copy().sort_values('date')

        remaining_credit = {idx: float(row['amount']) for idx, row in credits.iterrows()}

        for debit_idx, debit in debits.iterrows():
            debit_date = debit['date']
            debit_amount = float(debit['amount'])
            if pd.isna(debit_date) or debit_amount <= 0:
                continue

            window_end = debit_date + pd.Timedelta(days=self.window_days)
            candidate_credit_idxs = credits[
                (credits['date'] >= debit_date) &
                (credits['date'] <= window_end)
            ].index.tolist()

            reimbursed = 0.0
            for credit_idx in candidate_credit_idxs:
                available = remaining_credit.get(credit_idx, 0.0)
                if available <= 0:
                    continue

                needed = debit_amount - reimbursed
                if needed <= 0:
                    break

                applied = min(available, needed)
                reimbursed += applied
                remaining_credit[credit_idx] = available - applied

                if applied > 0:
                    self.df.at[credit_idx, 'is_reimbursement_credit'] = True

            if reimbursed > 0:
                self.df.at[debit_idx, 'reimbursed_amount'] = float(reimbursed)
                self.df.at[debit_idx, 'is_reimbursed'] = True
                self.df.at[debit_idx, 'net_amount'] = float(max(debit_amount - reimbursed, 0.0))
            else:
                self.df.at[debit_idx, 'net_amount'] = float(debit_amount)

    def _build_summary(self):
        debits = self.df[self.df['transaction_type'].astype(str).str.lower() == 'debit']

        gross_spend = float(debits['amount'].sum()) if not debits.empty else 0.0
        total_reimbursed = float(debits.get('reimbursed_amount', pd.Series(dtype=float)).sum()) if not debits.empty else 0.0
        net_spend = float(debits.get('net_amount', pd.Series(dtype=float)).sum()) if not debits.empty else 0.0

        reimbursed_txn_count = int((debits.get('reimbursed_amount', 0) > 0).sum()) if not debits.empty else 0
        full_reimbursements = int((debits.get('net_amount', 0).round(2) == 0).sum()) if not debits.empty else 0
        partial_reimbursements = max(reimbursed_txn_count - full_reimbursements, 0)

        return {
            'summary': {
                'gross_spend': gross_spend,
                'net_spend': net_spend,
                'total_reimbursed': total_reimbursed,
            },
            'reimbursements': {
                'reimbursed_transactions': reimbursed_txn_count,
                'full_reimbursements': full_reimbursements,
                'partial_reimbursements': partial_reimbursements,
            }
        }

    def generate_full_report(self):
        """Run reimbursement detection and return report payload."""
        self._detect_reimbursements()

        # Ensure derived fields are numeric after processing.
        self.df['reimbursed_amount'] = pd.to_numeric(self.df['reimbursed_amount'], errors='coerce').fillna(0.0)
        self.df['net_amount'] = pd.to_numeric(self.df['net_amount'], errors='coerce').fillna(self.df['amount'])

        report = self._build_summary()
        report['config'] = {
            'window_days': self.window_days
        }
        return report
