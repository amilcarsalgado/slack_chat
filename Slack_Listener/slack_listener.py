import logging
from datetime import datetime

# logging.basicConfig(level=logging.INFO)

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
    "C09GV7JFGV7": "cpo-broadband-team"
    #"C08PFDQM5M0": "ert-active-outages-channel"
}

TARGET_CHANNEL_IDS = [
    "C0C4051R9SN",  # #di-test
    "C09GV7JFGV7"  # #cpo-broadband-team
    # "C08PFDQM5M0" # #ert-active-outages-channel
]

app = App(token=SLACK_BOT_TOKEN)

# ==========================================
# 3. CODEWORD & TEMPLATE CONFIGURATION
# ==========================================
PROMPT_TEMPLATES = {
    "snowball": "Snow_Prompt_S.txt",
    "snowfall": "Snow_Prompt_C.txt",
    "snowman": "Snow_Prompt_M.txt"
}
DEFAULT_CODEWORD = "snowball"


# ==========================================
# 4. TEMPLATE LOADING & PROMPT GENERATION
# ==========================================
def create_prompt_file(case_number: str, template_filename: str, codeword: str) -> str:
    if not os.path.exists(template_filename):
        raise FileNotFoundError(f"Could not find template file: {template_filename}")

    with open(template_filename, "r", encoding="utf-8") as f:
        template_content = f.read()

    prompt_content = template_content.format(case_number=case_number)

    # Ensure generated text files have distinct names based on the codeword used
    output_filename = f"{case_number}_{codeword.upper()}.txt"

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(prompt_content)

    return output_filename


# ==========================================
# 5. SLACK EVENT LISTENER & HANDLER
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

    # Step 1: Look for any valid case number in the message
    case_match = re.search(r'\b(C\d{7,10})\b', text, re.IGNORECASE)

    if case_match:
        case_number = case_match.group(1).upper()
        text_lower = text.lower()
        selected_codeword = DEFAULT_CODEWORD

        # Step 2: Search the message independently for any known codeword
        for keyword in PROMPT_TEMPLATES.keys():
            if keyword in text_lower:
                selected_codeword = keyword
                break

        template_file = PROMPT_TEMPLATES[selected_codeword]

        say(
            text=f"Hi <@{user}>, detected case **{case_number}** using codeword `{selected_codeword}`. Generating prompt file from `{template_file}`...",
            thread_ts=message_ts
        )
        print(
            f"{timestamp} : [#{channel_name}] Hi <@{user}>, detected case **{case_number}** using codeword `{selected_codeword}`. Generating prompt file from `{template_file}`...")

        try:
            saved_filename = create_prompt_file(case_number, template_file, selected_codeword)
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

            # 🛠 THE FIX: Strip out Okta Auth and Metadata header
            if "Answer:" in mcp_output:
                mcp_output = mcp_output.split("Answer:", 1)[-1].strip()

            # 🛠️ THE FIX: Bulletproof Mojibake Translation using latin1
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
        # Dynamically check if they typed any valid keyword but messed up the case number format
        text_lower = text.lower()
        for keyword in PROMPT_TEMPLATES.keys():
            if keyword in text_lower:
                say(
                    text=f"Hi <@{user}>, I detected '{keyword}' but couldn't parse a valid case number format.",
                    thread_ts=message_ts
                )
                print(f"{timestamp} : [#{channel_name}] Detected '{keyword}' but couldn't parse case number.")
                break


# ==========================================
# 6. EXECUTION
# ==========================================
if __name__ == "__main__":
    print(f"⚡️ Slack Listener active! Monitoring channels: {', '.join(CHANNEL_MAP.values())}")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()