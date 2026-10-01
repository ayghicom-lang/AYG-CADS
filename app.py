import streamlit as st
import pandas as pd
import numpy as np
import requests
import re
import os

st.set_page_config(page_title="AYG CADS Control Panel", layout="wide")

# ==========================================
# 0. BACKEND SERVER CONFIGURATION
# ==========================================
HF_TOKEN = os.getenv("HF_TOKEN")
BACKEND_URL = "https://adabyouthgarage-ayg-hicom-backend-server-space.hf.space"
headers = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}

def get_data_from_backend(endpoint, payload=None):
    try:
        url = f"{BACKEND_URL}/{endpoint}"
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status() 
        return response.json()
    except Exception as e:
        st.error(f"Ralat Sambungan Pelayan: {e}")
        return None

# ==========================================
# 1. UNIVERSAL PARSER & SMART ENGINES
# ==========================================
def robust_date_parse(ts):
    """
    Mengharmonikan tarikh Google Form yang bertukar format di tengah jalan.
    Menghalang tarikh Ogos/September tersalah tafsir sebagai Disember.
    """
    ts_str = str(ts).replace('GMT+8', '').strip()
    if pd.isna(ts) or ts_str in ['nan', 'None', '', 'NaT']: 
        return pd.NaT
    try:
        # Jika ada komponen masa (ada simbol ':')
        if ':' in ts_str:
            parts = re.split(r'[/ -]', ts_str.split()[0])
            if len(parts) == 3 and len(parts[0]) == 4:
                # Format YYYY/MM/DD (cth: 2026/01/06 1:53:11 PM)
                return pd.to_datetime(ts_str, errors='coerce')
            else:
                # Format MM/DD/YYYY dengan masa (cth: 8/12/2026 8:27:17 -> 12 Ogos)
                return pd.to_datetime(ts_str, format='mixed', dayfirst=False, errors='coerce')
        else:
            # Tiada masa (cth: 10/3/2026 atau 24/6/2026) -> format DD/MM/YYYY
            return pd.to_datetime(ts_str, format='mixed', dayfirst=True, errors='coerce')
    except:
        return pd.to_datetime(ts_str, errors='coerce')

def is_anomalous_name(name):
    """
    Mengesan sama ada nama adalah anomali yang perlu masuk Triage:
    - Nama panggilan 1 perkataan (cth: Bulat, Sani, Acap, Khai, L)
    - Mengandungi nombor/digit (cth: 6g, Amani7, baiyan589)
    - Teks rawak atau spam (cth: Thjkjcc, Xjj9wj, Roblox, AMBATUKAM)
    """
    if not name or pd.isna(name):
        return True
    
    clean = re.sub(r'^\d+[\.\)]\s*', '', str(name)).strip()
    
    if len(clean) < 3:
        return True
        
    if re.search(r'\d', clean):
        return True
        
    troll_words = [
        'ambatukam', 'roblox', 'kapla', 'bidadari', 'cantik', 'lawa', 
        'comel', 'tak kenal', 'unknown', 'busuk', 'c.ronaldo', 'test', 'opah'
    ]
    name_lower = clean.lower()
    if any(tw in name_lower for tw in troll_words):
        return True
        
    words = clean.split()
    if len(words) < 2:
        if not any(k in name_lower.split() for k in ['bin', 'binti', 'bt', 'b.', 'a/l', 'a/p']):
            return True
            
    if re.search(r'[bcdfghjklmnpqrstvwxyz]{5,}', name_lower):
        return True

    return False

def parse_age_smart(val):
    """Mengekstrak umur sama ada dari nombor tepat atau kategori teks Google Form"""
    s = str(val).lower()
    if 'warga emas' in s or '60' in s: return 65
    if 'dewasa' in s: return 25
    if 'remaja' in s: return 15
    if 'kanak' in s: return 10
    nums = re.findall(r'\d+', s)
    if nums:
        return int(nums[0])
    return 12

def process_and_standardize_data(file):
    """
    Membaca data secara terus dan menampung format Kota Damansara mahupun Bangi.
    Menggunakan Positional Fallback jika nama lajur tiada 'Timestamp'.
    """
    if file.name.endswith('.csv'): 
        df = pd.read_csv(file)
    else: 
        df = pd.read_excel(file)
        
    # Buang baris kosong sepenuhnya di bahagian bawah fail
    df = df.dropna(how='all')
    df.columns = [str(c).strip('\ufeff').strip() for c in df.columns]
    
    standard_df = pd.DataFrame()
    
    # 1. Lajur Tarikh
    time_cols = [c for c in df.columns if 'timestamp' in c.lower() or 'column 1' in c.lower() or 'tarikh' in c.lower()]
    if time_cols:
        standard_df['raw_time'] = df[time_cols[0]]
    else:
        standard_df['raw_time'] = df.iloc[:, 0]
        
    standard_df['datetime'] = standard_df['raw_time'].apply(robust_date_parse)
    
    # 2. Lajur Nama
    name_cols = [c for c in df.columns if 'nama' in c.lower()]
    if name_cols:
        standard_df['name'] = df[name_cols].replace(r'^\s*$', np.nan, regex=True).bfill(axis=1).iloc[:, 0]
    else:
        standard_df['name'] = df.iloc[:, 1]
        
    standard_df['name'] = standard_df['name'].astype(str).str.strip().str.upper()
    
    # 3. Lajur Umur
    age_cols = [c for c in df.columns if 'umur' in c.lower()]
    if age_cols:
        standard_df['raw_age_category'] = df[age_cols[0]]
    elif len(df.columns) > 2:
        standard_df['raw_age_category'] = df.iloc[:, 2]
    else:
        standard_df['raw_age_category'] = "N/A"
        
    standard_df['age'] = standard_df['raw_age_category'].apply(parse_age_smart)
    
    # 4. Lajur Aktiviti (Default jika cawangan tidak mengutip data ini)
    act_cols = [c for c in df.columns if 'aktiviti' in c.lower() or 'perkara' in c.lower()]
    if act_cols:
        standard_df['activity'] = df[act_cols[0]]
    else:
        standard_df['activity'] = "Aktiviti Umum / Bebas"
        
    # 5. Lajur Jantina
    gender_cols = [c for c in df.columns if 'jantina' in c.lower()]
    if gender_cols:
        standard_df['gender'] = df[gender_cols[0]]
    else:
        def infer_gender(name_str):
            n = str(name_str).upper()
            if ' BINTI ' in n or ' BT ' in n or ' BT. ' in n or ' A/P ' in n:
                return 'Perempuan'
            elif ' BIN ' in n or ' B. ' in n or ' A/L ' in n:
                return 'Lelaki'
            return 'Tidak Dinyatakan'
        standard_df['gender'] = standard_df['name'].apply(infer_gender)
        
    house_cols = [c for c in df.columns if 'rumah' in c.lower()]
    standard_df['raw_house'] = df[house_cols[0]] if house_cols else "N/A"
    
    # Buang baris tarikh rosak atau nama kosong
    standard_df = standard_df.dropna(subset=['datetime'])
    standard_df = standard_df[~standard_df['name'].isin(['', 'NAN', 'NONE', 'TIDAK DIKETAHUI'])]
    
    # Lajur Waktu Piawai
    standard_df['TahunBulan'] = standard_df['datetime'].dt.strftime('%Y-%m')
    standard_df['date'] = standard_df['datetime'].dt.date
    standard_df['DayOfWeek'] = standard_df['datetime'].dt.day_name()
    
    return standard_df

def apply_triage_rules(df, alias_map, eliminated_names, new_profiles, force_triage_names):
    """
    Mengasingkan rekod kepada 'Reviewed' (auto-sort) dan 'Pending Review' (anomali sahaja)
    """
    if df is None or df.empty: return df
    df = df.copy()
    
    def evaluate_row(row):
        raw = row['name']
        
        # 1. Keputusan manual admin yang sedia ada
        if raw in eliminated_names:
            return 'Eliminated', raw, row['age'], row['gender']
        elif raw in alias_map:
            return 'Reviewed', alias_map[raw], row['age'], row['gender']
        elif raw in new_profiles:
            p = new_profiles[raw]
            return 'Reviewed', p['clean_name'], p['age'], p['gender']
            
        # 2. Semak jika admin menggunakan butang 'Force Reset'
        if raw in force_triage_names:
            return 'Pending Review', raw, row['age'], row['gender']
            
        # 3. Autotapis: Hanya nama anomali dimasukkan ke Triage
        if is_anomalous_name(raw):
            return 'Pending Review', raw, row['age'], row['gender']
        else:
            clean_profile = re.sub(r'^\d+[\.\)]\s*', '', str(raw)).strip().upper()
            return 'Reviewed', clean_profile, row['age'], row['gender']
            
    res = df.apply(evaluate_row, axis=1, result_type='expand')
    df['review_status'] = res[0]
    df['profile_id'] = res[1]
    df['age'] = res[2]
    df['gender'] = res[3]
    return df

# ==========================================
# 2. SESSION STATE
# ==========================================
if 'processed_df' not in st.session_state: st.session_state['processed_df'] = None
if 'alias_map' not in st.session_state: st.session_state['alias_map'] = {}
if 'eliminated_names' not in st.session_state: st.session_state['eliminated_names'] = set()
if 'new_profiles' not in st.session_state: st.session_state['new_profiles'] = {}
if 'force_triage_names' not in st.session_state: st.session_state['force_triage_names'] = set()
if 'effective_df' not in st.session_state: st.session_state['effective_df'] = None

# ==========================================
# 3. ACTIONS / CALLBACKS
# ==========================================
def update_effective_df():
    if st.session_state['processed_df'] is not None:
        st.session_state['effective_df'] = apply_triage_rules(
            st.session_state['processed_df'],
            st.session_state['alias_map'],
            st.session_state['eliminated_names'],
            st.session_state['new_profiles'],
            st.session_state['force_triage_names']
        )

def handle_upload():
    if st.session_state.file_upload is not None:
        try:
            processed_df = process_and_standardize_data(st.session_state.file_upload)
            st.session_state['processed_df'] = processed_df
            update_effective_df()
            st.toast("✅ Fail berjaya dimuat naik & diproses secara Live!", icon="🎉")
        except Exception as e:
            st.error(f"Ralat sewaktu membaca fail: {e}")

def end_session():
    st.session_state['processed_df'] = None
    st.session_state['alias_map'] = {}
    st.session_state['eliminated_names'] = set()
    st.session_state['new_profiles'] = {}
    st.session_state['force_triage_names'] = set()
    st.session_state['effective_df'] = None
    st.toast("🧹 Sesi ditamatkan dan data dibersihkan.")

def link_to_existing(original_name, target_profile_id):
    st.session_state['alias_map'][original_name] = target_profile_id
    st.session_state['force_triage_names'].discard(original_name)
    update_effective_df()
    st.toast(f"✅ Dipautkan '{original_name}' ke '{target_profile_id}'!")
    st.rerun()

def create_new_profile(original_name, clean_name, age, gender):
    st.session_state['new_profiles'][original_name] = {
        'clean_name': clean_name,
        'age': age,
        'gender': gender
    }
    st.session_state['force_triage_names'].discard(original_name)
    update_effective_df()
    st.toast(f"👤 Disahkan Profil: '{clean_name}'!")
    st.rerun()

def eliminate_record(original_name):
    st.session_state['eliminated_names'].add(original_name)
    st.session_state['force_triage_names'].discard(original_name)
    update_effective_df()
    st.warning(f"🗑️ Rekod '{original_name}' dihapuskan.")
    st.rerun()

def force_reset_new_attendees(sel_tb):
    """
    Mencari pelajar yang PERTAMA KALI hadir pada bulan pilihan, 
    dan meletakkannya ke dalam Triage secara manual.
    """
    df_all = st.session_state['effective_df']
    if df_all is None or df_all.empty: return 0
    
    first_months = df_all.groupby('profile_id')['TahunBulan'].min().to_dict()
    df_all['first_seen_month'] = df_all['profile_id'].map(first_months)
    
    new_rows = df_all[(df_all['TahunBulan'] == sel_tb) & (df_all['first_seen_month'] == sel_tb)]
    raw_names_to_reset = new_rows['name'].unique().tolist()
    
    reset_count = 0
    for raw_name in raw_names_to_reset:
        st.session_state['force_triage_names'].add(raw_name)
        if raw_name in st.session_state['alias_map']:
            del st.session_state['alias_map'][raw_name]
        if raw_name in st.session_state['new_profiles']:
            del st.session_state['new_profiles'][raw_name]
        reset_count += 1
        
    update_effective_df()
    return reset_count

def get_available_months(df):
    if df is None or df.empty: return []
    return sorted(df['TahunBulan'].unique().tolist(), reverse=True)

def get_existing_profiles(df):
    if df is None or df.empty: return []
    reviewed = df[df['review_status'] == 'Reviewed']
    return sorted(reviewed['profile_id'].unique().tolist())

# ==========================================
# 4. SIDEBAR
# ==========================================
st.sidebar.title("AYG CADS Settings")
st.sidebar.header("📤 Muat Naik Data")
st.sidebar.file_uploader(
    "Data Google Form (CSV atau Excel)", 
    type=["csv", "xlsx", "xls"], 
    key="file_upload", 
    on_change=handle_upload
)

if st.session_state['processed_df'] is not None:
    if st.sidebar.button("🔚 Tamat Sesi", use_container_width=True, type="secondary"):
        end_session()
        st.rerun()

    st.sidebar.header("🗓️ Pilihan Tapisan")
    months_available = get_available_months(st.session_state['processed_df'])
    
    if months_available:
        malay_months = {"01":"Jan","02":"Feb","03":"Mac","04":"April","05":"Mei","06":"Jun","07":"Julai","08":"Ogos","09":"Sep","10":"Okt","11":"Nov","12":"Dis"}
        month_labels = {m: f"{malay_months.get(m.split('-')[1], 'Bulan')} {m.split('-')[0]}" for m in months_available}
        sel_tb = st.sidebar.selectbox("Pilih Bulan Semasa:", options=months_available, format_func=lambda x: month_labels[x])
        paparan_text = month_labels[sel_tb]
    else:
        sel_tb, paparan_text = None, "N/A"
else:
    sel_tb, paparan_text = None, "N/A"
    st.sidebar.info("Sila muat naik fail data untuk memulakan sesi.")

st.sidebar.divider()
st.sidebar.caption("AYG CADS - Enjin Multi-Branch Tempatan")

# ==========================================
# 5. MAIN UI
# ==========================================
st.title("🛡️ AYG Centralized Automated Database System")

if st.session_state['effective_df'] is None:
    st.info("👋 Selamat Datang! Sila muat naik fail CSV atau Excel dari Google Forms di menu sisi untuk memulakan analisis.")
    st.stop()

df_all = st.session_state['effective_df']

if sel_tb:
    pending_df_month = df_all[(df_all['review_status'] == 'Pending Review') & (df_all['TahunBulan'] == sel_tb)]
    reviewed_df_month = df_all[(df_all['review_status'] == 'Reviewed') & (df_all['TahunBulan'] == sel_tb)]
    current_month_df = df_all[df_all['TahunBulan'] == sel_tb]
else:
    pending_df_month, reviewed_df_month, current_month_df = pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

pending_names = pending_df_month['name'].unique().tolist()
pending_count = len(pending_names)
total_reviewed = len(reviewed_df_month)
total_records = len(current_month_df[current_month_df['review_status'] != 'Eliminated'])

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    f"🕵️ Triage Anomali ({pending_count})", 
    "📊 Analitik Kehadiran", 
    "📈 Statistik Lanjutan",
    "📝 Laporan Aktiviti",
    "🔍 Audit & Pengesahan"
])

# ----------------- TAB 1: TRIAGE -----------------
with tab1:
    st.header(f"Semakan Data Anomali & Pelik ({paparan_text})")
    st.caption("Data nama sah telah disahkan secara automatik ke dalam analitik. Hanya nama samaran/pelik/singkat sahaja diletakkan di sini untuk semakan.")
    
    progress = total_reviewed / total_records if total_records > 0 else 1.0
    c_p1, c_p2 = st.columns([3, 1])
    c_p1.progress(progress, text=f"Kemajuan: {total_reviewed} sah / {total_records} jumlah")
    c_p2.metric("Data Perlu Semakan", pending_count)

    existing_profiles = get_existing_profiles(df_all)

    if pending_count == 0:
        st.success(f"🎉 Tiada data anomali untuk {paparan_text}! Semua data telah selesai diproses.")
    else:
        target_name = pending_names[0]
        sample_record = pending_df_month[pending_df_month['name'] == target_name].iloc[0]
        
        st.divider()
        st.subheader(f"Kemasukan Anomali: {target_name}")
        
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Tarikh dilihat:** {sample_record['datetime']}")
            c1.write(f"**Rumah:** {sample_record.get('raw_house', 'N/A')}")
            c2.write(f"**Input umur:** {sample_record.get('raw_age_category', 'N/A')}")
            c2.write(f"**Input jantina:** {sample_record.get('gender', 'N/A')}")
            c3.write(f"**Aktiviti:** {sample_record.get('activity', 'N/A')}")
            c3.write(f"**Kekerapan:** {len(pending_df_month[pending_df_month['name'] == target_name])} kali")
            
        st.write("")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 🔗 Pautkan ke Nama Sebenar (Alias)")
            selected_profile_name = st.selectbox("Cari nama profil sedia ada:", options=["-- Pilih --"] + existing_profiles, key="link_select")
            if st.button("Pautkan & Sahkan", type="primary", use_container_width=True):
                if selected_profile_name == "-- Pilih --": 
                    st.error("Sila pilih profil terlebih dahulu.")
                else: 
                    link_to_existing(target_name, selected_profile_name)
                    
        with col2:
            st.markdown("#### ➕ Sahkan / Cipta Profil Baru")
            with st.form("new_prof_form", border=True):
                suggested_clean = re.sub(r'^\d+[\.\)]\s*', '', str(target_name)).strip().upper()
                new_clean_name = st.text_input("Nama Penuh (Bersih):", value=suggested_clean)
                f1, f2 = st.columns(2)
                
                sug_age = sample_record.get('age', 12)
                new_age = f1.number_input("Umur:", min_value=1, max_value=99, value=int(sug_age))
                
                sug_g_idx = 0
                sample_gender = str(sample_record.get('gender', '')).lower()
                if 'lelaki' in sample_gender: sug_g_idx = 1
                elif 'perempuan' in sample_gender: sug_g_idx = 2
                new_gender = f2.selectbox("Jantina:", ["-- Pilih --", "Lelaki", "Perempuan"], index=sug_g_idx)
                
                if st.form_submit_button("Sahkan Profil Ini", use_container_width=True):
                    create_new_profile(target_name, new_clean_name, new_age, new_gender)
                        
        st.write("---")
        if st.button("🗑️ Hapus Rekod Ini (Spam / Mengelirukan)", type="secondary"):
            eliminate_record(target_name)

    # --- RESET BUTTON ZONE ---
    st.write("")
    st.write("---")
    st.subheader("⚙️ Tetapan Reset Triage Manual")
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.markdown("**Paksa Semak Kehadiran Baru:**")
        st.caption("Pindahkan semua pelajar yang pertama kali hadir pada bulan ini ke senarai Triage untuk semakan manual.")
        if st.button("🔄 Paksa Triage: Kehadiran Baru Bulan Ini", type="primary", use_container_width=True):
            cnt = force_reset_new_attendees(sel_tb)
            st.success(f"{cnt} rekod Kehadiran Baru dipindahkan ke Triage.")
            st.rerun()
            
    with col_r2:
        st.markdown("**Batal Paksa Semakan:**")
        st.caption("Kembalikan rekod kehadiran baru yang dipaksa ke status auto-proses asal.")
        if st.button("↩️ Batal Paksa Triage (Clear Reset)", use_container_width=True):
            st.session_state['force_triage_names'].clear()
            update_effective_df()
            st.info("Status paksaan dikosongkan.")
            st.rerun()

# ----------------- ANALYTICS TABS (LIVE) -----------------
analytics_df_all = df_all[df_all['review_status'] == 'Reviewed']

if sel_tb and not analytics_df_all.empty:
    current_df = analytics_df_all[analytics_df_all['TahunBulan'] == sel_tb]

    # --- TAB 2: KEHADIRAN (1 Hari = 1 Kehadiran) ---
    with tab2:
        st.markdown(f"<h1 style='text-align: center; color: #1E88E5;'>Kehadiran {paparan_text}</h1>", unsafe_allow_html=True)
        st.write("")

        if current_df.empty: 
            st.info(f"Tiada data kehadiran yang disahkan bagi bulan {paparan_text}.")
        else:
            # SYARAT UTAMA: 1 Hari = 1 Kehadiran per pelajar
            daily_unique = current_df.drop_duplicates(subset=['profile_id', 'date'])
            tot_kehadiran = len(daily_unique)
            active_days = current_df['date'].nunique()
            active_weeks = current_df['datetime'].dt.isocalendar().week.nunique()
            
            purata_minggu = round(tot_kehadiran / active_weeks) if active_weeks > 0 else 0
            purata_harian = round(tot_kehadiran / active_days) if active_days > 0 else 0
            
            # Kira Kehadiran Baru (Pertama kali hadir dari Januari hingga bulan ini)
            first_months = df_all.groupby('profile_id')['TahunBulan'].min().to_dict()
            df_all['first_seen_month'] = df_all['profile_id'].map(first_months)
            kehadiran_baru_count = len(current_df[current_df['profile_id'].map(first_months) == sel_tb]['profile_id'].unique())
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("JUMLAH KEHADIRAN", tot_kehadiran)
            c2.metric("PURATA MINGGUAN", purata_minggu)
            c3.metric("PURATA HARIAN", purata_harian)
            c4.metric("KEHADIRAN BARU", kehadiran_baru_count)

            st.divider()
            st.subheader("Pecahan Umur (Individu Unik)")
            unique_students = current_df.drop_duplicates(subset=['profile_id'])
            
            def count_age_range(min_age, max_age):
                return len(unique_students[(unique_students['age'] >= min_age) & (unique_students['age'] <= max_age)])
            
            a1, a2, a3, a4, a5, a6 = st.columns(6)
            a1.metric("<= 6 TAHUN", count_age_range(0, 6))
            a2.metric("7 - 9 TAHUN", count_age_range(7, 9))
            a3.metric("10 - 12 TAHUN", count_age_range(10, 12))
            a4.metric("13 - 15 TAHUN", count_age_range(13, 15))
            a5.metric("16 - 17 TAHUN", count_age_range(16, 17))
            a6.metric("18+ TAHUN", count_age_range(18, 99))

            st.write("")
            st.subheader("Kategori Kekerapan Hadir")
            student_freq = daily_unique.groupby('profile_id').size()
            f1, f2, f3 = st.columns(3)
            f1.metric("KEHADIRAN A (> 15 KALI)", len(student_freq[student_freq > 15]))
            f2.metric("KEHADIRAN B (10 - 14 KALI)", len(student_freq[(student_freq >= 10) & (student_freq <= 14)]))
            f3.metric("KEHADIRAN C (<= 9 KALI)", len(student_freq[student_freq <= 9]))

    # --- TAB 3: ADVANCED STATISTICS ---
    with tab3:
        st.header("📈 Kecerdasan Data Lanjutan")
        s1, s2 = st.columns(2)
        with s1:
            st.subheader("Berdasarkan Jantina")
            st.bar_chart(current_df['gender'].value_counts(), color="#1E88E5")
            
            st.subheader("Hari Paling Sibuk")
            day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            day_counts = current_df['DayOfWeek'].value_counts().reindex(day_order).fillna(0)
            st.line_chart(day_counts, color="#E53935")

        with s2:
            st.subheader("Pecahan Kategori Umur")
            bins = [0, 6, 9, 12, 15, 17, 99]
            labels = ['0-6', '7-9', '10-12', '13-15', '16-17', '18+']
            age_buckets = pd.cut(current_df['age'], bins=bins, labels=labels, right=True).value_counts()
            st.bar_chart(age_buckets, color="#8E24AA")
            
            st.subheader("Waktu Puncak Harian (Ikut Jam)")
            hour_counts = current_df['datetime'].dt.hour.value_counts().sort_index()
            hour_counts.index = hour_counts.index.map(lambda h: f"{h:02d}:00")
            st.line_chart(hour_counts, color="#FFCA28")

    # --- TAB 4: ACTIVITY REPORTING ---
    with tab4:
        st.header(f"📝 Laporan Aktiviti ({paparan_text})")
        act_df = current_df[~current_df['activity'].isin(['', 'N/A', 'N/a', 'None'])]
        if act_df.empty:
            st.info("Tiada data aktiviti direkodkan bagi cawangan ini.")
        else:
            a1, a2 = st.columns([1, 2])
            with a1:
                st.subheader("Top Aktiviti")
                top_act = act_df['activity'].value_counts().reset_index()
                top_act.columns = ['Nama Aktiviti', 'Jumlah']
                st.dataframe(top_act, hide_index=True, use_container_width=True)
            with a2:
                st.subheader("Senarai Penyertaan Pelajar")
                student_act = act_df.groupby(['profile_id', 'activity']).size().reset_index(name='Kekerapan')
                st.dataframe(student_act, hide_index=True, use_container_width=True)

    # --- TAB 5: AUDIT & VERIFICATION ---
    with tab5:
        st.header(f"🔍 Audit & Pengesahan Data ({paparan_text})")
        available_dates = sorted(current_df['date'].unique().tolist())
        selected_date = st.selectbox("Pilih Tarikh:", available_dates)
        
        if selected_date:
            raw_day_df = current_df[current_df['date'] == selected_date].copy()
            dedup_day_df = raw_day_df.drop_duplicates(subset=['profile_id', 'date']).copy()
            
            st.write("---")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"### 📥 Borang Mentah ({len(raw_day_df)})")
                st.dataframe(raw_day_df[['name', 'datetime', 'activity']], use_container_width=True)
            with col_b:
                st.markdown(f"### 🎯 Kehadiran Bersih ({len(dedup_day_df)})")
                st.dataframe(dedup_day_df[['profile_id', 'datetime', 'activity']], use_container_width=True)
            
            st.download_button(
                label="📥 Muat Turun Data Bersih (CSV)",
                data=dedup_day_df.to_csv(index=False).encode('utf-8'),
                file_name=f"AYG_Kehadiran_Bersih_{selected_date}.csv",
                mime="text/csv",
                use_container_width=True
            )
else:
    with tab2: st.info("Sila pilih bulan di menu sisi untuk melihat analitik.")
    with tab3: st.info("Sila pilih bulan di menu sisi untuk melihat analitik.")
    with tab4: st.info("Sila pilih bulan di menu sisi untuk melihat analitik.")
    with tab5: st.info("Sila pilih bulan di menu sisi untuk melihat analitik.")
    st.sidebar.divider()
    
st.sidebar.caption("AYG CADS v1.1.0 - Multi-Branch Engine")