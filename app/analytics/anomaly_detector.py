"""
detects monthly spending anomalies per category using z-score method
"""

import pandas as pd
import numpy as np


class AnomalyDetector:
    """Detect spending anomalies at category-month level"""

    def __init__(self, df, threshold=2.0, min_months=3):
        """
        Args:
            df: Transaction Dataframe with date, category, net_amount
            threshold: Z-score threshold
            min_months: minimum 3 months of history required
        """
        self.df = df.copy()
        self.threshold = threshold
        self.min_months = min_months
        self._prepare_data()

    def _prepare_data(self):
        """Prepare monthly aggregation"""
        if not pd.api.types.is_datetime64_any_dtype(self.df['date']):
            self.df['date'] = pd.to_datetime(self.df['date'])

        self.df['year_month'] = self.df['date'].dt.to_period('M').astype(str)

        # Aggregate by category and month
        self.monthly = self.df.groupby(['category', 'year_month'])['net_amount'].sum().reset_index()
        self.monthly.columns = ['category', 'year_month', 'spend']

    def detect_anomalies(self):
        """
        Detect anomalies using a rolling-window z-score method.

        Every month (from the ROLLING_WINDOW-th onward) is tested against the
        immediately-preceding ROLLING_WINDOW months as its baseline, so
        historical anomalies are detected and a long history no longer inflates
        the baseline std. Multiple flagged months in the same category are all
        kept — they are genuinely distinct events.

        Returns: List of anomaly dictionaries
        """
        ROLLING_WINDOW = 3  # months of prior history to use as baseline

        anomalies = []

        for category in self.monthly['category'].unique():
            cat_data = (
                self.monthly[self.monthly['category'] == category]
                .sort_values('year_month')
                .reset_index(drop=True)
            )

            # Skip if insufficient history
            if len(cat_data) < self.min_months:
                continue

            # Test each month starting from index ROLLING_WINDOW onward
            for i in range(ROLLING_WINDOW, len(cat_data)):
                current_row = cat_data.iloc[i]
                baseline = cat_data.iloc[max(0, i - ROLLING_WINDOW):i]['spend']

                # Skip if baseline too small
                if len(baseline) < 2:
                    continue

                baseline_mean = baseline.mean()
                baseline_std = baseline.std()

                # Skip if no variation (std = 0)
                if baseline_std == 0:
                    continue

                z_score = (current_row['spend'] - baseline_mean) / baseline_std

                # Ignore statistically significant but financially trivial
                # anomalies (e.g. a category that doubled from ₹50 to ₹100).
                MIN_ABSOLUTE_DIFF = 1000  # ₹
                abs_diff = abs(current_row['spend'] - baseline_mean)
                if abs_diff < MIN_ABSOLUTE_DIFF:
                    continue

                # Flag if exceeds threshold
                if abs(z_score) >= self.threshold:
                    # Plain-language explanation for the dashboard. The z-score
                    # stays in the returned dict (used for sorting/severity and
                    # available to logs) but is deliberately kept OUT of the
                    # user-facing string — non-technical users shouldn't see raw
                    # statistics or "3-month avg" jargon.
                    month_label = pd.Period(
                        current_row['year_month'], freq='M'
                    ).strftime('%b %Y')  # "2025-11" -> "Nov 2025"
                    direction_word = 'high' if z_score > 0 else 'low'
                    explanation = (
                        f"{category} spending was unusually {direction_word} in "
                        f"{month_label} — ₹{current_row['spend']:,.0f} vs your "
                        f"typical ₹{baseline_mean:,.0f}/month"
                    )

                    anomalies.append({
                        'category': category,
                        'month': current_row['year_month'],
                        'actual_spend': float(current_row['spend']),
                        'expected_spend': float(baseline_mean),
                        'z_score': float(z_score),
                        'anomaly_type': 'spike' if z_score > 0 else 'drop',
                        'severity': 'critical' if abs(z_score) >= 3.0
                                    else 'high' if abs(z_score) >= 2.5
                                    else 'moderate',
                        'explanation': explanation
                    })

        # Sort by absolute z-score (most significant first)
        anomalies.sort(key=lambda x: abs(x['z_score']), reverse=True)

        return anomalies

    def _generate_explanation(self, category, current, baseline, deviation_pct, direction, z_score):
        """Generate human-readable explanation"""
        severity = self._get_severity(abs(z_score))

        if severity == 'critical':
            severity_word = 'significantly'
        elif severity == 'high':
            severity_word = 'notably'
        else:
            severity_word = 'moderately'

        explanation = (
            f"{category} spending is {severity_word} {direction} than usual. "
            f"Current: ₹{current:,.0f}, Baseline: ₹{baseline:,.0f} "
            f"({abs(deviation_pct):.0f}% {direction})"
        )

        return explanation

    def _get_severity(self, abs_z_score):
        """Determine anomaly severity"""
        if abs_z_score >= 3.0:
            return 'critical'
        elif abs_z_score >= 2.5:
            return 'high'
        else:
            return 'moderate'

    def get_summary(self):
        """Get summary statistics"""
        anomalies = self.detect_anomalies()

        if not anomalies:
            return {
                'total_anomalies': 0,
                'categories_affected': 0,
                'spikes': 0,
                'drops': 0
            }

        return {
            'total_anomalies': len(anomalies),
            'categories_affected': len(set(a['category'] for a in anomalies)),
            'spikes': len([a for a in anomalies if a['anomaly_type'] == 'spike']),
            'drops': len([a for a in anomalies if a['anomaly_type'] == 'drop']),
            'critical': len([a for a in anomalies if a['severity'] == 'critical']),
            'high': len([a for a in anomalies if a['severity'] == 'high']),
            'moderate': len([a for a in anomalies if a['severity'] == 'moderate'])
        }

    def generate_report(self):
        """Generate complete anomaly report"""
        anomalies = self.detect_anomalies()
        summary = self.get_summary()

        return {
            'summary': summary,
            'anomalies': anomalies,
            'metadata': {
                'threshold': self.threshold,
                'min_months_required': self.min_months,
                'total_categories_analyzed': self.monthly['category'].nunique(),
                'total_months': self.monthly['year_month'].nunique()
            }
        }