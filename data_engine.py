"""
AYG CADS — Data Processing Engine
==================================
Processes Google Form CSV/Excel exports into clean, analytics-ready DataFrames.
No external database dependencies — everything runs in-memory via Pandas.
"""

import pandas as pd
import numpy as np
import hashlib
import re


# ==========================================
# 1. FILE PARSING
# ==========================================
def parse_uploaded_file(file):
    """
    Read a CSV or Excel file into a raw DataFrame.
    Auto-detects format by file extension.
    """
    name = file.name.lower()
    if name.endswith('.csv'):
        return pd.read_csv(file)
    elif name.endswith('.xlsx') or name.endswith('.xls'):
        return pd.read_excel(file)
    else:
        raise ValueError(f"Format fail tidak disokong: {name}. Sila guna .csv atau .xlsx")


# ==========================================
# 2. COLUMN COALESCING
# ==========================================
def coalesce_columns(df, keywords):
    """
    Merge all columns whose names contain any of the given keywords 
    into a single Series. Takes the first non-empty value per row.
    
    This handles the Google Form structure where each age category 
    creates its own set of columns (NAMA PENUH, NAMA PENUH.1, etc.)
    """
    upper_keywords = [k.upper() for k in keywords]
    target_cols = [col for col in df.columns if any(k in str(col).upper() for k in upper_keywords)]
    
    if not target_cols:
        return pd.Series([''] * len(df), index=df.index)
    
    merged = pd.Series(index=df.index, dtype=object)
    for col in target_cols:
        s = df[col].astype(str).replace(r'^\s*$', np.nan, regex=True).replace('nan', np.nan)
        merged = merged.combine_first(s)
    return merged.fillna('')


# ==========================================
# 3. FIELD PARSERS
# ==========================================
def parse_age(umur_str):
    """
    Extract numeric age from UMUR category string.
    Examples: '12 tahun' → 12, '7 tahun ke bawah' → 6 (mapped for category '6 TAHUN KE BAWAH')
    """
    if pd.isna(umur_str) or not str(umur_str).strip():
        return -1
    
    clean_str = str(umur_str).lower()
    
    # Force "7 tahun ke bawah" to be mapped to 6 so it falls into the "6 TAHUN KE BAWAH" bracket
    if '7' in clean_str and ('bawah' in clean_str or 'under' in clean_str or 'below' in clean_str):
        return 6
        
    nums = re.findall(r'\d+', clean_str)
    return int(nums[0]) if nums else -1


def generate_profile_id(name):
    """Generate a deterministic short ID from a cleaned uppercase name."""
    return hashlib.md5(name.encode('utf-8')).hexdigest()[:12]


def is_suspicious_name(name):
    """
    Flag names that likely need human triage:
    - Empty or NaN
    - Single word (likely nickname: 'ADIRA', 'AFIQ')
    - Very short (< 4 chars)
    """
    if not name or name == 'NAN' or name.strip() == '':
        return True
    words = name.strip().split()
    if len(words) <= 1:
        return True
    if len(name.strip()) < 4:
        return True
    return False


def parse_timestamp(ts_series):
    """
    Parse Google Form timestamps.
    Handles format: '2026/01/05 4:05:30 pm GMT+8'
    """
    cleaned = ts_series.astype(str).str.replace(r'\s*GMT\+\d+', '', regex=True)
    return pd.to_datetime(cleaned, errors='coerce')


# ==========================================
# 4. MAIN PROCESSING PIPELINE
# ==========================================
def process_raw_data(raw_df):
    """
    Full processing pipeline:
    1. Parse timestamps
    2. Coalesce multi-column fields (NAMA, JANTINA, RUMAH, etc.)
    3. Extract age from UMUR column
    4. Generate profile IDs
    5. Flag suspicious names for triage
    
    Returns a clean DataFrame ready for analytics.
    """
    df = raw_df.copy()
    
    # --- Timestamps ---
    df['datetime'] = parse_timestamp(df['Timestamp'])
    df = df.dropna(subset=['datetime'])
    
    # --- Coalesce repeated column groups ---
    df['name'] = coalesce_columns(df, ['NAMA']).str.upper().str.strip()
    df['raw_house'] = coalesce_columns(df, ['RUMAH', 'ALAMAT']).str.upper().str.strip()
    df['gender'] = coalesce_columns(df, ['JANTINA']).str.strip().str.capitalize()
    df['session'] = coalesce_columns(df, ['SESI KEHADIRAN']).str.strip()
    df['activity'] = coalesce_columns(df, ['AKTIVITI', 'AKTVITI']).str.strip().str.title()
    
    # --- Age ---
    if 'UMUR' in df.columns:
        df['age'] = df['UMUR'].apply(parse_age)
        df['raw_age_category'] = df['UMUR'].astype(str).str.strip()
    else:
        df['age'] = -1
        df['raw_age_category'] = 'Unknown'
    
    # --- Clean up invalid values ---
    df['gender'] = df['gender'].replace({'Nan': '', 'None': '', 'NAN': '', 'nan': ''})
    df['activity'] = df['activity'].replace({'Nan': '', 'None': '', 'NAN': '', 'nan': ''})
    df['session'] = df['session'].replace({'Nan': '', 'None': '', 'NAN': '', 'nan': ''})
    
    # --- Filter out empty names ---
    df = df[df['name'].str.len() > 0]
    df = df[df['name'] != 'NAN']
    
    # --- Generate IDs and time columns ---
    df['profile_id'] = df['name'].apply(generate_profile_id)
    df['TahunBulan'] = df['datetime'].dt.strftime('%Y-%m')
    df['date'] = df['datetime'].dt.date
    df['DayOfWeek'] = df['datetime'].dt.day_name()
    
    # --- Flag suspicious names or ages for triage ---
    def determine_status(row):
        if is_suspicious_name(row['name']):
            return 'Pending Review'
        if row['age'] >= 0 and row['age'] < 7:
            return 'Pending Review'
        return 'Reviewed'
        
    df['review_status'] = df.apply(determine_status, axis=1)
    
    # --- Select and order final columns ---
    result = df[['datetime', 'name', 'age', 'raw_age_category', 'gender', 'raw_house',
                  'session', 'activity', 'profile_id', 'TahunBulan',
                  'date', 'DayOfWeek', 'review_status']].copy()
    
    return result.reset_index(drop=True)


# ==========================================
# 5. QUERY HELPERS
# ==========================================
def get_available_months(df):
    """Return list of month strings from data, newest first."""
    months = df['TahunBulan'].unique().tolist()
    return sorted(months, reverse=True)


def get_profiles(df):
    """
    Extract unique profiles from processed data.
    Takes the most recent record for each profile_id.
    """
    reviewed = df[df['review_status'] == 'Reviewed']
    if reviewed.empty:
        return pd.DataFrame(columns=['profile_id', 'name', 'age', 'gender', 'raw_house'])
    
    profiles = reviewed.sort_values('datetime', ascending=False) \
                       .drop_duplicates(subset=['profile_id'], keep='first')
    return profiles[['profile_id', 'name', 'age', 'gender', 'raw_house']].reset_index(drop=True)


def apply_alias_map(df, alias_map):
    """
    Apply stored triage decisions to the DataFrame.
    alias_map: dict of {messy_name: target_profile_id}
    
    Updates profile_id and review_status for matched rows.
    """
    if not alias_map:
        return df
    
    df = df.copy()
    for messy_name, target_pid in alias_map.items():
        mask = (df['name'] == messy_name) & (df['review_status'] == 'Pending Review')
        df.loc[mask, 'profile_id'] = target_pid
        df.loc[mask, 'review_status'] = 'Reviewed'
    return df


def apply_eliminations(df, eliminated_names):
    """
    Mark all rows matching eliminated names as 'Eliminated'.
    eliminated_names: set of names to eliminate
    """
    if not eliminated_names:
        return df
    
    df = df.copy()
    mask = df['name'].isin(eliminated_names)
    df.loc[mask, 'review_status'] = 'Eliminated'
    return df


def apply_new_profiles(df, new_profiles):
    """
    Apply newly created profiles from triage.
    new_profiles: dict of {original_name: {'clean_name': str, 'age': int, 'gender': str}}
    """
    if not new_profiles:
        return df
    
    df = df.copy()
    for original_name, profile_info in new_profiles.items():
        mask = (df['name'] == original_name) & (df['review_status'] == 'Pending Review')
        clean_name = profile_info.get('clean_name', original_name)
        df.loc[mask, 'name'] = clean_name
        df.loc[mask, 'profile_id'] = generate_profile_id(clean_name)
        df.loc[mask, 'review_status'] = 'Reviewed'
        if profile_info.get('age'):
            df.loc[mask, 'age'] = profile_info['age']
        if profile_info.get('gender'):
            df.loc[mask, 'gender'] = profile_info['gender']
    return df


def get_effective_df(base_df, alias_map, eliminated_names, new_profiles):
    """
    Get the effective DataFrame after applying all triage decisions.
    This is the main function tabs should use for analytics.
    """
    df = apply_alias_map(base_df, alias_map)
    df = apply_eliminations(df, eliminated_names)
    df = apply_new_profiles(df, new_profiles)
    return df
