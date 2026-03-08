"""
Subscription Auditor Module
Detects recurring subscription-like transactions
"""

import pandas as pd
from datetime import timedelta
from collections import defaultdict


class SubscriptionAuditor:
    """Detect and audit recurring subscriptions"""

    def __init__(self, df, min_occurrences=3, amount_tolerance=0.15):
        """
        Args:
            df: Transaction DataFrame with date, entity_name, amount, category
            min_occurrences: Minimum occurrences to consider (default 3)
            amount_tolerance: Amount variance tolerance (default 15%)
        """
        self.df = df.copy()
        self.min_occurrences = min_occurrences
        self.amount_tolerance = amount_tolerance

        # Subscription-heavy categories (expanded to include Shopping for app stores)
        self.subscription_categories = [
            'Entertainment', 'Utilities', 'Services', 'Shopping',
            'Healthcare', 'Education', 'Other'
        ]

        self._prepare_data()

    def _prepare_data(self):
        """Prepare and filter data"""
        if not pd.api.types.is_datetime64_any_dtype(self.df['date']):
            self.df['date'] = pd.to_datetime(self.df['date'])

        # Filter to debits only
        self.df = self.df[self.df['transaction_type'] == 'debit']

        # Filter to subscription categories
        self.df = self.df[self.df['category'].isin(self.subscription_categories)]

        # Filter out P2P (persons)
        self.df = self.df[self.df.get('entity_type', 'unknown') != 'person']

        # Sort by entity and date
        self.df = self.df.sort_values(['entity_name', 'date'])

    def detect_subscriptions(self):
        """
        Detect recurring subscriptions
        Returns: List of subscription dictionaries
        """
        subscriptions = []

        # Group by entity
        for entity in self.df['entity_name'].unique():
            if entity == 'Unknown':
                continue

            entity_txns = self.df[self.df['entity_name'] == entity]

            # Need at least min_occurrences
            if len(entity_txns) < self.min_occurrences:
                continue

            # Check if multiple subscription tiers exist (e.g., Google Play ₹89 + ₹130)
            # Group by similar amounts
            amount_groups = self._group_by_similar_amounts(entity_txns)

            # Analyze each amount group separately
            for amount_key, group_txns in amount_groups.items():
                if len(group_txns) < self.min_occurrences:
                    continue

                result = self._analyze_entity(entity, group_txns, amount_tier=amount_key)

                if result:
                    subscriptions.append(result)

        # Sort by total cost (highest first)
        subscriptions.sort(key=lambda x: x['total_cost'], reverse=True)

        return subscriptions

    def _group_by_similar_amounts(self, txns):
        """
        Group transactions by similar amounts (for multi-tier subscriptions)
        Returns: Dict of {amount_key: DataFrame}
        """
        from collections import defaultdict

        amount_groups = defaultdict(list)

        for idx, txn in txns.iterrows():
            amount = txn['amount']

            # Find existing group with similar amount
            matched = False
            for existing_amt in amount_groups.keys():
                if abs(amount - existing_amt) / existing_amt <= self.amount_tolerance:
                    amount_groups[existing_amt].append(idx)
                    matched = True
                    break

            # Create new group
            if not matched:
                amount_groups[amount].append(idx)

        # Convert to DataFrames
        result = {}
        for amt, indices in amount_groups.items():
            result[amt] = txns.loc[indices]

        return result

    def _analyze_entity(self, entity, txns, amount_tier=None):
        """Analyze single entity for subscription pattern"""
        amounts = txns['amount'].tolist()
        dates = txns['date'].tolist()
        category = txns['category'].iloc[0]

        # Check amount consistency
        mean_amount = sum(amounts) / len(amounts)

        # Check if amounts are within tolerance
        amounts_consistent = all(
            abs(amt - mean_amount) / mean_amount <= self.amount_tolerance
            for amt in amounts
        )

        if not amounts_consistent:
            return None  # Too much variance

        # Calculate intervals between transactions
        intervals = []
        for i in range(1, len(dates)):
            delta = (dates[i] - dates[i-1]).days
            intervals.append(delta)

        if not intervals:
            return None

        avg_interval = sum(intervals) / len(intervals)

        # Classify frequency (RELAXED for intermittent subscriptions)
        if 20 <= avg_interval <= 70:  # Changed from 25-35 to catch monthly + skipped months
            frequency = 'monthly'
            expected_interval = 30
            max_variance = 15  # Allow more variance for intermittent
        elif 80 <= avg_interval <= 120:  # Relaxed quarterly
            frequency = 'quarterly'
            expected_interval = 90
            max_variance = 20
        elif 340 <= avg_interval <= 400:  # Relaxed yearly
            frequency = 'yearly'
            expected_interval = 365
            max_variance = 30
        else:
            return None  # Not a clear subscription pattern

        # Check interval consistency (relaxed)
        interval_variance = sum(abs(i - expected_interval) for i in intervals) / len(intervals)

        # Detect if intermittent (some intervals are multiples of expected)
        is_intermittent = any(
            abs(i - expected_interval * 2) < max_variance or  # Skipped 1 month
            abs(i - expected_interval * 3) < max_variance     # Skipped 2 months
            for i in intervals
        )

        # If not consistently regular, check if it's intermittent subscription
        if interval_variance > max_variance:
            if not is_intermittent:
                return None  # Too inconsistent

        # Detect cost trend
        cost_trend = self._detect_cost_trend(amounts)

        # Calculate metrics
        first_date = dates[0]
        last_date = dates[-1]
        months_active = ((last_date - first_date).days / 30) + 1
        total_cost = sum(amounts)

        # Flag zombie subscriptions (>6 months old, low usage category)
        is_zombie = months_active >= 6 and category in ['Entertainment', 'Services']

        # Generate flags
        flags = []
        if cost_trend == 'increasing':
            flags.append('cost_increase')
        if is_zombie:
            flags.append('long_running')
        if frequency == 'monthly' and mean_amount > 500:
            flags.append('high_cost')
        if is_intermittent:
            flags.append('irregular_pattern')  # New flag

        # Create entity display name (with tier if multiple)
        entity_display = entity
        if amount_tier is not None:
            entity_display = f"{entity} (₹{int(mean_amount)} tier)"

        return {
            'entity': entity_display,
            'category': category,
            'frequency': frequency,
            'occurrences': len(txns),
            'avg_amount': float(mean_amount),
            'latest_amount': float(amounts[-1]),
            'total_cost': float(total_cost),
            'months_active': float(months_active),
            'first_seen': first_date.strftime('%Y-%m-%d'),
            'last_seen': last_date.strftime('%Y-%m-%d'),
            'cost_trend': cost_trend,
            'flags': flags,
            'is_intermittent': is_intermittent,
            'explanation': self._generate_explanation(
                entity_display, frequency, mean_amount, months_active, cost_trend, flags, is_intermittent
            )
        }

    def _detect_cost_trend(self, amounts):
        """Detect if subscription cost is trending up/down"""
        if len(amounts) < 3:
            return 'stable'

        # Simple trend: compare first half vs second half
        mid = len(amounts) // 2
        first_half_avg = sum(amounts[:mid]) / mid
        second_half_avg = sum(amounts[mid:]) / (len(amounts) - mid)

        change = (second_half_avg - first_half_avg) / first_half_avg

        if change > 0.1:  # >10% increase
            return 'increasing'
        elif change < -0.1:  # >10% decrease
            return 'decreasing'
        else:
            return 'stable'

    def _generate_explanation(self, entity, frequency, amount, months, trend, flags, is_intermittent=False):
        """Generate human-readable explanation"""
        explanation = f"{entity}: {frequency.title()} subscription at ₹{amount:.0f}"

        if is_intermittent:
            explanation += " (irregular - active some months only)"

        if 'cost_increase' in flags:
            explanation += ". Cost increasing over time"
        elif trend == 'decreasing':
            explanation += ". Cost decreasing"

        if 'long_running' in flags:
            explanation += f". Active for {months:.0f} months - review if still needed"

        if 'high_cost' in flags:
            explanation += ". High-cost subscription"

        return explanation

    def get_summary(self):
        """Get subscription summary"""
        subscriptions = self.detect_subscriptions()

        if not subscriptions:
            return {
                'total_subscriptions': 0,
                'total_monthly_cost': 0,
                'categories': {}
            }

        total_monthly = sum(
            s['avg_amount'] if s['frequency'] == 'monthly'
            else s['avg_amount'] / 3 if s['frequency'] == 'quarterly'
            else s['avg_amount'] / 12
            for s in subscriptions
        )

        categories = defaultdict(int)
        for s in subscriptions:
            categories[s['category']] += 1

        return {
            'total_subscriptions': len(subscriptions),
            'total_monthly_cost': float(total_monthly),
            'by_category': dict(categories),
            'increasing_cost': len([s for s in subscriptions if 'cost_increase' in s['flags']]),
            'long_running': len([s for s in subscriptions if 'long_running' in s['flags']]),
            'high_cost': len([s for s in subscriptions if 'high_cost' in s['flags']])
        }

    def generate_report(self):
        """Generate complete subscription audit report"""
        subscriptions = self.detect_subscriptions()
        summary = self.get_summary()

        return {
            'summary': summary,
            'subscriptions': subscriptions,
            'metadata': {
                'min_occurrences': self.min_occurrences,
                'amount_tolerance': self.amount_tolerance,
                'total_entities_analyzed': self.df['entity_name'].nunique()
            }
        }