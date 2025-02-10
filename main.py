import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import datetime
import nest_asyncio
import os
import json
import pytz  # Thêm pytz để xử lý múi giờ
nest_asyncio.apply()  # Fix lỗi nested event loop

def connect_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

    client = gspread.authorize(creds)
    sheet = client.open("ViMo")  # Tên Google Sheet
    return sheet

def getnew():
    href = []
    r = requests.get('https://nguoiquansat.vn/vi-mo')
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

def update_google_sheet(data):
    sheet = connect_google_sheets()
    
    # Lấy thời gian hiện tại theo múi giờ Việt Nam (GMT+7)
    vn_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.datetime.now(vn_tz)
    today_date = now.strftime("%d-%m-%Y")
    current_time = now.strftime("%H:%M:%S")

    try:
        worksheet = sheet.worksheet(today_date)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=today_date, rows="1000", cols="3")
        worksheet.append_row(["Title", "Summary", "Link"])

    # Ghi đè thời gian cập nhật vào ô A1
    worksheet.update('A1', [[f"Cập nhật lúc: {current_time} (GMT+7)"]])

    # Kiểm tra các link đã tồn tại
    existing_links = set()
    all_rows = worksheet.get_all_values()
    for row in all_rows[1:]:  # Bỏ qua hàng đầu tiên (thời gian cập nhật)
        if len(row) > 2:
            existing_links.add(row[2])

    new_data = [row for row in data if row[2] not in existing_links]

    if new_data:
        worksheet.append_rows(new_data, value_input_option="RAW")
        print(f"Đã thêm {len(new_data)} tin mới vào Google Sheet.")
    else:
        print("Không có tin mới để thêm.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(f'Xin chào! Chat ID của bạn là: {chat_id}')

async def send_news():
    print("Đang tự động gửi tin tức...")
    href = getnew()
    chat_id = 7286547285  # Thay chat_id bằng ID của bạn

    if href:
        for title, summary, link in href:
            message = f"{title}\n{summary}\n{link}"
            await app.bot.send_message(chat_id=chat_id, text=message)

    update_google_sheet(href)

async def main():
    # Cấu hình bot Telegram
    global app
    app = ApplicationBuilder().token("8155741015:AAH4Ck3Dc-tpWKFUn8yMLZrNUTOLruZ3q9A").build()
    app.add_handler(CommandHandler("start", start))

    # Lên lịch tự động gửi tin mỗi 90 phút
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_news, 'interval', minutes=1)
    scheduler.start()

    print("Bot đang chạy...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
