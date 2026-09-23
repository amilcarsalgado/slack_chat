import logging

logging.basicConfig(level=logging.INFO)

import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# 1. Load Tokens using explicit path to root .env file
env_path = r"C:\Users\ravi\PycharmProjects\Slack_Chatalert\.env"
load_dotenv(dotenv_path=env_path)

SLACK_BOT_TOKEN = os.getenv("SLACK_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
    raise EnvironmentError(f"CRITICAL: Tokens missing. Checked path: {env_path}")

# 2. Target Channel ID (Make sure this matches your current #di-test ID)
TARGET_CHANNEL_ID = "C0C4051R9SN"

# 3. Initialize App
app = App(token=SLACK_BOT_TOKEN)


# 4. Event Handler to capture messages and threads
@app.event("message")
def handle_target_messages(event, say):
    # Ignore edits, deletions, or other non-message subtypes
    if event.get("subtype"):
        return

    channel_id = event.get("channel")
    text = event.get("text")
    user = event.get("user")
    thread_ts = event.get("thread_ts")
    message_ts = event.get("ts")

    # Debug print for every message heard across the socket
    print(f"👀 Heard message '{text}' from Channel ID: {channel_id}")

    # Filter: Only process messages from your designated target channel
    if channel_id != TARGET_CHANNEL_ID:
        print(f"   -> Ignored (doesn't match TARGET_CHANNEL_ID: {TARGET_CHANNEL_ID})\n")
        return

    print(f"   -> SUCCESS! Matched target channel!")

    if thread_ts:
        print(f"💬 Thread Reply Detected (Parent: {thread_ts})!")
    else:
        print(f"🔔 New Top-Level Post Detected!")

    print(f"   User: {user}")
    print(f"   Text: {text}\n")

    # FUTURE HOOK: Integration point for Snowflake Cortex analysis & automated replies
    # Example reply back: say(text="Processed by Cortex", thread_ts=message_ts)


if __name__ == "__main__":
    print("⚡️ Slack listener active! Locked onto target channel...")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()