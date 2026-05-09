import discord
from discord.ext import commands, tasks
import aiosqlite
import json
import random
import asyncio
from datetime import datetime, timedelta
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

# ==================================================
# REMOVE DEFAULT HELP COMMAND FIRST - THIS FIXES THE ERROR!
# ==================================================
bot.remove_command('help')

# ==================================================
# HELPER FUNCTIONS
# ==================================================
def parse_amount(amount_str: str):
    if amount_str.lower() == "all":
        return "all"
    amount_str = amount_str.lower().strip()
    if amount_str.endswith('k'):
        return int(float(amount_str[:-1]) * 1000)
    elif amount_str.endswith('m'):
        return int(float(amount_str[:-1]) * 1_000_000)
    elif amount_str.endswith('b'):
        return int(float(amount_str[:-1]) * 1_000_000_000)
    else:
        return int(float(amount_str))

def format_number(num: int) -> str:
    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.1f}b".replace('.0b', 'b')
    elif num >= 1_000_000:
        return f"{num/1_000_000:.1f}m".replace('.0m', 'm')
    elif num >= 1_000:
        return f"{num/1_000:.1f}k".replace('.0k', 'k')
    else:
        return str(num)

async def is_family_member(user_id: int, target_id: int) -> bool:
    user = await get_user(user_id)
    target = await get_user(target_id)
    if user[17] == target_id or target[17] == user_id:
        return True
    if user[18] == target_id or target[18] == user_id:
        return True
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM children WHERE parent_id=? AND child_id=?", (user_id, target_id)) as cur:
            if await cur.fetchone():
                return True
        async with db.execute("SELECT 1 FROM children WHERE parent_id=? AND child_id=?", (target_id, user_id)) as cur:
            if await cur.fetchone():
                return True
    return False

# ==================================================
# DATABASE SETUP
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
            money INTEGER DEFAULT 0,
            bank INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            total_xp INTEGER DEFAULT 0,
            protected INTEGER DEFAULT 0,
            blacklisted INTEGER DEFAULT 0,
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
            loan_amount INTEGER DEFAULT 0,
            loan_taken_at TIMESTAMP
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
            last_collected TIMESTAMP
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
            max_withdraw INTEGER DEFAULT 50000,
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
    print("✅ Database ready.")

# ==================================================
# BACKGROUND TASKS
# ==================================================
@tasks.loop(hours=1)
async def loan_interest():
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, loan_amount FROM users WHERE loan_amount > 0") as cur:
            rows = await cur.fetchall()
        for uid, loan in rows:
            new_loan = int(loan * 1.10)
            await db.execute("UPDATE users SET loan_amount = ? WHERE user_id = ?", (new_loan, uid))
        await db.commit()
    print("✅ Loan interest added")

@loan_interest.before_loop
async def before_loan():
    await bot.wait_until_ready()

@tasks.loop(hours=24)
async def bank_interest():
    async with aiosqlite.connect("hakari.db") as db:
        rate = 5
        async with db.execute("SELECT user_id, bank, last_interest FROM users WHERE bank > 0") as cur:
            rows = await cur.fetchall()
        for uid, bank, last in rows:
            if last:
                last_dt = datetime.fromisoformat(last)
                if datetime.utcnow() - last_dt < timedelta(hours=20):
                    continue
            earning = min(bank, 50000)
            interest = int(earning * rate / 100)
            if interest:
                await db.execute("UPDATE users SET bank = bank + ?, last_interest = ? WHERE user_id = ?",
                                 (interest, datetime.utcnow().isoformat(), uid))
        await db.commit()
    print("✅ Bank interest added")

@bank_interest.before_loop
async def before_bank():
    await bot.wait_until_ready()

# ==================================================
# DATABASE ACCESS HELPERS
# ==================================================
async def get_user(user_id: int):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return row
            await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur2:
                return await cur2.fetchone()

async def update_money(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def update_bank(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET bank = bank + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def log_action(user_id: int, action: str, details: str = ""):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO logs (timestamp, user_id, action, details) VALUES (?, ?, ?, ?)",
                         (datetime.utcnow().isoformat(), user_id, action, details))
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
        "interest_rate": 5, "max_withdraw": 50000,
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
    return u[7] == 1

async def is_protected(user_id: int) -> bool:
    u = await get_user(user_id)
    return u[6] == 1

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
        amount = data[1]
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return None, "❌ Invalid amount. Use numbers like 500, 1k, 2.5m, or 'all'."
    if amount <= 0:
        return None, "❌ Amount must be positive."
    if check_balance and data[1] < amount:
        return None, f"❌ You only have {format_number(data[1])} coins."
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
        if sender_data[1] < self.amount:
            await interaction.response.edit_message(content=f"❌ You no longer have enough coins.", view=None)
            self.completed = True
            return
        view2 = PaymentAcceptView(self.sender, self.recipient, self.amount, self.emoji)
        embed = discord.Embed(title="💸 Payment Request", color=discord.Color.blue())
        embed.add_field(name="From", value=self.sender.mention, inline=True)
        embed.add_field(name="Amount", value=f"{format_number(self.amount)}{self.emoji}", inline=True)
        embed.add_field(name="⏱️ Time", value="60 seconds", inline=True)
        await interaction.response.edit_message(content=f"✅ You confirmed. Waiting for {self.recipient.mention} to accept...", view=None)
        await interaction.channel.send(f"{self.recipient.mention}, {self.sender.mention} wants to send you {format_number(self.amount)}{self.emoji}. Do you accept?", embed=embed, view=view2)
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

class PaymentAcceptView(discord.ui.View):
    def __init__(self, sender, recipient, amount, emoji):
        super().__init__(timeout=60)
        self.sender = sender
        self.recipient = recipient
        self.amount = amount
        self.emoji = emoji
        self.completed = False

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction, button):
        if interaction.user.id != self.recipient.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        sender_data = await get_user(self.sender.id)
        if sender_data[1] < self.amount:
            await interaction.response.edit_message(content=f"❌ {self.sender.mention} no longer has enough coins.", view=None)
            self.completed = True
            return
        await update_money(self.sender.id, -self.amount)
        await update_money(self.recipient.id, self.amount)
        await interaction.response.edit_message(content=f"✅ {self.sender.mention} paid {format_number(self.amount)}{self.emoji} to {self.recipient.mention}!", view=None)
        self.completed = True
        self.stop()

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction, button):
        if interaction.user.id != self.recipient.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        await interaction.response.edit_message(content=f"❌ {self.recipient.mention} declined the payment.", view=None)
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
# HELP MENU
# ==================================================
class HelpView(discord.ui.View):
    def __init__(self, ctx, pages):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.pages = pages
        self.page = 0

    async def update(self, inter):
        await inter.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
    async def prev(self, inter, btn):
        if inter.user != self.ctx.author:
            return await inter.response.send_message("Not your menu!", ephemeral=True)
        self.page = (self.page - 1) % len(self.pages)
        await self.update(inter)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def nxt(self, inter, btn):
        if inter.user != self.ctx.author:
            return await inter.response.send_message("Not your menu!", ephemeral=True)
        self.page = (self.page + 1) % len(self.pages)
        await self.update(inter)

    @discord.ui.button(label="❌", style=discord.ButtonStyle.danger)
    async def close(self, inter, btn):
        if inter.user != self.ctx.author:
            return await inter.response.send_message("Not your menu!", ephemeral=True)
        await inter.message.delete()

@bot.command(name="cmds", aliases=["commands"])
async def help_cmd(ctx):
    owner = await is_owner(ctx.author.id)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    pages = [
        discord.Embed(title="💰 Economy (1/6)", color=discord.Color.blue()).add_field(
            name="Commands", value=f"`.bal` – balance\n`.daily` – {emoji}1500 (10 msg)\n`.work` – {emoji}150-300 (5m)\n`.sleep` – {emoji}2000-2500 (8h)\n`.crime` – {emoji}200-800 (15m)\n`.deposit <all/1k>`\n`.withdraw <all/1k>` (max 50k)\n`.pay @user <amount/all>`\n`.rob @user` (1h)\n`.interest`", inline=False),
        discord.Embed(title="🏦 Loans (2/6)", color=discord.Color.purple()).add_field(
            name="Commands", value="`.loan <amount>`\n`.repay <all/half/amount>`\n`.loaninfo`", inline=False),
        discord.Embed(title="🎰 Gambling (3/6)", color=discord.Color.gold()).add_field(
            name="Games", value="`.cf <amount> [heads/tails]`\n`.slots <amount>`\n`.bj <amount>`\n`.crash <amount>`\n`.mines <amount> <mines>` (1‑19)\n`.tower <amount> <floors>` (3‑12)", inline=False),
        discord.Embed(title="🛒 Shop & Business (4/6)", color=discord.Color.green()).add_field(
            name="Commands", value="`.createshop <name>`\n`.addshopitem <price> <item>`\n`.removeshopitem <item>`\n`.myshop`\n`.visitshop @user`\n`.buyfromshop @user <item>`\n`.closeshop`\n`.globalmarket`\n`.buybusiness <type>`\n`.business`\n`.upgradebusiness`\n`.collectprofits`\n`.sellbusiness`", inline=False),
        discord.Embed(title="💕 Relationships (5/6)", color=discord.Color.pink()).add_field(
            name="Commands", value="`.date @user`\n`.marry @user`\n`.divorce`\n`.affection`\n`.gift @user <amount>`\n`.adopt @user`\n`.children`\n`.family`\n`.pending`", inline=False),
        discord.Embed(title="📊 Leaderboards (6/6)", color=discord.Color.purple()).add_field(
            name="Commands", value="`.glb money` / `.glb xp`\n`.slb money` / `.slb xp`\n`.topcouples`\n`.level`", inline=False),
    ]
    if owner:
        pages.append(discord.Embed(title="👑 Owner (7/7)", color=discord.Color.red()).add_field(
            name="Commands", value="`.addowner <id>`\n`.removeowner <id>`\n`.ownerlist`\n`.addmoney @user <amount>`\n`.removemoney @user <amount>`\n`.setmoney @user <amount>`\n`.addbank @user <amount>`\n`.removebank @user <amount>`\n`.protect @user`\n`.unprotect @user`\n`.blacklist @user`\n`.whitelist @user`\n`.economywipe`\n`.toggleeconomy` / `.togglerob` / `.togglegambling`\n`.setdailyamount`\n`.setcurrency`\n`.logs`", inline=False))
    await ctx.send(embed=pages[0], view=HelpView(ctx, pages))

# ==================================================
# ECONOMY COMMANDS
# ==================================================
@bot.command(name="balance", aliases=["bal"])
@economy_check()
async def balance(ctx, user: discord.User = None):
    target = user or ctx.author
    data = await get_user(target.id)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    embed = discord.Embed(title=f"{target.display_name}'s Balance", color=discord.Color.teal())
    embed.add_field(name="Wallet", value=f"{format_number(data[1])}{emoji}", inline=True)
    embed.add_field(name="Bank", value=f"{format_number(data[2])}{emoji}", inline=True)
    embed.add_field(name="Total", value=f"{format_number(data[1]+data[2])}{emoji}", inline=True)
    if data[22] > 0:
        embed.add_field(name="⚠️ Loan", value=f"{format_number(data[22])}{emoji}", inline=True)
    await ctx.send(embed=embed)

@bot.command(name="daily")
@economy_check()
async def daily(ctx):
    data = await get_user(ctx.author.id)
    if data[8]:
        last = datetime.fromisoformat(data[8])
        if datetime.utcnow() - last < timedelta(hours=24):
            remain = timedelta(hours=24) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Already claimed. Try again in {remain.seconds//3600}h.")
    needed = await get_setting(ctx.guild.id, "daily_messages_needed")
    if data[13] < needed:
        return await ctx.send(f"❌ You need {needed - data[13]} more messages today.")
    amount = await get_setting(ctx.guild.id, "daily_amount")
    await update_money(ctx.author.id, amount)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_daily = ?, daily_messages = 0 WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Daily reward: +{format_number(amount)}{emoji}")

@bot.command(name="work")
@economy_check()
async def work(ctx):
    data = await get_user(ctx.author.id)
    if data[9]:
        last = datetime.fromisoformat(data[9])
        if datetime.utcnow() - last < timedelta(minutes=5):
            remain = timedelta(minutes=5) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Wait {remain.seconds//60}m {remain.seconds%60}s.")
    min_amt = await get_setting(ctx.guild.id, "work_amount_min")
    max_amt = await get_setting(ctx.guild.id, "work_amount_max")
    earn = random.randint(min_amt, max_amt)
    await update_money(ctx.author.id, earn)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_work = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"💼 Worked and earned {format_number(earn)}{emoji}!")

@bot.command(name="sleep")
@economy_check()
async def sleep(ctx):
    data = await get_user(ctx.author.id)
    if data[11]:
        last = datetime.fromisoformat(data[11])
        if datetime.utcnow() - last < timedelta(hours=8):
            remain = timedelta(hours=8) - (datetime.utcnow() - last)
            return await ctx.send(f"😴 Not tired. Try again in {remain.seconds//3600}h.")
    min_amt = await get_setting(ctx.guild.id, "sleep_amount_min")
    max_amt = await get_setting(ctx.guild.id, "sleep_amount_max")
    earn = random.randint(min_amt, max_amt)
    await update_money(ctx.author.id, earn)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_sleep = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"😴 You slept and woke up with {format_number(earn)}{emoji}!")

@bot.command(name="crime")
@economy_check()
async def crime(ctx):
    data = await get_user(ctx.author.id)
    if data[12]:
        last = datetime.fromisoformat(data[12])
        if datetime.utcnow() - last < timedelta(minutes=15):
            remain = timedelta(minutes=15) - (datetime.utcnow() - last)
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
        if data[1] >= fine:
            await update_money(ctx.author.id, -fine)
            await ctx.send(f"🚔 Caught! Lost {format_number(fine)}{emoji}.")
        else:
            await ctx.send("🚔 Caught! You went to jail.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_crime = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()

@bot.command(name="deposit")
@economy_check()
async def deposit(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    if amount_str.lower() == "all":
        amount = data[1]
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return await ctx.send("❌ Invalid amount.")
    if amount <= 0 or amount > data[1]:
        return await ctx.send(f"❌ You have {format_number(data[1])} coins.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = money - ?, bank = bank + ? WHERE user_id = ?", (amount, amount, ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Deposited {format_number(amount)}{emoji}.")

@bot.command(name="withdraw", aliases=["with"])
@economy_check()
async def withdraw(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    max_wd = await get_setting(ctx.guild.id, "max_withdraw")
    if amount_str.lower() == "all":
        amount = min(data[2], max_wd)
        if data[2] > max_wd:
            await ctx.send(f"⚠️ Max withdraw {format_number(max_wd)}. Withdrawing {format_number(amount)}.")
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return await ctx.send("❌ Invalid amount.")
    if amount <= 0:
        return
    if amount > max_wd:
        return await ctx.send(f"❌ Max withdraw is {format_number(max_wd)} per transaction.")
    if amount > data[2]:
        return await ctx.send(f"❌ You have {format_number(data[2])} in bank.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = money + ?, bank = bank - ? WHERE user_id = ?", (amount, amount, ctx.author.id))
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
            sdata = await get_user(ctx.author.id)
            amount = sdata[1]
        else:
            amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount.")
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive.")
    sender_data = await get_user(ctx.author.id)
    if sender_data[1] < amount:
        return await ctx.send(f"❌ You have {format_number(sender_data[1])} coins.")
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
    if tdata[1] < 100:
        return await ctx.send(f"❌ {target.mention} is too poor.")
    data = await get_user(ctx.author.id)
    if data[10]:
        last = datetime.fromisoformat(data[10])
        if datetime.utcnow() - last < timedelta(hours=1):
            remain = timedelta(hours=1) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Wait {remain.seconds//3600}h {(remain.seconds%3600)//60}m.")
    percent = random.uniform(1, 15)
    steal = int(tdata[1] * (percent / 100))
    steal = max(50, min(steal, tdata[1]))
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await update_money(target.id, -steal)
    await update_money(ctx.author.id, steal)
    await ctx.send(f"✅ Robbed {target.mention} for {format_number(steal)}{emoji} ({percent:.1f}% of their wallet).")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_rob = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()

@bot.command(name="interest")
@economy_check()
async def interest(ctx):
    rate = await get_setting(ctx.guild.id, "interest_rate")
    data = await get_user(ctx.author.id)
    bank = data[2]
    earn = min(bank, 50000)
    daily = int(earn * rate / 100)
    embed = discord.Embed(title="🏦 Bank Interest", color=discord.Color.gold())
    embed.add_field(name="Rate", value=f"{rate}% daily", inline=True)
    embed.add_field(name="Your Bank", value=f"{format_number(bank)}", inline=True)
    embed.add_field(name="Daily Interest", value=f"{format_number(daily)}", inline=True)
    await ctx.send(embed=embed)

# ==================================================
# LOAN COMMANDS
# ==================================================
@bot.command(name="loan")
@economy_check()
async def loan(ctx, amount_str: str):
    try:
        amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount (e.g., 500, 1k).")
    if amount <= 0:
        return
    data = await get_user(ctx.author.id)
    if data[22] > 0:
        return await ctx.send(f"❌ You already have a loan of {format_number(data[22])}. Repay first with `.repay all`.")
    if data[23]:
        last = datetime.fromisoformat(data[23])
        if datetime.utcnow() - last < timedelta(hours=1):
            remain = timedelta(hours=1) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ You just took a loan. Try again in {remain.seconds//60}m.")
    rate = await get_setting(ctx.guild.id, "loan_interest")
    await update_money(ctx.author.id, amount)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET loan_amount = ?, loan_taken_at = ? WHERE user_id = ?", (amount, datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"🏦 Loan approved! +{format_number(amount)}{emoji}. Interest: {rate}% per hour. Repay with `.repay`")

@bot.command(name="repay")
@economy_check()
async def repay(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    loan = data[22]
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
    if amount <= 0:
        return
    if data[1] < amount:
        return await ctx.send(f"❌ You have {format_number(data[1])} coins.")
    new_loan = loan - amount
    if new_loan < 0:
        new_loan = 0
    await update_money(ctx.author.id, -amount)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET loan_amount = ? WHERE user_id = ?", (new_loan, ctx.author.id))
        if new_loan == 0:
            await db.execute("UPDATE users SET loan_taken_at = NULL WHERE user_id = ?", (ctx.author.id,))
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
    loan = data[22]
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if loan <= 0:
        embed = discord.Embed(title="🏦 Loan Status", color=discord.Color.green())
        embed.add_field(name="Active Loan", value="None", inline=False)
        embed.add_field(name="How to get a loan", value="`.loan <amount>`", inline=False)
        await ctx.send(embed=embed)
    else:
        taken = data[23]
        if taken:
            taken_dt = datetime.fromisoformat(taken)
            hours = (datetime.utcnow() - taken_dt).total_seconds() / 3600
            total = int(loan * (1.10 ** hours))
        else:
            total = loan
        embed = discord.Embed(title="🏦 Loan Status", color=discord.Color.red())
        embed.add_field(name="Original", value=f"{format_number(loan)}{emoji}", inline=True)
        embed.add_field(name="Current Due", value=f"{format_number(total)}{emoji}", inline=True)
        embed.add_field(name="Interest", value="10% per hour", inline=True)
        await ctx.send(embed=embed)

# ==================================================
# BLACKJACK
# ==================================================
class BlackjackView(discord.ui.View):
    def __init__(self, ctx, bet, player, dealer):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.bet = bet
        self.player = player
        self.dealer = dealer
        self.emoji = None
        self.ended = False
        self.start = datetime.utcnow()

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
        remain = 120 - (datetime.utcnow() - self.start).total_seconds()
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
            msg = f"✅ You won {format_number(win)}{self.emoji}!"
        elif result == "lose":
            msg = f"❌ You lost {format_number(self.bet)}{self.emoji}!"
        elif result == "push":
            await update_money(self.ctx.author.id, self.bet)
            msg = "🤝 Push! Money returned."
        elif result == "blackjack":
            w = int(self.bet * 2.5)
            await update_money(self.ctx.author.id, w)
            msg = f"🎉 BLACKJACK! Won {format_number(w)}{self.emoji}!"
        else:
            msg = f"⏰ Timeout! Lost {format_number(self.bet)}{self.emoji}."
        embed = discord.Embed(title="Game Over", color=0xe74c3c)
        embed.add_field(name="Result", value=msg, inline=False)
        await self.ctx.send(embed=embed)
        self.ended = True
        self.stop()

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
            await self.end_game("win", self.bet*2)
        elif pv < dv:
            await self.end_game("lose")
        else:
            await self.end_game("push")
        await inter.message.delete()

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.danger)
    async def double(self, inter, btn):
        if inter.user != self.ctx.author:
            return
        self.bet *= 2
        self.player.append(random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11]))
        if await self.hand_value(self.player) > 21:
            await self.end_game("lose")
            await inter.message.delete()
            return
        await self.stand.callback(inter, btn)

    async def on_timeout(self):
        if not self.ended:
            await self.end_game("timeout")

@bot.command(name="bj", aliases=["blackjack"])
@economy_check()
async def blackjack(ctx, amount_str: str):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return await ctx.send("❌ Gambling disabled.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    cards = [2,3,4,5,6,7,8,9,10,10,10,10,11]
    player = [random.choice(cards), random.choice(cards)]
    dealer = [random.choice(cards), random.choice(cards)]
    pv = sum(player)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if pv == 21:
        win = int(amount * 2.5)
        await update_money(ctx.author.id, win)
        await ctx.send(f"🎉 BLACKJACK! Won {format_number(win)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        view = BlackjackView(ctx, amount, player, dealer)
        view.emoji = emoji
        embed = await view.embed_game()
        await ctx.send(embed=embed, view=view)

# ==================================================
# MINES (fixed - requires at least 1 reveal to cashout)
# ==================================================
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
        self.start = datetime.utcnow()
        for i in range(20):
            btn = discord.ui.Button(label="⬛", style=discord.ButtonStyle.secondary, row=i//5, custom_id=f"m{i}")
            btn.callback = self.make_callback(i)
            self.add_item(btn)
        self.cashout = discord.ui.Button(label="💰 Cashout", style=discord.ButtonStyle.success, row=4)
        self.cashout.callback = self.cashout_cb
        self.add_item(self.cashout)
        self.quit = discord.ui.Button(label="❌ Quit", style=discord.ButtonStyle.danger, row=4)
        self.quit.callback = self.quit_cb
        self.add_item(self.quit)

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
                await update_money(self.ctx.author.id, -self.bet)
                self.stop()
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
                remain = 120 - (datetime.utcnow() - self.start).total_seconds()
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
        await inter.response.edit_message(content=f"💰 Cashed out! Won {format_number(win)}{self.emoji}!", view=None)
        self.ended = True
        self.stop()

    async def quit_cb(self, inter):
        if inter.user != self.ctx.author or self.ended:
            return
        await inter.response.edit_message(content=f"❌ You quit. Lost {format_number(self.bet)}{self.emoji}.", view=None)
        self.ended = True
        self.stop()

    async def on_timeout(self):
        if not self.ended:
            await self.ctx.send(f"⏰ {self.ctx.author.mention} took too long! Lost {format_number(self.bet)}{self.emoji}.")

@bot.command(name="mines")
@economy_check()
async def mines_cmd(ctx, amount_str: str, mines: int = 5):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return await ctx.send("❌ Gambling disabled.")
    if mines < 1 or mines > 19:
        return await ctx.send("❌ Mines must be 1‑19.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
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
    await update_money(ctx.author.id, -amount)

# ==================================================
# OTHER GAMBLING
# ==================================================
@bot.command(name="cf", aliases=["coinflip"])
@economy_check()
async def coinflip(ctx, amount_str: str, choice: str = None):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    if choice and choice.lower() not in ("heads","tails"):
        return await ctx.send("❌ Choose heads or tails.")
    result = random.choice(["heads","tails"])
    win = (choice and choice.lower() == result) or (not choice and random.choice([True,False]))
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if win:
        await update_money(ctx.author.id, amount)
        await ctx.send(f"🪙 Coin landed on **{result}**! You won {format_number(amount)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        await ctx.send(f"🪙 Coin landed on **{result}**! You lost {format_number(amount)}{emoji}.")

@bot.command(name="slots")
@economy_check()
async def slots(ctx, amount_str: str):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    emojis = ["🍒","🍋","🍊","🍉","⭐","💎"]
    r = [random.choice(emojis) for _ in range(3)]
    mult = 0
    if r[0]==r[1]==r[2]:
        mult = 3 if r[0]=="💎" else 2
    elif r[0]==r[1] or r[1]==r[2] or r[0]==r[2]:
        mult = 0.5
    win = int(amount * mult)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if win > amount:
        await update_money(ctx.author.id, win)
        await ctx.send(f"🎰 `[{r[0]}] [{r[1]}] [{r[2]}]`\n🎉 JACKPOT! Won {format_number(win)}{emoji}!")
    elif mult > 0:
        await update_money(ctx.author.id, win)
        await ctx.send(f"🎰 `[{r[0]}] [{r[1]}] [{r[2]}]`\n✅ Won {format_number(win)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        await ctx.send(f"🎰 `[{r[0]}] [{r[1]}] [{r[2]}]`\n❌ Lost {format_number(amount)}{emoji}.")

@bot.command(name="crash")
@economy_check()
async def crash(ctx, amount_str: str):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    mult = round(random.uniform(1.01, 100), 2)
    if random.random() < 0.5:
        win = int(amount * mult)
        await update_money(ctx.author.id, win)
        await ctx.send(f"📈 Crash at {mult}x! Won {format_number(win)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        await ctx.send(f"💥 Crashed at {mult}x! Lost {format_number(amount)}{emoji}.")

@bot.command(name="tower")
@economy_check()
async def tower(ctx, amount_str: str, floors: int = 5):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return
    if floors < 3 or floors > 12:
        return await ctx.send("❌ Floors must be 3‑12.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    mult = round(1.5 ** floors, 2)
    if random.random() < (0.9 - floors*0.03):
        win = int(amount * mult)
        await update_money(ctx.author.id, win)
        await ctx.send(f"🏗️ Tower ({floors} floors) – Reached top! Won {format_number(win)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        await ctx.send(f"🏗️ CRASH at floor {random.randint(2,floors)}! Lost {format_number(amount)}{emoji}.")

# ==================================================
# SHOP & BUSINESS
# ==================================================
@bot.command(name="createshop")
@economy_check()
async def create_shop(ctx, *, name: str):
    data = await get_user(ctx.author.id)
    if data[14]:
        return await ctx.send("❌ You already have a shop.")
    if len(name) > 50:
        return await ctx.send("❌ Name too long.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_name = ?, shop_open = 1 WHERE user_id = ?", (name, ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Shop '{name}' created. Use `.addshopitem <price> <item>`.")

@bot.command(name="addshopitem")
@economy_check()
async def add_shop_item(ctx, price: int, *, item: str):
    if price <= 0:
        return
    data = await get_user(ctx.author.id)
    if not data[14]:
        return await ctx.send("❌ No shop.")
    if not data[16]:
        return await ctx.send("❌ Shop closed. Use `.closeshop` to open.")
    items = json.loads(data[15]) if data[15] else {}
    if len(items) >= 20:
        return await ctx.send("❌ Shop full (20 items max).")
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
    if not data[14]:
        return
    items = json.loads(data[15]) if data[15] else {}
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
    if not data[14]:
        return await ctx.send("❌ No shop.")
    items = json.loads(data[15]) if data[15] else {}
    status = "Open" if data[16] else "Closed"
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    msg = f"🏪 **{data[14]}** ({status})\n\n"
    if items:
        for it, pr in items.items():
            msg += f"• {it}: {format_number(pr)}{emoji}\n"
    else:
        msg += "No items for sale."
    await ctx.send(msg)

@bot.command(name="closeshop")
@economy_check()
async def close_shop(ctx):
    data = await get_user(ctx.author.id)
    if not data[14]:
        return
    new = 0 if data[16] else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_open = ? WHERE user_id = ?", (new, ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Shop is now {'open' if new else 'closed'}.")

@bot.command(name="buyfromshop")
@economy_check()
async def buy_from_shop(ctx, seller: discord.User, *, item: str):
    sdata = await get_user(seller.id)
    if not sdata[14] or not sdata[16]:
        return await ctx.send(f"❌ {seller.display_name}'s shop is not open.")
    items = json.loads(sdata[15]) if sdata[15] else {}
    if item not in items:
        return await ctx.send("❌ Item not found.")
    price = items[item]
    bdata = await get_user(ctx.author.id)
    if bdata[1] < price:
        return await ctx.send(f"❌ You need {format_number(price)} coins.")
    await update_money(ctx.author.id, -price)
    await update_money(seller.id, price)
    del items[item]
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), seller.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Bought '{item}' for {format_number(price)}{emoji}.")

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

@bot.command(name="buybusiness")
@economy_check()
async def buy_business(ctx, biz_type: str):
    types = ["restaurant","casino","cafe"]
    if biz_type.lower() not in types:
        return await ctx.send(f"❌ Choose from: {', '.join(types)}")
    data = await get_user(ctx.author.id)
    cost = 1000
    if data[1] < cost:
        return await ctx.send(f"❌ Need {format_number(cost)} coins.")
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            if await cur.fetchone():
                return await ctx.send("❌ You already own a business.")
        await update_money(ctx.author.id, -cost)
        await db.execute("INSERT INTO businesses (user_id, business_type, level, last_collected) VALUES (?,?,?,?)",
                         (ctx.author.id, biz_type.lower(), 1, datetime.utcnow().isoformat()))
        await db.commit()
    await ctx.send(f"✅ Bought a {biz_type} business!")

@bot.command(name="business")
@economy_check()
async def business_info(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT business_type, level FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return await ctx.send("❌ No business.")
    biz, lvl = row
    await ctx.send(f"🏪 **{biz}**\nLevel: {lvl}\nIncome: {format_number(50*lvl)} coins/hour")

@bot.command(name="upgradebusiness")
@economy_check()
async def upgrade_business(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return
    lvl = row[0]
    cost = 500 * lvl
    data = await get_user(ctx.author.id)
    if data[1] < cost:
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
        async with db.execute("SELECT level, last_collected FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return
    lvl, last = row
    now = datetime.utcnow()
    last_dt = datetime.fromisoformat(last)
    hours = (now - last_dt).total_seconds() / 3600
    if hours < 1:
        remain = 3600 - (now - last_dt).total_seconds()
        return await ctx.send(f"⏰ Next collection in {int(remain//60)} minutes.")
    profit = int(50 * lvl * min(hours, 24))
    await update_money(ctx.author.id, profit)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE businesses SET last_collected = ? WHERE user_id=?", (now.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Collected {format_number(profit)}{emoji}!")

@bot.command(name="sellbusiness")
@economy_check()
async def sell_business(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return
    value = 500 * row[0]
    await update_money(ctx.author.id, value)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM businesses WHERE user_id=?", (ctx.author.id,))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Sold business for {format_number(value)}{emoji}.")

# ==================================================
# RELATIONSHIP COMMANDS
# ==================================================
@bot.command(name="date")
@economy_check()
async def date(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("❌ Can't date yourself.")
    if await is_family_member(ctx.author.id, user.id):
        return await ctx.send("❌ You cannot date a family member.")
    data = await get_user(ctx.author.id)
    if data[17]:
        return await ctx.send("❌ You are already married. Divorce first.")
    if data[1] < 500:
        return await ctx.send("❌ Need 500 coins for a date.")
    await update_money(ctx.author.id, -500)
    gain = random.randint(50,150)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET affection = affection + ? WHERE user_id = ?", (gain, user.id))
        await db.commit()
    await ctx.send(f"💕 Date with {user.mention}! +{gain} affection.")

@bot.command(name="marry")
@economy_check()
async def marry(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("❌ Can't marry yourself.")
    if await is_family_member(ctx.author.id, user.id):
        return await ctx.send("❌ Cannot marry a family member.")
    data = await get_user(ctx.author.id)
    if data[17]:
        return await ctx.send("❌ Already married.")
    target = await get_user(user.id)
    if target[17]:
        return await ctx.send(f"❌ {user.mention} is already married.")
    if data[1] < 5000:
        return await ctx.send("❌ Need 5000 coins.")
    if target[19] < 1000:
        return await ctx.send(f"❌ Need 1000 affection with {user.mention}.")
    await update_money(ctx.author.id, -5000)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?,?,?,?)",
                         (ctx.author.id, user.id, "marriage", datetime.utcnow().isoformat()))
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
    spouse = data[17]
    if not spouse:
        return await ctx.send("❌ Not married.")
    if data[1] < 2500:
        return await ctx.send("❌ Need 2500 coins for divorce.")
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
    aff = data[19]
    if aff >= 5000:
        level = "👑 Eternal Bond"
    elif aff >= 3500:
        level = "❤️ Soulmates"
    elif aff >= 2000:
        level = "💜 Lovers"
    elif aff >= 1000:
        level = "💙 Close Friends"
    elif aff >= 500:
        level = "💚 Friends"
    else:
        level = "💔 Strangers"
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
    if data[1] < amount:
        return await ctx.send(f"❌ You have {format_number(data[1])} coins.")
    await update_money(ctx.author.id, -amount)
    await update_money(user.id, amount)
    gain = amount // 100
    if gain:
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET affection = affection + ? WHERE user_id = ?", (gain, user.id))
            await db.commit()
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
    if data[1] < 2000:
        return await ctx.send("❌ Need 2000 coins.")
    target = await get_user(user.id)
    if target[18]:
        return await ctx.send(f"❌ {user.mention} already has a parent.")
    await update_money(ctx.author.id, -2000)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?,?,?,?)",
                         (ctx.author.id, user.id, "adopt", datetime.utcnow().isoformat()))
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
    spouse = data[17]
    parent = data[18]
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
# LEADERBOARDS
# ==================================================
@bot.command(name="globalleaderboard", aliases=["glb"])
@economy_check()
async def glb(ctx, category: str = "money"):
    if category not in ("money","xp"):
        return await ctx.send("Usage: `.glb money` or `.glb xp`")
    async with aiosqlite.connect("hakari.db") as db:
        if category == "money":
            async with db.execute("SELECT user_id, money+bank as total FROM users ORDER BY total DESC LIMIT 10") as cur:
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
        msg += f"{i}. {name}: {format_number(val)}{suffix}\n"
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
            async with db.execute("SELECT money, bank, total_xp FROM users WHERE user_id=?", (m.id,)) as cur:
                row = await cur.fetchone()
            if row:
                if category=="money":
                    data.append((m, row[0]+row[1]))
                else:
                    data.append((m, row[4]))
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
    lvl = data[4]
    xp = data[5]
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
# OWNER COMMANDS
# ==================================================
@bot.command(name="addmoney")
@owner_only()
async def addmoney(ctx, user: discord.User, amount_str: str):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("Invalid amount.")
    await update_money(user.id, amt)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Added {format_number(amt)}{emoji} to {user.mention}.")

@bot.command(name="removemoney")
@owner_only()
async def removemoney(ctx, user: discord.User, amount_str: str):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("Invalid amount.")
    await update_money(user.id, -amt)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Removed {format_number(amt)}{emoji} from {user.mention}.")

@bot.command(name="setmoney")
@owner_only()
async def setmoney(ctx, user: discord.User, amount_str: str):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("Invalid amount.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = ? WHERE user_id = ?", (amt, user.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Set {user.mention}'s balance to {format_number(amt)}{emoji}.")

@bot.command(name="addbank")
@owner_only()
async def addbank(ctx, user: discord.User, amount_str: str):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("Invalid amount.")
    await update_bank(user.id, amt)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Added {format_number(amt)}{emoji} to {user.mention}'s bank.")

@bot.command(name="removebank")
@owner_only()
async def removebank(ctx, user: discord.User, amount_str: str):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("Invalid amount.")
    await update_bank(user.id, -amt)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Removed {format_number(amt)}{emoji} from {user.mention}'s bank.")

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
        await db.execute("UPDATE users SET money = 0, bank = 0")
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
    print(f"✅ Logged in as {bot.user}")
    print(f"✅ Ready on {len(bot.guilds)} servers")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.author.id,))
        await db.execute("UPDATE users SET daily_messages = daily_messages + 1 WHERE user_id = ?", (message.author.id,))
        await db.commit()
    new_lvl = await add_xp(message.author.id, random.randint(10,20))
    if new_lvl:
        lvl_msg = await message.channel.send(f"🎉 {message.author.mention} leveled up to level {new_lvl}!")
        await asyncio.sleep(5)
        await lvl_msg.delete()
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    print(f"Command error: {error}")

# ==================================================
# RUN BOT
# ==================================================
if __name__ == "__main__":
    bot.run(TOKEN)
