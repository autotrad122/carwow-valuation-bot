import os
import json
import time
import asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build
from playwright.async_api import async_playwright

# --- Load secrets from environment ---
SHEET_ID = os.environ['SHEET_ID']
GOOGLE_CREDS_JSON = os.environ['GOOGLE_CREDS_JSON']

def get_sheets_service():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return build('sheets', 'v4', credentials=creds)

async def get_carwow_price(playwright, reg, mileage):
    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page()
    try:
        await page.goto("https://www.carwow.co.uk/car-valuation")
        await page.fill('input[name="registration"]', reg)
        await page.fill('input[name="mileage"]', str(mileage))
        await page.click('button:has-text("Get valuation")')
        await page.wait_for_selector('[data-testid="valuation-price"]', timeout=10000)
        price_text = await page.text_content('[data-testid="valuation-price"]')
        price = int(price_text.replace('£', '').replace(',', '').strip())
        await browser.close()
        return price
    except Exception as e:
        await browser.close()
        print(f"Failed to get valuation for {reg}: {e}")
        return None

async def main():
    sheets = get_sheets_service()
    sheet_range = 'raw_data!A2:H'
    sheet = sheets.spreadsheets()

    # Get data
    result = sheet.values().get(spreadsheetId=SHEET_ID, range=sheet_range).execute()
    rows = result.get('values', [])

    updates = []
    async with async_playwright() as p:
        for i, row in enumerate(rows):
            if len(row) < 5:
                continue  # skip incomplete rows
            reg = row[2].strip()
            mileage = row[3].strip()
            ask_price = float(row[4])

            print(f"Fetching valuation for {reg}...")
            val = await get_carwow_price(p, reg, mileage)
            if val:
                delta = round(ask_price / val, 3)
                update_row = row[:5] + [val, delta] + row[7:8]
            else:
                update_row = row[:5] + ["", ""] + row[7:8]
            updates.append(update_row)
            time.sleep(3)  # polite delay

    # Push updated values
    sheet.values().update(
        spreadsheetId=SHEET_ID,
        range=sheet_range,
        valueInputOption="RAW",
        body={"values": updates}
    ).execute()

if __name__ == '__main__':
    asyncio.run(main())

