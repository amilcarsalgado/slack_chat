import getpass
from snowflake.snowpark import Session


def main():
    # 1. Dynamically build your user ID (e.g., ASALGADO@CIENA.COM)
    current_user = getpass.getuser().upper() + "@CIENA.COM"
    print(f"Attempting Okta SSO login for: {current_user}")

    # 2. Match the exact connection dictionary from the GUI disassembly
    connection_parameters = {
        "account": "ciena-ciena",  # [cite: 2]
        "user": current_user,  # [cite: 2]
        "authenticator": "externalbrowser",  # [cite: 2]
        "role": "SSO_SNOWFLAKE_GAI_SVC_RO",  # [cite: 2]
        "warehouse": "GAI_POC",  # [cite: 2]
        "database": "FLYGAIP",  # [cite: 2]
        "schema": "GAI_SERVICES",  # [cite: 2]
        # Critical network bypasses for corporate proxies (e.g., Zscaler)
        "insecure_mode": True,  # [cite: 2]
        "disable_ocsp_checks": True  # [cite: 2]
    }

    try:
        # 3. Build and create the Snowpark Session
        print("Waiting for browser authentication...")
        session = Session.builder.configs(connection_parameters).create()

        # 4. Verify the connection worked
        print("\n✅ Successfully connected to Snowpark!")

        # 5. The POC Task: Ask Cortex to summarize a dummy network outage
        mock_log = (
            "14:02 EST - ALARM: Loss of Signal (LOS) on Slot 3, Port 1. "
            "14:15 EST - Field tech dispatched to site. "
            "15:00 EST - Tech reports suspected fiber cut outside the facility. "
            "15:15 EST - Splicing team notified."
        )

        prompt = f"Summarize this network outage event in one short sentence: {mock_log}"

        print("\nSending prompt to Snowflake Cortex (llama3.1-8b)...")

        # Execute the native Cortex COMPLETE function
        query = f"SELECT SNOWFLAKE.CORTEX.COMPLETE('llama3.1-8b', '{prompt}') AS AI_RESPONSE"
        df = session.sql(query)

        # Collect fetches the data back to your local PyCharm memory
        results = df.collect()

        print("\n--- Cortex AI Response ---")
        # Extract the text from the first row and first column of the results
        print(results[0]["AI_RESPONSE"])
        print("--------------------------")

    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
    finally:
        # Always close the session to free up Snowflake resources
        if 'session' in locals():
            session.close()
            print("\nSession closed.")


if __name__ == "__main__":
    main()