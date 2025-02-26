async def run_bot(token, url, sheet_name, chat_id, minutes):
    bot = ApplicationBuilder().token(token).build()
    bot.add_handler(CommandHandler("start", lambda update, context: update.message.reply_text(f"Bot {sheet_name} đã hoạt động!")))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: asyncio.create_task(send_news(bot, url, sheet_name, chat_id)), 'interval', minutes=minutes, misfire_grace_time=30)
    scheduler.start()

    logger.info(f"Bot {sheet_name} đang chạy...")

    await bot.initialize()
    await bot.start()
    await bot.run_polling(allowed_updates=Update.ALL_TYPES)  # ✅ Dùng thay cho bot.idle()
