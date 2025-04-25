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
# Cấu hình bot Telegram
BOT_CONFIGS = [
    {"token": os.getenv("BOT_TOKEN_1"), "chat_id": "@newdndn", "url": "https://nguoiquansat.vn/doanh-nghiep", "sheet_name": "DoanhNghiepNQS"},
    {"token": os.getenv("BOT_TOKEN_2"), "chat_id": "@newvmvm", "url": "https://nguoiquansat.vn/vi-mo", "sheet_name": "ViMoNQS"}
]

bots = [Bot(cfg["token"]) for cfg in BOT_CONFIGS]

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

# Load & lưu danh sách tin đã gửi (xóa tin quá 3 ngày)
def load_sent_news():
    try:
        with open(SENT_NEWS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Lọc tin tức cũ hơn 3 ngày
            three_days_ago = datetime.datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")) - datetime.timedelta(days=3)
            return {link: date for link, date in data.items() if datetime.datetime.fromisoformat(date) > three_days_ago}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_sent_news(sent_news):
    with open(SENT_NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(sent_news, f, ensure_ascii=False, indent=4)

# Lưu tin với timestamp
sent_news = load_sent_news()

def mark_news_sent(link):
    sent_news[link] = datetime.datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).isoformat()
    save_sent_news(sent_news)

# Lấy tin tức
def get_news(url, config):
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

        try:
            r = requests.get(link, headers=headers, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')
            summary = soup.find('p', {'class': 'sc-longform-header-sapo'})
            news_list.append(
                (new.get_text(strip=True), summary.get_text(strip=True) if summary else "Không có tóm tắt", link,
                 datetime.datetime.now(pytz.timezone("Asia/Ho_Chi_Minh")).strftime("%H:%M:%S")))
        except requests.RequestException:
            continue
    #update_google_sheet(news_list, config["sheet_name"])
    return news_list

# Cập nhật Google Sheets
def update_google_sheet(data, sheet_name):
    if not data:
        return

    sheet = connect_google_sheets(sheet_name)
    vn_tz = pytz.timezone("Asia/Ho_Chi_Minh")
    now = datetime.datetime.now(vn_tz)
    today_date = now.strftime("%d-%m-%Y")

    worksheets = sheet.worksheets()
    if worksheets:
        last_sheet = worksheets[-1]
        if last_sheet.title != today_date:
            last_sheet.update_title(today_date)
            last_sheet.clear()
            last_sheet.append_row(["Title", "Summary", "Link", "Updated Time"])
    else:
        last_sheet = sheet.add_worksheet(title=today_date, rows="1000", cols="4")
        last_sheet.append_row(["Title", "Summary", "Link", "Updated Time"])
    
    existing_links = set(row[2] for row in last_sheet.get_all_values()[1:] if len(row) > 2)
    all_sent_links = sent_news.keys()

    new_data = [row for row in data if row[2] not in existing_links]
    
    if new_data:
        last_sheet.append_rows(new_data, value_input_option="RAW")
        print(f"Đã thêm {len(new_data)} tin mới vào Google Sheet {sheet_name}.")

# Gửi tin tức tới Telegram
async def send_news(bot, config):
    news_list = get_news(config["url"], config)
    update_google_sheet(news_list, config["sheet_name"])
    if not news_list:
        print(f"📭 Không có tin mới từ {config['url']}")
        return

    for title, summary, link, time in news_list:
        if link in sent_news:
            continue
        
        message = f"📢 *{title}*\n{summary}\n🔗 {link}"
        try:
            await bot.send_message(chat_id=config["chat_id"], text=message, parse_mode="Markdown")
            mark_news_sent(link)  # Lưu tin đã gửi
        except Exception as e:
            print(f"⚠️ Lỗi gửi tin: {e}")

# Scheduler
scheduler = BackgroundScheduler()
async def schedule_news_sending():
    print("🕒 Scheduler bắt đầu gửi tin...")
    tasks = [send_news(bot, cfg) for bot, cfg in zip(bots, BOT_CONFIGS)]
    await asyncio.gather(*tasks)

if not scheduler.get_jobs():
    scheduler.add_job(lambda: asyncio.run(schedule_news_sending()), 'interval', minutes=2, max_instances=10, replace_existing=True)
    scheduler.start()
    print("✅ Scheduler đã khởi động!")

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    Update.de_json(request.get_json(), bots[0])
    return "OK"

if __name__ == "__main__":
    app.debug = False
    app.use_reloader = False
    for i, bot in enumerate(bots):
        bot.set_webhook(url=f"{os.getenv('WEBHOOK_URL')}/{i}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
