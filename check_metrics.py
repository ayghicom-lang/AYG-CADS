import pandas as pd
import data_engine as de

df = pd.read_csv('KEHADIRAN AYG HICOM 2026.csv')
p_df = de.process_raw_data(df)

print(f"Raw rows: {len(df)}")
print(f"Processed rows: {len(p_df)}")
print(f"Missing names: {(p_df['name'] == '').sum()}")
print(f"Missing ages (<0): {(p_df['age'] < 0).sum()}")
print(f"Pending triage: {(p_df['review_status'] == 'Pending Review').sum()}")

# Check deduplication manually
daily_unique = p_df.drop_duplicates(subset=['profile_id', 'date'])
print(f"Total processed rows (with duplicates): {len(p_df)}")
print(f"Total unique daily attendances (deduplicated): {len(daily_unique)}")
