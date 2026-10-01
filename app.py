# --- START OF FILE app.py ---

import streamlit as st
import pandas as pd
import numpy as np
import data_engine as de
import requests
import os

st.set_page_config(page_title="AYG CADS Control Panel", layout="wide")

# ==========================================
# 0. BACKEND SERVER CONFIGURATION
# ==========================================
# Safely load the token from the server's environment (.env file)
HF_TOKEN = os.getenv("HF_TOKEN")

# The direct URL to your Hugging Face space
BACKEND_URL = "https://adabyouthgarage-ayg-hicom-backend-server-space.hf.space"

# Headers containing your secret token to unlock the private space
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
# 1. DATA NORMALIZATION ENGINE (MULTI-BRANCH)
# ==========================================
def normalize_raw_data(df, file_name=""):
    """
    Acts as a Universal Adapter for different Google Form schemas across Branches.
    Standardizes differing columns (like Bangi's 14 name columns) into a single schema.
    """
    standard_df = pd.DataFrame()

    # 1. Cawangan Detection
    if 'AYG Bangi' in str(df.columns) or 'bangi' in file_name.lower():
        standard_df['cawangan'] = 'Bangi'
    elif 'Column 1' in df.columns or 'kota damansara' in file_name.lower():
        standard_df['cawangan'] = 'Kota Damansara'
    else:
        standard_df['cawangan'] = 'Cawangan Lain'

    # 2. Normalize Timestamp
    time_cols = [col for col in df.columns if 'timestamp' in col.lower() or 'column 1' in col.lower() or 'tarikh' in col.lower()]
    if time_cols:
        standard_df['datetime'] = df[time_cols[0]]
    else:
        standard_df['datetime'] = pd.NaT

    # 3. Normalize Name (Intercepts Branching Logic giving 14 name columns)
    name_cols = [col for col in df.columns if 'nama' in col.lower()]
    if name_cols:
        # Replaces empty strings with NaN, backfills across columns to find the single written name
        standard_df['name'] = df[name_cols].replace(r'^\s*$', np.nan, regex=True).bfill(axis=1).iloc[:, 0]
    else:
        standard_df['name'] = "Unknown"

    # 4. Normalize Age
    age_cols = [col for col in df.columns if 'umur' in col.lower()]
    if age_cols:
        standard_df['raw_age_category'] = df[age_cols[0]]
    else:
        standard_df['raw_age_category'] = "N/A"

    # 5. Normalize Activity
    act_cols = [col for col in df.columns if 'aktiviti' in col.lower() or 'perkara' in col.lower()]
    if act_cols:
        standard_df['activity'] = df[act_cols[0]]
    else:
        standard_df['activity'] = "N/A"
        
    # 6. Normalize Gender
    gender_cols = [col for col in df.columns if 'jantina' in col.lower()]
    if gender_cols:
        standard_df['gender'] = df[gender_cols[0]]
    else:
        standard_df['gender'] = "N/A"

    return standard_df


# ==========================================
# 2. SESSION STATE INITIALIZATION
# ==========================================
if 'processed_df' not in st.session_state:
    st.session_state['processed_df'] = None
if 'alias_map' not in st.session_state:
    st.session_state['alias_map'] = {}
if 'eliminated_names' not in st.session_state:
    st.session_state['eliminated_names'] = set()
if 'new_profiles' not in st.session_state:
    st.session_state['new_profiles'] = {}
if 'effective_df' not in st.session_state:
    st.session_state['effective_df'] = None

# ==========================================
# 3. ACTIONS / CALLBACKS
# ==========================================
def handle_upload():
    if st.session_state.file_upload is not None:
        try:
            # Parse raw uploaded file via data engine
            raw_df = de.parse_uploaded_file(st.session_state.file_upload)
            file_name = st.session_state.file_upload.name
            
            # Magic Step: Normalize raw data regardless of branch schema
            normalized_df = normalize_raw_data(raw_df, file_name)
            
            # Pass unified schema into your original processing engine
            processed_df = de.process_raw_data(normalized_df)
            
            st.session_state['processed_df'] = processed_df
            update_effective_df()
            st.toast(f"✅ Fail {file_name} dinormalisasi & diproses berjaya!", icon="🎉")
        except Exception as e:
            st.error(f"Error processing file: {e}")

def update_effective_df():
    if st.session_state['processed_df'] is not None:
        st.session_state['effective_df'] = de.get_effective_df(
            st.session_state['processed_df'],
            st.session_state['alias_map'],
            st.session_state['eliminated_names'],
            st.session_state['new_profiles']
        )

def end_session():
    st.session_state['processed_df'] = None
    st.session_state['alias_map'] = {}
    st.session_state['eliminated_names'] = set()
    st.session_state['new_profiles'] = {}
    st.session_state['effective_df'] = None
    st.toast("🧹 Sesi ditamatkan dan data dibersihkan.")

# Triage actions
def link_to_existing(original_name, target_profile_id):
    st.session_state['alias_map'][original_name] = target_profile_id
    update_effective_df()
    st.toast(f"✅ Berjaya dipautkan '{original_name}' ke profail sedia ada!")
    st.rerun()

def create_new_profile(original_name, clean_name, age, gender):
    st.session_state['new_profiles'][original_name] = {
        'clean_name': clean_name,
        'age': age,
        'gender': gender
    }
    update_effective_df()
    st.toast(f"👤 Cipta & Paut Berjaya '{clean_name}'!")
    st.rerun()

def eliminate_record(original_name):
    st.session_state['eliminated_names'].add(original_name)
    update_effective_df()
    st.warning(f"🗑️ Rekod untuk '{original_name}' telah dihapuskan.")
    st.rerun()

# --- NEW: FORCE RESET ACTION ---
def force_reset_new_attendees(sel_tb):
    if st.session_state['effective_df'] is None: return 0
    
    df_all = st.session_state['effective_df']
    analytics_df_all = df_all[df_all['review_status'] == 'Reviewed']
    
    if analytics_df_all.empty: return 0
    
    # 1. Identifikasi siapa 'Kehadiran Baru' pada bulan ini
    min_dates = analytics_df_all.groupby('profile_id')['TahunBulan'].min().reset_index()
    new_prof_ids = min_dates[min_dates['TahunBulan'] == sel_tb]['profile_id'].tolist()
    
    # 2. Cari nama mentah (raw name) yang berhubung dengan profile_id baru tersebut
    target_rows = df_all[(df_all['profile_id'].isin(new_prof_ids)) & (df_all['TahunBulan'] == sel_tb)]
    raw_names_to_reset = target_rows['name'].unique().tolist()
    
    # 3. Buang nama-nama ini dari memori (Ini akan memulangkan status mereka ke 'Pending Review')
    reset_count = 0
    for raw_name in raw_names_to_reset:
        if raw_name in st.session_state['new_profiles']:
            del st.session_state['new_profiles'][raw_name]
            reset_count += 1
        if raw_name in st.session_state['alias_map']:
            del st.session_state['alias_map'][raw_name]
            reset_count += 1
            
    update_effective_df()
    return reset_count


# ==========================================
# 4. SIDEBAR & FILE UPLOAD
# ==========================================
st.sidebar.title("AYG CADS Settings")

st.sidebar.header("📤 Muat Naik Data")
st.sidebar.file_uploader(
    "Muat Naik Data Google Form (CSV atau Excel)", 
    type=["csv", "xlsx", "xls"], 
    key="file_upload",
    on_change=handle_upload
)

if st.session_state['processed_df'] is not None:
    if st.sidebar.button("🔚 Tamat Sesi", use_container_width=True, type="secondary"):
        end_session()
        st.rerun()

    st.sidebar.header("🗓️ Pilihan Tapisan")
    months_available = de.get_available_months(st.session_state['processed_df'])
    
    if months_available:
        malay_months = {"01": "Jan", "02": "Feb", "03": "Mac", "04": "April", "05": "Mei", "06": "Jun", "07": "Julai", "08": "Ogos", "09": "Sep", "10": "Okt", "11": "Nov", "12": "Dis"}
        month_labels = {m: f"{malay_months.get(m.split('-')[1], 'Bulan')} {m.split('-')[0]}" for m in months_available}
        sel_tb = st.sidebar.selectbox("Pilih Bulan Semasa:", options=months_available, format_func=lambda x: month_labels[x])
        paparan_text = month_labels[sel_tb]
    else:
        sel_tb = None
        paparan_text = "N/A"
else:
    sel_tb = None
    st.sidebar.info("Sila muat naik fail data untuk memulakan sesi.")

st.sidebar.divider()
st.sidebar.caption("AYG Centralized Automated Database System - Mod Enjin Tempatan")


# ==========================================
# 5. MAIN UI
# ==========================================
st.title("🛡️ AYG Centralized Automated Database System")

if st.session_state['effective_df'] is None:
    st.info("👋 Selamat Datang! Sila muat naik fail CSV atau Excel dari Google Forms di menu sisi (sidebar) untuk mula menjana laporan analitik.")
    st.stop()

# Data setup for tabs
df_all = st.session_state['effective_df']

if sel_tb:
    pending_df_month = df_all[(df_all['review_status'] == 'Pending Review') & (df_all['TahunBulan'] == sel_tb)]
    reviewed_df_month = df_all[(df_all['review_status'] == 'Reviewed') & (df_all['TahunBulan'] == sel_tb)]
    current_month_df = df_all[df_all['TahunBulan'] == sel_tb]
else:
    pending_df_month = pd.DataFrame()
    reviewed_df_month = pd.DataFrame()
    current_month_df = pd.DataFrame()

pending_names = pending_df_month['name'].unique().tolist()
pending_count = len(pending_names)
total_reviewed = len(reviewed_df_month)
total_records = len(current_month_df[current_month_df['review_status'] != 'Eliminated'])


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    f"🕵️ Triage ({pending_count})", 
    "📊 Analitik Kehadiran", 
    "📈 Statistik Lanjutan",
    "📝 Laporan Aktiviti",
    "🔍 Audit & Pengesahan"
])

# ----------------- TAB 1: TRIAGE -----------------
with tab1:
    st.header(f"Memerlukan Semakan Manusia ({paparan_text})")
    
    progress = total_reviewed / total_records if total_records > 0 else 1.0
    
    c_p1, c_p2 = st.columns([3, 1])
    c_p1.progress(progress, text=f"Kemajuan Semakan: {total_reviewed} rekod selesai / {total_records} jumlah rekod sah")
    c_p2.metric("Jumlah Nama Tertangguh", pending_count)

    profiles_df = de.get_profiles(df_all)
    profile_dict = dict(zip(profiles_df['name'], profiles_df['profile_id'])) if not profiles_df.empty else {}

    if pending_count == 0:
        st.success(f"🎉 Tiada rekod tertangguh untuk {paparan_text}! Sistem dikategorikan 100%.")
    else:
        target_name = pending_names[0]
        sample_record = pending_df_month[pending_df_month['name'] == target_name].iloc[0]
        
        st.divider()
        st.subheader(f"Kemasukan Triage: {target_name}")
        
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Pertama kali dilihat (bulan ini):** {sample_record['datetime']}")
            # Use dictionary safe fetching via .get to prevent errors if column missing
            c1.write(f"**Rumah:** {sample_record.get('raw_house', 'N/A')}")
            c2.write(f"**Input umur:** {sample_record.get('raw_age_category', 'N/A')}")
            c2.write(f"**Input jantina:** {sample_record.get('gender', 'N/A')}")
            c3.write(f"**Aktiviti:** {sample_record.get('activity', 'N/A')}")
            c3.write(f"**Kekerapan:** {len(pending_df_month[pending_df_month['name'] == target_name])} kali")
            
        st.write("")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 🔗 Pautkan ke Profail Sedia Ada")
            selected_profile_name = st.selectbox("Cari nama sebenar:", options=["-- Pilih --"] + sorted(list(profile_dict.keys())), key="link_select")
            
            if st.button("Pautkan & Semak", type="primary", use_container_width=True):
                if selected_profile_name == "-- Pilih --": 
                    st.error("Sila pilih profail terlebih dahulu.")
                else: 
                    link_to_existing(target_name, profile_dict[selected_profile_name])
                    
        with col2:
            st.markdown("#### ➕ Cipta Profail Baru")
            with st.form("new_prof_form", border=True):
                new_clean_name = st.text_input("Nama Penuh (Bersih):", value=target_name)
                f1, f2 = st.columns(2)
                
                # Fetching suggested age safely
                sug_age = sample_record.get('age', 12)
                if pd.isna(sug_age) or sug_age <= 0: sug_age = 12
                
                new_age = f1.number_input("Umur Tepat:", min_value=1, max_value=99, value=int(sug_age))
                
                sug_g_idx = 0
                sample_gender = str(sample_record.get('gender', '')).lower()
                if 'lelaki' in sample_gender: sug_g_idx = 1
                elif 'perempuan' in sample_gender: sug_g_idx = 2
                
                new_gender = f2.selectbox("Jantina:", ["-- Pilih --", "Lelaki", "Perempuan"], index=sug_g_idx)
                
                if st.form_submit_button("Cipta & Semak", use_container_width=True):
                    if not new_clean_name.strip(): 
                        st.error("Sila masukkan nama penuh yang bersih.")
                    elif new_gender == "-- Pilih --": 
                        st.error("Sila pilih jantina.")
                    else: 
                        create_new_profile(target_name, new_clean_name, new_age, new_gender)
                        
        st.write("---")
        if st.button("🗑️ Hapus Kemasukan Mengelirukan/Spam", type="secondary", use_container_width=True):
            eliminate_record(target_name)

    # --- FORCE RESET BUTTON ZONE ---
    st.write("")
    st.write("")
    with st.expander("⚠️ Zon Bahaya: Force Reset Kehadiran Baru", expanded=False):
        st.warning(
            "Fungsi ini akan **membatalkan Triage** bagi semua individu yang direkodkan sebagai "
            "**'Kehadiran Baru'** pada bulan ini. Mereka akan dikembalikan ke senarai 'Triage' untuk disemak semula. "
            "Gunakan fungsi ini jika admin tersilap klik 'Cipta Profail Baru' untuk pelajar yang sebenarnya telah sedia ada."
        )
        if st.button("🔄 Force Reset Data Kehadiran Baru Bulan Ini", type="primary"):
            res_count = force_reset_new_attendees(sel_tb)
            if res_count > 0:
                st.success(f"Berjaya membatalkan semakan. {res_count} profil nama telah dikembalikan ke Triage.")
            else:
                st.info("Tiada data Kehadiran Baru untuk di-reset pada bulan ini.")
            st.rerun()

# ----------------- Helper for Analytics -----------------
analytics_df_all = df_all[df_all['review_status'] == 'Reviewed']

if not sel_tb or analytics_df_all.empty:
    with tab2: st.info("Selesaikan proses Triage atau muat naik data untuk melihat analitik.")
    with tab3: st.info("Selesaikan proses Triage atau muat naik data untuk melihat analitik.")
    with tab4: st.info("Selesaikan proses Triage atau muat naik data untuk melihat analitik.")
    with tab5: st.info("Selesaikan proses Triage atau muat naik data untuk melihat analitik.")
else:
    current_df = analytics_df_all[analytics_df_all['TahunBulan'] == sel_tb]

    # --- TAB 2: KEHADIRAN ---
    with tab2:
        st.markdown(f"<h1 style='text-align: center; color: #1E88E5;'>Kehadiran {paparan_text}</h1>", unsafe_allow_html=True)
        st.write("")
        
        with st.expander("ℹ️ **Nota Penjelasan & Formula Kiraan Kategori (Info Board)**", expanded=False):
            st.markdown("""
            ### 📌 Peraturan & Formula Kiraan Kehadiran
            > **⚠️ Syarat Utama Deduplikasi:** Kehadiran dikira berdasarkan **tarikh unik** ($1\\text{ Hari} = 1\\text{ Kehadiran}$). 
            > Jika seseorang menghantar borang lebih daripada sekali dalam sehari, ia tetap dikira sebagai **1 kehadiran** sahaja untuk hari tersebut.
            """)

        st.divider()

        if current_df.empty: 
            st.info(f"Tiada data kehadiran yang disahkan bagi bulan {paparan_text}.")
        else:
            daily_unique = current_df.drop_duplicates(subset=['profile_id', 'date'])
            
            tot_kehadiran = len(daily_unique)
            active_days = current_df['date'].nunique()
            active_weeks = current_df['datetime'].dt.isocalendar().week.nunique()
            
            purata_minggu = round(tot_kehadiran / active_weeks) if active_weeks > 0 else 0
            purata_harian = round(tot_kehadiran / active_days) if active_days > 0 else 0
            
            min_dates = analytics_df_all.groupby('profile_id')['TahunBulan'].min().reset_index()
            new_attendees = min_dates[min_dates['TahunBulan'] == sel_tb]
            kehadiran_baru_count = len(new_attendees)
            
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                with st.container(border=True):
                    st.caption("JUMLAH KEHADIRAN MASUK")
                    st.title(f"{tot_kehadiran}")
            with c2:
                with st.container(border=True):
                    st.caption("PURATA MINGGUAN")
                    st.title(f"{purata_minggu}")
            with c3:
                with st.container(border=True):
                    st.caption("PURATA HARIAN")
                    st.title(f"{purata_harian}")
            with c4:
                with st.container(border=True):
                    st.caption("KEHADIRAN BARU")
                    st.title(f"{kehadiran_baru_count}")

            st.write("")
            st.subheader("Pecahan Umur (Individu Unik)")
            
            unique_students = current_df.drop_duplicates(subset=['profile_id'])
            
            def count_age_range(min_age, max_age):
                if 'age' not in unique_students.columns: return 0
                return len(unique_students[(unique_students['age'] >= min_age) & (unique_students['age'] <= max_age)])
            
            a1, a2, a3, a4, a5, a6 = st.columns(6)
            a1.metric("6 TAHUN KE BAWAH", count_age_range(0, 6))
            a2.metric("7 - 9 TAHUN", count_age_range(7, 9))
            a3.metric("10 - 12 TAHUN", count_age_range(10, 12))
            a4.metric("13 - 15 TAHUN", count_age_range(13, 15))
            a5.metric("16 - 17 TAHUN", count_age_range(16, 17))
            a6.metric("18 TAHUN KE ATAS", count_age_range(18, 99))

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
        if current_df.empty:
            st.warning("Tiada data untuk dianalisis.")
        else:
            s1, s2 = st.columns(2)
            with s1:
                st.subheader("Berdasarkan Jantina")
                if 'gender' in current_df.columns:
                    st.bar_chart(current_df['gender'].value_counts(), color="#1E88E5")
                
                st.subheader("Hari Paling Sibuk")
                if 'DayOfWeek' in current_df.columns:
                    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    day_counts = current_df['DayOfWeek'].value_counts().reindex(day_order).fillna(0)
                    st.line_chart(day_counts, color="#E53935")

            with s2:
                st.subheader("Pecahan Kategori Umur")
                if 'age' in current_df.columns:
                    bins = [0, 6, 9, 12, 15, 17, 99]
                    labels = ['0-6', '7-9', '10-12', '13-15', '16-17', '18+']
                    age_buckets = pd.cut(current_df['age'], bins=bins, labels=labels, right=True).value_counts()
                    st.bar_chart(age_buckets, color="#8E24AA")
                
                st.subheader("Waktu Puncak Harian (Ikut Jam)")
                if 'datetime' in current_df.columns:
                    hour_counts = current_df['datetime'].dt.hour.value_counts().sort_index()
                    hour_counts.index = hour_counts.index.map(lambda h: f"{h:02d}:00")
                    st.line_chart(hour_counts, color="#FFCA28")

    # --- TAB 4: ACTIVITY REPORTING ---
    with tab4:
        st.header(f"📝 Laporan Aktiviti ({paparan_text})")
        if current_df.empty:
            st.info("Tiada data aktiviti direkodkan.")
        else:
            act_df = current_df[~current_df['activity'].isin(['', 'N/A', 'N/a', 'None'])]
            if act_df.empty:
                st.info("Tiada data aktiviti yang sah.")
            else:
                a1, a2 = st.columns([1, 2])
                with a1:
                    st.subheader("Top Aktiviti")
                    top_act = act_df['activity'].value_counts().reset_index()
                    top_act.columns = ['Nama Aktiviti', 'Jumlah']
                    st.dataframe(top_act, hide_index=True, use_container_width=True)
                with a2:
                    st.subheader("Senarai Penyertaan Pelajar")
                    student_act = act_df.groupby(['name', 'activity']).size().reset_index(name='Kekerapan')
                    st.dataframe(student_act, hide_index=True, use_container_width=True)

    # --- TAB 5: AUDIT & VERIFICATION ---
    with tab5:
        st.header(f"🔍 Audit & Pengesahan Data ({paparan_text})")
        st.markdown("Gunakan alat ini untuk menyemak silang pengiraan mesin dengan data mentah.")
        
        if current_df.empty:
            st.info("Tiada data untuk disemak.")
        else:
            st.subheader("1. Pilih Tarikh Untuk Disemak")
            if 'date' in current_df.columns:
                available_dates = sorted(current_df['date'].unique().tolist())
                selected_date = st.selectbox("Tarikh:", available_dates)
                
                if selected_date:
                    raw_day_df = current_df[current_df['date'] == selected_date].copy()
                    dedup_day_df = raw_day_df.drop_duplicates(subset=['profile_id', 'date']).copy()
                    
                    st.write("---")
                    col_a, col_b = st.columns(2)
                    
                    with col_a:
                        st.markdown(f"### 📥 Borang Mentah (Jumlah: **{len(raw_day_df)}**)")
                        st.dataframe(raw_day_df[['name', 'datetime', 'activity']], use_container_width=True)
                        
                    with col_b:
                        st.markdown(f"### 🎯 Kehadiran Selepas Deduplikasi (Jumlah: **{len(dedup_day_df)}**)")
                        st.dataframe(dedup_day_df[['name', 'datetime', 'activity']], use_container_width=True)
                    
                    st.write("---")
                    st.subheader("2. Kenalpasti Pendua (Pengecam Pendua)")
                    
                    counts = raw_day_df['name'].value_counts()
                    dupes = counts[counts > 1]
                    
                    if not dupes.empty:
                        st.warning(f"⚠️ Terdapat **{len(dupes)}** individu yang menghantar borang lebih dari sekali pada tarikh ini.")
                        st.table(dupes.reset_index().rename(columns={'name': 'Nama', 'count': 'Jumlah Hantar Borang'}))
                    else:
                        st.success("✅ Tiada penghantaran borang pendua dikesan pada tarikh ini.")
                    
                    st.write("---")
                    st.subheader("3. Export Untuk Semakan Manual")
                    st.download_button(
                        label="📥 Muat Turun Data Bersih (CSV)",
                        data=dedup_day_df.to_csv(index=False).encode('utf-8'),
                        file_name=f"AYG_Kehadiran_Bersih_{selected_date}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )