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
# REMOVE DEFAULT HELP COMMAND
# ==================================================
bot.remove_command('help')

# ==================================================
# DATABASE SETUP
# ==================================================
async def init_db():
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS owners (user_id INTEGER PRIMARY KEY, is_main INTEGER DEFAULT 0)")
        await db.execute("INSERT OR IGNORE INTO owners (user_id, is_main) VALUES (?, 1)", (MAIN_OWNER_ID,))
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
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
                shop_name TEXT,
                shop_items TEXT DEFAULT '{}',
                shop_open INTEGER DEFAULT 0,
                spouse_id INTEGER,
                parent_id INTEGER,
                affection INTEGER DEFAULT 0,
                last_date TIMESTAMP
            )
        """)
        
        await db.execute("CREATE TABLE IF NOT EXISTS children (parent_id INTEGER, child_id INTEGER, PRIMARY KEY (parent_id, child_id))")
        await db.execute("CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY AUTOINCREMENT, from_id INTEGER, to_id INTEGER, request_type TEXT, timestamp TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS businesses (user_id INTEGER PRIMARY KEY, business_type TEXT, level INTEGER DEFAULT 1, last_collected TIMESTAMP)")
        await db.execute("CREATE TABLE IF NOT EXISTS guild_settings (guild_id INTEGER PRIMARY KEY, tax_rate INTEGER DEFAULT 5, economy_enabled INTEGER DEFAULT 1, rob_enabled INTEGER DEFAULT 1, gambling_enabled INTEGER DEFAULT 1, daily_amount INTEGER DEFAULT 100, sleep_amount INTEGER DEFAULT 50, currency_name TEXT DEFAULT 'coins', currency_emoji TEXT DEFAULT '💰', immune_roles TEXT DEFAULT '[]')")
        await db.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, user_id INTEGER, action TEXT, details TEXT)")
        
        await db.commit()
    print("✅ Database ready")

# ==================================================
# HELPER FUNCTIONS
# ==================================================
async def is_owner(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM owners WHERE user_id = ?", (ctx.author.id,)) as cursor:
            return await cursor.fetchone() is not None

async def is_main_owner(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT is_main FROM owners WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
            return row and row[0] == 1

async def get_user(user_id):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row
            await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor2:
                return await cursor2.fetchone()

async def update_money(user_id, amount):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def log_action(user_id, action, details=""):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO logs (timestamp, user_id, action, details) VALUES (?, ?, ?, ?)", (datetime.utcnow().isoformat(), user_id, action, details))
        await db.commit()

async def get_setting(guild_id, setting):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute(f"SELECT {setting} FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
    defaults = {"tax_rate": 5, "economy_enabled": 1, "rob_enabled": 1, "gambling_enabled": 1, "daily_amount": 100, "sleep_amount": 50, "currency_emoji": "💰", "immune_roles": "[]"}
    return defaults.get(setting, 1)

def owner_only():
    async def predicate(ctx):
        if await is_owner(ctx):
            return True
        await ctx.send("❌ You don't have permission to use this command.")
        return False
    return commands.check(predicate)

# ==================================================
# PAGINATED COMMANDS MENU
# ==================================================
class CommandsView(discord.ui.View):
    def __init__(self, ctx, pages):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.pages = pages
        self.page = 0

    async def update(self, interaction):
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction, btn):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Not your menu!", ephemeral=True)
        self.page = (self.page - 1) % len(self.pages)
        await self.update(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, btn):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Not your menu!", ephemeral=True)
        self.page = (self.page + 1) % len(self.pages)
        await self.update(interaction)

    @discord.ui.button(label="❌", style=discord.ButtonStyle.danger)
    async def close(self, interaction, btn):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Not your menu!", ephemeral=True)
        await interaction.message.delete()

@bot.command(name="cmds", aliases=["commands"])
async def show_commands(ctx):
    pages = [
        discord.Embed(title="💰 Economy Commands (1/3)", color=discord.Color.blue()).add_field(name="Commands", value="`.balance` / `.bal` - Check balance\n`.daily` - Daily reward\n`.sleep` - Sleep for coins\n`.work` - Work for coins\n`.rob <@user>` - Rob someone\n`.gamble <amount>` - Gamble coins\n`.deposit <amount>` - Deposit to bank\n`.withdraw <amount>` - Withdraw\n`.pay <@user> <amount>` - Send money", inline=False),
        discord.Embed(title="🛒 Shop & Business (2/3)", color=discord.Color.green()).add_field(name="Commands", value="`.createshop <name>` - Create shop\n`.addshopitem <price> <item>` - Add item\n`.removeshopitem <item>` - Remove item\n`.myshop` - View your shop\n`.visitshop <@user>` - Visit shop\n`.buyfromshop <@user> <item>` - Buy item\n`.closeshop` - Open/close\n`.globalmarket` - All shops\n`.buybusiness <type>` - Buy business\n`.business` - View business\n`.upgradebusiness` - Upgrade\n`.collectprofits` - Collect profits\n`.sellbusiness` - Sell business", inline=False),
        discord.Embed(title="💕 Relationships & More (3/3)", color=discord.Color.pink()).add_field(name="Commands", value="`.date <@user>` - Go on date (500 coins)\n`.marry <@user>` - Propose (5000 coins)\n`.divorce` - Divorce (2500 coins)\n`.affection` - Check love level\n`.gift <@user> <amount>` - Gift coins\n`.adopt <@user>` - Adopt child (2000 coins)\n`.children` - List children\n`.family` - Family tree\n`.accept` / `.reject` - Handle requests\n`.globalleaderboard money` - Top富豪榜\n`.serverleaderboard money` - Server rich list", inline=False)
    ]
    if await is_owner(ctx):
        pages.append(discord.Embed(title="👑 Owner Commands (4/4)", color=discord.Color.red()).add_field(name="Commands", value="`.addowner <id>` - Add owner\n`.removeowner <id>` - Remove owner\n`.ownerlist` - List owners\n`.addmoney <@user> <amount>` - Add money\n`.setmoney <@user> <amount>` - Set money\n`.protect <@user>` - Protect user\n`.blacklist <@user>` - Blacklist\n`.economywipe` - Wipe economy\n`.toggleeconomy` - Toggle economy\n`.setdailyamount <amount>` - Set daily reward\n`.logs` - View logs", inline=False))
    await ctx.send(embed=pages[0], view=CommandsView(ctx, pages))

# ==================================================
# ECONOMY COMMANDS
# ==================================================
@bot.command(name="balance", aliases=["bal"])
async def balance(ctx, user: discord.User = None):
    target = user or ctx.author
    data = await get_user(target.id)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"💰 **{target.display_name}**\nWallet: {data[1]}{emoji}\nBank: {data[2]}{emoji}\nTotal: {data[1]+data[2]}{emoji}")

@bot.command(name="daily")
async def daily(ctx):
    data = await get_user(ctx.author.id)
    if data[8]:
        last = datetime.fromisoformat(data[8])
        if datetime.utcnow() - last < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Try again in {remaining.seconds//3600}h {(remaining.seconds%3600)//60}m")
    amount = await get_setting(ctx.guild.id, "daily_amount")
    await update_money(ctx.author.id, amount)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ You received {amount} coins!")

@bot.command(name="work")
async def work(ctx):
    data = await get_user(ctx.author.id)
    if data[9]:
        last = datetime.fromisoformat(data[9])
        if datetime.utcnow() - last < timedelta(hours=1):
            remaining = timedelta(hours=1) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Try again in {remaining.seconds//60}m")
    earnings = random.randint(20, 100)
    await update_money(ctx.author.id, earnings)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_work = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    await ctx.send(f"💼 You worked hard and earned {earnings} coins!")

@bot.command(name="sleep")
async def sleep(ctx):
    data = await get_user(ctx.author.id)
    if data[9]:
        last = datetime.fromisoformat(data[9])
        if datetime.utcnow() - last < timedelta(hours=8):
            remaining = timedelta(hours=8) - (datetime.utcnow() - last)
            return await ctx.send(f"😴 You need rest! Try again in {remaining.seconds//3600}h")
    amount = await get_setting(ctx.guild.id, "sleep_amount")
    await update_money(ctx.author.id, amount)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_work = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    await ctx.send(f"😴 You slept and woke up with {amount} coins!")

@bot.command(name="deposit")
async def deposit(ctx, amount: int):
    if amount <= 0:
        return await ctx.send("Amount must be positive!")
    data = await get_user(ctx.author.id)
    if data[1] < amount:
        return await ctx.send("Not enough money in wallet!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = money - ?, bank = bank + ? WHERE user_id = ?", (amount, amount, ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Deposited {amount} coins to your bank!")

@bot.command(name="withdraw")
async def withdraw(ctx, amount: int):
    if amount <= 0:
        return await ctx.send("Amount must be positive!")
    data = await get_user(ctx.author.id)
    if data[2] < amount:
        return await ctx.send("Not enough money in bank!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = money + ?, bank = bank - ? WHERE user_id = ?", (amount, amount, ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Withdrew {amount} coins from your bank!")

@bot.command(name="pay")
async def pay(ctx, target: discord.User, amount: int):
    if amount <= 0:
        return await ctx.send("Amount must be positive!")
    if target == ctx.author:
        return await ctx.send("You can't pay yourself!")
    data = await get_user(ctx.author.id)
    if data[1] < amount:
        return await ctx.send("Not enough money!")
    await update_money(ctx.author.id, -amount)
    await update_money(target.id, amount)
    await ctx.send(f"✅ You paid {amount} coins to {target.mention}!")

@bot.command(name="rob")
async def rob(ctx, target: discord.User):
    if target == ctx.author:
        return await ctx.send("You can't rob yourself!")
    
    rob_enabled = await get_setting(ctx.guild.id, "rob_enabled")
    if not rob_enabled:
        return await ctx.send("Rob command is disabled!")
    
    target_data = await get_user(target.id)
    if target_data[6]:
        return await ctx.send(f"{target.mention} is protected!")
    
    data = await get_user(ctx.author.id)
    if data[10]:
        last = datetime.fromisoformat(data[10])
        if datetime.utcnow() - last < timedelta(minutes=30):
            remaining = timedelta(minutes=30) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Try again in {remaining.seconds//60}m")
    
    success = random.random() < 0.4
    if success:
        steal = random.randint(50, min(200, target_data[1]))
        if steal > 0:
            await update_money(target.id, -steal)
            await update_money(ctx.author.id, steal)
            await ctx.send(f"✅ You robbed {target.mention} and got {steal} coins!")
        else:
            await ctx.send(f"❌ {target.mention} has no money to rob!")
    else:
        fine = random.randint(30, 100)
        await update_money(ctx.author.id, -fine)
        await ctx.send(f"❌ You failed and lost {fine} coins!")
    
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_rob = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()

@bot.command(name="gamble")
async def gamble(ctx, amount: int):
    if amount <= 0:
        return await ctx.send("Amount must be positive!")
    
    gambling_enabled = await get_setting(ctx.guild.id, "gambling_enabled")
    if not gambling_enabled:
        return await ctx.send("Gambling is disabled!")
    
    data = await get_user(ctx.author.id)
    if data[1] < amount:
        return await ctx.send("Not enough money!")
    
    win = random.choice([True, False])
    if win:
        await update_money(ctx.author.id, amount)
        await ctx.send(f"🎉 You won {amount} coins! New balance: {data[1] + amount}")
    else:
        await update_money(ctx.author.id, -amount)
        await ctx.send(f"💔 You lost {amount} coins! New balance: {data[1] - amount}")

# ==================================================
# SHOP COMMANDS
# ==================================================
@bot.command(name="createshop")
async def create_shop(ctx, *, name: str):
    data = await get_user(ctx.author.id)
    if data[11]:
        return await ctx.send("You already have a shop! Use `.closeshop` first.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_name = ?, shop_open = 1 WHERE user_id = ?", (name, ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Shop '{name}' created! Use `.addshopitem <price> <item>` to add items.")

@bot.command(name="addshopitem")
async def add_shop_item(ctx, price: int, *, item: str):
    data = await get_user(ctx.author.id)
    if not data[11]:
        return await ctx.send("You don't have a shop! Use `.createshop`.")
    if not data[13]:
        return await ctx.send("Your shop is closed! Use `.closeshop` to open it.")
    
    items = json.loads(data[12]) if data[12] else {}
    items[item] = price
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Added '{item}' for {price} coins!")

@bot.command(name="removeshopitem")
async def remove_shop_item(ctx, *, item: str):
    data = await get_user(ctx.author.id)
    if not data[11]:
        return await ctx.send("You don't have a shop!")
    items = json.loads(data[12]) if data[12] else {}
    if item not in items:
        return await ctx.send("Item not found!")
    del items[item]
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Removed '{item}' from your shop!")

@bot.command(name="myshop")
async def my_shop(ctx):
    data = await get_user(ctx.author.id)
    if not data[11]:
        return await ctx.send("You don't have a shop!")
    
    items = json.loads(data[12]) if data[12] else {}
    status = "Open" if data[13] else "Closed"
    
    if not items:
        await ctx.send(f"🏪 **{data[11]}** ({status})\nNo items for sale.")
    else:
        msg = f"🏪 **{data[11]}** ({status})\n\n"
        for item, price in items.items():
            msg += f"• {item}: {price} coins\n"
        await ctx.send(msg)

@bot.command(name="visitshop")
async def visit_shop(ctx, user: discord.User):
    data = await get_user(user.id)
    if not data[11] or not data[13]:
        return await ctx.send(f"{user.display_name} doesn't have an open shop!")
    
    items = json.loads(data[12]) if data[12] else {}
    if not items:
        return await ctx.send(f"{user.display_name}'s shop has no items!")
    
    msg = f"🏪 **{data[11]}** (Owner: {user.display_name})\n\n"
    for item, price in items.items():
        msg += f"• {item}: {price} coins\n"
    msg += f"\nTo buy: `.buyfromshop {user.mention} <item>`"
    await ctx.send(msg)

@bot.command(name="buyfromshop")
async def buy_from_shop(ctx, seller: discord.User, *, item: str):
    seller_data = await get_user(seller.id)
    if not seller_data[11] or not seller_data[13]:
        return await ctx.send(f"{seller.display_name}'s shop is not open!")
    
    items = json.loads(seller_data[12]) if seller_data[12] else {}
    if item not in items:
        return await ctx.send(f"'{item}' not found in {seller.display_name}'s shop!")
    
    price = items[item]
    buyer_data = await get_user(ctx.author.id)
    if buyer_data[1] < price:
        return await ctx.send(f"You need {price} coins to buy this!")
    
    tax = int(price * 0.05)
    seller_gets = price - tax
    
    await update_money(ctx.author.id, -price)
    await update_money(seller.id, seller_gets)
    
    del items[item]
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), seller.id))
        await db.commit()
    
    await ctx.send(f"✅ You bought '{item}' for {price} coins! {seller.mention} received {seller_gets} coins (5% tax).")

@bot.command(name="closeshop")
async def close_shop(ctx):
    data = await get_user(ctx.author.id)
    if not data[11]:
        return await ctx.send("You don't have a shop!")
    
    new_status = 0 if data[13] else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_open = ? WHERE user_id = ?", (new_status, ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Shop is now {'open' if new_status else 'closed'}!")

@bot.command(name="globalmarket")
async def global_market(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, shop_name FROM users WHERE shop_open = 1 AND shop_name IS NOT NULL LIMIT 20") as cursor:
            shops = await cursor.fetchall()
    
    if not shops:
        return await ctx.send("No open shops found!")
    
    msg = "🌍 **Global Market**\n\n"
    for user_id, name in shops:
        user = await bot.fetch_user(user_id)
        msg += f"• {name} - Owner: {user.display_name}\n"
    await ctx.send(msg)

# ==================================================
# BUSINESS COMMANDS
# ==================================================
@bot.command(name="buybusiness")
async def buy_business(ctx, business_type: str):
    types = ["restaurant", "casino", "cafe", "techstore"]
    if business_type.lower() not in types:
        return await ctx.send(f"Types: {', '.join(types)}")
    
    data = await get_user(ctx.author.id)
    cost = 1000
    if data[1] < cost:
        return await ctx.send(f"You need {cost} coins!")
    
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            if await cursor.fetchone():
                return await ctx.send("You already own a business!")
        
        await update_money(ctx.author.id, -cost)
        await db.execute("INSERT INTO businesses (user_id, business_type, level, last_collected) VALUES (?, ?, ?, ?)",
                        (ctx.author.id, business_type.lower(), 1, datetime.utcnow().isoformat()))
        await db.commit()
    await ctx.send(f"✅ You bought a {business_type} business for {cost} coins!")

@bot.command(name="business")
async def business_info(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT business_type, level, last_collected FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return await ctx.send("You don't own a business!")
    
    biz_type, level, last = row
    await ctx.send(f"🏪 **Your {biz_type} business**\nLevel: {level}\nBase income: {50 * level} coins/hour\nUse `.collectprofits` to earn!")

@bot.command(name="upgradebusiness")
async def upgrade_business(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return await ctx.send("You don't own a business!")
    
    level = row[0]
    cost = 500 * level
    data = await get_user(ctx.author.id)
    if data[1] < cost:
        return await ctx.send(f"Upgrade costs {cost} coins!")
    
    await update_money(ctx.author.id, -cost)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE businesses SET level = level + 1 WHERE user_id = ?", (ctx.author.id,))
        await db.commit()
    await ctx.send(f"✅ Business upgraded to level {level + 1}!")

@bot.command(name="collectprofits")
async def collect_profits(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level, last_collected FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return await ctx.send("You don't own a business!")
    
    level, last = row
    now = datetime.utcnow()
    last_time = datetime.fromisoformat(last)
    hours = (now - last_time).total_seconds() / 3600
    
    if hours < 1:
        remaining = 3600 - (now - last_time).total_seconds()
        return await ctx.send(f"⏰ Next collection in {int(remaining//60)} minutes!")
    
    profit = int(50 * level * hours)
    await update_money(ctx.author.id, profit)
    
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE businesses SET last_collected = ? WHERE user_id = ?", (now.isoformat(), ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ You collected {profit} coins from your business!")

@bot.command(name="sellbusiness")
async def sell_business(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return await ctx.send("You don't own a business!")
    
    value = 500 * row[0]
    await update_money(ctx.author.id, value)
    
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM businesses WHERE user_id = ?", (ctx.author.id,))
        await db.commit()
    await ctx.send(f"✅ Sold your business for {value} coins!")

# ==================================================
# RELATIONSHIP COMMANDS
# ==================================================
@bot.command(name="date")
async def date_cmd(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("You can't date yourself!")
    
    data = await get_user(ctx.author.id)
    if data[14]:
        return await ctx.send("You're already married!")
    
    if data[17]:
        last = datetime.fromisoformat(data[17])
        if datetime.utcnow() - last < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Try again in {remaining.seconds//3600}h")
    
    if data[1] < 500:
        return await ctx.send("You need 500 coins for a date!")
    
    await update_money(ctx.author.id, -500)
    affection_gain = random.randint(50, 150)
    
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET affection = affection + ?, last_date = ? WHERE user_id = ?", 
                        (affection_gain, datetime.utcnow().isoformat(), user.id))
        await db.commit()
    
    await ctx.send(f"💕 You went on a date with {user.mention}! Affection +{affection_gain}!")

@bot.command(name="marry")
async def marry_cmd(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("You can't marry yourself!")
    
    data = await get_user(ctx.author.id)
    if data[14]:
        return await ctx.send("You're already married!")
    
    target = await get_user(user.id)
    if target[14]:
        return await ctx.send(f"{user.mention} is already married!")
    
    if data[1] < 5000:
        return await ctx.send("You need 5000 coins for a marriage proposal!")
    
    if target[16] < 1000:
        return await ctx.send(f"Your affection with {user.mention} is too low! Need 1000, have {target[16]}")
    
    await update_money(ctx.author.id, -5000)
    
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?, ?, 'marriage', ?)",
                        (ctx.author.id, user.id, datetime.utcnow().isoformat()))
        await db.commit()
    
    await ctx.send(f"💍 {ctx.author.mention} proposed to {user.mention}! They have 60 seconds to type `.accept`.")

@bot.command(name="divorce")
async def divorce_cmd(ctx):
    data = await get_user(ctx.author.id)
    spouse_id = data[14]
    if not spouse_id:
        return await ctx.send("You're not married!")
    
    if data[1] < 2500:
        return await ctx.send("You need 2500 coins for divorce!")
    
    await update_money(ctx.author.id, -2500)
    
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (ctx.author.id,))
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (spouse_id,))
        await db.commit()
    
    spouse = await bot.fetch_user(spouse_id)
    await ctx.send(f"💔 {ctx.author.mention} and {spouse.mention} are divorced!")

@bot.command(name="affection")
async def affection_cmd(ctx, user: discord.User = None):
    target = user or ctx.author
    data = await get_user(target.id)
    affection = data[16]
    
    level = "Strangers"
    if affection >= 5000: level = "Eternal Bond 👑"
    elif affection >= 3500: level = "Soulmates ❤️"
    elif affection >= 2000: level = "Lovers 💜"
    elif affection >= 1000: level = "Close Friends 💙"
    elif affection >= 500: level = "Friends 💚"
    elif affection >= 100: level = "Acquaintances 💛"
    
    bar_len = min(20, affection // 250)
    bar = "█" * bar_len + "░" * (20 - bar_len)
    
    await ctx.send(f"💕 **{target.display_name}**\nLevel: {level}\nAffection: {affection}\n`{bar}`")

@bot.command(name="gift")
async def gift_cmd(ctx, user: discord.User, amount: int):
    if amount <= 0:
        return await ctx.send("Amount must be positive!")
    if user == ctx.author:
        return await ctx.send("You can't gift yourself!")
    
    data = await get_user(ctx.author.id)
    if data[1] < amount:
        return await ctx.send("Not enough money!")
    
    await update_money(ctx.author.id, -amount)
    await update_money(user.id, amount)
    
    affection_gain = amount // 100
    if affection_gain > 0:
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET affection = affection + ? WHERE user_id = ?", (affection_gain, user.id))
            await db.commit()
    
    await ctx.send(f"🎁 You gifted {amount} coins to {user.mention}!" + (f" (+{affection_gain} affection)" if affection_gain > 0 else ""))

@bot.command(name="adopt")
async def adopt_cmd(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("You can't adopt yourself!")
    
    data = await get_user(ctx.author.id)
    if data[1] < 2000:
        return await ctx.send("You need 2000 coins to adopt!")
    
    target = await get_user(user.id)
    if target[15]:
        return await ctx.send(f"{user.mention} already has a parent!")
    
    await update_money(ctx.author.id, -2000)
    
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?, ?, 'adopt', ?)",
                        (ctx.author.id, user.id, datetime.utcnow().isoformat()))
        await db.commit()
    
    await ctx.send(f"👶 {ctx.author.mention} wants to adopt {user.mention}! They have 60 seconds to type `.accept`.")

@bot.command(name="children")
async def children_cmd(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT child_id FROM children WHERE parent_id = ?", (ctx.author.id,)) as cursor:
            children = await cursor.fetchall()
    
    if not children:
        return await ctx.send("You don't have any children!")
    
    msg = f"👶 **{ctx.author.display_name}'s Children**\n\n"
    for child_id in children:
        child = await bot.fetch_user(child_id[0])
        msg += f"• {child.mention}\n"
    await ctx.send(msg)

@bot.command(name="family")
async def family_cmd(ctx):
    data = await get_user(ctx.author.id)
    spouse_id = data[14]
    parent_id = data[15]
    
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT child_id FROM children WHERE parent_id = ?", (ctx.author.id,)) as cursor:
            children = await cursor.fetchall()
    
    msg = f"👨‍👩‍👧‍👦 **{ctx.author.display_name}'s Family**\n\n"
    
    if spouse_id:
        spouse = await bot.fetch_user(spouse_id)
        msg += f"💑 Spouse: {spouse.mention}\n"
    else:
        msg += "💑 Spouse: None\n"
    
    if parent_id:
        parent = await bot.fetch_user(parent_id)
        msg += f"👪 Parent: {parent.mention}\n"
    else:
        msg += "👪 Parent: None\n"
    
    if children:
        msg += "\n👶 Children:\n"
        for child_id in children:
            child = await bot.fetch_user(child_id[0])
            msg += f"• {child.mention}\n"
    else:
        msg += "\n👶 Children: None"
    
    await ctx.send(msg)

@bot.command(name="accept")
async def accept_cmd(ctx, request_id: int = None):
    if request_id is None:
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT id, from_id, request_type FROM requests WHERE to_id = ?", (ctx.author.id,)) as cursor:
                requests = await cursor.fetchall()
        
        if not requests:
            return await ctx.send("No pending requests!")
        
        msg = "📬 **Your pending requests**\n\n"
        for req_id, from_id, req_type in requests:
            user = await bot.fetch_user(from_id)
            msg += f"#{req_id}: {user.mention} - {req_type}\n"
        msg += "\nType `.accept <id>` to accept"
        return await ctx.send(msg)
    
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT from_id, request_type FROM requests WHERE id = ? AND to_id = ?", (request_id, ctx.author.id)) as cursor:
            req = await cursor.fetchone()
        
        if not req:
            return await ctx.send("Invalid request ID!")
        
        from_id, req_type = req
        
        if req_type == "marriage":
            await db.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (ctx.author.id, from_id))
            await db.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (from_id, ctx.author.id))
            await db.execute("DELETE FROM requests WHERE id = ?", (request_id,))
            await db.commit()
            
            from_user = await bot.fetch_user(from_id)
            await ctx.send(f"💕 {from_user.mention} and {ctx.author.mention} are now married! 🎉")
        
        elif req_type == "adopt":
            await db.execute("INSERT INTO children (parent_id, child_id) VALUES (?, ?)", (from_id, ctx.author.id))
            await db.execute("UPDATE users SET parent_id = ? WHERE user_id = ?", (from_id, ctx.author.id))
            await db.execute("DELETE FROM requests WHERE id = ?", (request_id,))
            await db.commit()
            
            from_user = await bot.fetch_user(from_id)
            await ctx.send(f"👶 {from_user.mention} adopted {ctx.author.mention}! Welcome to the family! 🎉")

@bot.command(name="reject")
async def reject_cmd(ctx, request_id: int):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM requests WHERE id = ? AND to_id = ?", (request_id, ctx.author.id)) as cursor:
            if not await cursor.fetchone():
                return await ctx.send("Invalid request ID!")
        
        await db.execute("DELETE FROM requests WHERE id = ?", (request_id,))
        await db.commit()
    await ctx.send(f"✅ Rejected request #{request_id}.")

# ==================================================
# LEADERBOARD COMMANDS
# ==================================================
@bot.command(name="globalleaderboard", aliases=["glb"])
async def global_leaderboard(ctx, category: str = "money"):
    if category not in ["money", "xp"]:
        return await ctx.send("Use: `.glb money` or `.glb xp`")
    
    async with aiosqlite.connect("hakari.db") as db:
        if category == "money":
            async with db.execute("SELECT user_id, money+bank as total FROM users ORDER BY total DESC LIMIT 10") as cursor:
                rows = await cursor.fetchall()
            title = "🌍 Global Richest"
        else:
            async with db.execute("SELECT user_id, total_xp FROM users ORDER BY total_xp DESC LIMIT 10") as cursor:
                rows = await cursor.fetchall()
            title = "🌍 Global Top XP"
    
    if not rows:
        return await ctx.send("No data yet!")
    
    msg = f"**{title}**\n\n"
    for i, (user_id, value) in enumerate(rows, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"User {user_id}"
        suffix = " coins" if category == "money" else " XP"
        msg += f"{i}. {name}: {value}{suffix}\n"
    await ctx.send(msg)

@bot.command(name="serverleaderboard", aliases=["slb"])
async def server_leaderboard(ctx, category: str = "money"):
    if category not in ["money", "xp"]:
        return await ctx.send("Use: `.slb money` or `.slb xp`")
    
    members = [m for m in ctx.guild.members if not m.bot]
    user_data = []
    
    async with aiosqlite.connect("hakari.db") as db:
        for member in members:
            async with db.execute("SELECT money, bank, total_xp FROM users WHERE user_id = ?", (member.id,)) as cursor:
                row = await cursor.fetchone()
            if row:
                if category == "money":
                    user_data.append((member, row[0] + row[1]))
                else:
                    user_data.append((member, row[4]))
    
    user_data.sort(key=lambda x: x[1], reverse=True)
    top = user_data[:10]
    
    if not top:
        return await ctx.send("No data yet!")
    
    title = f"📊 Server {'Richest' if category=='money' else 'Top XP'} - {ctx.guild.name}"
    msg = f"**{title}**\n\n"
    for i, (member, value) in enumerate(top, 1):
        suffix = " coins" if category == "money" else " XP"
        msg += f"{i}. {member.display_name}: {value}{suffix}\n"
    await ctx.send(msg)

@bot.command(name="topcouples")
async def top_couples(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, spouse_id, affection FROM users WHERE spouse_id IS NOT NULL ORDER BY affection DESC LIMIT 10") as cursor:
            couples = await cursor.fetchall()
    
    if not couples:
        return await ctx.send("No couples yet!")
    
    msg = "💕 **Top Couples by Affection**\n\n"
    for i, (user_id, spouse_id, affection) in enumerate(couples, 1):
        try:
            user = await bot.fetch_user(user_id)
            spouse = await bot.fetch_user(spouse_id)
            msg += f"{i}. {user.display_name} & {spouse.display_name}: {affection} ❤️\n"
        except:
            continue
    await ctx.send(msg)

# ==================================================
# OWNER COMMANDS
# ==================================================
@bot.command(name="addowner")
@owner_only()
async def add_owner(ctx, user_id: int):
    if not await is_main_owner(ctx):
        return await ctx.send("Only main owner can add owners!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO owners (user_id, is_main) VALUES (?, 0)", (user_id,))
        await db.commit()
    await ctx.send(f"✅ Added <@{user_id}> as owner!")

@bot.command(name="removeowner")
@owner_only()
async def remove_owner(ctx, user_id: int):
    if not await is_main_owner(ctx):
        return await ctx.send("Only main owner can remove owners!")
    if user_id == MAIN_OWNER_ID:
        return await ctx.send("Cannot remove main owner!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM owners WHERE user_id = ?", (user_id,))
        await db.commit()
    await ctx.send(f"✅ Removed <@{user_id}> from owners!")

@bot.command(name="ownerlist")
@owner_only()
async def owner_list(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, is_main FROM owners") as cursor:
            owners = await cursor.fetchall()
    msg = "👑 **Bot Owners**\n\n"
    for user_id, is_main in owners:
        role = "Main Owner" if is_main else "Owner"
        msg += f"• <@{user_id}> - {role}\n"
    await ctx.send(msg)

@bot.command(name="addmoney")
@owner_only()
async def add_money(ctx, user: discord.User, amount: int):
    await update_money(user.id, amount)
    await ctx.send(f"✅ Added {amount} coins to {user.mention}!")

@bot.command(name="setmoney")
@owner_only()
async def set_money(ctx, user: discord.User, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = ? WHERE user_id = ?", (amount, user.id))
        await db.commit()
    await ctx.send(f"✅ Set {user.mention}'s balance to {amount} coins!")

@bot.command(name="protect")
@owner_only()
async def protect_user(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET protected = 1 WHERE user_id = ?", (user.id,))
        await db.commit()
    await ctx.send(f"✅ {user.mention} is now protected (cannot be robbed)!")

@bot.command(name="unprotect")
@owner_only()
async def unprotect_user(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET protected = 0 WHERE user_id = ?", (user.id,))
        await db.commit()
    await ctx.send(f"✅ {user.mention} is no longer protected!")

@bot.command(name="protectedlist")
@owner_only()
async def protected_list(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id FROM users WHERE protected = 1") as cursor:
            users = await cursor.fetchall()
    if not users:
        return await ctx.send("No protected users!")
    msg = "🛡️ **Protected Users**\n\n"
    for user_id in users:
        msg += f"• <@{user_id[0]}>\n"
    await ctx.send(msg)

@bot.command(name="blacklist")
@owner_only()
async def blacklist_user(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET blacklisted = 1 WHERE user_id = ?", (user.id,))
        await db.commit()
    await ctx.send(f"✅ {user.mention} has been blacklisted!")

@bot.command(name="whitelist")
@owner_only()
async def whitelist_user(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET blacklisted = 0 WHERE user_id = ?", (user.id,))
        await db.commit()
    await ctx.send(f"✅ {user.mention} has been whitelisted!")

@bot.command(name="economywipe")
@owner_only()
async def economy_wipe(ctx):
    await ctx.send("⚠️ Type `confirm` to wipe ALL user balances!")
    def check(m): return m.author == ctx.author and m.content.lower() == "confirm"
    try:
        await bot.wait_for("message", timeout=30, check=check)
    except asyncio.TimeoutError:
        return await ctx.send("Cancelled.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = 0, bank = 0")
        await db.commit()
    await ctx.send("✅ Economy wiped!")

@bot.command(name="toggleeconomy")
@owner_only()
async def toggle_economy(ctx):
    current = await get_setting(ctx.guild.id, "economy_enabled")
    new = 0 if current else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, economy_enabled) VALUES (?, ?)", (ctx.guild.id, new))
        await db.commit()
    await ctx.send(f"✅ Economy commands {'enabled' if new else 'disabled'}!")

@bot.command(name="togglerob")
@owner_only()
async def toggle_rob(ctx):
    current = await get_setting(ctx.guild.id, "rob_enabled")
    new = 0 if current else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, rob_enabled) VALUES (?, ?)", (ctx.guild.id, new))
        await db.commit()
    await ctx.send(f"✅ Rob command {'enabled' if new else 'disabled'}!")

@bot.command(name="togglegambling")
@owner_only()
async def toggle_gambling(ctx):
    current = await get_setting(ctx.guild.id, "gambling_enabled")
    new = 0 if current else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, gambling_enabled) VALUES (?, ?)", (ctx.guild.id, new))
        await db.commit()
    await ctx.send(f"✅ Gambling command {'enabled' if new else 'disabled'}!")

@bot.command(name="setdailyamount")
@owner_only()
async def set_daily(ctx, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, daily_amount) VALUES (?, ?)", (ctx.guild.id, amount))
        await db.commit()
    await ctx.send(f"✅ Daily reward set to {amount} coins!")

@bot.command(name="setsleepamount")
@owner_only()
async def set_sleep(ctx, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, sleep_amount) VALUES (?, ?)", (ctx.guild.id, amount))
        await db.commit()
    await ctx.send(f"✅ Sleep reward set to {amount} coins!")

@bot.command(name="setcurrency")
@owner_only()
async def set_currency(ctx, emoji: str):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, currency_emoji) VALUES (?, ?)", (ctx.guild.id, emoji))
        await db.commit()
    await ctx.send(f"✅ Currency emoji set to {emoji}!")

@bot.command(name="logs")
@owner_only()
async def view_logs(ctx, limit: int = 10):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT timestamp, user_id, action, details FROM logs ORDER BY id DESC LIMIT ?", (limit,)) as cursor:
            logs = await cursor.fetchall()
    if not logs:
        return await ctx.send("No logs found!")
    msg = "📜 **Recent Logs**\n\n"
    for timestamp, user_id, action, details in logs[:10]:
        msg += f"• {timestamp[:16]} - <@{user_id}>: {action} {details}\n"
    await ctx.send(msg[:1900])

# ==================================================
# EVENTS
# ==================================================
@bot.event
async def on_ready():
    await init_db()
    print(f"✅ Logged in as {bot.user}")
    print(f"✅ Ready on {len(bot.guilds)} servers")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    # XP system
    xp_gain = random.randint(10, 20)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.author.id,))
        await db.execute("UPDATE users SET xp = xp + ?, total_xp = total_xp + ? WHERE user_id = ?", (xp_gain, xp_gain, message.author.id))
        async with db.execute("SELECT total_xp, level FROM users WHERE user_id = ?", (message.author.id,)) as cursor:
            row = await cursor.fetchone()
        if row:
            total_xp, level = row
            new_level = int((total_xp / 100) ** 0.5)
            if new_level > level:
                await db.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_level, message.author.id))
                await db.commit()
                await message.channel.send(f"🎉 {message.author.mention} leveled up to level {new_level}!")
    
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission!")
    else:
        print(f"Error: {error}")

# ==================================================
# RUN BOT
# ==================================================
if __name__ == "__main__":
    bot.run(TOKEN)
