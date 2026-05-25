"""
Bank Detector — identifies the bank from an uploaded Excel statement
and routes to the correct parser.

Currently supported:
  - HDFC Bank (.xls / .xlsx)
  - SBI — State Bank of India (.xls / .xlsx)

To add a new bank: write its parser, import it here, add a detection
rule to _detect_bank(), and add it to the PARSERS dict.
"""

import pandas as pd
import os


def detect_bank(filepath: str) -> str:
    """
    Read the first 30 rows of the file and identify the bank.

    Detection strategy:
      - HDFC: contains 'HDFC' in metadata rows, or columns include 'Narration'
              and 'Withdrawal Amt.'
      - SBI:  contains 'State Bank' or 'SBI' in metadata rows, or columns
              include 'Txn Date' and 'Ref No./Cheque No.'

    Returns: 'hdfc', 'sbi', or 'unknown'
    """
    try:
        ext     = os.path.splitext(filepath)[1].lower()
        engines = ['openpyxl', 'xlrd'] if ext == '.xlsx' else ['xlrd', 'openpyxl']

        raw_df = None
        for engine in engines:
            try:
                raw_df = pd.read_excel(
                    filepath, engine=engine,
                    header=None, dtype=str, nrows=35
                )
                break
            except:
                continue

        if raw_df is None:
            return 'unknown'

        # Flatten all text in first 35 rows for scanning
        all_text = ' '.join(
            str(v).upper()
            for v in raw_df.values.flatten()
            if str(v).strip() and str(v).lower() != 'nan'
        )

        # SBI identifiers
        sbi_signals = [
            'STATE BANK OF INDIA',
            'SBIN',           # IFSC prefix
            'TXN DATE',
            'REF NO./CHEQUE NO.',
            'REF NO',
            'MICR CODE',      # SBI metadata field
            'CIF NO',         # SBI-specific field
            'DRAWING POWER',  # SBI-specific field
        ]

        # HDFC identifiers
        hdfc_signals = [
            'HDFC',
            'WITHDRAWAL AMT',
            'DEPOSIT AMT',
            'NARRATION',
            'CHQ./REF.NO',
            'CLOSING BALANCE',
        ]

        sbi_score  = sum(1 for s in sbi_signals  if s in all_text)
        hdfc_score = sum(1 for s in hdfc_signals if s in all_text)

        print(f"   [BankDetector] SBI signals: {sbi_score}, HDFC signals: {hdfc_score}")

        if sbi_score > hdfc_score and sbi_score >= 2:
            print("   [BankDetector] Detected: SBI")
            return 'sbi'
        elif hdfc_score > sbi_score and hdfc_score >= 2:
            print("   [BankDetector] Detected: HDFC")
            return 'hdfc'
        elif sbi_score == hdfc_score:
            # Tie-break: look for the most distinctive single signal
            if 'STATE BANK OF INDIA' in all_text or 'CIF NO' in all_text:
                return 'sbi'
            if 'HDFC' in all_text or 'WITHDRAWAL AMT' in all_text:
                return 'hdfc'

        print("   [BankDetector] Could not identify bank — defaulting to HDFC parser")
        return 'unknown'

    except Exception as e:
        print(f"   [BankDetector] Detection error: {e}")
        return 'unknown'


def get_parser(bank: str):
    """
    Return the appropriate parser instance for the detected bank.
    Imports are deferred to avoid circular dependencies.
    """
    if bank == 'sbi':
        from src.sbi_parser import SBIStatementParser, SBIStatementValidator
        return SBIStatementParser(), SBIStatementValidator()
    else:
        # Default to HDFC for both 'hdfc' and 'unknown'
        from src.bank_statement_parser import HDFCStatementParser, BankStatementValidator
        return HDFCStatementParser(), BankStatementValidator()