"""
Entity Resolution Module
Extracts and normalizes merchant/person names from transaction descriptions
"""

import re
import hashlib


class EntityResolver:
    """Resolve transaction descriptions to canonical entity names"""

    def __init__(self):
        # Common UPI patterns - extract merchant name, not payment app.
        # Two formats are supported (tried SBI-first in resolve()):

        # SBI format: UPI/DR|CR|DRC/<digits>/<merchant>
        self.upi_sbi_pattern = re.compile(
            r'UPI[/-](?:CR|DR|DRC)[/-]\d+[/-]([A-Z][A-Z0-9\s\.\-]{2,30}?)(?:[/-]|$)',
            re.IGNORECASE
        )

        # HDFC format: UPI-<merchant>-<vpa or ref>
        self.upi_hdfc_pattern = re.compile(
            r'UPI[-/]([A-Z][A-Z\s\.\-]{2,29}?)[-@]',
            re.IGNORECASE
        )

        # SBI UPI VPA / handle — 6th segment of UPI/DR|CR/<rrn>/<name>/<bank>/<VPA>/...
        # Used as a secondary merchant/person signal when the name is ambiguous.
        self.vpa_pattern = re.compile(
            r'UPI[/-](?:CR|DR|DRC)[/-]\d+[/-][^/]+[/-][^/]+[/-]([^/\s]+)',
            re.IGNORECASE
        )

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

    def resolve(self, description, merchant=None, vpa=None):
        """
        Extract canonical entity name from transaction description

        Returns: (entity_name, entity_type)
        entity_type: 'platform', 'person', 'merchant', 'atm', 'direct_debit', 'unknown'

        `vpa` is an optional secondary signal (the SBI UPI handle). When not
        supplied it is self-extracted from `description`, so callers that only
        pass (description, merchant) still benefit from VPA-based tie-breaking.
        """
        # Check for known platforms first (but NOT payment apps in UPI context)
        text_upper = f"{description} {merchant}".upper()

        # Non-UPI SBI transaction types: no UPI name to extract, but a known
        # entity/type can be assigned straight from the description prefix.
        desc_upper = str(description).upper().strip()
        if desc_upper.startswith('SWEEP'):
            return 'Internal Transfer', 'internal'
        if desc_upper.startswith('ATM'):
            return 'ATM Withdrawal', 'atm'
        if desc_upper.startswith('DIRECT DR') or desc_upper.startswith('DIRECT DEBIT'):
            return 'Direct Debit', 'direct_debit'
        if 'HDFC BANK CREDIT CARD' in desc_upper or 'INB HDFC' in desc_upper:
            return 'HDFC Credit Card', 'merchant'
        if 'SBICARD' in desc_upper or 'SBI CARD' in desc_upper:
            return 'SBI Card', 'merchant'

        # Self-extract the SBI UPI VPA when the caller did not pass one.
        if vpa is None:
            vpa_m = self.vpa_pattern.search(description)
            vpa = vpa_m.group(1) if vpa_m else None

        # Extract from UPI pattern FIRST (before platform check).
        # Try SBI format (indicator + ref precede name), then HDFC (name first).
        upi_match = self.upi_sbi_pattern.search(description)
        from_sbi = upi_match is not None  # SBI format (/DR|CR|DRC/<digits>/); HDFC never matches this
        if not upi_match:
            upi_match = self.upi_hdfc_pattern.search(description)
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
                            if re.search(rf'\b{re.escape(platform)}\b', actual_merchant):
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
                if re.search(rf'\b{re.escape(platform)}\b', name_upper):
                    return platform.title(), 'platform'

            # SBI single-word truncated payee names: SBI caps the UPI name field
            # at ~8 chars, collapsing many person names to one token (e.g.
            # "Shashwat Narayan" → "SHASHWAT"), which fails is_human_name()'s
            # ≥2-word gate and lands them in "Other". For SBI-format matches only,
            # treat a single-word name that is not a payment app or known platform
            # as a person (→ Transfer / P2P). HDFC strings never reach here via
            # upi_sbi_pattern, so the HDFC path is structurally unaffected.
            if from_sbi and ' ' not in name and name_upper not in self.payment_apps:
                # platforms already returned above, so name is not a known platform.
                # Break the tie with the VPA: a merchant-looking handle (toyworld.6,
                # isthara.p) overrides to merchant; a person-looking or processor/
                # unknown handle keeps the person default (recovers truncated P2P).
                if self._classify_vpa(vpa) == 'merchant':
                    return self.normalize_name(name), 'merchant'
                return self.normalize_name(name), 'person'

            # Check if it's a human name
            if self.is_human_name(name):
                return self.normalize_name(name), 'person'

            # Otherwise it's a merchant
            return self.normalize_name(name), 'merchant'

        # Check for known platforms in full text (substring match)
        for platform in self.platforms:
            if re.search(rf'\b{re.escape(platform)}\b', text_upper):
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

        # POS transactions - extract merchant name.
        # Two shapes occur:
        #   (a) HDFC card swipe: POS <card> <ref> <DDMONYY> <HH:MM:SS> <city> <merchant...>
        #       — the HH:MM:SS token anchors the structured prefix; the merchant is
        #       everything after the <time> <city> pair (city = first token after time).
        #   (b) generic POS: POS <terminal> <merchant...>  (legacy behaviour).
        if 'POS' in description.upper():
            merchant_name = self._extract_pos_merchant(description)
            if merchant_name:
                # Re-run platform detection: a card-swipe merchant can embed a known
                # brand that the earlier whole-word scan missed while it was still
                # glued to the ref/date/city noise (e.g. WWWBIGBASKETCOM).
                mu = merchant_name.upper()
                for platform in self.platforms:
                    if re.search(rf'\b{re.escape(platform)}\b', mu):
                        return platform.title(), 'platform'
                # A card swipe is a merchant by definition, never a P2P person —
                # so we do NOT run it through is_human_name() (which would flag any
                # two Title-case words, e.g. "Star Bazaar", as a person).
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

    def _extract_pos_merchant(self, description):
        """
        Pull the merchant name out of a POS narration.

        HDFC debit-card swipes read:
            POS <masked-card> <ref> <DDMONYY> <HH:MM:SS> <city> <merchant...>
        The HH:MM:SS token is a reliable anchor for the structured prefix: the
        token immediately after it is the city, and everything past the city is
        the merchant. Falls back to the legacy "POS <terminal> <merchant>" shape
        when no time token is present.

        Returns the raw (upper-cased) merchant string, or '' if nothing usable.
        """
        tokens = description.split()

        time_idx = next(
            (i for i, t in enumerate(tokens) if re.fullmatch(r'\d{1,2}:\d{2}:\d{2}', t)),
            None
        )
        if time_idx is not None:
            tail = tokens[time_idx + 1:]          # <city> <merchant...>  or  <merchant>
            # First token after the time is the city; drop it. If only one token
            # follows, treat it as the merchant (no city present).
            merchant = ' '.join(tail[1:]) if len(tail) >= 2 else (tail[0] if tail else '')
        else:
            # Legacy: drop 'POS' and the next token (terminal id), keep the rest.
            pos_idx = next((i for i, t in enumerate(tokens) if 'POS' in t.upper()), None)
            if pos_idx is None or pos_idx + 2 >= len(tokens):
                return ''
            merchant = ' '.join(tokens[pos_idx + 2:])

        merchant = merchant.split('-')[0].strip()

        # Normalise a bare web address (WWWBIGBASKETCOM / www.bigbasket.com -> BIGBASKET)
        if merchant.upper().startswith('WWW'):
            merchant = re.sub(r'^WWW\.?', '', merchant, flags=re.IGNORECASE)
            merchant = re.sub(r'\.?COM$', '', merchant, flags=re.IGNORECASE).strip()

        return merchant

    def _classify_vpa(self, vpa):
        """
        Classify a UPI VPA/handle as a secondary signal.

        Returns 'merchant', 'person', or None (no usable signal).
        """
        if not vpa:
            return None
        v = str(vpa).lower().strip()

        # Payment processors / QR aggregators — carry no merchant/person signal
        processors = ('paytmqr', 'bharatpe', 'pinelabs', 'phonepe', 'gpay',
                      'amazonpay', 'razorpay', 'billdesk')
        if any(p in v for p in processors):
            return None

        # Explicit business keywords → merchant
        business_kw = ('store', 'mart', 'shop', 'hotel', 'cafe', 'foods',
                       'pay', 'qr', 'pos')
        if any(k in v for k in business_kw):
            return 'merchant'

        # Structural heuristic on the handle. SBI merchant handles tend to be
        # <business>.<short/numeric bank-or-QR tag> (toyworld.6, isthara.p,
        # indigo2.pa); personal handles are either a single token with digits
        # (shashwatn2, kasoju1978) or <name>.<name-fragment> (piyush.kha).
        if '.' in v:
            suffix = v.rsplit('.', 1)[1]
            if suffix.isdigit() or len(suffix) <= 2:
                return 'merchant'
            return 'person'

        # No dot → firstname+digits / single token → person
        return 'person'

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