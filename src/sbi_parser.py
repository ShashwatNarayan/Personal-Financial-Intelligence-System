"""
SBI Bank Statement Parser
Handles Excel statements downloaded from SBI Net Banking / YONO app.

SBI Excel format structure:
  - Rows 0-N: Account metadata (Account Name, Address, Date, Account Number,
              Branch, Drawing Power, Interest Rate, MOD Balance, CIF No.,
              IFS Code, MICR Code, Nomination Registered, Balance as on...)
  - One row: "Account Statement from DD Mon YYYY to DD Mon YYYY"
  - Header row: Txn Date | Value Date | Description | Ref No./Cheque No. | Debit | Credit | Balance
  - Data rows: actual transactions
"""

import pandas as pd
import numpy as np
import re
import os
from datetime import datetime


class SBIStatementParser:
    """
    Parses SBI Bank Excel statements into a standardized DataFrame
    matching the output schema of HDFCStatementParser.

    Output columns (identical to HDFC parser output):
        date, description, merchant, amount, transaction_type, balance
    """

    # All known SBI column name variants across different export versions
    COLUMN_MAPPINGS = [
        # Format 1: Standard SBI Net Banking download
        {
            'Txn Date':           'date',
            'Value Date':         'value_date',
            'Description':        'description',
            'Ref No./Cheque No.': 'reference',
            'Debit':              'debit',
            'Credit':             'credit',
            'Balance':            'balance',
        },
        # Format 2: Some SBI YONO exports use slightly different headers
        {
            'Txn Date':           'date',
            'Value Date':         'value_date',
            'Narration':          'description',
            'Ref No':             'reference',
            'Debit':              'debit',
            'Credit':             'credit',
            'Balance':            'balance',
        },
        # Format 3: Branch-printed statements
        {
            'Transaction Date':   'date',
            'Value Date':         'value_date',
            'Description':        'description',
            'Cheque No':          'reference',
            'Debit':              'debit',
            'Credit':             'credit',
            'Balance':            'balance',
        },
    ]

    def __init__(self):
        self.raw_df    = None
        self.parsed_df = None

    def load_excel(self, filepath: str) -> pd.DataFrame:
        """
        Load SBI Excel file. SBI exports are typically .xlsx from Net Banking
        but older branch-printed exports may be .xls.
        """
        ext = os.path.splitext(filepath)[1].lower()
        print(f"   [SBI] File type: {ext}")

        engines = ['openpyxl', 'xlrd'] if ext == '.xlsx' else ['xlrd', 'openpyxl']
        last_error = None

        for engine in engines:
            try:
                self.raw_df = pd.read_excel(
                    filepath,
                    engine=engine,
                    header=None,
                    dtype=str
                )
                print(f"   [SBI] Loaded {len(self.raw_df)} rows (engine: {engine})")
                return self.raw_df
            except Exception as e:
                last_error = e
                print(f"   [SBI] Engine '{engine}' failed: {str(e)[:60]}")
                continue

        raise ValueError(
            f"[SBI] Could not load file with any engine. "
            f"Ensure xlrd and openpyxl are installed. Error: {str(last_error)}"
        )

    def find_header_row(self, df: pd.DataFrame) -> int:
        """
        Locate the transaction table header row.

        SBI statements have a variable number of metadata rows at the top
        (typically 10-20 rows). The header row contains 'Txn Date' or
        'Transaction Date' alongside 'Description' and 'Balance'.
        """
        for idx in range(min(40, len(df))):
            row_values = [str(v).strip() for v in df.iloc[idx].values]
            row_text   = ' '.join(row_values).upper()

            # Skip empty rows
            non_empty = [v for v in row_values if v and v.lower() != 'nan']
            if not non_empty:
                continue

            has_txn_date   = any('TXN DATE' in v.upper() or 'TRANSACTION DATE' in v.upper()
                                  for v in row_values)
            has_description = any('DESCRIPTION' in v.upper() or 'NARRATION' in v.upper()
                                   for v in row_values)
            has_balance     = any('BALANCE' in v.upper() for v in row_values)
            has_debit       = any('DEBIT' in v.upper() for v in row_values)

            if has_txn_date and has_description and (has_balance or has_debit):
                print(f"   [SBI] Header row found at index {idx}")
                print(f"   [SBI] Columns: {[v for v in row_values if v and v.lower() != 'nan'][:7]}")
                return idx

        raise ValueError(
            "[SBI] Could not locate header row. "
            "Expected columns: 'Txn Date', 'Description', 'Debit', 'Credit', 'Balance'. "
            "Check that this is a valid SBI Excel statement."
        )

    def parse(self, filepath: str) -> pd.DataFrame:
        """Main parsing pipeline. Returns standardized DataFrame."""
        print("\n[SBI] Starting SBI Statement Parsing...")

        # Step 1: Load
        raw_df = self.load_excel(filepath)

        # Step 2: Find header
        header_idx = self.find_header_row(raw_df)

        # Step 3: Extract table
        df = raw_df.iloc[header_idx:].reset_index(drop=True)
        df.columns = df.iloc[0]
        df = df.iloc[1:].reset_index(drop=True)

        # Remove rows where Txn Date column is empty or NaN
        # (SBI sometimes has trailing summary rows like "Opening Balance", "Closing Balance")
        df.columns = [str(c).strip() for c in df.columns]

        # Step 4: Rename columns
        df = self._rename_columns(df)

        # Step 5: Remove non-transaction rows
        # SBI sometimes appends summary rows at the bottom
        df = self._remove_summary_rows(df)

        # Step 6: Parse dates
        df = self._parse_dates(df)

        # Step 7: Process amounts
        df = self._process_amounts(df)

        # Step 8: Clean descriptions
        df = self._clean_descriptions(df)

        # Step 9: Extract merchants
        df = self._extract_merchants(df)

        # Step 10: Remove invalid rows
        df = self._remove_invalid_rows(df)

        # Step 11: Final column selection (matches HDFC parser output exactly)
        final_cols = ['date', 'description', 'merchant', 'amount', 'transaction_type', 'balance']
        df = df[[c for c in final_cols if c in df.columns]].copy()

        if 'balance' not in df.columns:
            df['balance'] = np.nan

        df = df.sort_values('date').reset_index(drop=True)
        self.parsed_df = df

        print(f"\n   [SBI] Parsing Complete!")
        print(f"   [SBI] Total transactions: {len(df)}")
        if len(df) > 0:
            print(f"   [SBI] Date range: {df['date'].min().date()} to {df['date'].max().date()}")
            print(f"   [SBI] Debits:  {(df['transaction_type'] == 'debit').sum()}")
            print(f"   [SBI] Credits: {(df['transaction_type'] == 'credit').sum()}")

        return df

    def _rename_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map SBI column names to the standard internal schema."""
        for mapping in self.COLUMN_MAPPINGS:
            column_mapping = {}

            for sbi_col, std_col in mapping.items():
                for df_col in df.columns:
                    sbi_clean = str(sbi_col).replace(' ', '').replace('.', '').replace('/', '').upper()
                    df_clean  = str(df_col).replace(' ', '').replace('.', '').replace('/', '').upper()

                    if sbi_clean == df_clean or sbi_clean in df_clean or df_clean in sbi_clean:
                        column_mapping[df_col] = std_col
                        break

            # Valid mapping must have at minimum date + description
            if 'date' in column_mapping.values() and 'description' in column_mapping.values():
                df = df.rename(columns=column_mapping)
                print(f"   [SBI] Columns mapped: {list(column_mapping.items())[:5]}")
                return df

        raise ValueError(
            f"[SBI] Could not map columns. Found: {list(df.columns)}. "
            f"Expected SBI format: 'Txn Date', 'Description', 'Debit', 'Credit', 'Balance'"
        )

    def _remove_summary_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove SBI-specific non-transaction rows.
        SBI appends rows like 'Opening Balance', 'Closing Balance',
        and blank rows at the end of the transaction table.
        """
        if 'date' not in df.columns:
            return df

        # Remove rows where the date field contains summary labels
        summary_patterns = [
            'OPENING BALANCE', 'CLOSING BALANCE', 'TOTAL',
            'OPENING', 'CLOSING', 'BROUGHT FORWARD'
        ]

        def is_summary_row(row):
            date_val = str(row.get('date', '')).upper()
            desc_val = str(row.get('description', '')).upper()
            return any(p in date_val or p in desc_val for p in summary_patterns)

        initial = len(df)
        df = df[~df.apply(is_summary_row, axis=1)]

        removed = initial - len(df)
        if removed > 0:
            print(f"   [SBI] Removed {removed} summary/non-transaction rows")

        return df.reset_index(drop=True)

    def _parse_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Parse SBI date format. SBI uses 'DD Mon YYYY' (e.g., '5 Sep 2022',
        '14 Sep 2022') from Net Banking exports.
        Some older formats use 'DD/MM/YYYY'.
        """
        if 'date' not in df.columns:
            raise ValueError("[SBI] Date column not found after column mapping")

        def parse_date_flexible(date_str):
            if pd.isna(date_str) or str(date_str).strip() in ('', 'nan', 'NaT'):
                return pd.NaT

            date_str = str(date_str).strip()

            formats = [
                '%d %b %Y',   # 5 Sep 2022  ← primary SBI format
                '%d %b %y',   # 5 Sep 22
                '%d/%m/%Y',   # 05/09/2022
                '%d/%m/%y',   # 05/09/22
                '%d-%m-%Y',   # 05-09-2022
                '%d-%b-%Y',   # 05-Sep-2022
                '%d-%b-%y',   # 05-Sep-22
                '%Y-%m-%d',   # 2022-09-05
            ]

            for fmt in formats:
                try:
                    return pd.to_datetime(date_str, format=fmt)
                except:
                    continue

            try:
                return pd.to_datetime(date_str, dayfirst=True)
            except:
                return pd.NaT

        df['date'] = df['date'].apply(parse_date_flexible)
        valid   = df['date'].notna().sum()
        invalid = df['date'].isna().sum()
        print(f"   [SBI] Dates parsed: {valid} valid, {invalid} invalid")
        return df

    def _process_amounts(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Process SBI debit/credit columns.
        SBI uses separate Debit and Credit columns (same as HDFC).
        Empty cells mean zero for that direction.
        """
        def clean_amount(series):
            if series is None:
                return pd.Series([0.0] * len(df))
            return (
                series.astype(str)
                .str.replace(r'[₹,\s]', '', regex=True)
                .pipe(pd.to_numeric, errors='coerce')
                .fillna(0.0)
            )

        df['debit']  = clean_amount(df.get('debit'))
        df['credit'] = clean_amount(df.get('credit'))
        df['amount'] = df['debit'] + df['credit']

        df['transaction_type'] = df.apply(
            lambda row: 'credit' if row['credit'] > 0 else 'debit',
            axis=1
        )

        if 'balance' in df.columns:
            df['balance'] = clean_amount(df['balance'])

        return df

    def _clean_descriptions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize SBI description text."""
        if 'description' not in df.columns:
            df['description'] = 'UNKNOWN'
            return df

        df['description'] = (
            df['description']
            .astype(str)
            .str.strip()
            .str.upper()
            .str.replace(r'\s+', ' ', regex=True)
        )
        return df

    def _extract_merchants(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract merchant names from SBI descriptions.

        SBI description patterns differ from HDFC:
        - UPI transactions:  "UPI/CR/123456789012/MERCHANT NAME/BANK/VPA"
                             "UPI/DR/123456789012/MERCHANT NAME/BANK/VPA"
        - IMPS:              "IMPS/123456789012/NAME/BANK"
        - NEFT:              "NEFT/NXXXXXXX/NAME/BANK/REF"
        - ATM:               "ATM WDL/XXXXXXXXXX/LOCATION"
        - POS:               "POS/XXXXXXXXXX/MERCHANT NAME"
        - Interest:          "INT.PAID/COMPUTED ON..."
        - Charges:           "CHARGES/..."
        """
        def extract_merchant_name(description: str) -> str:
            desc = str(description).upper()

            # UPI pattern: UPI/CR or UPI/DR followed by ref/merchant/bank/vpa
            # Format: UPI/CR/REFNUMBER/MERCHANTNAME/BANKNAME/VPA@BANK
            upi_match = re.search(
                r'UPI/(?:CR|DR)/\d+/([A-Z][A-Z\s\.\-]{2,30}?)(?:/|$)',
                desc
            )
            if upi_match:
                name = upi_match.group(1).strip()
                if name and len(name) > 2:
                    return name.title()

            # Alternative UPI format: UPI-MERCHANTNAME-REF
            upi_alt = re.search(r'UPI[-/]([A-Z][A-Z\s]{2,25}?)[-@/]', desc)
            if upi_alt:
                name = upi_alt.group(1).strip()
                if name:
                    return name.title()

            # IMPS: IMPS/REFNUMBER/PERSONNAME/BANK
            imps_match = re.search(r'IMPS/\d+/([A-Z][A-Z\s]{2,30}?)/', desc)
            if imps_match:
                return imps_match.group(1).strip().title()

            # NEFT: NEFT/REFNUMBER/PERSONNAME
            neft_match = re.search(r'NEFT/[A-Z0-9]+/([A-Z][A-Z\s]{2,30}?)(?:/|$)', desc)
            if neft_match:
                return neft_match.group(1).strip().title()

            # ATM withdrawal
            if 'ATM WDL' in desc or 'ATM/WDL' in desc or 'ATM CASH' in desc:
                return 'ATM'

            # POS transaction
            pos_match = re.search(r'POS/[A-Z0-9]+/([A-Z][A-Z\s]{2,25})', desc)
            if pos_match:
                return pos_match.group(1).strip().title()

            # Known platforms (direct mention in description)
            known_platforms = [
                'SWIGGY', 'ZOMATO', 'AMAZON', 'FLIPKART', 'UBER',
                'OLA', 'NETFLIX', 'SPOTIFY', 'HOTSTAR', 'MYNTRA',
                'AIRTEL', 'JIO', 'BLINKIT', 'BIGBASKET', 'DUNZO',
                'RAPIDO', 'PAYTM', 'PHONEPE', 'GPAY'
            ]
            for platform in known_platforms:
                if platform in desc:
                    return platform.title()

            # Interest / charges
            if 'INT.PAID' in desc or 'INTEREST' in desc:
                return 'Interest'
            if 'CHARGES' in desc or 'CHRGS' in desc:
                return 'Bank Charges'
            if 'SALARY' in desc or 'SAL/' in desc:
                return 'Salary'

            # Fallback: first meaningful word cluster
            words = [w for w in desc.split() if len(w) > 2 and w.isalpha()]
            return words[0].title()[:20] if words else 'UNKNOWN'

        df['merchant'] = df['description'].apply(extract_merchant_name)
        return df

    def _remove_invalid_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove rows with invalid dates or zero amounts."""
        initial = len(df)

        df = df.dropna(subset=['date'])
        df = df[df['amount'] > 0]
        df = df[df['date'] <= pd.Timestamp.now()]
        df = df[df['amount'] < 10_000_000]

        removed = initial - len(df)
        if removed > 0:
            print(f"   [SBI] Removed {removed} invalid rows")

        return df


class SBIStatementValidator:
    """Validates parsed SBI statement — identical interface to BankStatementValidator."""

    def __init__(self):
        self.errors   = []
        self.warnings = []

    def validate(self, df: pd.DataFrame) -> bool:
        print("\n   [SBI] Running validation...")
        self.errors   = []
        self.warnings = []

        required = ['date', 'description', 'amount']
        missing  = [c for c in required if c not in df.columns]
        if missing:
            self.errors.append(f"Missing columns: {missing}")

        if len(df) == 0:
            self.errors.append("No valid transactions found")
            return False

        if df['date'].max() > pd.Timestamp.now():
            self.errors.append("Statement contains future dates")

        dupes = df.duplicated(subset=['date', 'amount', 'description'], keep=False)
        if dupes.sum() > 0:
            self.warnings.append(f"Found {dupes.sum()} potential duplicate transactions")

        if self.errors:
            print("   [SBI] VALIDATION FAILED:")
            for e in self.errors:
                print(f"      ERROR: {e}")
            return False

        if self.warnings:
            for w in self.warnings:
                print(f"   [SBI] WARNING: {w}")

        print("   [SBI] Validation passed!")
        return True