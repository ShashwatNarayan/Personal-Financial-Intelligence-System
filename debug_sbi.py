import pandas as pd

filepath = r"Email_Statement_12062026092225670284.xlsx"

for engine in ['openpyxl', 'xlrd']:
    try:
        df = pd.read_excel(filepath, engine=engine, header=None, dtype=str)
        print(f"\nEngine: {engine} — {len(df)} rows loaded")
        print("\nFirst 30 rows (non-empty cells only):")
        for i in range(min(30, len(df))):
            vals = [str(v).strip() for v in df.iloc[i].values if str(v).strip() and str(v).lower() != 'nan']
            if vals:
                print(f"  Row {i:2d}: {vals}")
        break
    except Exception as e:
        print(f"Engine {engine} failed: {e}")
