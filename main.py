import asyncio
import os
import json
import requests
import gspread
import nest_asyncio
from flask import Flask, request
from telegram import Bot, Update
from apscheduler.schedulers.background import BackgroundScheduler
from oauth2client.service_account import ServiceAccountCredentials
from bs4 import BeautifulSoup
import datetime
import pytz

nest_asyncio.apply()

app = Flask(__name__)
SENT_NEWS_FILE = "sent_news.json"

# Kết nối Google Sheets
def connect_google_sheets(sheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("❌ Lỗi: GOOGLE_CREDENTIALS không tồn tại!")
    try:
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds).open(sheet_name)
    except json.JSONDecodeError:
        raise ValueError("❌ Lỗi: GOOGLE_CREDENTIALS không hợp lệ!")

# Load & lưu danh sách tin đã gửi
def load_sent_news():
    try:
        with open(SENT_NEWS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_sent_news(sent_news):
    with open(SENT_NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(sent_news), f, ensure_ascii=False, indent=4)

sent_news = load_sent_news()

# Lấy tin tức từ Người Quan Sát
def get_news(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
    except requests.RequestException:
        return []

    news_list = []
    for new in soup.find_all(['h2', 'h3'], {'class': 'b-grid__title'}):
        link_tag = new.find('a')
        if not link_tag:
            continue
        link = link_tag.get('href')
        if not link or "http" in link:
            continue

        try:
            r = requests.get(link, headers=headers, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')
            summary = soup.find('p', {'class': 'sc-longform-header-sapo'})
            news_list.append(
                (new.get_text(strip=True), summary.get_text(strip=True) if summary else "Không có tóm tắt", link))
        except requests.RequestException:
            continue
    return news_list

# Cập nhật Google Sheets
def update_google_sheet(data, sheet_name):
    if not data:
        return

    sheet = connect_google_sheets(sheet_name)
    vn_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.datetime.now(vn_tz)
    today_date = now.strftime("%d-%m-%Y")
    current_time = now.strftime("%H:%M:%S")

    try:
        worksheet = sheet.worksheet(today_date)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=today_date, rows="1000", cols="4")
        worksheet.append_row(["Title", "Summary", "Link", "Updated Time"])

    worksheet.update(range_name="D1", values=[[f"Cập nhật lúc: {current_time} (GMT+7)"]])

    existing_links = set(row[2] for row in worksheet.get_all_values()[1:] if len(row) > 2)
    new_data = [row for row in data if row[2] not in existing_links]

    if new_data:
        worksheet.append_rows(new_data, value_input_option="RAW")
        print(f"Đã thêm {len(new_data)} tin mới vào Google Sheet {sheet_name}.")

# Gửi tin tức tới Telegram
async def send_news(bot, config):
    news_list = get_news(config["url"])
    if not news_list:
        print(f"📭 Không có tin mới từ {config['url']}")
        return

    new_entries = []
    for title, summary, link in news_list:
        message = f"📢 *{title}*\n{summary}\n🔗 {link}"
        try:
            await bot.send_message(chat_id=config["chat_id"], text=message, parse_mode="Markdown")
            sent_news.add(link)
            save_sent_news(sent_news)
            new_entries.append(
                (title, summary, link, datetime.datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%H:%M:%S")))
        except Exception as e:
            print(f"⚠️ Lỗi gửi tin: {e}")

    update_google_sheet(new_entries, config["sheet_name"])

# Cấu hình bot Telegram
BOT_CONFIGS = [
    {"token": os.getenv("BOT_TOKEN_1"), "chat_id": 7286547285 , "url": "https://nguoiquansat.vn/doanh-nghiep", "sheet_name": "DoanhNghiepNQS"},
    {"token": os.getenv("BOT_TOKEN_2"), "chat_id": 7286547285, "url": "https://nguoiquansat.vn/vi-mo", "sheet_name": "ViMoNQS"}
]

bots = [Bot(cfg["token"]) for cfg in BOT_CONFIGS]

# Scheduler
scheduler = BackgroundScheduler()
async def schedule_news_sending():
    print("🕒 Scheduler bắt đầu gửi tin...")
    tasks = [send_news(bot, cfg) for bot, cfg in zip(bots, BOT_CONFIGS)]
    await asyncio.gather(*tasks)

if not scheduler.get_jobs():
    scheduler.add_job(lambda: asyncio.run(schedule_news_sending()), 'interval', minutes=2, max_instances=1,
                      replace_existing=True)
    scheduler.start()
    print("✅ Scheduler đã khởi động!")

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    Update.de_json(request.get_json(), bots[0])
    return "OK"

if __name__ == "__main__":
    app.debug = False
    app.use_reloader = False
    for bot in bots:
        bot.set_webhook(url=os.getenv("WEBHOOK_URL"))
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
