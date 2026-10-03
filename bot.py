import os
import sqlite3
import hashlib
import random
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from contextlib import contextmanager
from typing import Optional

from telegram import Update, BotCommand, ChatMember
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ChatType

# ========= 配置区 =========
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")
DEFAULT_PUSH_HOUR = 9
DEFAULT_PUSH_MINUTE = 0
DB_FILE = "checkin.db"

# 日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ========= 数据库 =========
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
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

        # 群组表（含推送配置）
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                chat_title TEXT,
                push_enabled INTEGER DEFAULT 1,
                push_hour INTEGER DEFAULT 9,
                push_minute INTEGER DEFAULT 0,
                push_text TEXT DEFAULT '🌞 早上好！\n今天记得签到哦～发送「签到」即可\n保持连续不要断！',
                last_push TEXT,
                created_at TEXT
            )
        """)

        # 兼容旧数据库：尝试添加缺失字段
        try:
            cur.execute("ALTER TABLE chats ADD COLUMN push_hour INTEGER DEFAULT 9")
        except sqlite3.OperationalError:
            pass
        try:
            cur.execute("ALTER TABLE chats ADD COLUMN push_minute INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cur.execute("ALTER TABLE chats ADD COLUMN last_push TEXT")
        except sqlite3.OperationalError:
            pass


def save_chat(chat_id: int, chat_title: str):
    with get_db() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO chats (chat_id, chat_title, created_at)
            VALUES (?, ?, ?)
        """, (chat_id, chat_title, datetime.now(TIMEZONE).isoformat()))


def get_chat_config(chat_id: int) -> Optional[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM chats WHERE chat_id=?", (chat_id,)
        ).fetchone()


def is_push_enabled(chat_id: int) -> bool:
    row = get_chat_config(chat_id)
    return bool(row["push_enabled"]) if row else True


def set_push_enabled(chat_id: int, enabled: bool):
    with get_db() as conn:
        conn.execute(
            "UPDATE chats SET push_enabled=? WHERE chat_id=?",
            (1 if enabled else 0, chat_id)
        )


def get_push_text(chat_id: int) -> str:
    row = get_chat_config(chat_id)
    if not row or not row["push_text"]:
        return "🌞 早上好！\n今天记得签到哦～发送「签到」即可\n保持连续不要断！"
    return row["push_text"]


def set_push_text(chat_id: int, text: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE chats SET push_text=? WHERE chat_id=?",
            (text, chat_id)
        )


def set_push_time(chat_id: int, hour: int, minute: int):
    with get_db() as conn:
        conn.execute(
            "UPDATE chats SET push_hour=?, push_minute=? WHERE chat_id=?",
            (hour, minute, chat_id)
        )


def update_last_push(chat_id: int, date_str: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE chats SET last_push=? WHERE chat_id=?",
            (date_str, chat_id)
        )


# ========= 工具函数 =========
def now() -> datetime:
    return datetime.now(TIMEZONE)


def today() -> str:
    return now().date().isoformat()


def get_display_name(user) -> str:
    if user.username:
        return f"@{user.username}"
    if user.first_name:
        return user.first_name
    return "用户"


def generate_fortune(user_id: int):
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
        ("大吉", "🚀 今天你的行动力会特别强，适合推进项目。"),
        ("小吉", "🎁 可能会收到意想不到的小礼物或好消息。"),
    ])


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """检查是否为管理员（私聊直接放行）"""
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return False

    if chat.type == ChatType.PRIVATE:
        return True

    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        return member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except Exception as e:
        logger.warning(f"检查管理员失败: {e}")
        return False


# ========= 命令处理 =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    cid = update.effective_chat.id
    title = update.effective_chat.title or "私聊"
    save_chat(cid, title)

    cfg = get_chat_config(cid)
    status = "✅ 已开启" if (cfg and cfg["push_enabled"]) else "❌ 已关闭"
    hour = cfg["push_hour"] if cfg else DEFAULT_PUSH_HOUR
    minute = cfg["push_minute"] if cfg else DEFAULT_PUSH_MINUTE

    await update.message.reply_text(f"""🤖 签到机器人

📅 /checkin — 签到+运势
👤 /me — 我的资料
🏆 /rank — 排行榜
🔮 /fortune — 今日运势

📤 /push_on — 开启每日推送
🔕 /push_off — 关闭每日推送
✏️ /push_text 内容 — 自定义推送文案
⏰ /push_time 9:30 — 设置推送时间
📊 /push_status — 查看推送配置
ℹ️ /help — 帮助

当前推送：{status}
推送时间：{hour:02d}:{minute:02d}

直接发送「签到」也可以！
""")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""📖 使用说明

【签到类】
  发送「签到」或 /checkin 完成今日签到
  /me 查看个人资料
  /rank 查看本群排行
  /fortune 单独查运势

【推送管理】（群内仅管理员可用）
  /push_on — 开启每日定时推送
  /push_off — 关闭每日推送
  /push_text 早上好！记得打卡哦～
    → 自定义推送内容，支持换行
  /push_time 9:30
    → 设置推送时间（24小时制）
  /push_status — 查看当前推送配置

🔥 连续7天起每日额外+5积分
🔥 连续30天起每日额外+10积分
""")


async def do_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_chat:
        return

    u = update.effective_user
    c = update.effective_chat
    save_chat(c.id, c.title or "私聊")
    name = get_display_name(u)
    today_str = today()

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE chat_id=? AND user_id=?",
            (c.id, u.id)
        ).fetchone()

        if row and row["last_checkin"] == today_str:
            lv, ft = generate_fortune(u.id)
            await update.message.reply_text(
                f"👤 {name}\n已签到 ✅\n【{lv}】{ft}\n🔥 {row['streak']}天 | ⭐ {row['points']}"
            )
            return

        if not row:
            streak, points = 1, 10
            conn.execute("""
                INSERT INTO users (
                    chat_id, user_id, username, first_name,
                    total_checkins, streak, points, last_checkin, created_at
                ) VALUES (?, ?, ?, ?, 1, 1, 10, ?, ?)
            """, (c.id, u.id, u.username, u.first_name, today_str, now().isoformat()))
        else:
            last_date = None
            if row["last_checkin"]:
                try:
                    last_date = datetime.fromisoformat(row["last_checkin"]).date()
                except Exception:
                    pass

            if last_date and (now().date() - last_date).days == 1:
                streak = row["streak"] + 1
            else:
                streak = 1

            bonus = 0
            if streak >= 30:
                bonus = 10
            elif streak >= 7:
                bonus = 5

            points = row["points"] + 10 + bonus

            conn.execute("""
                UPDATE users SET
                    username=?, first_name=?,
                    total_checkins = total_checkins + 1,
                    streak=?, points=?, last_checkin=?
                WHERE chat_id=? AND user_id=?
            """, (u.username, u.first_name, streak, points, today_str, c.id, u.id))

        row = conn.execute(
            "SELECT * FROM users WHERE chat_id=? AND user_id=?",
            (c.id, u.id)
        ).fetchone()

    lv, ft = generate_fortune(u.id)
    await update.message.reply_text(f"""👤 {name}
【{lv}】{ft}
━━━━━━━━━━
📅 第 {row['total_checkins']} 天
🔥 连续 {row['streak']} 天
⭐ 积分 {row['points']}
""")


async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await do_checkin(update, context)


async def fortune_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    lv, ft = generate_fortune(update.effective_user.id)
    await update.message.reply_text(
        f"🔮 {get_display_name(update.effective_user)}\n【{lv}】{ft}\n📅 {today()}"
    )


async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_chat:
        return

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE chat_id=? AND user_id=?",
            (update.effective_chat.id, update.effective_user.id)
        ).fetchone()

    if not row:
        await update.message.reply_text("还没签到，发送「签到」开始吧 ❤️")
        return

    await update.message.reply_text(f"""👤 {get_display_name(update.effective_user)}
📅 总签到：{row['total_checkins']}
🔥 连续：{row['streak']} 天
⭐ 积分：{row['points']}
🕐 最后：{row['last_checkin']}""")


async def rank_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE chat_id=? ORDER BY points DESC LIMIT 10",
            (update.effective_chat.id,)
        ).fetchall()

    if not rows:
        await update.message.reply_text("🏆 暂无记录")
        return

    text = "🏆 本群排行榜\n\n"
    for i, r in enumerate(rows):
        n = r["username"] or r["first_name"] or "用户"
        icon = ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i+1}."
        text += f"{icon} {n}\n   🔥 {r['streak']}天 ⭐ {r['points']}分 📅 {r['total_checkins']}次\n\n"

    await update.message.reply_text(text)


# ========= 推送管理指令 =========
async def push_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    if not await is_admin(update, context):
        await update.message.reply_text("❌ 只有管理员可以操作推送设置")
        return

    set_push_enabled(update.effective_chat.id, True)
    cfg = get_chat_config(update.effective_chat.id)
    hour = cfg["push_hour"] if cfg else DEFAULT_PUSH_HOUR
    minute = cfg["push_minute"] if cfg else DEFAULT_PUSH_MINUTE

    await update.message.reply_text(
        f"✅ 每日推送已开启\n将在每天 {hour:02d}:{minute:02d} 发送提醒"
    )


async def push_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    if not await is_admin(update, context):
        await update.message.reply_text("❌ 只有管理员可以操作推送设置")
        return

    set_push_enabled(update.effective_chat.id, False)
    await update.message.reply_text("❌ 每日推送已关闭")


async def push_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    if not await is_admin(update, context):
        await update.message.reply_text("❌ 只有管理员可以操作推送设置")
        return

    new_text = " ".join(context.args).strip()
    if not new_text:
        current = get_push_text(update.effective_chat.id)
        await update.message.reply_text(
            "✏️ 用法：/push_text 这里写你的推送内容\n"
            "支持换行，例如：\n"
            "/push_text 早上好！\n今天也要加油哦～\n记得签到！\n\n"
            f"当前文案：\n{current}"
        )
        return

    set_push_text(update.effective_chat.id, new_text)
    await update.message.reply_text(f"✅ 推送文案已更新为：\n━━━━━━━━━━\n{new_text}")


async def push_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return
    if not await is_admin(update, context):
        await update.message.reply_text("❌ 只有管理员可以操作推送设置")
        return

    if not context.args:
        cfg = get_chat_config(update.effective_chat.id)
        hour = cfg["push_hour"] if cfg else DEFAULT_PUSH_HOUR
        minute = cfg["push_minute"] if cfg else DEFAULT_PUSH_MINUTE
        await update.message.reply_text(
            f"⏰ 用法：/push_time 9:30\n"
            f"当前推送时间：{hour:02d}:{minute:02d}\n"
            f"请使用 24 小时制，例如 /push_time 08:00 或 /push_time 21:30"
        )
        return

    time_str = context.args[0].strip()
    try:
        if ":" in time_str:
            h, m = map(int, time_str.split(":"))
        else:
            h = int(time_str)
            m = 0

        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError

        set_push_time(update.effective_chat.id, h, m)
        await update.message.reply_text(f"✅ 推送时间已设置为 {h:02d}:{m:02d}")
    except Exception:
        await update.message.reply_text(
            "❌ 时间格式错误\n请使用例如：/push_time 9:30 或 /push_time 09:00"
        )


async def push_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat:
        return

    cfg = get_chat_config(update.effective_chat.id)
    if not cfg:
        await update.message.reply_text("暂无推送配置，请先使用 /start")
        return

    status = "✅ 已开启" if cfg["push_enabled"] else "❌ 已关闭"
    text = f"""📊 当前推送配置

状态：{status}
时间：{cfg['push_hour']:02d}:{cfg['push_minute']:02d}
上次推送：{cfg['last_push'] or '从未推送'}

文案：
{cfg['push_text'] or '（默认文案）'}
"""
    await update.message.reply_text(text)


# ========= 定时推送任务（每分钟检查） =========
async def check_and_push(context: ContextTypes.DEFAULT_TYPE):
    """每分钟运行一次，检查哪些群需要推送"""
    current = now()
    current_hour = current.hour
    current_minute = current.minute
    today_str = today()

    with get_db() as conn:
        chats = conn.execute(
            "SELECT chat_id, push_enabled, push_hour, push_minute, push_text, last_push FROM chats"
        ).fetchall()

    for c in chats:
        if not c["push_enabled"]:
            continue

        # 时间匹配
        if c["push_hour"] != current_hour or c["push_minute"] != current_minute:
            continue

        # 今天已经推过
        if c["last_push"] == today_str:
            continue

        text = c["push_text"] or "🌞 记得签到哦～"
        try:
            await context.bot.send_message(c["chat_id"], text)
            update_last_push(c["chat_id"], today_str)
            logger.info(f"推送成功 → chat_id={c['chat_id']}")
        except Exception as e:
            logger.error(f"推送失败 {c['chat_id']}: {e}")


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
        BotCommand("push_time", "设置推送时间"),
        BotCommand("push_status", "查看推送配置"),
        BotCommand("help", "帮助"),
    ])


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)


# ========= 主程序 =========
def main():
    if not BOT_TOKEN:
        print("❌ 请设置环境变量 BOT_TOKEN")
        return

    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(setup_commands)
        .build()
    )

    # 签到相关
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("checkin", checkin_command))
    app.add_handler(CommandHandler("me", me_command))
    app.add_handler(CommandHandler("rank", rank_command))
    app.add_handler(CommandHandler("fortune", fortune_command))
    app.add_handler(MessageHandler(filters.Regex(r"^(签到|打卡|簽到)$"), do_checkin))

    # 推送管理
    app.add_handler(CommandHandler("push_on", push_on))
    app.add_handler(CommandHandler("push_off", push_off))
    app.add_handler(CommandHandler("push_text", push_text))
    app.add_handler(CommandHandler("push_time", push_time))
    app.add_handler(CommandHandler("push_status", push_status))

    # 定时任务：每分钟检查一次
    if app.job_queue is not None:
        app.job_queue.run_repeating(
            check_and_push,
            interval=60,          # 每 60 秒
            first=10,             # 启动后 10 秒开始第一次检查
        )
        logger.info("✅ 定时推送任务已启动（每分钟检查）")
    else:
        logger.warning("⚠️ JobQueue 未启用，定时推送已跳过。请安装 python-telegram-bot[job-queue]")

    app.add_error_handler(error_handler)
    logger.info("✅ 机器人启动成功")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
