import pandas as pd
import numpy as np
from supabase import create_client, Client
from datetime import datetime
import re

# ==========================================
# 1. DATABASE CONFIGURATION
# ==========================================
SUPABASE_URL = "https://upzssharcoyuwuthgjxh.supabase.co"
SUPABASE_KEY = "sb_publishable_A5Ak_zbX-P-SWj_Niq-HnA_cVgqUe2r" 
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

NORMALIZATION_MAP = {
    "ALISHA HUMAIRAH": "ALISHA HUMAIRAH BINTI MUHAMAD HUZAIMI",
    "ERRYSHA": "ERRYSHA DHAWEYYA BINTI MOHD ROSDI",
    "ERRYSHA DAWEYYA BINTI MOHD ROSDI": "ERRYSHA DHAWEYYA BINTI MOHD ROSDI",
    "ERRYSHA DHAWEYYA": "ERRYSHA DHAWEYYA BINTI MOHD ROSDI",
    "ERRYSHA DHAWEYYA BINTI MOHD ROSDI": "ERRYSHA DHAWEYYA BINTI MOHD ROSDI",
    "ERRYSHA DHAWEYYADHAWEYYA BINTI MOHD ROSDI": "ERRYSHA DHAWEYYA BINTI MOHD ROSDI",
    "ERRYSYAM": "ERRYSYAM AMEER AIMAN BIN ABDULLAH",
    "ERRYSYAM AMEER AIMAN BIN ABDALLAH": "ERRYSYAM AMEER AIMAN BIN ABDULLAH",
    "MUHAMMAD FARISH HAIQAL BIN FAIRUZ": "MUHAMMAD FARISH HAIQAL BIN MOHD FAIRUZ",
    "MUHAMMDAD FARISH HAIQAL BIN MOHD FAIRUZ": "MUHAMMAD FARISH HAIQAL BIN MOHD FAIRUZ",
    "MUHD FARISH HAIQAL BIN MOHD FAAIRUZ": "MUHAMMAD FARISH HAIQAL BIN MOHD FAIRUZ",
    "MUHD FARISH HAIQAL BIN MOHD FAIRUZ": "MUHAMMAD FARISH HAIQAL BIN MOHD FAIRUZ",
    "NUR ANEESA ILYANA": "NUR ANEESA ILYANA BINTI MAZLI",
    "NUR ANEESA ILYANA BINTI": "NUR ANEESA ILYANA BINTI MAZLI",
    "SITI AISYAH": "SITI AISYAH BT HARUN",
    "ZAHIRA ARDANI": "NUR ZAHIRA ARDHANI",
    "ZAHIRA ARDHANI": "NUR ZAHIRA ARDHANI",
    "ZAHIRA ARDHANN": "NUR ZAHIRA ARDHANI",
    "NUR ZAHIRA": "NUR ZAHIRA ARDHANI",
    "NUR ZAHIRA ARDANI": "NUR ZAHIRA ARDHANI",
    "NUR ZAHIRA ARDHANI": "NUR ZAHIRA ARDHANI",
    "NUR ZAHIRA ARDHNI BNTI FAIZA": "NUR ZAHIRA ARDHANI",
    "NUR ZADA FAIHAH": "NUR ZADA FAKIHAH",
    "NUR ZADA FAQIHA": "NUR ZADA FAKIHAH",
    "NUR ZADA FAQIHA BINTI MUHAMMADUN": "NUR ZADA FAKIHAH",
    "ZADA FAQIHAH BINTI MUHAMMADUN": "NUR ZADA FAKIHAH",
    "MUHAMMAD RAMADAN": "MUHAMMAD RAMADHAN",
    "MUHAMMAD RAMADHAN FITRI": "MUHAMMAD RAMADHAN",
    "SAIDATUL UMAIRAH BINTI MAD KHAIRI": "SAIDATUL UMAIRAH BINTI MD KHAIRI",
    "SAIDATUL UMAIRAH BITNI MD KHAIRI": "SAIDATUL UMAIRAH BINTI MD KHAIRI",
    "SAIDATUL UMAIRH BINTI MD KHAIRI": "SAIDATUL UMAIRAH BINTI MD KHAIRI",
    "RASYIDI": "MUHAMMAD RASYIDI",
}

malay_to_english_months = {
    'jan': 'Jan', 'feb': 'Feb', 'mac': 'Mar', 'apr': 'Apr', 
    'mei': 'May', 'jun': 'Jun', 'jul': 'Jul', 'ogo': 'Aug', 
    'sep': 'Sep', 'okt': 'Oct', 'nov': 'Nov', 'dis': 'Dec',
    'januari': 'January', 'februari': 'February', 'mac': 'March',
    'april': 'April', 'mei': 'May', 'julai': 'July',
    'ogos': 'August', 'september': 'September', 'oktober': 'October',
    'november': 'November', 'disember': 'December'
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

def parse_age(raw_age_str):
    if not raw_age_str or pd.isna(raw_age_str): return None
    s = str(raw_age_str).lower().strip()
    nums = re.findall(r'\d+', s)
    if nums:
        num = int(nums[0])
        if num == 7 and "bawah" in s: return 6
        return num
    return None

def parse_gender(raw_gender_str):
    if not raw_gender_str or pd.isna(raw_gender_str): return None
    s = str(raw_gender_str).strip().capitalize()
    if s in ['Lelaki', 'Perempuan']: return s
    return None

print("🚀 Starting Complete Database Migration...")

# ==========================================
# 2. LOAD & INITIAL PARSE (Entire Year)
# ==========================================
print("📂 Loading raw data CSV...")
df = pd.read_csv("raw_data.csv")
df['parsed_timestamp'] = df['Timestamp'].apply(strict_malaysian_date_parser)
df['Timestamp'] = df['parsed_timestamp']
df = df.dropna(subset=['Timestamp'])

# Extract and merge all columns (Handles Google Forms Section Branching)
df['raw_name'] = coalesce_columns(df, ['NAMA']).astype(str).str.upper().str.strip()
df = df[df['raw_name'] != ''] # Exclude empty names
df['raw_age_cat'] = df.iloc[:, 1].fillna('')

# NEW: Merge and extract raw gender, house block, activity, and session [1]
df['raw_gender'] = coalesce_columns(df, ['JANTINA', 'GENDER', 'SEX']).astype(str).str.strip()
df['raw_house_block'] = coalesce_columns(df, ['RUMAH', 'BLOCK', 'ALAMAT']).astype(str).str.strip()
df['raw_activity'] = coalesce_columns(df, ['AKTIVITI', 'ACTIVITY']).astype(str).str.strip()
df['raw_session'] = coalesce_columns(df, ['SESI', 'SESSION']).astype(str).str.strip()

# Capture first joined dates across the entire year dataset (Jan-July)
first_seen_df = df.groupby('raw_name')['Timestamp'].min().reset_index()
first_joined_map = dict(zip(first_seen_df['raw_name'], first_seen_df['Timestamp']))

# ==========================================
# 3. FREQUENCY FILTERING (Threshold: 10+ visits)
# ==========================================
name_counts = df['raw_name'].value_counts()
trusted_names = name_counts[name_counts >= 10].index.tolist()
print(f"🧠 Found {len(trusted_names)} trusted profiles. All others will be sent to Triage.")

# ==========================================
# 4. STRICT MAY & JUNE 2026 FILTER
# ==========================================
df['Month'] = df['Timestamp'].dt.month
df['Year'] = df['Timestamp'].dt.year
df = df[(df['Year'] == 2026) & (df['Month'].isin([5, 6]))]
print(f"✨ Strict Filter: Kept {len(df)} records belonging strictly to Mei and Jun 2026.")

# ==========================================
# 5. SEED YOUTH PROFILES
# ==========================================
print("🧑‍🤝‍🧑 Seeding Youth Profiles...")
profile_map = {}
for name in trusted_names:
    child_logs = df[df['raw_name'] == name]
    if child_logs.empty: continue
    
    valid_ages = child_logs['raw_age_cat'].apply(parse_age).dropna().astype(int).tolist()
    consensus_age = max(set(valid_ages), key=valid_ages.count) if valid_ages else None
    
    valid_genders = child_logs['raw_gender'].apply(parse_gender).dropna().tolist()
    consensus_gender = max(set(valid_genders), key=valid_genders.count) if valid_genders else None
    
    join_date = first_joined_map.get(name)
    join_date_str = join_date.strftime('%Y-%m-%d') if pd.notna(join_date) else None
    
    res = supabase.table('youth_profiles').insert({
        "name": name,
        "age": consensus_age,
        "gender": consensus_gender,
        "first_joined": join_date_str
    }).execute()
    profile_map[name] = res.data[0]['id']

print(f"✅ Created unique Youth Profiles.")

# ==========================================
# 6. UPLOAD ATTENDANCE LOGS (Preserves All Raw Parameters!) [1]
# ==========================================
print("📤 Uploading Attendance Logs with full raw data parameters...")
success_count = 0
for index, row in df.iterrows():
    raw_name = row['raw_name']
    
    profile_id = profile_map.get(raw_name, None)
    status = 'Reviewed' if profile_id else 'Pending Review'
    
    # Fully loaded payload preserving raw columns [1]
    payload = {
        "form_timestamp": row['Timestamp'].isoformat(),
        "raw_name": raw_name,
        "raw_age_category": str(row['raw_age_cat']),
        "processed_by_profile_id": profile_id,
        "review_status": status,
        "raw_house_block": str(row.get('raw_house_block', '')),
        "raw_gender": str(row.get('raw_gender', '')),
        "raw_activity": str(row.get('raw_activity', '')),
        "raw_session": str(row.get('raw_session', ''))
    }
    
    try:
        supabase.table('attendance_raw').insert(payload).execute()
        success_count += 1
        if success_count % 100 == 0:
            print(f"   Uploaded {success_count} logs...")
    except Exception as e:
        print(f"Error on row {index}: {e}")

print(f"✅ Migrated {success_count} records. Run Streamlit to check Triage!")
print("\n🎉 MIGRATION COMPLETE!")