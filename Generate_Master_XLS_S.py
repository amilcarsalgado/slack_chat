import os
import sys
import glob
import pandas as pd
import numpy as np
from datetime import datetime


def sanitize_excel_field(value):
    if isinstance(value, str) and value and value[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    return df.apply(lambda col: col.map(sanitize_excel_field) if col.dtype == object else col)


# ---------------------------------------------------------
# 1. SETUP & FIND LATEST MASTER CSV 17Aug2026 __
# ---------------------------------------------------------
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_dir = os.path.join(script_dir, "CSV_files")
xls_dir = os.path.join(script_dir, "XLS_files")
os.makedirs(xls_dir, exist_ok=True)

search_pattern = os.path.join(csv_dir, "Master_Swarming_Report_*.csv")
list_of_files = glob.glob(search_pattern)

if not list_of_files:
    print("❌ No Master CSV found in the CSV_files folder. Please run the extraction script first.")
    sys.exit(1)

latest_file = max(list_of_files, key=os.path.getmtime)
print(f"📄 Loading Data from: {os.path.basename(latest_file)}")

try:
    df = pd.read_csv(latest_file)
except Exception as e:
    print(f"❌ Error reading CSV: {e}")
    sys.exit(1)

# ---------------------------------------------------------
# 2. DATA PREPARATION (Extract & Transform)
# ---------------------------------------------------------
required_cols = ['Post Timestamp', 'Channel_Source', 'Status', 'Message Text']
for col in required_cols:
    if col not in df.columns:
        print(f"❌ Missing required column '{col}' in CSV.")
        sys.exit(1)


def extract_alert_name(text):
    text_str = str(text) if pd.notna(text) else ""
    if "Alert" in text_str:
        return text_str.split("Alert")[0].strip()
    return text_str.strip()


df['Alert'] = df['Message Text'].apply(extract_alert_name)

dt_col = pd.to_datetime(df['Post Timestamp'], errors='coerce')

# Map Specific FTS Shifts based on UTC Rules
conditions_fts = [
    (dt_col.dt.hour >= 4) & (dt_col.dt.hour < 10),  # India
    (dt_col.dt.hour >= 10) & (dt_col.dt.hour < 16),  # EMEA
    (dt_col.dt.hour >= 16) & (dt_col.dt.hour < 22)  # NA
]
choices_fts = ['India', 'EMEA', 'NA']
df['Region'] = np.select(conditions_fts, choices_fts, default='Manila')
df.loc[dt_col.isna(), 'Region'] = 'Unknown'

# Calculate Hour of Week (0 to 167)
df['Hour_of_Week'] = dt_col.dt.dayofweek * 24 + dt_col.dt.hour


# Calculate relative Intra-Shift Hour (1 to 6)
def get_shift_hour(h):
    if pd.isna(h): return np.nan
    h = int(h)
    if 4 <= h < 10:
        return h - 4 + 1
    elif 10 <= h < 16:
        return h - 10 + 1
    elif 16 <= h < 22:
        return h - 16 + 1
    else:
        return (h - 22 + 1) if h >= 22 else (h + 2 + 1)


df['Shift_Hour'] = dt_col.dt.hour.apply(get_shift_hour)

# Select requested columns
df_final = df[['Post Timestamp', 'Hour_of_Week', 'Shift_Hour', 'Channel_Source', 'Status', 'Alert', 'Region']].copy()
df_final = sanitize_dataframe(df_final)

# ---------------------------------------------------------
# 3. BUILD AGGREGATIONS
# ---------------------------------------------------------
# Summary 1: Standard Regional Summary
df_summary = df_final.groupby(['Region', 'Channel_Source', 'Alert']).size().reset_index(name='Alert Count')
df_summary = df_summary.sort_values(by=['Region', 'Channel_Source', 'Alert Count'], ascending=[True, True, False])
df_summary = sanitize_dataframe(df_summary)

# Summary 2: Shift Intra-Hour Distribution (Specifically for Queue Unstaffed)
df_qu = df_final[df_final['Alert'].str.contains("Queue Unstaffed", na=False, case=False)].copy()
df_shift_dist = df_qu.groupby(['Region', 'Shift_Hour']).size().reset_index(name='QU_Count')
df_shift_totals = df_qu.groupby('Region').size().reset_index(name='Total_QU')
df_shift_dist = df_shift_dist.merge(df_shift_totals, on='Region')
df_shift_dist['Percent_of_Shift'] = round((df_shift_dist['QU_Count'] / df_shift_dist['Total_QU']) * 100, 1)
df_shift_dist = sanitize_dataframe(df_shift_dist)

# [NEW] Summary 3: Weekday Distribution (Fatigue Plot Data)
df_qu['Post Timestamp'] = pd.to_datetime(df_qu['Post Timestamp'])
df_qu['Day_of_Week'] = df_qu['Post Timestamp'].dt.day_name()
day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
df_weekday_dist = df_qu.groupby('Day_of_Week').size().reindex(day_order, fill_value=0).reset_index(name='QU_Count')
df_weekday_dist = sanitize_dataframe(df_weekday_dist)

# ---------------------------------------------------------
# 4. EXPORT TO EXCEL
# ---------------------------------------------------------
current_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
xls_filename = os.path.join(xls_dir, f"Alert_Summary_{current_timestamp}.xlsx")

print(f"\n💾 Saving Cleaned Alert Data & Summaries to Excel...")

try:
    with pd.ExcelWriter(xls_filename, engine='xlsxwriter') as writer:
        df_summary.to_excel(writer, sheet_name='Regional Summary', index=False)
        df_shift_dist.to_excel(writer, sheet_name='Shift Distribution', index=False)
        df_weekday_dist.to_excel(writer, sheet_name='Weekday Distribution', index=False)
        df_final.to_excel(writer, sheet_name='Raw Alerts', index=False)

        for sheet_name, d_frame in [('Regional Summary', df_summary), ('Shift Distribution', df_shift_dist),
                                    ('Weekday Distribution', df_weekday_dist), ('Raw Alerts', df_final)]:
            worksheet = writer.sheets[sheet_name]
            for i, col in enumerate(d_frame.columns):
                max_len = max(d_frame[col].astype(str).map(len).max(), len(col)) + 2
                worksheet.set_column(i, i, max_len)

    print(f"🎉 SUCCESS: Excel Summary created at {xls_filename}")
except Exception as e:
    print(f"❌ Error saving Excel file: {e}")
    sys.exit(1)