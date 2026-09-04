import pandas as pd
from supabase import create_client, Client

SUPABASE_URL = "https://upzssharcoyuwuthgjxh.supabase.co"
SUPABASE_KEY = "sb_publishable_A5Ak_zbX-P-SWj_Niq-HnA_cVgqUe2r"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def check_data():
    sel_tb = '2026-03'
    # Fetch ALL reviewed records for March
    all_reviewed = supabase.table('attendance_raw').select('*').eq('review_status', 'Reviewed').gte('form_timestamp', '2026-03-01').lt('form_timestamp', '2026-04-01').execute().data
    df_all = pd.DataFrame(all_reviewed)
    
    # Fetch JOINED reviewed records for March
    joined_data = supabase.table('attendance_raw').select('*, youth_profiles(*)').eq('review_status', 'Reviewed').gte('form_timestamp', '2026-03-01').lt('form_timestamp', '2026-04-01').execute().data
    df_joined = pd.DataFrame(joined_data)
    
    orphans = df_all[~df_all['id'].isin(df_joined['id'])]
    print(f"Total Reviewed (All): {len(df_all)}")
    print(f"Total Reviewed (Joined): {len(df_joined)}")
    print(f"Orphans: {len(orphans)}")
    
    if not orphans.empty:
        # Check first 5 orphans
        for i, row in orphans.head(5).iterrows():
            p_id = row['processed_by_profile_id']
            # Try to fetch this profile directly
            prof = supabase.table('youth_profiles').select('*').eq('id', p_id).execute().data
            print(f"Record {row['id']} (Name: {row['raw_name']}) -> Profile ID {p_id}: {'EXISTS' if prof else 'MISSING'}")
            if prof:
                print(f"  Profile Data: {prof[0]}")

if __name__ == "__main__":
    check_data()
