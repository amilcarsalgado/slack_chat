import os
import csv
import time
import re
import sys
import threading
import tkinter as tk
from tkinter import messagebox
from datetime import datetime, timezone   # [FIX L-1] import timezone for UTC-aware datetimes
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------


load_dotenv()
# Slack Bot Token - Keep this secure!
SLACK_TOKEN = os.getenv("SLACK_TOKEN")

# [FIX H-3] Abort immediately if token is missing rather than failing silently mid-run
if not SLACK_TOKEN:
    raise EnvironmentError(
        "CRITICAL: SLACK_TOKEN environment variable is not set or is empty. "
        "Ensure a valid .env file exists in the script directory. Aborting."
    )

# Initialize the Slack WebClient
client = WebClient(token=SLACK_TOKEN)


# ---------------------------------------------------------
# AUTO-MODE: ROLLING 4-QUARTER DATE CALCULATOR
# ---------------------------------------------------------
def get_rolling_4q_window():
    """Calculates the exact Start Date (FQ-3) and End Date (Now) based on a Nov 1 FQ1 Start"""
    now = datetime.now()
    month = now.month
    year = now.year

    # 1. Determine Current FY and FQ
    if month in [11, 12]:
        fy, fq = year + 1, 1
    elif month == 1:
        fy, fq = year, 1
    elif month in [2, 3, 4]:
        fy, fq = year, 2
    elif month in [5, 6, 7]:
        fy, fq = year, 3
    else:  # 8, 9, 10
        fy, fq = year, 4

    # 2. Calculate the FQ from 3 quarters ago using a continuous index
    curr_fq_index = fy * 4 + fq
    start_fq_index = curr_fq_index - 3

    # 3. Convert back to FY and FQ
    start_fy = (start_fq_index - 1) // 4
    start_fq = ((start_fq_index - 1) % 4) + 1

    # 4. Map FQ back to Calendar Month and Year
    if start_fq == 1:
        start_month = 11
        start_year = start_fy - 1
    elif start_fq == 2:
        start_month = 2
        start_year = start_fy
    elif start_fq == 3:
        start_month = 5
        start_year = start_fy
    else:  # FQ == 4
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
        print("Creating a default channels_config.txt file. Please update it with your channels.")
        with open(config_path, "w") as f:
            f.write("#gcc_swarming_nms_all\n#gcc_swarming_6500_all\n")
        return ["#gcc_swarming_nms_all", "#gcc_swarming_6500_all"]

    channels = []
    with open(config_path, "r") as f:
        for line in f:
            clean_line = line.strip()
            if clean_line and not clean_line.startswith("//"):  # Ignore empty lines and comments
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

    tk.Label(root, text="Select the channels you want to analyze:", font=("Arial", 12, "bold")).pack(anchor="w",
                                                                                                     pady=(0, 10))

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
    tk.Button(btn_frame, text="Run Analysis", width=15, bg="#3498db", fg="white", font=("Arial", 10, "bold"),
              command=submit).pack(side="right", padx=5)

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
    # [FIX M-1] Cap retries to prevent infinite hang on sustained rate-limits or outages
    MAX_RETRIES = 10
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return method(**kwargs)
        except SlackApiError as e:
            if e.response.get("error") == "ratelimited" and attempt < MAX_RETRIES:
                retry_after = int(e.response.headers.get("Retry-After", 5))
                print(f"⚠️ Rate limited by Slack (attempt {attempt}/{MAX_RETRIES}). "
                      f"Sleeping for {retry_after} seconds...")
                time.sleep(retry_after)
            else:
                raise
    raise RuntimeError("slack_call: exceeded maximum retry attempts.")


def load_user_cache():
    print("Loading user database from Slack...")
    users = {}
    cursor = None
    while True:
        resp = slack_call(client.users_list, limit=200, cursor=cursor)
        for user in resp.get("members", []):
            users[user["id"]] = {"is_bot": user.get("is_bot", False),
                                 "name": user.get("real_name") or user.get("name") or user.get("id")}
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor: break
    return users


def get_channel_id(channel_name):
    cursor = None
    while True:
        resp = slack_call(client.conversations_list, limit=1000, types="public_channel,private_channel", cursor=cursor)
        for ch in resp.get("channels", []):
            if ch.get("name") == channel_name.strip("#"): return ch["id"]
        cursor = resp.get("response_metadata", {}).get("next_cursor")
        if not cursor: return None


# [FIX M-3] Neutralise CSV formula injection: fields starting with =, +, -, @, TAB, CR
# are prefixed with an apostrophe so spreadsheet apps don't interpret them as formulas.
def sanitize_csv_field(value):
    if isinstance(value, str) and value and value[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


def sanitize_row(row: dict) -> dict:
    """Apply CSV formula-injection sanitisation to every string field in a row."""
    return {k: sanitize_csv_field(v) for k, v in row.items()}


def generate_report(channel_name, start_time, end_time, user_cache):
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
        # [FIX L-1] Use UTC to avoid server-local-timezone drift and DST anomalies
        post_dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
        text = msg.get("text", "") or ""

        u_id = msg.get("user") or msg.get("bot_id", "UNKNOWN")
        originator_name = user_cache.get(u_id, {}).get("name", u_id)

        if "Service Cloud" in originator_name or msg.get("subtype") == "bot_message":
            match = re.search(r"<@(U[A-Z0-9]+)>", text)
            if match: originator_name = user_cache.get(match.group(1), {}).get("name", match.group(1))

        reply_count = msg.get("reply_count", 0)
        thread_ts = msg.get("thread_ts", msg["ts"])
        replier_counts = {}
        first_human_reply_ts = ""
        replies = []

        if reply_count > 0:
            try:
                replies_resp = slack_call(client.conversations_replies, channel=channel_id, ts=thread_ts)
                replies = replies_resp.get("messages", [])

                for reply in replies[1:]:
                    r_uid = reply.get("user") or reply.get("bot_id")
                    if not r_uid: continue
                    r_user_info = user_cache.get(r_uid, {})
                    r_name = r_user_info.get("name", r_uid)
                    is_real_human = not r_user_info.get("is_bot", False)

                    if "Service Cloud" in r_name:
                        r_match = re.search(r"<@(U[A-Z0-9]+)>", reply.get("text", ""))
                        if r_match:
                            r_name = user_cache.get(r_match.group(1), {}).get("name", r_match.group(1))
                            is_real_human = True

                    if is_real_human:
                        if first_human_reply_ts == "":
                            # [FIX L-1] UTC-aware reply timestamp
                            first_human_reply_ts = datetime.fromtimestamp(
                                float(reply["ts"]), tz=timezone.utc
                            ).strftime("%Y-%m-%d %H:%M:%S")
                        replier_counts[r_name] = replier_counts.get(r_name, 0) + 1
                time.sleep(0.05)
            except SlackApiError as e:
                # [FIX M-2] Log the failure instead of silently discarding reply data
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
            # [FIX L-1] Compare in UTC
            latest_dt = datetime.fromtimestamp(latest_ts_float, tz=timezone.utc)
            if (datetime.now(tz=timezone.utc) - latest_dt).days >= 14:
                thread_status = "Closed"

        report.append(sanitize_row({   # [FIX M-3] sanitize before writing to CSV
            "Thread_ID": str(msg["ts"]),
            "Channel_Source": clean_channel_name,
            "Status": thread_status,
            "Post Timestamp": post_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "First Reply Timestamp": first_human_reply_ts,
            "Originator": originator_name,
            "Message Text": text.replace("\n", " "),
            "Number of Replies": reply_count,
            "Repliers Breakdown": "; ".join(f"{u}:{c}" for u, c in replier_counts.items())
        }))

    print(f"✅ Extracted {len(report)} records.")
    return report


# ---------------------------------------------------------
# EXECUTION START
# ---------------------------------------------------------
if __name__ == "__main__":
    mode = "AUTO"  # Default mode


    def wait_for_user():
        global mode
        try:
            print("\n" + "=" * 50)
            print("🚀 SLACK SWARMING PIPELINE INITIATED")
            print("=" * 50)
            print("The script will run in AUTO MODE in 10 seconds.")
            print("Press [ENTER] right now to switch to MANUAL MODE...")
            input()  # This blocks and waits for Enter
            mode = "MANUAL"
        except EOFError:
            # Cron jobs send EOF immediately. We catch this to prevent crashes!
            pass
        except Exception:
            pass


    # Start the countdown timer in the background
    t = threading.Thread(target=wait_for_user)
    t.daemon = True
    t.start()
    t.join(10)  # Give the user exactly 10 seconds

    # Decide what to do based on the result
    if mode == "AUTO":
        print("\n\n⏳ Timeout reached (or running via Cron). Proceeding in AUTO MODE...")
        target_channels = read_config_channels()
        start_time, end_time = get_rolling_4q_window()
    else:
        print("\n\n✋ Manual Mode selected.")
        target_channels = prompt_for_channels()
        start_time, end_time = get_reporting_range_from_input()

    # Run the core extraction logic
    user_cache = load_user_cache()
    master_report = []

    for channel in target_channels:
        channel_data = generate_report(channel, start_time, end_time, user_cache)
        if channel_data:
            master_report.extend(channel_data)

    if master_report:
        print("\n💾 Saving Master CSV File...")
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CSV_files")
        os.makedirs(output_dir, exist_ok=True)

        current_timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        full_path = os.path.join(output_dir, f"Master_Swarming_Report_{current_timestamp}.csv")

        headers = [
            "Thread_ID", "Channel_Source", "Status", "Post Timestamp",
            "First Reply Timestamp", "Originator", "Message Text",
            "Number of Replies", "Repliers Breakdown"
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
            # stdin=subprocess.DEVNULL prevents the background thread from locking the console!
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