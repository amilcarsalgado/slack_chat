import logging

logging.basicConfig(level=logging.INFO)

import os
import re
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# ==========================================
# 1. ENVIRONMENT & TOKEN CONFIGURATION
# ==========================================
env_path = r"C:\Users\ravi\PycharmProjects\Slack_Chatalert\.env"
load_dotenv(dotenv_path=env_path)

SLACK_BOT_TOKEN = os.getenv("SLACK_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
    raise EnvironmentError(f"CRITICAL: Tokens missing. Checked path: {env_path}")

# Monitored Channels (including your #di-test channel)
TARGET_CHANNEL_IDS = [
    "C0C4051R9SN",  # #di-test
    "ADD_SECOND_CHANNEL_ID_HERE",
    "ADD_THIRD_CHANNEL_ID_HERE"
]

app = App(token=SLACK_BOT_TOKEN)


# ==========================================
# 2. MOCK / INTEGRATION HOOK FOR MCP & SNOWFLAKE
# ==========================================
def query_snowflake_cortex_for_similar_cases(case_number: str) -> str:
    """
    POC Function: Replace this body with your actual MCP server access script
    or Snowflake/Cortex API calls.
    """
    print(f"🤖 [MCP/Snowflake] Executing search for case: {case_number}")

    # --- PLACEHOLDER FOR YOUR MCP / SNOWFLAKE LOGIC ---
    # Example:
    # response = run_mcp_snowflake_query(f"Find cases similar to {case_number}")

    # Mocking the response for the POC
    simulated_output = (
        f"Snowball Analysis for {case_number}:\n"
        f"• Similar Case #1: C8839210 (Root cause: Network timeout via Zscaler proxy)\n"
        f"• Similar Case #2: C7742119 (Resolution: Updated socket timeout parameters)\n"
        f"• Recommendation: Verify websocket connection states and proxy route configurations."
    )

    return simulated_output


# ==========================================
# 3. SLACK EVENT LISTENER & HANDLER
# ==========================================
@app.event("message")
def handle_incoming_case_request(event, say):
    # Ignore edits, deletions, or bot-generated messages to prevent loops
    if event.get("subtype") or event.get("bot_id"):
        return

    channel_id = event.get("channel")
    text = event.get("text", "")
    user = event.get("user")
    message_ts = event.get("ts")

    # Filter: Only process messages from your designated target channels
    if channel_id not in TARGET_CHANNEL_IDS:
        return

    print(f"🎯 Matched Target Channel [{channel_id}] from user <@{user}>")
    print(f"   Incoming Text: {text}")

    # Regex to catch case numbers matching patterns like 'C10999999' or 'Snowball C10999999'
    # Adjust pattern if your naming convention differs
    case_match = re.search(r'\b(C\d{7,10})\b', text, re.IGNORECASE)

    if case_match:
        case_number = case_match.group(1).upper()
        print(f"🔍 Case Number Extracted: {case_number}")

        # Acknowledge receipt immediately in the thread
        say(
            text=f"Hi <@{user}>, detected case **{case_number}**. Querying Snowflake Cortex via MCP...",
            thread_ts=message_ts
        )

        try:
            # 1. Call MCP / Snowflake Logic
            analysis_result = query_snowflake_cortex_for_similar_cases(case_number)

            # 2. Save response locally to a file
            output_filename = f"analysis_{case_number}.txt"
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(analysis_result)
            print(f"💾 Saved analysis output to local file: {output_filename}")

            # 3. Send results back to the Slack channel thread
            formatted_reply = (
                f"📊 *Snowflake Cortex Analysis for {case_number}*:\n```\n{analysis_result}\n```\n"
                f"*(Report also archived locally to `{output_filename}`)*"
            )
            say(
                text=formatted_reply,
                thread_ts=message_ts
            )

        except Exception as e:
            print(f"❌ Error processing case query: {e}")
            say(
                text=f"Sorry <@{user}>, an error occurred while querying Snowflake for {case_number}.",
                thread_ts=message_ts
            )
    else:
        # Optional: Reply if someone posts without a valid case number format
        if "help" in text.lower():
            say(
                text=f"Hi <@{user}>, to search for similar cases, please include a case identifier (e.g., `C10999999`) in your message.",
                thread_ts=message_ts
            )


# ==========================================
# 4. EXECUTION
# ==========================================
if __name__ == "__main__":
    print(f"⚡️ Slack POC Listener active! Monitoring {len(TARGET_CHANNEL_IDS)} channels...")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()