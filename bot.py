import os
import sqlite3
import hashlib
import random
from datetime import datetime, time
from zoneinfo import ZoneInfo
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============= 配置区 =============
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")
DAILY_PUSH_ENABLED = True
DAILY_PUSH_HOUR = 9
DAILY_PUSH_MINUTE = 0
DB_FILE = "checkin.db"

# ============= 数据库 =============
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            first_name TEXT,
            total_checkins INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            last_checkin TEXT,
            created_at TEXT,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            chat_title TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_chat(chat_id, chat_title):
    conn = get_db()
    conn.execute("""
        INSERT OR REPLACE INTO chats
        (chat_id, chat_title, created_at)
        VALUES (?, ?, COALESCE(
            (SELECT created_at FROM chats WHERE chat_id = ?),
            ?
        ))
    """, (chat_id, chat_title, chat_id, datetime.now(TIMEZONE).isoformat()))
    conn.commit()
    conn.close()

# ============= 工具函数 =============
def now(): return datetime.now(TIMEZONE)
def today(): return now().date().isoformat()

def get_display_name(user):
    if user.username: return f"@{user.username}"
    if user.first_name: return user.first_name
    return "用户"

def generate_fortune(user_id):
    date_string = today()
    seed = int(hashlib.md5(f"{user_id}-{date_string}".encode()).hexdigest(), 16)
    random.seed(seed)
    fortunes = [
        ("大吉", "🍀 好运正在靠近，今天适合做重要决定。"),
        ("吉", "🍵 一杯清茶，一份好运。慢下来，你会发现事情没有那么复杂。"),
        ("小吉", "✨ 今天会有一些小惊喜，保持好心情。"),
        ("吉", "💰 财运平稳，努力会得到不错的回应。"),
        ("大吉", "🌟 今天适合行动，犹豫可能会错过机会。"),
        ("平", "🌙 平稳的一天，少一点焦虑，多一点耐心。"),
        ("小吉", "☕ 今天适合处理积压已久的小事情。"),
        ("吉", "🌟 保持微笑，你今天的气场很足！"),
        ("大吉", "❤️ 人际关系顺利，可能会收到令人开心的消息。"),
        ("平", "🌿 保持节奏，不必急于证明自己，按部就班就是前进。"),
    ]
    return random.choice(fortunes)

# ============= 命令处理 =============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat: return
    save_chat(update.effective_chat.id, update.effective_chat.title or "私聊")
    await update.message.reply_text("""🤖 签到机器人 v1.0
欢迎使用！
📅 /checkin — 签到+运势
👤 /me — 我的资料
🏆 /rank — 排行榜
🔮 /fortune — 今日运势
ℹ️ /help — 帮助
也可直接发送：签到
""")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""📖 使用说明
发送「签到」或 /checkin 完成今日签到
/me 查看个人资料
/rank 查看本群排行
/fortune 单独查运势
🔥 连续签到越久奖励越多
""")

async def do_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_chat: return
    user, chat = update.effective_user, update.effective_chat
    save_chat(chat.id, chat.title or "私聊")
    display_name = get_display_name(user)
    current_date = today()
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE chat_id=? AND user_id=?", (chat.id, user.id)).fetchone()

    if row and row["last_checkin"] == current_date:
        lv, ft = generate_fortune(user.id)
        await update.message.reply_text(
            f"👤 {display_name}\n已签到 ✅\n【{lv}】{ft}\n🔥 连续: {row['streak']}天 ⭐ 积分: {row['points']}"
        )
        conn.close()
        return

    if row is None:
        total, streak, points = 1, 1, 10
        conn.execute("""
            INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)
        """, (chat.id, user.id, user.username, user.first_name, total, streak, points, current_date, now().isoformat()))
    else:
        last_date = None
        if row["last_checkin"]:
            try: last_date = datetime.fromisoformat(row["last_checkin"]).date()
            except: pass
        streak = row["streak"] + 1 if (last_date and (now().date() - last_date).days == 1) else 1
        total = row["total_checkins"] + 1
        add = 10
        if streak >= 7: add += 5
        if streak >= 30: add += 10
        points = row["points"] + add
        conn.execute("""
            UPDATE users SET username=?,first_name=?,total_checkins=?,streak=?,points=?,last_checkin=?
            WHERE chat_id=? AND user_id=?
        """, (user.username, user.first_name, total, streak, points, current_date, chat.id, user.id))
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE chat_id=? AND user_id=?", (chat.id, user.id)).fetchone()
    conn.close()

    lv, ft = generate_fortune(user.id)
    await update.message.reply_text(f"""👤 {display_name}
【{lv}】{ft}
━━━━━━━━━━
📅 第 {row['total_checkins']} 天
🔥 连续 {row['streak']} 天
⭐ 积分 {row['points']}
""")

async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await do_checkin(update, context)

async def chinese_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    if update.message.text.strip() in ["签到", "打卡", "簽到", "打卡签到"]:
        await do_checkin(update, context)

async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u, c = update.effective_user, update.effective_chat
    if not u or not c: return
    row = get_db().execute("SELECT * FROM users WHERE chat_id=? AND user_id=?", (c.id, u.id)).fetchone()
    if not row:
        await update.message.reply_text("还没签到，发送「签到」开始吧 ❤️")
        return
    dn = get_display_name(u)
    await update.message.reply_text(
        f"👤 {dn}\n📅 总签到: {row['total_checkins']}\n🔥 连续: {row['streak']}天\n⭐ 积分: {row['points']}\n🕐 最后: {row['last_checkin']}"
    )

async def fortune_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user: return
    lv, ft = generate_fortune(update.effective_user.id)
    await update.message.reply_text(f"🔮 {get_display_name(update.effective_user)}\n【{lv}】{ft}\n📅 {today()}")

async def rank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat: return
    rows = get_db().execute("SELECT * FROM users WHERE chat_id=? ORDER BY points DESC,total_checkins DESC LIMIT 10", (update.effective_chat.id,)).fetchall()
    if not rows:
        await update.message.reply_text("🏆 暂无记录")
        return
    txt = "🏆 本群排行榜\n\n"
    md = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows):
        n = r["username"] or r["first_name"] or "用户"
        txt += f"{md[i] if i<3 else f'{i+1}.'} {n}\n   🔥 {r['streak']}天  ⭐ {r['points']}分  📅 {r['total_checkins']}次\n\n"
    await update.message.reply_text(txt)

async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    if not DAILY_PUSH_ENABLED: return
    chats = get_db().execute("SELECT chat_id FROM chats").fetchall()
    txt = "🌞 早上好！\n今天记得签到哦～发送「签到」即可\n保持连续不要断！"
    for c in chats:
        try: await context.bot.send_message(c["chat_id"], txt)
        except: pass

async def setup_commands(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "开始使用"),
        BotCommand("checkin", "今日签到"),
        BotCommand("me", "我的资料"),
        BotCommand("rank", "排行榜"),
        BotCommand("fortune", "今日运势"),
        BotCommand("help", "帮助"),
    ])

async def error_handler(u, e):
    print("Error:", e)

# ============= 主程序 =============
def main():
    if not BOT_TOKEN:
        print("❌ 请设置环境变量 BOT_TOKEN")
        return
    init_db()

    app = Application.builder().token(BOT_TOKEN).post_init(setup_commands).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("checkin", checkin_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("rank", rank_command))
    app.add_handler(CommandHandler("fortune", fortune_command))
    app.add_handler(MessageHandler(filters.Regex("^签到$|^打卡$|^簽到$"), do_checkin))

    # ✅ 安全判断：job_queue 存在才设置定时任务
    if DAILY_PUSH_ENABLED:
        if app.job_queue:
            app.job_queue.run_daily(
                daily_push,
                time=time(DAILY_PUSH_HOUR, DAILY_PUSH_MINUTE, tzinfo=TIMEZONE)
            )
            print(f"✅ 定时推送已设置 {DAILY_PUSH_HOUR}:{DAILY_PUSH_MINUTE}")
        else:
            print("⚠️ JobQueue 不可用，跳过定时推送（安装 python-telegram-bot[job-queue] 启用）")

    app.add_error_handler(error_handler)
    print("✅ 启动成功")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
