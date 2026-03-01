"""
Temporal Insights Module
Analyzes spending trends over time with MoM changes, growth patterns, and acceleration flags
"""

import pandas as pd
from datetime import datetime


class TemporalInsights:
    """Time-aware analysis for transaction data"""

    def __init__(self, df):
        """
        Initialize with transaction DataFrame
        Expected columns: date, category, amount
        """
        self.df = df.copy()
        self._prepare_data()

    def _prepare_data(self):
        """Prepare data for temporal analysis"""
        # Ensure date is datetime
        if not pd.api.types.is_datetime64_any_dtype(self.df['date']):
            self.df['date'] = pd.to_datetime(self.df['date'])

        # Create year_month column (YYYY-MM)
        self.df['year_month'] = self.df['date'].dt.to_period('M').astype(str)

    def get_data_quality(self):
        """Check data quality and return metadata"""
        months = self.df['year_month'].nunique()
        min_date = self.df['date'].min()
        max_date = self.df['date'].max()

        warning = None
        if months < 6:
            warning = f"Limited data ({months} months). Insights improve with 6+ months."

        return {
            'months_available': months,
            'date_range': {
                'start': min_date.strftime('%Y-%m-%d'),
                'end': max_date.strftime('%Y-%m-%d')
            },
            'warning': warning
        }

    def get_monthly_aggregation(self):
        """
        Create base monthly aggregation table
        Returns: DataFrame with [category, year_month, total_spend]
        """
        monthly = self.df.groupby(['category', 'year_month'])['amount'].agg([
            ('total_spend', 'sum'),
            ('transaction_count', 'count')
        ]).reset_index()

        return monthly

    def calculate_mom_changes(self):
        """
        Calculate month-over-month changes for each category
        Returns: List of MoM change dictionaries
        """
        monthly = self.get_monthly_aggregation()

        # Filter categories with sufficient data (5+ transactions per month avg)
        category_counts = monthly.groupby('category')['transaction_count'].mean()
        valid_categories = category_counts[category_counts >= 5].index.tolist()

        monthly = monthly[monthly['category'].isin(valid_categories)]

        # Sort by category and month
        monthly = monthly.sort_values(['category', 'year_month'])

        # Calculate MoM changes
        mom_changes = []

        for category in monthly['category'].unique():
            cat_data = monthly[monthly['category'] == category].sort_values('year_month')

            if len(cat_data) < 2:
                continue  # Need at least 2 months

            # Get last 2 months
            current = cat_data.iloc[-1]
            previous = cat_data.iloc[-2]

            change_amount = current['total_spend'] - previous['total_spend']

            # Handle division by zero
            if previous['total_spend'] > 0:
                change_percent = (change_amount / previous['total_spend']) * 100
            else:
                change_percent = 100 if change_amount > 0 else 0

            # Create explanation
            direction = "increased" if change_amount > 0 else "decreased"
            explanation = f"{category} {direction} by ₹{abs(change_amount):,.0f} ({abs(change_percent):.0f}%) vs last month"

            mom_changes.append({
                'category': category,
                'current_month': current['year_month'],
                'previous_month': previous['year_month'],
                'current_spend': float(current['total_spend']),
                'previous_spend': float(previous['total_spend']),
                'change_amount': float(change_amount),
                'change_percent': float(change_percent),
                'explanation': explanation
            })

        # Sort by absolute change amount (descending)
        mom_changes.sort(key=lambda x: abs(x['change_amount']), reverse=True)

        return mom_changes

    def get_fastest_growing_category(self):
        """
        Identify category with highest MoM percentage increase
        Returns: Dictionary with fastest growing category info
        """
        mom_changes = self.calculate_mom_changes()

        if not mom_changes:
            return None

        # Filter only positive growth
        growing = [c for c in mom_changes if c['change_percent'] > 0]

        if not growing:
            return None

        # Get highest percentage growth
        fastest = max(growing, key=lambda x: x['change_percent'])

        # Cap display at 999%
        display_percent = min(fastest['change_percent'], 999)

        return {
            'category': fastest['category'],
            'change_percent': float(fastest['change_percent']),
            'change_amount': float(fastest['change_amount']),
            'current_spend': float(fastest['current_spend']),
            'previous_spend': float(fastest['previous_spend']),
            'explanation': f"{fastest['category']} grew {display_percent:.0f}% MoM (fastest growing category)"
        }

    def detect_acceleration(self, threshold=1.3):
        """
        Detect categories with accelerating spending

        Args:
            threshold: Multiplier for trailing average (default 1.3 = 30% above avg)

        Returns: List of flagged categories
        """
        monthly = self.get_monthly_aggregation()

        # Filter categories with sufficient data
        category_counts = monthly.groupby('category')['transaction_count'].mean()
        valid_categories = category_counts[category_counts >= 5].index.tolist()

        monthly = monthly[monthly['category'].isin(valid_categories)]

        acceleration_flags = []

        for category in monthly['category'].unique():
            cat_data = monthly[monthly['category'] == category].sort_values('year_month')

            if len(cat_data) < 4:
                continue  # Need at least 4 months (1 current + 3 trailing)

            # Get current month
            current_spend = cat_data.iloc[-1]['total_spend']

            # Get trailing 2-3 months average (excluding current)
            trailing_months = min(3, len(cat_data) - 1)
            trailing_data = cat_data.iloc[-(trailing_months + 1):-1]
            trailing_avg = trailing_data['total_spend'].mean()

            # Check if current exceeds threshold
            if trailing_avg > 0:
                ratio = current_spend / trailing_avg

                if ratio > threshold:
                    percent_above = (ratio - 1) * 100

                    acceleration_flags.append({
                        'category': category,
                        'current_spend': float(current_spend),
                        'trailing_avg': float(trailing_avg),
                        'ratio': float(ratio),
                        'percent_above_avg': float(percent_above),
                        'explanation': f"{category} spending {percent_above:.0f}% above recent average"
                    })

        # Sort by percent above average (descending)
        acceleration_flags.sort(key=lambda x: x['percent_above_avg'], reverse=True)

        return acceleration_flags

    def generate_full_report(self):
        """
        Generate complete temporal insights report
        Returns: Dictionary with all insights
        """
        return {
            'data_quality': self.get_data_quality(),
            'mom_changes': self.calculate_mom_changes(),
            'fastest_growing': self.get_fastest_growing_category(),
            'acceleration_flags': self.detect_acceleration()
        }