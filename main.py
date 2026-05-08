import discord
from discord.ext import commands, tasks
import aiosqlite
import json
import random
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
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
# REMOVE DEFAULT HELP COMMAND & ADD CUSTOM .cmds
# ==================================================
bot.remove_command('help')

@bot.command(name="cmds", aliases=["commands"])
async def show_commands(ctx):
    """Shows all available bot commands"""
    
    embed = discord.Embed(
        title="🤖 Hakari Bot Commands",
        description="Here are all the commands you can use:",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="💰 Economy Commands",
        value="`.balance` / `.bal` - Check your balance\n"
              "`.daily` - Claim daily reward\n"
              "`.sleep` - Earn coins by sleeping\n"
              "`.work` - Work for coins\n"
              "`.rob <@user>` - Try to rob someone\n"
              "`.gamble <amount>` - Gamble your coins\n"
              "`.deposit <amount>` - Deposit to bank\n"
              "`.withdraw <amount>` - Withdraw from bank\n"
              "`.pay <@user> <amount>` - Pay another user",
        inline=False
    )
    
    embed.add_field(
        name="🛒 Shop Commands",
        value="`.createshop <name>` - Create your own shop\n"
              "`.shopinfo` - View shop info\n"
              "`.shopinventory` - View shop items\n"
              "`.addshopitem <price> <item>` - Add item to shop\n"
              "`.removeshopitem <item>` - Remove item\n"
              "`.myshop` - View your shop\n"
              "`.visitshop <@user>` - Visit someone's shop\n"
              "`.buyfromshop <@user> <item>` - Buy an item\n"
              "`.closeshop` - Open/close your shop\n"
              "`.upgradeshop <size/slots/advert/tax_reduction>` - Upgrade shop\n"
              "`.collectshopincome` - Collect passive income\n"
              "`.globalmarket` - View all shops\n"
              "`.searchmarket <item>` - Search for an item\n"
              "`.topshops` - Top shops by reputation",
        inline=False
    )
    
    embed.add_field(
        name="🏪 Business Commands",
        value="`.buybusiness <type>` - Buy a business\n"
              "`.business` - View your business\n"
              "`.upgradebusiness` - Upgrade your business\n"
              "`.collectprofits` - Collect business profits\n"
              "`.sellbusiness` - Sell your business\n"
              "`.businessleaderboard` - Top businesses",
        inline=False
    )
    
    embed.add_field(
        name="💕 Dating & Relationship Commands",
        value="`.date <@user>` - Ask someone on a date (costs 500 coins)\n"
              "`.marry <@user>` - Propose marriage (costs 5000 coins)\n"
              "`.divorce` - Divorce your spouse (costs 2500 coins)\n"
              "`.affection` - Check your relationship level\n"
              "`.gift <@user> <amount>` - Gift coins to increase affection\n"
              "`.children` - List your adopted children\n"
              "`.adopt <@user>` - Adopt a child (costs 2000 coins)\n"
              "`.family` - View your family tree\n"
              "`.accept` - Accept a pending request\n"
              "`.reject` - Reject a pending request\n"
              "`.pending` - View your pending requests",
        inline=False
    )
    
    embed.add_field(
        name="📊 Leaderboard Commands",
        value="`.globalleaderboard money` / `.glb money` - Global richest\n"
              "`.globalleaderboard xp` - Global XP rankings\n"
              "`.serverleaderboard money` / `.slb money` - Server richest\n"
              "`.serverleaderboard xp` - Server XP rankings\n"
              "`.topcouples` - Top couples by affection",
        inline=False
    )
    
    if await is_owner(ctx):
        embed.add_field(
            name="👑 Owner Commands",
            value="`.addowner <id>` - Add owner\n"
                  "`.removeowner <id>` - Remove owner\n"
                  "`.ownerlist` - List owners\n"
                  "`.ownerpanel` - Owner control panel\n"
                  "`.addmoney <@user> <amount>` - Add money\n"
                  "`.removemoney <@user> <amount>` - Remove money\n"
                  "`.setmoney <@user> <amount>` - Set money\n"
                  "`.addbank <@user> <amount>` - Add bank\n"
                  "`.removebank <@user> <amount>` - Remove bank\n"
                  "`.protect <@user>` - Protect user\n"
                  "`.unprotect <@user>` - Unprotect user\n"
                  "`.protectedlist` - List protected users\n"
                  "`.blacklist <@user>` - Blacklist user\n"
                  "`.whitelist <@user>` - Whitelist user\n"
                  "`.setroleimmune <@role>` - Set immune role\n"
                  "`.removeroleimmune <@role>` - Remove immune role\n"
                  "`.economywipe` - Wipe economy\n"
                  "`.toggleeconomy` - Toggle economy\n"
                  "`.togglerob` - Toggle rob command\n"
                  "`.togglegambling` - Toggle gambling\n"
                  "`.setdailyamount <amount>` - Set daily reward\n"
                  "`.setsleepamount <amount>` - Set sleep reward\n"
                  "`.setcurrency <name> <emoji>` - Set currency\n"
                  "`.logs` - View logs\n"
                  "`.anticheat` - Toggle anticheat\n"
                  "`.shoptax <percent>` - Set shop tax",
            inline=False
        )
    
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)

# ==================================================
# DATABASE SETUP
# ==================================================
async def init_db():
    async with aiosqlite.connect("hakari.db") as db:
        # Owners table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS owners (
                user_id INTEGER PRIMARY KEY,
                is_main INTEGER DEFAULT 0
            )
        """)
        await db.execute(
            "INSERT OR IGNORE INTO owners (user_id, is_main) VALUES (?, 1)",
            (MAIN_OWNER_ID,)
        )
        
        # Users table with relationship columns
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                money INTEGER DEFAULT 0,
                bank INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                total_xp INTEGER DEFAULT 0,
                gang TEXT,
                family TEXT,
                protected INTEGER DEFAULT 0,
                blacklisted INTEGER DEFAULT 0,
                whitelisted INTEGER DEFAULT 0,
                last_daily TIMESTAMP,
                last_work TIMESTAMP,
                last_rob TIMESTAMP,
                shop_name TEXT,
                shop_items TEXT DEFAULT '{}',
                shop_upgrades TEXT DEFAULT '{}',
                shop_rep INTEGER DEFAULT 0,
                last_shop_income TIMESTAMP,
                shop_open INTEGER DEFAULT 0,
                spouse_id INTEGER,
                parent_id INTEGER,
                affection INTEGER DEFAULT 0,
                last_date TIMESTAMP
            )
        """)
        
        # Children table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS children (
                parent_id INTEGER,
                child_id INTEGER,
                PRIMARY KEY (parent_id, child_id)
            )
        """)
        
        # Pending requests table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id INTEGER,
                to_id INTEGER,
                request_type TEXT,
                timestamp TEXT
            )
        """)
        
        # Businesses table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS businesses (
                user_id INTEGER PRIMARY KEY,
                business_type TEXT,
                level INTEGER DEFAULT 1,
                last_collected TIMESTAMP
            )
        """)
        
        # Guild settings
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                tax_rate INTEGER DEFAULT 5,
                economy_enabled INTEGER DEFAULT 1,
                rob_enabled INTEGER DEFAULT 1,
                gambling_enabled INTEGER DEFAULT 1,
                daily_amount INTEGER DEFAULT 100,
                sleep_amount INTEGER DEFAULT 50,
                currency_name TEXT DEFAULT 'coins',
                currency_emoji TEXT DEFAULT '💰',
                immune_roles TEXT DEFAULT '[]'
            )
        """)
        
        # Logs table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_id INTEGER,
                action TEXT,
                details TEXT
            )
        """)
        
        # Anticheat settings
        await db.execute("""
            CREATE TABLE IF NOT EXISTS anticheat_settings (
                guild_id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 1
            )
        """)
        
        await db.commit()
    print("✅ Database initialized successfully!")

# ==================================================
# HELPER FUNCTIONS
# ==================================================
async def log_action(user_id: int, action: str, details: str = ""):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute(
            "INSERT INTO logs (timestamp, user_id, action, details) VALUES (?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), user_id, action, details)
        )
        await db.commit()

async def is_owner(ctx, user_id: int = None) -> bool:
    if user_id is None:
        user_id = ctx.author.id
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM owners WHERE user_id = ?", (user_id,)) as cursor:
            result = await cursor.fetchone()
    return result is not None

async def is_main_owner(ctx, user_id: int = None) -> bool:
    if user_id is None:
        user_id = ctx.author.id
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT is_main FROM owners WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
    return row is not None and row[0] == 1

async def is_blacklisted(user_id: int) -> bool:
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT blacklisted FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
    return row is not None and row[0] == 1

async def get_guild_setting(guild_id: int, setting: str):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT {} FROM guild_settings WHERE guild_id = ?".format(setting), (guild_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
    defaults = {
        "tax_rate": 5,
        "economy_enabled": 1,
        "rob_enabled": 1,
        "gambling_enabled": 1,
        "daily_amount": 100,
        "sleep_amount": 50,
        "currency_name": "coins",
        "currency_emoji": "💰",
        "immune_roles": "[]"
    }
    return defaults.get(setting)

async def update_user_money(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute(
            "UPDATE users SET money = money + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

async def get_user_data(user_id: int):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row
            await db.execute(
                "INSERT INTO users (user_id) VALUES (?)",
                (user_id,)
            )
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor2:
                return await cursor2.fetchone()

async def add_xp(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.execute("UPDATE users SET xp = xp + ?, total_xp = total_xp + ? WHERE user_id = ?", (amount, amount, user_id))
        await db.commit()
        async with db.execute("SELECT total_xp, level FROM users WHERE user_id = ?", (user_id,)) as cursor:
            result = await cursor.fetchone()
        if result is None:
            return None
        total_xp, level = result
        new_level = int((total_xp / 100) ** 0.5)
        if new_level > level:
            await db.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_level, user_id))
            await db.commit()
            return new_level
    return None

async def get_affection_level(affection: int) -> str:
    if affection < 100:
        return "💔 Strangers"
    elif affection < 500:
        return "💛 Acquaintances"
    elif affection < 1000:
        return "💚 Friends"
    elif affection < 2000:
        return "💙 Close Friends"
    elif affection < 3500:
        return "💜 Lovers"
    elif affection < 5000:
        return "❤️ Soulmates"
    else:
        return "👑 Eternal Bond"

# ==================================================
# RELATIONSHIP HELPER FUNCTIONS
# ==================================================
async def send_request(from_id: int, to_id: int, request_type: str):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute(
            "INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?, ?, ?, ?)",
            (from_id, to_id, request_type, datetime.utcnow().isoformat())
        )
        await db.commit()

async def get_pending_requests(user_id: int):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT id, from_id, request_type FROM requests WHERE to_id = ?", (user_id,)) as cursor:
            return await cursor.fetchall()

async def accept_request(request_id: int):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT from_id, to_id, request_type FROM requests WHERE id = ?", (request_id,)) as cursor:
            request = await cursor.fetchone()
        if not request:
            return None
        from_id, to_id, req_type = request
        if req_type == "marriage":
            await db.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (to_id, from_id))
            await db.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (from_id, to_id))
        elif req_type == "adopt":
            await db.execute("INSERT INTO children (parent_id, child_id) VALUES (?, ?)", (to_id, from_id))
            await db.execute("UPDATE users SET parent_id = ? WHERE user_id = ?", (to_id, from_id))
        await db.execute("DELETE FROM requests WHERE id = ?", (request_id,))
        await db.commit()
        return (from_id, to_id, req_type)

async def reject_request(request_id: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM requests WHERE id = ?", (request_id,))
        await db.commit()

async def get_children(parent_id: int):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT child_id FROM children WHERE parent_id = ?", (parent_id,)) as cursor:
            return [row[0] for row in await cursor.fetchall()]

# ==================================================
# CHECKS
# ==================================================
def owner_only():
    async def predicate(ctx):
        if await is_owner(ctx):
            return True
        await ctx.send("You do not have permission to use this command.")
        await log_action(ctx.author.id, "Failed owner command attempt", f"Command: {ctx.message.content}")
        return False
    return commands.check(predicate)

def main_owner_only():
    async def predicate(ctx):
        if await is_main_owner(ctx):
            return True
        await ctx.send("Only the main owner can use this command.")
        return False
    return commands.check(predicate)

def economy_enabled():
    async def predicate(ctx):
        enabled = await get_guild_setting(ctx.guild.id, "economy_enabled")
        if enabled:
            return True
        await ctx.send("Economy commands are currently disabled.")
        return False
    return commands.check(predicate)

def not_blacklisted():
    async def predicate(ctx):
        if await is_blacklisted(ctx.author.id):
            await ctx.send("You are blacklisted from using this bot.")
            return False
        return True
    return commands.check(predicate)

# ==================================================
# DATING & RELATIONSHIP COMMANDS
# ==================================================
@bot.command(name="date")
@economy_enabled()
@not_blacklisted()
async def date_command(ctx, user: discord.User):
    if user == ctx.author:
        await ctx.send("You cannot date yourself!")
        return
    
    data = await get_user_data(ctx.author.id)
    if data[21]:
        await ctx.send("You are already married! You cannot date someone else.")
        return
    
    target_data = await get_user_data(user.id)
    if target_data[21]:
        await ctx.send(f"{user.mention} is already married!")
        return
    
    last_date = data[25]
    if last_date:
        last = datetime.fromisoformat(last_date)
        if datetime.utcnow() - last < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.utcnow() - last)
            await ctx.send(f"You already went on a date recently! Try again in {remaining.seconds//3600}h {(remaining.seconds%3600)//60}m.")
            return
    
    if data[1] < 500:
        await ctx.send("You need 500 coins to go on a date!")
        return
    
    await update_user_money(ctx.author.id, -500)
    
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_date = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    
    outcomes = [
        "had a romantic dinner 🍽️",
        "watched a movie together 🎬",
        "took a walk in the park 🌳",
        "went to an amusement park 🎢",
        "had a picnic 🧺",
        "visited a museum 🏛️",
        "went stargazing ✨",
        "cooked dinner together 🍳"
    ]
    
    affection_gain = random.randint(50, 150)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET affection = affection + ? WHERE user_id = ?", (affection_gain, user.id))
        await db.commit()
    
    await ctx.send(f"💕 {ctx.author.mention} and {user.mention} {random.choice(outcomes)}!\nAffection increased by +{affection_gain}!")

@bot.command(name="marry")
@economy_enabled()
@not_blacklisted()
async def marry_command(ctx, user: discord.User):
    if user == ctx.author:
        await ctx.send("You cannot marry yourself!")
        return
    
    data = await get_user_data(ctx.author.id)
    if data[21]:
        await ctx.send("You are already married! Divorce first with `.divorce`.")
        return
    
    target_data = await get_user_data(user.id)
    if target_data[21]:
        await ctx.send(f"{user.mention} is already married!")
        return
    
    if data[1] < 5000:
        await ctx.send("You need 5000 coins to propose marriage!")
        return
    
    if target_data[24] < 1000:
        await ctx.send(f"Your affection with {user.mention} is too low! You need at least 1000 affection. Current: {target_data[24]}")
        return
    
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM requests WHERE from_id = ? AND to_id = ? AND request_type = 'marriage'", (ctx.author.id, user.id)) as cursor:
            if await cursor.fetchone():
                await ctx.send("You already sent a marriage request to this person!")
                return
    
    await update_user_money(ctx.author.id, -5000)
    await send_request(ctx.author.id, user.id, "marriage")
    
    await ctx.send(f"💍 {ctx.author.mention} proposed to {user.mention} with a beautiful ring! They have 5 minutes to type `.accept` to accept the marriage proposal!")

@bot.command(name="divorce")
@economy_enabled()
@not_blacklisted()
async def divorce_command(ctx):
    data = await get_user_data(ctx.author.id)
    spouse_id = data[21]
    
    if not spouse_id:
        await ctx.send("You are not married!")
        return
    
    if data[1] < 2500:
        await ctx.send("You need 2500 coins to get a divorce!")
        return
    
    await update_user_money(ctx.author.id, -2500)
    
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (ctx.author.id,))
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (spouse_id,))
        await db.commit()
    
    spouse = await bot.fetch_user(spouse_id)
    await ctx.send(f"💔 {ctx.author.mention} and {spouse.mention} have divorced. {ctx.author.mention} paid 2500 coins for the divorce fee.")

@bot.command(name="affection")
@economy_enabled()
@not_blacklisted()
async def affection_command(ctx, user: discord.User = None):
    target = user or ctx.author
    data = await get_user_data(target.id)
    affection = data[24]
    level = await get_affection_level(affection)
    
    embed = discord.Embed(title=f"💕 Affection Level: {target.display_name}", color=discord.Color.pink())
    embed.add_field(name="Level", value=level, inline=False)
    embed.add_field(name="Points", value=f"{affection}/∞", inline=False)
    
    if affection < 5000:
        bar_length = min(20, int(affection / 250))
        bar = "█" * bar_length + "░" * (20 - bar_length)
        embed.add_field(name="Progress", value=f"`{bar}`", inline=False)
    
    if data[21]:
        spouse = await bot.fetch_user(data[21])
        embed.add_field(name="Spouse", value=spouse.mention, inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name="gift")
@economy_enabled()
@not_blacklisted()
async def gift_command(ctx, user: discord.User, amount: int):
    if amount <= 0:
        await ctx.send("Amount must be positive!")
        return
    
    if user == ctx.author:
        await ctx.send("You cannot gift yourself!")
        return
    
    sender_data = await get_user_data(ctx.author.id)
    if sender_data[1] < amount:
        await ctx.send("You don't have enough money to gift that much!")
        return
    
    await update_user_money(ctx.author.id, -amount)
    await update_user_money(user.id, amount)
    
    affection_gain = amount // 100
    if affection_gain > 0:
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET affection = affection + ? WHERE user_id = ?", (affection_gain, user.id))
            await db.commit()
    
    currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"🎁 {ctx.author.mention} gifted {amount}{currency} to {user.mention}!")
    if affection_gain > 0:
        await ctx.send(f"💕 Affection increased by +{affection_gain}!")

@bot.command(name="children")
@economy_enabled()
@not_blacklisted()
async def children_command(ctx):
    children = await get_children(ctx.author.id)
    
    if not children:
        await ctx.send("You don't have any children yet. Use `.adopt <@user>` to adopt a child!")
        return
    
    embed = discord.Embed(title=f"👶 {ctx.author.display_name}'s Children", color=discord.Color.teal())
    for child_id in children:
        child = await bot.fetch_user(child_id)
        embed.add_field(name="Child", value=child.mention, inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="adopt")
@economy_enabled()
@not_blacklisted()
async def adopt_command(ctx, user: discord.User):
    if user == ctx.author:
        await ctx.send("You cannot adopt yourself!")
        return
    
    data = await get_user_data(ctx.author.id)
    
    if data[1] < 2000:
        await ctx.send("You need 2000 coins to adopt a child!")
        return
    
    target_data = await get_user_data(user.id)
    if target_data[22]:
        await ctx.send(f"{user.mention} already has a parent!")
        return
    
    await update_user_money(ctx.author.id, -2000)
    
    await send_request(ctx.author.id, user.id, "adopt")
    await ctx.send(f"👶 {ctx.author.mention} wants to adopt {user.mention}! They have 5 minutes to type `.accept` to accept the adoption.")

@bot.command(name="family")
@economy_enabled()
@not_blacklisted()
async def family_command(ctx):
    data = await get_user_data(ctx.author.id)
    spouse_id = data[21]
    parent_id = data[22]
    children = await get_children(ctx.author.id)
    
    embed = discord.Embed(title=f"👨‍👩‍👧‍👦 {ctx.author.display_name}'s Family Tree", color=discord.Color.purple())
    
    if spouse_id:
        spouse = await bot.fetch_user(spouse_id)
        embed.add_field(name="💑 Spouse", value=spouse.mention, inline=False)
    else:
        embed.add_field(name="💑 Spouse", value="None", inline=False)
    
    if parent_id:
        parent = await bot.fetch_user(parent_id)
        embed.add_field(name="👪 Parent", value=parent.mention, inline=False)
    else:
        embed.add_field(name="👪 Parent", value="None", inline=False)
    
    if children:
        child_list = []
        for child_id in children:
            child = await bot.fetch_user(child_id)
            child_list.append(child.mention)
        embed.add_field(name="👶 Children", value="\n".join(child_list), inline=False)
    else:
        embed.add_field(name="👶 Children", value="None", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="accept")
@economy_enabled()
@not_blacklisted()
async def accept_request_cmd(ctx, request_id: int = None):
    if request_id is None:
        requests = await get_pending_requests(ctx.author.id)
        if not requests:
            await ctx.send("You have no pending requests.")
            return
        
        embed = discord.Embed(title="📬 Your Pending Requests", color=discord.Color.green())
        for req_id, from_id, req_type in requests:
            user = await bot.fetch_user(from_id)
            embed.add_field(name=f"Request #{req_id}", value=f"From: {user.mention}\nType: {req_type}", inline=False)
        
        embed.add_field(name="How to accept", value="Type `.accept <request_id>` to accept a specific request.", inline=False)
        await ctx.send(embed=embed)
        return
    
    result = await accept_request(request_id)
    if not result:
        await ctx.send("Invalid request ID or request expired.")
        return
    
    from_id, to_id, req_type = result
    from_user = await bot.fetch_user(from_id)
    
    if req_type == "marriage":
        await ctx.send(f"💕 {from_user.mention} and {ctx.author.mention} are now married! Congratulations! 🎉")
    elif req_type == "adopt":
        await ctx.send(f"👶 {from_user.mention} has adopted {ctx.author.mention}! Welcome to the family! 🎉")

@bot.command(name="reject")
@economy_enabled()
@not_blacklisted()
async def reject_request_cmd(ctx, request_id: int):
    await reject_request(request_id)
    await ctx.send(f"✅ Rejected request #{request_id}.")

@bot.command(name="pending")
@economy_enabled()
@not_blacklisted()
async def pending_requests_cmd(ctx):
    requests = await get_pending_requests(ctx.author.id)
    if not requests:
        await ctx.send("You have no pending requests.")
        return
    
    embed = discord.Embed(title="📬 Your Pending Requests", color=discord.Color.orange())
    for req_id, from_id, req_type in requests:
        user = await bot.fetch_user(from_id)
        embed.add_field(name=f"Request #{req_id}", value=f"From: {user.mention}\nType: {req_type}", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name="topcouples")
@economy_enabled()
@not_blacklisted()
async def top_couples(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, spouse_id, affection FROM users WHERE spouse_id IS NOT NULL ORDER BY affection DESC LIMIT 10") as cursor:
            couples = await cursor.fetchall()
    
    if not couples:
        await ctx.send("No couples found.")
        return
    
    embed = discord.Embed(title="💕 Top Couples by Affection", color=discord.Color.pink())
    for idx, (user_id, spouse_id, affection) in enumerate(couples, 1):
        user = await bot.fetch_user(user_id)
        spouse = await bot.fetch_user(spouse_id)
        level = await get_affection_level(affection)
        embed.add_field(name=f"#{idx} - {user.display_name} & {spouse.display_name}", value=f"❤️ {affection} points - {level}", inline=False)
    
    await ctx.send(embed=embed)

# ==================================================
# COGS
# ==================================================
class OwnerCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="addowner")
    @main_owner_only()
    async def add_owner(self, ctx, user_id: int):
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("INSERT OR IGNORE INTO owners (user_id, is_main) VALUES (?, 0)", (user_id,))
            await db.commit()
        await ctx.send(f"Added <@{user_id}> as an owner.")
        await log_action(ctx.author.id, "Add owner", f"Added {user_id}")

    @commands.command(name="removeowner")
    @main_owner_only()
    async def remove_owner(self, ctx, user_id: int):
        if user_id == MAIN_OWNER_ID:
            await ctx.send("Cannot remove the main owner.")
            return
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("DELETE FROM owners WHERE user_id = ?", (user_id,))
            await db.commit()
        await ctx.send(f"Removed <@{user_id}> from owners.")
        await log_action(ctx.author.id, "Remove owner", f"Removed {user_id}")

    @commands.command(name="ownerlist")
    @owner_only()
    async def owner_list(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT user_id, is_main FROM owners") as cursor:
                owners = await cursor.fetchall()
        embed = discord.Embed(title="Bot Owners", color=discord.Color.gold())
        for owner_id, is_main in owners:
            role = "Main Owner" if is_main else "Owner"
            embed.add_field(name=role, value=f"<@{owner_id}>", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="ownerpanel")
    @owner_only()
    async def owner_panel(self, ctx):
        embed = discord.Embed(title="Owner Control Panel", description="Use the commands below to manage the bot.", color=discord.Color.blue())
        embed.add_field(name="Economy", value="`.addmoney`, `.removemoney`, `.setmoney`, `.addbank`, `.removebank`, `.economywipe`, `.toggleeconomy`", inline=False)
        embed.add_field(name="Protection", value="`.protect`, `.unprotect`, `.protectedlist`, `.setroleimmune`, `.removeroleimmune`", inline=False)
        embed.add_field(name="Blacklist", value="`.blacklist`, `.whitelist`", inline=False)
        embed.add_field(name="Settings", value="`.setdailyamount`, `.setsleepamount`, `.setcurrency`, `.togglerob`, `.togglegambling`", inline=False)
        embed.add_field(name="Logs & AntiCheat", value="`.logs`, `.anticheat`", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="addmoney")
    @owner_only()
    async def add_money(self, ctx, user: discord.User, amount: int):
        await update_user_money(user.id, amount)
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"Added {amount}{currency} to {user.mention}.")
        await log_action(ctx.author.id, "Add money", f"User {user.id}, Amount {amount}")

    @commands.command(name="removemoney")
    @owner_only()
    async def remove_money(self, ctx, user: discord.User, amount: int):
        await update_user_money(user.id, -amount)
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"Removed {amount}{currency} from {user.mention}.")
        await log_action(ctx.author.id, "Remove money", f"User {user.id}, Amount {amount}")

    @commands.command(name="setmoney")
    @owner_only()
    async def set_money(self, ctx, user: discord.User, amount: int):
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET money = ? WHERE user_id = ?", (amount, user.id))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"Set {user.mention}'s balance to {amount}{currency}.")
        await log_action(ctx.author.id, "Set money", f"User {user.id}, Amount {amount}")

    @commands.command(name="addbank")
    @owner_only()
    async def add_bank(self, ctx, user: discord.User, amount: int):
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET bank = bank + ? WHERE user_id = ?", (amount, user.id))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"Added {amount}{currency} to {user.mention}'s bank.")
        await log_action(ctx.author.id, "Add bank", f"User {user.id}, Amount {amount}")

    @commands.command(name="removebank")
    @owner_only()
    async def remove_bank(self, ctx, user: discord.User, amount: int):
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET bank = bank - ? WHERE user_id = ?", (amount, user.id))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"Removed {amount}{currency} from {user.mention}'s bank.")
        await log_action(ctx.author.id, "Remove bank", f"User {user.id}, Amount {amount}")

    @commands.command(name="protect")
    @owner_only()
    async def protect_user(self, ctx, user: discord.User):
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET protected = 1 WHERE user_id = ?", (user.id,))
            await db.commit()
        await ctx.send(f"{user.mention} is now protected (cannot be robbed/taxed).")
        await log_action(ctx.author.id, "Protect user", f"User {user.id}")

    @commands.command(name="unprotect")
    @owner_only()
    async def unprotect_user(self, ctx, user: discord.User):
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET protected = 0 WHERE user_id = ?", (user.id,))
            await db.commit()
        await ctx.send(f"{user.mention} is no longer protected.")
        await log_action(ctx.author.id, "Unprotect user", f"User {user.id}")

    @commands.command(name="protectedlist")
    @owner_only()
    async def protected_list(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT user_id FROM users WHERE protected = 1") as cursor:
                users = await cursor.fetchall()
        if not users:
            await ctx.send("No protected users.")
            return
        embed = discord.Embed(title="Protected Users", color=discord.Color.green())
        for user_id in users:
            embed.add_field(name="User", value=f"<@{user_id[0]}>", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="blacklist")
    @owner_only()
    async def blacklist_user(self, ctx, user: discord.User):
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET blacklisted = 1, whitelisted = 0 WHERE user_id = ?", (user.id,))
            await db.commit()
        await ctx.send(f"{user.mention} has been blacklisted.")
        await log_action(ctx.author.id, "Blacklist user", f"User {user.id}")

    @commands.command(name="whitelist")
    @owner_only()
    async def whitelist_user(self, ctx, user: discord.User):
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET blacklisted = 0, whitelisted = 1 WHERE user_id = ?", (user.id,))
            await db.commit()
        await ctx.send(f"{user.mention} has been whitelisted.")
        await log_action(ctx.author.id, "Whitelist user", f"User {user.id}")

    @commands.command(name="setroleimmune")
    @owner_only()
    async def set_role_immune(self, ctx, role: discord.Role):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT immune_roles FROM guild_settings WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
            immune_roles = json.loads(row[0]) if row else []
            if role.id not in immune_roles:
                immune_roles.append(role.id)
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, immune_roles) VALUES (?, ?)",
                (ctx.guild.id, json.dumps(immune_roles))
            )
            await db.commit()
        await ctx.send(f"{role.mention} is now immune to robbery/taxes.")
        await log_action(ctx.author.id, "Set role immune", f"Guild {ctx.guild.id}, Role {role.id}")

    @commands.command(name="removeroleimmune")
    @owner_only()
    async def remove_role_immune(self, ctx, role: discord.Role):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT immune_roles FROM guild_settings WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
            immune_roles = json.loads(row[0]) if row else []
            if role.id in immune_roles:
                immune_roles.remove(role.id)
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, immune_roles) VALUES (?, ?)",
                (ctx.guild.id, json.dumps(immune_roles))
            )
            await db.commit()
        await ctx.send(f"{role.mention} is no longer immune.")
        await log_action(ctx.author.id, "Remove role immune", f"Guild {ctx.guild.id}, Role {role.id}")

    @commands.command(name="economywipe")
    @owner_only()
    async def economy_wipe(self, ctx):
        await ctx.send("⚠️ **WARNING**: This will reset all users' money and bank to 0. Type `confirm` within 30 seconds to proceed.")
        def check(m):
            return m.author == ctx.author and m.content.lower() == "confirm"
        try:
            await bot.wait_for("message", timeout=30.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Economy wipe cancelled.")
            return
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET money = 0, bank = 0")
            await db.commit()
        await ctx.send("Economy has been wiped.")
        await log_action(ctx.author.id, "Economy wipe", "Full wipe performed")

    @commands.command(name="toggleeconomy")
    @owner_only()
    async def toggle_economy(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT economy_enabled FROM guild_settings WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
            current = row[0] if row else 1
            new = 0 if current else 1
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, economy_enabled) VALUES (?, ?)",
                (ctx.guild.id, new)
            )
            await db.commit()
        status = "enabled" if new else "disabled"
        await ctx.send(f"Economy commands have been {status}.")
        await log_action(ctx.author.id, "Toggle economy", f"Guild {ctx.guild.id}, New state {new}")

    @commands.command(name="togglerob")
    @owner_only()
    async def toggle_rob(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT rob_enabled FROM guild_settings WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
            current = row[0] if row else 1
            new = 0 if current else 1
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, rob_enabled) VALUES (?, ?)",
                (ctx.guild.id, new)
            )
            await db.commit()
        status = "enabled" if new else "disabled"
        await ctx.send(f"Rob command has been {status}.")
        await log_action(ctx.author.id, "Toggle rob", f"Guild {ctx.guild.id}, New state {new}")

    @commands.command(name="togglegambling")
    @owner_only()
    async def toggle_gambling(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT gambling_enabled FROM guild_settings WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
            current = row[0] if row else 1
            new = 0 if current else 1
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, gambling_enabled) VALUES (?, ?)",
                (ctx.guild.id, new)
            )
            await db.commit()
        status = "enabled" if new else "disabled"
        await ctx.send(f"Gambling commands have been {status}.")
        await log_action(ctx.author.id, "Toggle gambling", f"Guild {ctx.guild.id}, New state {new}")

    @commands.command(name="setdailyamount")
    @owner_only()
    async def set_daily_amount(self, ctx, amount: int):
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, daily_amount) VALUES (?, ?)",
                (ctx.guild.id, amount)
            )
            await db.commit()
        await ctx.send(f"Daily reward amount set to {amount}.")
        await log_action(ctx.author.id, "Set daily amount", f"Guild {ctx.guild.id}, Amount {amount}")

    @commands.command(name="setsleepamount")
    @owner_only()
    async def set_sleep_amount(self, ctx, amount: int):
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, sleep_amount) VALUES (?, ?)",
                (ctx.guild.id, amount)
            )
            await db.commit()
        await ctx.send(f"Sleep command reward amount set to {amount}.")
        await log_action(ctx.author.id, "Set sleep amount", f"Guild {ctx.guild.id}, Amount {amount}")

    @commands.command(name="setcurrency")
    @owner_only()
    async def set_currency(self, ctx, name: str = None, emoji: str = None):
        async with aiosqlite.connect("hakari.db") as db:
            if name:
                await db.execute(
                    "INSERT OR REPLACE INTO guild_settings (guild_id, currency_name) VALUES (?, ?)",
                    (ctx.guild.id, name)
                )
            if emoji:
                await db.execute(
                    "INSERT OR REPLACE INTO guild_settings (guild_id, currency_emoji) VALUES (?, ?)",
                    (ctx.guild.id, emoji)
                )
            await db.commit()
        await ctx.send(f"Currency updated: Name={name or 'unchanged'}, Emoji={emoji or 'unchanged'}.")
        await log_action(ctx.author.id, "Set currency", f"Guild {ctx.guild.id}, Name {name}, Emoji {emoji}")

    @commands.command(name="logs")
    @owner_only()
    async def view_logs(self, ctx, limit: int = 10):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT timestamp, user_id, action, details FROM logs ORDER BY id DESC LIMIT ?", (limit,)) as cursor:
                logs = await cursor.fetchall()
        if not logs:
            await ctx.send("No logs found.")
            return
        embed = discord.Embed(title="Recent Logs", color=discord.Color.dark_gray())
        for timestamp, user_id, action, details in logs:
            embed.add_field(name=f"{timestamp} - {action}", value=f"User: <@{user_id}>\nDetails: {details}", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="anticheat")
    @owner_only()
    async def anticheat_toggle(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT enabled FROM anticheat_settings WHERE guild_id = ?", (ctx.guild.id,)) as cursor:
                row = await cursor.fetchone()
            current = row[0] if row else 1
            new = 0 if current else 1
            await db.execute(
                "INSERT OR REPLACE INTO anticheat_settings (guild_id, enabled) VALUES (?, ?)",
                (ctx.guild.id, new)
            )
            await db.commit()
        status = "enabled" if new else "disabled"
        await ctx.send(f"Anticheat has been {status}.")
        await log_action(ctx.author.id, "Toggle anticheat", f"Guild {ctx.guild.id}, New state {new}")

class EconomyCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="balance", aliases=["bal"])
    @economy_enabled()
    @not_blacklisted()
    async def balance(self, ctx, user: discord.User = None):
        target = user or ctx.author
        data = await get_user_data(target.id)
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        embed = discord.Embed(title=f"{target.display_name}'s Balance", color=discord.Color.teal())
        embed.add_field(name="Wallet", value=f"{data[1]}{currency}", inline=True)
        embed.add_field(name="Bank", value=f"{data[2]}{currency}", inline=True)
        embed.add_field(name="Total", value=f"{data[1] + data[2]}{currency}", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="daily")
    @economy_enabled()
    @not_blacklisted()
    async def daily(self, ctx):
        data = await get_user_data(ctx.author.id)
        last_daily = data[10]
        if last_daily:
            last = datetime.fromisoformat(last_daily)
            if datetime.utcnow() - last < timedelta(hours=24):
                remaining = timedelta(hours=24) - (datetime.utcnow() - last)
                await ctx.send(f"You already claimed your daily reward. Try again in {remaining.seconds//3600}h {(remaining.seconds%3600)//60}m.")
                return
        amount = await get_guild_setting(ctx.guild.id, "daily_amount")
        await update_user_money(ctx.author.id, amount)
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"You received your daily reward of {amount}{currency}!")

    @commands.command(name="sleep")
    @economy_enabled()
    @not_blacklisted()
    async def sleep(self, ctx):
        data = await get_user_data(ctx.author.id)
        last_work = data[11]
        if last_work:
            last = datetime.fromisoformat(last_work)
            if datetime.utcnow() - last < timedelta(hours=8):
                remaining = timedelta(hours=8) - (datetime.utcnow() - last)
                await ctx.send(f"You need rest! Try again in {remaining.seconds//3600}h {(remaining.seconds%3600)//60}m.")
                return
        amount = await get_guild_setting(ctx.guild.id, "sleep_amount")
        await update_user_money(ctx.author.id, amount)
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET last_work = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"You went to sleep and woke up with {amount}{currency}!")

    @commands.command(name="work")
    @economy_enabled()
    @not_blacklisted()
    async def work(self, ctx):
        data = await get_user_data(ctx.author.id)
        last_work = data[11]
        if last_work:
            last = datetime.fromisoformat(last_work)
            if datetime.utcnow() - last < timedelta(hours=1):
                remaining = timedelta(hours=1) - (datetime.utcnow() - last)
                await ctx.send(f"You're tired. Try again in {remaining.seconds//60} minutes.")
                return
        earnings = random.randint(20, 100)
        await update_user_money(ctx.author.id, earnings)
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET last_work = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"You worked hard and earned {earnings}{currency}!")

    @commands.command(name="rob")
    @economy_enabled()
    @not_blacklisted()
    async def rob(self, ctx, target: discord.User):
        if target == ctx.author:
            await ctx.send("You cannot rob yourself.")
            return
        rob_enabled = await get_guild_setting(ctx.guild.id, "rob_enabled")
        if not rob_enabled:
            await ctx.send("Rob command is disabled.")
            return
        data_target = await get_user_data(target.id)
        if data_target[8]:
            await ctx.send(f"{target.mention} is protected and cannot be robbed.")
            return
        immune_roles = json.loads(await get_guild_setting(ctx.guild.id, "immune_roles"))
        member = ctx.guild.get_member(target.id)
        if member and any(role.id in immune_roles for role in member.roles):
            await ctx.send(f"{target.mention} has an immune role and cannot be robbed.")
            return
        data_author = await get_user_data(ctx.author.id)
        last_rob = data_author[12]
        if last_rob:
            last = datetime.fromisoformat(last_rob)
            if datetime.utcnow() - last < timedelta(minutes=30):
                remaining = timedelta(minutes=30) - (datetime.utcnow() - last)
                await ctx.send(f"You already robbed someone recently. Try again in {remaining.seconds//60} minutes.")
                return
        chance = random.randint(1, 100)
        if chance <= 40:
            steal = random.randint(50, 200)
            if data_target[1] < steal:
                steal = data_target[1]
            await update_user_money(target.id, -steal)
            await update_user_money(ctx.author.id, steal)
            currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
            await ctx.send(f"You successfully robbed {target.mention} and got {steal}{currency}!")
            await log_action(ctx.author.id, "Rob", f"Target {target.id}, Amount {steal}")
        else:
            fine = random.randint(30, 100)
            await update_user_money(ctx.author.id, -fine)
            currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
            await ctx.send(f"You failed to rob {target.mention} and lost {fine}{currency} as a fine!")
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET last_rob = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
            await db.commit()

    @commands.command(name="gamble")
    @economy_enabled()
    @not_blacklisted()
    async def gamble(self, ctx, amount: int):
        gambling_enabled = await get_guild_setting(ctx.guild.id, "gambling_enabled")
        if not gambling_enabled:
            await ctx.send("Gambling is disabled.")
            return
        if amount <= 0:
            await ctx.send("Amount must be positive.")
            return
        data = await get_user_data(ctx.author.id)
        if data[1] < amount:
            await ctx.send("You don't have enough money.")
            return
        win = random.choice([True, False])
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        if win:
            await update_user_money(ctx.author.id, amount)
            await ctx.send(f"You won! You gained {amount}{currency}. New balance: {data[1] + amount}{currency}")
        else:
            await update_user_money(ctx.author.id, -amount)
            await ctx.send(f"You lost! You lost {amount}{currency}. New balance: {data[1] - amount}{currency}")

    @commands.command(name="deposit")
    @economy_enabled()
    @not_blacklisted()
    async def deposit(self, ctx, amount: int):
        data = await get_user_data(ctx.author.id)
        if amount <= 0:
            await ctx.send("Amount must be positive.")
            return
        if data[1] < amount:
            await ctx.send("You don't have enough money in your wallet.")
            return
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET money = money - ?, bank = bank + ? WHERE user_id = ?", (amount, amount, ctx.author.id))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"Deposited {amount}{currency} into your bank.")

    @commands.command(name="withdraw")
    @economy_enabled()
    @not_blacklisted()
    async def withdraw(self, ctx, amount: int):
        data = await get_user_data(ctx.author.id)
        if amount <= 0:
            await ctx.send("Amount must be positive.")
            return
        if data[2] < amount:
            await ctx.send("You don't have enough money in your bank.")
            return
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET money = money + ?, bank = bank - ? WHERE user_id = ?", (amount, amount, ctx.author.id))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"Withdrew {amount}{currency} from your bank.")

    @commands.command(name="pay")
    @economy_enabled()
    @not_blacklisted()
    async def pay(self, ctx, target: discord.User, amount: int):
        if amount <= 0:
            await ctx.send("Amount must be positive.")
            return
        data = await get_user_data(ctx.author.id)
        if data[1] < amount:
            await ctx.send("You don't have enough money.")
            return
        await update_user_money(ctx.author.id, -amount)
        await update_user_money(target.id, amount)
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"You paid {amount}{currency} to {target.mention}.")

class ShopCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="createshop")
    @economy_enabled()
    @not_blacklisted()
    async def create_shop(self, ctx, *, name: str):
        data = await get_user_data(ctx.author.id)
        if data[13]:
            await ctx.send("You already own a shop. Use `.closeshop` first if you want to create a new one.")
            return
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET shop_name = ?, shop_open = 1 WHERE user_id = ?", (name, ctx.author.id))
            await db.commit()
        await ctx.send(f"Your shop '{name}' has been created! Use `.addshopitem` to add items.")

    @commands.command(name="shopinfo")
    @economy_enabled()
    @not_blacklisted()
    async def shop_info(self, ctx, user: discord.User = None):
        target = user or ctx.author
        data = await get_user_data(target.id)
        if not data[13]:
            await ctx.send(f"{target.display_name} does not have a shop.")
            return
        open_status = "Open" if data[20] else "Closed"
        embed = discord.Embed(title=f"{data[13]}", description=f"Owner: {target.display_name}\nStatus: {open_status}", color=discord.Color.purple())
        embed.add_field(name="Reputation", value=data[18], inline=True)
        upgrades = json.loads(data[15])
        embed.add_field(name="Upgrades", value=f"Size: {upgrades.get('size', 1)}\nSlots: {upgrades.get('slots', 5)}\nAdvert: {upgrades.get('advert', 0)}\nTax Reduction: {upgrades.get('tax_reduction', 0)}%", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="shopinventory")
    @economy_enabled()
    @not_blacklisted()
    async def shop_inventory(self, ctx, user: discord.User = None):
        target = user or ctx.author
        data = await get_user_data(target.id)
        if not data[13]:
            await ctx.send(f"{target.display_name} does not have a shop.")
            return
        items = json.loads(data[14])
        if not items:
            await ctx.send("This shop has no items for sale.")
            return
        embed = discord.Embed(title=f"{data[13]} - Inventory", color=discord.Color.gold())
        for item, price in items.items():
            embed.add_field(name=item, value=f"{price} coins", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="addshopitem")
    @economy_enabled()
    @not_blacklisted()
    async def add_shop_item(self, ctx, price: int, *, item_name: str):
        data = await get_user_data(ctx.author.id)
        if not data[13]:
            await ctx.send("You don't have a shop. Use `.createshop` first.")
            return
        if not data[20]:
            await ctx.send("Your shop is closed. Use `.closeshop` to open/close.")
            return
        items = json.loads(data[14])
        upgrades = json.loads(data[15])
        max_slots = 5 + upgrades.get('slots', 0) * 2
        if len(items) >= max_slots:
            await ctx.send(f"Your shop has reached the maximum item slots ({max_slots}). Upgrade your shop with `.upgradeshop`.")
            return
        items[item_name] = price
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), ctx.author.id))
            await db.commit()
        await ctx.send(f"Added '{item_name}' to your shop for {price} coins.")

    @commands.command(name="removeshopitem")
    @economy_enabled()
    @not_blacklisted()
    async def remove_shop_item(self, ctx, *, item_name: str):
        data = await get_user_data(ctx.author.id)
        if not data[13]:
            await ctx.send("You don't have a shop.")
            return
        items = json.loads(data[14])
        if item_name not in items:
            await ctx.send("Item not found in your shop.")
            return
        del items[item_name]
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), ctx.author.id))
            await db.commit()
        await ctx.send(f"Removed '{item_name}' from your shop.")

    @commands.command(name="myshop")
    @economy_enabled()
    @not_blacklisted()
    async def my_shop(self, ctx):
        await self.shop_info(ctx, ctx.author)

    @commands.command(name="visitshop")
    @economy_enabled()
    @not_blacklisted()
    async def visit_shop(self, ctx, user: discord.User):
        data = await get_user_data(user.id)
        if not data[13] or not data[20]:
            await ctx.send(f"{user.display_name} does not have an open shop.")
            return
        await self.shop_inventory(ctx, user)

    @commands.command(name="buyfromshop")
    @economy_enabled()
    @not_blacklisted()
    async def buy_from_shop(self, ctx, seller: discord.User, *, item_name: str):
        seller_data = await get_user_data(seller.id)
        buyer_data = await get_user_data(ctx.author.id)
        if not seller_data[13] or not seller_data[20]:
            await ctx.send(f"{seller.display_name} does not have an open shop.")
            return
        items = json.loads(seller_data[14])
        if item_name not in items:
            await ctx.send("Item not found in that shop.")
            return
        price = items[item_name]
        if buyer_data[1] < price:
            await ctx.send("You don't have enough money.")
            return
        tax_rate = await get_guild_setting(ctx.guild.id, "tax_rate")
        tax = int(price * tax_rate / 100)
        seller_earnings = price - tax
        await update_user_money(ctx.author.id, -price)
        await update_user_money(seller.id, seller_earnings)
        del items[item_name]
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), seller.id))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"You bought '{item_name}' for {price}{currency}. {seller.mention} received {seller_earnings}{currency} after {tax_rate}% tax.")
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET shop_rep = shop_rep + 1 WHERE user_id = ?", (seller.id,))
            await db.commit()

    @commands.command(name="closeshop")
    @economy_enabled()
    @not_blacklisted()
    async def close_shop(self, ctx):
        data = await get_user_data(ctx.author.id)
        if not data[13]:
            await ctx.send("You don't have a shop.")
            return
        new_status = 0 if data[20] else 1
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET shop_open = ? WHERE user_id = ?", (new_status, ctx.author.id))
            await db.commit()
        status = "opened" if new_status else "closed"
        await ctx.send(f"Your shop is now {status}.")

    @commands.command(name="upgradeshop")
    @economy_enabled()
    @not_blacklisted()
    async def upgrade_shop(self, ctx, upgrade: str):
        data = await get_user_data(ctx.author.id)
        if not data[13]:
            await ctx.send("You don't have a shop.")
            return
        upgrades = json.loads(data[15])
        costs = {
            "size": 500,
            "slots": 300,
            "advert": 400,
            "tax_reduction": 600
        }
        if upgrade not in costs:
            await ctx.send("Valid upgrades: size, slots, advert, tax_reduction")
            return
        level = upgrades.get(upgrade, 0)
        cost = costs[upgrade] * (level + 1)
        if data[1] < cost:
            await ctx.send(f"Insufficient funds. Cost: {cost} coins.")
            return
        await update_user_money(ctx.author.id, -cost)
        upgrades[upgrade] = level + 1
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET shop_upgrades = ? WHERE user_id = ?", (json.dumps(upgrades), ctx.author.id))
            await db.commit()
        await ctx.send(f"Upgraded {upgrade} to level {level+1} for {cost} coins.")

    @commands.command(name="collectshopincome")
    @economy_enabled()
    @not_blacklisted()
    async def collect_shop_income(self, ctx):
        data = await get_user_data(ctx.author.id)
        if not data[13] or not data[20]:
            await ctx.send("You need an open shop.")
            return
        last = data[19]
        now = datetime.utcnow()
        if last:
            last_time = datetime.fromisoformat(last)
            hours_passed = (now - last_time).total_seconds() / 3600
            if hours_passed < 1:
                await ctx.send("You can collect passive income every hour.")
                return
        else:
            hours_passed = 0
        upgrades = json.loads(data[15])
        base_income = 20
        size_bonus = 1 + 0.1 * upgrades.get("size", 0)
        advert_bonus = 1 + 0.05 * upgrades.get("advert", 0)
        rep_bonus = 1 + 0.02 * data[18]
        income = int(base_income * size_bonus * advert_bonus * rep_bonus * max(1, hours_passed))
        await update_user_money(ctx.author.id, income)
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET last_shop_income = ? WHERE user_id = ?", (now.isoformat(), ctx.author.id))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"Your shop generated {income}{currency} in passive income!")

    @commands.command(name="globalmarket")
    @economy_enabled()
    @not_blacklisted()
    async def global_market(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT user_id, shop_name FROM users WHERE shop_open = 1 AND shop_name IS NOT NULL") as cursor:
                shops = await cursor.fetchall()
        if not shops:
            await ctx.send("No open shops found.")
            return
        embed = discord.Embed(title="Global Market", color=discord.Color.blue())
        for user_id, name in shops[:10]:
            embed.add_field(name=name, value=f"Owner: <@{user_id}>", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="searchmarket")
    @economy_enabled()
    @not_blacklisted()
    async def search_market(self, ctx, *, item: str):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT user_id, shop_items FROM users WHERE shop_open = 1") as cursor:
                rows = await cursor.fetchall()
        results = []
        for user_id, items_json in rows:
            items = json.loads(items_json)
            if item in items:
                results.append((user_id, items[item]))
        if not results:
            await ctx.send(f"No shop selling '{item}'.")
            return
        embed = discord.Embed(title=f"Shops selling '{item}'", color=discord.Color.green())
        for user_id, price in results[:5]:
            embed.add_field(name=f"<@{user_id}>", value=f"Price: {price} coins", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="topshops")
    @economy_enabled()
    @not_blacklisted()
    async def top_shops(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT user_id, shop_name, shop_rep FROM users WHERE shop_open = 1 ORDER BY shop_rep DESC LIMIT 10") as cursor:
                shops = await cursor.fetchall()
        if not shops:
            await ctx.send("No shops found.")
            return
        embed = discord.Embed(title="Top Shops by Reputation", color=discord.Color.gold())
        for idx, (user_id, name, rep) in enumerate(shops, 1):
            embed.add_field(name=f"#{idx} - {name}", value=f"Owner: <@{user_id}>\nRep: {rep}", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="shoptax")
    @owner_only()
    async def set_shop_tax(self, ctx, percent: int):
        if percent < 0 or percent > 25:
            await ctx.send("Tax must be between 0 and 25.")
            return
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute(
                "INSERT OR REPLACE INTO guild_settings (guild_id, tax_rate) VALUES (?, ?)",
                (ctx.guild.id, percent)
            )
            await db.commit()
        await ctx.send(f"Shop tax rate set to {percent}%.")
        await log_action(ctx.author.id, "Set shop tax", f"Guild {ctx.guild.id}, Tax {percent}")

class BusinessCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="buybusiness")
    @economy_enabled()
    @not_blacklisted()
    async def buy_business(self, ctx, business_type: str):
        valid_types = ["restaurant", "casino", "weaponshop", "cafe", "techstore", "fishingstore"]
        if business_type.lower() not in valid_types:
            await ctx.send(f"Invalid business type. Choose from: {', '.join(valid_types)}")
            return
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT 1 FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
                if await cursor.fetchone():
                    await ctx.send("You already own a business. Sell it first with `.sellbusiness`.")
                    return
        cost = 1000
        data = await get_user_data(ctx.author.id)
        if data[1] < cost:
            await ctx.send(f"You need {cost} coins to buy a business.")
            return
        await update_user_money(ctx.author.id, -cost)
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute(
                "INSERT INTO businesses (user_id, business_type, level, last_collected) VALUES (?, ?, ?, ?)",
                (ctx.author.id, business_type.lower(), 1, datetime.utcnow().isoformat())
            )
            await db.commit()
        await ctx.send(f"You bought a {business_type} business for {cost} coins!")

    @commands.command(name="business")
    @economy_enabled()
    @not_blacklisted()
    async def business_info(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT business_type, level, last_collected FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            await ctx.send("You don't own a business.")
            return
        business_type, level, last_collected = row
        embed = discord.Embed(title=f"Your {business_type} Business", color=discord.Color.orange())
        embed.add_field(name="Level", value=level, inline=True)
        embed.add_field(name="Passive Income Base", value=50 * level, inline=True)
        if last_collected:
            last = datetime.fromisoformat(last_collected)
            hours = (datetime.utcnow() - last).total_seconds() / 3600
            if hours >= 1:
                embed.add_field(name="Pending Profits", value=f"~{int(50 * level * hours)} coins", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="upgradebusiness")
    @economy_enabled()
    @not_blacklisted()
    async def upgrade_business(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT level FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            await ctx.send("You don't own a business.")
            return
        level = row[0]
        cost = 500 * level
        data = await get_user_data(ctx.author.id)
        if data[1] < cost:
            await ctx.send(f"Upgrade to level {level+1} costs {cost} coins.")
            return
        await update_user_money(ctx.author.id, -cost)
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE businesses SET level = level + 1 WHERE user_id = ?", (ctx.author.id,))
            await db.commit()
        await ctx.send(f"Your business is now level {level+1}!")

    @commands.command(name="collectprofits")
    @economy_enabled()
    @not_blacklisted()
    async def collect_profits(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT level, last_collected FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            await ctx.send("You don't own a business.")
            return
        level, last_collected = row
        now = datetime.utcnow()
        last = datetime.fromisoformat(last_collected)
        hours = (now - last).total_seconds() / 3600
        if hours < 1:
            await ctx.send("You can collect profits every hour.")
            return
        profit = int(50 * level * hours)
        await update_user_money(ctx.author.id, profit)
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE businesses SET last_collected = ? WHERE user_id = ?", (now.isoformat(), ctx.author.id))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"You collected {profit}{currency} from your business!")

    @commands.command(name="sellbusiness")
    @economy_enabled()
    @not_blacklisted()
    async def sell_business(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT level FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
                row = await cursor.fetchone()
        if not row:
            await ctx.send("You don't own a business.")
            return
        level = row[0]
        value = 500 * level
        await update_user_money(ctx.author.id, value)
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("DELETE FROM businesses WHERE user_id = ?", (ctx.author.id,))
            await db.commit()
        currency = await get_guild_setting(ctx.guild.id, "currency_emoji")
        await ctx.send(f"You sold your business for {value}{currency}.")

    @commands.command(name="businessleaderboard")
    @economy_enabled()
    @not_blacklisted()
    async def business_leaderboard(self, ctx):
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT user_id, business_type, level FROM businesses ORDER BY level DESC LIMIT 10") as cursor:
                businesses = await cursor.fetchall()
        if not businesses:
            await ctx.send("No businesses found.")
            return
        embed = discord.Embed(title="Top Businesses", color=discord.Color.purple())
        for idx, (user_id, biz_type, level) in enumerate(businesses, 1):
            embed.add_field(name=f"#{idx} - {biz_type.title()}", value=f"Owner: <@{user_id}>\nLevel: {level}", inline=False)
        await ctx.send(embed=embed)

class LeaderboardCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="globalleaderboard", aliases=["glb"])
    async def global_leaderboard(self, ctx, category: str = "money"):
        if category not in ["money", "xp", "gangs", "families"]:
            await ctx.send("Valid categories: money, xp, gangs, families")
            return
        async with aiosqlite.connect("hakari.db") as db:
            if category == "money":
                async with db.execute("SELECT user_id, money+bank as total FROM users ORDER BY total DESC LIMIT 10") as cursor:
                    rows = await cursor.fetchall()
                title = "Global Richest Users"
                value_func = lambda row: f"{row[1]} coins"
            elif category == "xp":
                async with db.execute("SELECT user_id, total_xp FROM users ORDER BY total_xp DESC LIMIT 10") as cursor:
                    rows = await cursor.fetchall()
                title = "Global Top XP"
                value_func = lambda row: f"{row[1]} XP (Level {int((row[1]/100)**0.5)})"
            elif category == "gangs":
                async with db.execute("SELECT gang, SUM(money+bank) as total FROM users WHERE gang IS NOT NULL GROUP BY gang ORDER BY total DESC LIMIT 10") as cursor:
                    rows = await cursor.fetchall()
                title = "Top Gangs by Wealth"
                value_func = lambda row: f"{row[0]} - {row[1]} coins"
            else:
                async with db.execute("SELECT family, SUM(money+bank) as total FROM users WHERE family IS NOT NULL GROUP BY family ORDER BY total DESC LIMIT 10") as cursor:
                    rows = await cursor.fetchall()
                title = "Top Families by Wealth"
                value_func = lambda row: f"{row[0]} - {row[1]} coins"
        if not rows:
            await ctx.send("No data available.")
            return
        embed = discord.Embed(title=title, color=discord.Color.gold())
        for idx, row in enumerate(rows, 1):
            if category in ["money", "xp"]:
                user_id = row[0]
                try:
                    user = await bot.fetch_user(user_id)
                    name = user.display_name if user else str(user_id)
                except:
                    name = str(user_id)
                embed.add_field(name=f"#{idx} - {name}", value=value_func(row), inline=False)
            else:
                embed.add_field(name=f"#{idx}", value=value_func(row), inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="serverleaderboard", aliases=["slb"])
    async def server_leaderboard(self, ctx, category: str = "money"):
        if category not in ["money", "xp"]:
            await ctx.send("Valid categories: money, xp")
            return
        members = ctx.guild.members
        user_data = []
        async with aiosqlite.connect("hakari.db") as db:
            for member in members:
                if member.bot:
                    continue
                async with db.execute("SELECT money, bank, total_xp FROM users WHERE user_id = ?", (member.id,)) as cursor:
                    row = await cursor.fetchone()
                if row:
                    if category == "money":
                        total = row[0] + row[1]
                        user_data.append((member, total))
                    else:
                        user_data.append((member, row[2]))
        user_data.sort(key=lambda x: x[1], reverse=True)
        top = user_data[:10]
        if not top:
            await ctx.send("No data available.")
            return
        title = f"Server {'Richest' if category=='money' else 'Top XP'} - {ctx.guild.name}"
        embed = discord.Embed(title=title, color=discord.Color.blue())
        for idx, (member, value) in enumerate(top, 1):
            if category == "money":
                embed.add_field(name=f"#{idx} - {member.display_name}", value=f"{value} coins", inline=False)
            else:
                embed.add_field(name=f"#{idx} - {member.display_name}", value=f"{value} XP", inline=False)
        await ctx.send(embed=embed)

# ==================================================
# EVENTS
# ==================================================
@bot.event
async def on_ready():
    await init_db()
    print(f"✅ Logged in as {bot.user}")
    print(f"✅ Bot is ready!")
    print(f"✅ Serving {len(bot.guilds)} servers")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    xp_gain = random.randint(10, 20)
    new_level = await add_xp(message.author.id, xp_gain)
    if new_level:
        await message.channel.send(f"🎉 {message.author.mention} leveled up to level {new_level}!")
    await bot.process_commands(message)

# ==================================================
# RUN BOT
# ==================================================
if __name__ == "__main__":
    bot.add_cog(OwnerCommands(bot))
    bot.add_cog(EconomyCommands(bot))
    bot.add_cog(ShopCommands(bot))
    bot.add_cog(BusinessCommands(bot))
    bot.add_cog(LeaderboardCommands(bot))
    bot.run(TOKEN)
