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

# ========= 配置区 =========
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")
DAILY_PUSH_HOUR = 9
DAILY_PUSH_MINUTE = 0
DB_FILE = "checkin.db"

# ========= 数据库 =========
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    # 用户签到表
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
    # 群组表（含推送开关+自定义内容）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            chat_title TEXT,
            push_enabled INTEGER DEFAULT 1,
            push_text TEXT DEFAULT '🌞 早上好！\n今天记得签到哦～发送「签到」即可\n保持连续不要断！',
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_chat(chat_id, chat_title):
    conn = get_db()
    conn.execute("""
        INSERT OR IGNORE INTO chats (chat_id, chat_title, created_at)
        VALUES (?, ?, ?)
    """, (chat_id, chat_title, datetime.now(TIMEZONE).isoformat()))
    conn.commit()
    conn.close()

def is_push_enabled(chat_id) -> bool:
    """获取该群推送状态"""
    row = get_db().execute(
        "SELECT push_enabled FROM chats WHERE chat_id=?", (chat_id,)
    ).fetchone()
    return bool(row["push_enabled"]) if row else True

def set_push_enabled(chat_id, enabled: bool):
    """设置推送开关"""
    get_db().execute(
        "UPDATE chats SET push_enabled=? WHERE chat_id=?",
        (1 if enabled else 0, chat_id)
    )
    get_db().commit()

def get_push_text(chat_id) -> str:
    """获取该群推送文案"""
    row = get_db().execute(
        "SELECT push_text FROM chats WHERE chat_id=?", (chat_id,)
    ).fetchone()
    if not row or not row["push_text"]:
        return "🌞 早上好！\n今天记得签到哦～发送「签到」即可\n保持连续不要断！"
    return row["push_text"]

def set_push_text(chat_id, text: str):
    """设置推送文案"""
    get_db().execute(
        "UPDATE chats SET push_text=? WHERE chat_id=?",
        (text, chat_id)
    )
    get_db().commit()

# ========= 工具函数 =========
def now(): return datetime.now(TIMEZONE)
def today(): return now().date().isoformat()

def get_display_name(user):
    if user.username: return f"@{user.username}"
    if user.first_name: return user.first_name
    return "用户"

def generate_fortune(user_id):
    seed = int(hashlib.md5(f"{user_id}-{today()}".encode()).hexdigest(), 16)
    random.seed(seed)
    return random.choice([
        ("大吉", "🍀 好运正在靠近，今天适合做重要决定。"),
        ("吉", "🍵 慢下来，你会发现事情没有那么复杂。"),
        ("小吉", "✨ 今天会有一些小惊喜，保持好心情。"),
        ("吉", "💰 财运平稳，努力会得到不错的回应。"),
        ("大吉", "🌟 今天适合行动，犹豫可能会错过机会。"),
        ("平", "🌙 平稳的一天，少一点焦虑，多一点耐心。"),
        ("小吉", "☕ 今天适合处理积压已久的小事情。"),
        ("吉", "🌟 保持微笑，你今天的气场很足！"),
        ("大吉", "❤️ 人际关系顺利，可能会收到开心消息。"),
        ("平", "🌿 按部就班就是前进，别着急。"),
    ])

# ========= 命令处理 =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat: return
    cid, title = update.effective_chat.id, update.effective_chat.title or "私聊"
    save_chat(cid, title)
    status = "✅ 已开启" if is_push_enabled(cid) else "❌ 已关闭"
    await update.message.reply_text(f"""🤖 签到机器人
📅 /checkin — 签到+运势
👤 /me — 我的资料
🏆 /rank — 排行榜
🔮 /fortune — 今日运势
📤 /push_on — 开启每日推送
🔕 /push_off — 关闭每日推送
✏️ /push_text 内容 — 自定义推送文案
ℹ️ /help — 帮助

当前推送：{status}
直接发送「签到」也可以！
""")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""📖 使用说明
签到类：
  发送「签到」或 /checkin 完成今日签到
  /me 查看个人资料
  /rank 查看本群排行
  /fortune 单独查运势

推送管理：
  /push_on — 开启每日定时推送
  /push_off — 关闭每日推送
  /push_text 早上好！记得打卡哦～
    → 自定义推送内容，支持换行

🔥 连续7天起每日+5积分，连续30天起每日+10积分
""")

async def do_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_chat: return
    u, c = update.effective_user, update.effective_chat
    save_chat(c.id, c.title or "私聊")
    name = get_display_name(u)
    today_str = today()
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE chat_id=? AND user_id=?", (c.id, u.id)).fetchone()

    if row and row["last_checkin"] == today_str:
        lv, ft = generate_fortune(u.id)
        await update.message.reply_text(
            f"👤 {name}\n已签到 ✅\n【{lv}】{ft}\n🔥 {row['streak']}天 | ⭐ {row['points']}"
        )
        conn.close()
        return

    if not row:
        total, streak, points = 1, 1, 10
        conn.execute("""INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?)""",
            (c.id, u.id, u.username, u.first_name, 1, 1, 10, today_str, now().isoformat()))
    else:
        last_date = datetime.fromisoformat(row["last_checkin"]).date() if row["last_checkin"] else None
        streak = row["streak"] + 1 if (last_date and (now().date() - last_date).days == 1) else 1
        points = row["points"] + 10 + (5 if streak >= 7 else 0) + (5 if streak >= 30 else 0)
        conn.execute("""UPDATE users SET
            username=?,first_name=?,total_checkins=total_checkins+1,
            streak=?,points=?,last_checkin=?
            WHERE chat_id=? AND user_id=?""",
            (u.username, u.first_name, streak, points, today_str, c.id, u.id))
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE chat_id=? AND user_id=?", (c.id, u.id)).fetchone()
    conn.close()

    lv, ft = generate_fortune(u.id)
    await update.message.reply_text(f"""👤 {name}
【{lv}】{ft}
━━━━━━━━━━
📅 第 {row['total_checkins']} 天
🔥 连续 {row['streak']} 天
⭐ 积分 {row['points']}
""")

async def checkin_command(update: Update, ctx): await do_checkin(update, ctx)

async def fortune_command(update: Update, ctx):
    lv, ft = generate_fortune(update.effective_user.id)
    await update.message.reply_text(f"🔮 {get_display_name(update.effective_user)}\n【{lv}】{ft}\n📅 {today()}")

async def me_command(update: Update, ctx):
    row = get_db().execute("SELECT * FROM users WHERE chat_id=? AND user_id=?",
        (update.effective_chat.id, update.effective_user.id)).fetchone()
    if not row:
        await update.message.reply_text("还没签到，发送「签到」开始吧 ❤️")
        return
    await update.message.reply_text(f"""👤 {get_display_name(update.effective_user)}
📅 总签到：{row['total_checkins']}
🔥 连续：{row['streak']} 天
⭐ 积分：{row['points']}
🕐 最后：{row['last_checkin']}""")

async def rank_command(update: Update, ctx):
    rows = get_db().execute("SELECT * FROM users WHERE chat_id=? ORDER BY points DESC LIMIT 10",
        (update.effective_chat.id,)).fetchall()
    if not rows:
        await update.message.reply_text("🏆 暂无记录")
        return
    text = "🏆 本群排行榜\n\n"
    for i, r in enumerate(rows):
        n = r["username"] or r["first_name"] or "用户"
        icon = ["🥇","🥈","🥉"][i] if i<3 else f"{i+1}."
        text += f"{icon} {n}\n   🔥 {r['streak']}天 ⭐ {r['points']}分 📅 {r['total_checkins']}次\n\n"
    await update.message.reply_text(text)

# ========= 新增：推送管理指令 =========
async def push_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat: return
    set_push_enabled(update.effective_chat.id, True)
    await update.message.reply_text("✅ 每日推送已开启\n将在每天 {}:{:02d} 发送提醒".format(DAILY_PUSH_HOUR, DAILY_PUSH_MINUTE))

async def push_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat: return
    set_push_enabled(update.effective_chat.id, False)
    await update.message.reply_text("❌ 每日推送已关闭")

async def push_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat: return
    new_text = " ".join(context.args).strip()
    if not new_text:
        await update.message.reply_text(
            "✏️ 用法：/push_text 这里写你的推送内容\n"
            "支持换行，例如：\n"
            "/push_text 早上好！\n今天也要加油哦～\n记得签到！\n\n"
            f"当前文案：\n{get_push_text(update.effective_chat.id)}"
        )
        return
    set_push_text(update.effective_chat.id, new_text)
    await update.message.reply_text(f"✅ 推送文案已更新为：\n━━━━━━━━━━\n{new_text}")

# ========= 定时推送任务 =========
async def daily_push(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    chats = conn.execute("SELECT chat_id, push_enabled, push_text FROM chats").fetchall()
    conn.close()
    for c in chats:
        if c["push_enabled"]:
            text = c["push_text"] or "🌞 记得签到哦～"
            try:
                await context.bot.send_message(c["chat_id"], text)
            except Exception as e:
                print(f"推送失败 {c['chat_id']}: {e}")

async def setup_commands(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "开始使用"),
        BotCommand("checkin", "今日签到"),
        BotCommand("me", "我的资料"),
        BotCommand("rank", "排行榜"),
        BotCommand("fortune", "今日运势"),
        BotCommand("push_on", "开启每日推送"),
        BotCommand("push_off", "关闭每日推送"),
        BotCommand("push_text", "自定义推送文案"),
        BotCommand("help", "帮助"),
    ])

async def error_handler(_, ctx):
    print("Error:", ctx.error)

# ========= 主程序 =========
def main():
    if not BOT_TOKEN:
        print("❌ 请设置环境变量 BOT_TOKEN")
        return
    init_db()

    app = Application.builder().token(BOT_TOKEN).post_init(setup_commands).build()

    # 签到相关指令
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("checkin", checkin_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("rank", rank_command))
    app.add_handler(CommandHandler("fortune", fortune_command))
    app.add_handler(MessageHandler(filters.Regex("^签到$|^打卡$|^簽到$"), do_checkin))

    # 推送管理指令
    app.add_handler(CommandHandler("push_on", push_on))
    app.add_handler(CommandHandler("push_off", push_off))
    app.add_handler(CommandHandler("push_text", push_text))

    # ✅ 定时任务 —— 安全判断
    if app.job_queue is not None:
        app.job_queue.run_daily(
            daily_push,
            time=time(DAILY_PUSH_HOUR, DAILY_PUSH_MINUTE, tzinfo=TIMEZONE)
        )
        print(f"✅ 定时任务已启动：每日 {DAILY_PUSH_HOUR}:{DAILY_PUSH_MINUTE:02d}")
    else:
        print("⚠️ JobQueue 未启用，定时推送已跳过")

    app.add_error_handler(error_handler)
    print("✅ 启动成功")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
