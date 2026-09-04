import pandas as pd
import numpy as np
from supabase import create_client, Client
import re

# ==========================================
# 1. CONFIGURATION
# ==========================================
SUPABASE_URL = "https://upzssharcoyuwuthgjxh.supabase.co"
SUPABASE_KEY = "sb_publishable_A5Ak_zbX-P-SWj_Niq-HnA_cVgqUe2r"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def coalesce_columns(dataframe, keywords):
    """
    Combines all columns that match any of the keywords into a single series.
    Prioritizes non-empty values.
    """
    target_cols = [col for col in dataframe.columns if any(k in str(col).upper() for k in keywords)]
    if not target_cols:
        return pd.Series([''] * len(dataframe))
    
    merged = pd.Series(index=dataframe.index, dtype=object)
    for col in target_cols:
        # Clean white space and treat empty strings as NaN for combine_first
        s = dataframe[col].astype(str).replace(r'^\s*$', np.nan, regex=True).replace('nan', np.nan)
        merged = merged.combine_first(s)
    return merged.fillna('')

print("🚀 Starting Corrected Ingestion...")

# ==========================================
# 2. LOAD AND CLEAN CSV
# ==========================================
df = pd.read_csv("raw_data.csv")

# Clean Timestamps
df['Timestamp'] = pd.to_datetime(df['Timestamp'].astype(str).str.replace(r' GMT\+8', '', regex=True), errors='coerce')
df = df.dropna(subset=['Timestamp'])

# FILTER: Start from March 2026 as requested
df = df[df['Timestamp'] >= '2026-03-01']
print(f"📊 Found {len(df)} records from March 2026 onwards.")

# Extract RAW fields using robust coalescence
df['raw_name'] = coalesce_columns(df, ['NAMA']).astype(str).str.upper().str.strip()
df['raw_house_block'] = coalesce_columns(df, ['RUMAH', 'ALAMAT']).astype(str).str.upper().str.strip()
df['raw_gender'] = coalesce_columns(df, ['JANTINA']).astype(str).str.strip().str.capitalize()
df['raw_session'] = coalesce_columns(df, ['SESI KEHADIRAN']).astype(str).str.strip()
df['raw_activity'] = coalesce_columns(df, ['AKTIVITI', 'AKTVITI']).astype(str).str.strip()
df['raw_age_cat'] = df.iloc[:, 1].fillna('') # Column index 1 is usually the "UMUR" (category)

# ==========================================
# 3. DATABASE SYNC
# ==========================================
print("🧹 Cleaning up existing March+ records in Supabase (RESTARTING MARCH FRESH)...")
supabase.table('attendance_raw').delete().gte('form_timestamp', '2026-03-01').execute()

# Also delete Jan/Feb as requested
print("🗑️ Removing Jan/Feb data as requested...")
supabase.table('attendance_raw').delete().lt('form_timestamp', '2026-03-01').execute()

print("📤 Uploading Cleaned Raw Attendance Logs...")
success_count = 0

# Prepare batches
payloads = []
for index, row in df.iterrows():
    if not row['raw_name'] or row['raw_name'] == 'NAN':
        continue
        
    payload = {
        "form_timestamp": row['Timestamp'].isoformat(),
        "raw_name": row['raw_name'],
        "raw_age_category": str(row['raw_age_cat']),
        "raw_house_block": row['raw_house_block'] if row['raw_house_block'] != 'NAN' else None,
        "raw_gender": row['raw_gender'] if row['raw_gender'] != 'Nan' else None,
        "raw_session": row['raw_session'] if row['raw_session'] != 'NAN' else None,
        "raw_activity": row['raw_activity'] if row['raw_activity'] != 'NAN' else None,
        "review_status": "Pending Review"
    }
    payloads.append(payload)

# Bulk insert
CHUNK_SIZE = 100
for i in range(0, len(payloads), CHUNK_SIZE):
    chunk = payloads[i:i + CHUNK_SIZE]
    supabase.table('attendance_raw').insert(chunk).execute()
    success_count += len(chunk)
    print(f"   Uploaded {success_count}/{len(payloads)} records...")

# ==========================================
# 4. RECOVERY (AUTO-RESOLVE)
# ==========================================
print("🧠 Re-applying system memory (Auto-resolving based on existing aliases)...")
# We use the logic from app.py to immediately recover reviews
pending = supabase.table('attendance_raw').select('*').eq('review_status', 'Pending Review').execute().data
aliases = supabase.table('alias_map').select('*').execute().data
alias_dict = {a['messy_input']: a['resolved_to_profile_id'] for a in aliases}

resolved_count = 0
for row in pending:
    if row['raw_name'] in alias_dict:
        supabase.table('attendance_raw').update({
            'processed_by_profile_id': alias_dict[row['raw_name']],
            'review_status': 'Reviewed'
        }).eq('id', row['id']).execute()
        resolved_count += 1

print(f"✨ FINISHED!")
print(f"✅ Ingested {success_count} records for March.")
print(f"⚡ Automatically recovered {resolved_count} reviews using your alias memory.")
print(f"📝 {success_count - resolved_count} records remain for Triage.")
