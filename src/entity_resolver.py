"""
Entity Resolution Module
Extracts and normalizes merchant/person names from transaction descriptions
"""

import re
import hashlib


class EntityResolver:
    """Resolve transaction descriptions to canonical entity names"""

    def __init__(self):
        # Common UPI patterns - extract merchant name, not payment app
        self.upi_pattern = re.compile(r'UPI[/-]([A-Z\s]+?)[-/@]', re.IGNORECASE)

        # Payment apps to ignore (extract what comes AFTER these)
        self.payment_apps = {'PAYTM', 'GPAY', 'GOOGLEPAY', 'PHONEPE', 'BHIM'}

        # Known platforms (exact matches)
        self.platforms = {
            'SWIGGY', 'ZOMATO', 'UBER', 'OLA', 'RAPIDO',
            'AMAZON', 'FLIPKART', 'MYNTRA', 'AJIO',
            'NETFLIX', 'SPOTIFY', 'PRIME', 'HOTSTAR', 'APPLE',
            'AIRTEL', 'JIO', 'JIOMART', 'VODAFONE', 'VI', 'RELIANCE', 'PPSL',
            'DOMINOS', 'KFC', 'MCDONALDS', 'SUBWAY', 'BURGERKING', 'BURGER KING',
            'BLINKIT', 'DUNZO', 'ZEPTO', 'INSTAMART', 'BBNOW', 'BIGBASKET',
            'EKART', 'DELHIVERY', 'BLUEDART',
            'NIKE', 'BATA', 'ADIDAS', 'PUMA', 'AMUL',
            'GROWW', 'ZERODHA', 'UPSTOX', 'ANGELONE', 'KITE',
            'GOOGLE', 'PLAY', 'PLAYSTORE'  # Google Play variants
        }

        # Human name indicators
        self.name_pattern = re.compile(r'^[A-Z][a-z]+(?:\s[A-Z][a-z]+){1,2}$')

    def resolve(self, description, merchant):
        """
        Extract canonical entity name from transaction description

        Returns: (entity_name, entity_type)
        entity_type: 'platform', 'person', 'merchant', 'unknown'
        """
        # Check for known platforms first (but NOT payment apps in UPI context)
        text_upper = f"{description} {merchant}".upper()

        # Extract from UPI pattern FIRST (before platform check)
        upi_match = self.upi_pattern.search(description)
        if upi_match:
            name = upi_match.group(1).strip()

            # If UPI shows payment app, extract the REAL merchant from rest of description
            if name.upper() in self.payment_apps:
                # Look for merchant name after payment app in description
                parts = description.upper().split('-')
                for i, part in enumerate(parts):
                    if part in self.payment_apps and i + 1 < len(parts):
                        # Next part is the actual merchant
                        actual_merchant = parts[i + 1].strip()

                        # Check if it's a known platform (substring match)
                        for platform in self.platforms:
                            if platform in actual_merchant:
                                return platform.title(), 'platform'

                        # Check if human name
                        if self.is_human_name(actual_merchant):
                            return self.normalize_name(actual_merchant), 'person'

                        # Check local merchant keywords
                        for keyword in ['RESTAURANT', 'CAFE', 'FOOD', 'DHABA', 'HOTEL', 'FRUITS', 'LAUNDRY']:
                            if keyword in actual_merchant:
                                return self.normalize_name(actual_merchant), 'merchant'

                        return self.normalize_name(actual_merchant), 'merchant'

                # If can't extract, return Unknown (will trigger fallback)
                return 'Unknown', 'unknown'

            # Check if it's a platform (substring match for "SWIGGY LIMITED" → "SWIGGY")
            name_upper = name.upper()
            for platform in self.platforms:
                if platform in name_upper:
                    return platform.title(), 'platform'

            # Check if it's a human name
            if self.is_human_name(name):
                return self.normalize_name(name), 'person'

            # Otherwise it's a merchant
            return self.normalize_name(name), 'merchant'

        # Check for known platforms in full text (substring match)
        for platform in self.platforms:
            if platform in text_upper:
                return platform.title(), 'platform'

        # Check for local merchant keywords
        local_keywords = {
            'KAFE': 'merchant', 'CAFE': 'merchant', 'GUEST HOUSE': 'merchant',
            'FILLING': 'merchant', 'PETROL': 'merchant', 'SUPER MARKET': 'merchant',
            'SUPERMARKET': 'merchant', 'SALON': 'merchant', 'TRENDS': 'merchant',
            'MARKET': 'merchant', 'STORE': 'merchant', 'SHOP': 'merchant',
            'HOSPITAL': 'merchant', 'CLINIC': 'merchant', 'ICE CREAM': 'merchant',
            'BAKERY': 'merchant', 'HOSPITALITY': 'merchant', 'RESTAURANT': 'merchant',
            'FRUITS': 'merchant', 'LAUNDRY': 'merchant', 'RETAIL': 'merchant',
            'PIZZA': 'merchant', 'FOOD': 'merchant'
        }

        for keyword, etype in local_keywords.items():
            if keyword in text_upper:
                if merchant and merchant != 'Unknown':
                    return self.normalize_name(merchant), etype
                return 'Local Merchant', etype

        # POS transactions - extract merchant name
        if 'POS' in description.upper():
            pos_parts = description.split()
            for i, part in enumerate(pos_parts):
                if 'POS' in part.upper() and i + 2 < len(pos_parts):
                    merchant_name = ' '.join(pos_parts[i+2:]).strip()
                    merchant_name = merchant_name.split('-')[0].strip()
                    return self.normalize_name(merchant_name), 'merchant'

        # Try to extract from merchant field
        if merchant and merchant != 'Unknown':
            clean_merchant = self.clean_merchant_name(merchant)

            # Skip payment apps
            if clean_merchant.upper() in self.payment_apps:
                return 'Unknown', 'unknown'

            # Check if looks like human name
            if self.is_human_name(clean_merchant):
                return clean_merchant, 'person'

            return clean_merchant, 'merchant'

        return 'Unknown', 'unknown'

    def is_human_name(self, name):
        """Check if name looks like a person (2-3 capitalized words)"""
        words = name.split()
        if len(words) < 2 or len(words) > 3:
            return False

        # Check if mostly alphabetic (allows for names like "O M")
        if not all(word.replace('.', '').replace("'", '').isalpha() for word in words if word):
            return False

        # At least 2 words should start with capital letter
        capital_count = sum(1 for word in words if word and word[0].isupper())
        return capital_count >= 2

    def normalize_name(self, name):
        """Normalize entity name"""
        # Remove extra spaces
        name = ' '.join(name.split())

        # Title case
        return name.title()

    def clean_merchant_name(self, merchant):
        """Clean merchant name from common prefixes/suffixes"""
        # Remove common prefixes
        prefixes = ['UPI-', 'POS-', 'ATM-', 'NEFT-', 'IMPS-']
        for prefix in prefixes:
            if merchant.startswith(prefix):
                merchant = merchant[len(prefix):]

        # Remove reference numbers
        merchant = re.sub(r'-\d+$', '', merchant)
        merchant = re.sub(r'\d{10,}', '', merchant)  # Phone numbers

        return self.normalize_name(merchant)

    def get_entity_id(self, entity_name):
        """Generate the unique ID for entity"""
        return hashlib.md5(entity_name.encode()).hexdigest()[:12]

    def categorize_by_entity(self, entity_name, entity_type):
        """Suggest category based on entity type"""
        if entity_type == 'person':
            return 'Transfer / P2P'
        elif entity_type == 'platform':
            # Known platform categories
            food_platforms = {'Swiggy', 'Zomato', 'Dominos', 'Kfc', 'Mcdonalds', 'Subway', 'Bbnow', 'Bigbasket', 'Instamart', 'Burger King', 'Burgerking', 'Amul'}
            transport_platforms = {'Uber', 'Ola', 'Rapido'}
            shopping_platforms = {'Amazon', 'Flipkart', 'Myntra', 'Ajio', 'Blinkit', 'Dunzo', 'Zepto', 'Ekart', 'Nike', 'Bata', 'Adidas', 'Puma', 'Jiomart'}
            entertainment_platforms = {'Netflix', 'Spotify', 'Prime', 'Hotstar', 'Apple'}
            utilities_platforms = {'Airtel', 'Jio', 'Vodafone', 'Vi'}
            investment_platforms = {'Groww', 'Zerodha', 'Upstox', 'Angelone', 'Kite'}

            # Special case: PPSL/Reliance without "Jiomart" context → Shopping
            if entity_name in ['Reliance', 'Ppsl'] and entity_type == 'platform':
                return 'Shopping'

            if entity_name in food_platforms:
                return 'Food & Dining'
            elif entity_name in transport_platforms:
                return 'Transport'
            elif entity_name in shopping_platforms:
                return 'Shopping'
            elif entity_name in entertainment_platforms:
                return 'Entertainment'
            elif entity_name in utilities_platforms:
                return 'Utilities'
            elif entity_name in investment_platforms:
                return 'Investment'
        elif entity_type == 'merchant':
            # Local merchant keywords
            name_lower = entity_name.lower()
            if any(word in name_lower for word in ['kafe', 'cafe', 'restaurant', 'dhaba', 'food', 'guest house', 'hotel', 'ice cream', 'bakery', 'hospitality', 'dining']):
                return 'Food & Dining'
            elif any(word in name_lower for word in ['filling', 'petrol', 'fuel']):
                return 'Transport'
            elif any(word in name_lower for word in ['market', 'store', 'shop', 'supermarket', 'mart', 'variety', 'retail']):
                return 'Shopping'
            elif any(word in name_lower for word in ['hospital', 'clinic', 'medical']):
                return 'Healthcare'
            elif any(word in name_lower for word in ['salon', 'trends', 'barber', 'spa']):
                return 'Other'

        return None  # Will fall back to keyword matching