import streamlit as st
import pandas as pd
from supabase import create_client, Client

st.set_page_config(page_title="AYG CADS Control Panel", layout="wide")

# ==========================================
# 1. SECURE DATABASE CONNECTION
# ==========================================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except KeyError:
    st.error("🚨 CRITICAL ERROR: Database credentials missing. Check your .streamlit/secrets.toml file.")
    st.stop()

@st.cache_resource
def init_connection():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase: Client = init_connection()

# ==========================================
# 2. BULLETPROOF DATA FETCHING (PAGINATED)
# ==========================================
def get_exact_count(status, month_filter=None):
    query = supabase.table('attendance_raw').select('id', count='exact').eq('review_status', status)
    if month_filter:
        year, month = map(int, month_filter.split('-'))
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month+1:02d}-01" if month < 12 else f"{year+1}-01-01"
        query = query.gte('form_timestamp', start_date).lt('form_timestamp', end_date)
    res = query.limit(1).execute()
    return res.count if res.count else 0

@st.cache_data(ttl=600)
def load_profiles():
    all_profiles = []
    offset = 0
    while True:
        batch = supabase.table('youth_profiles').select('*').order('name').range(offset, offset + 999).execute().data
        if not batch: break
        all_profiles.extend(batch)
        offset += 1000
    df = pd.DataFrame(all_profiles)
    return df.dropna(subset=['name']) if not df.empty else df

def load_pending_reviews(month_filter=None):
    all_pending = []
    offset = 0
    while True:
        query = supabase.table('attendance_raw').select('*').eq('review_status', 'Pending Review').order('form_timestamp')
        if month_filter:
            year, month = map(int, month_filter.split('-'))
            start_date = f"{year}-{month:02d}-01"
            end_date = f"{year}-{month+1:02d}-01" if month < 12 else f"{year+1}-01-01"
            query = query.gte('form_timestamp', start_date).lt('form_timestamp', end_date)
        
        batch = query.range(offset, offset + 999).execute().data
        if not batch: break
        all_pending.extend(batch)
        offset += 1000
    return all_pending

@st.cache_data(ttl=600)
def load_all_clean_data():
    """Fetches all reviewed records across all months to calculate metrics like new attendees."""
    all_records = []
    offset = 0
    while True:
        batch = supabase.table('attendance_raw') \
            .select('*, youth_profiles(*)') \
            .eq('review_status', 'Reviewed') \
            .order('form_timestamp', desc=True) \
            .range(offset, offset + 999).execute().data
        if not batch: break
        all_records.extend(batch)
        offset += 1000
    return all_records

# ==========================================
# 3. AUTOMATION & RESOLUTION FUNCTIONS
# ==========================================
def auto_resolve_known_profiles(pending_data, profiles_df):
    if not pending_data or profiles_df.empty: return 0
    
    name_map = dict(zip(profiles_df['name'], profiles_df['id']))
    aliases = supabase.table('alias_map').select('*').execute().data
    alias_map = {a['messy_input']: a['resolved_to_profile_id'] for a in aliases}
    
    resolved_count = 0
    with st.spinner("🤖 System is analyzing and auto-categorizing records..."):
        for record in pending_data:
            raw_name = record['raw_name'].upper() if record['raw_name'] else ""
            match_id = None
            
            if raw_name in name_map:
                match_id = name_map[raw_name]
            elif raw_name in alias_map:
                match_id = alias_map[raw_name]
                
            if match_id:
                supabase.table('attendance_raw').update({
                    'processed_by_profile_id': match_id, 
                    'review_status': 'Reviewed'
                }).eq('id', record['id']).execute()
                resolved_count += 1
                
    st.cache_data.clear()
    return resolved_count

def link_to_existing(raw_id, messy_name, profile_id):
    supabase.table('attendance_raw').update({'processed_by_profile_id': profile_id, 'review_status': 'Reviewed'}).eq('id', raw_id).execute()
    try: supabase.table('alias_map').insert({'messy_input': messy_name, 'mapping_type': 'name', 'resolved_to_profile_id': profile_id}).execute()
    except: pass
    
    st.cache_data.clear()
    st.toast(f"✅ Linked '{messy_name}'!")
    st.rerun()

def create_new_profile(raw_id, messy_name, clean_name, age, gender, block):
    res = supabase.table('youth_profiles').insert({
        'name': clean_name.upper(), 
        'age': int(age) if age else None, 
        'gender': gender, 
        'house_block': block
    }).execute()
    new_id = res.data[0]['id']
    supabase.table('attendance_raw').update({'processed_by_profile_id': new_id, 'review_status': 'Reviewed'}).eq('id', raw_id).execute()
    try: supabase.table('alias_map').insert({'messy_input': messy_name, 'mapping_type': 'name', 'resolved_to_profile_id': new_id}).execute()
    except: pass
    
    st.cache_data.clear()
    st.toast(f"👤 Created & Linked '{clean_name}'!")
    st.rerun()

def eliminate_record(raw_id):
    supabase.table('attendance_raw').update({'review_status': 'Eliminated'}).eq('id', raw_id).execute()
    
    st.cache_data.clear()
    st.warning("🗑️ Record eliminated.")
    st.rerun()

# ==========================================
# 4. GLOBAL FILTERS
# ==========================================
st.sidebar.header("Filter Global (Mission 2026)")

months_available = ["2026-07", "2026-06", "2026-05"]
malay_months = {"05": "Mei", "06": "Jun", "07": "Julai"}
month_labels = {m: f"{malay_months.get(m.split('-')[1])} {m.split('-')[0]}" for m in months_available}
sel_tb = st.sidebar.selectbox("Pilih Bulan Semasa:", options=months_available, format_func=lambda x: month_labels[x])
paparan_text = month_labels[sel_tb]

if st.sidebar.button("🔄 Force Refresh All Data", use_container_width=True):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

st.sidebar.markdown("[Open Supabase Dashboard](https://supabase.com/dashboard)", unsafe_allow_html=True)

# ==========================================
# 5. USER INTERFACE (TABS)
# ==========================================
st.title("AYG Centralized Automated Database System")

pending_data_all = load_pending_reviews(month_filter=sel_tb)
pending_count = len(pending_data_all)

tab1, tab2, tab3, tab4 = st.tabs([
    f"🕵️ Triage ({pending_count})", 
    "📊 Kehadiran Analytics", 
    "📈 Advanced Statistics",
    "📝 Activity Report"
])

# ----------------- TAB 1: TRIAGE -----------------
with tab1:
    st.header(f"Requires Human Review ({paparan_text})")
    
    reviewed_count = get_exact_count('Reviewed', month_filter=sel_tb)
    total_raw = reviewed_count + pending_count
    progress = reviewed_count / total_raw if total_raw > 0 else 1.0
    
    c_p1, c_p2 = st.columns([3, 1])
    c_p1.progress(progress, text=f"Review Progress: {reviewed_count} done / {total_raw} total records")
    c_p2.metric(f"Total Pending", pending_count)

    profiles_df = load_profiles()
    
    if pending_count > 0:
        st.info("💡 Tip: Let the system resolve known names automatically before doing manual review.")
        if st.button("⚡ AUTO-RESOLVE KNOWN PROFILES", type="primary", use_container_width=True):
            cleared = auto_resolve_known_profiles(pending_data_all, profiles_df)
            st.success(f"🎉 System automatically categorized {cleared} records! Refreshing...")
            st.rerun()

    if not pending_data_all:
        st.success(f"🎉 No pending records for {paparan_text}! The pipeline is 100% categorized.")
    else:
        record = pending_data_all[0]
        st.divider()
        st.subheader(f"Triage Entry: {record['raw_name']}")
        
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Timestamp:** {record['form_timestamp'][:16].replace('T', ' ')}")
            c1.write(f"**Raw House:** {record.get('raw_house_block') or 'N/A'}")
            c2.write(f"**Raw Age:** {record['raw_age_category']}")
            c2.write(f"**Raw Gender:** {record.get('raw_gender') or 'N/A'}")
            c3.write(f"**Raw Activity:** {record.get('raw_activity') or 'No activity recorded'}")
        
        st.write("")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 🔗 Link to Existing Profile (Typo fix)")
            profile_dict = dict(zip(profiles_df['name'], profiles_df['id'])) if not profiles_df.empty else {}
            selected_profile = st.selectbox("Search real name:", options=["-- Select --"] + list(profile_dict.keys()), key="link_select")
            
            if st.button("Link & Review", type="primary", use_container_width=True):
                if selected_profile == "-- Select --": 
                    st.error("Please select a profile first.")
                else: 
                    link_to_existing(record['id'], record['raw_name'], profile_dict[selected_profile])
                    
        with col2:
            st.markdown("#### ➕ Create New Profile (First time visitor)")
            with st.form("new_prof_form", border=True):
                new_clean_name = st.text_input("Clean Full Name:", value=record['raw_name'].upper() if record['raw_name'] else "")
                f1, f2 = st.columns(2)
                new_age = f1.number_input("Exact Age:", min_value=1, max_value=99, value=12)
                new_gender = f2.selectbox("Gender:", ["-- Select --", "Lelaki", "Perempuan"], index=0)
                new_block = st.text_input("House/Block:", value=record.get('raw_house_block', ''))
                
                if st.form_submit_button("Create & Review", use_container_width=True):
                    if not new_clean_name.strip(): st.error("Please enter a clean full name.")
                    elif new_gender == "-- Select --": st.error("Please select a gender.")
                    else: create_new_profile(record['id'], record['raw_name'], new_clean_name, new_age, new_gender, new_block)
                        
        st.write("---")
        if st.button("🗑️ Eliminate Confusing/Spam Entry", type="secondary", use_container_width=True):
            eliminate_record(record['id'])

# ----------------- ANALYTICS ENGINE -----------------
def render_analytics(month_filter):
    raw_data = load_all_clean_data()
    if not raw_data:
        return
        
    flat_data = []
    for r in raw_data:
        prof = r.get('youth_profiles') or {}
        db_age = prof.get('age')
        try: final_age = int(float(db_age)) if pd.notna(db_age) and db_age is not None else -1
        except: final_age = -1
            
        flat_data.append({
            'profile_id': r['processed_by_profile_id'],
            'name': prof.get('name', 'Unknown'),
            'age': final_age,
            'gender': str(prof.get('gender')).capitalize() if prof.get('gender') else 'Unknown',
            'date': pd.to_datetime(r['form_timestamp']).date(),
            'datetime': pd.to_datetime(r['form_timestamp']),
            'TahunBulan': pd.to_datetime(r['form_timestamp']).strftime('%Y-%m'),
            'activity': str(r.get('raw_activity')).strip().title(),
            'session': str(r.get('raw_session', 'N/A')).strip().title()
        })
        
    df = pd.DataFrame(flat_data)
    if df.empty: return
    
    df['DayOfWeek'] = df['datetime'].dt.day_name()
    current_df = df[df['TahunBulan'] == month_filter]

    # --- TAB 2: KEHADIRAN (1 DATE = 1 ATTENDANCE RULE) ---
    with tab2:
        st.markdown(f"<h1 style='text-align: center; color: #1E88E5;'>Kehadiran {month_labels[month_filter]}</h1>", unsafe_allow_html=True)
        st.write("")
        
        with st.expander("ℹ️ **Nota Penjelasan & Formula Kiraan Kategori (Info Board)**", expanded=False):
            st.markdown("""
            ### 📌 Peraturan & Formula Kiraan Kehadiran
            
            > **⚠️ Syarat Utama Deduplikasi:** Kehadiran dikira berdasarkan **tarikh unik** ($1\\text{ Hari} = 1\\text{ Kehadiran}$). 
            > Jika seseorang menghantar borang lebih daripada sekali dalam sehari, ia tetap dikira sebagai **1 kehadiran** sahaja untuk hari tersebut.

            ---
            #### 1. Ringkasan Kehadiran
            * **Jumlah Kehadiran Masuk:** Jumlah bilangan hari unik kehadiran yang disahkan (*Reviewed*) dalam bulan terpilih.
            * **Purata Kehadiran Mingguan:** $\\text{Jumlah Kehadiran Unik} \\div \\text{Bilangan Minggu Beroperasi}$.
            * **Purata Kehadiran Harian:** $\\text{Jumlah Kehadiran Unik} \\div \\text{Bilangan Hari Beroperasi}$.
            * **Kehadiran Baru:** Bilangan individu unik yang **pertama kali** mendaftar masuk ke sistem pada bulan terpilih ini.

            ---
            #### 2. Kategori Kekerapan Hadir
            * 🔴 **Kehadiran A (Tinggi):** Hadir **lebih dari 15 hari** dalam bulan terpilih ($> 15\\text{ hari}$).
            * 🟡 **Kehadiran B (Sederhana):** Hadir **antara 10 hingga 14 hari** dalam bulan terpilih ($10 - 14\\text{ hari}$).
            * 🟢 **Kehadiran C (Rendah):** Hadir **9 hari atau kurang** dalam bulan terpilih ($\le 9\\text{ hari}$).

            ---
            #### 3. Pecahan Umur
            Diukur berdasarkan umur rasmi dalam profil pelajar (*youth_profiles*):
            * **6 Tahun Ke Bawah:** Umur $\le 6$ tahun
            * **7 - 9 Tahun:** Umur $7 - 9$ tahun
            * **10 - 12 Tahun:** Umur $10 - 12$ tahun
            * **13 - 15 Tahun:** Umur $13 - 15$ tahun
            * **16 - 17 Tahun:** Umur $16 - 17$ tahun
            * **18 Tahun Ke Atas:** Umur $\ge 18$ tahun
            """)

        st.divider()

        if current_df.empty: 
            st.info(f"Tiada data kehadiran direkodkan bagi bulan {month_labels[month_filter]}.")
        else:
            daily_unique = current_df.drop_duplicates(subset=['profile_id', 'date'])
            
            # 1. OVERALL STATS
            tot_kehadiran = len(daily_unique)
            active_days = current_df['date'].nunique()
            active_weeks = current_df['datetime'].dt.isocalendar().week.nunique()
            
            purata_minggu = round(tot_kehadiran / active_weeks) if active_weeks > 0 else 0
            purata_harian = round(tot_kehadiran / active_days) if active_days > 0 else 0
            
            min_dates = df.groupby('profile_id')['TahunBulan'].min().reset_index()
            new_attendees = min_dates[min_dates['TahunBulan'] == month_filter]
            kehadiran_baru_count = len(new_attendees)
            
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                with st.container(border=True):
                    st.caption("JUMLAH KEHADIRAN MASUK KE AYG BAGI BULAN SEMASA")
                    st.title(f"{tot_kehadiran}")
            with c2:
                with st.container(border=True):
                    st.caption("PURATA KEHADIRAN MASUK KE AYG DALAM SATU MINGGU")
                    st.title(f"{purata_minggu}")
            with c3:
                with st.container(border=True):
                    st.caption("PURATA KEHADIRAN MASUK KE AYG DALAM SATU HARI")
                    st.title(f"{purata_harian}")
            with c4:
                with st.container(border=True):
                    st.caption("KEHADIRAN BARU BAGI BULAN SEMASA")
                    st.title(f"{kehadiran_baru_count}")

            st.write("")
            st.subheader("Pecahan Umur")
            
            # 2. AGE CATEGORIES
            unique_students = current_df.drop_duplicates(subset=['profile_id'])
            
            under_6 = len(unique_students[unique_students['age'] <= 6])
            age_7_9 = len(unique_students[(unique_students['age'] >= 7) & (unique_students['age'] <= 9)])
            age_10_12 = len(unique_students[(unique_students['age'] >= 10) & (unique_students['age'] <= 12)])
            age_13_15 = len(unique_students[(unique_students['age'] >= 13) & (unique_students['age'] <= 15)])
            age_16_17 = len(unique_students[(unique_students['age'] >= 16) & (unique_students['age'] <= 17)])
            above_18 = len(unique_students[unique_students['age'] >= 18])

            a1, a2, a3, a4, a5, a6 = st.columns(6)
            with a1:
                with st.container(border=True):
                    st.caption("6 TAHUN KE BAWAH")
                    st.subheader(f"{under_6}")
            with a2:
                with st.container(border=True):
                    st.caption("7 - 9 TAHUN")
                    st.subheader(f"{age_7_9}")
            with a3:
                with st.container(border=True):
                    st.caption("10 - 12 TAHUN")
                    st.subheader(f"{age_10_12}")
            with a4:
                with st.container(border=True):
                    st.caption("13 - 15 TAHUN")
                    st.subheader(f"{age_13_15}")
            with a5:
                with st.container(border=True):
                    st.caption("16 - 17 TAHUN")
                    st.subheader(f"{age_16_17}")
            with a6:
                with st.container(border=True):
                    st.caption("18 TAHUN KE ATAS")
                    st.subheader(f"{above_18}")

            st.write("")
            st.subheader("Kategori Kekerapan Hadir")
            
            # 3. FREQUENCY CATEGORIES
            student_freq = daily_unique.groupby('profile_id').size()
            
            freq_A = len(student_freq[student_freq > 15])
            freq_B = len(student_freq[(student_freq >= 10) & (student_freq <= 14)])
            freq_C = len(student_freq[student_freq <= 9])

            f1, f2, f3 = st.columns(3)
            with f1:
                with st.container(border=True):
                    st.caption("KEHADIRAN A (MELEBIHI 15 KALI HADIR DALAM SEBULAN)")
                    st.subheader(f"{freq_A}")
            with f2:
                with st.container(border=True):
                    st.caption("KEHADIRAN B (HADIR ANTARA 10 HINGGA 14 KALI DALAM SEBULAN)")
                    st.subheader(f"{freq_B}")
            with f3:
                with st.container(border=True):
                    st.caption("KEHADIRAN C (KURANG DARI 9 KALI HADIR DALAM SEBULAN)")
                    st.subheader(f"{freq_C}")

    # --- TAB 3: ADVANCED STATISTICS ---
    with tab3:
        st.header("📈 Advanced Data Intelligence")
        if current_df.empty:
            st.warning("Tiada data untuk dianalisis.")
        else:
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

    # --- TAB 4: ACTIVITY REPORTING ---
    with tab4:
        st.header(f"📝 Activity Report ({month_labels[month_filter]})")
        if current_df.empty:
            st.info("Tiada data aktiviti direkodkan.")
        else:
            act_df = current_df[~current_df['activity'].str.lower().isin(['n/a', 'none', '', 'nan'])]
            a1, a2 = st.columns([1, 2])
            with a1:
                st.subheader("Top Aktiviti")
                top_activities = act_df['activity'].value_counts().reset_index()
                top_activities.columns = ['Nama Aktiviti', 'Jumlah']
                st.dataframe(top_activities, hide_index=True, use_container_width=True)
            with a2:
                st.subheader("Senarai Penyertaan")
                student_act = act_df.groupby(['name', 'activity']).size().reset_index(name='Kekerapan')
                st.dataframe(student_act, hide_index=True, use_container_width=True)

# Run Analytics
render_analytics(sel_tb)