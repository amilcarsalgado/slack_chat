import os
import glob
import html
import pathlib
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==============================================================================
# CONFIGURATION 17Aug2026
# ==============================================================================
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(_SCRIPT_DIR, "XLS_files")
OUTPUT_DIR = os.path.join(_SCRIPT_DIR, "HTML_files")


def safe_output_path(directory: str, filename: str) -> str:
    resolved = (pathlib.Path(directory) / filename).resolve()
    if resolved.parent != pathlib.Path(directory).resolve():
        raise ValueError("SECURITY: Path escapes directory.")
    return str(resolved)


CSS_STYLE = """
<style>
    :root {
        --primary: #2C3E50; --danger: #C0392B; --danger-light: #E74C3C; 
        --warning: #F39C12; --bg: #F8F9F9; --card-bg: #FFFFFF;
        --text: #333333; --text-light: #7F8C8D;
    }
    body { font-family: 'Segoe UI', Tahoma, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 0; }

    .header { background: var(--primary); color: white; padding: 25px 40px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.2);}
    .header h1 { margin: 0 0 15px 0; font-size: 32px; text-transform: uppercase; letter-spacing: 2px;}

    .nav-tabs { display: flex; justify-content: center; gap: 15px; margin-bottom: -25px;}
    .nav-tabs a { background: rgba(255,255,255,0.2); color: white; text-decoration: none; padding: 10px 25px; border-radius: 5px 5px 0 0; font-weight: bold; transition: 0.3s;}
    .nav-tabs a:hover { background: rgba(255,255,255,0.4); }
    .nav-tabs a.active { background: var(--bg); color: var(--primary); }

    .container { max-width: 1400px; margin: 50px auto; padding: 0 20px; }

    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-bottom: 30px; }
    .kpi-card { background: var(--card-bg); padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-top: 6px solid var(--primary); text-align: center;}
    .kpi-title { font-size: 13px; color: var(--text-light); text-transform: uppercase; font-weight: bold; margin-bottom: 10px; }
    .kpi-value { font-size: 24px; font-weight: bold; color: var(--primary); margin: 0; }
    .kpi-value.bad { color: var(--danger); font-size: 32px; }

    .chart-grid { display: grid; grid-template-columns: 1fr; gap: 40px; margin-bottom: 40px; }
    .chart-card { background: var(--card-bg); padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #eee; overflow: hidden;}

    .four-chart-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 30px; margin-bottom: 40px; }

    .region-section { margin-bottom: 40px; background: var(--card-bg); padding: 25px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-left: 8px solid var(--primary); }
    .region-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #eee; padding-bottom: 10px; margin-bottom: 15px;}
    .region-header h2 { margin: 0; color: var(--primary); font-size: 26px; text-transform: uppercase;}
    .region-total { background: var(--primary); color: white; padding: 8px 20px; border-radius: 20px; font-weight: bold;}

    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th, td { padding: 14px 15px; text-align: left; border-bottom: 1px solid #ddd; font-size: 15px;}
    th { background-color: #f8f9f9; color: var(--primary); border-bottom: 3px solid #ddd; text-transform: uppercase;}
    .count-col { font-weight: bold; color: var(--primary); text-align: center; font-size: 18px;}
</style>
"""


def build_accountability_charts(df_summary):
    region_order = df_summary.groupby('Region')['Alert Count'].sum().sort_values(ascending=False).index
    fig_stacked = go.Figure()
    channels = df_summary['Channel_Source'].unique()
    colors = ['#2C3E50', '#34495E', '#7F8C8D', '#95A5A6', '#BDC3C7', '#3498DB', '#2980B9']

    for i, channel in enumerate(channels):
        df_ch = df_summary[df_summary['Channel_Source'] == channel]
        counts = [df_ch[df_ch['Region'] == r]['Alert Count'].sum() for r in region_order]
        fig_stacked.add_trace(go.Bar(x=region_order, y=counts, name=channel, marker_color=colors[i % len(colors)]))

    fig_stacked.update_layout(
        title="Unanswered Alerts by Region", title_font=dict(size=18, color='#2C3E50'),
        template='plotly_white', height=500, barmode='stack', margin=dict(l=60, r=20, t=60, b=120),
        yaxis_title="Total Unanswered Alerts", hoverlabel=dict(namelength=-1), hovermode="x unified",
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="center", x=0.5, itemwidth=80)
    )

    df_alerts = df_summary.groupby('Alert')['Alert Count'].sum().reset_index().sort_values(by='Alert Count').tail(10)
    df_alerts['Alert_Short'] = df_alerts['Alert'].apply(lambda x: (x[:45] + '...') if len(x) > 48 else x)

    fig_alerts = go.Figure(go.Bar(x=df_alerts['Alert Count'], y=df_alerts['Alert_Short'], orientation='h',
                                  marker_color='#3498DB', text=df_alerts['Alert Count'], textposition='auto',
                                  hovertext=df_alerts['Alert']))
    fig_alerts.update_layout(title="Top 10 Most Frequent Alert Types", title_font=dict(size=18),
                             template='plotly_white',
                             height=450, margin=dict(l=160, r=40, t=60, b=60), xaxis_title="Alert Volume",
                             hoverlabel=dict(namelength=-1))

    return fig_stacked.to_html(full_html=False, include_plotlyjs=True), fig_alerts.to_html(full_html=False,
                                                                                           include_plotlyjs=False)


def generate_index_dashboard(df_summary):
    total_alerts = df_summary['Alert Count'].sum()
    worst_region = df_summary.groupby('Region')['Alert Count'].sum().idxmax() if total_alerts > 0 else "N/A"
    worst_channel = df_summary.groupby('Channel_Source')['Alert Count'].sum().idxmax() if total_alerts > 0 else "N/A"
    worst_alert = df_summary.groupby('Alert')['Alert Count'].sum().idxmax() if total_alerts > 0 else "N/A"

    chart_stacked, chart_alerts = build_accountability_charts(df_summary)

    wall_html = ""
    for region, total in df_summary.groupby('Region')['Alert Count'].sum().sort_values(ascending=False).items():
        rows = "".join([
                           f"<tr><td>{html.escape(str(r['Channel_Source']))}</td><td>{html.escape(str(r['Alert']))}</td><td class='count-col'>{r['Alert Count']}</td></tr>"
                           for _, r in df_summary[df_summary['Region'] == region].sort_values('Alert Count',
                                                                                              ascending=False).iterrows()])
        wall_html += f"<div class='region-section'><div class='region-header'><h2>{html.escape(str(region))}</h2><div class='region-total'>{total} Unanswered</div></div><table><thead><tr><th>Channel</th><th>Alert Type</th><th class='count-col'>Count</th></tr></thead><tbody>{rows}</tbody></table></div>"

    html_out = f"""
    <!DOCTYPE html><html><head><title>Automated Alerts Dashboard</title>{CSS_STYLE}</head><body>
        <div class="header">
            <h1>Automated Alerts Dashboard</h1>
            <div class="nav-tabs">
                <a href="index.html" class="active">Dashboard</a>
                <a href="qu_timeline.html">Queue Unstaffed FTS Timeline</a>
            </div>
        </div>
        <div class="container">
            <div class="kpi-grid">
                <div class="kpi-card"><div class="kpi-title">Total Unanswered</div><div class="kpi-value bad">{total_alerts}</div></div>
                <div class="kpi-card"><div class="kpi-title">Highest Volume Region</div><div class="kpi-value" style="color: #2C3E50;">{worst_region}</div></div>
                <div class="kpi-card"><div class="kpi-title">Highest Volume Channel</div><div class="kpi-value">{worst_channel}</div></div>
                <div class="kpi-card"><div class="kpi-title">Highest Volume Alert</div><div class="kpi-value" style="font-size: 15px;">{worst_alert}</div></div>
            </div>
            <div class="chart-grid"><div class="chart-card">{chart_stacked}</div><div class="chart-card">{chart_alerts}</div></div>
            <h2 style="color: var(--primary); border-bottom: 3px solid var(--primary); padding-bottom: 10px; margin-top: 50px;">REGIONAL BREAKDOWN</h2>
            {wall_html}
        </div>
    </body></html>
    """
    with open(safe_output_path(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f: f.write(html_out)


def generate_timeline_dashboard(df_raw, df_shift_dist, df_weekday_dist):
    df_qu = df_raw[df_raw['Alert'].str.contains("Queue Unstaffed", na=False, case=False)].copy()

    if df_qu.empty:
        html_out = f"<!DOCTYPE html><html><head><title>Timeline</title>{CSS_STYLE}</head><body><div class='header'><h1>Automated Alerts Dashboard</h1><div class='nav-tabs'><a href='index.html'>Dashboard</a><a href='qu_timeline.html' class='active'>Queue Unstaffed FTS Timeline</a></div></div><div class='container'><h2>No Queue Unstaffed data available to plot.</h2></div></body></html>"
        with open(safe_output_path(OUTPUT_DIR, "qu_timeline.html"), "w", encoding="utf-8") as f: f.write(html_out)
        return

    # --- PART 1: INTRA-SHIFT HOURLY DISTRIBUTION ---
    regions = ['India', 'EMEA', 'NA', 'Manila']
    shift_colors = {'Manila': '#E8DAEF', 'India': '#D6EAF8', 'EMEA': '#D5F5E3', 'NA': '#FDEBD0'}
    dist_html_blocks = ""
    plotly_included = False

    for r in regions:
        df_r = df_shift_dist[df_shift_dist['Region'] == r]
        if df_r.empty: continue

        fig_r = go.Figure()
        color = shift_colors[r]
        line_color = '#2C3E50'

        fig_r.add_trace(go.Bar(
            x=df_r['Shift_Hour'], y=df_r['Percent_of_Shift'], marker_color=color, marker_line_color=line_color,
            marker_line_width=1.5, text=df_r['Percent_of_Shift'].apply(lambda x: f"{x}%"), textposition='outside',
            hovertemplate="Shift Hour: %{x}<br>Percentage: %{y}%<br>Raw Count: %{customdata}<extra></extra>",
            customdata=df_r['QU_Count']
        ))

        fig_r.update_layout(
            title=f"{r} - Distribution", title_font=dict(size=16, color='#2C3E50'), template='plotly_white', height=300,
            margin=dict(l=40, r=20, t=50, b=40),
            xaxis=dict(title="Hour of Shift (1 to 6)", tickvals=[1, 2, 3, 4, 5, 6]),
            yaxis=dict(title="% of Regional Total", showgrid=True, gridcolor='#eee',
                       range=[0, max(df_r['Percent_of_Shift']) * 1.2])
        )

        if not plotly_included:
            dist_html_blocks += f"<div class='chart-card' style='padding: 10px;'>{fig_r.to_html(full_html=False, include_plotlyjs=True)}</div>"
            plotly_included = True
        else:
            dist_html_blocks += f"<div class='chart-card' style='padding: 10px;'>{fig_r.to_html(full_html=False, include_plotlyjs=False)}</div>"

    # --- PART 2: WEEKDAY FATIGUE DISTRIBUTION ---
    fatigue_colors = []
    for day in df_weekday_dist['Day_of_Week']:
        if day == 'Friday':
            fatigue_colors.append('#C0392B')
        elif day == 'Tuesday':
            fatigue_colors.append('#E67E22')
        else:
            fatigue_colors.append('#7FB3D5')

    fig_fatigue = go.Figure(go.Bar(
        x=df_weekday_dist['Day_of_Week'],
        y=df_weekday_dist['QU_Count'],
        marker_color=fatigue_colors,
        text=df_weekday_dist['QU_Count'],
        textposition='outside',
        textfont=dict(weight='bold'),
        hovertemplate="Day: %{x}<br>Alerts: %{y}<extra></extra>"
    ))

    fig_fatigue.update_layout(
        title="Queue Unstaffed Alerts by Day of the Week (Highlighting Friday & Tuesday Fatigue)",
        title_font=dict(size=16, color='#2C3E50'),
        template='plotly_white',
        height=450,
        margin=dict(l=40, r=40, t=60, b=40),
        yaxis_title="Total Unanswered Alerts",
        xaxis_title="Day of the Week",
        yaxis=dict(range=[0, df_weekday_dist['QU_Count'].max() * 1.15])
    )
    fatigue_html = fig_fatigue.to_html(full_html=False, include_plotlyjs=False)

    # --- PART 3: CHRONOLOGICAL TIMELINE PLOT (2 WEEKS PER ROW, CAPPED AT MAX DATA DATE) ---
    df_qu['Post Timestamp'] = pd.to_datetime(df_qu['Post Timestamp'])
    df_qu = df_qu.sort_values('Post Timestamp')

    max_data_date = df_qu['Post Timestamp'].max()
    min_date = df_qu['Post Timestamp'].min()
    start_date = min_date - pd.to_timedelta(min_date.dayofweek, unit='D')
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    df_qu['Days_Since'] = (df_qu['Post Timestamp'] - start_date).dt.days
    df_qu['Block_ID'] = df_qu['Days_Since'] // 28
    df_qu['Hour_Bin'] = df_qu['Post Timestamp'].dt.floor('h')

    blocks = df_qu['Block_ID'].unique()
    blocks.sort()

    row_intervals = []
    row_titles = []
    for b in blocks:
        b_start = start_date + pd.to_timedelta(b * 28, unit='D')
        b_mid = b_start + pd.Timedelta(days=14)
        b_end = b_start + pd.Timedelta(days=28)

        # Only include 2-week intervals that start on or before max_data_date
        if b_start <= max_data_date:
            row_intervals.append((b_start, b_mid))
            row_titles.append(
                f"2-Week Window: {b_start.strftime('%b %d, %Y')} to {(b_mid - pd.Timedelta(seconds=1)).strftime('%b %d, %Y')} (UTC)")

        if b_mid <= max_data_date:
            row_intervals.append((b_mid, b_end))
            row_titles.append(
                f"2-Week Window: {b_mid.strftime('%b %d, %Y')} to {(b_end - pd.Timedelta(seconds=1)).strftime('%b %d, %Y')} (UTC)")

    fig_h = max(800, len(row_intervals) * 320)
    fig_timeline = make_subplots(rows=len(row_intervals), cols=1, shared_xaxes=False, vertical_spacing=0.06,
                                 subplot_titles=row_titles)

    all_shapes = []

    for i, (r_start, r_end) in enumerate(row_intervals):
        df_r = df_qu[(df_qu['Post Timestamp'] >= r_start) & (df_qu['Post Timestamp'] < r_end)]

        hourly_counts = df_r.groupby('Hour_Bin').size().reset_index(name='Count')

        # Shift bar x-coordinates forward by 30 minutes so they align perfectly within their hour block
        shifted_x = hourly_counts['Hour_Bin'] + pd.Timedelta(minutes=30)

        fig_timeline.add_trace(go.Bar(
            x=shifted_x,
            y=hourly_counts['Count'],
            marker_color='#2C3E50',
            showlegend=False,
            width=3600000 * 0.85,
            hovertemplate="Alerts: %{y}<extra></extra>"
        ), row=i + 1, col=1)

        xref_str = f"x{i + 1}" if i > 0 else "x"
        yref_str = f"y{i + 1} domain" if i > 0 else "y domain"

        for day_offset in range(-1, 14):
            base_day = r_start + pd.Timedelta(days=day_offset)
            shifts_in_day = [
                ('Manila', base_day + pd.Timedelta(hours=22), base_day + pd.Timedelta(hours=28)),
                ('India', base_day + pd.Timedelta(hours=4), base_day + pd.Timedelta(hours=10)),
                ('EMEA', base_day + pd.Timedelta(hours=10), base_day + pd.Timedelta(hours=16)),
                ('NA', base_day + pd.Timedelta(hours=16), base_day + pd.Timedelta(hours=22))
            ]
            for s_name, s_start, s_end in shifts_in_day:
                x0 = max(r_start, s_start)
                x1 = min(r_end, s_end)
                if x0 < x1:
                    all_shapes.append(dict(
                        type="rect",
                        xref=xref_str,
                        yref=yref_str,
                        x0=x0, x1=x1,
                        y0=0, y1=1,
                        fillcolor=shift_colors[s_name],
                        opacity=0.5,
                        layer="below",
                        line=dict(width=0.5, color='black')
                    ))

        midnight_dates = pd.date_range(start=r_start, end=r_end, freq='D')
        for md in midnight_dates:
            all_shapes.append(dict(
                type="line",
                xref=xref_str,
                yref=yref_str,
                x0=md, x1=md,
                y0=0, y1=1,
                line=dict(width=1.2, color='#2C3E50', dash='dot')
            ))

        tick_dates = pd.date_range(start=r_start, end=r_end - pd.Timedelta(days=1), freq='D')
        tick_vals = list(tick_dates)
        tick_texts = [d.strftime('%b %d<br>(%a)') for d in tick_dates]

        fig_timeline.update_xaxes(
            range=[r_start, r_end],
            tickvals=tick_vals,
            ticktext=tick_texts,
            showgrid=False,
            row=i + 1,
            col=1
        )

    fig_timeline.update_layout(shapes=all_shapes)

    fig_timeline.add_trace(
        go.Bar(x=[None], y=[None], marker_color=shift_colors['Manila'], name='Manila (22:00-04:00 UTC)'))
    fig_timeline.add_trace(
        go.Bar(x=[None], y=[None], marker_color=shift_colors['India'], name='India (04:00-10:00 UTC)'))
    fig_timeline.add_trace(go.Bar(x=[None], y=[None], marker_color=shift_colors['EMEA'], name='EMEA (10:00-16:00 UTC)'))
    fig_timeline.add_trace(go.Bar(x=[None], y=[None], marker_color=shift_colors['NA'], name='NA (16:00-22:00 UTC)'))

    fig_timeline.update_yaxes(title_text="Alerts", showgrid=True, gridcolor='#eee')
    fig_timeline.update_layout(
        template='plotly_white', height=fig_h, margin=dict(l=40, r=40, t=60, b=80),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )

    timeline_html = fig_timeline.to_html(full_html=False, include_plotlyjs=True)

    # --- FINAL HTML ASSEMBLY ---
    html_out = f"""
    <!DOCTYPE html><html><head><title>Queue Unstaffed Timeline</title>{CSS_STYLE}</head><body>
        <div class="header">
            <h1>Automated Alerts Dashboard</h1>
            <div class="nav-tabs">
                <a href="index.html">Dashboard</a>
                <a href="qu_timeline.html" class="active">Queue Unstaffed FTS Timeline</a>
            </div>
        </div>
        <div class="container">

            <!-- SECTION 1: INTRA-SHIFT DISTRIBUTION -->
            <h2 style="color: var(--primary); border-bottom: 3px solid var(--primary); padding-bottom: 10px; margin-top: 10px;">INTRA-SHIFT DISTRIBUTION</h2>
            <p style="color: var(--text-light); margin-bottom: 30px;">
                This breaks down when Queue Unstaffed alerts occur relative to the start of each region's 6-hour shift. 
                Hour 1 represents the first hour of the shift, while Hour 6 represents the final hour (handover).
            </p>
            <div class="four-chart-grid">
                {dist_html_blocks}
            </div>

            <!-- SECTION 2: WEEKLY FATIGUE PATTERNS -->
            <h2 style="color: var(--primary); border-bottom: 3px solid var(--primary); padding-bottom: 10px; margin-top: 50px;">WEEKLY FATIGUE PATTERNS</h2>
            <p style="color: var(--text-light); margin-bottom: 30px;">
                This chart highlights the Queue Unstaffed operational fatigue across the week. Notice the significant drop in discipline on Fridays, as well as the mid-week slump on Tuesdays.
            </p>
            <div class="chart-card" style="padding: 10px; margin-bottom: 50px;">
                {fatigue_html}
            </div>

            <!-- SECTION 3: TIMELINE (MOVED TO BOTTOM) -->
            <h2 style="color: var(--primary); border-bottom: 3px solid var(--primary); padding-bottom: 10px; margin-top: 50px;">QUEUE UNSTAFFED ALERTS VS FTS SHIFTS (CHRONOLOGICAL TIMELINE)</h2>
            <p style="color: var(--text-light); margin-bottom: 20px;">
                This chronological chart plots exact alert occurrences across true calendar dates (2 weeks per row). The background colors represent active shifts with crisp shift boundaries, and dotted vertical lines mark the start of each day (00:00 UTC).
            </p>
            <div class="chart-card" style="padding: 0; margin-bottom: 50px;">{timeline_html}</div>

        </div>
    </body></html>
    """
    with open(safe_output_path(OUTPUT_DIR, "qu_timeline.html"), "w", encoding="utf-8") as f:
        f.write(html_out)


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main():
    print(f"\n🚀 Generating Dashboards...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    search_pattern = os.path.join(INPUT_DIR, "Alert_Summary_*.xlsx")
    files = glob.glob(search_pattern)

    if not files:
        print(f"❌ No 'Alert_Summary_*.xlsx' file found.")
        return

    latest_file = max(files, key=os.path.getmtime)
    print(f"📄 Reading Data from: {os.path.basename(latest_file)}")

    df_summary = pd.read_excel(latest_file, sheet_name='Regional Summary', keep_default_na=False)
    df_shift_dist = pd.read_excel(latest_file, sheet_name='Shift Distribution', keep_default_na=False)
    df_weekday_dist = pd.read_excel(latest_file, sheet_name='Weekday Distribution', keep_default_na=False)
    df_raw = pd.read_excel(latest_file, sheet_name='Raw Alerts', keep_default_na=False)

    generate_index_dashboard(df_summary)
    generate_timeline_dashboard(df_raw, df_shift_dist, df_weekday_dist)

    print(f"🎉 SUCCESS: Dashboards complete! Open '{OUTPUT_DIR}/index.html' to view.")


if __name__ == "__main__":
    main()