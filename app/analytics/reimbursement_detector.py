"""
Reimbursement detection for transaction data.

Matching strategy (v4 — strict exact match):
  ─────────────────────────────────────────────────────────────────────
  A credit is treated as a refund for a debit only when ALL of the
  following hold:

    1. Credit amount == debit amount, within ₹1 (_HIGH_CONF_RUPEES).
    2. Same entity — normalized entity_name/merchant/description match.
    3. The debit's category is 'Shopping' (refunds = retail returns).
    4. The credit falls within a 60-day forward window of the debit.
    5. One-to-one — each credit offsets at most one debit.

  This is deliberately conservative: it trades recall (refunds that
  return under a different name are missed) for precision (no false
  positives from salary, P2P, interest, or unrelated credits — the
  problem the earlier amount-proximity matcher caused). Because criterion
  3 needs a 'category' column, the debit rows fed to the detector must be
  the categorized rows (see app/api/routes.py).

Expected input columns:
  Required        : date, amount, transaction_type (debit/credit)
  For criterion 3 : category (on debit rows)
  For criterion 2 : entity_name / merchant / description
"""

import pandas as pd

_MAX_DEBIT_AMOUNT   = 100_000.0   # ₹ — retained constant; not used by the strict matcher
_HIGH_CONF_RUPEES   = 1.0         # ≤ ₹1 difference → exact-amount tolerance


def _normalize_entity(row):
    """Lowercased, stripped best-available entity name for a row."""
    for col in ('entity_name', 'merchant', 'description'):
        val = str(row.get(col, '')).strip().lower()
        if val and val not in ('', 'nan', 'none'):
            return val
    return ''


class ReimbursementDetector:
    """
    Detect refund/reimbursement credits for debit transactions.

    Strict exact matching: same entity, exact amount (±₹1), debit
    category 'Shopping', 60-day forward window, one-to-one — see the
    module docstring for full rationale.
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
            # Criterion 3: only Shopping-category debits are eligible
            if str(debit.get('category', '')) != 'Shopping':
                continue

            debit_date   = debit['date']
            debit_amount = float(debit['amount'])
            debit_entity = _normalize_entity(debit)

            if pd.isna(debit_date) or debit_amount <= 0 or not debit_entity:
                continue

            window_end = debit_date + pd.Timedelta(days=60)

            # Strict candidate mask: unmatched + forward window + exact amount + same entity
            avail_mask   = ~credits_df.index.isin(matched_credit_idxs)
            date_mask    = (credits_df['date'] >= debit_date) & (credits_df['date'] <= window_end)
            amount_mask  = abs(credits_df['amount'] - debit_amount) <= _HIGH_CONF_RUPEES
            entity_mask  = credits_df.apply(
                lambda r: _normalize_entity(r) == debit_entity, axis=1
            )

            candidates = credits_df[
                avail_mask & date_mask & amount_mask & entity_mask
            ].sort_values('date')

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
            'window_days':         self.window_days,
            'match_strategy':      'exact-amount + same-entity + Shopping',
            'amount_tolerance_rs': _HIGH_CONF_RUPEES,
        }
        report['matched_pairs'] = matched_pairs
        return report
