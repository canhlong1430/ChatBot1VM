import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
import pytz
import nest_asyncio
import os
import json
nest_asyncio.apply()  # Fix lỗi nested event loop

# ===============================
# Hàm kết nối Google Sheets
# ===============================
def connect_google_sheets(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

    client = gspread.authorize(creds)
    sheet = client.open(sheet_name)
    return sheet

def update_google_sheet(data, sheet_name):
    sheet = connect_google_sheets(sheet_name)  # Hàm kết nối Google Sheets
    vn_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.datetime.now(vn_tz)

    today_date = now.strftime("%d-%m-%Y")
    current_time = now.strftime("%H:%M:%S")

    # Lấy danh sách tất cả sheet trong file
    worksheets = sheet.worksheets()
    sheet_titles = [ws.title for ws in worksheets]

    if len(sheet_titles) > 0:
        latest_sheet = sheet_titles[-1]  # Sheet cuối cùng trong danh sách
        if latest_sheet != today_date:
            # Rename sheet cũ thành ngày mới
            sheet.worksheet(latest_sheet).update_title(today_date)

            # Xóa dữ liệu cũ, giữ lại tiêu đề
            worksheet = sheet.worksheet(today_date)
            worksheet.batch_clear(["A2:D1000"])  # Xóa dữ liệu từ dòng 2 trở đi

    try:
        worksheet = sheet.worksheet(today_date)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=today_date, rows="1000", cols="4")
        worksheet.append_row(["Title", "Summary", "Link", "Updated Time"])

    # Cập nhật thời gian vào ô D1
    worksheet.update(range_name='D1', values=[[f"Cập nhật lúc: {current_time} (GMT+7)"]])

    # Kiểm tra các link đã có để tránh trùng lặp
    existing_links = set(row[2] for row in worksheet.get_all_values()[1:] if len(row) > 2)
    new_data = [row for row in data if row[2] not in existing_links]

    if new_data:
        worksheet.append_rows(new_data, value_input_option="RAW")
        print(f"Đã thêm {len(new_data)} tin mới vào Google Sheet {sheet_name}.")
    else:
        print(f"Không có tin mới để thêm vào {sheet_name}.")

# ===============================
# Lấy tin tức từ website
# ===============================
def get_news(url, headers):
    href = []
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, 'html.parser')
    mydiv_nqs = soup.find_all('h2', {'class': 'b-grid__title'})
    mydiv_nqs1 = soup.find_all('h3', {'class': 'b-grid__title'})

    for new in mydiv_nqs + mydiv_nqs1:
        link = new.a.get('href')
        r = requests.get(link)
        soup = BeautifulSoup(r.text, 'html.parser')
        smr = soup.find('p', {'class': 'sc-longform-header-sapo block-sc-sapo'})
        summary = smr.get_text() if smr else "No summary available"
        title = new.a.get_text()
        href.append((title, summary, link))

    return href

# ===============================
# Bot DoanhNghiepNQS
# ===============================
async def send_news_doanhnghiepnqs():

    print("Bot DoanhNghiepNQS đang gửi tin tức...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    href = get_news('https://nguoiquansat.vn/doanh-nghiep', headers)
    chat_id = "@newdndn"  # 🔥 Thay bằng username channel hoặc -100xxxxxxxxxx nếu là kênh private

    if href:
        for title, summary, link in href:
            await asyncio.sleep(1)  # Chờ 1 giây trước khi gửi tin nhắn tiếp theo

            message = f"📢 {title}\n{summary}\n🔗 {link}"
            await bot_doanhnghiepnqs.bot.send_message(chat_id=chat_id, text=message, disable_notification=True)
    update_google_sheet(href, "DoanhNghiepNQS")

async def run_bot_doanhnghiepnqs():
    global bot_doanhnghiepnqs
    bot_doanhnghiepnqs = ApplicationBuilder().token("7555641534:AAHmv8xvoycx7gDQrOMcbEYcHtv1yJJjGc8").build()
    bot_doanhnghiepnqs.add_handler(CommandHandler("start", start_doanhnghiepnqs))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_news_doanhnghiepnqs, 'interval', minutes=2, misfire_grace_time=30)
    scheduler.start()

    print("Bot DoanhNghiepNQS đang chạy...")
    await bot_doanhnghiepnqs.run_polling()

async def start_doanhnghiepnqs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Bot DoanhNghiepNQS đã hoạt động!")

# ===============================
# Bot ViMoNQS
# ===============================
async def send_news_vimonqs():
    print("Bot ViMoNQS đang gửi tin tức...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    href = get_news('https://nguoiquansat.vn/vi-mo', headers)
    chat_id = "@nqsvmm"  # 🔥 Thay bằng username channel hoặc -100xxxxxxxxxx nếu là kênh private

    if href:
        for title, summary, link in href:
            await asyncio.sleep(1.5)  # Chờ 1 giây trước khi gửi tin nhắn tiếp theo

            message = f"📢 {title}\n{summary}\n🔗 {link}"
            await bot_vimonqs.bot.send_message(chat_id=chat_id, text=message, disable_notification=True)

    update_google_sheet(href, "ViMoNQS")

async def run_bot_vimonqs():
    global bot_vimonqs
    bot_vimonqs = ApplicationBuilder().token("8155741015:AAH4Ck3Dc-tpWKFUn8yMLZrNUTOLruZ3q9A").build()
    bot_vimonqs.add_handler(CommandHandler("start", start_vimonqs))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_news_vimonqs, 'interval', minutes=2, misfire_grace_time=30)
    scheduler.start()

    print("Bot ViMoNQS đang chạy...")
    await bot_vimonqs.run_polling()

async def start_vimonqs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Bot ViMoNQS đã hoạt động!")

# ===============================
# Chạy song song hai bot
# ===============================
async def main():
    await asyncio.gather(run_bot_vimonqs(), run_bot_doanhnghiepnqs())

if __name__ == "__main__":
    asyncio.run(main())
