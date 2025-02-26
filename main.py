import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import pytz
import os
import json
import logging

# ===============================
# Setup logging
# ===============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===============================
# Hàm kết nối Google Sheets
# ===============================
def connect_google_sheets(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        logger.error("GOOGLE_CREDENTIALS không tồn tại!")
        return None
    
    try:
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open(sheet_name)
        return sheet
    except json.JSONDecodeError as e:
        logger.error(f"Lỗi JSONDecodeError: {e}")
        return None

def update_google_sheet(data, sheet_name):
    sheet = connect_google_sheets(sheet_name)
    if not sheet:
        return set()
    
    vn_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.datetime.now(vn_tz)
    today_date = now.strftime("%d-%m-%Y")
    current_time = now.strftime("%H:%M:%S")

    try:
        worksheet = sheet.worksheet(today_date)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=today_date, rows="1000", cols="4")
        worksheet.append_row(["Title", "Summary", "Link", "Updated Time"])

    worksheet.update(range_name='D1', values=[[f"Cập nhật lúc: {current_time} (GMT+7)"]])

    existing_links = set(row[2] for row in worksheet.get_all_values()[1:] if len(row) > 2)
    new_data = [row for row in data if row[2] not in existing_links]

    if new_data:
        worksheet.append_rows(new_data, value_input_option="RAW")
        logger.info(f"Đã thêm {len(new_data)} tin mới vào Google Sheet {sheet_name}.")
    else:
        logger.info(f"Không có tin mới để thêm vào {sheet_name}.")

    return existing_links

# ===============================
# Lấy tin tức từ website
# ===============================
def get_news(url, headers):
    href = []
    r = requests.get(url, headers=headers)
    r.encoding = 'utf-8'
    soup = BeautifulSoup(r.text, 'html.parser')

    mydiv_nqs = soup.find_all('h2', {'class': 'b-grid__title'})
    mydiv_nqs1 = soup.find_all('h3', {'class': 'b-grid__title'})

    for new in mydiv_nqs + mydiv_nqs1:
        link = new.a.get('href')
        r = requests.get(link)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'html.parser')
        smr = soup.find('p', {'class': 'sc-longform-header-sapo block-sc-sapo'})
        summary = smr.get_text() if smr else "No summary available"
        title = new.a.get_text()
        href.append((title, summary, link))

    return href

# ===============================
# Bot gửi tin tức
# ===============================
async def send_news(bot, url, sheet_name, chat_id):
    logger.info(f"Bot {sheet_name} đang gửi tin tức...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    href = get_news(url, headers)
    existing_links = update_google_sheet(href, sheet_name)

    if href:
        for title, summary, link in href:
            if link not in existing_links:
                await asyncio.sleep(1)
                message = f"📢 {title}\n{summary}\n🔗 {link}"
                try:
                    await bot.bot.send_message(chat_id=chat_id, text=message)
                except Exception as e:
                    logger.error(f"Lỗi khi gửi tin: {e}")

# ===============================
# Chạy bot với APScheduler
# ===============================
async def run_bot(token, url, sheet_name, chat_id, minutes):
    bot = ApplicationBuilder().token(token).build()
    bot.add_handler(CommandHandler("start", lambda update, context: update.message.reply_text(f"Bot {sheet_name} đã hoạt động!")))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: asyncio.create_task(send_news(bot, url, sheet_name, chat_id)), 'interval', minutes=minutes, misfire_grace_time=30)
    scheduler.start()

    logger.info(f"Bot {sheet_name} đang chạy...")
    
    # ✅ Không dùng await để tránh lỗi Railway
    asyncio.create_task(bot.run_polling())

# ===============================
# Chạy nhiều bot cùng lúc
# ===============================
async def main():
    tasks = [
        run_bot("7555641534:AAHmv8xvoycx7gDQrOMcbEYcHtv1yJJjGc8", 'https://nguoiquansat.vn/doanh-nghiep', "DoanhNghiepNQS", "@newdndn", 6),
        run_bot("8155741015:AAH4Ck3Dc-tpWKFUn8yMLZrNUTOLruZ3q9A", 'https://nguoiquansat.vn/vi-mo', "ViMoNQS", "@newvmvm", 4)
    ]
    await asyncio.gather(*tasks)

# ===============================
# Entry Point
# ===============================
if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()  # ✅ Tạo event loop mới
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except RuntimeError as e:
        logger.error(f"Lỗi runtime: {e}")
