import discord
from discord.ext import commands, tasks
import aiosqlite
import json
import random
import asyncio
from datetime import datetime, timezone, timedelta
from collections import deque
import os

# ==================================================
# BOT CONFIGURATION
# ==================================================
MAIN_OWNER_ID = 1486785358162300969
COMMAND_PREFIX = "."
TOKEN = os.environ["TOKEN"]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
bot.remove_command('help')

# ==================================================
# GAMBLING COOLDOWN (3 seconds after game ends)
# ==================================================
gambling_cooldowns = {}

# ==================================================
# RECENT MESSAGE TRACKING (for .rewardlast)
# ==================================================
recent_message_authors = {}  # guild_id → deque(user_ids)

# ==================================================
# NUMBER FORMATTING (unlimited integer parsing)
# ==================================================
def parse_amount(amount_str: str):
    """Convert a string like '5k', '1.2m', '100sx', 'all', or plain int to a Python int."""
    if amount_str.lower() == "all":
        return "all"
    amount_str = amount_str.lower().strip()
    mult = {
        'k': 1_000,
        'm': 1_000_000,
        'b': 1_000_000_000,
        't': 1_000_000_000_000,
        'q': 1_000_000_000_000_000,
        'Q': 1_000_000_000_000_000_000,
        'sx': 1_000_000_000_000_000_000_000,
        'sp': 1_000_000_000_000_000_000_000_000,
        'oc': 1_000_000_000_000_000_000_000_000_000,
        'no': 1_000_000_000_000_000_000_000_000_000_000,
        'dc': 1_000_000_000_000_000_000_000_000_000_000_000,
    }
    for suffix in sorted(mult, key=len, reverse=True):
        if amount_str.endswith(suffix):
            num_part = amount_str[:-len(suffix)]
            if '.' in num_part:
                int_part, dec_part = num_part.split('.', 1)
                dec_factor = 10 ** len(dec_part)
                value = (int(int_part) * mult[suffix] * dec_factor +
                         int(dec_part) * mult[suffix]) // dec_factor
            else:
                value = int(num_part) * mult[suffix]
            return value
    try:
        return int(amount_str)
    except ValueError:
        raise ValueError("Invalid amount")

def format_number(num: int) -> str:
    if num >= 1_000_000_000_000_000_000_000_000_000_000_000:
        return f"{num/1_000_000_000_000_000_000_000_000_000_000_000:.1f}dc".replace('.0dc','dc')
    if num >= 1_000_000_000_000_000_000_000_000_000_000:
        return f"{num/1_000_000_000_000_000_000_000_000_000_000:.1f}no".replace('.0no','no')
    if num >= 1_000_000_000_000_000_000_000_000_000:
        return f"{num/1_000_000_000_000_000_000_000_000_000:.1f}oc".replace('.0oc','oc')
    if num >= 1_000_000_000_000_000_000_000_000:
        return f"{num/1_000_000_000_000_000_000_000_000:.1f}sp".replace('.0sp','sp')
    if num >= 1_000_000_000_000_000_000_000:
        return f"{num/1_000_000_000_000_000_000_000:.1f}sx".replace('.0sx','sx')
    if num >= 1_000_000_000_000_000_000:
        return f"{num/1_000_000_000_000_000_000:.1f}Q".replace('.0Q','Q')
    if num >= 1_000_000_000_000_000:
        return f"{num/1_000_000_000_000_000:.1f}q".replace('.0q','q')
    if num >= 1_000_000_000_000:
        return f"{num/1_000_000_000_000:.1f}t".replace('.0t','t')
    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.1f}b".replace('.0b','b')
    if num >= 1_000_000:
        return f"{num/1_000_000:.1f}m".replace('.0m','m')
    if num >= 1_000:
        return f"{num/1_000:.1f}k".replace('.0k','k')
    return str(num)

# ==================================================
# DATABASE SETUP (money / bank stored as TEXT)
# ==================================================
async def init_db():
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS owners (
            user_id INTEGER PRIMARY KEY,
            is_main INTEGER DEFAULT 0
        )''')
        await db.execute("INSERT OR IGNORE INTO owners (user_id, is_main) VALUES (?, 1)", (MAIN_OWNER_ID,))

        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            money TEXT DEFAULT '0',
            bank TEXT DEFAULT '0',
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            total_xp INTEGER DEFAULT 0,
            protected INTEGER DEFAULT 0,
            blacklisted INTEGER DEFAULT 0,
            tax_exempt INTEGER DEFAULT 0,
            last_daily TIMESTAMP,
            last_work TIMESTAMP,
            last_rob TIMESTAMP,
            last_sleep TIMESTAMP,
            last_crime TIMESTAMP,
            last_interest TIMESTAMP,
            daily_messages INTEGER DEFAULT 0,
            shop_name TEXT,
            shop_items TEXT DEFAULT '{}',
            shop_open INTEGER DEFAULT 0,
            spouse_id INTEGER,
            parent_id INTEGER,
            affection INTEGER DEFAULT 0,
            gang TEXT,
            loan_amount TEXT DEFAULT '0',
            loan_taken_at TIMESTAMP,
            business_daily TIMESTAMP
        )''')

        await db.execute('''CREATE TABLE IF NOT EXISTS children (
            parent_id INTEGER,
            child_id INTEGER,
            PRIMARY KEY (parent_id, child_id)
        )''')

        await db.execute('''CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id INTEGER,
            to_id INTEGER,
            request_type TEXT,
            timestamp TEXT
        )''')

        await db.execute('''CREATE TABLE IF NOT EXISTS businesses (
            user_id INTEGER PRIMARY KEY,
            business_type TEXT,
            level INTEGER DEFAULT 1,
            last_collected TIMESTAMP,
            daily_bonus_collected TIMESTAMP,
            reputation INTEGER DEFAULT 0
        )''')

        await db.execute('''CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            economy_enabled INTEGER DEFAULT 1,
            rob_enabled INTEGER DEFAULT 1,
            gambling_enabled INTEGER DEFAULT 1,
            daily_amount INTEGER DEFAULT 1500,
            daily_messages_needed INTEGER DEFAULT 10,
            sleep_amount_min INTEGER DEFAULT 2000,
            sleep_amount_max INTEGER DEFAULT 2500,
            work_amount_min INTEGER DEFAULT 150,
            work_amount_max INTEGER DEFAULT 300,
            crime_amount_min INTEGER DEFAULT 200,
            crime_amount_max INTEGER DEFAULT 800,
            interest_rate INTEGER DEFAULT 5,
            max_withdraw INTEGER DEFAULT 999999999,
            loan_interest INTEGER DEFAULT 10,
            currency_emoji TEXT DEFAULT '💰'
        )''')

        await db.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            user_id INTEGER,
            action TEXT,
            details TEXT
        )''')

        await db.commit()
        for guild in bot.guilds:
            await db.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild.id,))
        await db.commit()
    print("✅ Database ready (unlimited money).")

# ==================================================
# BACKGROUND TASKS (Python arithmetic)
# ==================================================
@tasks.loop(hours=1)
async def loan_interest():
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, loan_amount FROM users WHERE CAST(loan_amount AS INTEGER) > 0") as cur:
            rows = await cur.fetchall()
        for uid, loan_str in rows:
            loan = int(loan_str)
            new_loan = int(loan * 1.10)
            await db.execute("UPDATE users SET loan_amount = ? WHERE user_id = ?", (str(new_loan), uid))
        await db.commit()

@loan_interest.before_loop
async def before_loan():
    await bot.wait_until_ready()

@tasks.loop(hours=24)
async def bank_interest():
    async with aiosqlite.connect("hakari.db") as db:
        rate = await get_setting(0, "interest_rate") if bot.guilds else 5
        async with db.execute("SELECT user_id, bank, last_interest FROM users WHERE CAST(bank AS INTEGER) > 0") as cur:
            rows = await cur.fetchall()
        for uid, bank_str, last in rows:
            if last:
                last_dt = datetime.fromisoformat(last)
                if datetime.now(timezone.utc) - last_dt < timedelta(hours=20):
                    continue
            bank = int(bank_str)
            earning = min(bank, 50000)
            interest = int(earning * rate / 100)
            if interest:
                new_bank = bank + interest
                await db.execute("UPDATE users SET bank = ?, last_interest = ? WHERE user_id = ?",
                                 (str(new_bank), datetime.now(timezone.utc).isoformat(), uid))
        await db.commit()
    print("✅ Bank interest added")

@bank_interest.before_loop
async def before_bank():
    await bot.wait_until_ready()

# ==================================================
# DATABASE HELPERS (all arithmetic in Python)
# ==================================================
async def get_user(user_id: int):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                cols = [desc[0] for desc in cur.description]
                data = dict(zip(cols, row))
                data['money'] = int(data.get('money', '0'))
                data['bank'] = int(data.get('bank', '0'))
                data['loan_amount'] = int(data.get('loan_amount', '0'))
                return data
        await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur2:
            row2 = await cur2.fetchone()
            cols2 = [desc[0] for desc in cur2.description]
            data2 = dict(zip(cols2, row2))
            data2['money'] = int(data2.get('money', '0'))
            data2['bank'] = int(data2.get('bank', '0'))
            data2['loan_amount'] = int(data2.get('loan_amount', '0'))
            return data2

async def update_money(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT money FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        cur_money = int(row[0]) if row else 0
        new = cur_money + amount
        await db.execute("UPDATE users SET money = ? WHERE user_id = ?", (str(new), user_id))
        await db.commit()

async def update_bank(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT bank FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        cur_bank = int(row[0]) if row else 0
        new = cur_bank + amount
        await db.execute("UPDATE users SET bank = ? WHERE user_id = ?", (str(new), user_id))
        await db.commit()

async def update_affection(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET affection = affection + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def set_affection(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET affection = ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def log_action(user_id: int, action: str, details: str = ""):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO logs (timestamp, user_id, action, details) VALUES (?, ?, ?, ?)",
                         (datetime.now(timezone.utc).isoformat(), user_id, action, details))
        await db.commit()

async def get_setting(guild_id: int, setting: str):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute(f"SELECT {setting} FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return row[0]
    defaults = {
        "economy_enabled": 1, "rob_enabled": 1, "gambling_enabled": 1,
        "daily_amount": 1500, "daily_messages_needed": 10,
        "sleep_amount_min": 2000, "sleep_amount_max": 2500,
        "work_amount_min": 150, "work_amount_max": 300,
        "crime_amount_min": 200, "crime_amount_max": 800,
        "interest_rate": 5, "max_withdraw": 999999999,
        "loan_interest": 10, "currency_emoji": "💰"
    }
    return defaults.get(setting, 1)

async def is_owner(user_id: int) -> bool:
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM owners WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone() is not None

async def is_main_owner(user_id: int) -> bool:
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT is_main FROM owners WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row and row[0] == 1

async def is_blacklisted(user_id: int) -> bool:
    u = await get_user(user_id)
    return u.get("blacklisted", 0) == 1

async def is_protected(user_id: int) -> bool:
    u = await get_user(user_id)
    return u.get("protected", 0) == 1

async def is_tax_exempt(user_id: int) -> bool:
    u = await get_user(user_id)
    return u.get("tax_exempt", 0) == 1

async def add_xp(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.execute("UPDATE users SET xp = xp + ?, total_xp = total_xp + ? WHERE user_id = ?", (amount, amount, user_id))
        await db.commit()
        async with db.execute("SELECT total_xp, level FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                total, lvl = row
                new_lvl = int((total / 100) ** 0.5)
                if new_lvl > lvl:
                    await db.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_lvl, user_id))
                    await db.commit()
                    return new_lvl
    return None

async def get_bet_amount(ctx, amount_str, check_balance=True):
    data = await get_user(ctx.author.id)
    if amount_str.lower() == "all":
        amount = data["money"]
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return None, "❌ Invalid amount. Use numbers like 500, 1k, 2.5m, etc. or 'all'."
    if amount <= 0:
        return None, "❌ Amount must be positive."
    if check_balance and data["money"] < amount:
        return None, f"❌ You only have {format_number(data['money'])} coins."
    return amount, None

def economy_check():
    async def pred(ctx):
        if await get_setting(ctx.guild.id, "economy_enabled") == 0:
            await ctx.send("❌ Economy is disabled.")
            return False
        if await is_blacklisted(ctx.author.id):
            await ctx.send("❌ You are blacklisted.")
            return False
        return True
    return commands.check(pred)

def owner_only():
    async def pred(ctx):
        if await is_owner(ctx.author.id):
            return True
        await ctx.send("❌ You don't have permission.")
        return False
    return commands.check(pred)

def main_owner_only():
    async def pred(ctx):
        if await is_main_owner(ctx.author.id):
            return True
        await ctx.send("❌ Only the main owner can use this.")
        return False
    return commands.check(pred)

# ==================================================
# GAMBLING COOLDOWN CHECK
# ==================================================
def gambling_cooldown_check():
    async def pred(ctx):
        if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
            await ctx.send("❌ Gambling disabled.")
            return False
        last = gambling_cooldowns.get(ctx.author.id)
        if last and datetime.now(timezone.utc) < last:
            await ctx.send("⏰ Please wait a few seconds before gambling again.")
            return False
        return True
    return commands.check(pred)

async def set_gambling_cooldown(user_id, seconds=3):
    gambling_cooldowns[user_id] = datetime.now(timezone.utc) + timedelta(seconds=seconds)

# ==================================================
# INTERACTIVE VIEWS
# ==================================================
class PaymentConfirmView(discord.ui.View):
    def __init__(self, sender, recipient, amount, emoji):
        super().__init__(timeout=60)
        self.sender = sender
        self.recipient = recipient
        self.amount = amount
        self.emoji = emoji
        self.completed = False

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        if interaction.user.id != self.sender.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        sender_data = await get_user(self.sender.id)
        if sender_data["money"] < self.amount:
            await interaction.response.edit_message(content="❌ You no longer have enough coins.", view=None)
            self.completed = True
            return
        await update_money(self.sender.id, -self.amount)
        await update_money(self.recipient.id, self.amount)
        await interaction.response.edit_message(content=f"✅ You paid {format_number(self.amount)}{self.emoji} to {self.recipient.mention}!", view=None)
        await log_action(self.sender.id, "Payment", f"Paid {self.amount} to {self.recipient.id}")
        self.completed = True
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction, button):
        if interaction.user.id != self.sender.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        await interaction.response.edit_message(content="❌ Payment cancelled.", view=None)
        self.completed = True
        self.stop()

class RequestView(discord.ui.View):
    def __init__(self, from_user, to_user, req_type, req_id):
        super().__init__(timeout=120)
        self.from_user = from_user
        self.to_user = to_user
        self.req_type = req_type
        self.req_id = req_id
        self.completed = False

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept_btn(self, interaction, button):
        if interaction.user.id != self.to_user.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT from_id, request_type FROM requests WHERE id = ?", (self.req_id,)) as cur:
                req = await cur.fetchone()
            if not req:
                await interaction.response.edit_message(content="❌ Request expired.", view=None)
                self.completed = True
                return
            from_id, rtype = req
            if rtype == "marriage":
                await db.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (self.to_user.id, from_id))
                await db.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (from_id, self.to_user.id))
                await db.execute("DELETE FROM requests WHERE id = ?", (self.req_id,))
                await db.commit()
                await interaction.response.edit_message(content=f"💕 {self.from_user.mention} and {self.to_user.mention} are now married! 🎉", view=None)
            elif rtype == "adopt":
                await db.execute("INSERT INTO children (parent_id, child_id) VALUES (?, ?)", (from_id, self.to_user.id))
                await db.execute("UPDATE users SET parent_id = ? WHERE user_id = ?", (from_id, self.to_user.id))
                await db.execute("DELETE FROM requests WHERE id = ?", (self.req_id,))
                await db.commit()
                await interaction.response.edit_message(content=f"👶 {self.from_user.mention} adopted {self.to_user.mention}!", view=None)
        self.completed = True
        self.stop()

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline_btn(self, interaction, button):
        if interaction.user.id != self.to_user.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("DELETE FROM requests WHERE id = ?", (self.req_id,))
            await db.commit()
        await interaction.response.edit_message(content=f"❌ {self.to_user.mention} declined the {self.req_type} request.", view=None)
        self.completed = True
        self.stop()

# ==================================================
# PAGINATED HELP VIEWS
# ==================================================
class HelpView(discord.ui.View):
    def __init__(self, ctx, pages):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.pages = pages
        self.page = 0

    async def update(self, inter):
        try:
            await inter.edit_original_response(embed=self.pages[self.page], view=self)
        except discord.NotFound:
            self.stop()

    @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
    async def prev(self, inter, btn):
        if inter.user != self.ctx.author:
            return await inter.response.send_message("Not your menu!", ephemeral=True)
        await inter.response.defer()
        self.page = (self.page - 1) % len(self.pages)
        await self.update(inter)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def nxt(self, inter, btn):
        if inter.user != self.ctx.author:
            return await inter.response.send_message("Not your menu!", ephemeral=True)
        await inter.response.defer()
        self.page = (self.page + 1) % len(self.pages)
        await self.update(inter)

    @discord.ui.button(label="❌", style=discord.ButtonStyle.danger)
    async def close(self, inter, btn):
        if inter.user != self.ctx.author:
            return await inter.response.send_message("Not your menu!", ephemeral=True)
        await inter.message.delete()
        self.stop()

class OwnerHelpView(discord.ui.View):
    def __init__(self, ctx, pages):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.pages = pages
        self.page = 0

    async def update(self, inter):
        try:
            await inter.edit_original_response(embed=self.pages[self.page], view=self)
        except discord.NotFound:
            self.stop()

    @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
    async def prev(self, inter, btn):
        if inter.user != self.ctx.author:
            return await inter.response.send_message("Not your menu!", ephemeral=True)
        await inter.response.defer()
        self.page = (self.page - 1) % len(self.pages)
        await self.update(inter)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def nxt(self, inter, btn):
        if inter.user != self.ctx.author:
            return await inter.response.send_message("Not your menu!", ephemeral=True)
        await inter.response.defer()
        self.page = (self.page + 1) % len(self.pages)
        await self.update(inter)

    @discord.ui.button(label="❌", style=discord.ButtonStyle.danger)
    async def close(self, inter, btn):
        if inter.user != self.ctx.author:
            return await inter.response.send_message("Not your menu!", ephemeral=True)
        await inter.message.delete()
        self.stop()

# ==================================================
# HELP COMMANDS
# ==================================================
@bot.command(name="cmds", aliases=["commands"])
async def help_cmd(ctx):
    owner = await is_owner(ctx.author.id)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    pages = [
        discord.Embed(title="💰 Economy (1/7)", color=discord.Color.blue()).add_field(
            name="Commands", value=f"`.bal` – balance\n`.daily` – {emoji}1500 (10 msg)\n`.work` – {emoji}150-300 (5m)\n`.sleep` – {emoji}2000-2500 (8h)\n`.crime` – {emoji}200-800 (15m)\n`.dep <all/1k>`\n`.with <all/1k>`\n`.pay @user <amount/all>`\n`.rob @user` (1h)\n`.interest`", inline=False),
        discord.Embed(title="🏦 Loans (2/7)", color=discord.Color.purple()).add_field(
            name="Commands", value="`.loan <amount>` (max 50k)\n`.repay <all/half/amount>`\n`.loaninfo`", inline=False),
        discord.Embed(title="🎰 Gambling (3/7)", color=discord.Color.gold()).add_field(
            name="Games", value="`.cf <amount> [heads/tails]`\n`.slots <amount>`\n`.bj <amount>`\n`.crash <amount>`\n`.mines <amount> <mines>` (1‑19)\n`.tower <amount>`\n`.roulette <amount> <red/black/green/number>`\n`.highlow <amount> <h/l>`\n`.dice <amount> <1-6>`\n`.horserace <amount> <A/B/C/D>`", inline=False),
        discord.Embed(title="🛒 Shop & Business (4/7)", color=discord.Color.green()).add_field(
            name="Commands", value="`.createshop <name>`\n`.addshopitem <price> <item>` (prices: 1k, 5m, 100sx)\n`.removeshopitem <item>`\n`.myshop`\n`.buyfromshop @user <item>` (tax may apply)\n`.closeshop`\n`.globalmarket`\n`.buybusiness <type>`\n`.business`\n`.upgradebusiness`\n`.collectprofits`\n`.dailybonus`\n`.sellbusiness`", inline=False),
        discord.Embed(title="💕 Relationships (5/7)", color=discord.Color.pink()).add_field(
            name="Commands", value="`.date @user`\n`.marry @user`\n`.divorce`\n`.affection`\n`.gift @user <amount>`\n`.adopt @user`\n`.children`\n`.family`\n`.leavefamily` (if child)\n`.pending`", inline=False),
        discord.Embed(title="📊 Leaderboards (6/7)", color=discord.Color.purple()).add_field(
            name="Commands", value="`.glb money` / `.glb xp`\n`.slb money` / `.slb xp`\n`.topcouples`\n`.level`", inline=False),
        discord.Embed(title="👑 Owner (7/7)", color=discord.Color.red()).add_field(
            name="Commands", value="`.ccmds` – Show owner commands\n`.avt @user` – Toggle tax exemption\n`.addaffection @user <amount>`\n`.setaffection @user <amount>`\n`.rewardlast <amount> [count]`", inline=False)
    ]
    await ctx.send(embed=pages[0], view=HelpView(ctx, pages))

@bot.command(name="ccmds")
@owner_only()
async def owner_commands_cmd(ctx):
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    pages = [
        discord.Embed(title="👑 Owner Commands (1/2)", color=discord.Color.red()).add_field(
            name="Economy Management",
            value="`.addmoney @user <amount>`\n`.removemoney @user <amount>`\n`.setmoney @user <amount>`\n`.addbank @user <amount>`\n`.removebank @user <amount>`\n`.economywipe`\n`.toggleeconomy`\n`.togglerob`\n`.togglegambling`\n`.setdailyamount <amount>`\n`.setcurrency <emoji>`\n`.rewardlast <amount> [count]` – add to last chatters", inline=False),
        discord.Embed(title="👑 Owner Commands (2/2)", color=discord.Color.red()).add_field(
            name="Protection & Logs",
            value="`.protect @user`\n`.unprotect @user`\n`.blacklist @user`\n`.whitelist @user`\n`.avt @user`\n`.addaffection @user <amount>`\n`.setaffection @user <amount>`\n`.logs [limit]`\n\n**Owner Management**\n`.addowner <id>`\n`.removeowner <id>`\n`.ownerlist`", inline=False)
    ]
    await ctx.send(embed=pages[0], view=OwnerHelpView(ctx, pages))

# ==================================================
# ECONOMY COMMANDS (core)
# ==================================================
@bot.command(name="balance", aliases=["bal"])
@economy_check()
async def balance(ctx, user: discord.User = None):
    target = user or ctx.author
    data = await get_user(target.id)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    embed = discord.Embed(title=f"{target.display_name}'s Balance", color=discord.Color.teal())
    embed.add_field(name="Wallet", value=f"{format_number(data['money'])}{emoji}", inline=True)
    embed.add_field(name="Bank", value=f"{format_number(data['bank'])}{emoji}", inline=True)
    embed.add_field(name="Total", value=f"{format_number(data['money']+data['bank'])}{emoji}", inline=True)
    if data.get('loan_amount', 0) > 0:
        embed.add_field(name="⚠️ Loan", value=f"{format_number(data['loan_amount'])}{emoji}", inline=True)
    await ctx.send(embed=embed)

@bot.command(name="daily")
@economy_check()
async def daily(ctx):
    data = await get_user(ctx.author.id)
    if data.get('last_daily'):
        last = datetime.fromisoformat(data['last_daily'])
        if datetime.now(timezone.utc) - last < timedelta(hours=24):
            remain = timedelta(hours=24) - (datetime.now(timezone.utc) - last)
            return await ctx.send(f"⏰ Already claimed. Try again in {remain.seconds//3600}h.")
    needed = await get_setting(ctx.guild.id, "daily_messages_needed")
    if data.get('daily_messages', 0) < needed:
        return await ctx.send(f"❌ You need {needed - data['daily_messages']} more messages today.")
    amount = await get_setting(ctx.guild.id, "daily_amount")
    await update_money(ctx.author.id, amount)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_daily = ?, daily_messages = 0 WHERE user_id = ?",
                         (datetime.now(timezone.utc).isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Daily reward: +{format_number(amount)}{emoji}")

@bot.command(name="work")
@economy_check()
async def work(ctx):
    data = await get_user(ctx.author.id)
    if data.get('last_work'):
        last = datetime.fromisoformat(data['last_work'])
        if datetime.now(timezone.utc) - last < timedelta(minutes=5):
            remain = timedelta(minutes=5) - (datetime.now(timezone.utc) - last)
            return await ctx.send(f"⏰ Wait {remain.seconds//60}m {remain.seconds%60}s.")
    min_amt = await get_setting(ctx.guild.id, "work_amount_min")
    max_amt = await get_setting(ctx.guild.id, "work_amount_max")
    earn = random.randint(min_amt, max_amt)
    await update_money(ctx.author.id, earn)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_work = ? WHERE user_id = ?",
                         (datetime.now(timezone.utc).isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"💼 Worked and earned {format_number(earn)}{emoji}!")

@bot.command(name="sleep")
@economy_check()
async def sleep(ctx):
    data = await get_user(ctx.author.id)
    if data.get('last_sleep'):
        last = datetime.fromisoformat(data['last_sleep'])
        if datetime.now(timezone.utc) - last < timedelta(hours=8):
            remain = timedelta(hours=8) - (datetime.now(timezone.utc) - last)
            return await ctx.send(f"😴 Not tired. Try again in {remain.seconds//3600}h.")
    min_amt = await get_setting(ctx.guild.id, "sleep_amount_min")
    max_amt = await get_setting(ctx.guild.id, "sleep_amount_max")
    earn = random.randint(min_amt, max_amt)
    await update_money(ctx.author.id, earn)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_sleep = ? WHERE user_id = ?",
                         (datetime.now(timezone.utc).isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"😴 You slept and woke up with {format_number(earn)}{emoji}!")

@bot.command(name="crime")
@economy_check()
async def crime(ctx):
    data = await get_user(ctx.author.id)
    if data.get('last_crime'):
        last = datetime.fromisoformat(data['last_crime'])
        if datetime.now(timezone.utc) - last < timedelta(minutes=15):
            remain = timedelta(minutes=15) - (datetime.now(timezone.utc) - last)
            return await ctx.send(f"⏰ Wait {remain.seconds//60}m.")
    crimes = [("Pickpocket", 0.7), ("Store robbery", 0.55), ("Bank heist", 0.4)]
    name, rate = random.choice(crimes)
    success = random.random() < rate
    min_amt = await get_setting(ctx.guild.id, "crime_amount_min")
    max_amt = await get_setting(ctx.guild.id, "crime_amount_max")
    reward = random.randint(min_amt, max_amt)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if success:
        await update_money(ctx.author.id, reward)
        await ctx.send(f"🦹 {name} successful! +{format_number(reward)}{emoji}!")
    else:
        fine = reward // 2
        if data['money'] >= fine:
            await update_money(ctx.author.id, -fine)
            await ctx.send(f"🚔 Caught! Lost {format_number(fine)}{emoji}.")
        else:
            await ctx.send("🚔 Caught! You went to jail.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_crime = ? WHERE user_id = ?",
                         (datetime.now(timezone.utc).isoformat(), ctx.author.id))
        await db.commit()

@bot.command(name="deposit", aliases=["dep"])
@economy_check()
async def deposit(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    if amount_str.lower() == "all":
        amount = data['money']
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return await ctx.send("❌ Invalid amount.")
    if amount <= 0 or amount > data['money']:
        return await ctx.send(f"❌ You have {format_number(data['money'])} coins.")
    # use Python arithmetic for safety
    new_money = data['money'] - amount
    new_bank = data['bank'] + amount
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = ?, bank = ? WHERE user_id = ?",
                         (str(new_money), str(new_bank), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Deposited {format_number(amount)}{emoji}.")

@bot.command(name="withdraw", aliases=["with"])
@economy_check()
async def withdraw(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    if amount_str.lower() == "all":
        amount = data['bank']
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return await ctx.send("❌ Invalid amount.")
    if amount <= 0 or amount > data['bank']:
        return await ctx.send(f"❌ You have {format_number(data['bank'])} in bank.")
    new_money = data['money'] + amount
    new_bank = data['bank'] - amount
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = ?, bank = ? WHERE user_id = ?",
                         (str(new_money), str(new_bank), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Withdrew {format_number(amount)}{emoji}.")

@bot.command(name="pay")
@economy_check()
async def pay(ctx, target: discord.User, amount_str: str):
    if target == ctx.author:
        return await ctx.send("❌ Can't pay yourself.")
    try:
        if amount_str.lower() == "all":
            amount = (await get_user(ctx.author.id))['money']
        else:
            amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount.")
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive.")
    sender_data = await get_user(ctx.author.id)
    if sender_data['money'] < amount:
        return await ctx.send(f"❌ You have {format_number(sender_data['money'])} coins.")
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    view = PaymentConfirmView(ctx.author, target, amount, emoji)
    embed = discord.Embed(title="💸 Confirm Payment", color=discord.Color.blue())
    embed.add_field(name="To", value=target.mention, inline=True)
    embed.add_field(name="Amount", value=f"{format_number(amount)}{emoji}", inline=True)
    embed.add_field(name="⏱️ Time", value="60 seconds", inline=True)
    await ctx.send(f"{ctx.author.mention}, you are about to send {format_number(amount)}{emoji} to {target.mention}. Confirm?", embed=embed, view=view)

@bot.command(name="rob")
@economy_check()
async def rob(ctx, target: discord.User):
    if target == ctx.author:
        return await ctx.send("❌ Can't rob yourself.")
    if await get_setting(ctx.guild.id, "rob_enabled") == 0:
        return await ctx.send("❌ Rob disabled.")
    if await is_protected(target.id):
        return await ctx.send(f"❌ {target.mention} is protected.")
    tdata = await get_user(target.id)
    if tdata['money'] < 100:
        return await ctx.send(f"❌ {target.mention} is too poor.")
    data = await get_user(ctx.author.id)
    if data.get('last_rob'):
        last = datetime.fromisoformat(data['last_rob'])
        if datetime.now(timezone.utc) - last < timedelta(hours=1):
            remain = timedelta(hours=1) - (datetime.now(timezone.utc) - last)
            return await ctx.send(f"⏰ Wait {remain.seconds//3600}h {(remain.seconds%3600)//60}m.")
    percent = random.uniform(1, 15)
    steal = int(tdata['money'] * (percent / 100))
    steal = max(50, min(steal, tdata['money']))
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await update_money(target.id, -steal)
    await update_money(ctx.author.id, steal)
    await ctx.send(f"✅ Robbed {target.mention} for {format_number(steal)}{emoji} ({percent:.1f}% of their wallet).")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_rob = ? WHERE user_id = ?",
                         (datetime.now(timezone.utc).isoformat(), ctx.author.id))
        await db.commit()

@bot.command(name="interest")
@economy_check()
async def interest(ctx):
    rate = await get_setting(ctx.guild.id, "interest_rate")
    data = await get_user(ctx.author.id)
    bank = data['bank']
    earn = min(bank, 50000)
    daily = int(earn * rate / 100)
    embed = discord.Embed(title="🏦 Bank Interest", color=discord.Color.gold())
    embed.add_field(name="Rate", value=f"{rate}% daily", inline=True)
    embed.add_field(name="Your Bank", value=f"{format_number(bank)}", inline=True)
    embed.add_field(name="Daily Interest", value=f"{format_number(daily)}", inline=True)
    await ctx.send(embed=embed)

# ==================================================
# LOAN COMMANDS (with unlimited money support)
# ==================================================
@bot.command(name="loan")
@economy_check()
async def loan(ctx, amount_str: str):
    try:
        amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount (e.g., 500, 1k).")
    if amount <= 0 or amount > 50000:
        return await ctx.send("❌ Max loan is 50,000 coins per request.")
    data = await get_user(ctx.author.id)
    if data.get('loan_amount', 0) > 0:
        return await ctx.send(f"❌ You already have a loan of {format_number(data['loan_amount'])}. Repay first with `.repay all`.")
    if data.get('loan_taken_at'):
        last = datetime.fromisoformat(data['loan_taken_at'])
        if datetime.now(timezone.utc) - last < timedelta(hours=1):
            remain = timedelta(hours=1) - (datetime.now(timezone.utc) - last)
            return await ctx.send(f"⏰ You just took a loan. Try again in {remain.seconds//60}m.")
    await update_money(ctx.author.id, amount)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET loan_amount = ?, loan_taken_at = ? WHERE user_id = ?",
                         (str(amount), datetime.now(timezone.utc).isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"🏦 Loan approved! +{format_number(amount)}{emoji}. Interest: 10% per hour. Repay with `.repay`")

@bot.command(name="repay")
@economy_check()
async def repay(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    loan = data.get('loan_amount', 0)
    if loan <= 0:
        return await ctx.send("❌ No active loan.")
    if amount_str.lower() == "all":
        amount = loan
    elif amount_str.lower() == "half":
        amount = loan // 2
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return await ctx.send("❌ Invalid amount.")
    if amount <= 0 or amount > loan:
        return await ctx.send("❌ Invalid amount.")
    if data['money'] < amount:
        return await ctx.send(f"❌ You have {format_number(data['money'])} coins.")
    await update_money(ctx.author.id, -amount)
    new_loan = loan - amount
    async with aiosqlite.connect("hakari.db") as db:
        if new_loan == 0:
            await db.execute("UPDATE users SET loan_amount = '0', loan_taken_at = NULL WHERE user_id = ?", (ctx.author.id,))
        else:
            await db.execute("UPDATE users SET loan_amount = ? WHERE user_id = ?", (str(new_loan), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if new_loan == 0:
        await ctx.send(f"✅ Loan fully repaid! Paid {format_number(amount)}{emoji}. You are debt-free!")
    else:
        await ctx.send(f"✅ Repaid {format_number(amount)}{emoji}. Remaining: {format_number(new_loan)}{emoji}")

@bot.command(name="loaninfo")
@economy_check()
async def loaninfo(ctx):
    data = await get_user(ctx.author.id)
    loan = data.get('loan_amount', 0)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if loan <= 0:
        embed = discord.Embed(title="🏦 Loan Status", color=discord.Color.green())
        embed.add_field(name="Active Loan", value="None", inline=False)
        await ctx.send(embed=embed)
    else:
        taken = data.get('loan_taken_at')
        if taken:
            taken_dt = datetime.fromisoformat(taken)
            hours = (datetime.now(timezone.utc) - taken_dt).total_seconds() / 3600
            total = int(loan * (1.10 ** hours))
        else:
            total = loan
        embed = discord.Embed(title="🏦 Loan Status", color=discord.Color.red())
        embed.add_field(name="Original", value=f"{format_number(loan)}{emoji}", inline=True)
        embed.add_field(name="Current Due", value=f"{format_number(total)}{emoji}", inline=True)
        embed.add_field(name="Interest", value="10% per hour", inline=True)
        await ctx.send(embed=embed)

# ==================================================
# GAMBLING COMMANDS (with cooldown & bet deduction first)
# ==================================================
@bot.command(name="cf", aliases=["coinflip"])
@economy_check()
@gambling_cooldown_check()
async def coinflip(ctx, amount_str: str, choice: str = None):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    if choice and choice.lower() not in ("heads","tails"):
        return await ctx.send("❌ Choose heads or tails.")
    await update_money(ctx.author.id, -amount)
    result = random.choice(["heads","tails"])
    win = (choice and choice.lower() == result) or (not choice and random.choice([True,False]))
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if win:
        winnings = amount * 2
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🪙 Coin landed on **{result}**! You won {format_number(winnings-amount)}{emoji}!")
    else:
        await ctx.send(f"🪙 Coin landed on **{result}**! You lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

@bot.command(name="slots")
@economy_check()
@gambling_cooldown_check()
async def slots(ctx, amount_str: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    emojis = ["🍒","🍋","🍊","🍉","⭐","💎"]
    r = [random.choice(emojis) for _ in range(3)]
    mult = 0
    if r[0]==r[1]==r[2]:
        mult = 3 if r[0]=="💎" else 2
    elif r[0]==r[1] or r[1]==r[2] or r[0]==r[2]:
        mult = 0.5
    winnings = int(amount * mult)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if mult >= 1:
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🎰 `[{r[0]}] [{r[1]}] [{r[2]}]`\n🎉 You won {format_number(winnings-amount)}{emoji}!")
    elif mult > 0:
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🎰 `[{r[0]}] [{r[1]}] [{r[2]}]`\n✅ Small win! Got back {format_number(winnings)}{emoji}.")
    else:
        await ctx.send(f"🎰 `[{r[0]}] [{r[1]}] [{r[2]}]`\n❌ Lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

class BlackjackView(discord.ui.View):
    def __init__(self, ctx, bet, player, dealer, emoji):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.bet = bet
        self.player = player
        self.dealer = dealer
        self.emoji = emoji
        self.ended = False
        self.start = datetime.now(timezone.utc)

    def card_emoji(self, c):
        m = {2:"🃒",3:"🃓",4:"🃔",5:"🃕",6:"🃖",7:"🃗",8:"🃘",9:"🃙",10:"🃚",11:"🃑"}
        return m.get(c, "🃟")

    async def hand_value(self, hand):
        val = sum(hand)
        aces = hand.count(11)
        while val > 21 and aces:
            val -= 10
            aces -= 1
        return val

    async def embed_game(self):
        remain = 120 - (datetime.now(timezone.utc) - self.start).total_seconds()
        mins, secs = divmod(max(0, int(remain)), 60)
        pv = await self.hand_value(self.player)
        pstr = " ".join(self.card_emoji(c) for c in self.player)
        dstr = f"{self.card_emoji(self.dealer[0])} ?" if len(self.dealer)==2 else " ".join(self.card_emoji(c) for c in self.dealer)
        dv = "?" if len(self.dealer)==2 else str(await self.hand_value(self.dealer))
        embed = discord.Embed(title=f"{self.ctx.author.display_name}'s Blackjack", color=0x2ecc71)
        embed.add_field(name=f"Your Hand ({pv})", value=pstr, inline=False)
        embed.add_field(name="Dealer", value=f"{dstr}\n**{dv}**", inline=False)
        embed.add_field(name="💰 Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
        embed.add_field(name="⏱️ Time", value=f"{mins}m {secs}s", inline=True)
        return embed

    async def end_game(self, result, win=0):
        if result == "win":
            await update_money(self.ctx.author.id, win)
            msg = f"✅ You won {format_number(win-self.bet)}{self.emoji}!"
        elif result == "lose":
            msg = f"❌ You lost {format_number(self.bet)}{self.emoji}!"
        elif result == "push":
            await update_money(self.ctx.author.id, self.bet)
            msg = "🤝 Push! Money returned."
        elif result == "blackjack":
            w = int(self.bet * 2.5)
            await update_money(self.ctx.author.id, w)
            msg = f"🎉 BLACKJACK! Won {format_number(w-self.bet)}{self.emoji}!"
        else:
            msg = f"⏰ Timeout! Lost {format_number(self.bet)}{self.emoji}."
        embed = discord.Embed(title="Game Over", color=0xe74c3c)
        embed.add_field(name="Result", value=msg, inline=False)
        await self.ctx.send(embed=embed)
        self.ended = True
        self.stop()
        await set_gambling_cooldown(self.ctx.author.id)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, inter, btn):
        if inter.user != self.ctx.author:
            return
        self.player.append(random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11]))
        if await self.hand_value(self.player) > 21:
            await self.end_game("lose")
            await inter.message.delete()
            return
        await inter.response.edit_message(embed=await self.embed_game(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success)
    async def stand(self, inter, btn):
        if inter.user != self.ctx.author:
            return
        pv = await self.hand_value(self.player)
        while await self.hand_value(self.dealer) < 17:
            self.dealer.append(random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11]))
        dv = await self.hand_value(self.dealer)
        if dv > 21 or pv > dv:
            w = self.bet * 2
            await self.end_game("win", w)
        elif pv < dv:
            await self.end_game("lose")
        else:
            await self.end_game("push")
        await inter.message.delete()

    async def on_timeout(self):
        if not self.ended:
            await self.end_game("timeout")

@bot.command(name="bj", aliases=["blackjack"])
@economy_check()
@gambling_cooldown_check()
async def blackjack(ctx, amount_str: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    cards = [2,3,4,5,6,7,8,9,10,10,10,10,11]
    player = [random.choice(cards), random.choice(cards)]
    dealer = [random.choice(cards), random.choice(cards)]
    pv = sum(player)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if pv == 21:
        win = int(amount * 2.5)
        await update_money(ctx.author.id, win)
        await ctx.send(f"🎉 BLACKJACK! Won {format_number(win-amount)}{emoji}!")
        await set_gambling_cooldown(ctx.author.id)
    else:
        view = BlackjackView(ctx, amount, player, dealer, emoji)
        embed = await view.embed_game()
        await ctx.send(embed=embed, view=view)

class MinesView(discord.ui.View):
    def __init__(self, ctx, bet, mines, multiplier, emoji):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.bet = bet
        self.mines = mines
        self.mult = multiplier
        self.emoji = emoji
        self.revealed = [False]*20
        self.mine_pos = set(random.sample(range(20), mines))
        self.safe_reveals = 0
        self.ended = False
        self.start = datetime.now(timezone.utc)
        for i in range(20):
            btn = discord.ui.Button(label="⬛", style=discord.ButtonStyle.secondary, row=i//5, custom_id=f"m{i}")
            btn.callback = self.make_callback(i)
            self.add_item(btn)
        self.cashout = discord.ui.Button(label="💰 Cashout", style=discord.ButtonStyle.success, row=4)
        self.cashout.callback = self.cashout_cb
        self.add_item(self.cashout)

    def make_callback(self, pos):
        async def cb(inter):
            if inter.user != self.ctx.author or self.ended:
                return
            if self.revealed[pos]:
                return
            self.revealed[pos] = True
            if pos in self.mine_pos:
                self.ended = True
                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.custom_id and child.custom_id.startswith("m"):
                        idx = int(child.custom_id[1:])
                        if idx in self.mine_pos:
                            child.label = "💣"
                            child.style = discord.ButtonStyle.danger
                        elif self.revealed[idx]:
                            child.label = "💎"
                            child.style = discord.ButtonStyle.success
                        child.disabled = True
                await inter.response.edit_message(content=f"💥 BOOM! You lost {format_number(self.bet)}{self.emoji}.", view=self)
                self.stop()
                await set_gambling_cooldown(self.ctx.author.id)
            else:
                self.safe_reveals += 1
                self.mult = round(1.02 * (25/(25-self.mines))**(1+self.safe_reveals*0.1), 2)
                self.mult = min(self.mult, 100)
                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.custom_id == f"m{pos}":
                        child.label = "💎"
                        child.style = discord.ButtonStyle.success
                        child.disabled = True
                        break
                remain = 120 - (datetime.now(timezone.utc) - self.start).total_seconds()
                mins, secs = divmod(max(0, int(remain)), 60)
                board = ""
                for i in range(20):
                    board += "💎 " if self.revealed[i] else "⬛ "
                    if (i+1)%5==0:
                        board += "\n"
                embed = discord.Embed(title="💣 Minesweeper", color=discord.Color.gold())
                embed.add_field(name="Board", value=board, inline=False)
                embed.add_field(name="Mines", value=f"{self.mines} bombs", inline=True)
                embed.add_field(name="Multiplier", value=f"{self.mult}x", inline=True)
                embed.add_field(name="Cashout", value=f"{format_number(int(self.bet*self.mult))}{self.emoji}", inline=True)
                embed.add_field(name="⏱️ Time", value=f"{mins}m {secs}s", inline=True)
                await inter.response.edit_message(embed=embed, view=self)
        return cb

    async def cashout_cb(self, inter):
        if inter.user != self.ctx.author or self.ended:
            return
        if self.safe_reveals == 0:
            return await inter.response.send_message("❌ You must reveal at least one tile before cashing out!", ephemeral=True)
        win = int(self.bet * self.mult)
        await update_money(self.ctx.author.id, win)
        await inter.response.edit_message(content=f"💰 Cashed out! Won {format_number(win-self.bet)}{self.emoji}!", view=None)
        self.ended = True
        self.stop()
        await set_gambling_cooldown(self.ctx.author.id)

    async def on_timeout(self):
        if not self.ended:
            await self.ctx.send(f"⏰ {self.ctx.author.mention} took too long! Lost {format_number(self.bet)}{self.emoji}.")
            await set_gambling_cooldown(self.ctx.author.id)

@bot.command(name="mines")
@economy_check()
@gambling_cooldown_check()
async def mines_cmd(ctx, amount_str: str, mines: int = 5):
    if mines < 1 or mines > 19:
        return await ctx.send("❌ Mines must be 1‑19.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    mult = round(1.02 * (25/(25-mines))**1.2, 2)
    mult = min(mult, 100)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    view = MinesView(ctx, amount, mines, mult, emoji)
    board = "⬛ ⬛ ⬛ ⬛ ⬛\n⬛ ⬛ ⬛ ⬛ ⬛\n⬛ ⬛ ⬛ ⬛ ⬛\n⬛ ⬛ ⬛ ⬛ ⬛"
    embed = discord.Embed(title="💣 Minesweeper", color=discord.Color.gold())
    embed.add_field(name="Board", value=board, inline=False)
    embed.add_field(name="Mines", value=f"{mines} bombs", inline=True)
    embed.add_field(name="Multiplier", value=f"{mult}x", inline=True)
    embed.add_field(name="Cashout", value=f"{format_number(int(amount*mult))}{emoji}", inline=True)
    embed.add_field(name="⏱️ Time", value="2 minutes", inline=True)
    embed.set_footer(text="Reveal tiles to increase multiplier. Must reveal at least 1 to cashout!")
    await ctx.send(embed=embed, view=view)

@bot.command(name="crash")
@economy_check()
@gambling_cooldown_check()
async def crash(ctx, amount_str: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    mult = round(random.uniform(1.01, 100), 2)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if random.random() < 0.5:
        win = int(amount * mult)
        await update_money(ctx.author.id, win)
        await ctx.send(f"📈 Crash at {mult}x! Won {format_number(win-amount)}{emoji}!")
    else:
        await ctx.send(f"💥 Crashed at {mult}x! Lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

class TowerDoorView(discord.ui.View):
    def __init__(self, ctx, bet, emoji):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.bet = bet
        self.emoji = emoji
        self.current_floor = 0
        self.max_floor = random.randint(8, 12)
        self.game_over = False
        self.start_time = datetime.now(timezone.utc)
        self.mine_position = None
        self.add_floor_buttons()

    def add_floor_buttons(self):
        for child in self.children[:]:
            if isinstance(child, discord.ui.Button) and child.custom_id and child.custom_id.startswith("door_"):
                self.remove_item(child)
        self.mine_position = random.randint(1, 3)
        for i in range(1, 4):
            btn = discord.ui.Button(label=f"🚪 Door {i}", style=discord.ButtonStyle.secondary, custom_id=f"door_{i}")
            btn.callback = self.make_door_callback(i)
            self.add_item(btn)
        if not any(isinstance(c, discord.ui.Button) and c.label == "💰 Cash Out" for c in self.children):
            self.cashout_btn = discord.ui.Button(label="💰 Cash Out", style=discord.ButtonStyle.success)
            self.cashout_btn.callback = self.cashout_callback
            self.add_item(self.cashout_btn)

    def get_multiplier(self, floor):
        return round(1.5 ** floor, 2)

    def get_cashout_value(self):
        if self.current_floor == 0:
            return self.bet
        return int(self.bet * self.get_multiplier(self.current_floor))

    async def update_embed(self, interaction, crashed=False):
        cashout_value = self.get_cashout_value()
        embed = discord.Embed(
            title=f"{self.ctx.author.display_name}'s Tower – Door Pick",
            color=0x2ecc71 if not crashed else 0xe74c3c
        )
        embed.add_field(name="Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
        embed.add_field(name="Floor", value=f"{self.current_floor}/{self.max_floor}", inline=True)
        embed.add_field(name="💰 Cashout Value", value=f"{format_number(cashout_value)} {self.emoji}", inline=True)
        if not crashed:
            embed.add_field(name="Pick a Door", value="One door hides a 💣 mine. The other two are safe.", inline=False)
        else:
            embed.add_field(name="💥 BOOM!", value=f"You picked the door with the mine at floor **{self.current_floor+1}**! Lost {format_number(self.bet)}{self.emoji}.", inline=False)
        embed.set_footer(text=f"Floors: {self.max_floor} | Multiplier: {self.get_multiplier(self.current_floor)}x")
        await interaction.response.edit_message(embed=embed, view=self if not crashed else None)

    def make_door_callback(self, door_number):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                return await interaction.response.send_message("Not your game!", ephemeral=True)
            if self.game_over:
                return
            if door_number == self.mine_position:
                self.game_over = True
                await self.update_embed(interaction, crashed=True)
                self.stop()
                await set_gambling_cooldown(self.ctx.author.id)
                return
            self.current_floor += 1
            if self.current_floor == self.max_floor:
                winnings = self.get_cashout_value()
                await update_money(self.ctx.author.id, winnings)
                embed = discord.Embed(
                    title=f"{self.ctx.author.display_name}'s Tower - COMPLETE!",
                    color=0xf1c40f
                )
                embed.add_field(name="Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
                embed.add_field(name="Floors Cleared", value=f"{self.current_floor}/{self.max_floor}", inline=True)
                embed.add_field(name="Winnings", value=f"{format_number(winnings)} {self.emoji}", inline=True)
                embed.add_field(name="🎉 CONGRATULATIONS!", value="You reached the top!", inline=False)
                await interaction.response.edit_message(embed=embed, view=None)
                self.game_over = True
                self.stop()
                await set_gambling_cooldown(self.ctx.author.id)
            else:
                self.add_floor_buttons()
                await self.update_embed(interaction, crashed=False)
        return callback

    async def cashout_callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Not your game!", ephemeral=True)
        if self.game_over:
            return
        if self.current_floor == 0:
            return await interaction.response.send_message("❌ You must clear at least one floor before cashing out!", ephemeral=True)
        winnings = self.get_cashout_value()
        await update_money(self.ctx.author.id, winnings)
        embed = discord.Embed(
            title=f"{self.ctx.author.display_name}'s Tower",
            color=0x2ecc71
        )
        embed.add_field(name="Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
        embed.add_field(name="Floors Cleared", value=f"{self.current_floor}/{self.max_floor}", inline=True)
        embed.add_field(name="Cashed Out", value=f"{format_number(winnings)} {self.emoji}", inline=True)
        embed.add_field(name="✅ You cashed out!", value="Smart choice!", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)
        self.game_over = True
        self.stop()
        await set_gambling_cooldown(self.ctx.author.id)

    async def on_timeout(self):
        if not self.game_over:
            await self.ctx.send(f"⏰ {self.ctx.author.mention} took too long! Lost {format_number(self.bet)}{self.emoji}.")
            await set_gambling_cooldown(self.ctx.author.id)

@bot.command(name="tower")
@economy_check()
@gambling_cooldown_check()
async def tower(ctx, amount_str: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    view = TowerDoorView(ctx, amount, emoji)
    embed = discord.Embed(
        title=f"{ctx.author.display_name}'s Tower – Door Pick",
        color=0x2ecc71
    )
    embed.add_field(name="Bet", value=f"{format_number(amount)} {emoji}", inline=True)
    embed.add_field(name="Floor", value="0/???", inline=True)
    embed.add_field(name="💰 Cashout Value", value=f"{format_number(amount)} {emoji}", inline=True)
    embed.add_field(name="Pick a Door", value="One door hides a 💣 mine. The other two are safe.", inline=False)
    embed.set_footer(text="Each safe door increases your multiplier. Cash out anytime.")
    await ctx.send(embed=embed, view=view)

@bot.command(name="roulette", aliases=["rl"])
@economy_check()
@gambling_cooldown_check()
async def roulette(ctx, amount_str: str, *, bet: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    bet = bet.lower().strip()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    number = random.randint(0, 36)
    if number == 0:
        color = "green"
    elif number in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]:
        color = "red"
    else:
        color = "black"
    win = False
    payout = 0
    if bet.isdigit():
        if int(bet) == number:
            win, payout = True, amount * 35
    elif bet in ["red", "r"]:
        if color == "red":
            win, payout = True, amount * 2
    elif bet in ["black", "b"]:
        if color == "black":
            win, payout = True, amount * 2
    elif bet in ["green", "g", "0"]:
        if number == 0:
            win, payout = True, amount * 14
    else:
        await update_money(ctx.author.id, amount)  # refund invalid bet
        return await ctx.send("❌ Invalid bet! Choose: red, black, green, or a number 0-36")
    if win:
        await update_money(ctx.author.id, payout)
        await ctx.send(f"🎯 The ball landed on **{number}** ({color})! You won {format_number(payout-amount)}{emoji}!")
    else:
        await ctx.send(f"❌ The ball landed on **{number}** ({color}). You lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

@bot.command(name="highlow", aliases=["hl"])
@economy_check()
@gambling_cooldown_check()
async def highlow(ctx, amount_str: str, choice: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    if choice.lower() not in ["h", "higher", "l", "lower"]:
        return await ctx.send("❌ Choose: h (higher) or l (lower)")
    await update_money(ctx.author.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    cards = {2:"2",3:"3",4:"4",5:"5",6:"6",7:"7",8:"8",9:"9",10:"10",11:"J",12:"Q",13:"K",14:"A"}
    values = [2,3,4,5,6,7,8,9,10,11,12,13,14]
    first = random.choice(values)
    second = random.choice(values)
    if choice.lower() in ["h","higher"] and second > first:
        winnings = int(amount * 1.1)
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🃏 First: {cards[first]}, Second: {cards[second]}\n✅ You won {format_number(winnings-amount)}{emoji} (1.1x)!")
    elif choice.lower() in ["l","lower"] and second < first:
        winnings = int(amount * 1.1)
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🃏 First: {cards[first]}, Second: {cards[second]}\n✅ You won {format_number(winnings-amount)}{emoji} (1.1x)!")
    elif second == first:
        await update_money(ctx.author.id, amount)
        await ctx.send(f"🃏 First: {cards[first]}, Second: {cards[second]} (Tie! Money returned).")
    else:
        await ctx.send(f"🃏 First: {cards[first]}, Second: {cards[second]}\n❌ You lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

@bot.command(name="dice", aliases=["dc"])
@economy_check()
@gambling_cooldown_check()
async def dice(ctx, amount_str: str, guess: int):
    if guess < 1 or guess > 6:
        return await ctx.send("❌ Guess must be between 1 and 6.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    roll = random.randint(1,6)
    if roll == guess:
        payout = amount * 5
        await update_money(ctx.author.id, payout)
        await ctx.send(f"🎲 You rolled a **{roll}**! You guessed correctly! Won {format_number(payout-amount)}{emoji}!")
    else:
        await ctx.send(f"🎲 You rolled a **{roll}**. You guessed {guess}. Lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

@bot.command(name="horserace", aliases=["hrace"])
@economy_check()
@gambling_cooldown_check()
async def horserace(ctx, amount_str: str, horse: str):
    horse = horse.upper()
    if horse not in ["A","B","C","D"]:
        return await ctx.send("❌ Choose horse A, B, C, or D.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    horses = {"A":2.5, "B":3.0, "C":4.0, "D":6.0}
    rand = random.random()
    if rand < 0.40:
        winner = "A"
    elif rand < 0.70:
        winner = "B"
    elif rand < 0.90:
        winner = "C"
    else:
        winner = "D"
    msg = await ctx.send("🏁 **THE RACE IS STARTING!** 🏁\n🏁 A: 🐎     B: 🐎     C: 🐎     D: 🐎")
    frames = [
        "🏁 A: 🐎→   B: 🐎     C: 🐎     D: 🐎",
        "🏁 A: 🐎→→  B: 🐎→    C: 🐎     D: 🐎",
        "🏁 A: 🐎→→→ B: 🐎→→   C: 🐎→    D: 🐎",
        "🏁 A: 🐎→→→→B: 🐎→→→  C: 🐎→→   D: 🐎→",
    ]
    for f in frames:
        await asyncio.sleep(1)
        await msg.edit(content=f)
    if horse == winner:
        payout = int(amount * horses[winner])
        await update_money(ctx.author.id, payout)
        await ctx.send(f"🏆 **Horse {winner} WINS!** 🏆\nYour horse {horse} won! You won {format_number(payout-amount)}{emoji}!")
    else:
        await ctx.send(f"🏆 **Horse {winner} WINS!** 🏆\nYour horse {horse} lost. You lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

# ==================================================
# SHOP COMMANDS (with suffix price support)
# ==================================================
@bot.command(name="createshop")
@economy_check()
async def create_shop(ctx, *, name: str):
    data = await get_user(ctx.author.id)
    if data.get('shop_name'):
        return await ctx.send("❌ You already have a shop.")
    if len(name) > 50:
        return await ctx.send("❌ Name too long (max 50 chars).")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_name = ?, shop_open = 1 WHERE user_id = ?", (name, ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Shop '{name}' created! Use `.addshopitem <price> <item>` to add items. (Prices support suffixes like 1k, 5m, 100sx)")

@bot.command(name="addshopitem")
@economy_check()
async def add_shop_item(ctx, price_str: str, *, item: str):
    data = await get_user(ctx.author.id)
    if not data.get('shop_name'):
        return await ctx.send("❌ You don't have a shop. Create one with `.createshop <name>`.")
    if not data.get('shop_open'):
        return await ctx.send("❌ Your shop is closed. Use `.closeshop` to open it.")
    try:
        price = parse_amount(price_str)
    except:
        return await ctx.send("❌ Invalid price. Use a number or suffix (e.g., 500, 1k, 2.5m, 100sx).")
    if price <= 0:
        return await ctx.send("❌ Price must be positive.")
    items = json.loads(data.get('shop_items', '{}'))
    if len(items) >= 20:
        return await ctx.send("❌ Shop is full (20 items max).")
    items[item] = price
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Added '{item}' for {format_number(price)}{emoji}.")

@bot.command(name="removeshopitem")
@economy_check()
async def remove_shop_item(ctx, *, item: str):
    data = await get_user(ctx.author.id)
    if not data.get('shop_name'):
        return await ctx.send("❌ You don't have a shop.")
    items = json.loads(data.get('shop_items', '{}'))
    if item not in items:
        return await ctx.send("❌ Item not found.")
    del items[item]
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Removed '{item}'.")

@bot.command(name="myshop")
@economy_check()
async def my_shop(ctx):
    data = await get_user(ctx.author.id)
    if not data.get('shop_name'):
        return await ctx.send("❌ No shop.")
    items = json.loads(data.get('shop_items', '{}'))
    status = "Open" if data.get('shop_open') else "Closed"
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    msg = f"🏪 **{data['shop_name']}** ({status})\n\n"
    if items:
        for item, price in items.items():
            msg += f"• {item}: {format_number(price)}{emoji}\n"
    else:
        msg += "No items for sale."
    await ctx.send(msg)

@bot.command(name="buyfromshop")
@economy_check()
async def buy_from_shop(ctx, seller: discord.User, *, item: str):
    sdata = await get_user(seller.id)
    if not sdata.get('shop_name') or not sdata.get('shop_open'):
        return await ctx.send(f"❌ {seller.display_name}'s shop is closed or doesn't exist.")
    items = json.loads(sdata.get('shop_items', '{}'))
    if item not in items:
        return await ctx.send("❌ Item not found.")
    price = items[item]
    bdata = await get_user(ctx.author.id)
    if bdata['money'] < price:
        return await ctx.send(f"❌ You need {format_number(price)} coins.")
    tax_rate = 10
    exempt = await is_tax_exempt(ctx.author.id)
    seller_earnings = price if exempt else price - int(price * tax_rate / 100)
    await update_money(ctx.author.id, -price)
    await update_money(seller.id, seller_earnings)
    del items[item]
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), seller.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    msg = f"✅ Bought '{item}' for {format_number(price)}{emoji}."
    if not exempt:
        msg += f" Seller received {format_number(seller_earnings)}{emoji} after 10% tax."
    else:
        msg += " (Tax exempt)"
    await ctx.send(msg)

@bot.command(name="closeshop")
@economy_check()
async def close_shop(ctx):
    data = await get_user(ctx.author.id)
    if not data.get('shop_name'):
        return await ctx.send("❌ No shop.")
    new = 0 if data.get('shop_open') else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_open = ? WHERE user_id = ?", (new, ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Shop is now {'open' if new else 'closed'}.")

@bot.command(name="globalmarket")
@economy_check()
async def global_market(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, shop_name FROM users WHERE shop_open=1 AND shop_name IS NOT NULL LIMIT 20") as cur:
            shops = await cur.fetchall()
    if not shops:
        return await ctx.send("No open shops.")
    msg = "🌍 **Global Market**\n\n"
    for uid, name in shops:
        try:
            u = await bot.fetch_user(uid)
            msg += f"• {name} – {u.display_name}\n"
        except:
            msg += f"• {name}\n"
    await ctx.send(msg)

# ==================================================
# BUSINESS COMMANDS (unchanged)
# ==================================================
@bot.command(name="buybusiness")
@economy_check()
async def buy_business(ctx, biz_type: str):
    types = ["restaurant","casino","cafe"]
    if biz_type.lower() not in types:
        return await ctx.send(f"❌ Choose from: {', '.join(types)}")
    data = await get_user(ctx.author.id)
    cost = 1000
    if data['money'] < cost:
        return await ctx.send(f"❌ Need {format_number(cost)} coins.")
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            if await cur.fetchone():
                return await ctx.send("❌ You already own a business.")
        await update_money(ctx.author.id, -cost)
        await db.execute("INSERT INTO businesses (user_id, business_type, level, last_collected, daily_bonus_collected, reputation) VALUES (?,?,?,?,?,0)",
                         (ctx.author.id, biz_type.lower(), 1, datetime.now(timezone.utc).isoformat(), None))
        await db.commit()
    await ctx.send(f"✅ Bought a {biz_type} business! Use `.collectprofits` to earn.")

@bot.command(name="business")
@economy_check()
async def business_info(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT business_type, level, reputation FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return await ctx.send("❌ No business.")
    biz, lvl, rep = row
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    base = 50 * lvl
    total = int(base * (1 + rep/100))
    await ctx.send(f"🏪 **{biz}**\nLevel: {lvl}\nReputation: {rep}\nIncome: {format_number(total)}{emoji}/hour")

@bot.command(name="upgradebusiness")
@economy_check()
async def upgrade_business(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return await ctx.send("❌ No business.")
    lvl = row[0]
    cost = 500 * lvl
    data = await get_user(ctx.author.id)
    if data['money'] < cost:
        return await ctx.send(f"❌ Upgrade costs {format_number(cost)} coins.")
    await update_money(ctx.author.id, -cost)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE businesses SET level = level+1 WHERE user_id=?", (ctx.author.id,))
        await db.commit()
    await ctx.send(f"✅ Business upgraded to level {lvl+1}!")

@bot.command(name="collectprofits")
@economy_check()
async def collect_profits(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level, last_collected, reputation FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return await ctx.send("❌ No business.")
    lvl, last, rep = row
    now = datetime.now(timezone.utc)
    last_dt = datetime.fromisoformat(last)
    hours = (now - last_dt).total_seconds() / 3600
    if hours < 1:
        remain = 3600 - (now - last_dt).total_seconds()
        return await ctx.send(f"⏰ Next collection in {int(remain//60)} minutes.")
    base_profit = int(50 * lvl * hours)
    profit = int(base_profit * (1 + rep/100))
    await update_money(ctx.author.id, profit)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE businesses SET last_collected = ?, reputation = reputation + 1 WHERE user_id=?", (now.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Collected {format_number(profit)}{emoji}. Reputation +1.")

@bot.command(name="dailybonus")
@economy_check()
async def daily_bonus(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level, daily_bonus_collected, reputation FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return await ctx.send("❌ No business.")
    lvl, last_bonus, rep = row
    now = datetime.now(timezone.utc)
    if last_bonus:
        last_dt = datetime.fromisoformat(last_bonus)
        if (now - last_dt).total_seconds() < 86400:
            return await ctx.send("⏰ Already claimed today.")
    bonus = int(500 * lvl * (1 + rep/100))
    await update_money(ctx.author.id, bonus)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE businesses SET daily_bonus_collected = ? WHERE user_id=?", (now.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"🎁 Daily bonus: {format_number(bonus)}{emoji}!")

@bot.command(name="sellbusiness")
@economy_check()
async def sell_business(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level, reputation FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return await ctx.send("❌ No business.")
    lvl, rep = row
    value = int(500 * lvl * (1 + rep/200))
    await update_money(ctx.author.id, value)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM businesses WHERE user_id=?", (ctx.author.id,))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Sold business for {format_number(value)}{emoji}.")

# ==================================================
# RELATIONSHIP COMMANDS (including leavefamily)
# ==================================================
async def is_family_member_local(user_id, target_id):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM children WHERE parent_id=? AND child_id=?", (user_id, target_id)) as cur:
            if await cur.fetchone():
                return True
        async with db.execute("SELECT 1 FROM children WHERE parent_id=? AND child_id=?", (target_id, user_id)) as cur:
            if await cur.fetchone():
                return True
    return False

@bot.command(name="date")
@economy_check()
async def date(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("❌ Can't date yourself.")
    if await is_family_member_local(ctx.author.id, user.id):
        return await ctx.send("❌ Cannot date a family member.")
    data = await get_user(ctx.author.id)
    if data.get('spouse_id'):
        return await ctx.send("❌ Already married.")
    if data['money'] < 500:
        return await ctx.send("❌ Need 500 coins.")
    await update_money(ctx.author.id, -500)
    gain = random.randint(50,150)
    await update_affection(user.id, gain)
    await ctx.send(f"💕 Date with {user.mention}! +{gain} affection.")

@bot.command(name="marry")
@economy_check()
async def marry(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("❌ Can't marry yourself.")
    if await is_family_member_local(ctx.author.id, user.id):
        return await ctx.send("❌ Cannot marry a family member.")
    data = await get_user(ctx.author.id)
    if data.get('spouse_id'):
        return await ctx.send("❌ Already married.")
    target = await get_user(user.id)
    if target.get('spouse_id'):
        return await ctx.send(f"❌ {user.mention} is already married.")
    if data['money'] < 5000:
        return await ctx.send("❌ Need 5000 coins.")
    if target.get('affection', 0) < 1000:
        return await ctx.send(f"❌ Need 1000 affection with {user.mention}.")
    await update_money(ctx.author.id, -5000)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?,?,?,?)",
                         (ctx.author.id, user.id, "marriage", datetime.now(timezone.utc).isoformat()))
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            rid = (await cur.fetchone())[0]
    view = RequestView(ctx.author, user, "marriage", rid)
    embed = discord.Embed(title="💍 Marriage Proposal", color=discord.Color.purple())
    embed.add_field(name="From", value=ctx.author.mention)
    embed.add_field(name="Time", value="2 minutes")
    await ctx.send(f"💍 {ctx.author.mention} proposed to {user.mention}!", embed=embed, view=view)

@bot.command(name="divorce")
@economy_check()
async def divorce(ctx):
    data = await get_user(ctx.author.id)
    spouse = data.get('spouse_id')
    if not spouse:
        return await ctx.send("❌ Not married.")
    if data['money'] < 2500:
        return await ctx.send("❌ Need 2500 coins.")
    await update_money(ctx.author.id, -2500)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (ctx.author.id,))
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (spouse,))
        await db.commit()
    s = await bot.fetch_user(spouse)
    await ctx.send(f"💔 Divorced {s.mention}.")

@bot.command(name="affection")
@economy_check()
async def affection(ctx, user: discord.User = None):
    target = user or ctx.author
    data = await get_user(target.id)
    aff = data.get('affection', 0)
    if aff >= 5000: level = "👑 Eternal Bond"
    elif aff >= 3500: level = "❤️ Soulmates"
    elif aff >= 2000: level = "💜 Lovers"
    elif aff >= 1000: level = "💙 Close Friends"
    elif aff >= 500: level = "💚 Friends"
    else: level = "💔 Strangers"
    bar = "█" * min(20, aff//250) + "░" * (20 - min(20, aff//250))
    embed = discord.Embed(title=f"💕 {target.display_name}'s Affection", color=discord.Color.pink())
    embed.add_field(name="Level", value=level, inline=False)
    embed.add_field(name="Points", value=format_number(aff), inline=False)
    embed.add_field(name="Progress", value=f"`{bar}`", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="gift")
@economy_check()
async def gift(ctx, user: discord.User, amount_str: str):
    try:
        amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount.")
    if amount <= 0 or user == ctx.author:
        return
    data = await get_user(ctx.author.id)
    if data['money'] < amount:
        return await ctx.send(f"❌ You have {format_number(data['money'])} coins.")
    await update_money(ctx.author.id, -amount)
    await update_money(user.id, amount)
    gain = amount // 100
    if gain:
        await update_affection(user.id, gain)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    msg = f"🎁 Gifted {format_number(amount)}{emoji} to {user.mention}!"
    if gain:
        msg += f" (+{format_number(gain)} affection)"
    await ctx.send(msg)

@bot.command(name="adopt")
@economy_check()
async def adopt(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("❌ Can't adopt yourself.")
    data = await get_user(ctx.author.id)
    if data['money'] < 2000:
        return await ctx.send("❌ Need 2000 coins.")
    target = await get_user(user.id)
    if target.get('parent_id'):
        return await ctx.send(f"❌ {user.mention} already has a parent.")
    await update_money(ctx.author.id, -2000)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?,?,?,?)",
                         (ctx.author.id, user.id, "adopt", datetime.now(timezone.utc).isoformat()))
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            rid = (await cur.fetchone())[0]
    view = RequestView(ctx.author, user, "adopt", rid)
    embed = discord.Embed(title="👶 Adoption Request", color=discord.Color.teal())
    embed.add_field(name="From", value=ctx.author.mention)
    embed.add_field(name="Time", value="2 minutes")
    await ctx.send(f"👶 {ctx.author.mention} wants to adopt {user.mention}!", embed=embed, view=view)

@bot.command(name="children")
@economy_check()
async def children(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT child_id FROM children WHERE parent_id=?", (ctx.author.id,)) as cur:
            kids = await cur.fetchall()
    if not kids:
        return await ctx.send("No children.")
    msg = f"👶 {ctx.author.display_name}'s children:\n"
    for cid in kids:
        try:
            c = await bot.fetch_user(cid[0])
            msg += f"• {c.mention}\n"
        except:
            msg += f"• User {cid[0]}\n"
    await ctx.send(msg)

@bot.command(name="family")
@economy_check()
async def family(ctx):
    data = await get_user(ctx.author.id)
    spouse = data.get('spouse_id')
    parent = data.get('parent_id')
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT child_id FROM children WHERE parent_id=?", (ctx.author.id,)) as cur:
            kids = await cur.fetchall()
    msg = f"👨‍👩‍👧‍👦 **{ctx.author.display_name}'s Family**\n\n"
    if spouse:
        try:
            s = await bot.fetch_user(spouse)
            msg += f"💑 Spouse: {s.mention}\n"
        except:
            msg += f"💑 Spouse: User {spouse}\n"
    else:
        msg += "💑 Spouse: None\n"
    if parent:
        try:
            p = await bot.fetch_user(parent)
            msg += f"👪 Parent: {p.mention}\n"
        except:
            msg += f"👪 Parent: User {parent}\n"
    else:
        msg += "👪 Parent: None\n"
    if kids:
        msg += "\n👶 Children:\n"
        for cid in kids:
            try:
                c = await bot.fetch_user(cid[0])
                msg += f"• {c.mention}\n"
            except:
                msg += f"• User {cid[0]}\n"
    else:
        msg += "\n👶 Children: None"
    await ctx.send(msg)

@bot.command(name="leavefamily")
@economy_check()
async def leave_family(ctx):
    """Leave your parent family (if you are a child)."""
    data = await get_user(ctx.author.id)
    parent = data.get('parent_id')
    if not parent:
        return await ctx.send("❌ You don't have a parent to leave.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM children WHERE parent_id = ? AND child_id = ?", (parent, ctx.author.id))
        await db.execute("UPDATE users SET parent_id = NULL WHERE user_id = ?", (ctx.author.id,))
        await db.commit()
    await ctx.send(f"👋 You have left your family. You are no longer a child of <@{parent}>.")

@bot.command(name="pending")
@economy_check()
async def pending(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT id, from_id, request_type FROM requests WHERE to_id=?", (ctx.author.id,)) as cur:
            reqs = await cur.fetchall()
    if not reqs:
        return await ctx.send("No pending requests.")
    msg = "📬 Pending requests:\n"
    for rid, fid, rtype in reqs:
        try:
            u = await bot.fetch_user(fid)
            msg += f"`{rid}`: {u.mention} - {rtype}\n"
        except:
            msg += f"`{rid}`: User {fid} - {rtype}\n"
    await ctx.send(msg)

# ==================================================
# LEADERBOARDS (unchanged but use Python math)
# ==================================================
@bot.command(name="globalleaderboard", aliases=["glb"])
@economy_check()
async def glb(ctx, category: str = "money"):
    if category not in ("money","xp"):
        return await ctx.send("Usage: `.glb money` or `.glb xp`")
    async with aiosqlite.connect("hakari.db") as db:
        if category == "money":
            async with db.execute("SELECT user_id, CAST(money AS INTEGER) + CAST(bank AS INTEGER) as total FROM users ORDER BY total DESC LIMIT 10") as cur:
                rows = await cur.fetchall()
            title = "🌍 Global Richest"
        else:
            async with db.execute("SELECT user_id, total_xp FROM users ORDER BY total_xp DESC LIMIT 10") as cur:
                rows = await cur.fetchall()
            title = "🌍 Global Top XP"
    if not rows:
        return await ctx.send("No data yet.")
    msg = f"**{title}**\n\n"
    for i, (uid, val) in enumerate(rows, 1):
        try:
            u = await bot.fetch_user(uid)
            name = u.display_name
        except:
            name = f"User {uid}"
        suffix = " coins" if category=="money" else " XP"
        msg += f"{i}. {name}: {format_number(int(val))}{suffix}\n"
    await ctx.send(msg)

@bot.command(name="serverleaderboard", aliases=["slb"])
@economy_check()
async def slb(ctx, category: str = "money"):
    if category not in ("money","xp"):
        return await ctx.send("Usage: `.slb money` or `.slb xp`")
    members = [m for m in ctx.guild.members if not m.bot]
    data = []
    async with aiosqlite.connect("hakari.db") as db:
        for m in members:
            async with db.execute("SELECT CAST(money AS INTEGER), CAST(bank AS INTEGER), total_xp FROM users WHERE user_id=?", (m.id,)) as cur:
                row = await cur.fetchone()
            if row:
                if category=="money":
                    data.append((m, int(row[0]) + int(row[1])))
                else:
                    data.append((m, row[2]))
    data.sort(key=lambda x: x[1], reverse=True)
    top = data[:10]
    if not top:
        return await ctx.send("No data.")
    title = f"📊 Server {'Richest' if category=='money' else 'Top XP'} – {ctx.guild.name}"
    msg = f"**{title}**\n\n"
    for i, (m, val) in enumerate(top, 1):
        suffix = " coins" if category=="money" else " XP"
        msg += f"{i}. {m.display_name}: {format_number(val)}{suffix}\n"
    await ctx.send(msg)

@bot.command(name="topcouples")
@economy_check()
async def top_couples(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, spouse_id, affection FROM users WHERE spouse_id IS NOT NULL ORDER BY affection DESC LIMIT 10") as cur:
            rows = await cur.fetchall()
    if not rows:
        return await ctx.send("No couples.")
    msg = "💕 **Top Couples**\n\n"
    for i, (uid, sid, aff) in enumerate(rows, 1):
        try:
            u = await bot.fetch_user(uid)
            s = await bot.fetch_user(sid)
            msg += f"{i}. {u.display_name} & {s.display_name}: {format_number(aff)} ❤️\n"
        except:
            continue
    await ctx.send(msg)

@bot.command(name="level", aliases=["rank"])
@economy_check()
async def level(ctx):
    data = await get_user(ctx.author.id)
    lvl = data.get('level', 0)
    xp = data.get('total_xp', 0)
    next_xp = ((lvl+1)**2)*100
    needed = next_xp - xp
    if lvl == 0:
        bar_len = min(20, int(xp/100*20))
    else:
        prev_xp = (lvl**2)*100
        bar_len = min(20, int((xp-prev_xp)/(next_xp-prev_xp)*20))
    bar = "█"*bar_len + "░"*(20-bar_len)
    await ctx.send(f"📊 **{ctx.author.display_name}**\nLevel: {lvl}\nXP: {format_number(xp)} / {format_number(next_xp)}\nProgress: `{bar}`\nNeeded: {format_number(needed)} XP")

# ==================================================
# OWNER COMMANDS (with unlimited money)
# ==================================================
@bot.command(name="addmoney")
@owner_only()
async def addmoney(ctx, user: discord.User, amount_str: str):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount.")
    await update_money(user.id, amt)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Added {format_number(amt)}{emoji} to {user.mention}.")

@bot.command(name="removemoney")
@owner_only()
async def removemoney(ctx, user: discord.User, amount_str: str):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount.")
    cur = await get_user(user.id)
    total = cur['money'] + cur['bank']
    if total == 0:
        return await ctx.send(f"⚠️ {user.mention} has 0 coins total.")
    if amt > total:
        await update_money(user.id, -cur['money'])
        await update_bank(user.id, -cur['bank'])
        await ctx.send(f"⚠️ {user.mention} only had {format_number(total)} coins total. Removed all.")
    else:
        if cur['money'] >= amt:
            await update_money(user.id, -amt)
            removed_from = "wallet"
        else:
            await update_money(user.id, -cur['money'])
            remaining = amt - cur['money']
            await update_bank(user.id, -remaining)
            removed_from = f"wallet ({format_number(cur['money'])}) and bank ({format_number(remaining)})"
        emoji = await get_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"✅ Removed {format_number(amt)}{emoji} from {user.mention} (from {removed_from}).")

@bot.command(name="setmoney")
@owner_only()
async def setmoney(ctx, user: discord.User, amount_str: str):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = ? WHERE user_id = ?", (str(amt), user.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Set {user.mention}'s wallet to {format_number(amt)}{emoji}.")

@bot.command(name="addbank")
@owner_only()
async def addbank(ctx, user: discord.User, amount_str: str):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount.")
    await update_bank(user.id, amt)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Added {format_number(amt)}{emoji} to {user.mention}'s bank.")

@bot.command(name="removebank")
@owner_only()
async def removebank(ctx, user: discord.User, amount_str: str):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount.")
    cur = await get_user(user.id)
    if cur['bank'] < amt:
        await update_bank(user.id, -cur['bank'])
        await ctx.send(f"⚠️ {user.mention} only had {format_number(cur['bank'])} in bank. Removed all.")
    else:
        await update_bank(user.id, -amt)
        emoji = await get_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"✅ Removed {format_number(amt)}{emoji} from {user.mention}'s bank.")

@bot.command(name="avt")
@owner_only()
async def avt(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET tax_exempt = 1 - tax_exempt WHERE user_id = ?", (user.id,))
        await db.commit()
    data = await get_user(user.id)
    status = "enabled" if data.get('tax_exempt', 0) else "disabled"
    await ctx.send(f"✅ Tax exemption {status} for {user.mention}.")

@bot.command(name="addaffection")
@owner_only()
async def addaffection(ctx, user: discord.User, amount: int):
    await update_affection(user.id, amount)
    await ctx.send(f"✅ Added {amount} affection to {user.mention}.")
    await log_action(ctx.author.id, "AddAffection", f"{user.id} +{amount}")

@bot.command(name="setaffection")
@owner_only()
async def setaffection(ctx, user: discord.User, amount: int):
    await set_affection(user.id, amount)
    await ctx.send(f"✅ Set {user.mention}'s affection to {amount}.")
    await log_action(ctx.author.id, "SetAffection", f"{user.id} ={amount}")

@bot.command(name="rewardlast")
@owner_only()
async def reward_last(ctx, amount_str: str, count: int = 1):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount.")
    guild_id = ctx.guild.id
    if guild_id not in recent_message_authors:
        return await ctx.send("❌ No recent message data for this server.")
    dq = recent_message_authors[guild_id]
    seen = set()
    rewarded = []
    for uid in reversed(dq):
        if uid not in seen:
            seen.add(uid)
            rewarded.append(uid)
            if len(rewarded) == count:
                break
    if not rewarded:
        return await ctx.send("❌ No eligible users found.")
    async with aiosqlite.connect("hakari.db") as db:
        for uid in rewarded:
            async with db.execute("SELECT money FROM users WHERE user_id=?", (uid,)) as cur:
                row = await cur.fetchone()
            cur_money = int(row[0]) if row else 0
            new_money = cur_money + amt
            await db.execute("UPDATE users SET money = ? WHERE user_id = ?", (str(new_money), uid))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    mentions = ', '.join(f"<@{uid}>" for uid in rewarded)
    await ctx.send(f"✅ Added {format_number(amt)}{emoji} to the last {len(rewarded)} message authors: {mentions}")

@bot.command(name="addowner")
@owner_only()
@main_owner_only()
async def addowner(ctx, user_id: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO owners (user_id, is_main) VALUES (?,0)", (user_id,))
        await db.commit()
    await ctx.send(f"✅ Added <@{user_id}> as owner.")

@bot.command(name="removeowner")
@owner_only()
@main_owner_only()
async def removeowner(ctx, user_id: int):
    if user_id == MAIN_OWNER_ID:
        return await ctx.send("❌ Cannot remove main owner.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM owners WHERE user_id=?", (user_id,))
        await db.commit()
    await ctx.send(f"✅ Removed <@{user_id}> from owners.")

@bot.command(name="ownerlist")
@owner_only()
async def ownerlist(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, is_main FROM owners") as cur:
            rows = await cur.fetchall()
    if not rows:
        return await ctx.send("No owners.")
    msg = "👑 **Bot Owners**\n\n"
    for uid, main in rows:
        msg += f"• <@{uid}> – {'Main Owner' if main else 'Owner'}\n"
    await ctx.send(msg)

@bot.command(name="protect")
@owner_only()
async def protect(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET protected = 1 WHERE user_id=?", (user.id,))
        await db.commit()
    await ctx.send(f"🛡️ {user.mention} is now protected from robbery.")

@bot.command(name="unprotect")
@owner_only()
async def unprotect(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET protected = 0 WHERE user_id=?", (user.id,))
        await db.commit()
    await ctx.send(f"✅ {user.mention} is no longer protected.")

@bot.command(name="blacklist")
@owner_only()
async def blacklist(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET blacklisted = 1 WHERE user_id=?", (user.id,))
        await db.commit()
    await ctx.send(f"⛔ {user.mention} has been blacklisted.")

@bot.command(name="whitelist")
@owner_only()
async def whitelist(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET blacklisted = 0 WHERE user_id=?", (user.id,))
        await db.commit()
    await ctx.send(f"✅ {user.mention} has been whitelisted.")

@bot.command(name="economywipe")
@owner_only()
async def economywipe(ctx):
    await ctx.send("⚠️ Type `confirm` within 30 seconds to wipe all money and bank.")
    def check(m): return m.author == ctx.author and m.content.lower() == "confirm"
    try:
        await bot.wait_for("message", timeout=30, check=check)
    except:
        return await ctx.send("❌ Cancelled.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = '0', bank = '0'")
        await db.commit()
    await ctx.send("✅ Economy wiped.")

@bot.command(name="toggleeconomy")
@owner_only()
async def toggle_economy(ctx):
    cur = await get_setting(ctx.guild.id, "economy_enabled")
    new = 0 if cur else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, economy_enabled) VALUES (?,?)", (ctx.guild.id, new))
        await db.commit()
    await ctx.send(f"✅ Economy {'enabled' if new else 'disabled'}.")

@bot.command(name="togglerob")
@owner_only()
async def toggle_rob(ctx):
    cur = await get_setting(ctx.guild.id, "rob_enabled")
    new = 0 if cur else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, rob_enabled) VALUES (?,?)", (ctx.guild.id, new))
        await db.commit()
    await ctx.send(f"✅ Rob {'enabled' if new else 'disabled'}.")

@bot.command(name="togglegambling")
@owner_only()
async def toggle_gambling(ctx):
    cur = await get_setting(ctx.guild.id, "gambling_enabled")
    new = 0 if cur else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, gambling_enabled) VALUES (?,?)", (ctx.guild.id, new))
        await db.commit()
    await ctx.send(f"✅ Gambling {'enabled' if new else 'disabled'}.")

@bot.command(name="setdailyamount")
@owner_only()
async def setdaily(ctx, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, daily_amount) VALUES (?,?)", (ctx.guild.id, amount))
        await db.commit()
    await ctx.send(f"✅ Daily reward set to {format_number(amount)} coins.")

@bot.command(name="setcurrency")
@owner_only()
async def setcurrency(ctx, emoji: str):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, currency_emoji) VALUES (?,?)", (ctx.guild.id, emoji))
        await db.commit()
    await ctx.send(f"✅ Currency emoji set to {emoji}.")

@bot.command(name="logs")
@owner_only()
async def logs(ctx, limit: int = 10):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT timestamp, user_id, action, details FROM logs ORDER BY id DESC LIMIT ?", (min(limit,20),)) as cur:
            rows = await cur.fetchall()
    if not rows:
        return await ctx.send("No logs.")
    msg = "📜 **Recent Logs**\n\n"
    for ts, uid, act, det in rows:
        msg += f"• {ts[:16]} – <@{uid}>: {act} {det}\n"
        if len(msg) > 1900:
            break
    await ctx.send(msg)

# ==================================================
# EVENTS
# ==================================================
@bot.event
async def on_ready():
    await init_db()
    loan_interest.start()
    bank_interest.start()
    print(f"✅ {bot.user} is ready (unlimited money).")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    guild_id = message.guild.id if message.guild else None
    if guild_id:
        if guild_id not in recent_message_authors:
            recent_message_authors[guild_id] = deque(maxlen=100)
        recent_message_authors[guild_id].append(message.author.id)

    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.author.id,))
        await db.execute("UPDATE users SET daily_messages = daily_messages + 1 WHERE user_id = ?", (message.author.id,))
        await db.commit()
    new_lvl = await add_xp(message.author.id, random.randint(10,20))
    if new_lvl:
        lvl_msg = await message.channel.send(f"🎉 {message.author.mention} leveled up to level {new_lvl}!")
        await asyncio.sleep(5)
        try:
            await lvl_msg.delete()
        except discord.NotFound:
            pass
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"Error: {error}")

if __name__ == "__main__":
    asyncio.run(bot.start(TOKEN))
