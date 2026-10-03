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


# =========================================================
# 基本设置
# =========================================================

BOT_TOKEN = "8700209900:AAETFk9XhHLJdzKs9N0eNcYbeDzxgGmrKHc"

TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")

# 每天自动提醒
DAILY_PUSH_ENABLED = True

# 每天几点推送
DAILY_PUSH_HOUR = 9
DAILY_PUSH_MINUTE = 0

DB_FILE = "checkin.db"


# =========================================================
# 数据库
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    # 用户签到数据
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

    # 已经使用过机器人的群
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
    """, (
        chat_id,
        chat_title,
        chat_id,
        datetime.now(TIMEZONE).isoformat()
    ))

    conn.commit()
    conn.close()


# =========================================================
# 工具
# =========================================================

def now():
    return datetime.now(TIMEZONE)


def today():
    return now().date().isoformat()


def get_display_name(user):
    if user.username:
        return f"@{user.username}"

    if user.first_name:
        return user.first_name

    return "用户"


def generate_fortune(user_id):
    """
    同一个用户当天得到固定运势，
    不会每次签到都变化。
    """

    date_string = today()

    seed_string = f"{user_id}-{date_string}"

    seed = int(
        hashlib.md5(
            seed_string.encode()
        ).hexdigest(),
        16
    )

    random.seed(seed)

    fortunes = [
        (
            "大吉",
            "🍀 好运正在靠近，今天适合做重要决定。",
        ),
        (
            "吉",
            "🍵 一杯清茶，一份好运。慢下来，你会发现事情没有那么复杂。",
        ),
        (
            "小吉",
            "✨ 今天会有一些小惊喜，保持好心情。",
        ),
        (
            "吉",
            "💰 财运平稳，努力会得到不错的回应。",
        ),
        (
            "大吉",
            "🌟 今天适合行动，犹豫可能会错过机会。",
        ),
        (
            "平",
            "🌙 平稳的一天，少一点焦虑，多一点耐心。",
        ),
        (
            "小吉",
            "☕ 今天适合处理积压已久的小事情。",
        ),
        (
            "吉",
            "🌟 保持微笑，你今天的气场很足！",
        ),
        (
            "大吉",
            "❤️ 人际关系顺利，可能会收到令人开心的消息。",
        ),
        (
            "平",
            "🌿 保持节奏，不必急于证明自己，按部就班就是前进，别着急。",
        ),
    ]

    return random.choice(fortunes)


# =========================================================
# /start
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.effective_chat:
        return

    chat = update.effective_chat

    save_chat(
        chat.id,
        chat.title or "私聊"
    )

    text = """
🤖 签到机器人 v1.0

欢迎使用！

📅 /checkin
签到 + 获取今日运势

👤 /me
查看个人签到资料

🏆 /rank
查看本群签到排行榜

🔮 /fortune
查看今日运势

ℹ️ /help
查看帮助

也可以直接发送：

签到
"""

    await update.message.reply_text(text)


# =========================================================
# /help
# =========================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
📖 签到机器人使用说明

📅 签到
发送：

签到

或者：

/checkin

即可完成今日签到。

👤 我的资料
/me

🏆 签到排行榜
/rank

🔮 今日运势
/fortune

🔥 连续签到越久，获得积分越多。

每天只能签到一次。
"""

    await update.message.reply_text(text)


# =========================================================
# 签到
# =========================================================

async def do_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.effective_user:
        return

    if not update.effective_chat:
        return

    user = update.effective_user
    chat = update.effective_chat

    save_chat(
        chat.id,
        chat.title or "私聊"
    )

    display_name = get_display_name(user)

    current_date = today()

    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM users
        WHERE chat_id = ?
        AND user_id = ?
    """, (
        chat.id,
        user.id
    )).fetchone()

    # =====================================================
    # 已经签到
    # =====================================================

    if row and row["last_checkin"] == current_date:

        fortune_level, fortune_text = generate_fortune(
            user.id
        )

        await update.message.reply_text(
            f"👤 {display_name}\n\n"
            f"你今天已经签到过啦 ❤️\n\n"
            f"🔮 今日运势：\n"
            f"【{fortune_level}】 {fortune_text}\n\n"
            f"🔥 连续签到：{row['streak']} 天\n"
            f"⭐ 当前积分：{row['points']}"
        )

        conn.close()
        return

    # =====================================================
    # 第一次签到
    # =====================================================

    if row is None:

        total_checkins = 1
        streak = 1
        points = 10

        conn.execute("""
            INSERT INTO users (
                chat_id,
                user_id,
                username,
                first_name,
                total_checkins,
                streak,
                points,
                last_checkin,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            chat.id,
            user.id,
            user.username,
            user.first_name,
            total_checkins,
            streak,
            points,
            current_date,
            now().isoformat()
        ))

    # =====================================================
    # 老用户签到
    # =====================================================

    else:

        old_streak = row["streak"]

        last_date = None

        if row["last_checkin"]:
            try:
                last_date = datetime.fromisoformat(
                    row["last_checkin"]
                ).date()
            except:
                pass

        current_day = now().date()

        # 昨天签到 → 连续
        if last_date and (
            current_day - last_date
        ).days == 1:

            streak = old_streak + 1

        else:

            streak = 1

        total_checkins = row["total_checkins"] + 1

        # 基础10积分
        points_add = 10

        # 连续签到奖励
        if streak >= 7:
            points_add += 5

        if streak >= 30:
            points_add += 10

        points = row["points"] + points_add

        conn.execute("""
            UPDATE users
            SET
                username = ?,
                first_name = ?,
                total_checkins = ?,
                streak = ?,
                points = ?,
                last_checkin = ?
            WHERE chat_id = ?
            AND user_id = ?
        """, (
            user.username,
            user.first_name,
            total_checkins,
            streak,
            points,
            current_date,
            chat.id,
            user.id
        ))

    conn.commit()

    # 获取最新资料
    row = conn.execute("""
        SELECT *
        FROM users
        WHERE chat_id = ?
        AND user_id = ?
    """, (
        chat.id,
        user.id
    )).fetchone()

    conn.close()

    # =====================================================
    # 今日运势
    # =====================================================

    fortune_level, fortune_text = generate_fortune(
        user.id
    )

    # =====================================================
    # 回复
    # =====================================================

    message = (
        f"👤 {display_name} 的今日运势：\n\n"
        f"【{fortune_level}】 {fortune_text}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"📅 今日签到：第 {row['total_checkins']} 天\n"
        f"🔥 连续签到：{row['streak']} 天\n"
        f"⭐ 当前积分：{row['points']}\n"
        f"━━━━━━━━━━━━━━"
    )

    await update.message.reply_text(message)


# =========================================================
# /checkin
# =========================================================

async def checkin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await do_checkin(update, context)


# =========================================================
# 中文“签到”
# =========================================================

async def chinese_checkin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    text = update.message.text.strip()

    if text in ["签到", "打卡", "簽到", "打卡签到"]:

        await do_checkin(update, context)


# =========================================================
# /me
# =========================================================

async def me_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM users
        WHERE chat_id = ?
        AND user_id = ?
    """, (
        chat.id,
        user.id
    )).fetchone()

    conn.close()

    if not row:

        await update.message.reply_text(
            "你还没有签到过。\n\n"
            "发送「签到」开始第一次签到吧 ❤️"
        )

        return

    display_name = get_display_name(user)

    text = (
        f"👤 {display_name}\n\n"
        f"📅 总签到：{row['total_checkins']} 次\n"
        f"🔥 连续签到：{row['streak']} 天\n"
        f"⭐ 当前积分：{row['points']}\n"
        f"🕐 最后签到：{row['last_checkin']}"
    )

    await update.message.reply_text(text)


# =========================================================
# /fortune
# =========================================================

async def fortune_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user:
        return

    level, fortune_text = generate_fortune(
        user.id
    )

    name = get_display_name(user)

    text = (
        f"🔮 {name} 的今日运势\n\n"
        f"【{level}】\n\n"
        f"{fortune_text}\n\n"
        f"📅 {today()}"
    )

    await update.message.reply_text(text)


# =========================================================
# /rank
# =========================================================

async def rank_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    chat = update.effective_chat

    if not chat:
        return

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM users
        WHERE chat_id = ?
        ORDER BY points DESC, total_checkins DESC
        LIMIT 10
    """, (
        chat.id,
    )).fetchall()

    conn.close()

    if not rows:

        await update.message.reply_text(
            "🏆 目前还没有签到记录。"
        )

        return

    text = "🏆 本群签到排行榜\n\n"

    medals = [
        "🥇",
        "🥈",
        "🥉"
    ]

    for index, row in enumerate(rows):

        name = row["username"]

        if not name:
            name = row["first_name"] or "用户"

        if index < 3:
            icon = medals[index]
        else:
            icon = f"{index + 1}."

        text += (
            f"{icon} {name}\n"
            f"   🔥 {row['streak']}天"
            f"  ⭐ {row['points']}积分"
            f"  📅 {row['total_checkins']}次\n\n"
        )

    await update.message.reply_text(text)


# =========================================================
# 每日自动推送
# =========================================================

async def daily_push(context: ContextTypes.DEFAULT_TYPE):

    if not DAILY_PUSH_ENABLED:
        return

    conn = get_db()

    chats = conn.execute("""
        SELECT chat_id, chat_title
        FROM chats
    """).fetchall()

    conn.close()

    text = (
        "🌞 早上好！\n\n"
        "新的一天开始啦 ❤️\n\n"
        "📅 今天记得签到\n"
        "🔮 看看你的今日运势\n"
        "🔥 连续签到不要断哦！\n\n"
        "发送「签到」即可完成签到。"
    )

    for chat in chats:

        try:

            await context.bot.send_message(
                chat_id=chat["chat_id"],
                text=text
            )

        except Exception as e:

            print(
                f"无法发送到 {chat['chat_id']}: {e}"
            )


# =========================================================
# 设置 Bot Commands
# =========================================================

async def setup_commands(app: Application):

    commands = [

        BotCommand(
            "start",
            "开始使用"
        ),

        BotCommand(
            "checkin",
            "今日签到"
        ),

        BotCommand(
            "me",
            "我的签到资料"
        ),

        BotCommand(
            "rank",
            "签到排行榜"
        ),

        BotCommand(
            "fortune",
            "今日运势"
        ),

        BotCommand(
            "help",
            "帮助"
        ),

    ]

    await app.bot.set_my_commands(commands)


# =========================================================
# 错误处理
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    print(
        "Bot Error:",
        context.error
    )


# =========================================================
# 主程序
# =========================================================

def main():

    if BOT_TOKEN == "把你的BOT_TOKEN放这里":

        print(
            "\n❌ 请先在 bot.py 里面填写 BOT_TOKEN\n"
        )

        return

    # 初始化数据库
    init_db()

    # 创建 Bot
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(setup_commands)
        .build()
    )

    # =====================================================
    # Commands
    # =====================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        CommandHandler(
            "checkin",
            checkin_command
        )
    )

    app.add_handler(
        CommandHandler(
            "me",
            me_command
        )
    )

    app.add_handler(
        CommandHandler(
            "rank",
            rank_command
        )
    )

    app.add_handler(
        CommandHandler(
            "fortune",
            fortune_command
        )
    )

    # =====================================================
    # 中文签到
    # =====================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            chinese_checkin
        )
    )

    # =====================================================
    # 每天自动推送
    # =====================================================

    if DAILY_PUSH_ENABLED:

        app.job_queue.run_daily(
            daily_push,
            time=time(
                hour=DAILY_PUSH_HOUR,
                minute=DAILY_PUSH_MINUTE,
                tzinfo=TIMEZONE
            ),
            name="daily_checkin_push"
        )

    # =====================================================
    # 错误处理
    # =====================================================

    app.add_error_handler(
        error_handler
    )

    print(
        "================================"
    )

    print(
        "🤖 Telegram 签到机器人启动成功"
    )

    print(
        "🌏 时区：Asia/Kuala_Lumpur"
    )

    print(
        "📅 每日签到：开启"
    )

    print(
        "================================"
    )

    # 启动
    app.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()