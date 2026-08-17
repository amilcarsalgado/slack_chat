import os
import csv
import time
import re
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timezone
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# ---------------------------------------------------------
# CONFIGURATION 17Aug2026 _
# ---------------------------------------------------------
load_dotenv()
SLACK_TOKEN = os.getenv("SLACK_TOKEN")

if not SLACK_TOKEN:
    raise EnvironmentError(
        "CRITICAL: SLACK_TOKEN environment variable is not set or is empty. "
        "Ensure a valid .env file exists in the script directory. Aborting."
    )

client = WebClient(token=SLACK_TOKEN)


# ---------------------------------------------------------
# AUTO-MODE: ROLLING 4-QUARTER DATE CALCULATOR
# ---------------------------------------------------------
def get_rolling_4q_window():
    now = datetime.now()
    month = now.month
    year = now.year

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

    curr_fq_index = fy * 4 + fq
    start_fq_index = curr_fq_index - 3

    start_fy = (start_fq_index - 1) // 4
    start_fq = ((start_fq_index - 1) % 4) + 1

    if start_fq == 1:
        start_month = 11
        start_year = start_fy - 1
    elif start_fq == 2:
        start_month = 2
        start_year = start_fy
    elif start_fq == 3:
        start_month = 5
        start_year = start_fy
    else:
        start_month = 8
        start_year = start_fy

    start_dt = datetime(start_year, start_month, 1)

    print(f"📊 Auto-Calculated Window: FQ{start_fq} '{str(start_fy)[-2:]} through FQ{fq} '{str(fy)[-2:]} (TD)")
    print(f"   Start Date: {start_dt.strftime('%Y-%m-%d')}")
    print(f"   End Date:   {now.strftime('%Y-%m-%d')}\n")

    return start_dt, now


# ---------------------------------------------------------
# AUTO-MODE: READ CONFIG FILE
# ---------------------------------------------------------
def read_config_channels():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "channels_config.txt")

    if not os.path.exists(config_path):
        print(f"⚠️ Config file not found at {config_path}")
        with open(config_path, "w") as f:
            f.write("#gcc_swarming_nms_all\n#gcc_swarming_6500_all\n")
        return ["#gcc_swarming_nms_all", "#gcc_swarming_6500_all"]

    channels = []
    with open(config_path, "r") as f:
        for line in f:
            clean_line = line.strip()
            if clean_line and not clean_line.startswith("//"):
                channels.append(clean_line)

    print(f"📁 Loaded {len(channels)} channels from config file.")
    return channels


# ---------------------------------------------------------
# MANUAL-MODE: PROMPTS
# ---------------------------------------------------------
def prompt_for_channels():
    active_channels = [
        ("01. gcc-chatalert-cpo", "#gcc-chatalert-cpo"),
        ("02. gcc-chatalert-ncp", "#gcc-chatalert-ncp"),
        ("03. gcc-chatalert-rsp", "#gcc-chatalert-rsp"),
        ("04. gcc-chatalert-switching", "#gcc-chatalert-switching")
    ]

    root = tk.Tk()
    root.title("Select Swarming Channels")
    root.geometry("")
    root.config(padx=20, pady=20)
    root.attributes('-topmost', True)

    tk.Label(root, text="Select the channels you want to analyze:", font=("Arial", 12, "bold")).pack(anchor="w", pady=(0, 10))

    checkbox_vars = {}
    cb_frame = tk.Frame(root)
    cb_frame.pack(anchor="w", fill="x")

    for display_text, channel_tag in active_channels:
        var = tk.BooleanVar(value=False)
        checkbox_vars[channel_tag] = var
        cb = tk.Checkbutton(cb_frame, text=display_text, variable=var, font=("Consolas", 10))
        cb.pack(anchor="w", pady=2)

    selected_channels = []

    def select_all():
        for var in checkbox_vars.values(): var.set(True)

    def submit():
        for channel_tag, var in checkbox_vars.items():
            if var.get(): selected_channels.append(channel_tag)
        if not selected_channels:
            messagebox.showwarning("No Selection", "Please select at least one channel to proceed.")
            return
        root.destroy()

    btn_frame = tk.Frame(root)
    btn_frame.pack(fill="x", pady=(15, 0))
    tk.Button(btn_frame, text="Select All", width=12, command=select_all).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Run Analysis", width=15, bg="#3498db", fg="white", font=("Arial", 10, "bold"), command=submit).pack(side="right", padx=5)

    root.mainloop()
    return selected_channels


def get_reporting_range_from_input():
    print("\n--- Manual Date Range Selection ---")
    while True:
        try:
            start_input = input("Enter start date (DD/MM/YY): ").strip()
            start_dt = datetime.strptime(start_input, "%d/%m/%y")
            end_input = input("Enter end date (DD/MM/YY) or 'Now': ").strip()
            if end_input.lower() == "now":
                end_dt = datetime.now()
            else:
                end_dt = datetime.strptime(end_input, "%d/%m/%y")
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
            return start_dt, end_dt
        except ValueError:
            print("❌ Invalid input. Please use DD/MM/YY format.")


# ---------------------------------------------------------
# SLACK API CORE LOGIC
# ---------------------------------------------------------
def slack_call(method, **kwargs):
    MAX_RETRIES = 10
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return method(**kwargs)
        except SlackApiError as e:
            if e.response.get("error") == "ratelimited" and attempt < MAX_RETRIES:
                retry_after = int(e.response.headers.get("Retry-After", 5))
                print(f"⚠️ Rate limited by Slack (attempt {attempt}/{MAX_RETRIES}). Sleeping for {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                raise
    raise RuntimeError("slack_call: exceeded maximum retry attempts.")


def get_channel_id(channel_name):
    cursor = None
    while True:
        resp = slack_call(client.conversations_list, limit=1000, types="public_channel,private_channel", cursor=cursor)
        for ch in resp.get("channels", []):
            if ch.get("name") == channel_name.strip("#"): return ch["id"]
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor: return None


def sanitize_csv_field(value):
    if isinstance(value, str) and value and value[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


def sanitize_row(row: dict) -> dict:
    return {k: sanitize_csv_field(v) for k, v in row.items()}


def generate_report(channel_name, start_time, end_time):
    print(f"\n🔄 Processing {channel_name}...")
    channel_id = get_channel_id(channel_name)
    if not channel_id:
        print(f"❌ Channel not found. Skipping.")
        return []

    messages = []
    cursor = None
    while True:
        resp = slack_call(client.conversations_history, channel=channel_id, oldest=start_time.timestamp(),
                          latest=end_time.timestamp(), limit=200, cursor=cursor)
        messages.extend(resp.get("messages", []))
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor: break

    report = []
    clean_channel_name = channel_name.strip("#")

    for msg in messages:
        if msg.get("subtype") in ["channel_join", "channel_leave", "channel_purpose"]: continue

        ts_float = float(msg["ts"])
        post_dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
        text = msg.get("text", "") or ""

        # Default originator directly to Salesforce / bot username
        originator_name = msg.get("username") or "Salesforce"

        reply_count = msg.get("reply_count", 0)
        thread_ts = msg.get("thread_ts", msg["ts"])
        replies = []

        if reply_count > 0:
            try:
                replies_resp = slack_call(client.conversations_replies, channel=channel_id, ts=thread_ts)
                replies = replies_resp.get("messages", [])
                time.sleep(0.05)
            except SlackApiError as e:
                print(f"⚠️ WARNING: Could not fetch replies for thread {thread_ts} "
                      f"in channel {channel_id}: {e.response.get('error', e)}")

        # Thread Status Logic
        thread_status = "Open"
        target_string = "*Closed* :white_check_mark"

        if target_string in text:
            thread_status = "Closed"
        if thread_status == "Open" and reply_count > 0 and len(replies) > 1:
            for reply in replies[1:]:
                if target_string in reply.get("text", ""):
                    thread_status = "Closed"
                    break

        if thread_status == "Open":
            latest_ts_float = ts_float
            if reply_count > 0 and len(replies) > 0:
                latest_ts_float = float(replies[-1]["ts"])
            latest_dt = datetime.fromtimestamp(latest_ts_float, tz=timezone.utc)
            if (datetime.now(tz=timezone.utc) - latest_dt).days >= 14:
                thread_status = "Closed"

        report.append(sanitize_row({
            "Thread_ID": str(msg["ts"]),
            "Channel_Source": clean_channel_name,
            "Status": thread_status,
            "Post Timestamp": post_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "Originator": originator_name,
            "Message Text": text.replace("\n", " ")
        }))

    print(f"✅ Extracted {len(report)} records.")
    return report


# ---------------------------------------------------------
# EXECUTION START
# ---------------------------------------------------------
if __name__ == "__main__":
    mode = "AUTO"

    def wait_for_user():
        global mode
        try:
            print("\n" + "=" * 50)
            print("🚀 SLACK SWARMING PIPELINE INITIATED")
            print("=" * 50)
            print("The script will run in AUTO MODE in 10 seconds.")
            print("Press [ENTER] right now to switch to MANUAL MODE...")
            input()
            mode = "MANUAL"
        except EOFError:
            pass
        except Exception:
            pass

    t = threading.Thread(target=wait_for_user)
    t.daemon = True
    t.start()
    t.join(10)

    if mode == "AUTO":
        print("\n\n⏳ Timeout reached (or running via Cron). Proceeding in AUTO MODE...")
        target_channels = read_config_channels()
        start_time, end_time = get_rolling_4q_window()
    else:
        print("\n\n✋ Manual Mode selected.")
        target_channels = prompt_for_channels()
        start_time, end_time = get_reporting_range_from_input()

    master_report = []

    for channel in target_channels:
        channel_data = generate_report(channel, start_time, end_time)
        if channel_data:
            master_report.extend(channel_data)

    if master_report:
        print("\n💾 Saving Master CSV File...")
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CSV_files")
        os.makedirs(output_dir, exist_ok=True)

        current_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        full_path = os.path.join(output_dir, f"Master_Swarming_Report_{current_timestamp}.csv")

        # Removed 'Number of Replies' from headers
        headers = [
            "Thread_ID", "Channel_Source", "Status", "Post Timestamp",
            "Originator", "Message Text"
        ]

        with open(full_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(master_report)

        print(f"🎉 SUCCESS: Master CSV created. Total Records: {len(master_report)}")

        # ---------------------------------------------------------
        # PIPELINE TRIGGER: RUN NEXT SCRIPTS
        # ---------------------------------------------------------
        import subprocess

        script_dir = os.path.dirname(os.path.abspath(__file__))
        xls_script = os.path.join(script_dir, "Generate_Master_XLS_S.py")
        html_script = os.path.join(script_dir, "Generate_master_HTM_S.py")

        print("\n" + "=" * 50)
        print("🚀 PIPELINE STAGE 2: Generating Excel Summary...")
        print("=" * 50)
        try:
            subprocess.run([sys.executable, xls_script], check=True, stdin=subprocess.DEVNULL)

            print("\n" + "=" * 50)
            print("🚀 PIPELINE STAGE 3: Generating HTML Dashboards...")
            print("=" * 50)
            subprocess.run([sys.executable, html_script], check=True, stdin=subprocess.DEVNULL)

            print("\n✅ FULL PIPELINE EXECUTED SUCCESSFULLY!")
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Pipeline stopped. An error occurred in a downstream script: {e}")

    else:
        print("\n⚠️ No data extracted. Pipeline stopped.")