"""
Anomaly Detection Module
Detects monthly spending anomalies per category using z-score method
"""

import pandas as pd
import numpy as np


class AnomalyDetector:
    """Detect spending anomalies at category-month level"""

    def __init__(self, df, threshold=2.0, min_months=3):
        """
        Args:
            df: Transaction DataFrame with date, category, net_amount
            threshold: Z-score threshold (default 2.0 = ~95% confidence)
            min_months: Minimum months of history required (default 3)
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
        Detect anomalies using z-score method
        Returns: List of anomaly dictionaries
        """
        anomalies = []

        for category in self.monthly['category'].unique():
            cat_data = self.monthly[self.monthly['category'] == category].sort_values('year_month')

            # Skip if insufficient history
            if len(cat_data) < self.min_months:
                continue

            # Get current (most recent) month
            current_month = cat_data.iloc[-1]
            current_spend = current_month['spend']
            current_ym = current_month['year_month']

            # Get baseline (all previous months)
            if len(cat_data) == self.min_months:
                # If exactly min_months, use all but current
                baseline = cat_data.iloc[:-1]['spend']
            else:
                # Use all previous months
                baseline = cat_data.iloc[:-1]['spend']

            # Skip if baseline too small
            if len(baseline) < 2:
                continue

            # Calculate baseline statistics
            baseline_mean = baseline.mean()
            baseline_std = baseline.std()

            # Skip if no variation (std = 0)
            if baseline_std == 0:
                continue

            # Calculate z-score
            z_score = (current_spend - baseline_mean) / baseline_std

            # Flag if exceeds threshold
            if abs(z_score) >= self.threshold:
                # Determine type
                if z_score > 0:
                    anomaly_type = 'spike'
                    direction = 'higher'
                else:
                    anomaly_type = 'drop'
                    direction = 'lower'

                # Calculate deviation percentage
                deviation_pct = ((current_spend - baseline_mean) / baseline_mean) * 100

                # Generate explanation
                explanation = self._generate_explanation(
                    category, current_spend, baseline_mean,
                    deviation_pct, direction, z_score
                )

                anomalies.append({
                    'category': category,
                    'month': current_ym,
                    'current_spend': float(current_spend),
                    'baseline_mean': float(baseline_mean),
                    'baseline_std': float(baseline_std),
                    'z_score': float(z_score),
                    'deviation_percent': float(deviation_pct),
                    'anomaly_type': anomaly_type,
                    'severity': self._get_severity(abs(z_score)),
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