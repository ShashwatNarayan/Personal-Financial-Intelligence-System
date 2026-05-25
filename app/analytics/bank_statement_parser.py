"""
Enhanced Bank Statement Parser - Handles Real HDFC Formats
Fixes: .xls (old format), .xlsx (new format), multiple column name variations
"""

import pandas as pd
import numpy as np
from datetime import datetime
import re
import os


class HDFCStatementParser:
    """
    Handles real HDFC Bank Excel statements in both .xls and .xlsx formats
    """

    COLUMN_MAPPINGS = [
        # Format 1: Real HDFC download (Withdrawal/Deposit)
        {
            'Date': 'date',
            'Narration': 'description',
            'Withdrawal Amt.': 'debit',
            'Deposit Amt.': 'credit',
            'Closing Balance': 'balance',
            'Chq./Ref.No.': 'reference',
            'Value Dt': 'value_date'
        },
        # Format 2: Standard sample format
        {
            'Date': 'date',
            'Narration': 'description',
            'Debit Amt': 'debit',
            'Credit Amt': 'credit',
            'Closing Balance': 'balance',
            'Chq/Ref No': 'reference',
            'Value Dt': 'value_date'
        },
        # Format 3: Shortened column names
        {
            'Date': 'date',
            'Narration': 'description',
            'Debit': 'debit',
            'Credit': 'credit',
            'Balance': 'balance',
        }
    ]

    def __init__(self):
        self.raw_df = None
        self.parsed_df = None
        self.validation_log = []

    def load_excel(self, filepath):
        """
        Load Excel file - handles both .xls and .xlsx formats
        Tries multiple engines automatically
        """
        ext = os.path.splitext(filepath)[1].lower()
        print(f"   File type detected: {ext}")

        # Engine priority order based on file extension
        if ext == '.xls':
            engines = ['xlrd', 'openpyxl']
        else:
            engines = ['openpyxl', 'xlrd']

        last_error = None

        for engine in engines:
            try:
                self.raw_df = pd.read_excel(
                    filepath,
                    engine=engine,
                    header=None,
                    dtype=str  # Read everything as string first
                )
                print(f"   Loaded Excel file: {len(self.raw_df)} rows (engine: {engine})")
                return self.raw_df
            except Exception as e:
                last_error = e
                print(f"   Engine '{engine}' failed: {str(e)[:60]}")
                continue

        # If both engines fail, try reading as CSV (sometimes banks export as CSV with .xls extension)
        try:
            self.raw_df = pd.read_csv(filepath, header=None, dtype=str)
            print(f"  Loaded as CSV: {len(self.raw_df)} rows")
            return self.raw_df
        except:
            pass

        raise ValueError(
            f"Failed to load file. "
            f"Please ensure 'xlrd' is installed for .xls files: "
            f"Run 'pip install xlrd' in your terminal. "
            f"Original error: {str(last_error)}"
        )

    def find_header_row(self, df):
        """
        Find the actual header row in the statement
        Handles star separator rows and metadata rows
        """
        for idx in range(min(35, len(df))):
            row_values = [str(v) for v in df.iloc[idx].values]
            row_text = ' '.join(row_values).upper()

            # Skip rows that are mostly stars or dashes
            non_empty = [v for v in row_values if v.strip() and v.strip() != 'nan']
            if non_empty and all(
                set(v.strip()).issubset({'*', '-', '='}) for v in non_empty
            ):
                continue

            # Skip empty rows
            if not non_empty:
                continue

            # Look for multiple header indicators
            has_date = 'DATE' in row_text
            has_narration = 'NARRATION' in row_text or 'DESCRIPTION' in row_text
            has_amount = any(
                x in row_text
                for x in ['DEBIT', 'CREDIT', 'WITHDRAWAL', 'DEPOSIT', 'AMOUNT']
            )
            has_balance = 'BALANCE' in row_text

            if has_date and (has_narration or has_amount or has_balance):
                print(f"  Found header row at index {idx}")
                print(f"   Columns: {[v for v in row_values if v.strip() and v != 'nan'][:6]}")
                return idx

        raise ValueError(
            "Could not find header row. "
            "Try opening the file in Excel and check which row has "
            "'Date', 'Narration', 'Withdrawal Amt.' headers."
        )

    def parse(self, filepath):
        """Main parsing pipeline"""
        print("\n  Starting HDFC Statement Parsing...")

        # Step 1: Load Excel
        raw_df = self.load_excel(filepath)

        # Step 2: Find header row
        try:
            header_idx = self.find_header_row(raw_df)
        except ValueError as e:
            print(f"\n   {str(e)}")
            print("\n   First 25 rows of your file:")
            for i in range(min(25, len(raw_df))):
                vals = [str(v) for v in raw_df.iloc[i].values if str(v).strip() and str(v) != 'nan']
                if vals:
                    print(f"   Row {i}: {vals[:4]}")
            raise

        # Step 3: Extract data from header row onward
        df = raw_df.iloc[header_idx:].reset_index(drop=True)
        df.columns = df.iloc[0]  # First row becomes column headers
        df = df.iloc[1:].reset_index(drop=True)

        # Remove star/separator rows from data
        def is_separator_row(row):
            vals = [str(v) for v in row.values if str(v).strip() and str(v) != 'nan']
            if not vals:
                return True
            return all(set(v.strip()).issubset({'*', '-', '='}) for v in vals)

        df = df[~df.apply(is_separator_row, axis=1)]
        df = df.reset_index(drop=True)

        print(f"  Extracted {len(df)} data rows")
        print(f"   Raw columns: {[str(c)[:25] for c in list(df.columns)[:6]]}")

        # Step 4: Rename columns
        df = self._rename_columns(df)

        # Step 5: Parse dates
        df = self._parse_dates(df)

        # Step 6: Process amounts
        df = self._process_amounts(df)

        # Step 7: Clean descriptions
        df = self._clean_descriptions(df)

        # Step 8: Extract merchants
        df = self._extract_merchants(df)

        # Step 9: Remove invalid rows
        df = self._remove_invalid_rows(df)

        # Step 10: Final column selection
        final_cols = ['date', 'description', 'merchant', 'amount', 'transaction_type', 'balance']
        df = df[[c for c in final_cols if c in df.columns]].copy()

        if 'balance' not in df.columns:
            df['balance'] = np.nan

        df = df.sort_values('date').reset_index(drop=True)
        self.parsed_df = df

        print(f"\n  Parsing Complete!")
        print(f"   Total transactions: {len(df)}")
        if len(df) > 0:
            print(f"   Date range: {df['date'].min().date()} to {df['date'].max().date()}")
            print(f"   Debits:  {(df['transaction_type'] == 'debit').sum()}")
            print(f"   Credits: {(df['transaction_type'] == 'credit').sum()}")

        return df

    def _rename_columns(self, df):
        """Rename columns using flexible matching"""

        # Clean column names first (remove leading/trailing spaces)
        df.columns = [str(c).strip() for c in df.columns]

        for mapping in self.COLUMN_MAPPINGS:
            column_mapping = {}

            for hdfc_col, std_col in mapping.items():
                for df_col in df.columns:
                    hdfc_clean = str(hdfc_col).replace(' ', '').replace('.', '').upper()
                    df_clean = str(df_col).replace(' ', '').replace('.', '').upper()

                    if hdfc_clean == df_clean:
                        column_mapping[df_col] = std_col
                        break
                    elif hdfc_clean in df_clean or df_clean in hdfc_clean:
                        column_mapping[df_col] = std_col
                        break

            # Validate: must have at minimum date + description
            if 'date' in column_mapping.values() and 'description' in column_mapping.values():
                df = df.rename(columns=column_mapping)
                print(f"  Columns mapped: {list(column_mapping.items())[:5]}")
                return df

        # Last resort: try positional mapping
        # HDFC format: Date | Narration | Ref | Value Dt | Withdrawal | Deposit | Balance
        print("⚠️  Trying positional column mapping...")
        cols = list(df.columns)
        positional_map = {}

        for i, col in enumerate(cols):
            col_upper = str(col).upper()
            if 'DATE' in col_upper and 'VALUE' not in col_upper:
                positional_map[col] = 'date'
            elif 'NARRATION' in col_upper or 'DESCRIPTION' in col_upper:
                positional_map[col] = 'description'
            elif 'WITHDRAWAL' in col_upper or ('DEBIT' in col_upper and 'CREDIT' not in col_upper):
                positional_map[col] = 'debit'
            elif 'DEPOSIT' in col_upper or ('CREDIT' in col_upper and 'DEBIT' not in col_upper):
                positional_map[col] = 'credit'
            elif 'CLOSING' in col_upper or 'BALANCE' in col_upper:
                positional_map[col] = 'balance'

        if 'date' in positional_map.values() and 'description' in positional_map.values():
            df = df.rename(columns=positional_map)
            print(f"  Positional mapping applied: {list(positional_map.items())[:5]}")
            return df

        raise ValueError(
            f"Could not map columns. Found columns: {list(df.columns)}. "
            f"Expected: 'Date', 'Narration', 'Withdrawal Amt.', 'Deposit Amt.', 'Closing Balance'"
        )

    def _parse_dates(self, df):
        """Parse dates with multiple format support"""
        if 'date' not in df.columns:
            raise ValueError("Date column not found")

        def parse_date_flexible(date_str):
            if pd.isna(date_str) or str(date_str).strip() in ('', 'nan', 'NaT'):
                return pd.NaT

            date_str = str(date_str).strip()

            formats = [
                '%d/%m/%Y',  # 01/11/2025
                '%d/%m/%y',  # 01/11/25
                '%d-%m-%Y',  # 01-11-2025
                '%d-%m-%y',  # 01-11-25
                '%d-%b-%Y',  # 01-Nov-2025
                '%d-%b-%y',  # 01-Nov-25
                '%d %b %Y',  # 01 Nov 2025
                '%Y-%m-%d',  # 2025-11-01
                '%d %b %y',  # 01 Nov 25
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

        invalid = df['date'].isna().sum()
        valid = df['date'].notna().sum()
        print(f"  Dates parsed: {valid} valid, {invalid} invalid")

        return df

    def _process_amounts(self, df):
        """Process debit/credit amounts"""

        def clean_amount(series):
            if series is None:
                return pd.Series([0] * len(df))
            return (
                series.astype(str)
                .str.replace('[₹,\s]', '', regex=True)
                .pipe(pd.to_numeric, errors='coerce')
                .fillna(0)
            )

        df['debit'] = clean_amount(df.get('debit'))
        df['credit'] = clean_amount(df.get('credit'))
        df['amount'] = df['debit'] + df['credit']

        df['transaction_type'] = df.apply(
            lambda row: 'credit' if row['credit'] > 0 else 'debit',
            axis=1
        )

        if 'balance' in df.columns:
            df['balance'] = clean_amount(df['balance'])

        return df

    def _clean_descriptions(self, df):
        """Normalize description text"""
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

    def _extract_merchants(self, df):
        """Extract merchant names from descriptions"""

        def extract_merchant_name(description):
            desc = str(description).upper()

            # UPI pattern: UPI-MERCHANTNAME-REFERENCE
            upi_match = re.search(r'UPI[-/]([A-Z0-9][A-Z0-9\s]{2,30}?)[-@/]', desc)
            if upi_match:
                merchant = upi_match.group(1).strip()
                # Clean trailing digits
                merchant = re.sub(r'\d{5,}$', '', merchant).strip()
                if merchant:
                    return merchant

            # POS transactions
            if 'POS' in desc:
                pos_match = re.search(r'POS\s+\S+\s+([A-Z][A-Z\s]{2,25})', desc)
                if pos_match:
                    return pos_match.group(1).strip()
                return 'POS'

            # Known merchants
            for merchant in ['SWIGGY', 'ZOMATO', 'AMAZON', 'FLIPKART', 'UBER',
                             'OLA', 'NETFLIX', 'SPOTIFY', 'HOTSTAR', 'MYNTRA',
                             'PAYTM', 'PHONEPE', 'GPAY', 'RAPIDO', 'AIRTEL',
                             'JIO', 'BSNL']:
                if merchant in desc:
                    return merchant

            if 'ATM' in desc:
                return 'ATM'
            if 'SALARY' in desc:
                return 'SALARY'
            if any(x in desc for x in ['NEFT', 'IMPS', 'RTGS']):
                return 'TRANSFER'

            # Fallback: first meaningful word
            words = [w for w in desc.split() if len(w) > 2 and w.isalpha()]
            return words[0][:20] if words else 'UNKNOWN'

        df['merchant'] = df['description'].apply(extract_merchant_name)
        return df

    def _remove_invalid_rows(self, df):
        """Remove invalid/empty rows"""
        initial = len(df)

        df = df.dropna(subset=['date'])
        df = df[df['amount'] > 0]
        df = df[df['date'] <= pd.Timestamp.now()]
        df = df[df['amount'] < 10_000_000]

        removed = initial - len(df)
        if removed > 0:
            print(f"⚠️  Removed {removed} invalid rows")

        return df


class BankStatementValidator:
    """Validates parsed statement data"""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def validate(self, df):
        print("\n🔍 Running validation checks...")
        self.errors = []
        self.warnings = []

        required = ['date', 'description', 'amount']
        missing = [c for c in required if c not in df.columns]
        if missing:
            self.errors.append(f"Missing columns: {missing}")

        if len(df) == 0:
            self.errors.append("No valid transactions found after parsing")
            return False

        if df['date'].max() > pd.Timestamp.now():
            self.errors.append("Statement contains future dates")

        dupes = df.duplicated(subset=['date', 'amount', 'description'], keep=False)
        if dupes.sum() > 0:
            self.warnings.append(f"Found {dupes.sum()} potential duplicate transactions")

        if self.errors:
            print("\n  VALIDATION FAILED:")
            for e in self.errors:
                print(f"   ERROR: {e}")
            return False

        if self.warnings:
            print("\n⚠️  VALIDATION WARNINGS:")
            for w in self.warnings:
                print(f"   WARNING: {w}")

        print("  Validation passed!")
        return True


def test_parser(filepath):
    """Quick test function"""
    parser = HDFCStatementParser()
    df = parser.parse(filepath)

    validator = BankStatementValidator()
    is_valid = validator.validate(df)

    if is_valid:
        print("\n  Sample Data (first 5 rows):")
        print(df[['date', 'merchant', 'amount', 'transaction_type']].head())
        print(f"\n  Debits:  ₹{df[df['transaction_type']=='debit']['amount'].sum():,.2f}")
        print(f"   Credits: ₹{df[df['transaction_type']=='credit']['amount'].sum():,.2f}")
        print(f"\n  Top Merchants:")
        print(df['merchant'].value_counts().head(8))

    return df


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        test_parser(sys.argv[1])
    else:
        print("Usage: python bank_statement_parser.py <path_to_statement.xls>")