import os
import glob
import html
import pathlib
import pandas as pd
import plotly.graph_objects as go

# ==============================================================================
# CONFIGURATION
# ==============================================================================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(_SCRIPT_DIR, "XLS_files")
OUTPUT_DIR = os.path.join(_SCRIPT_DIR, "HTML_files")


def safe_output_path(directory: str, filename: str) -> str:
    resolved = (pathlib.Path(directory) / filename).resolve()
    if resolved.parent != pathlib.Path(directory).resolve():
        raise ValueError(
            f"SECURITY: Resolved output path '{resolved}' escapes the output directory "
            f"'{directory}'. Channel name may contain path-traversal characters."
        )
    return str(resolved)


_CSP_META = (
    '<meta http-equiv="Content-Security-Policy" '
    'content="default-src \'self\'; script-src \'unsafe-inline\'; '
    'style-src \'unsafe-inline\'; frame-ancestors \'none\';">'
)

CSS_STYLE = _CSP_META + """
<style>
    :root {
        --primary: #2C3E50;
        --secondary: #34495E;
        --accent: #3498DB;
        --bg: #F8F9F9;
        --card-bg: #FFFFFF;
        --text: #333333;
        --text-light: #7F8C8D;
    }
    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; }
    .header { background-color: var(--primary); color: white; padding: 20px 40px; display: flex; justify-content: space-between; align-items: center; }
    .header h1 { margin: 0; font-size: 24px; font-weight: 500; }
    .header a { color: white; text-decoration: none; font-weight: bold; padding: 8px 16px; background-color: var(--accent); border-radius: 4px; transition: 0.2s; }
    .header a:hover { background-color: #2980B9; }
    .container { max-width: 1200px; margin: 30px auto; padding: 0 20px; }

    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 15px; }
    .kpi-card { background: var(--card-bg); padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border-top: 4px solid var(--accent); }
    .kpi-title { font-size: 14px; color: var(--text-light); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }
    .kpi-value { font-size: 32px; font-weight: bold; color: var(--primary); margin: 0; }
    .kpi-value-small { font-size: 26px; font-weight: bold; color: var(--primary); margin: 0; }

    .legend-container { background: var(--card-bg); padding: 15px 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 30px; border-left: 4px solid var(--secondary); font-size: 13px; color: var(--text-light); }
    .legend-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; margin-top: 8px; }
    .legend-item b { color: var(--primary); font-weight: 600; }

    .chart-grid { display: flex; flex-direction: column; gap: 20px; margin-bottom: 30px; }
    .tables-column { display: flex; flex-direction: column; gap: 20px; }

    .chart-card, .table-card { background: var(--card-bg); padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .table-card h3 { margin-top: 0; color: var(--primary); }
    table { width: 100%; border-collapse: collapse; margin-top: 15px; }
    th, td { padding: 12px 15px; text-align: left; border-bottom: 1px solid #ddd; }
    th { background-color: #f2f2f2; font-weight: 600; color: var(--secondary); }
    tr:hover { background-color: #f9f9f9; }
    .menu-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; }
    .menu-btn { display: block; text-align: center; background: white; padding: 15px; border-radius: 6px; color: var(--primary); text-decoration: none; font-weight: 600; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #eee; transition: 0.2s;}
    .menu-btn:hover { border-color: var(--accent); color: var(--accent); transform: translateY(-2px); }
</style>
"""

LEGEND_HTML = """
<div class="legend-container">
    <strong style="color: var(--secondary); font-size: 14px;">KPI Glossary & Context</strong>
    <div class="legend-grid">
        <div class="legend-item"><b>Rolling 4Q:</b> Trailing 3 Qs + Current QTD (Quarter-to-Date).</div>
        <div class="legend-item"><b>Threads:</b> Total distinct swarming threads initiated.</div>
        <div class="legend-item"><b>Engagement Rate:</b> % of requests receiving at least 1 human reply.</div>
        <div class="legend-item"><b>Messages:</b> Initial parent posts + all subsequent replies.</div>
        <div class="legend-item"><b>Average MTTA:</b> Mean Time To Acknowledge (post to 1st human reply).</div>
        <div class="legend-item"><b>Contributors:</b> Total distinct individuals who replied.</div>
        <div class="legend-item"><b>Avg Unique Experts:</b> Avg unique individuals contributing to a thread.</div>
        <div class="legend-item"><b>SME Dominated:</b> Complex threads (>3 replies) where >50% of effort is 1 person.</div>
        <div class="legend-item" style="grid-column: span 2;"><b>P90 Replies:</b> The 90th percentile of thread depth. 90% of all swarming threads are resolved with fewer replies than this number, revealing the complexity ceiling of the toughest 10% of cases.</div>
    </div>
</div>
"""


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def clean_numeric(val):
    try:
        f = float(val)
        return str(int(f)) if f.is_integer() else str(val)
    except ValueError:
        return str(val)


def time_to_minutes(hhmmss):
    if pd.isna(hhmmss) or not isinstance(hhmmss, str) or hhmmss == '00:00:00':
        return 0
    try:
        parts = hhmmss.split(':')
        return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 60.0
    except:
        return 0


def build_trend_charts(df_quarterly):
    fig_vol = go.Figure()
    fig_vol.add_trace(go.Bar(x=df_quarterly['Fiscal Quarter'], y=df_quarterly['Total Swarming Threads'], name='Threads',
                             marker_color='#3498DB'))
    fig_vol.add_trace(go.Bar(x=df_quarterly['Fiscal Quarter'], y=df_quarterly['Total Messages'], name='Total Messages',
                             marker_color='#95A5A6'))
    fig_vol.update_layout(title="Quarterly Volume Trend", barmode='group', template='plotly_white', height=350,
                          margin=dict(l=20, r=20, t=50, b=20))
    html_vol = fig_vol.to_html(full_html=False, include_plotlyjs=True)

    df_quarterly['MTTA_Min'] = df_quarterly['Average MTTA (hh:mm:ss)'].apply(time_to_minutes)
    fig_vel = go.Figure()
    fig_vel.add_trace(go.Scatter(x=df_quarterly['Fiscal Quarter'], y=df_quarterly['MTTA_Min'], mode='lines+markers',
                                 name='MTTA (Min)', line=dict(color='#E74C3C', width=3), marker=dict(size=8)))
    fig_vel.update_layout(title="Quarterly MTTA Trend (Minutes)", template='plotly_white', height=350,
                          margin=dict(l=20, r=20, t=50, b=20), yaxis_title="Minutes")
    html_vel = fig_vel.to_html(full_html=False, include_plotlyjs=False)

    return html_vol, html_vel


# ==============================================================================
# DASHBOARD GENERATORS
# ==============================================================================
def generate_channel_page(channel, df_ch_all, df_top_ch):
    df_quarters = df_ch_all[df_ch_all['Fiscal Quarter'] != 'Total (Rolling 4Q)'].copy()
    total_row = df_ch_all[df_ch_all['Fiscal Quarter'] == 'Total (Rolling 4Q)'].iloc[0]

    chart_vol, chart_vel = build_trend_charts(df_quarters)

    top_list_html_blocks = ""
    if not df_top_ch.empty:
        quarters = df_top_ch['Fiscal Quarter'].unique()

        historical_qs = [q for q in quarters if q != 'Total (Rolling 4Q)']
        historical_qs.reverse()

        ordered_quarters = ['Total (Rolling 4Q)'] + historical_qs

        for q in ordered_quarters:
            q_stars = df_top_ch[df_top_ch['Fiscal Quarter'] == q]
            if q_stars.empty: continue

            q_escaped = html.escape(str(q))
            table_title = "Top Contributors: Rolling 4Q (Trailing 3 Qs + Current QTD)" if q == 'Total (Rolling 4Q)' else f"Top 5 Contributors: {q_escaped}"

            rows_html = ""
            row_data = q_stars.iloc[0]

            for i in range(1, 6):
                val = row_data.get(f'Top {i}', '')
                if pd.notna(val) and str(val).strip() != "":
                    parts = str(val).rsplit('(', 1)
                    if len(parts) == 2:
                        name_clean = html.escape(parts[0].strip())
                        count_clean = html.escape(parts[1].replace(')', '').strip())
                    else:
                        name_clean = html.escape(str(val))
                        count_clean = ""
                    rows_html += f"<tr><td>#{i}</td><td>{name_clean}</td><td>{count_clean}</td></tr>"

            if rows_html == "":
                rows_html = "<tr><td colspan='3'>No contributor data available for this period.</td></tr>"

            top_list_html_blocks += f"""
            <div class="table-card" style="margin-bottom: 20px;">
                <h3>{table_title}</h3>
                <table>
                    <thead><tr><th>Rank</th><th>Engineer Name</th><th>Total Replies</th></tr></thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>
            """
    else:
        top_list_html_blocks = """
        <div class="table-card" style="margin-bottom: 20px;">
            <h3>Top Contributors</h3>
            <table>
                <tbody><tr><td>No contributor data available for this period.</td></tr></tbody>
            </table>
        </div>
        """

    ch_escaped = html.escape(str(channel))
    kpi = {k: html.escape(clean_numeric(total_row[k])) for k in [
        'Total Swarming Threads', 'Engagement Rate (%)', 'Total Messages',
        'Average MTTA (hh:mm:ss)', 'Unique Contributors', 'Avg Unique Experts',
        'SME Dominated Threads', 'P90 Replies'
    ]}

    html_out = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{ch_escaped} Dashboard</title>
        {CSS_STYLE}
    </head>
    <body>
        <div class="header">
            <h1>{ch_escaped} <span style="font-weight:300; font-size:18px; opacity:0.8;">| Rolling 4Q (Trailing 3 Qs + Current QTD)</span></h1>
            <a href="index.html">← Back to Global</a>
        </div>
        <div class="container">
            <div class="kpi-grid">
                <div class="kpi-card"><div class="kpi-title">Total Threads</div><div class="kpi-value">{kpi['Total Swarming Threads']}</div></div>
                <div class="kpi-card"><div class="kpi-title">Engagement Rate</div><div class="kpi-value">{kpi['Engagement Rate (%)']}%</div></div>
                <div class="kpi-card"><div class="kpi-title">Total Messages</div><div class="kpi-value">{kpi['Total Messages']}</div></div>
                <div class="kpi-card"><div class="kpi-title">Average MTTA</div><div class="kpi-value-small">{kpi['Average MTTA (hh:mm:ss)']}</div></div>

                <div class="kpi-card" style="border-top-color: #9b59b6;"><div class="kpi-title">Unique Contributors</div><div class="kpi-value">{kpi['Unique Contributors']}</div></div>
                <div class="kpi-card" style="border-top-color: #9b59b6;"><div class="kpi-title">Avg Unique Experts</div><div class="kpi-value">{kpi['Avg Unique Experts']}</div></div>
                <div class="kpi-card" style="border-top-color: #9b59b6;"><div class="kpi-title">SME Dominated</div><div class="kpi-value">{kpi['SME Dominated Threads']}</div></div>
                <div class="kpi-card" style="border-top-color: #9b59b6;"><div class="kpi-title">P90 Replies</div><div class="kpi-value">{kpi['P90 Replies']}</div></div>
            </div>

            {LEGEND_HTML}

            <div class="chart-grid">
                <div class="chart-card">{chart_vol}</div>
                <div class="chart-card">{chart_vel}</div>
            </div>

            <div class="tables-column">
                {top_list_html_blocks}
            </div>

        </div>
    </body>
    </html>
    """

    filename = ch_escaped.replace("#", "") + ".html"
    with open(safe_output_path(OUTPUT_DIR, filename), "w", encoding="utf-8") as f:
        f.write(html_out)


def generate_index_page(df_global_all, df_all_star, channels):
    df_quarters = df_global_all[df_global_all['Fiscal Quarter'] != 'Total (Rolling 4Q)'].copy()
    total_row = df_global_all[df_global_all['Fiscal Quarter'] == 'Total (Rolling 4Q)'].iloc[0]

    chart_vol, chart_vel = build_trend_charts(df_quarters)

    all_star_html_blocks = ""
    if not df_all_star.empty:
        quarters = df_all_star['Fiscal Quarter'].unique()

        historical_qs = [q for q in quarters if q != 'Total (Rolling 4Q)']
        historical_qs.reverse()

        ordered_quarters = ['Total (Rolling 4Q)'] + historical_qs

        for q in ordered_quarters:
            q_stars = df_all_star[df_all_star['Fiscal Quarter'] == q].head(10)
            if q_stars.empty: continue

            q_escaped = html.escape(str(q))
            table_title = "Global Contributor All-Stars: Rolling 4Q (Trailing 3 Qs + Current QTD)" if q == 'Total (Rolling 4Q)' else f"Top 10 All-Stars: {q_escaped}"

            rows_html = ""
            for _, row in q_stars.iterrows():
                rank = html.escape(str(row['Rank']))
                name = html.escape(str(row['Name']))
                total_rep = html.escape(str(row['Total Replies']))
                ch_active = html.escape(str(row['Channels Active In']))
                # Use .get() to gracefully handle old Excel files during testing
                ch_list = html.escape(str(row.get('Channel List', '')))

                # Added the Active Channels column with slightly subdued styling
                rows_html += f"<tr><td>#{rank}</td><td>{name}</td><td>{total_rep}</td><td>{ch_active}</td><td style='font-size: 13px; color: var(--text-light); max-width: 250px; line-height: 1.4;'>{ch_list}</td></tr>"

            all_star_html_blocks += f"""
            <div class="table-card" style="margin-bottom: 20px;">
                <h3>{table_title}</h3>
                <table>
                    <thead><tr><th>Global Rank</th><th>Engineer Name</th><th>Total Replies</th><th>Channels Spanned</th><th>Active Channels</th></tr></thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>
            """

    nav_links = ""
    for ch in sorted(channels):
        if ch != 'Global':
            ch_escaped = html.escape(str(ch))
            link = ch_escaped.replace("#", "") + ".html"
            nav_links += f"<a href='{link}' class='menu-btn'>{ch_escaped}</a>"

    kpi = {k: html.escape(clean_numeric(total_row[k])) for k in [
        'Total Swarming Threads', 'Engagement Rate (%)', 'Total Messages',
        'Average MTTA (hh:mm:ss)', 'Unique Contributors', 'Avg Unique Experts',
        'SME Dominated Threads', 'P90 Replies'
    ]}

    html_out = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>GCC Swarming Dashboard</title>
        {CSS_STYLE}
    </head>
    <body>
        <div class="header">
            <h1>GCC Global Swarming <span style="font-weight:300; font-size:18px; opacity:0.8;">| Executive Overview: Rolling 4Q (Trailing 3 Qs + Current QTD)</span></h1>
        </div>
        <div class="container">
            <div class="kpi-grid">
                <div class="kpi-card"><div class="kpi-title">Global Threads</div><div class="kpi-value">{kpi['Total Swarming Threads']}</div></div>
                <div class="kpi-card"><div class="kpi-title">Engagement Rate</div><div class="kpi-value">{kpi['Engagement Rate (%)']}%</div></div>
                <div class="kpi-card"><div class="kpi-title">Global Messages</div><div class="kpi-value">{kpi['Total Messages']}</div></div>
                <div class="kpi-card"><div class="kpi-title">Global MTTA</div><div class="kpi-value-small">{kpi['Average MTTA (hh:mm:ss)']}</div></div>

                <div class="kpi-card" style="border-top-color: #9b59b6;"><div class="kpi-title">Active Engineers</div><div class="kpi-value">{kpi['Unique Contributors']}</div></div>
                <div class="kpi-card" style="border-top-color: #9b59b6;"><div class="kpi-title">Avg Unique Experts</div><div class="kpi-value">{kpi['Avg Unique Experts']}</div></div>
                <div class="kpi-card" style="border-top-color: #9b59b6;"><div class="kpi-title">SME Dominated</div><div class="kpi-value">{kpi['SME Dominated Threads']}</div></div>
                <div class="kpi-card" style="border-top-color: #9b59b6;"><div class="kpi-title">P90 Replies</div><div class="kpi-value">{kpi['P90 Replies']}</div></div>
            </div>

            {LEGEND_HTML}

            <div class="chart-grid">
                <div class="chart-card">{chart_vol}</div>
                <div class="chart-card">{chart_vel}</div>
            </div>

            <div class="table-card" style="margin-bottom: 30px;">
                <h3>Channel Analytics Deep Dives</h3>
                <p style="color: var(--text-light); margin-bottom: 20px;">Select a product swarm channel below to view localized quarterly trends and top contributors.</p>
                <div class="menu-grid">
                    {nav_links}
                </div>
            </div>

            <div class="tables-column">
                {all_star_html_blocks}
            </div>

        </div>
    </body>
    </html>
    """

    with open(safe_output_path(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_out)


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main():
    print(f"\n🚀 Generating HTML Dashboards...")

    if os.path.exists(OUTPUT_DIR):
        print(f"🧹 Clearing old HTML files from '{OUTPUT_DIR}'...")
        for file_path in glob.glob(os.path.join(OUTPUT_DIR, "*")):
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"   ⚠️ Could not delete {file_path}: {e}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    search_pattern = os.path.join(INPUT_DIR, "Summary_Report_*.xlsx")
    files = glob.glob(search_pattern)

    if not files:
        print(f"❌ No Summary Excel file found in '{INPUT_DIR}'. Please run the Generate_Master_XLS.py script first.")
        return

    latest_file = max(files, key=os.path.getmtime)
    print(f"📄 Reading Data from: {os.path.basename(latest_file)}")

    df_overview = pd.read_excel(latest_file, sheet_name='Overview')
    df_top = pd.read_excel(latest_file, sheet_name='Top Contributors')
    df_all_star = pd.read_excel(latest_file, sheet_name='Contributor All Star')

    df_overview = df_overview.dropna(subset=['Total Swarming Threads']).copy()
    channels = df_overview['Channel'].unique()

    for ch in channels:
        if ch == 'Global':
            continue

        df_ch_ov = df_overview[df_overview['Channel'] == ch]
        df_ch_top = df_top[df_top['Channel'] == ch] if not df_top.empty else pd.DataFrame()

        generate_channel_page(ch, df_ch_ov, df_ch_top)
        print(f"   - Created page for: {ch}")

    df_global_ov = df_overview[df_overview['Channel'] == 'Global']
    generate_index_page(df_global_ov, df_all_star, channels)
    print(f"   - Created Global Index Page")

    print(f"\n🎉 SUCCESS: Website generation complete! Open '{OUTPUT_DIR}/index.html' in your browser to view.")


if __name__ == "__main__":
    main()