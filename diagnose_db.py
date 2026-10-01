import pandas as pd
from supabase import create_client, Client
import datetime

SUPABASE_URL = "https://upzssharcoyuwuthgjxh.supabase.co"
SUPABASE_KEY = "sb_publishable_A5Ak_zbX-P-SWj_Niq-HnA_cVgqUe2r"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def diagnose():
    print("--- DIAGNOSIS START ---")
    
    # Load all reviewed records
    all_records = []
    offset = 0
    while True:
        batch = supabase.table('attendance_raw') \
            .select('id, form_timestamp, raw_name, raw_age_category, processed_by_profile_id, youth_profiles(age, name)') \
            .eq('review_status', 'Reviewed') \
            .range(offset, offset + 999).execute().data
        if not batch: break
        all_records.extend(batch)
        offset += 1000
    
    df = pd.DataFrame(all_records)
    df['datetime'] = pd.to_datetime(df['form_timestamp'])
    df['date'] = df['datetime'].dt.date
    df['month'] = df['datetime'].dt.strftime('%Y-%m')
    
    print(f"Total Reviewed Records: {len(df)}")
    
    # Check for exact duplicates (same timestamp, same name)
    dupes = df[df.duplicated(subset=['form_timestamp', 'raw_name'], keep=False)]
    print(f"Exact Duplicates (Same Timestamp & Name): {len(dupes)}")
    if len(dupes) > 0:
        print(dupes[['form_timestamp', 'raw_name']].head(10))
        
    # Check for "Multi-session" records (Same Profile, Same Date)
    daily_groups = df.groupby(['processed_by_profile_id', 'date']).size()
    multi_session = daily_groups[daily_groups > 1]
    print(f"Profiles with >1 session per day: {len(multi_session)}")
    print(f"Total 'extra' sessions across all days: {multi_session.sum() - len(multi_session)}")

    # Age Group Analysis
    def get_age(row):
        p = row['youth_profiles']
        if p and isinstance(p, dict):
            return p.get('age')
        return None

    df['final_age'] = df.apply(get_age, axis=1)
    
    for m in sorted(df['month'].unique()):
        m_df = df[df['month'] == m]
        # Calculate attendance per day (unique profile per day)
        daily_att = m_df.drop_duplicates(subset=['processed_by_profile_id', 'date'])
        
        print(f"\nMonth: {m}")
        print(f"  Total Raw Records: {len(m_df)}")
        print(f"  Deduplicated Daily Attendance: {len(daily_att)}")
        
        # Breakdown by final_age
        def count_bin(low, high):
            return len(daily_att[(daily_att['final_age'] >= low) & (daily_att['final_age'] <= high)])
        
        print(f"  10-12: {count_bin(10, 12)}")
        print(f"  13-15: {count_bin(13, 15)}")
        print(f"  16-17: {count_bin(16, 17)}")
        print(f"  18+: {count_bin(18, 99)}")
        
        # Check raw_age_category distribution for this month
        print("  Raw Age Category Counts:")
        print(m_df['raw_age_category'].value_counts().head(5))

diagnose()
