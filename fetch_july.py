import pandas as pd
import numpy as np
from supabase import create_client, Client
from datetime import datetime
import re

# ==========================================
# 1. DATABASE CONFIGURATION
# ==========================================
# Use your actual database credentials here
SUPABASE_URL = "https://upzssharcoyuwuthgjxh.supabase.co" 
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVwenNzaGFyY295dXd1dGhnanhoIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MDU3MTQ1NiwiZXhwIjoyMDk2MTQ3NDU2fQ.9sqeO__zS16Wdt6QKBm6TqyEzXRxV7wlIeidq4KWztY" 
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

malay_to_english_months = {
    'jan': 'Jan', 'feb': 'Feb', 'mac': 'Mar', 'apr': 'Apr', 
    'mei': 'May', 'jun': 'Jun', 'jul': 'Jul', 'ogo': 'Aug', 
    'sep': 'Sep', 'okt': 'Oct', 'nov': 'Nov', 'dis': 'Dec',
    'julai': 'July', 'ogos': 'August'
}

def coalesce_columns(dataframe, keywords):
    target_cols = [col for col in dataframe.columns if any(k in str(col).upper() for k in keywords)]
    merged = pd.Series(index=dataframe.index, dtype=object)
    for col in target_cols:
        s = dataframe[col].replace(r'^\s*$', np.nan, regex=True)
        merged = merged.combine_first(s)
    return merged.fillna('')

def strict_malaysian_date_parser(date_str):
    if not date_str or pd.isna(date_str): return None
    s = str(date_str).lower().strip()
    s = re.sub(r'\s*gmt\+8\s*', '', s)
    for mal, eng in malay_to_english_months.items():
        s = re.sub(r'\b' + mal + r'\b', eng, s)
        
    date_patterns = [
        "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%d %b %Y %H:%M:%S",
        "%d %B %Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"
    ]
    for pattern in date_patterns:
        try: return datetime.strptime(s, pattern)
        except ValueError: continue
    try: return pd.to_datetime(s, dayfirst=True, format='mixed')
    except: return None

print("🚀 Starting July 2026 Extraction...")

# ==========================================
# 2. LOAD & EXTRACT DATA
# ==========================================
df = pd.read_csv("raw_data.csv")
df['parsed_timestamp'] = df['Timestamp'].apply(strict_malaysian_date_parser)
df['Timestamp'] = df['parsed_timestamp']
df = df.dropna(subset=['Timestamp'])

df['raw_name'] = coalesce_columns(df, ['NAMA']).astype(str).str.upper().str.strip()
df = df[df['raw_name'] != ''] 
df['raw_age_cat'] = df.iloc[:, 1].fillna('')
df['raw_gender'] = coalesce_columns(df, ['JANTINA', 'GENDER', 'SEX']).astype(str).str.strip()
df['raw_house_block'] = coalesce_columns(df, ['RUMAH', 'BLOCK', 'ALAMAT']).astype(str).str.strip()
df['raw_activity'] = coalesce_columns(df, ['AKTIVITI', 'ACTIVITY']).astype(str).str.strip()
df['raw_session'] = coalesce_columns(df, ['SESI', 'SESSION']).astype(str).str.strip()

# ==========================================
# 3. STRICT JULY 2026 FILTER
# ==========================================
df['Month'] = df['Timestamp'].dt.month
df['Year'] = df['Timestamp'].dt.year

# This specifically isolates only July 2026
df_july = df[(df['Year'] == 2026) & (df['Month'] == 7)]

print(f"✨ Found {len(df_july)} records belonging strictly to Julai 2026.")

# ==========================================
# 4. UPLOAD ATTENDANCE LOGS
# ==========================================
print("📤 Uploading July logs to Triage (Pending Review)...")
success_count = 0

for index, row in df_july.iterrows():
    payload = {
        "form_timestamp": row['Timestamp'].isoformat(),
        "raw_name": row['raw_name'],
        "raw_age_category": str(row['raw_age_cat']),
        "review_status": "Pending Review",
        "raw_house_block": str(row.get('raw_house_block', '')),
        "raw_gender": str(row.get('raw_gender', '')),
        "raw_activity": str(row.get('raw_activity', '')),
        "raw_session": str(row.get('raw_session', ''))
    }
    
    try:
        supabase.table('attendance_raw').insert(payload).execute()
        success_count += 1
        if success_count % 50 == 0:
            print(f"   Uploaded {success_count} logs...")
    except Exception as e:
        print(f"Error on row {index}: {e}")

print(f"✅ Successfully injected {success_count} July records into your Triage pipeline!")