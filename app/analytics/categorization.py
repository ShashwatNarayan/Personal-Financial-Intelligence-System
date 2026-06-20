from app.analytics.entity_resolver import EntityResolver
from app.analytics.entity_memory import EntityMemory


class SmartCategorizer:
    """Enhanced categorizer with persistent memory and per-user DB corrections."""

    def __init__(self, user_id=None):
        self.entity_resolver = EntityResolver()
        # H5-disabled: self.memory = EntityMemory()
        self.memory = None  # H5-disabled: global JSON memory removed (privacy leak)
        self.user_id = user_id
        self._db_cache = {}
        self._global_cache = {}
        if user_id is not None:
            self._load_db_cache(user_id)
        # Global memory is cross-user (not scoped to user_id), so always preload
        # the full table once — avoids one DB query per row in categorize_dataframe.
        self._load_global_cache()

        self.category_keywords = {
            'Food & Dining': [
                'swiggy', 'zomato', 'dominos', 'pizza', 'restaurant',
                'cafe', 'food', 'kfc', 'mcdonalds', 'subway', 'burger',
                'biryani', 'dhaba', 'meal', 'lunch', 'dinner',
                'bakery', 'juice', 'chai', 'thali', 'hotel', 'sweet',
                'mithai', 'lassi', 'icecream', 'ice cream', 'tiffin', 'mess',
                'canteen', 'eatery', 'snack', 'dine', 'grill', 'kitchen',
                'dabba', 'paratha', 'rolls', 'shawarma', 'sushi', 'noodles',
                'chinese', 'fast food', 'cloud kitchen' ,'Cinnabon'
            ],
            'Transport': [
                'uber', 'ola', 'rapido', 'cab', 'taxi', 'petrol', 'fuel',
                'parking', 'toll', 'fastag', 'metro', 'bus',
                'irctc', 'railway', 'auto', 'rickshaw', 'flight', 'indigo',
                'spicejet', 'air india', 'akasa', 'diesel', 'highway', 'nhai',
                'redbus', 'abhibus', 'train', 'airways', 'aviation', 'airport',
                'filling station', 'fuel station', 'service station', 'pump'
            ],
            'Shopping': [
                'amazon', 'flipkart', 'myntra', 'ajio', 'shopping', 'mall',
                'store', 'retail', 'fashion', 'clothes', 'electronics',
                'reliance', 'dmart', 'trader', 'mart', 'enterprise',
                'hypermarket', 'nykaa', 'meesho', 'wholesale', 'general',
                'kirana', 'bazaar', 'bazar', 'emporium', 'outlet', 'showroom',
                'depot', 'suppliers', 'distributors', 'agencies', 'works',
                'brothers', 'sons', 'co ', 'pvt', 'ltd','Medkart'
            ],
            'Utilities': [
                'electricity', 'water', 'gas', 'lpg', 'airtel', 'jio',
                'vodafone', 'vodafone vi', ' vi ', 'internet', 'broadband', 'mobile', 'recharge',
                'bescom', 'tsspdcl', 'apepdcl', 'msedcl', 'bsnl', 'act fibernet',
                'hathway', 'dish tv', 'tata sky', 'tatasky', 'd2h', 'sun direct',
                'videocon', 'tneb', 'cesc', 'adani electricity', 'torrent power',
                'mahanagar gas', 'indane', 'hp gas', 'bharat gas', 'piped gas',
                'water board', 'municipal', 'corporation tax', 'property tax',
                'maintenance'
            ],
            'Entertainment': [
                'netflix', 'spotify', 'prime', 'hotstar', 'movie', 'theatre',
                'cinema', 'pvr', 'inox', 'book', 'music', 'game',
                'youtube', 'disney', 'zee5', 'sonyliv', 'voot', 'mxplayer',
                'jiocinema', 'apple tv', 'bookmyshow', 'paytm movies',
                'amusement', 'multiplex', 'imax', 'bowling', 'gaming', 'steam',
                'playstation', 'xbox', 'concert', 'event', 'ticket', 'club',
                'lounge'
            ],
            'Healthcare': [
                'hospital', 'clinic', 'doctor', 'medical', 'pharmacy',
                'medicine', 'apollo', 'health', 'dental', 'lab',
                'polo', 'fortis', 'manipal', 'max hospital', 'medplus',
                'netmeds', '1mg', 'nursing', 'diagnostic', 'scan', 'xray',
                'x-ray', 'pathology', 'ayurveda', 'homeopathy', 'physiotherapy',
                'optician', 'optical', 'spectacles', 'lens', 'vet',
                'veterinary', 'care hospital', 'nursing home', 'dispensary',
                'surgeon', 'ortho', 'cardio', 'neuro', 'dermat', 'skin clinic',
                'eye care'
            ],
            'Rent': [
                'rent', 'lease', 'housing', 'apartment',
                'pg ', 'paying guest', 'hostel', 'dormitory', 'accommodation',
                'tenant', 'landlord', 'society', 'flat', 'room rent'
            ],
            'Education': [
                'school', 'college', 'university', 'course', 'tuition',
                'education', 'books', 'fees', 'exam',
                'byju', 'unacademy', 'vedantu', 'coaching', 'udemy', 'coursera',
                'skillshare', 'linkedin learning', 'upgrad', 'simplilearn',
                'testbook', 'gradeup', 'institute', 'academy', 'tutorial',
                'classes', 'training', 'workshop', 'certification', 'library',
                'stationery', 'notebook', 'pen '
            ],
            'ATM / Cash': ['atm', 'cash withdrawal', 'cdm'],
        }

    def _load_db_cache(self, user_id):
        """Pre-load all entity memories for this user — one query, avoids N+1 in categorize_dataframe."""
        from app.models import EntityMemory as DbEntityMemory
        rows = DbEntityMemory.query.filter_by(user_id=user_id).all()
        self._db_cache = {r.entity_name: (r.category, r.confidence) for r in rows}

    def _load_global_cache(self):
        """Pre-load the ENTIRE GlobalEntityMemory table — one query, avoids the
        per-row N+1 in categorize_dataframe (was ~1 query/row, ~52ms each).

        This table is cross-user, so the load is unfiltered (no user scoping,
        no limit, no pagination). Keys are normalized with .lower().strip() to
        match the case-insensitive lookup that get_global_category performs —
        stored names are already lowercase, but the resolver hands in
        Title-cased names, so both sides must be normalized identically.
        """
        from app.models import GlobalEntityMemory
        rows = GlobalEntityMemory.query.all()
        self._global_cache = {
            r.entity_name.lower().strip(): r.category for r in rows
        }

    def get_db_category(self, entity_name, user_id):
        """
        Check DB entity_memory for this user+entity first.
        Returns (category, confidence) or (None, None) if not found.
        Uses cache loaded at init to avoid N+1 queries.
        """
        result = self._db_cache.get(entity_name)
        if result:
            return result  # (category, confidence)
        return None, None

    def get_global_category(self, entity_name):
        """Stage 2b: Check global entity memory (cross-user corrections)."""
        # Global memory is seeded by any user's corrections (in practice
        # owner-seeded — only the base account writes; see api/routes.py).
        # The most-corrected/accurate user naturally dominates the global
        # store over time via the upsert logic.
        if not entity_name:
            return None
        # Read from the preloaded dict instead of querying per row. The lookup
        # key is normalized identically to the cache keys (.lower().strip()) so
        # this stays case-insensitive, matching the original SQL behavior.
        return self._global_cache.get(entity_name.lower().strip())

    def categorize_transaction(self, merchant, description):
        """
        Categorize with DB memory priority + confidence level.

        Returns: (category, entity_name, entity_type, confidence_level)
        confidence_level: 'high', 'medium', 'low'
        """
        # Step 1: Entity resolution
        entity_name, entity_type = self.entity_resolver.resolve(description, merchant)

        # Step 2: Check user's DB entity memory first (user-confirmed corrections)
        if self.user_id is not None:
            db_category, db_confidence = self.get_db_category(entity_name, self.user_id)
            if db_category is not None and db_confidence >= 0.9:
                return db_category, entity_name, entity_type, 'high'

        # Step 2b: Global entity memory (cross-user, owner-seeded corrections)
        global_cat = self.get_global_category(entity_name)
        if global_cat:
            return global_cat, entity_name, entity_type, 'high'

        # Step 3: Check shared JSON memory (heuristic cache)
        # H5-disabled: stored = self.memory.get(entity_name)
        # H5-disabled: if stored:
        # H5-disabled:     confidence = 'high' if stored.get('source') == 'user' else 'medium'
        # H5-disabled:     return stored['category'], entity_name, entity_type, confidence

        # Step 4: Entity-based category (platform/person detection)
        entity_category = self.entity_resolver.categorize_by_entity(entity_name, entity_type)
        if entity_category:
            if entity_type == 'platform':
                confidence = 'high'
            else:
                confidence = 'medium'
            # H5-disabled: self.memory.store(entity_name, entity_category, entity_type)
            return entity_category, entity_name, entity_type, confidence

        # Step 5: Keyword matching (fallback)
        text = f"{merchant} {description}".lower()
        for category, keywords in self.category_keywords.items():
            if any(keyword in text for keyword in keywords):
                # H5-disabled: self.memory.store(entity_name, category, entity_type)
                return category, entity_name, entity_type, 'medium'

        # Default: Other (low confidence)
        # H5-disabled: self.memory.store(entity_name, 'Other', entity_type)
        return 'Other', entity_name, entity_type, 'low'

    def categorize_dataframe(self, df):
        """Categorize all transactions in DataFrame with confidence levels."""
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
        """Get categorization statistics including confidence breakdown."""
        total = len(df)
        categorized = len(df[df['category'] != 'Other'])

        # H5-disabled: stats = self.memory.get_stats()
        stats = {}  # H5-disabled: global JSON memory removed (privacy leak)

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
