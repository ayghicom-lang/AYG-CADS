import pandas as pd
import numpy as np
import re
from supabase import create_client, Client

SUPABASE_URL = "https://upzssharcoyuwuthgjxh.supabase.co"
SUPABASE_KEY = "sb_publishable_A5Ak_zbX-P-SWj_Niq-HnA_cVgqUe2r" 
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def coalesce_columns(dataframe, keywords):
    target_cols = [col for col in dataframe.columns if any(k in str(col).upper() for k in keywords)]
    merged = pd.Series(index=dataframe.index, dtype=object)
    for col in target_cols:
        s = dataframe[col].replace(r'^\s*$', np.nan, regex=True)
        merged = merged.combine_first(s)
    return merged.fillna('')

# ==========================================
# THE BINARY DETECTOR (Based on your hint!)
# ==========================================
def is_full_mqa_name(name):
    name_str = str(name).strip().upper()
    
    # Check 1: Does it contain official Malaysian name markers?
    markers = [' BIN ', ' BINTI ', ' BT ', ' BTE ', ' A/L ', ' A/P ', ' ANAK ']
    if any(marker in name_str for marker in markers):
        return True
        
    # Check 2: Does it have 3 or more words? (e.g. "MUHAMMAD ARFAN AQIM")
    words = name_str.split()
    if len(words) >= 3:
        return True
        
    # If it fails both, it's a short manual input like "Arfan" or "Errysha"
    return False

print("🚀 Starting BINARY Database Migration (Full Name Detector)...")

df = pd.read_csv("raw_data.csv")
df['Timestamp'] = pd.to_datetime(df['Timestamp'].astype(str).str.replace(r' GMT\+8', '', regex=True), errors='coerce')
df = df.dropna(subset=['Timestamp'])

# EXTRACT FULL DATA
df['raw_name'] = coalesce_columns(df, ['NAMA']).astype(str).str.upper().str.strip()
df['raw_age_cat'] = df.iloc[:, 1].fillna('') 
df['raw_gender'] = coalesce_columns(df, ['JANTINA', 'GENDER']).astype(str).str.strip().str.capitalize()
df['raw_house'] = coalesce_columns(df, ['RUMAH', 'BLOCK', 'BLOK']).astype(str).str.strip()
df['raw_activity'] = coalesce_columns(df, ['AKTIVITI', 'ACTIVITY']).astype(str).str.strip()

print("\n🧑‍🤝‍🧑 Seeding Official Master Profiles...")
profile_data_dict = {}

for index, row in df.iterrows():
    name = row['raw_name']
    if not name or name == 'NAN': continue
    
    # BINARY DECISION 1: Is this a Full Name (MQA)? If no, skip profile creation!
    if not is_full_mqa_name(name):
        continue 
        
    age_str = str(row['raw_age_cat'])
    nums = re.findall(r'\d+', age_str)
    exact_age = int(nums[0]) if nums else None

    gender = row['raw_gender']
    if gender not in ['Lelaki', 'Perempuan']: gender = None
    
    # Keep the most complete data for the Master Profile
    if name not in profile_data_dict:
        profile_data_dict[name] = {
            "name": name,
            "age": exact_age,
            "gender": gender,
            "house_block": row['raw_house'] if row['raw_house'] else None
        }
    else:
        if profile_data_dict[name]['age'] is None and exact_age is not None:
            profile_data_dict[name]['age'] = exact_age
        if profile_data_dict[name]['gender'] is None and gender is not None:
            profile_data_dict[name]['gender'] = gender

profile_map = {}
for name, data in profile_data_dict.items():
    res = supabase.table('youth_profiles').insert(data).execute()
    profile_map[name] = res.data[0]['id']

print(f"   ✅ Created {len(profile_map)} Official Master Profiles.")

print("📤 Uploading Logs (Automating MQA & Triaging Others/Age Outliers)...")
success_count = 0
triage_count = 0

for index, row in df.iterrows():
    raw_name = row['raw_name']
    
    age_str = str(row['raw_age_cat'])
    nums = re.findall(r'\d+', age_str)
    age_val = int(nums[0]) if nums else None
    
    # ----------------------------------------------------
    # STRICT BINARY TRIAGE LOGIC
    # ----------------------------------------------------
    if not is_full_mqa_name(raw_name):
        # Decision 1: It's a short manual input (e.g. "Arfan"). Force to Triage!
        profile_id = None
        status = "Pending Review"
        triage_count += 1
    else:
        # Decision 2: It's a Full Name (MQA or manually typed full name).
        profile_id = profile_map.get(raw_name)
        
        # Age <=7 or >=18 MUST still be Triaged
        if not profile_id or not age_val or age_val <= 7 or age_val >= 18:
            status = "Pending Review"
            triage_count += 1
        else:
            status = "Reviewed" # Successfully cataloged automatically!
            
    payload = {
        "form_timestamp": row['Timestamp'].isoformat(),
        "raw_name": raw_name,
        "raw_age_category": str(row['raw_age_cat']),
        "raw_gender": str(row['raw_gender']),
        "raw_house_block": str(row['raw_house']),
        "raw_activity": str(row['raw_activity']),
        "processed_by_profile_id": profile_id,
        "review_status": status
    }
    
    supabase.table('attendance_raw').insert(payload).execute()
    success_count += 1
    if success_count % 100 == 0: print(f"   Uploaded {success_count} logs...")

print(f"✅ Migration Complete! {success_count} logs uploaded.")
print(f"✅ {success_count - triage_count} logs were cataloged automatically.")
print(f"🚨 {triage_count} records ('Others' inputs & Age Outliers) were sent to Triage.")