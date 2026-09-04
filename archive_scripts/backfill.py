import pandas as pd
import requests
import json
import re
import numpy as np

SUPABASE_URL = "https://upzssharcoyuwuthgjxh.supabase.co"
SUPABASE_KEY = "sb_publishable_A5Ak_zbX-P-SWj_Niq-HnA_cVgqUe2r"

print("🚀 Loading CSV for Definitive Backfill...")
df = pd.read_csv("raw_data.csv")

# 1. Clean Timestamps
df['Timestamp'] = df['Timestamp'].astype(str).str.replace(r' GMT\+8', '', regex=True)
df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%Y/%m/%d %I:%M:%S %p', errors='coerce')
df = df.dropna(subset=['Timestamp'])
# --- 🧠 THE "STRUCTURED DYNAMIC MAPPING" ---
# This version finds the best field mapping based on keywords, ensuring all data is captured.
def extract_row_data(row):
    cat_raw = str(row.iloc[1]).strip()
    cat = cat_raw.lower()

    # Identify non-null fields
    data_only = row.iloc[2:]
    valid_mask = data_only.notna() & (data_only.astype(str).str.strip() != "")
    non_null_vals = data_only[valid_mask].values.tolist()

    if not non_null_vals: return None, None, None, None, None, None, cat_raw

    # Extract name (first valid field)
    name = non_null_vals[0]

    # Extract age
    age_num = 0
    nums = re.findall(r'\d+', cat)
    if nums: age_num = int(nums[0])

    # Extract others based on field count
    gender, house, session, activity = "", "", "", ""
    if len(non_null_vals) >= 5:
        # Assuming block order: Name, House, Gender, Session, Activity
        # 18+ block is slightly different in the form
        if '18 tahun' in cat:
            gender, house, session, activity = non_null_vals[1:5]
        else:
            house, gender, session, activity = non_null_vals[1:5]
    elif len(non_null_vals) >= 2:
        house = non_null_vals[1]

    # Clean strings
    if name: name = str(name).strip().upper()
    if gender: gender = str(gender).strip().capitalize()
    if house: house = str(house).strip().upper()

    return name, age_num, gender, house, session, activity, cat_raw


# --- 🧪 NORMALIZATION & OVERRIDES ---
NORMALIZATION_MAP = {
    "ERRYSYAM": "ERRYSYAM AMEER AIMAN BIN ABDULLAH",
    "AIMAN": "MUHAMMAD SHAHAZIQ AIMAN",
    "RASYIDI": "MUHAMMAD RASYIDI",
}

SENARAI_19_TAHUN_CLEAN = [
    "MUHAMAD FITRI ASHARI BIN MUHAMAD FAIZAN", "MAIZATULAKMA LISA AQILAH BINTI ABDULLAH",
    "NUR PUTRI RAMADHANI AKMA BIN MOHD NOOR AZLAN", "THIRAN A/L VIJAYA NATHAN",
    "NURFATIN UMAIRAH BINTI ABD RAHIM", "MUHAMMAD IDHAM BIN ROSLAN",
    "NURUL SUFI AIDURA BINTI MOHAMAD KHAIR", "MUHAMMAD AMMAR SAUQI BIN KAMA",
    "ALIFF", "SHAIRAH BINTI ROSLAN", "MOHAMAD AZRUL AZRAI BIN HISHAM",
    "MOHAMAD AZRUL AZIEM BIN HISHAM", "MUHAMMAD NAQIB IRHAS BIN RAMLAN",
    "LUTH MIKHAIL BIN AHMAD NOOR", "ADAM ZAKRY BIN ZUL AMALI",
    "MUHAMMAD ALIFF FURQAN BIN LOKMAN"
]
SENARAI_19_TAHUN_CLEAN = [n.upper().strip() for n in SENARAI_19_TAHUN_CLEAN]

# 2. Process everything into a clean list
clean_data = []
for idx, row in df.iterrows():
    name, age, gender, house, session, activity, cat_raw = extract_row_data(row)
    
    if name:
        # Apply Normalization
        if name in NORMALIZATION_MAP: name = NORMALIZATION_MAP[name]
        
        # Apply 19+ Workaround
        if age == 18 and name in SENARAI_19_TAHUN_CLEAN:
            age = 19
            
        clean_data.append({
            "waktu_submit": row['Timestamp'].isoformat(),
            "kategori_umur": str(cat_raw),
            "nama_penuh": str(name),
            "umur_tepat": str(age),
            "no_rumah": str(house),
            "jantina": str(gender).strip().capitalize() if pd.notna(gender) else "",
            "sesi_kehadiran": str(session),
            "aktiviti": str(activity)
        })

print(f"✅ Data processed. Found {len(clean_data)} valid records.")

# --- ⚡ BULK UPLOAD ---
headers = {
    "apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", 
    "Content-Type": "application/json", "Prefer": "return=minimal"
}
endpoint = f"{SUPABASE_URL}/rest/v1/attendance_logs"

CHUNK_SIZE = 200
success_total = 0
for i in range(0, len(clean_data), CHUNK_SIZE):
    chunk = clean_data[i:i + CHUNK_SIZE]
    try:
        response = requests.post(endpoint, headers=headers, data=json.dumps(chunk))
        if response.status_code in [200, 201]:
            success_total += len(chunk)
            print(f"📤 Uploaded {i} to {min(i + CHUNK_SIZE, len(clean_data))}...")
        else: print(f"❌ Error: {response.text}")
    except Exception as e: print(f"❌ Network error: {e}")

print(f"\n✨ FINISHED! {success_total} records synced to Supabase using STRICT MAPPING.")
