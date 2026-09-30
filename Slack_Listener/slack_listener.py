import logging
from datetime import datetime

#logging.basicConfig(level=logging.INFO)

import os
import re
import subprocess
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# ==========================================
# 1. ENVIRONMENT & TOKEN CONFIGURATION V1
# ==========================================
# env_path = r"C:\Users\ravi\PycharmProjects\Slack_Chatalert\.env"
env_path = r"C:\Users\asalgado\PycharmProjects\Slack_Chatalert\.env"
load_dotenv(dotenv_path=env_path)

SLACK_BOT_TOKEN = os.getenv("SLACK_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
    raise EnvironmentError(f"CRITICAL: Tokens missing. Checked path: {env_path}")

# ==========================================
# 2. TARGET CHANNELS CONFIGURATION
# ==========================================
CHANNEL_MAP = {
    "C0C4051R9SN": "di-test",
    "C09GV7JFGV7": "cpo-broadband-team",
    "C08PFDQM5M0": "ert-active-outages-channel"
}

TARGET_CHANNEL_IDS = [
    "C0C4051R9SN",  # #di-test
    "C09GV7JFGV7"  # #cpo-broadband-team
    # "C08PFDQM5M0"  # #ert-active-outages-channel
]

app = App(token=SLACK_BOT_TOKEN)


# ==========================================
# 3. TEMPLATE LOADING & PROMPT GENERATION
# ==========================================
def create_ert_prompt_file(case_number: str) -> str:
    template_filename = "ERT_Prompt_Snowflake wo Product.txt"

    if not os.path.exists(template_filename):
        raise FileNotFoundError(f"Could not find template file: {template_filename}")

    with open(template_filename, "r", encoding="utf-8") as f:
        template_content = f.read()

    prompt_content = template_content.format(case_number=case_number)
    output_filename = f"{case_number}_ERT.txt"

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(prompt_content)

    return output_filename


# ==========================================
# 4. SLACK EVENT LISTENER & HANDLER
# ==========================================
@app.event("message")
def handle_incoming_case_request(event, say):
    if event.get("subtype") or event.get("bot_id"):
        return

    channel_id = event.get("channel")
    text = event.get("text", "")
    user = event.get("user")
    message_ts = event.get("ts")

    if channel_id not in TARGET_CHANNEL_IDS:
        return

    # Generate timestamp and resolve channel name
    timestamp = datetime.now().strftime("%d-%b-%y_%I:%M:%S%p")
    channel_name = CHANNEL_MAP.get(channel_id, "unknown-channel")

    print(f"{timestamp} : [#{channel_name}] API Interface for Python")
    print(f"{timestamp} : [#{channel_name}] Incoming Text from <@{user}>: {text}")

    case_match = re.search(r'Snowball\s+(C\d{7,10})', text, re.IGNORECASE)
    if not case_match:
        case_match = re.search(r'\b(C\d{7,10})\b', text, re.IGNORECASE)

    if case_match:
        case_number = case_match.group(1).upper()

        say(
            text=f"Hi <@{user}>, detected case **{case_number}**. Generating ERT prompt file from template...",
            thread_ts=message_ts
        )
        print(
            f"{timestamp} : [#{channel_name}] Hi <@{user}>, detected case **{case_number}**. Generating ERT prompt file from template...")

        try:
            saved_filename = create_ert_prompt_file(case_number)
            say(
                text=f"✅ Generated prompt: `{saved_filename}` for `{case_number}`. Sending to Snowflake... Response in ~ 5 mins!!",
                thread_ts=message_ts
            )
            print(
                f"{timestamp} : [#{channel_name}] Successfully generated prompt file: {saved_filename} for case {case_number}. Sending to Snowflake...\nIt will take ~ 5 mins to get a response!!")

            # mcp_python_exe = r"C:\Users\ravi\PycharmProjects\SnF_MCP_Test\.venv\Scripts\python.exe"
            # mcp_script_path = r"C:\Users\ravi\PycharmProjects\SnF_MCP_Test\call_snfl.py"

            mcp_python_exe = r"C:\Users\asalgado\PycharmProjects\SnF_MCP_Test\.venv\Scripts\python.exe"
            mcp_script_path = r"C:\Users\asalgado\PycharmProjects\SnF_MCP_Test\call_snfl.py"

            # Capture in memory cleanly
            result = subprocess.run(
                [mcp_python_exe, mcp_script_path, saved_filename],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                timeout=600
            )

            mcp_output = result.stdout.strip()

            # 🛠️ THE FIX: Strip out Okta Auth and Metadata header
            if "Answer:" in mcp_output:
                mcp_output = mcp_output.split("Answer:", 1)[-1].strip()

            # 🛠️ THE FIX: Bulletproof Mojibake Translation using latin1
            # latin1 prevents the 'charmap' crash because it perfectly maps all 256 byte values
            try:
                mcp_output = mcp_output.encode("latin1", errors="ignore").decode("utf-8", errors="replace")
            except Exception as decode_err:
                pass

            output_filename = f"{case_number}_snfl_op.txt"
            with open(output_filename, "w", encoding="utf-8") as out_f:
                out_f.write(mcp_output)

            formatted_reply = (
                f"📊 *Snowflake Cortex Analysis for Case {case_number}*:\n"
                f"```\n{mcp_output}\n```\n"
                f"*(Archived locally to `{output_filename}`)*"
            )
            say(
                text=formatted_reply,
                thread_ts=message_ts
            )
            print(f"{timestamp} : [#{channel_name}] Posted final Snowflake Cortex Analysis for Case {case_number}.")

        except subprocess.TimeoutExpired:
            say(
                text=f"⚠️ Sorry <@{user}>, the Snowflake query for {case_number} took longer than 10 minutes and timed out.",
                thread_ts=message_ts
            )
            print(f"{timestamp} : [#{channel_name}] Error: Subprocess timed out for case {case_number}.")
        except subprocess.CalledProcessError as e:
            say(
                text=f"❌ An error occurred while executing `call_snfl.py` for {case_number}.",
                thread_ts=message_ts
            )
            print(f"{timestamp} : [#{channel_name}] Error: Subprocess execution failed for {case_number}.")
        except Exception as e:
            say(
                text=f"Sorry <@{user}>, an error occurred: {str(e)}",
                thread_ts=message_ts
            )
            print(f"{timestamp} : [#{channel_name}] Error: {str(e)}")
    else:
        if "snowball" in text.lower():
            say(
                text=f"Hi <@{user}>, I detected 'Snowball' but couldn't parse a valid case number format.",
                thread_ts=message_ts
            )
            print(f"{timestamp} : [#{channel_name}] Detected 'Snowball' but couldn't parse case number.")


# ==========================================
# 5. EXECUTION
# ==========================================
if __name__ == "__main__":
    SocketModeHandler(app, SLACK_APP_TOKEN).start()