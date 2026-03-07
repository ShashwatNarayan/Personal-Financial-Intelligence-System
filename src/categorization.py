from src.entity_resolver import EntityResolver
from src.entity_memory import EntityMemory


class SmartCategorizer:
    """Enhanced categorizer with persistent memory"""

    def __init__(self):
        self.entity_resolver = EntityResolver()
        self.memory = EntityMemory()

        # Existing keyword rules
        self.category_keywords = {
            'Food & Dining': [
                'swiggy', 'zomato', 'dominos', 'pizza', 'restaurant',
                'cafe', 'food', 'kfc', 'mcdonalds', 'subway', 'burger',
                'biryani', 'dhaba', 'meal', 'lunch', 'dinner'
            ],
            'Transport': [
                'uber', 'ola', 'rapido', 'cab', 'taxi', 'petrol', 'fuel',
                'parking', 'toll', 'fastag', 'metro', 'bus'
            ],
            'Shopping': [
                'amazon', 'flipkart', 'myntra', 'ajio', 'shopping', 'mall',
                'store', 'retail', 'fashion', 'clothes', 'electronics'
            ],
            'Utilities': [
                'electricity', 'water', 'gas', 'lpg', 'airtel', 'jio',
                'vodafone', 'vi', 'internet', 'broadband', 'mobile', 'recharge'
            ],
            'Entertainment': [
                'netflix', 'spotify', 'prime', 'hotstar', 'movie', 'theatre',
                'cinema', 'pvr', 'inox', 'book', 'music', 'game'
            ],
            'Healthcare': [
                'hospital', 'clinic', 'doctor', 'medical', 'pharmacy',
                'medicine', 'apollo', 'health', 'dental', 'lab'
            ],
            'Rent': ['rent', 'lease', 'housing', 'apartment'],
            'Education': [
                'school', 'college', 'university', 'course', 'tuition',
                'education', 'books', 'fees', 'exam'
            ],
            'ATM / Cash': ['atm', 'cash withdrawal', 'cdm'],
        }

    def categorize_transaction(self, merchant, description):
        """
        Categorize with memory priority + confidence level

        Returns: (category, entity_name, entity_type, confidence_level)
        confidence_level: 'high', 'medium', 'low'
        """
        # Step 1: Entity resolution
        entity_name, entity_type = self.entity_resolver.resolve(description, merchant)

        # Step 2: Check memory FIRST
        stored = self.memory.get(entity_name)
        if stored:
            # High confidence: User-confirmed or previously learned
            confidence = 'high' if stored.get('source') == 'user' else 'high'
            return stored['category'], entity_name, entity_type, confidence

        # Step 3: Entity-based category (platform/person detection)
        entity_category = self.entity_resolver.categorize_by_entity(entity_name, entity_type)
        if entity_category:
            # High: Known platform (Swiggy, Netflix)
            # Medium: Inferred from entity type (person→P2P, merchant→shopping)
            if entity_type == 'platform':
                confidence = 'high'
            else:
                confidence = 'medium'

            # Store in memory for next time
            self.memory.store(entity_name, entity_category, entity_type)
            return entity_category, entity_name, entity_type, confidence

        # Step 4: Keyword matching (fallback)
        text = f"{merchant} {description}".lower()

        for category, keywords in self.category_keywords.items():
            if any(keyword in text for keyword in keywords):
                # Medium: Keyword match (heuristic inference)
                self.memory.store(entity_name, category, entity_type)
                return category, entity_name, entity_type, 'medium'

        # Default: Other (low confidence - fallback guess)
        self.memory.store(entity_name, 'Other', entity_type)
        return 'Other', entity_name, entity_type, 'low'

    def categorize_dataframe(self, df):
        """Categorize all transactions in DataFrame with confidence levels"""
        categories = []
        entity_names = []
        entity_types = []
        confidence_levels = []

        for idx, row in df.iterrows():
            merchant = row.get('merchant', 'Unknown')
            description = row.get('description', '')

            category, entity_name, entity_type, confidence = self.categorize_transaction(merchant, description)

            categories.append(category)
            entity_names.append(entity_name)
            entity_types.append(entity_type)
            confidence_levels.append(confidence)

        df['category'] = categories
        df['entity_name'] = entity_names
        df['entity_type'] = entity_types
        df['confidence_level'] = confidence_levels

        return df

    def get_category_stats(self, df):
        """Get categorization statistics including confidence breakdown"""
        total = len(df)
        categorized = len(df[df['category'] != 'Other'])

        stats = self.memory.get_stats()

        # Confidence distribution
        confidence_counts = df['confidence_level'].value_counts().to_dict()

        return {
            'total_transactions': total,
            'categorized': categorized,
            'categorization_rate': (categorized / total * 100) if total > 0 else 0,
            'category_distribution': df['category'].value_counts().to_dict(),
            'confidence_distribution': confidence_counts,
            'high_confidence_count': confidence_counts.get('high', 0),
            'medium_confidence_count': confidence_counts.get('medium', 0),
            'low_confidence_count': confidence_counts.get('low', 0),
            'memory_stats': stats
        }