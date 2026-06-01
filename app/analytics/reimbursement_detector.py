"""
Reimbursement detection for transaction data.

Matching strategy (v3 — amount-proximity, no entity-name requirement):
  ─────────────────────────────────────────────────────────────────────
  Indian bank refunds almost never arrive under the same entity name as
  the original debit.  A Nike purchase via UPI returns as "RAZORPAY
  SETTLEMENTS", "NEFT CR", "PAYTM REFUND", or a plain bank credit with
  no recognisable merchant.  Matching on entity name therefore misses
  virtually all real refunds.

  Instead, we match purely on amount proximity within a 60-day forward
  window, subject to four guard-rails that suppress false positives:

    1. The credit must fall within 60 days of the debit (forward only).
    2. The credit amount must be within 5% of the debit amount.
    3. Each credit can offset at most one debit (one-to-one).
    4. Credits where entity_type == 'person' are excluded — salary
       credits and peer-to-peer transfers must not be treated as refunds.
    5. Debits >= ₹1,00,000 are excluded — large transfers are almost
       certainly not retail refunds.

  When multiple credits qualify for a debit the closest one in time is
  preferred.  Confidence is 'high' when credit ≈ debit within ₹1,
  otherwise 'medium'.

Expected input columns:
  Required : date, amount
  Optional : transaction_type (debit/credit), entity_type,
             entity_name / merchant / description
"""

import pandas as pd

_MAX_DEBIT_AMOUNT   = 100_000.0   # ₹ — skip amounts this large
_TOLERANCE_PCT      = 0.05        # 5 % proximity band
_HIGH_CONF_RUPEES   = 1.0         # ≤ ₹1 difference → high confidence


class ReimbursementDetector:
    """
    Detect refund/reimbursement credits for debit transactions.

    Matching is based entirely on amount proximity within a rolling
    forward window.  Entity names are never compared — see module
    docstring for full rationale.
    """

    def __init__(self, df, window_days=60):
        self.window_days = int(window_days)
        self.df = df.copy()
        self._prepare_data()

    # ── Schema normalisation ─────────────────────────────────────────

    def _prepare_data(self):
        """Normalise column types and initialise reimbursement fields."""
        if 'date' in self.df.columns and not pd.api.types.is_datetime64_any_dtype(self.df['date']):
            self.df['date'] = pd.to_datetime(self.df['date'], errors='coerce')

        if 'amount' in self.df.columns:
            self.df['amount'] = pd.to_numeric(self.df['amount'], errors='coerce').fillna(0.0).abs()
        else:
            self.df['amount'] = 0.0

        if 'transaction_type' not in self.df.columns:
            self.df['transaction_type'] = 'debit'

        if 'net_amount' not in self.df.columns:
            self.df['net_amount'] = self.df['amount'].astype(float)
        else:
            self.df['net_amount'] = (
                pd.to_numeric(self.df['net_amount'], errors='coerce')
                .fillna(self.df['amount'])
            )

        for col, default in [
            ('is_reimbursed',         False),
            ('is_reimbursement_credit', False),
        ]:
            if col not in self.df.columns:
                self.df[col] = default

        if 'reimbursed_amount' not in self.df.columns:
            self.df['reimbursed_amount'] = 0.0
        else:
            self.df['reimbursed_amount'] = (
                pd.to_numeric(self.df['reimbursed_amount'], errors='coerce').fillna(0.0)
            )

    # ── Helpers ──────────────────────────────────────────────────────

    def _get_entity(self, row):
        """Return the best available display name for a transaction row."""
        for col in ('entity_name', 'merchant', 'description'):
            val = row.get(col, None)
            if val and str(val).strip() not in ('', 'nan', 'NaN', 'None'):
                return str(val).strip()
        return 'Unknown'

    @staticmethod
    def _is_person_credit(row):
        """Return True if the credit looks like a P2P/salary transfer."""
        return str(row.get('entity_type', '')).lower() == 'person'

    @staticmethod
    def _confidence(debit_amount, credit_amount):
        """'high' if amounts match within ₹1, else 'medium'."""
        return 'high' if abs(debit_amount - credit_amount) <= _HIGH_CONF_RUPEES else 'medium'

    # ── Core matching ─────────────────────────────────────────────────

    def _detect_reimbursements(self):
        """
        Match forward credits to debits by amount proximity.

        Returns:
            list[dict] — matched_pairs for the report (may be empty).
        """
        if self.df.empty:
            return []

        type_col    = self.df['transaction_type'].astype(str).str.lower()
        debits_mask = type_col == 'debit'
        credits_mask = type_col == 'credit'

        if not credits_mask.any() or not debits_mask.any():
            return []

        credits_df = self.df.loc[credits_mask].copy().sort_values('date')
        debits_df  = self.df.loc[debits_mask].copy().sort_values('date')

        matched_credit_idxs: set = set()
        matched_pairs: list      = []

        for debit_idx, debit in debits_df.iterrows():
            debit_date   = debit['date']
            debit_amount = float(debit['amount'])

            # Guard-rail 5: skip very large debits
            if pd.isna(debit_date) or debit_amount <= 0 or debit_amount >= _MAX_DEBIT_AMOUNT:
                continue

            window_end = debit_date + pd.Timedelta(days=self.window_days)
            tolerance  = debit_amount * _TOLERANCE_PCT

            # Build candidate mask — amount proximity + date window
            avail_mask   = ~credits_df.index.isin(matched_credit_idxs)
            date_mask    = (credits_df['date'] >= debit_date) & (credits_df['date'] <= window_end)
            amount_mask  = abs(credits_df['amount'] - debit_amount) <= tolerance

            candidates = credits_df[avail_mask & date_mask & amount_mask].sort_values('date')

            # Guard-rail 4: skip person credits (salary, P2P)
            candidates = candidates[
                ~candidates.apply(self._is_person_credit, axis=1)
            ]

            if candidates.empty:
                continue

            best_idx    = candidates.index[0]
            best_credit = candidates.iloc[0]
            credit_amt  = float(best_credit['amount'])

            matched_credit_idxs.add(best_idx)

            self.df.at[debit_idx, 'is_reimbursed']           = True
            self.df.at[debit_idx, 'reimbursed_amount']        = credit_amt
            self.df.at[debit_idx, 'net_amount']               = max(debit_amount - credit_amt, 0.0)
            self.df.at[best_idx,  'is_reimbursement_credit']  = True

            matched_pairs.append({
                'debit_date':    str(debit_date.date()),
                'debit_entity':  self._get_entity(debit),
                'debit_amount':  debit_amount,
                'credit_date':   str(best_credit['date'].date()),
                'credit_entity': self._get_entity(best_credit),
                'credit_amount': credit_amt,
                'days_between':  int((best_credit['date'] - debit_date).days),
                'confidence':    self._confidence(debit_amount, credit_amt),
            })

        return matched_pairs

    # ── Summary ───────────────────────────────────────────────────────

    def _build_summary(self):
        debits = self.df[self.df['transaction_type'].astype(str).str.lower() == 'debit']

        gross_spend      = float(debits['amount'].sum())                                   if not debits.empty else 0.0
        total_reimbursed = float(debits.get('reimbursed_amount', pd.Series(dtype=float)).sum()) if not debits.empty else 0.0
        net_spend        = float(debits.get('net_amount',         pd.Series(dtype=float)).sum()) if not debits.empty else 0.0

        reimbursed_txn_count   = int((debits.get('reimbursed_amount', 0) > 0).sum())          if not debits.empty else 0
        full_reimbursements    = int((debits.get('net_amount', 0).round(2) == 0).sum())        if not debits.empty else 0
        partial_reimbursements = max(reimbursed_txn_count - full_reimbursements, 0)

        return {
            'summary': {
                'gross_spend':      gross_spend,
                'net_spend':        net_spend,
                'total_reimbursed': total_reimbursed,
            },
            'reimbursements': {
                'reimbursed_transactions': reimbursed_txn_count,
                'full_reimbursements':     full_reimbursements,
                'partial_reimbursements':  partial_reimbursements,
            },
        }

    # ── Public API ────────────────────────────────────────────────────

    def generate_full_report(self):
        """Run detection and return the full report payload."""
        matched_pairs = self._detect_reimbursements()

        # Final type normalisation after in-place updates
        self.df['reimbursed_amount'] = (
            pd.to_numeric(self.df['reimbursed_amount'], errors='coerce').fillna(0.0)
        )
        self.df['net_amount'] = (
            pd.to_numeric(self.df['net_amount'], errors='coerce').fillna(self.df['amount'])
        )

        report = self._build_summary()
        report['config'] = {
            'window_days':          self.window_days,
            'amount_tolerance_pct': int(_TOLERANCE_PCT * 100),
            'max_debit_amount':     _MAX_DEBIT_AMOUNT,
        }
        report['matched_pairs'] = matched_pairs
        return report
