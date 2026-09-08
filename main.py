import tkinter as tk
from tkinter import filedialog
import pandas as pd
import sys
import re
import os


def main():
    # 1. Prompt for User Name in the console with your hard-coded default
    user_input = input("Please enter your User Name (Press Enter to use default 'Alvaro Salgado'):")

    # If you just press Enter, it defaults to "Alvaro Salgado".
    user_name = user_input.strip() if user_input.strip() else "Alvaro Salgado"

    # Initialize tkinter and hide the main background window
    root = tk.Tk()
    root.withdraw()

    # 2. Open the Windows file explorer to select the Excel file
    print(f"\nHello, {user_name}! Opening the file explorer so you can select your Excel file...")

    # This forces the file dialog to appear on top of other windows
    root.attributes('-topmost', True)

    file_path = filedialog.askopenfilename(
        title="Select Excel File",
        filetypes=[
            ("Excel files", "*.xlsx *.xls *.xlsm"),
            ("All files", "*.*")
        ]
    )

    # Exit gracefully if the user closes the file dialog without selecting a file
    if not file_path:
        print("No file selected. Exiting...")
        sys.exit()

    print(f"Loading file: {file_path} ...")

    # 3. Open the file, check sheets, and count the rows and columns
    try:
        # Load the Excel file wrapper to see all sheet names
        xls = pd.ExcelFile(file_path)

        # Read the SECOND sheet (index 1) which contains your data
        df = pd.read_excel(file_path, sheet_name=1)

        # 4. Clean up the column names by removing hidden newline and space characters
        df.columns = df.columns.str.replace('\n', '').str.strip()

        # 5. Filter the DataFrame for rows where you are the SME
        sme_cases = df[df['SME'] == user_name].copy()

        # 6. Parse the number after "interactions=" in the 'Snapshot Age' column
        sme_cases['Parsed Interactions'] = sme_cases['Snapshot Age'].astype(str).str.extract(
            r"interactions\s*=\s*(\d+)")

        # 7. Count how many times "Item n" appears in the Comments column
        sme_cases['Item Count'] = sme_cases['Last k Comments/Work-notes in snapshot (k=20)'].astype(str).str.count(
            r"Item \d+")

        # 8. Print the final list of cases and map them to a list for selection
        print(f"\n--- Cases for SME: {user_name} ---")

        # We will store the cases in a list so line number '1' maps to index '0'
        case_list = []

        if sme_cases.empty:
            print("No cases found.")
            sys.exit()
        else:
            for index, row in sme_cases.iterrows():
                case_num = row['Case Number']
                interactions = row['Parsed Interactions']
                item_count = row['Item Count']

                # Handle cases where the regex didn't find a match for interactions
                if pd.isna(interactions):
                    interactions = "No number found"

                # Add to our list
                case_list.append(case_num)
                line_number = len(case_list)

                print(
                    f"{line_number} - Case Number: {case_num} | Interactions: {interactions} | Items Found: {item_count}")
        print("-" * 40 + "\n")

        # ---------------------------------------------------------
        # SINGLE PASS: Prompt for line number, Extract, Clipboard & File Gen
        # ---------------------------------------------------------

        # Prompt for the line number and validate the input
        try:
            selection = int(input("Enter the line number of the case you want to inspect: ").strip())

            # Ensure the number is actually in our list range
            if selection < 1 or selection > len(case_list):
                print(f"Invalid selection. Please enter a number between 1 and {len(case_list)}. Exiting...")
                sys.exit()
        except ValueError:
            print("Invalid input. Please type a number. Exiting...")
            sys.exit()

        # Retrieve the case number from the list (subtract 1 because Python lists start at 0)
        target_case = case_list[selection - 1]

        # Search for the case number in the dataframe
        case_row = df[df['Case Number'] == target_case]

        # Extract basic case info
        case_num = str(case_row.iloc[0]['Case Number'])
        base_case_num = case_num.split('-')[0]  # Strips the "-n" suffix

        # Confirming mapping: Subject (Col B) and Description (Col C)
        subject = str(case_row.iloc[0].get('Subject', 'No Subject'))
        description = str(case_row.iloc[0].get('Description', 'No Description'))

        # Grab the full text from the Comments column (Col F)
        full_cell_text = str(case_row.iloc[0]['Last k Comments/Work-notes in snapshot (k=20)'])

        if full_cell_text.lower() == 'nan' or not full_cell_text.strip():
            print("No comments found for this case. Exiting...")
            sys.exit()

        # Clean up the FULL interaction text by removing all blank lines for section 2
        cleaned_full_interaction = "\n".join([line for line in full_cell_text.splitlines() if line.strip()])

        # Find all instances of "Item n"
        matches = list(re.finditer(r"Item \d+", full_cell_text))

        if not matches:
            print("No 'Item' tags found in this case. Exiting...")
            sys.exit()

        # Get the last match object
        last_match = matches[-1]

        # Grab text from the LAST "Item n" to the end of the cell for section 4 (Text File)
        last_item_text = full_cell_text[last_match.start():]
        final_output = "\n".join([line for line in last_item_text.splitlines() if line.strip()])

        # Grab text EXCLUDING the "Item n" prefix for the Database Search Prompt
        search_text_raw = full_cell_text[last_match.end():]
        search_text = "\n".join([line for line in search_text_raw.splitlines() if line.strip()])

        # 1. Print and Copy to Clipboard
        db_prompt = (
            "Using FLYGAIP.GAI_SERVICES.RSVC_CASE_FEED_V (joined to FLYGAIP.GAI_SERVICES.RSVC_CASE_V on PARENT_ID = ID) "
            "and FLYGAIP.GAI_SERVICES.RSVC_CASEHISTORY_V (joined on CASEID = ID), find the CREATED_DATE/CREATEDDATE "
            "that corresponds to the following comment:\n\n"
            f"{search_text}\n\n"
            "Steps:\n"
            "1. Extract the case number from the comment text.\n"
            "2. Determine the comment type and query accordingly:\n"
            "   a. CASE CREATION (e.g., \"New Case Created\"): Query RSVC_CASEHISTORY_V where FIELD = 'created', "
            "or RSVC_CASE_FEED_V where TYPE = 'CreateRecordEvent'.\n"
            "   b. STATUS CHANGE (e.g., \"marked as In Progress\", \"marked as With Customer\", \"Case Being Worked\", \"Closed\"): "
            "Query RSVC_CASEHISTORY_V where FIELD = 'Status' and NEWVALUE matches the status described in the comment.\n"
            "   c. TEXT POST (e.g., analysis notes, customer update, case summary, engineer comment): "
            "Query RSVC_CASE_FEED_V and search the BODY column using LIKE with a distinctive phrase from the comment.\n"
            "3. Note: The BODY column may contain the Salesforce internal format of the comment, not the exact email template text. "
            "Try multiple distinctive phrases if the first search returns no results.\n"
            "4. Return the timestamp."
        )

        print("\n" + "=" * 60)
        print(db_prompt)
        print("=" * 60 + "\n")

        # Push to clipboard
        root.clipboard_clear()
        root.clipboard_append(db_prompt)
        root.update()
        print("[SUCCESS] The text above has been copied to your clipboard!\n")

        # 2. Prompt for the cut/off date response
        user_response = input("Please enter the response text for the cut/off date (Point 3):\n> ")

        # 3. Prompt for the Pass number
        pass_number = input("Is this Pass 1 or 2? (Enter 1 or 2):\n> ").strip()

        # 4. Create the text file
        filename = f"{base_case_num}.txt"
        n_items = len(matches)

        with open(filename, 'w', encoding='utf-8') as f:
            # Header
            f.write(f"This is Pass {pass_number} for case {base_case_num} with {n_items} Items\n\n")

            # Point 1 (Inline and stripped of suffix)
            f.write(f"1. Case number: {base_case_num}\n\n\n")

            # Point 2
            f.write("2. Case data Used by Kahuna\n\n")
            f.write("Subject:\n")
            f.write(f"{subject}\n\n")
            f.write("Description:\n")
            f.write(f"{description}\n\n")
            f.write("Interaction detail:\n")
            f.write(f"{cleaned_full_interaction}\n\n\n")

            # Point 3
            f.write("3. The cut/off date based on the last interaction\n\n")
            f.write(f"{user_response}\n\n\n")

            # Point 4
            f.write("4. Content of last Interaction\n\n")
            f.write(f"{final_output}\n")

        print(f"\n[SUCCESS] File '{filename}' has been created in your current folder!\n")
        print("-" * 60 + "\n")

    except Exception as e:
        print(f"An error occurred while reading the file: {e}")


if __name__ == "__main__":
    main()