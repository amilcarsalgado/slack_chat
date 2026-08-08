import os
import sys
import glob
import pandas as pd
import numpy as np
from datetime import datetime

# [FIX M-4] Excel formula injection sanitiser.
def sanitize_excel_field(value):
    if isinstance(value, str) and value and value[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value

def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply Excel formula-injection sanitisation to all string columns in a DataFrame."""
    return df.apply(lambda col: col.map(sanitize_excel_field) if col.dtype == object else col)

# ---------------------------------------------------------
# 1. SETUP & FIND LATEST MASTER CSV
# ---------------------------------------------------------
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_dir = os.path.join(script_dir, "CSV_files")
xls_dir = os.path.join(script_dir, "XLS_files")
os.makedirs(xls_dir, exist_ok=True)

search_pattern = os.path.join(csv_dir, "Master_Swarming_Report_*.csv")
list_of_files = glob.glob(search_pattern)

if not list_of_files:
    print("❌ No Master CSV found in the CSV_files folder. Please run the Main_SWC_02.py script first.")
    sys.exit(1)

latest_file = max(list_of_files, key=os.path.getmtime)
print(f"📄 Loading Data from: {os.path.basename(latest_file)}")

df = pd.read_csv(latest_file)

# ---------------------------------------------------------
# 2. DATA PREPARATION & ADVANCED METRICS
# ---------------------------------------------------------
df['Post Timestamp'] = pd.to_datetime(df['Post Timestamp'], errors='coerce')
df['First Reply Timestamp'] = pd.to_datetime(df['First Reply Timestamp'], errors='coerce')
df['MTTA_Seconds'] = (df['First Reply Timestamp'] - df['Post Timestamp']).dt.total_seconds()

def seconds_to_hhmmss(seconds):
    if pd.isna(seconds): return "00:00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def analyze_thread_complexity(row):
    breakdown = str(row['Repliers Breakdown'])
    replies = row['Number of Replies']
    unique_experts = 0
    is_sme_dominated = 0

    if breakdown and breakdown.lower() != 'nan':
        users = breakdown.split(';')
        unique_experts = len([u for u in users if ':' in u])

        if replies > 3:
            max_user_replies = 0
            for u in users:
                if ':' in u:
                    try:
                        count = int(u.rsplit(':', 1)[1].strip())
                    except (ValueError, IndexError):
                        continue
                    if count > max_user_replies:
                        max_user_replies = count
            if max_user_replies > 0 and (max_user_replies / replies) > 0.5:
                is_sme_dominated = 1

    return pd.Series([unique_experts, is_sme_dominated])

df[['Unique_Experts_Count', 'Is_SME_Dominated']] = df.apply(analyze_thread_complexity, axis=1)

def get_fiscal_info(date_val):
    if pd.isna(date_val): return pd.Series([None, None, None])
    month = date_val.month
    year = date_val.year
    if month in [11, 12]:
        fy, fq = year + 1, 1
    elif month == 1:
        fy, fq = year, 1
    elif month in [2, 3, 4]:
        fy, fq = year, 2
    elif month in [5, 6, 7]:
        fy, fq = year, 3
    else:
        fy, fq = year, 4
    return pd.Series([fy, fq, fy * 4 + fq])

df[['FY', 'FQ', 'FQ_Index']] = df['Post Timestamp'].apply(get_fiscal_info)

curr_dt = datetime.now()
curr_fy, curr_fq, curr_fq_index = get_fiscal_info(curr_dt)

df = df[(df['FQ_Index'] >= curr_fq_index - 3) & (df['FQ_Index'] <= curr_fq_index)].copy()

def make_label(row):
    label = f"FQ{int(row['FQ'])} '{str(int(row['FY']))[-2:]}"
    if row['FQ_Index'] == curr_fq_index: label += " (TD)"
    return label

df['FQ_Label'] = df.apply(make_label, axis=1)

replier_records = []
for index, row in df.iterrows():
    breakdown = str(row['Repliers Breakdown'])
    if breakdown and breakdown.lower() != 'nan':
        users = breakdown.split(';')
        for u in users:
            if ':' in u:
                name, count = u.rsplit(':', 1)
                replier_records.append({
                    'Channel': row['Channel_Source'],
                    'FQ_Index': row['FQ_Index'],
                    'FQ_Label': row['FQ_Label'],
                    'Name': name.strip(),
                    'Replies': int(count.strip())
                })
df_repliers = pd.DataFrame(replier_records)

# ---------------------------------------------------------
# 3. BUILD TAB 1: OVERVIEW
# ---------------------------------------------------------
overview_data = []
all_channels = ['Global'] + list(df['Channel_Source'].unique())

def build_overview_row(group, fq_label, ch_name, rep_group):
    q_cases = len(group)
    q_engaged = len(group[group['Number of Replies'] > 0])
    eng_rate = round((q_engaged / q_cases * 100), 2) if q_cases > 0 else 0

    avg_experts = round(group[group['Unique_Experts_Count'] > 0]['Unique_Experts_Count'].mean(), 2)
    if pd.isna(avg_experts): avg_experts = 0

    p90_replies = round(group['Number of Replies'].quantile(0.9), 1)
    if pd.isna(p90_replies): p90_replies = 0

    return {
        'Channel': ch_name,
        'Fiscal Quarter': fq_label,
        'Total Swarming Threads': q_cases,
        'Engagement Rate (%)': eng_rate,
        'Total Messages': q_cases + group['Number of Replies'].sum(),
        'Average MTTA (hh:mm:ss)': seconds_to_hhmmss(group['MTTA_Seconds'].mean()),
        'Avg Unique Experts': avg_experts,
        'SME Dominated Threads': group['Is_SME_Dominated'].sum(),
        'P90 Replies': p90_replies,
        'Unique Contributors': rep_group['Name'].nunique() if not rep_group.empty else 0,
        'Unique Originators': group['Originator'].nunique()
    }

for ch in all_channels:
    ch_df = df if ch == 'Global' else df[df['Channel_Source'] == ch]
    ch_repliers = df_repliers if ch == 'Global' else df_repliers[df_repliers['Channel'] == ch]

    grouped = ch_df.groupby(['FQ_Index', 'FQ_Label'])
    for (fq_idx, fq_label), group in grouped:
        q_reps = ch_repliers[ch_repliers['FQ_Index'] == fq_idx] if not ch_repliers.empty else pd.DataFrame()
        overview_data.append(build_overview_row(group, fq_label, ch, q_reps))

    overview_data.append(build_overview_row(ch_df, 'Total (Rolling 4Q)', ch, ch_repliers))

df_overview = pd.DataFrame(overview_data)

# ---------------------------------------------------------
# 4. BUILD TAB 2: TOP CONTRIBUTORS
# ---------------------------------------------------------
top_contribs_data = []
channels = df['Channel_Source'].unique()

for ch in channels:
    ch_reps = df_repliers[df_repliers['Channel'] == ch]
    if ch_reps.empty: continue

    grouped = ch_reps.groupby(['FQ_Index', 'FQ_Label'])
    for (fq_idx, fq_label), group in grouped:
        user_totals = group.groupby('Name')['Replies'].sum().reset_index().sort_values(by='Replies',
                                                                                       ascending=False).head(5)
        row_data = {'Channel': ch, 'Fiscal Quarter': fq_label}
        for i in range(5):
            row_data[f'Top {i + 1}'] = f"{user_totals.iloc[i]['Name']} ({user_totals.iloc[i]['Replies']})" if i < len(
                user_totals) else ""
        top_contribs_data.append(row_data)

    user_totals = ch_reps.groupby('Name')['Replies'].sum().reset_index().sort_values(by='Replies',
                                                                                     ascending=False).head(5)
    row_data = {'Channel': ch, 'Fiscal Quarter': 'Total (Rolling 4Q)'}
    for i in range(5):
        row_data[f'Top {i + 1}'] = f"{user_totals.iloc[i]['Name']} ({user_totals.iloc[i]['Replies']})" if i < len(
            user_totals) else ""
    top_contribs_data.append(row_data)

df_top_ch = pd.DataFrame(top_contribs_data) if top_contribs_data else pd.DataFrame()

# ---------------------------------------------------------
# 5. BUILD TAB 3: CONTRIBUTOR ALL STAR
# ---------------------------------------------------------
all_stars_data = []

if not df_repliers.empty:
    grouped = df_repliers.groupby(['FQ_Index', 'FQ_Label'])
    for (fq_idx, fq_label), group in grouped:
        q_stars = group.groupby('Name').agg(
            Total_Replies=('Replies', 'sum'),
            Channels_Active=('Channel', 'nunique'),
            Channel_List=('Channel', lambda x: ', '.join(sorted(x.unique())))
        ).reset_index()
        q_stars = q_stars.sort_values(by='Total_Replies', ascending=False).reset_index(drop=True)
        q_stars.insert(0, 'Rank', q_stars.index + 1)
        q_stars.insert(0, 'Fiscal Quarter', fq_label)
        q_stars['FQ_Index'] = fq_idx
        all_stars_data.append(q_stars)

    t_stars = df_repliers.groupby('Name').agg(
        Total_Replies=('Replies', 'sum'),
        Channels_Active=('Channel', 'nunique'),
        Channel_List=('Channel', lambda x: ', '.join(sorted(x.unique())))
    ).reset_index()
    t_stars = t_stars.sort_values(by='Total_Replies', ascending=False).reset_index(drop=True)
    t_stars.insert(0, 'Rank', t_stars.index + 1)
    t_stars.insert(0, 'Fiscal Quarter', 'Total (Rolling 4Q)')
    t_stars['FQ_Index'] = 999999
    all_stars_data.append(t_stars)

    df_all_star = pd.concat(all_stars_data, ignore_index=True).sort_values(by=['FQ_Index', 'Rank']).drop(
        columns=['FQ_Index'])
    df_all_star = df_all_star.rename(
        columns={'Total_Replies': 'Total Replies', 'Channels_Active': 'Channels Active In', 'Channel_List': 'Channel List'}
    )
else:
    df_all_star = pd.DataFrame(columns=['Fiscal Quarter', 'Rank', 'Name', 'Total Replies', 'Channels Active In', 'Channel List'])

# ---------------------------------------------------------
# 6. EXPORT TO EXCEL WITH TIMESTAMP AND GLOSSARY
# ---------------------------------------------------------
current_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
xls_filename = os.path.join(xls_dir, f"Summary_Report_{current_timestamp}.xlsx")

print(f"\n💾 Saving Executive Summary to Excel...")

with pd.ExcelWriter(xls_filename, engine='xlsxwriter') as writer:
    sanitize_dataframe(df_overview).to_excel(writer, sheet_name='Overview', index=False)

    if not df_top_ch.empty:
        sanitize_dataframe(df_top_ch).to_excel(writer, sheet_name='Top Contributors', index=False)
    sanitize_dataframe(df_all_star).to_excel(writer, sheet_name='Contributor All Star', index=False)

    workbook = writer.book
    worksheet_overview = writer.sheets['Overview']

    start_row = len(df_overview) + 2
    bold_format = workbook.add_format({'bold': True})
    italic_format = workbook.add_format({'italic': True, 'font_color': '#555555'})

    worksheet_overview.write_string(start_row, 0, "Metric Definitions (Trailing 4 Quarters):", bold_format)

    definitions = [
        ("Total Swarming Threads", "The total number of individual swarming threads initiated (distinct from Salesforce Cases)."),
        ("Engagement Rate (%)", "Percentage of requests receiving at least one human reply."),
        ("Total Messages", "The sum of the initial parent posts plus all subsequent replies within those threads."),
        ("Average MTTA", "Mean Time To Acknowledge. The average time elapsed between the original post and the first human reply."),
        ("Avg Unique Experts", "Avg unique individuals contributing to a thread (excl. Originator & Bots)."),
        ("SME Dominated Threads", "Complex threads (>3 replies) where >50% of effort came from one person."),
        ("P90 Replies", "Complexity Ceiling. Top 10% depth."),
        ("Unique Contributors", "The total number of distinct individuals who replied to assist with threads."),
        ("Unique Originators", "The total number of distinct individuals (or systems) who initiated a thread.")
    ]

    for i, (term, definition) in enumerate(definitions):
        worksheet_overview.write_string(start_row + 1 + i, 0, term, bold_format)
        worksheet_overview.write_string(start_row + 1 + i, 1, definition, italic_format)

    for sheet_name, df_sheet in zip(['Overview', 'Top Contributors', 'Contributor All Star'],
                                    [df_overview, df_top_ch, df_all_star]):
        if df_sheet.empty: continue
        worksheet = writer.sheets[sheet_name]
        for i, col in enumerate(df_sheet.columns):
            max_len = max(df_sheet[col].astype(str).map(len).max(), len(col)) + 2
            if sheet_name == 'Overview' and i == 1: max_len = max(max_len, 90)
            worksheet.set_column(i, i, max_len)

print(f"🎉 SUCCESS: Excel Summary created at {xls_filename}")