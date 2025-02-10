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
import pytz  # Xử lý múi giờ

nest_asyncio.apply()  # Fix lỗi nested event loop

# Hàm kết nối Google Sheets
def connect_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

    client = gspread.authorize(creds)
    sheet = client.open("ViMo")  # Tên Google Sheet
    return sheet

# Hàm lấy tin tức từ website
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
        title = new.a.get_text().strip()
        href.append((title, summary.strip(), link))

    return href

# Hàm cập nhật Google Sheet
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
        worksheet = sheet.add_worksheet(title=today_date, rows="1000", cols="4")
        worksheet.append_row(["Title", "Summary", "Link"])

    # Ghi thời gian cập nhật vào ô D1 (giá trị cần nằm trong danh sách lồng nhau)
    worksheet.update('D1', [[f"Cập nhật lúc: {current_time} (GMT+7)"]])

    # Kiểm tra link đã tồn tại
    existing_links = set(row[2] for row in worksheet.get_all_values()[1:] if len(row) > 2)
    new_data = [row for row in data if row[2] not in existing_links]

    if new_data:
        worksheet.append_rows(new_data, value_input_option="RAW")
        print(f"Đã thêm {len(new_data)} t
