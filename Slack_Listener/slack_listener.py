import os
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# 1. Load Tokens using explicit path (since script is inside the subfolder)

env_path = r"C:\Users\asalgado\PycharmProjects\Slack_Chatalert\.env"
load_dotenv(dotenv_path=env_path)

SLACK_BOT_TOKEN = os.getenv("SLACK_TOKEN")
SLACK_APP_TOKEN = os.getenv("BOT_TOKEN")

if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
    raise EnvironmentError(f"CRITICAL: Tokens missing. Checked path: {env_path}")

# TODO: Replace with the actual 'C...' ID you retrieve from your console for #di-test
TARGET_CHANNEL_ID = "C0C4051R9SN"

# 2. Initialize App
app = App(token=SLACK_BOT_TOKEN)


# 3. Listen for messages, supporting channel filtering and thread replies
@app.event("message")
def handle_any_mesage(client, event, say):
    print(f"Raw Event Received: {event}")

'''
def handle_all_messages(event, say):
    # Ignore hidden events (edits, deletions, bot messages, etc.)
    if event.get("subtype"):
        return

    channel_id = event.get("channel")

    # Filter: Only process messages from your target channel
    if channel_id != TARGET_CHANNEL_ID:
        return

    text = event.get("text")
    user = event.get("user")
    thread_ts = event.get("thread_ts")  # Present if this message is a reply inside a thread

    if thread_ts:
        print(f"💬 Thread Reply Detected (Parent: {thread_ts})!")
    else:
        print(f"🔔 New Top-Level Post Detected!")

    print(f"   User: {user}")
    print(f"   Text: {text}\n")

'''


if __name__ == "__main__":
    print("⚡️ Slack listener active! Monitoring target channel and threads...")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()