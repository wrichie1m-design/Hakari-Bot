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
CUSTOM_CURRENCY_EMOJI_ID = 1508331993266524251  # Your custom coin emoji

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

gambling_cooldowns = {}
recent_message_authors = {}
active_wordle_games = {}
invite_cache = {}
custom_currency_emoji = None  # Will be set in on_ready

# ==================================================
# NUMBER FORMATTING
# ==================================================
def parse_amount(amount_str: str):
    if amount_str.lower() in ["all", "half"]:
        return amount_str.lower()
    amount_str = amount_str.lower().strip()
    mult = {
        'k': 1_000, 'm': 1_000_000, 'b': 1_000_000_000, 't': 1_000_000_000_000,
        'q': 1_000_000_000_000_000, 'Q': 1_000_000_000_000_000_000,
        'sx': 1_000_000_000_000_000_000_000, 'sp': 1_000_000_000_000_000_000_000_000,
        'oc': 1_000_000_000_000_000_000_000_000_000,
        'no': 1_000_000_000_000_000_000_000_000_000_000,
        'dc': 1_000_000_000_000_000_000_000_000_000_000_000,
        'udc': 10**36, 'ddc': 10**39, 'tdc': 10**42, 'qadc': 10**45,
        'qidc': 10**48, 'sxdc': 10**51, 'spdc': 10**54, 'ocdc': 10**57,
        'nodc': 10**60, 'vgdc': 10**63,
    }
    for suffix in sorted(mult, key=len, reverse=True):
        if amount_str.endswith(suffix):
            num_part = amount_str[:-len(suffix)]
            if '.' in num_part:
                int_part, dec_part = num_part.split('.', 1)
                dec_factor = 10 ** len(dec_part)
                value = (int(int_part) * mult[suffix] * dec_factor + int(dec_part) * mult[suffix]) // dec_factor
            else:
                value = int(num_part) * mult[suffix]
            return value
    try:
        return int(amount_str)
    except ValueError:
        raise ValueError("Invalid amount")

def format_number(num: int) -> str:
    if num < 0:
        return "0"
    if num < 1_000:
        return str(num)
    tiers = [
        (10**63, "vgdc"), (10**60, "nodc"), (10**57, "ocdc"),
        (10**54, "spdc"), (10**51, "sxdc"), (10**48, "qidc"),
        (10**45, "qadc"), (10**42, "tdc"), (10**39, "ddc"),
        (10**36, "udc"), (10**33, "dc"), (10**30, "no"),
        (10**27, "oc"), (10**24, "sp"), (10**21, "sx"),
        (10**18, "Q"), (10**15, "q"), (10**12, "t"),
        (10**9, "b"), (10**6, "m"), (10**3, "k"),
    ]
    for divisor, suffix in tiers:
        if num >= divisor:
            whole = num // divisor
            remainder = num % divisor
            decimal = (remainder * 10) // divisor
            if decimal == 0:
                return f"{whole}{suffix}"
            return f"{whole}.{decimal}{suffix}"
    return str(num)

# ==================================================
# DATABASE SETUP
# ==================================================
async def init_db():
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS owners (
            user_id INTEGER PRIMARY KEY, is_main INTEGER DEFAULT 0)''')
        await db.execute("INSERT OR IGNORE INTO owners VALUES (?,1)", (MAIN_OWNER_ID,))
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            money TEXT DEFAULT '0',
            bank TEXT DEFAULT '0',
            xp INTEGER DEFAULT 0, level INTEGER DEFAULT 0, total_xp INTEGER DEFAULT 0,
            protected INTEGER DEFAULT 0, blacklisted INTEGER DEFAULT 0, tax_exempt INTEGER DEFAULT 0,
            last_daily TIMESTAMP, last_work TIMESTAMP, last_rob TIMESTAMP,
            last_sleep TIMESTAMP, last_crime TIMESTAMP, last_interest TIMESTAMP,
            daily_messages INTEGER DEFAULT 0,
            shop_name TEXT, shop_items TEXT DEFAULT '{}', shop_open INTEGER DEFAULT 0,
            spouse_id INTEGER, parent_id INTEGER, affection INTEGER DEFAULT 0,
            gang TEXT, loan_amount TEXT DEFAULT '0', loan_taken_at TIMESTAMP,
            business_daily TIMESTAMP, security_until TIMESTAMP,
            invite_count INTEGER DEFAULT 0, invite_joins INTEGER DEFAULT 0,
            invite_left INTEGER DEFAULT 0, invite_fake INTEGER DEFAULT 0,
            invite_rejoins INTEGER DEFAULT 0,
            quest_data TEXT DEFAULT '{}', quest_last_reset TIMESTAMP,
            badges TEXT DEFAULT '[]', showcase_badges TEXT DEFAULT '[]',
            last_heist TIMESTAMP, lottery_tickets INTEGER DEFAULT 0, lottery_last_tickets TIMESTAMP,
            gambling_won INTEGER DEFAULT 0, gambling_lost INTEGER DEFAULT 0,
            last_message TIMESTAMP
        )''')
        for col in ["security_until TIMESTAMP", "invite_count INTEGER DEFAULT 0",
                     "invite_joins INTEGER DEFAULT 0", "invite_left INTEGER DEFAULT 0",
                     "invite_fake INTEGER DEFAULT 0", "invite_rejoins INTEGER DEFAULT 0",
                     "quest_data TEXT DEFAULT '{}'", "quest_last_reset TIMESTAMP",
                     "badges TEXT DEFAULT '[]'", "showcase_badges TEXT DEFAULT '[]'",
                     "last_heist TIMESTAMP", "lottery_tickets INTEGER DEFAULT 0", "lottery_last_tickets TIMESTAMP",
                     "gambling_won INTEGER DEFAULT 0", "gambling_lost INTEGER DEFAULT 0",
                     "last_message TIMESTAMP"]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except:
                pass
        await db.execute('''CREATE TABLE IF NOT EXISTS invite_codes (
            code TEXT PRIMARY KEY,
            guild_id INTEGER,
            inviter_id INTEGER,
            uses INTEGER DEFAULT 0,
            created_at TIMESTAMP
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS children (
            parent_id INTEGER, child_id INTEGER, PRIMARY KEY (parent_id, child_id))''')
        await db.execute('''CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, from_id INTEGER, to_id INTEGER,
            request_type TEXT, timestamp TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS businesses (
            user_id INTEGER PRIMARY KEY, business_type TEXT, level INTEGER DEFAULT 1,
            last_collected TIMESTAMP, daily_bonus_collected TIMESTAMP, reputation INTEGER DEFAULT 0)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            economy_enabled INTEGER DEFAULT 1, rob_enabled INTEGER DEFAULT 1,
            gambling_enabled INTEGER DEFAULT 1, daily_amount INTEGER DEFAULT 1500,
            daily_messages_needed INTEGER DEFAULT 10,
            sleep_amount_min INTEGER DEFAULT 2000, sleep_amount_max INTEGER DEFAULT 2500,
            work_amount_min INTEGER DEFAULT 150, work_amount_max INTEGER DEFAULT 300,
            crime_amount_min INTEGER DEFAULT 200, crime_amount_max INTEGER DEFAULT 800,
            interest_rate INTEGER DEFAULT 5, max_withdraw INTEGER DEFAULT 999999999,
            loan_interest INTEGER DEFAULT 10, currency_emoji TEXT DEFAULT '💰',
            invite_reward_amount TEXT DEFAULT '50000000', invite_threshold INTEGER DEFAULT 3,
            lottery_jackpot TEXT DEFAULT '0', lottery_tickets_sold INTEGER DEFAULT 0,
            lottery_last_draw TIMESTAMP
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS heist_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            leader_id INTEGER, member_ids TEXT DEFAULT '[]',
            status TEXT DEFAULT 'forming', created_at TIMESTAMP
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, user_id INTEGER,
            action TEXT, details TEXT)''')
        await db.commit()
        for guild in bot.guilds:
            await db.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild.id,))
        await db.commit()
    print("Database ready.")

# ==================================================
# BACKGROUND TASKS
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
async def before_loan(): await bot.wait_until_ready()

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
            interest = int(min(bank, 50000) * rate / 100)
            if interest:
                await db.execute("UPDATE users SET bank = ?, last_interest = ? WHERE user_id = ?",
                                 (str(bank + interest), datetime.now(timezone.utc).isoformat(), uid))
        await db.commit()
@bank_interest.before_loop
async def before_bank(): await bot.wait_until_ready()

@tasks.loop(hours=168)
async def lottery_draw():
    async with aiosqlite.connect("hakari.db") as db:
        for guild in bot.guilds:
            guild_id = guild.id
            jackpot_str = await get_setting(guild_id, "lottery_jackpot")
            jackpot = int(jackpot_str) if jackpot_str else 0
            tickets_sold = await get_setting(guild_id, "lottery_tickets_sold")
            if jackpot > 0 and tickets_sold > 0:
                async with db.execute("SELECT user_id, lottery_tickets FROM users WHERE lottery_tickets > 0") as cur:
                    rows = await cur.fetchall()
                total_tickets = sum(r[1] for r in rows)
                if total_tickets == 0:
                    continue
                ticket_winner = random.randint(1, total_tickets)
                winner_id = None
                for uid, tickets in rows:
                    ticket_winner -= tickets
                    if ticket_winner <= 0:
                        winner_id = uid
                        break
                if winner_id:
                    await update_money(winner_id, jackpot)
                    try:
                        channel = guild.system_channel or guild.text_channels[0]
                        await channel.send(f"🎰 Weekly lottery winner: <@{winner_id}> won {format_number(jackpot)} {await get_setting(guild_id, 'currency_emoji')}!")
                    except:
                        pass
                await db.execute("UPDATE guild_settings SET lottery_jackpot = '0', lottery_tickets_sold = 0 WHERE guild_id = ?", (guild_id,))
                await db.execute("UPDATE users SET lottery_tickets = 0")
        await db.commit()
@lottery_draw.before_loop
async def before_lottery(): await bot.wait_until_ready()

# ==================================================
# DATABASE HELPERS
# ==================================================
async def get_user(uid):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT * FROM users WHERE user_id=?", (uid,)) as cur:
            row = await cur.fetchone()
        if row:
            cols = [d[0] for d in cur.description]
            data = dict(zip(cols, row))
            data['money'] = int(data.get('money','0'))
            data['bank'] = int(data.get('bank','0'))
            data['loan_amount'] = int(data.get('loan_amount','0'))
            data['invite_joins'] = int(data.get('invite_joins',0))
            data['invite_left'] = int(data.get('invite_left',0))
            data['invite_fake'] = int(data.get('invite_fake',0))
            data['invite_rejoins'] = int(data.get('invite_rejoins',0))
            data['gambling_won'] = int(data.get('gambling_won',0))
            data['gambling_lost'] = int(data.get('gambling_lost',0))
            data['lottery_tickets'] = int(data.get('lottery_tickets',0))
            return data
        await db.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        await db.commit()
        async with db.execute("SELECT * FROM users WHERE user_id=?", (uid,)) as cur2:
            row2 = await cur2.fetchone()
            cols2 = [d[0] for d in cur2.description]
            data2 = dict(zip(cols2, row2))
            data2['money'] = int(data2.get('money','0'))
            data2['bank'] = int(data2.get('bank','0'))
            data2['loan_amount'] = int(data2.get('loan_amount','0'))
            data2['invite_joins'] = int(data2.get('invite_joins',0))
            data2['invite_left'] = int(data2.get('invite_left',0))
            data2['invite_fake'] = int(data2.get('invite_fake',0))
            data2['invite_rejoins'] = int(data2.get('invite_rejoins',0))
            data2['gambling_won'] = int(data2.get('gambling_won',0))
            data2['gambling_lost'] = int(data2.get('gambling_lost',0))
            data2['lottery_tickets'] = int(data2.get('lottery_tickets',0))
            return data2

async def update_money(uid, amount):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT money FROM users WHERE user_id=?", (uid,)) as cur:
            row = await cur.fetchone()
        cur_money = int(row[0]) if row else 0
        new = max(0, cur_money + amount)
        await db.execute("UPDATE users SET money=? WHERE user_id=?", (str(new), uid))
        await db.commit()
        if amount > 0:
            await check_badges(uid)

async def update_bank(uid, amount):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT bank FROM users WHERE user_id=?", (uid,)) as cur:
            row = await cur.fetchone()
        cur_bank = int(row[0]) if row else 0
        new = max(0, cur_bank + amount)
        await db.execute("UPDATE users SET bank=? WHERE user_id=?", (str(new), uid))
        await db.commit()

async def update_gambling_stats(uid, won=0, lost=0):
    async with aiosqlite.connect("hakari.db") as db:
        if won:
            await db.execute("UPDATE users SET gambling_won = gambling_won + ? WHERE user_id = ?", (won, uid))
        if lost:
            await db.execute("UPDATE users SET gambling_lost = gambling_lost + ? WHERE user_id = ?", (lost, uid))
        await db.commit()

async def update_affection(uid, amount):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET affection=affection+? WHERE user_id=?", (amount, uid))
        await db.commit()

async def set_affection(uid, amount):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET affection=? WHERE user_id=?", (amount, uid))
        await db.commit()

async def log_action(uid, action, details=""):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO logs (timestamp,user_id,action,details) VALUES (?,?,?,?)",
                         (datetime.now(timezone.utc).isoformat(), uid, action, details))
        await db.commit()

async def get_setting(gid, setting):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute(f"SELECT {setting} FROM guild_settings WHERE guild_id=?", (gid,)) as cur:
            row = await cur.fetchone()
        if row: result = row[0]
        else: result = None
    defaults = {"economy_enabled":1,"rob_enabled":1,"gambling_enabled":1,"daily_amount":1500,
                "daily_messages_needed":10,"sleep_amount_min":2000,"sleep_amount_max":2500,
                "work_amount_min":150,"work_amount_max":300,"crime_amount_min":200,"crime_amount_max":800,
                "interest_rate":5,"max_withdraw":999999999,"loan_interest":10,"currency_emoji":"💰",
                "invite_reward_amount":"50000000","invite_threshold":3,
                "lottery_jackpot":"0","lottery_tickets_sold":0}
    if result is None:
        result = defaults.get(setting, 1)
    # Override default currency emoji with custom emoji if set and not changed by server
    if setting == "currency_emoji" and result == "💰" and custom_currency_emoji:
        return custom_currency_emoji
    return result

async def is_owner(uid): return (await db_fetchone("SELECT 1 FROM owners WHERE user_id=?", (uid,))) is not None
async def is_main_owner(uid): row = await db_fetchone("SELECT is_main FROM owners WHERE user_id=?", (uid,)); return row and row[0]==1
async def is_blacklisted(uid): return (await get_user(uid)).get("blacklisted",0)==1
async def is_protected(uid): return (await get_user(uid)).get("protected",0)==1
async def is_tax_exempt(uid): return (await get_user(uid)).get("tax_exempt",0)==1
async def has_security(uid):
    data = await get_user(uid)
    until = data.get('security_until')
    if until:
        until_dt = datetime.fromisoformat(until)
        if datetime.now(timezone.utc) < until_dt:
            return True
    return False

async def db_fetchone(query, params=()):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute(query, params) as cur:
            return await cur.fetchone()

async def add_xp(uid, amount):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
        await db.execute("UPDATE users SET xp=xp+?, total_xp=total_xp+? WHERE user_id=?", (amount, amount, uid))
        await db.commit()
        async with db.execute("SELECT total_xp, level FROM users WHERE user_id=?", (uid,)) as cur:
            row = await cur.fetchone()
            if row:
                total,lvl = row
                new_lvl = int((total/100)**0.5)
                if new_lvl > lvl:
                    await db.execute("UPDATE users SET level=? WHERE user_id=?", (new_lvl, uid))
                    await db.commit()
                    return new_lvl
    return None

async def get_bet_amount(ctx, amt_str, check=True):
    data = await get_user(ctx.author.id)
    if amt_str.lower() == "all":
        amount = data['money']
    elif amt_str.lower() == "half":
        amount = data['money'] // 2
    else:
        try:
            amount = parse_amount(amt_str)
        except:
            return None, "Invalid amount."
    if amount <= 0:
        return None, "Positive amount required."
    if check and data['money'] < amount:
        return None, f"You have {format_number(data['money'])} coins."
    return amount, None

def economy_check():
    async def pred(ctx):
        if await get_setting(ctx.guild.id,"economy_enabled")==0: await ctx.send("Economy disabled."); return False
        if await is_blacklisted(ctx.author.id): await ctx.send("Blacklisted."); return False
        return True
    return commands.check(pred)

def owner_only():
    async def pred(ctx):
        if await is_owner(ctx.author.id): return True
        await ctx.send("Owner only."); return False
    return commands.check(pred)

def main_owner_only():
    async def pred(ctx):
        if await is_main_owner(ctx.author.id): return True
        await ctx.send("Main owner only."); return False
    return commands.check(pred)

def gambling_cooldown_check():
    async def pred(ctx):
        if await get_setting(ctx.guild.id,"gambling_enabled")==0: await ctx.send("Gambling disabled."); return False
        if ctx.author.id in gambling_cooldowns and datetime.now(timezone.utc) < gambling_cooldowns[ctx.author.id]:
            await ctx.send("Wait a few seconds before gambling again."); return False
        return True
    return commands.check(pred)

async def set_gambling_cooldown(uid, seconds=3):
    gambling_cooldowns[uid] = datetime.now(timezone.utc) + timedelta(seconds=seconds)

# ==================================================
# INVITE TRACKING SYSTEM
# ==================================================
async def cache_invites():
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            invite_cache[guild.id] = {}
            for inv in invites:
                invite_cache[guild.id][inv.code] = inv.uses
            print(f"Cached {len(invites)} invites for {guild.name}")
        except Exception as e:
            print(f"Failed to cache invites for {guild.name}: {e}")
            invite_cache[guild.id] = {}

async def update_invite_cache(guild):
    try:
        invites = await guild.invites()
        if guild.id not in invite_cache:
            invite_cache[guild.id] = {}
        for inv in invites:
            invite_cache[guild.id][inv.code] = inv.uses
    except:
        pass

async def find_used_invite(guild):
    try:
        new_invites = await guild.invites()
        old_cache = invite_cache.get(guild.id, {})
        used_invite = None
        for inv in new_invites:
            old_uses = old_cache.get(inv.code, 0)
            if inv.uses > old_uses:
                used_invite = inv
                break
        if guild.id not in invite_cache:
            invite_cache[guild.id] = {}
        for inv in new_invites:
            invite_cache[guild.id][inv.code] = inv.uses
        return used_invite
    except Exception as e:
        print(f"Error finding used invite: {e}")
        await update_invite_cache(guild)
        return None

@bot.event
async def on_invite_create(invite):
    if invite.guild.id not in invite_cache:
        invite_cache[invite.guild.id] = {}
    invite_cache[invite.guild.id][invite.code] = invite.uses
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute(
            "INSERT OR REPLACE INTO invite_codes (code, guild_id, inviter_id, uses, created_at) VALUES (?,?,?,?,?)",
            (invite.code, invite.guild.id, invite.inviter.id, invite.uses, datetime.now(timezone.utc).isoformat())
        )
        await db.commit()

@bot.event
async def on_invite_delete(invite):
    if invite.guild.id in invite_cache:
        invite_cache[invite.guild.id].pop(invite.code, None)

@bot.event
async def on_member_join(member):
    if member.bot:
        return
    guild = member.guild
    await asyncio.sleep(0.5)
    try:
        used_invite = await find_used_invite(guild)
        if used_invite and used_invite.inviter:
            inviter_id = used_invite.inviter.id
            account_age = (datetime.now(timezone.utc) - member.created_at.replace(tzinfo=timezone.utc)).days
            is_fake = account_age < 30
            async with aiosqlite.connect("hakari.db") as db:
                if is_fake:
                    await db.execute("UPDATE users SET invite_fake = invite_fake + 1 WHERE user_id = ?", (inviter_id,))
                else:
                    await db.execute("UPDATE users SET invite_joins = invite_joins + 1, invite_count = invite_count + 1 WHERE user_id = ?", (inviter_id,))
                await db.execute("UPDATE invite_codes SET uses = ? WHERE code = ?", (used_invite.uses, used_invite.code))
                await db.commit()
    except Exception as e:
        print(f"Error in member join handler: {e}")
        await update_invite_cache(guild)

@bot.event
async def on_member_remove(member):
    if member.bot:
        return
    guild = member.guild
    try:
        current_invites = await guild.invites()
        old_cache = invite_cache.get(guild.id, {})
        for inv in current_invites:
            old_uses = old_cache.get(inv.code)
            if old_uses is not None and inv.uses < old_uses:
                inviter_id = None
                async with aiosqlite.connect("hakari.db") as db:
                    async with db.execute("SELECT inviter_id FROM invite_codes WHERE code = ?", (inv.code,)) as cur:
                        row = await cur.fetchone()
                        if row:
                            inviter_id = row[0]
                    if inviter_id:
                        await db.execute("UPDATE users SET invite_left = invite_left + 1 WHERE user_id = ?", (inviter_id,))
                        await db.commit()
                break
        for inv in current_invites:
            invite_cache[guild.id][inv.code] = inv.uses
    except Exception as e:
        print(f"Error in member leave handler: {e}")
        await update_invite_cache(guild)

@bot.event
async def on_guild_join(guild):
    await update_invite_cache(guild)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild.id,))
        await db.commit()

@bot.event
async def on_guild_remove(guild):
    if guild.id in invite_cache:
        del invite_cache[guild.id]

@bot.command(name="ci", aliases=["createinvite"])
@economy_check()
async def create_invite(ctx, max_uses: int = 0, max_age: int = 0):
    try:
        invite = await ctx.channel.create_invite(max_uses=max_uses if max_uses > 0 else 0, max_age=max_age if max_age > 0 else 0, reason=f"Created by {ctx.author.name}")
        if ctx.guild.id not in invite_cache:
            invite_cache[ctx.guild.id] = {}
        invite_cache[ctx.guild.id][invite.code] = invite.uses
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("INSERT OR REPLACE INTO invite_codes (code, guild_id, inviter_id, uses, created_at) VALUES (?,?,?,?,?)",
                             (invite.code, ctx.guild.id, ctx.author.id, invite.uses, datetime.now(timezone.utc).isoformat()))
            await db.commit()
        embed = discord.Embed(title="📨 Invite Created", color=0x2ecc71)
        embed.add_field(name="🔗 Link", value=f"https://discord.gg/{invite.code}", inline=False)
        embed.add_field(name="👤 Max Uses", value=str(max_uses) if max_uses > 0 else "Unlimited", inline=True)
        embed.add_field(name="⏰ Expires", value=f"{max_age}s" if max_age > 0 else "Never", inline=True)
        embed.set_footer(text=f"Created by {ctx.author.name}")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Failed to create invite: {e}")

@bot.command(name="i", aliases=["invites", "inv"])
@economy_check()
async def invite_stats(ctx, user: discord.User = None):
    if user is None:
        user = ctx.author
    data = await get_user(user.id)
    joins = data.get('invite_joins', 0)
    left = data.get('invite_left', 0)
    fake = data.get('invite_fake', 0)
    total = joins + fake
    embed = discord.Embed(title="Invites", color=0x2b2d31)
    embed.set_author(name=user.name, icon_url=user.avatar.url if user.avatar else user.default_avatar.url)
    embed.add_field(name="🟢 Regular", value=f"`{joins}`", inline=True)
    embed.add_field(name="🔴 Left", value=f"`{left}`", inline=True)
    embed.add_field(name="🟡 Fake", value=f"`{fake}`", inline=True)
    embed.add_field(name="📊 Total", value=f"`{total}`", inline=True)
    embed.set_footer(text=f"Requested by {ctx.author.name}")
    embed.timestamp = datetime.now(timezone.utc)
    await ctx.send(embed=embed)

@bot.command(name="lb", aliases=["leaderboard"])
@economy_check()
async def leaderboard_cmd(ctx, category: str = "i"):
    if category.lower() in ["i", "inv", "invites"]:
        await invite_leaderboard(ctx)
    elif category.lower() in ["money", "bal", "balance"]:
        await server_money_leaderboard(ctx)
    elif category.lower() in ["xp", "level", "levels"]:
        await server_xp_leaderboard(ctx)
    else:
        await ctx.send("Usage: `.lb i` (invites), `.lb money` (money), `.lb xp` (xp)")

async def invite_leaderboard(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute(
            "SELECT user_id, invite_joins, invite_left, invite_fake FROM users WHERE invite_joins > 0 OR invite_fake > 0 ORDER BY (invite_joins + invite_fake) DESC LIMIT 10"
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        return await ctx.send("No invite data yet!")
    embed = discord.Embed(title="🏆 Invite Leaderboard", color=0x2b2d31)
    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
    description = ""
    for i, (uid, joins, left, fake) in enumerate(rows, 1):
        user = ctx.guild.get_member(uid)
        if user:
            total = joins + fake
            description += f"`{i}` **{user.name}** • {total:,} invites\n"
        else:
            total = joins + fake
            description += f"`{i}` **Unknown User** • {total:,} invites\n"
    embed.description = description
    embed.set_footer(text=f"Top 10 inviters in {ctx.guild.name}")
    await ctx.send(embed=embed)

async def server_money_leaderboard(ctx):
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    members = [m for m in ctx.guild.members if not m.bot]
    data = []
    for m in members:
        ud = await get_user(m.id)
        total = ud['money'] + ud['bank']
        if total > 0:
            data.append((m.id, m.display_name, total))
    data.sort(key=lambda x: x[2], reverse=True)
    data = data[:10]
    if not data:
        return await ctx.send("No money data yet!")
    embed = discord.Embed(title="🏆 Money Leaderboard", color=0x2b2d31)
    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
    description = ""
    for i, (uid, name, total) in enumerate(data, 1):
        description += f"`{i}` **{name}** • {format_number(total)} {emoji}\n"
    embed.description = description
    embed.set_footer(text=f"Top 10 richest in {ctx.guild.name}")
    await ctx.send(embed=embed)

async def server_xp_leaderboard(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        data = []
        for m in ctx.guild.members:
            if not m.bot:
                async with db.execute("SELECT total_xp FROM users WHERE user_id=?", (m.id,)) as cur:
                    row = await cur.fetchone()
                if row and row[0] > 0:
                    data.append((m.id, m.display_name, row[0]))
        data.sort(key=lambda x: x[2], reverse=True)
        data = data[:10]
    if not data:
        return await ctx.send("No XP data yet!")
    embed = discord.Embed(title="🏆 XP Leaderboard", color=0x2b2d31)
    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
    description = ""
    for i, (uid, name, xp) in enumerate(data, 1):
        level = int((xp/100)**0.5)
        description += f"`{i}` **{name}** • Level {level} ({format_number(xp)} XP)\n"
    embed.description = description
    embed.set_footer(text=f"Top 10 in {ctx.guild.name}")
    await ctx.send(embed=embed)

# ==================================================
# STATS COMMAND
# ==================================================
@bot.command(name="stats")
@economy_check()
async def stats_cmd(ctx):
    data = await get_user(ctx.author.id)
    won = data.get('gambling_won', 0)
    lost = data.get('gambling_lost', 0)
    net = won - lost
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    embed = discord.Embed(title=f"{ctx.author.display_name}'s Gambling Stats", color=0xf1c40f)
    embed.add_field(name="💰 Total Won", value=f"{format_number(won)} {emoji}", inline=True)
    embed.add_field(name="💸 Total Lost", value=f"{format_number(lost)} {emoji}", inline=True)
    embed.add_field(name="📈 Net Profit", value=f"{format_number(net)} {emoji}", inline=True)
    await ctx.send(embed=embed)

# ==================================================
# QUEST SYSTEM (Daily & Weekly)
# ==================================================
DAILY_QUEST_TEMPLATES = [
    {"id":"gamble_win", "desc":"Win {target} gambling games", "target":3, "reward":25000, "type":"gamble_win"},
    {"id":"rob", "desc":"Rob {target} people", "target":5, "reward":30000, "type":"rob"},
    {"id":"earn", "desc":"Earn {target} coins", "target":25000, "reward":15000, "type":"earn"},
    {"id":"work", "desc":"Use .work {target} times", "target":10, "reward":20000, "type":"work"},
    {"id":"messages", "desc":"Send {target} messages", "target":50, "reward":10000, "type":"messages"},
    {"id":"invite", "desc":"Invite {target} people", "target":3, "reward":250000, "type":"invite", "manual":True},
]
WEEKLY_QUEST_TEMPLATES = [
    {"id":"big_gamble", "desc":"Win {target} gambling games", "target":30, "reward":200000, "type":"gamble_win"},
    {"id":"big_earn", "desc":"Earn {target} coins", "target":200000, "reward":100000, "type":"earn"},
    {"id":"big_invite", "desc":"Invite {target} people", "target":10, "reward":1000000, "type":"invite", "manual":True},
]

async def get_quests(user_id):
    data = await get_user(user_id)
    quest_data = json.loads(data.get('quest_data','{}'))
    now = datetime.now(timezone.utc)
    last_reset = data.get('quest_last_reset')
    reset_daily = True
    reset_weekly = True
    if last_reset:
        last_dt = datetime.fromisoformat(last_reset)
        if (now - last_dt).total_seconds() < 86400:
            reset_daily = False
        if (now - last_dt).total_seconds() < 604800:
            reset_weekly = False
    if reset_daily:
        quest_data['daily'] = []
        for tmpl in DAILY_QUEST_TEMPLATES:
            q = tmpl.copy()
            q['progress'] = 0; q['claimed'] = False
            quest_data['daily'].append(q)
    if reset_weekly:
        quest_data['weekly'] = []
        for tmpl in WEEKLY_QUEST_TEMPLATES:
            q = tmpl.copy()
            q['progress'] = 0; q['claimed'] = False
            quest_data['weekly'].append(q)
    if not quest_data.get('daily'):
        quest_data['daily'] = []
        for tmpl in DAILY_QUEST_TEMPLATES:
            q = tmpl.copy()
            q['progress'] = 0; q['claimed'] = False
            quest_data['daily'].append(q)
    if not quest_data.get('weekly'):
        quest_data['weekly'] = []
        for tmpl in WEEKLY_QUEST_TEMPLATES:
            q = tmpl.copy()
            q['progress'] = 0; q['claimed'] = False
            quest_data['weekly'].append(q)
    quest_data['last_reset'] = now.isoformat()
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET quest_data=?, quest_last_reset=? WHERE user_id=?",
                         (json.dumps(quest_data), now.isoformat(), user_id))
        await db.commit()
    return quest_data

async def update_quest_progress(user_id, quest_type, amount=1):
    data = await get_quests(user_id)
    changed = False
    for category in ('daily','weekly'):
        for q in data.get(category,[]):
            if q['type'] == quest_type and not q['claimed']:
                q['progress'] = min(q['progress'] + amount, q['target'])
                changed = True
    if changed:
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET quest_data=? WHERE user_id=?", (json.dumps(data), user_id))
            await db.commit()

class QuestView(discord.ui.View):
    def __init__(self, user_id, quest_data):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.quest_data = quest_data
    @discord.ui.button(label="Claim Rewards", style=discord.ButtonStyle.success)
    async def claim_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your quests!", ephemeral=True)
        total_reward = 0
        for category in ('daily','weekly'):
            for q in self.quest_data.get(category,[]):
                if q['progress'] >= q['target'] and not q['claimed']:
                    q['claimed'] = True
                    total_reward += q['reward']
        if total_reward == 0:
            return await interaction.response.send_message("No completed quests to claim!", ephemeral=True)
        await update_money(self.user_id, total_reward)
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET quest_data=? WHERE user_id=?", (json.dumps(self.quest_data), self.user_id))
            await db.commit()
        emoji = await get_setting(interaction.guild.id, "currency_emoji")
        await interaction.response.send_message(f"✅ Claimed {format_number(total_reward)}{emoji} from quests!", ephemeral=True)
        await self.update_display(interaction)
    async def update_display(self, interaction):
        embed = self.build_embed()
        await interaction.edit_original_response(embed=embed, view=self)
    def build_embed(self):
        emoji = "💰"
        embed = discord.Embed(title="📋 Quest Board", color=0x9b59b6)
        if self.quest_data.get('daily'):
            text = ""
            for q in self.quest_data['daily']:
                text += f"{'✅' if q['claimed'] else '▫'} {q['desc'].format(target=q['target'])}: {q['progress']}/{q['target']} ({format_number(q['reward'])}{emoji})\n"
            embed.add_field(name="Daily Quests", value=text, inline=False)
        if self.quest_data.get('weekly'):
            text = ""
            for q in self.quest_data['weekly']:
                text += f"{'✅' if q['claimed'] else '▫'} {q['desc'].format(target=q['target'])}: {q['progress']}/{q['target']} ({format_number(q['reward'])}{emoji})\n"
            embed.add_field(name="Weekly Quests", value=text, inline=False)
        return embed

@bot.command(name="tasks")
@economy_check()
async def tasks_cmd(ctx):
    data = await get_quests(ctx.author.id)
    view = QuestView(ctx.author.id, data)
    embed = view.build_embed()
    await ctx.send(embed=embed, view=view)

# ==================================================
# BADGE SYSTEM
# ==================================================
BADGES = {
    "first_1m": {"name":"First 1M", "emoji":"💵", "desc":"Reach 1,000,000 total coins"},
    "bj_master": {"name":"Blackjack Master", "emoji":"🃏", "desc":"Win 50 blackjack games"},
    "rob_king": {"name":"Robbery King", "emoji":"💰", "desc":"Rob 100 times"},
    "daily_grinder": {"name":"Daily Grinder", "emoji":"☀️", "desc":"Complete 30 daily quests"},
    "gambling_addict": {"name":"Gambling Addict", "emoji":"🎰", "desc":"Play 500 gambling games"},
    "rich_player": {"name":"Rich Player", "emoji":"💎", "desc":"Reach 100,000,000 total coins"},
}
async def check_badges(user_id):
    data = await get_user(user_id)
    total = data['money'] + data['bank']
    badges = json.loads(data.get('badges','[]'))
    new_badges = []
    if total >= 1_000_000 and "first_1m" not in badges:
        badges.append("first_1m"); new_badges.append("first_1m")
    if total >= 100_000_000 and "rich_player" not in badges:
        badges.append("rich_player"); new_badges.append("rich_player")
    if new_badges:
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET badges=? WHERE user_id=?", (json.dumps(badges), user_id))
            await db.commit()
        return new_badges
    return []

@bot.command(name="badges")
@economy_check()
async def badges_cmd(ctx):
    data = await get_user(ctx.author.id)
    badges = json.loads(data.get('badges','[]'))
    if not badges: return await ctx.send("You have no badges yet.")
    embed = discord.Embed(title="🏅 Your Badges", color=0xf1c40f)
    for badge_id in badges:
        info = BADGES.get(badge_id)
        if info:
            embed.add_field(name=f"{info['emoji']} {info['name']}", value=info['desc'], inline=False)
    await ctx.send(embed=embed)

@bot.command(name="badgesselect", aliases=["bs"])
@economy_check()
async def badge_select(ctx, badge1: str = None, badge2: str = None, badge3: str = None):
    data = await get_user(ctx.author.id)
    owned = set(json.loads(data.get('badges','[]')))
    selected = []
    for b in (badge1, badge2, badge3):
        if b and b in owned:
            selected.append(b)
    if len(selected) > 3: return await ctx.send("Maximum 3 showcase badges.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET showcase_badges=? WHERE user_id=?", (json.dumps(selected), ctx.author.id))
        await db.commit()
    await ctx.send(f"Showcase badges set: {', '.join(selected)}" if selected else "Showcase cleared.")

# ==================================================
# ECONOMY COMMANDS
# ==================================================
@bot.command(name="bal", aliases=["balance"])
@economy_check()
async def balance(ctx, user: discord.User = None):
    if user is None:
        user = ctx.author
    data = await get_user(user.id)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    embed = discord.Embed(title=f"{user.display_name}'s Balance", color=0x2ecc71)
    embed.add_field(name="Wallet", value=f"{format_number(data['money'])} {emoji}", inline=True)
    embed.add_field(name="Bank", value=f"{format_number(data['bank'])} {emoji}", inline=True)
    embed.add_field(name="Total", value=f"{format_number(data['money']+data['bank'])} {emoji}", inline=False)
    if data['loan_amount'] > 0:
        embed.add_field(name="Loan", value=f"{format_number(data['loan_amount'])} {emoji} (10%/hr)", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="dep", aliases=["deposit"])
@economy_check()
async def deposit(ctx, amount_str: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    await update_bank(ctx.author.id, amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Deposited {format_number(amount)}{emoji} into your bank.")

@bot.command(name="with", aliases=["withdraw"])
@economy_check()
async def withdraw(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    if amount_str.lower() == "all":
        amount = data['bank']
        if amount <= 0:
            return await ctx.send("Your bank is empty.")
    elif amount_str.lower() == "half":
        amount = data['bank'] // 2
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return await ctx.send("Invalid amount.")
    if amount <= 0:
        return await ctx.send("Amount must be positive.")
    max_withdraw = await get_setting(ctx.guild.id, "max_withdraw")
    if amount > max_withdraw and max_withdraw != 0:
        return await ctx.send(f"Maximum withdraw is {format_number(max_withdraw)} coins.")
    if data['bank'] < amount:
        return await ctx.send(f"You only have {format_number(data['bank'])} in the bank.")
    await update_bank(ctx.author.id, -amount)
    await update_money(ctx.author.id, amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Withdrew {format_number(amount)}{emoji} from your bank.")

@bot.command(name="daily")
@economy_check()
async def daily(ctx):
    data = await get_user(ctx.author.id)
    now = datetime.now(timezone.utc)
    if data.get('last_daily'):
        last = datetime.fromisoformat(data['last_daily'])
        if now - last < timedelta(hours=20):
            remain = timedelta(hours=20) - (now - last)
            return await ctx.send(f"⏰ You can claim daily again in {remain.seconds//3600}h {(remain.seconds%3600)//60}m.")
    needed = await get_setting(ctx.guild.id, "daily_messages_needed")
    if data.get('daily_messages',0) < needed:
        return await ctx.send(f"You need {needed} messages since last claim. You have {data['daily_messages']}.")
    reward = await get_setting(ctx.guild.id, "daily_amount")
    await update_money(ctx.author.id, reward)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_daily=?, daily_messages=0 WHERE user_id=?",
                         (now.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Daily claimed! +{format_number(reward)}{emoji}")

@bot.command(name="work")
@economy_check()
async def work(ctx):
    data = await get_user(ctx.author.id)
    now = datetime.now(timezone.utc)
    if data.get('last_work'):
        last = datetime.fromisoformat(data['last_work'])
        if now - last < timedelta(minutes=5):
            remain = timedelta(minutes=5) - (now - last)
            secs = remain.seconds
            return await ctx.send(f"⏰ Work cooldown: {secs//60}m {secs%60}s.")
    min_reward = await get_setting(ctx.guild.id, "work_amount_min")
    max_reward = await get_setting(ctx.guild.id, "work_amount_max")
    reward = random.randint(min_reward, max_reward)
    await update_money(ctx.author.id, reward)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_work=? WHERE user_id=?", (now.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Work complete! +{format_number(reward)}{emoji}")
    await update_quest_progress(ctx.author.id, "work")

@bot.command(name="sleep")
@economy_check()
async def sleep(ctx):
    data = await get_user(ctx.author.id)
    now = datetime.now(timezone.utc)
    if data.get('last_sleep'):
        last = datetime.fromisoformat(data['last_sleep'])
        if now - last < timedelta(hours=8):
            remain = timedelta(hours=8) - (now - last)
            return await ctx.send(f"⏰ Sleep cooldown: {remain.seconds//3600}h {(remain.seconds%3600)//60}m.")
    min_reward = await get_setting(ctx.guild.id, "sleep_amount_min")
    max_reward = await get_setting(ctx.guild.id, "sleep_amount_max")
    reward = random.randint(min_reward, max_reward)
    await update_money(ctx.author.id, reward)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_sleep=? WHERE user_id=?", (now.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Sleep well! +{format_number(reward)}{emoji}")

@bot.command(name="crime")
@economy_check()
async def crime(ctx):
    data = await get_user(ctx.author.id)
    now = datetime.now(timezone.utc)
    if data.get('last_crime'):
        last = datetime.fromisoformat(data['last_crime'])
        if now - last < timedelta(minutes=15):
            remain = timedelta(minutes=15) - (now - last)
            secs = remain.seconds
            return await ctx.send(f"⏰ Crime cooldown: {secs//60}m {secs%60}s.")
    min_reward = await get_setting(ctx.guild.id, "crime_amount_min")
    max_reward = await get_setting(ctx.guild.id, "crime_amount_max")
    if random.random() < 0.3:
        fine = random.randint(1000, 5000)
        await update_money(ctx.author.id, -fine)
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET last_crime=? WHERE user_id=?", (now.isoformat(), ctx.author.id))
            await db.commit()
        emoji = await get_setting(ctx.guild.id, "currency_emoji")
        return await ctx.send(f"🚔 Busted! You lost {format_number(fine)}{emoji}.")
    reward = random.randint(min_reward, max_reward)
    await update_money(ctx.author.id, reward)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_crime=? WHERE user_id=?", (now.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Crime successful! +{format_number(reward)}{emoji}")

# ==================================================
# ROB COMMAND
# ==================================================
@bot.command(name="rob")
@economy_check()
async def rob(ctx, user: discord.User):
    if await get_setting(ctx.guild.id, "rob_enabled") == 0:
        return await ctx.send("Robbery is disabled.")
    if user == ctx.author:
        return await ctx.send("You can't rob yourself.")
    target_data = await get_user(user.id)
    if await is_protected(user.id) or await has_security(user.id):
        return await ctx.send(f"{user.mention} is protected.")
    if target_data['money'] <= 500:
        return await ctx.send(f"{user.mention} doesn't have enough to steal (minimum 500 coins needed).")
    data = await get_user(ctx.author.id)
    now = datetime.now(timezone.utc)
    if data.get('last_rob'):
        last = datetime.fromisoformat(data['last_rob'])
        if now - last < timedelta(hours=1):
            remain = timedelta(hours=1) - (now - last)
            return await ctx.send(f"⏰ Rob cooldown: {remain.seconds//3600}h {(remain.seconds%3600)//60}m.")
    roll = random.random() * 100
    if roll < 40:
        steal_percent = random.uniform(0.05, 0.15)
    elif roll < 65:
        steal_percent = random.uniform(0.15, 0.25)
    elif roll < 82:
        steal_percent = random.uniform(0.25, 0.35)
    elif roll < 93:
        steal_percent = random.uniform(0.35, 0.45)
    elif roll < 98:
        steal_percent = random.uniform(0.45, 0.50)
    else:
        steal_percent = 0.50
    stolen = int(target_data['money'] * steal_percent)
    stolen = max(stolen, 100)
    await update_money(user.id, -stolen)
    await update_money(ctx.author.id, stolen)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_rob=? WHERE user_id=?", (now.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    steal_pct_display = int(steal_percent * 100)
    await ctx.send(f"🤑 You stole **{format_number(stolen)}{emoji}** ({steal_pct_display}% of their wallet) from {user.mention}!")
    await update_quest_progress(ctx.author.id, "rob")

@bot.command(name="interest")
@economy_check()
async def interest(ctx):
    rate = await get_setting(ctx.guild.id, "interest_rate")
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Bank interest rate: {rate}% per 24h on balances up to 50,000{emoji}.")

# ==================================================
# SECURITY COMMAND
# ==================================================
@bot.command(name="security")
@economy_check()
async def security(ctx, hours: int):
    if hours <= 0 or hours > 8:
        return await ctx.send("You can only buy 1 to 8 hours of security.")
    cost = 10_000_000 * (2 ** (hours - 1))
    data = await get_user(ctx.author.id)
    if data['money'] < cost:
        return await ctx.send(f"Security for {hours}h costs {format_number(cost)} coins. You have {format_number(data['money'])}.")
    await update_money(ctx.author.id, -cost)
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET security_until=? WHERE user_id=?", (until.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"🔒 Security activated for {hours} hours. Cost: {format_number(cost)}{emoji}")

@bot.command(name="pay")
@economy_check()
async def pay(ctx, user: discord.User, amount_str: str):
    if user == ctx.author:
        return await ctx.send("You can't pay yourself.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err:
        return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    await update_money(user.id, amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Paid {format_number(amount)}{emoji} to {user.mention}.")

# ==================================================
# LOAN COMMANDS
# ==================================================
@bot.command(name="loan")
@economy_check()
async def loan(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    if data['loan_amount'] > 0:
        return await ctx.send(f"You already have a loan of {format_number(data['loan_amount'])}. Repay it first.")
    try:
        amount = parse_amount(amount_str)
    except:
        return await ctx.send("Invalid amount.")
    if amount <= 0:
        return await ctx.send("Amount must be positive.")
    max_loan = 50000
    if amount > max_loan:
        return await ctx.send(f"Maximum loan is {format_number(max_loan)} coins.")
    await update_money(ctx.author.id, amount)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET loan_amount=?, loan_taken_at=? WHERE user_id=?",
                         (str(amount), datetime.now(timezone.utc).isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Loan of {format_number(amount)}{emoji} granted. 10% interest per hour until repaid.")

@bot.command(name="repay")
@economy_check()
async def repay(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    if data['loan_amount'] <= 0:
        return await ctx.send("You don't have a loan.")
    if amount_str.lower() == "all":
        amount = data['loan_amount']
    elif amount_str.lower() == "half":
        amount = data['loan_amount'] // 2
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return await ctx.send("Invalid amount (use all, half, or a number).")
    if amount <= 0:
        return await ctx.send("Amount must be positive.")
    if amount > data['loan_amount']:
        amount = data['loan_amount']
    if data['money'] < amount:
        return await ctx.send(f"You need {format_number(amount)} in your wallet. You have {format_number(data['money'])}.")
    await update_money(ctx.author.id, -amount)
    new_loan = data['loan_amount'] - amount
    async with aiosqlite.connect("hakari.db") as db:
        if new_loan == 0:
            await db.execute("UPDATE users SET loan_amount='0', loan_taken_at=NULL WHERE user_id=?", (ctx.author.id,))
        else:
            await db.execute("UPDATE users SET loan_amount=? WHERE user_id=?", (str(new_loan), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Repaid {format_number(amount)}{emoji}. Remaining loan: {format_number(new_loan)}{emoji}" if new_loan > 0 else f"Loan fully repaid! 🎉")

@bot.command(name="loaninfo")
@economy_check()
async def loaninfo(ctx):
    data = await get_user(ctx.author.id)
    if data['loan_amount'] <= 0:
        return await ctx.send("No loan.")
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    taken = data.get('loan_taken_at')
    if taken:
        taken_dt = datetime.fromisoformat(taken)
        elapsed = datetime.now(timezone.utc) - taken_dt
        hours_passed = elapsed.total_seconds() / 3600
        interest = int(data['loan_amount'] * (0.10 * hours_passed))
        total_due = data['loan_amount'] + interest
        await ctx.send(f"Loan: {format_number(data['loan_amount'])}{emoji}\nAccrued interest: {format_number(interest)}{emoji}\nTotal due: {format_number(total_due)}{emoji}")
    else:
        await ctx.send(f"Loan: {format_number(data['loan_amount'])}{emoji}")

# ==================================================
# GAMBLING COMMANDS
# ==================================================
@bot.command(name="cf", aliases=["coinflip"])
@economy_check()
@gambling_cooldown_check()
async def coinflip(ctx, amount_str: str, choice: str = None):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    if choice and choice.lower() not in ("heads","tails"): return await ctx.send("Choose heads or tails.")
    await update_money(ctx.author.id, -amount)
    result = random.choice(["heads","tails"])
    win = (choice and choice.lower() == result) or (not choice and random.choice([True,False]))
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if win:
        winnings = amount * 2
        await update_money(ctx.author.id, winnings)
        profit = winnings - amount
        await update_gambling_stats(ctx.author.id, won=profit)
        await ctx.send(f"Coin landed on **{result}**! You won {format_number(profit)}{emoji}!")
        await update_quest_progress(ctx.author.id, "gamble_win")
    else:
        await update_gambling_stats(ctx.author.id, lost=amount)
        await ctx.send(f"Coin landed on **{result}**! You lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

@bot.command(name="slots")
@economy_check()
@gambling_cooldown_check()
async def slots(ctx, amount_str: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    emojis = ["🍒","🍋","🍊","🍉","⭐","💎"]
    r = [random.choice(emojis) for _ in range(3)]
    mult = 0
    if r[0]==r[1]==r[2]: mult = 3 if r[0]=="💎" else 2
    elif r[0]==r[1] or r[1]==r[2] or r[0]==r[2]: mult = 0.5
    winnings = int(amount * mult)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if mult >= 1:
        await update_money(ctx.author.id, winnings)
        profit = winnings - amount
        await update_gambling_stats(ctx.author.id, won=profit)
        await ctx.send(f"🎰 `{r[0]} {r[1]} {r[2]}`\nYou won {format_number(profit)}{emoji}!")
        await update_quest_progress(ctx.author.id, "gamble_win")
    elif mult > 0:
        await update_money(ctx.author.id, winnings)
        profit = winnings - amount
        if profit > 0:
            await update_gambling_stats(ctx.author.id, won=profit)
        else:
            await update_gambling_stats(ctx.author.id, lost=abs(profit))
        await ctx.send(f"🎰 `{r[0]} {r[1]} {r[2]}`\nSmall win! Got back {format_number(winnings)}{emoji}.")
    else:
        await update_gambling_stats(ctx.author.id, lost=amount)
        await ctx.send(f"🎰 `{r[0]} {r[1]} {r[2]}`\nLost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

# Blackjack
class BlackjackView(discord.ui.View):
    def __init__(self, ctx, bet, player, dealer, emoji):
        super().__init__(timeout=120)
        self.ctx=ctx; self.bet=bet; self.player=player; self.dealer=dealer
        self.emoji=emoji; self.ended=False; self.start=datetime.now(timezone.utc)
    def card_emoji(self, c):
        m = {2:"2",3:"3",4:"4",5:"5",6:"6",7:"7",8:"8",9:"9",10:"10",11:"A"}
        return m.get(c, "?")
    async def hand_value(self, hand):
        val = sum(hand); aces = hand.count(11)
        while val>21 and aces: val-=10; aces-=1
        return val
    async def embed_game(self):
        remain = 120 - (datetime.now(timezone.utc)-self.start).total_seconds()
        mins, secs = divmod(max(0,int(remain)),60)
        pv = await self.hand_value(self.player)
        pstr = " ".join(self.card_emoji(c) for c in self.player)
        dstr = f"{self.card_emoji(self.dealer[0])} ?" if len(self.dealer)==2 else " ".join(self.card_emoji(c) for c in self.dealer)
        dv = "?" if len(self.dealer)==2 else str(await self.hand_value(self.dealer))
        embed = discord.Embed(title=f"{self.ctx.author.display_name}'s Blackjack", color=0x2ecc71)
        embed.add_field(name=f"Your Hand ({pv})", value=pstr, inline=False)
        embed.add_field(name="Dealer", value=f"{dstr}\n**{dv}**", inline=False)
        embed.add_field(name="Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
        embed.add_field(name="Time", value=f"{mins}m {secs}s", inline=True)
        return embed
    async def end_game(self, result, win=0, dealer_final_hand=None, dealer_final_val=None):
        if result=="win":
            await update_money(self.ctx.author.id, win)
            profit = win - self.bet
            await update_gambling_stats(self.ctx.author.id, won=profit)
            msg = f"You won {format_number(profit)}{self.emoji}!"
            await update_quest_progress(self.ctx.author.id, "gamble_win")
        elif result=="lose":
            await update_gambling_stats(self.ctx.author.id, lost=self.bet)
            msg = f"Lost {format_number(self.bet)}{self.emoji}."
        elif result=="push":
            await update_money(self.ctx.author.id, self.bet)
            msg = "Push! Money returned."
        elif result=="blackjack":
            w = int(self.bet*2.5)
            await update_money(self.ctx.author.id, w)
            profit = w - self.bet
            await update_gambling_stats(self.ctx.author.id, won=profit)
            msg = f"BLACKJACK! Won {format_number(profit)}{self.emoji}!"
            await update_quest_progress(self.ctx.author.id, "gamble_win")
        else:
            await update_gambling_stats(self.ctx.author.id, lost=self.bet)
            msg = f"Timeout! Lost {format_number(self.bet)}{self.emoji}."
        embed = discord.Embed(title="Game Over", color=0xe74c3c)
        embed.add_field(name="Result", value=msg, inline=False)
        if dealer_final_hand and dealer_final_val is not None:
            hand_str = " ".join(self.card_emoji(c) for c in dealer_final_hand)
            embed.add_field(name=f"Dealer's Final Hand ({dealer_final_val})", value=hand_str, inline=False)
        await self.ctx.send(embed=embed)
        self.ended=True; self.stop()
        await set_gambling_cooldown(self.ctx.author.id)
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, inter, btn):
        if inter.user != self.ctx.author: return
        self.player.append(random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11]))
        if await self.hand_value(self.player) > 21:
            await self.end_game("lose", dealer_final_hand=self.dealer, dealer_final_val=await self.hand_value(self.dealer))
            await inter.message.delete(); return
        await inter.response.edit_message(embed=await self.embed_game(), view=self)
    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success)
    async def stand(self, inter, btn):
        if inter.user != self.ctx.author: return
        while await self.hand_value(self.dealer) < 17:
            self.dealer.append(random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11]))
        dv = await self.hand_value(self.dealer); pv = await self.hand_value(self.player)
        dealer_final = self.dealer.copy(), dv
        if dv > 21 or pv > dv:
            await self.end_game("win", self.bet*2, *dealer_final)
        elif pv < dv:
            await self.end_game("lose", dealer_final_hand=self.dealer, dealer_final_val=dv)
        else:
            await self.end_game("push", dealer_final_hand=self.dealer, dealer_final_val=dv)
        await inter.message.delete()
    async def on_timeout(self):
        if not self.ended:
            await self.end_game("timeout", dealer_final_hand=self.dealer, dealer_final_val=await self.hand_value(self.dealer))

@bot.command(name="bj", aliases=["blackjack"])
@economy_check()
@gambling_cooldown_check()
async def blackjack(ctx, amount_str: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    cards = [2,3,4,5,6,7,8,9,10,10,10,10,11]
    player = [random.choice(cards), random.choice(cards)]
    dealer = [random.choice(cards), random.choice(cards)]
    pv = sum(player); emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if pv == 21:
        win = int(amount*2.5)
        await update_money(ctx.author.id, win)
        profit = win - amount
        await update_gambling_stats(ctx.author.id, won=profit)
        await ctx.send(f"BLACKJACK! Won {format_number(profit)}{emoji}!")
        await update_quest_progress(ctx.author.id, "gamble_win")
        await set_gambling_cooldown(ctx.author.id)
    else:
        view = BlackjackView(ctx, amount, player, dealer, emoji)
        embed = await view.embed_game()
        await ctx.send(embed=embed, view=view)

# Mines
class MinesView(discord.ui.View):
    def __init__(self, ctx, bet, mines, multiplier, emoji):
        super().__init__(timeout=120)
        self.ctx=ctx; self.bet=bet; self.mines=mines; self.mult=multiplier; self.emoji=emoji
        self.revealed=[False]*20; self.mine_pos=set(random.sample(range(20), mines))
        self.safe_reveals=0; self.ended=False; self.start=datetime.now(timezone.utc)
        for i in range(20):
            btn = discord.ui.Button(label="⬛", style=discord.ButtonStyle.secondary, row=i//5, custom_id=f"m{i}")
            btn.callback = self.make_callback(i)
            self.add_item(btn)
        self.cashout = discord.ui.Button(label="💰 Cashout", style=discord.ButtonStyle.success, row=4)
        self.cashout.callback = self.cashout_cb
        self.add_item(self.cashout)
    def make_callback(self, pos):
        async def cb(inter):
            if inter.user != self.ctx.author or self.ended: return
            if self.revealed[pos]: return
            self.revealed[pos]=True
            if pos in self.mine_pos:
                self.ended=True
                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.custom_id and child.custom_id.startswith("m"):
                        idx=int(child.custom_id[1:])
                        if idx in self.mine_pos: child.label="💣"; child.style=discord.ButtonStyle.danger
                        elif self.revealed[idx]: child.label="💎"; child.style=discord.ButtonStyle.success
                        child.disabled=True
                await update_gambling_stats(self.ctx.author.id, lost=self.bet)
                await inter.response.edit_message(content=f"💥 BOOM! You lost {format_number(self.bet)}{self.emoji}.", view=self)
                self.stop(); await set_gambling_cooldown(self.ctx.author.id)
            else:
                self.safe_reveals+=1
                self.mult = round(1.02 * (25/(25-self.mines))**(1+self.safe_reveals*0.1),2)
                self.mult = min(self.mult,100)
                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.custom_id == f"m{pos}":
                        child.label="💎"; child.style=discord.ButtonStyle.success; child.disabled=True; break
                remain = 120 - (datetime.now(timezone.utc)-self.start).total_seconds()
                mins, secs = divmod(max(0,int(remain)),60)
                board = ""
                for i in range(20):
                    board += "💎 " if self.revealed[i] else "⬛ "
                    if (i+1)%5==0: board+="\n"
                embed = discord.Embed(title="💣 Minesweeper", color=0xf1c40f)
                embed.add_field(name="Board", value=board, inline=False)
                embed.add_field(name="Mines", value=f"{self.mines} bombs", inline=True)
                embed.add_field(name="Multiplier", value=f"{self.mult}x", inline=True)
                embed.add_field(name="Cashout", value=f"{format_number(int(self.bet*self.mult))}{self.emoji}", inline=True)
                embed.add_field(name="Time", value=f"{mins}m {secs}s", inline=True)
                await inter.response.edit_message(embed=embed, view=self)
        return cb
    async def cashout_cb(self, inter):
        if inter.user != self.ctx.author or self.ended: return
        if self.safe_reveals==0: return await inter.response.send_message("❌ Reveal at least one tile before cashing out!", ephemeral=True)
        win = int(self.bet*self.mult)
        await update_money(self.ctx.author.id, win)
        profit = win - self.bet
        await update_gambling_stats(self.ctx.author.id, won=profit)
        await inter.response.edit_message(content=f"💰 Cashed out! Won {format_number(profit)}{self.emoji}!", view=None)
        self.ended=True; self.stop()
        await set_gambling_cooldown(self.ctx.author.id)
        await update_quest_progress(self.ctx.author.id, "gamble_win")
    async def on_timeout(self):
        if not self.ended:
            await update_gambling_stats(self.ctx.author.id, lost=self.bet)
            try:
                await self.ctx.send(f"⏰ {self.ctx.author.mention} took too long! Lost {format_number(self.bet)}{self.emoji}.")
            except:
                pass
            await set_gambling_cooldown(self.ctx.author.id)

@bot.command(name="mines")
@economy_check()
@gambling_cooldown_check()
async def mines_cmd(ctx, amount_str: str, mines: int = 5):
    if mines<1 or mines>19: return await ctx.send("❌ Mines must be 1-19.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    mult = round(1.02 * (25/(25-mines))**1.2,2)
    mult = min(mult,100)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    view = MinesView(ctx, amount, mines, mult, emoji)
    board = "⬛ ⬛ ⬛ ⬛ ⬛\n⬛ ⬛ ⬛ ⬛ ⬛\n⬛ ⬛ ⬛ ⬛ ⬛\n⬛ ⬛ ⬛ ⬛ ⬛"
    embed = discord.Embed(title="💣 Minesweeper", color=0xf1c40f)
    embed.add_field(name="Board", value=board, inline=False)
    embed.add_field(name="Mines", value=f"{mines} bombs", inline=True)
    embed.add_field(name="Multiplier", value=f"{mult}x", inline=True)
    embed.add_field(name="Cashout", value=f"{format_number(int(amount*mult))}{emoji}", inline=True)
    embed.add_field(name="Time", value="2 minutes", inline=True)
    embed.set_footer(text="Reveal tiles to increase multiplier. Must reveal at least 1 to cashout!")
    await ctx.send(embed=embed, view=view)

# Crash
class CrashView(discord.ui.View):
    def __init__(self, ctx, bet, emoji):
        super().__init__(timeout=30)
        self.ctx = ctx; self.bet = bet; self.emoji = emoji
        self.crashed = False; self.cashed_out = False
        self.multiplier = 1.0
        self.crash_point = self.generate_crash_point()
        self.start_time = datetime.now(timezone.utc)
        self.message = None; self.update_task = None; self._lock = asyncio.Lock()
    def generate_crash_point(self):
        roll = random.random() * 100
        if roll < 30: return round(random.uniform(1.01, 1.50), 2)
        elif roll < 55: return round(random.uniform(1.51, 2.50), 2)
        elif roll < 75: return round(random.uniform(2.51, 5.00), 2)
        elif roll < 88: return round(random.uniform(5.01, 15.00), 2)
        elif roll < 96: return round(random.uniform(15.01, 50.00), 2)
        elif roll < 99: return round(random.uniform(50.01, 200.00), 2)
        else: return round(random.uniform(200.01, 1000.00), 2)
    async def start_update_task(self):
        self.update_task = asyncio.create_task(self.auto_update())
    async def auto_update(self):
        try:
            while not self.crashed and not self.cashed_out:
                elapsed = (datetime.now(timezone.utc) - self.start_time).total_seconds()
                self.multiplier = round(1.0 * (1.08 ** elapsed), 2)
                if self.multiplier >= self.crash_point:
                    self.crashed = True
                    await self.crash()
                    return
                embed = discord.Embed(title="📈 Crash", color=0x2ecc71)
                embed.add_field(name="Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
                embed.add_field(name="Multiplier", value=f"{self.multiplier}x", inline=True)
                embed.add_field(name="Potential Win", value=f"{format_number(int(self.bet * self.multiplier))} {self.emoji}", inline=True)
                embed.set_footer(text="Click 'Cash Out' to secure your winnings!")
                if self.message: 
                    try:
                        await self.message.edit(embed=embed, view=self)
                    except discord.NotFound:
                        return
                await asyncio.sleep(0.6)
        except (discord.NotFound, asyncio.CancelledError): pass
    async def crash(self):
        async with self._lock:
            await update_gambling_stats(self.ctx.author.id, lost=self.bet)
            embed = discord.Embed(title="💥 CRASHED!", color=0xe74c3c)
            embed.add_field(name="Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
            embed.add_field(name="Crashed at", value=f"{self.multiplier}x", inline=True)
            embed.add_field(name="Lost", value=f"{format_number(self.bet)} {self.emoji}", inline=False)
            for child in self.children: child.disabled = True
            try:
                if self.message: await self.message.edit(embed=embed, view=None)
            except discord.NotFound: pass
            self.stop()
            await set_gambling_cooldown(self.ctx.author.id)
    @discord.ui.button(label="💰 Cash Out", style=discord.ButtonStyle.success)
    async def cash_out(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._lock:
            if interaction.user.id != self.ctx.author.id: return await interaction.response.send_message("This is not your game!", ephemeral=True)
            if self.cashed_out or self.crashed: return
            self.cashed_out = True
            if self.update_task and not self.update_task.done(): self.update_task.cancel()
            win_amount = int(self.bet * self.multiplier)
            await update_money(self.ctx.author.id, win_amount)
            profit = win_amount - self.bet
            await update_gambling_stats(self.ctx.author.id, won=profit)
            embed = discord.Embed(title="✅ Cashed Out!", color=0x2ecc71)
            embed.add_field(name="Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
            embed.add_field(name="Multiplier", value=f"{self.multiplier}x", inline=True)
            embed.add_field(name="Won", value=f"{format_number(profit)} {self.emoji}", inline=False)
            for child in self.children: child.disabled = True
            await interaction.response.edit_message(embed=embed, view=None)
            self.stop()
            await set_gambling_cooldown(self.ctx.author.id)
            await update_quest_progress(self.ctx.author.id, "gamble_win")
    async def on_timeout(self):
        async with self._lock:
            if not self.crashed and not self.cashed_out:
                self.crashed = True
                if self.update_task and not self.update_task.done(): self.update_task.cancel()
                await self.crash()

@bot.command(name="crash")
@economy_check()
@gambling_cooldown_check()
async def crash(ctx, amount_str: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    view = CrashView(ctx, amount, emoji)
    embed = discord.Embed(title="📈 Crash", color=0x2ecc71)
    embed.add_field(name="Bet", value=f"{format_number(amount)} {emoji}", inline=True)
    embed.add_field(name="Multiplier", value="1.0x", inline=True)
    embed.add_field(name="Potential Win", value=f"{format_number(int(amount))} {emoji}", inline=True)
    embed.set_footer(text="Click 'Cash Out' to secure your winnings!\nLow multipliers are common, high multipliers are rare")
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg
    await view.start_update_task()

# Tower
class TowerDoorView(discord.ui.View):
    def __init__(self, ctx, bet, emoji):
        super().__init__(timeout=120)
        self.ctx=ctx; self.bet=bet; self.emoji=emoji
        self.current_floor=0; self.max_floor=random.randint(8,12)
        self.game_over=False; self.start_time=datetime.now(timezone.utc)
        self.mine_position=None; self.message=None
        self.add_floor_buttons()
    def add_floor_buttons(self):
        for child in self.children[:]:
            if isinstance(child, discord.ui.Button) and child.custom_id and child.custom_id.startswith("door_"):
                self.remove_item(child)
        self.mine_position=random.randint(1,3)
        for i in range(1,4):
            btn = discord.ui.Button(label=f"🚪 Door {i}", style=discord.ButtonStyle.secondary, custom_id=f"door_{i}")
            btn.callback=self.make_door_callback(i)
            self.add_item(btn)
        if not any(isinstance(c, discord.ui.Button) and c.label=="💰 Cash Out" for c in self.children):
            self.cashout_btn = discord.ui.Button(label="💰 Cash Out", style=discord.ButtonStyle.success)
            self.cashout_btn.callback = self.cashout_callback
            self.add_item(self.cashout_btn)
    def get_multiplier(self, floor): return round(1.5**floor,2)
    def get_cashout_value(self):
        if self.current_floor==0: return self.bet
        return int(self.bet * self.get_multiplier(self.current_floor))
    async def update_embed(self, interaction, crashed=False):
        cashout = self.get_cashout_value()
        embed = discord.Embed(title=f"{self.ctx.author.display_name}'s Tower – Door Pick",
                              color=0x2ecc71 if not crashed else 0xe74c3c)
        embed.add_field(name="Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
        embed.add_field(name="Floor", value=f"{self.current_floor}/{self.max_floor}", inline=True)
        embed.add_field(name="💰 Cashout Value", value=f"{format_number(cashout)} {self.emoji}", inline=True)
        if not crashed:
            embed.add_field(name="Pick a Door", value="One door hides a 💣 mine. The other two are safe.", inline=False)
        else:
            embed.add_field(name="💥 BOOM!", value=f"You hit the mine at floor {self.current_floor+1}! Lost {format_number(self.bet)}{self.emoji}.", inline=False)
        embed.set_footer(text=f"Floors: {self.max_floor} | Multiplier: {self.get_multiplier(self.current_floor)}x")
        await interaction.response.edit_message(embed=embed, view=self if not crashed else None)
    def make_door_callback(self, door_number):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author: return await interaction.response.send_message("Not your game!", ephemeral=True)
            if self.game_over: return
            if door_number == self.mine_position:
                self.game_over=True
                await update_gambling_stats(self.ctx.author.id, lost=self.bet)
                await self.update_embed(interaction, crashed=True)
                self.stop()
                await set_gambling_cooldown(self.ctx.author.id)
                return
            self.current_floor+=1
            if self.current_floor == self.max_floor:
                winnings = self.get_cashout_value()
                await update_money(self.ctx.author.id, winnings)
                profit = winnings - self.bet
                await update_gambling_stats(self.ctx.author.id, won=profit)
                embed = discord.Embed(title=f"{self.ctx.author.display_name}'s Tower - COMPLETE!", color=0xf1c40f)
                embed.add_field(name="Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
                embed.add_field(name="Floors Cleared", value=f"{self.current_floor}/{self.max_floor}", inline=True)
                embed.add_field(name="Winnings", value=f"{format_number(profit)} {self.emoji}", inline=True)
                embed.add_field(name="🎉 CONGRATULATIONS!", value="You reached the top!", inline=False)
                await interaction.response.edit_message(embed=embed, view=None)
                self.game_over=True; self.stop()
                await set_gambling_cooldown(self.ctx.author.id)
                await update_quest_progress(self.ctx.author.id, "gamble_win")
            else:
                self.add_floor_buttons()
                await self.update_embed(interaction, crashed=False)
        return callback
    async def cashout_callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author: return await interaction.response.send_message("Not your game!", ephemeral=True)
        if self.game_over: return
        if self.current_floor==0: return await interaction.response.send_message("❌ Clear at least one floor before cashing out!", ephemeral=True)
        winnings = self.get_cashout_value()
        await update_money(self.ctx.author.id, winnings)
        profit = winnings - self.bet
        await update_gambling_stats(self.ctx.author.id, won=profit)
        embed = discord.Embed(title=f"{self.ctx.author.display_name}'s Tower", color=0x2ecc71)
        embed.add_field(name="Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
        embed.add_field(name="Floors Cleared", value=f"{self.current_floor}/{self.max_floor}", inline=True)
        embed.add_field(name="Cashed Out", value=f"{format_number(profit)} {self.emoji}", inline=True)
        embed.add_field(name="✅ You cashed out!", value="Smart choice!", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)
        self.game_over=True; self.stop()
        await set_gambling_cooldown(self.ctx.author.id)
        await update_quest_progress(self.ctx.author.id, "gamble_win")
    async def on_timeout(self):
        if not self.game_over:
            await update_gambling_stats(self.ctx.author.id, lost=self.bet)
            try:
                await self.ctx.send(f"⏰ {self.ctx.author.mention} took too long! Lost {format_number(self.bet)}{self.emoji}.")
            except:
                pass
            await set_gambling_cooldown(self.ctx.author.id)

@bot.command(name="tower")
@economy_check()
@gambling_cooldown_check()
async def tower(ctx, amount_str: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    view = TowerDoorView(ctx, amount, emoji)
    embed = discord.Embed(title=f"{ctx.author.display_name}'s Tower – Door Pick", color=0x2ecc71)
    embed.add_field(name="Bet", value=f"{format_number(amount)} {emoji}", inline=True)
    embed.add_field(name="Floor", value="0/???", inline=True)
    embed.add_field(name="💰 Cashout Value", value=f"{format_number(amount)} {emoji}", inline=True)
    embed.add_field(name="Pick a Door", value="One door hides a 💣 mine. The other two are safe.", inline=False)
    embed.set_footer(text="Each safe door increases your multiplier. Cash out anytime.")
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

# Roulette
@bot.command(name="roulette", aliases=["rl"])
@economy_check()
@gambling_cooldown_check()
async def roulette(ctx, amount_str: str, *, bet: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    bet = bet.lower().strip()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    number = random.randint(0,36)
    if number==0: color="green"
    elif number in [1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36]: color="red"
    else: color="black"
    win=False; payout=0
    if bet.isdigit():
        if int(bet)==number: win,payout = True, amount*35
    elif bet in ["red","r"]:
        if color=="red": win,payout = True, amount*2
    elif bet in ["black","b"]:
        if color=="black": win,payout = True, amount*2
    elif bet in ["green","g","0"]:
        if number==0: win,payout = True, amount*14
    else:
        await update_money(ctx.author.id, amount)
        return await ctx.send("❌ Invalid bet! Choose: red, black, green, or a number 0-36")
    if win:
        await update_money(ctx.author.id, payout)
        profit = payout - amount
        await update_gambling_stats(ctx.author.id, won=profit)
        await ctx.send(f"🎯 The ball landed on **{number}** ({color})! You won {format_number(profit)}{emoji}!")
        await update_quest_progress(ctx.author.id, "gamble_win")
    else:
        await update_gambling_stats(ctx.author.id, lost=amount)
        await ctx.send(f"❌ The ball landed on **{number}** ({color}). You lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

# HighLow
@bot.command(name="highlow", aliases=["hl"])
@economy_check()
@gambling_cooldown_check()
async def highlow(ctx, amount_str: str, choice: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    if choice.lower() not in ["h","higher","l","lower"]:
        return await ctx.send("❌ Choose: h (higher) or l (lower)")
    await update_money(ctx.author.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    cards = {2:"2",3:"3",4:"4",5:"5",6:"6",7:"7",8:"8",9:"9",10:"10",11:"J",12:"Q",13:"K",14:"A"}
    values = [2,3,4,5,6,7,8,9,10,11,12,13,14]
    first = random.choice(values); second = random.choice(values)
    if choice.lower() in ["h","higher"] and second>first:
        winnings = int(amount*1.1)
        await update_money(ctx.author.id, winnings)
        profit = winnings - amount
        await update_gambling_stats(ctx.author.id, won=profit)
        await ctx.send(f"🃏 First: {cards[first]}, Second: {cards[second]}\n✅ You won {format_number(profit)}{emoji} (1.1x)!")
        await update_quest_progress(ctx.author.id, "gamble_win")
    elif choice.lower() in ["l","lower"] and second<first:
        winnings = int(amount*1.1)
        await update_money(ctx.author.id, winnings)
        profit = winnings - amount
        await update_gambling_stats(ctx.author.id, won=profit)
        await ctx.send(f"🃏 First: {cards[first]}, Second: {cards[second]}\n✅ You won {format_number(profit)}{emoji} (1.1x)!")
        await update_quest_progress(ctx.author.id, "gamble_win")
    elif second==first:
        await update_money(ctx.author.id, amount)
        await ctx.send(f"🃏 First: {cards[first]}, Second: {cards[second]} (Tie! Money returned).")
    else:
        await update_gambling_stats(ctx.author.id, lost=amount)
        await ctx.send(f"🃏 First: {cards[first]}, Second: {cards[second]}\n❌ You lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

# Dice
@bot.command(name="dice", aliases=["dc"])
@economy_check()
@gambling_cooldown_check()
async def dice(ctx, amount_str: str, guess: int):
    if guess<1 or guess>6: return await ctx.send("❌ Guess must be between 1 and 6.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    roll = random.randint(1,6)
    if roll==guess:
        payout = amount*5
        await update_money(ctx.author.id, payout)
        profit = payout - amount
        await update_gambling_stats(ctx.author.id, won=profit)
        await ctx.send(f"🎲 You rolled a **{roll}**! You guessed correctly! Won {format_number(profit)}{emoji}!")
        await update_quest_progress(ctx.author.id, "gamble_win")
    else:
        await update_gambling_stats(ctx.author.id, lost=amount)
        await ctx.send(f"🎲 You rolled a **{roll}**. You guessed {guess}. Lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

# HorseRace
@bot.command(name="horserace", aliases=["hrace"])
@economy_check()
@gambling_cooldown_check()
async def horserace(ctx, amount_str: str, horse: str):
    horse = horse.upper()
    if horse not in ["A","B","C","D"]: return await ctx.send("❌ Choose horse A, B, C, or D.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    horses = {"A":2.5,"B":3.0,"C":4.0,"D":6.0}
    rand = random.random()
    if rand<0.40: winner="A"
    elif rand<0.70: winner="B"
    elif rand<0.90: winner="C"
    else: winner="D"
    msg = await ctx.send("🏁 **THE RACE IS STARTING!** 🏁\n🏁 A: 🐎     B: 🐎     C: 🐎     D: 🐎")
    frames = [
        "🏁 A: 🐎→   B: 🐎     C: 🐎     D: 🐎",
        "🏁 A: 🐎→→  B: 🐎→    C: 🐎     D: 🐎",
        "🏁 A: 🐎→→→ B: 🐎→→   C: 🐎→    D: 🐎",
        "🏁 A: 🐎→→→→B: 🐎→→→  C: 🐎→→   D: 🐎→",
    ]
    for f in frames:
        await asyncio.sleep(1)
        try:
            await msg.edit(content=f)
        except:
            break
    if horse==winner:
        payout = int(amount*horses[winner])
        await update_money(ctx.author.id, payout)
        profit = payout - amount
        await update_gambling_stats(ctx.author.id, won=profit)
        await ctx.send(f"🏆 **Horse {winner} WINS!** 🏆\nYour horse {horse} won! You won {format_number(profit)}{emoji}!")
        await update_quest_progress(ctx.author.id, "gamble_win")
    else:
        await update_gambling_stats(ctx.author.id, lost=amount)
        await ctx.send(f"🏆 **Horse {winner} WINS!** 🏆\nYour horse {horse} lost. You lost {format_number(amount)}{emoji}.")
    await set_gambling_cooldown(ctx.author.id)

# Rock-Paper-Scissors
class RPSView(discord.ui.View):
    def __init__(self, ctx, bet):
        super().__init__(timeout=60)
        self.ctx = ctx; self.bet = bet; self.ended = False
    async def play(self, interaction, player_choice):
        if self.ended: return
        self.ended = True
        choices = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
        bot_choice = random.choice(list(choices.keys()))
        result = None
        if player_choice == bot_choice: result = "tie"
        elif (player_choice == "rock" and bot_choice == "scissors") or \
             (player_choice == "paper" and bot_choice == "rock") or \
             (player_choice == "scissors" and bot_choice == "paper"):
            result = "win"
        else:
            result = "lose"
        emoji = await get_setting(interaction.guild.id, "currency_emoji")
        if result == "win":
            winnings = self.bet * 2
            await update_money(self.ctx.author.id, winnings)
            profit = winnings - self.bet
            await update_gambling_stats(self.ctx.author.id, won=profit)
            msg = f"You chose **{choices[player_choice]}** {player_choice}, bot chose **{choices[bot_choice]}** {bot_choice}. You won {format_number(profit)}{emoji}!"
            await update_quest_progress(self.ctx.author.id, "gamble_win")
        elif result == "tie":
            await update_money(self.ctx.author.id, self.bet)
            msg = f"Both chose {choices[player_choice]}. Tie! Bet returned."
        else:
            await update_gambling_stats(self.ctx.author.id, lost=self.bet)
            msg = f"You chose **{choices[player_choice]}** {player_choice}, bot chose **{choices[bot_choice]}** {bot_choice}. You lost {format_number(self.bet)}{emoji}."
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(content=msg, view=None)
        await set_gambling_cooldown(self.ctx.author.id)
        self.stop()
    @discord.ui.button(label="🪨 Rock", style=discord.ButtonStyle.secondary)
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "rock")
    @discord.ui.button(label="📄 Paper", style=discord.ButtonStyle.secondary)
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "paper")
    @discord.ui.button(label="✂️ Scissors", style=discord.ButtonStyle.secondary)
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play(interaction, "scissors")

@bot.command(name="rps")
@economy_check()
@gambling_cooldown_check()
async def rps(ctx, amount_str: str):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    view = RPSView(ctx, amount)
    await ctx.send("Choose your move:", view=view)

# Plinko
@bot.command(name="plinko")
@economy_check()
@gambling_cooldown_check()
async def plinko(ctx, amount_str: str, risk: str = "medium", rows: int = 12):
    if risk not in ["low", "medium", "high"]:
        return await ctx.send("Risk must be low, medium, or high.")
    if rows < 8 or rows > 16:
        return await ctx.send("Rows must be between 8 and 16.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if risk == 'low':
        base_mult = [0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 1.5, 1.2, 1.0, 0.8, 0.5]
    elif risk == 'medium':
        base_mult = [0.2, 0.4, 0.7, 1.2, 2.0, 5.0, 2.0, 1.2, 0.7, 0.4, 0.2]
    else:
        base_mult = [0.1, 0.2, 0.4, 0.8, 1.5, 10.0, 1.5, 0.8, 0.4, 0.2, 0.1]
    slots = rows + 1
    mid = len(base_mult) // 2
    multipliers = [base_mult[mid]]
    for i in range(1, slots//2 + 1):
        left_idx = mid - i
        right_idx = mid + i
        if left_idx >= 0:
            multipliers.insert(0, base_mult[left_idx])
        if right_idx < len(base_mult):
            multipliers.append(base_mult[right_idx])
        else:
            multipliers.append(base_mult[-1])
    multipliers = multipliers[:slots]
    while len(multipliers) < slots:
        multipliers.append(0.2)
    col = rows // 2
    path = [col]
    for r in range(rows):
        direction = random.choice([-1, 1])
        col += direction
        col = max(0, min(r + 1, col))
        path.append(col)
    multiplier = multipliers[path[-1]]
    msg = await ctx.send("🎱 Dropping...")
    for step in range(rows + 1):
        board = ""
        for r in range(rows):
            pegs = r + 1
            line = ""
            for c in range(pegs):
                line += "🔴 " if step == r and c == path[r] else "⚪ "
            board += "  " * (rows - r) + line + "\n"
        slot_line = ""
        for c in range(slots):
            slot_line += f"🔴{multipliers[c]}x " if step == rows and c == path[-1] else f" {multipliers[c]}x "
        board += slot_line
        try:
            await msg.edit(content=f"🎱 Plinko\n```\n{board}```")
        except:
            break
        await asyncio.sleep(0.4)
    win_amount = int(amount * multiplier)
    if multiplier > 1:
        await update_money(ctx.author.id, win_amount)
        profit = win_amount - amount
        await update_gambling_stats(ctx.author.id, won=profit)
        result_text = f"💎 Ball landed in **x{multiplier}** slot! You won {format_number(profit)}{emoji}!"
        await update_quest_progress(ctx.author.id, "gamble_win")
    elif multiplier == 1:
        await update_money(ctx.author.id, amount)
        result_text = "🔵 Multiplier 1x – you get your bet back."
    else:
        lost_amount = amount - win_amount
        await update_gambling_stats(ctx.author.id, lost=lost_amount)
        result_text = f"🔴 Lost! Multiplier x{multiplier}, lost {format_number(lost_amount)}{emoji}."
    try:
        await msg.edit(content=f"{msg.content}\n{result_text}")
    except:
        await ctx.send(result_text)
    await set_gambling_cooldown(ctx.author.id)

# Wordle
easy_words = ["apple","beach","bread","chair","cloud","dance","dream","earth","flame","fruit","ghost","grape","green","happy","heart","honey","house","juice","light","magic","mango","metal","money","music","ocean","piano","pizza","plant","queen","radio","river","robot","sheep","smile","snake","sound","space","spoon","stone","storm","sugar","sunny","table","tiger","toast","tower","train","truck","water","whale","world","young","zebra"]
medium_words = ["adobe","agile","aisle","alley","amuse","arena","argue","armor","aroma","arrow","atlas","attic","badge","bagel","banjo","basil","berry","bison","black","blink","bloom","blush","booth","briar","brick","bride","broom","brown","brush","cabin","camel","cargo","carve","cedar","chain","charm","chess","chili","chime","cider","civic","clash","clerk","climb","cloak","clock","clown","cobra","comet","couch","crown","curve"]
hard_words = ["aback","abyss","affix","axiom","azure","balmy","banal","bicep","bluff","boozy","cairn","crypt","cycle","dizzy","dwarf","eject","ennui","equip","exist","fjord","fluff","gauze","ghoul","gnash","gnome","guile","gypsy","haiku","hymen","ivied","jaunt","jazzy","jiffy","jumpy","khaki","llama","lymph","mauve","midge","nymph","ovoid","oxide","prawn","psyche","puffy","quack","quail","qualm","quart","queue","quill","quirk","quota","rabid"]
GUESS_TIMEOUT = 300

class WordleGame:
    def __init__(self, ctx, bet, difficulty):
        self.ctx = ctx
        self.bet = bet
        self.difficulty = difficulty
        if difficulty == "easy":
            self.word = random.choice(easy_words)
        elif difficulty == "hard":
            self.word = random.choice(hard_words)
        else:
            self.word = random.choice(medium_words)
        self.guesses_left = 5
        self.won = False
        self.message = None
    def get_multiplier(self):
        if self.difficulty == "easy": return 1.5
        elif self.difficulty == "hard": return 3.5
        else: return 2.0
    def guess_feedback(self, guess):
        feedback = []
        word_letters = list(self.word)
        for i, (g, w) in enumerate(zip(guess, self.word)):
            if g == w:
                feedback.append("🟩")
                word_letters[i] = None
            else:
                feedback.append("⬛")
        for i, (g, fb) in enumerate(zip(guess, feedback)):
            if fb == "⬛" and g in word_letters:
                feedback[i] = "🟨"
                word_letters[word_letters.index(g)] = None
        return "".join(feedback)
    async def start(self):
        emoji = await get_setting(self.ctx.guild.id, "currency_emoji")
        embed = discord.Embed(title="🔤 Wordle Betting", color=0x9b59b6)
        embed.add_field(name="Difficulty", value=self.difficulty.capitalize(), inline=True)
        embed.add_field(name="Bet", value=f"{format_number(self.bet)} {emoji}", inline=True)
        embed.add_field(name="Multiplier", value=f"{self.get_multiplier()}x", inline=True)
        embed.add_field(name="Guesses", value="5", inline=False)
        embed.set_footer(text="Type your 5-letter guess in chat. 5 minute timeout!")
        self.message = await self.ctx.send(embed=embed)
    async def guess(self, guess: str):
        if len(guess) != 5 or not guess.isalpha():
            await self.ctx.send("❌ Guess must be a 5-letter word.", delete_after=5)
            return False
        guess = guess.lower()
        feedback = self.guess_feedback(guess)
        self.guesses_left -= 1
        embed = self.message.embeds[0]
        current_field = embed.fields[3] if len(embed.fields) > 3 else None
        if current_field:
            previous = current_field.value
        else:
            previous = ""
        new_line = f"{guess.upper()} {feedback}\n"
        if len(embed.fields) >= 4:
            embed.set_field_at(3, name="Guesses", value=previous + new_line, inline=False)
        else:
            embed.add_field(name="Guesses", value=new_line, inline=False)
        embed.set_field_at(2, name="Guesses Left", value=str(self.guesses_left), inline=True)
        await self.message.edit(embed=embed)
        if guess == self.word:
            self.won = True
            return True
        if self.guesses_left == 0:
            return False
        return None

@bot.command(name="wordle")
@economy_check()
@gambling_cooldown_check()
async def wordle(ctx, amount_str: str, difficulty: str = "medium"):
    if difficulty not in ["easy", "medium", "hard"]:
        return await ctx.send("Difficulty must be easy, medium, or hard.")
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    await update_money(ctx.author.id, -amount)
    game = WordleGame(ctx, amount, difficulty)
    await game.start()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    active_wordle_games[ctx.author.id] = game
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    while True:
        try:
            msg = await bot.wait_for("message", timeout=GUESS_TIMEOUT, check=check)
        except asyncio.TimeoutError:
            await update_gambling_stats(ctx.author.id, lost=amount)
            await ctx.send(f"⏰ 5 minute timeout! The word was **{game.word}**. You lost {format_number(amount)}{emoji}.")
            break
        if msg.content.lower().startswith("."):
            continue
        result = await game.guess(msg.content)
        if result is True:
            mult = game.get_multiplier()
            win_amount = int(amount * mult)
            await update_money(ctx.author.id, win_amount)
            profit = win_amount - amount
            await update_gambling_stats(ctx.author.id, won=profit)
            await ctx.send(f"🎉 Correct! The word was **{game.word}**. You won {format_number(profit)}{emoji} (x{mult})!")
            await update_quest_progress(ctx.author.id, "gamble_win")
            break
        elif result is False:
            await update_gambling_stats(ctx.author.id, lost=amount)
            await ctx.send(f"❌ Out of guesses! The word was **{game.word}**. You lost {format_number(amount)}{emoji}.")
            break
    active_wordle_games.pop(ctx.author.id, None)
    await set_gambling_cooldown(ctx.author.id)

# Baccarat
@bot.command(name="baccarat", aliases=["bac"])
@economy_check()
@gambling_cooldown_check()
async def baccarat(ctx, amount_str: str, bet_on: str = None):
    amount, err = await get_bet_amount(ctx, amount_str)
    if err: return await ctx.send(err)
    if bet_on not in ['player', 'banker', 'tie']: return await ctx.send("Bet on: player, banker, or tie.")
    await update_money(ctx.author.id, -amount)
    def calc_value(cards): return sum(cards) % 10
    player_hand = [random.randint(1,9) for _ in range(2)]
    banker_hand = [random.randint(1,9) for _ in range(2)]
    player_val = calc_value(player_hand)
    banker_val = calc_value(banker_hand)
    if player_val <= 5:
        player_hand.append(random.randint(1,9)); player_val = calc_value(player_hand)
    if banker_val <= 5:
        banker_hand.append(random.randint(1,9)); banker_val = calc_value(banker_hand)
    result = "tie"
    if player_val > banker_val: result = "player"
    elif banker_val > player_val: result = "banker"
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    win = False; payout = 0
    if result == bet_on:
        win = True
        if bet_on == 'tie': payout = amount * 8
        else: payout = int(amount * 1.2)
    if win:
        await update_money(ctx.author.id, payout)
        profit = payout - amount
        await update_gambling_stats(ctx.author.id, won=profit)
        msg = f"Player: {player_val}, Banker: {banker_val}. {result.capitalize()} wins! You won {format_number(profit)}{emoji}!"
        await update_quest_progress(ctx.author.id, "gamble_win")
    else:
        await update_gambling_stats(ctx.author.id, lost=amount)
        msg = f"Player: {player_val}, Banker: {banker_val}. {result.capitalize()} wins. You lost {format_number(amount)}{emoji}."
    await ctx.send(msg)
    await set_gambling_cooldown(ctx.author.id)

# ==================================================
# BANK HEIST SYSTEM
# ==================================================
class HeistJoinView(discord.ui.View):
    def __init__(self, leader_id):
        super().__init__(timeout=180)
        self.leader_id = leader_id
        self.members = [leader_id]
        self.message = None
    @discord.ui.button(label="✅ Join & Accept", style=discord.ButtonStyle.success)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.members:
            return await interaction.response.send_message("Already in heist!", ephemeral=True)
        if len(self.members) >= 10:
            return await interaction.response.send_message("Heist is full (max 10)!", ephemeral=True)
        self.members.append(interaction.user.id)
        embed = self.message.embeds[0]
        members_str = "\n".join(f"✅ <@{uid}>" for uid in self.members)
        embed.set_field_at(0, name=f"Members ({len(self.members)}/10)", value=members_str)
        await self.message.edit(embed=embed)
        await interaction.response.send_message("You're in!", ephemeral=True)
    @discord.ui.button(label="❌ Leave", style=discord.ButtonStyle.danger)
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in self.members:
            return await interaction.response.send_message("You're not in this heist!", ephemeral=True)
        if interaction.user.id == self.leader_id:
            return await interaction.response.send_message("Leader cannot leave! Use Cancel instead.", ephemeral=True)
        self.members.remove(interaction.user.id)
        embed = self.message.embeds[0]
        members_str = "\n".join(f"✅ <@{uid}>" for uid in self.members)
        embed.set_field_at(0, name=f"Members ({len(self.members)}/10)", value=members_str)
        await self.message.edit(embed=embed)
        await interaction.response.send_message("You've left the heist.", ephemeral=True)
    @discord.ui.button(label="🚫 Cancel Heist", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.leader_id:
            return await interaction.response.send_message("Only the leader can cancel!", ephemeral=True)
        embed = discord.Embed(title="🚫 Heist Cancelled", description=f"Heist cancelled by <@{self.leader_id}>.", color=0xe74c3c)
        await self.message.edit(embed=embed, view=None)
        self.stop()
    @discord.ui.button(label="⚡ Force Start (Leader)", style=discord.ButtonStyle.primary)
    async def force_start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.leader_id:
            return await interaction.response.send_message("Only the leader can force start!", ephemeral=True)
        if len(self.members) < 2:
            return await interaction.response.send_message("Need at least 2 members to start!", ephemeral=True)
        await self.start_heist()
        self.stop()
    async def start_heist(self):
        member_count = len(self.members)
        success_chance = min(0.20 + (member_count * 0.02), 0.40)
        success = random.random() < success_chance
        if success:
            reward_per_member = 100000 // member_count
            for uid in self.members:
                await update_money(uid, reward_per_member)
            embed = discord.Embed(title="🏦 Bank Heist Successful!",
                                  description=f"Split 100k between {member_count} members!\nEach got {format_number(reward_per_member)}💰",
                                  color=0x2ecc71)
        else:
            fine_per_member = 50000 // member_count
            for uid in self.members:
                await update_money(uid, -fine_per_member)
            embed = discord.Embed(title="🚔 Bank Heist Failed!",
                                  description=f"Police caught you!\nEach member lost {format_number(fine_per_member)}💰",
                                  color=0xe74c3c)
        async with aiosqlite.connect("hakari.db") as db:
            for uid in self.members:
                await db.execute("UPDATE users SET last_heist=? WHERE user_id=?",
                               (datetime.now(timezone.utc).isoformat(), uid))
            await db.commit()
        await self.message.channel.send(embed=embed)
        await self.message.delete()
    async def on_timeout(self):
        try:
            if len(self.members) < 2:
                await self.message.edit(content="❌ Heist cancelled - need at least 2 members!", view=None)
                return
            await self.start_heist()
        except (discord.NotFound, discord.HTTPException):
            pass

@bot.command(name="bankheist", aliases=["heist"])
@economy_check()
async def bank_heist(ctx):
    data = await get_user(ctx.author.id)
    if data.get('last_heist'):
        last = datetime.fromisoformat(data['last_heist'])
        if datetime.now(timezone.utc) - last < timedelta(hours=24):
            remain = timedelta(hours=24) - (datetime.now(timezone.utc) - last)
            return await ctx.send(f"⏰ Heist cooldown: {remain.seconds//3600}h {(remain.seconds%3600)//60}m.")
    view = HeistJoinView(ctx.author.id)
    embed = discord.Embed(title="🏦 Bank Heist Forming", color=0x2ecc71)
    embed.add_field(name=f"Members (1/10)", value=f"✅ {ctx.author.mention}")
    embed.add_field(name="Status", value="Need at least 2 members to start.\n3 minute timer.", inline=False)
    embed.add_field(name="Buttons", value="✅ Join - Join the heist\n❌ Leave - Leave the heist\n🚫 Cancel - Leader cancels heist\n⚡ Force Start - Leader starts early", inline=False)
    embed.set_footer(text="Click 'Join & Accept' to participate!")
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

# ==================================================
# LOTTERY SYSTEM
# ==================================================
@bot.command(name="lottery", aliases=["lotto"])
@economy_check()
async def lottery(ctx):
    jackpot = int(await get_setting(ctx.guild.id, "lottery_jackpot"))
    tickets_sold = await get_setting(ctx.guild.id, "lottery_tickets_sold")
    data = await get_user(ctx.author.id)
    user_tickets = data.get('lottery_tickets', 0)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    
    embed = discord.Embed(title="🎟️ Weekly Lottery", color=0xf1c40f)
    embed.add_field(name="💰 Current Jackpot", value=f"{format_number(jackpot)}{emoji}", inline=True)
    embed.add_field(name="🎫 Tickets Sold", value=str(tickets_sold), inline=True)
    embed.add_field(name="🎟️ Your Tickets", value=str(user_tickets), inline=True)
    embed.add_field(name="💵 Ticket Price", value=f"50,000{emoji} each", inline=False)
    embed.add_field(name="📋 How to Play", 
                    value="`.buyticket <amount>` - Purchase tickets\n"
                          "`.lottery` - View lottery info\n"
                          "`.mytickets` - Check your tickets\n\n"
                          "• More tickets = higher chance to win\n"
                          "• Drawing every Sunday\n"
                          "• Winner takes the entire jackpot!\n"
                          "• 50% of ticket sales go to jackpot", inline=False)
    embed.set_footer(text="Next draw: Sunday | Use .buyticket to enter!")
    await ctx.send(embed=embed)

@bot.command(name="buyticket", aliases=["bt"])
@economy_check()
async def buy_ticket(ctx, amount: int = 1):
    if amount <= 0: return await ctx.send("Must buy at least 1 ticket.")
    cost = amount * 50000
    data = await get_user(ctx.author.id)
    if data['money'] < cost: return await ctx.send(f"You need {format_number(cost)} coins.")
    await update_money(ctx.author.id, -cost)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE guild_settings SET lottery_jackpot = CAST(lottery_jackpot AS INTEGER) + ?, lottery_tickets_sold = lottery_tickets_sold + ? WHERE guild_id=?",
                         (cost // 2, amount, ctx.guild.id))
        await db.execute("UPDATE users SET lottery_tickets = lottery_tickets + ? WHERE user_id=?", (amount, ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Purchased {amount} lottery ticket(s) for {format_number(cost)}{emoji}!")

@bot.command(name="mytickets", aliases=["mt"])
@economy_check()
async def my_tickets(ctx):
    data = await get_user(ctx.author.id)
    tickets = data.get('lottery_tickets', 0)
    jackpot = int(await get_setting(ctx.guild.id, "lottery_jackpot"))
    total_sold = await get_setting(ctx.guild.id, "lottery_tickets_sold")
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    
    if tickets <= 0:
        return await ctx.send(f"You don't have any lottery tickets! Buy some with `.buyticket <amount>`")
    
    chance = (tickets / total_sold * 100) if total_sold > 0 else 0
    
    embed = discord.Embed(title="🎟️ Your Lottery Tickets", color=0xf1c40f)
    embed.add_field(name="Your Tickets", value=str(tickets), inline=True)
    embed.add_field(name="Total Sold", value=str(total_sold), inline=True)
    embed.add_field(name="Win Chance", value=f"{chance:.2f}%", inline=True)
    embed.add_field(name="Current Jackpot", value=f"{format_number(jackpot)}{emoji}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="setlotteryjackpot", aliases=["slj"])
@owner_only()
async def set_lottery_jackpot(ctx, amount_str: str):
    try: amount = parse_amount(amount_str)
    except: return await ctx.send("Invalid amount.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, lottery_jackpot) VALUES (?,?)", 
                         (ctx.guild.id, str(amount)))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Lottery jackpot set to {format_number(amount)}{emoji}.")

@bot.command(name="forcedraw", aliases=["fdraw"])
@owner_only()
async def force_draw(ctx):
    guild_id = ctx.guild.id
    async with aiosqlite.connect("hakari.db") as db:
        jackpot_str = await get_setting(guild_id, "lottery_jackpot")
        jackpot = int(jackpot_str) if jackpot_str else 0
        tickets_sold = await get_setting(guild_id, "lottery_tickets_sold")
        if jackpot <= 0 or tickets_sold <= 0:
            return await ctx.send("No active lottery to draw!")
        async with db.execute("SELECT user_id, lottery_tickets FROM users WHERE lottery_tickets > 0") as cur:
            rows = await cur.fetchall()
        total_tickets = sum(r[1] for r in rows)
        if total_tickets == 0:
            return await ctx.send("No tickets were sold!")
        ticket_winner = random.randint(1, total_tickets)
        winner_id = None
        for uid, tickets in rows:
            ticket_winner -= tickets
            if ticket_winner <= 0:
                winner_id = uid
                break
        if winner_id:
            await update_money(winner_id, jackpot)
            emoji = await get_setting(guild_id, "currency_emoji")
            await ctx.send(f"🎰 Force draw complete! <@{winner_id}> won {format_number(jackpot)}{emoji}!")
            await db.execute("UPDATE guild_settings SET lottery_jackpot = '0', lottery_tickets_sold = 0 WHERE guild_id = ?", (guild_id,))
            await db.execute("UPDATE users SET lottery_tickets = 0")
            await db.commit()

# ==================================================
# SHOP & BUSINESS COMMANDS
# ==================================================
@bot.command(name="createshop", aliases=["cs"])
@economy_check()
async def create_shop(ctx, *, name: str):
    data = await get_user(ctx.author.id)
    if data.get('shop_name'): return await ctx.send("Already have a shop.")
    if len(name)>50: return await ctx.send("Name too long (max 50).")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_name=?, shop_open=1 WHERE user_id=?", (name, ctx.author.id))
        await db.commit()
    await ctx.send(f"Shop '{name}' created!")

@bot.command(name="addshopitem", aliases=["asi"])
@economy_check()
async def add_shop_item(ctx, price_str: str, *, item: str):
    data = await get_user(ctx.author.id)
    if not data.get('shop_name'): return await ctx.send("No shop.")
    if not data.get('shop_open'): return await ctx.send("Shop closed.")
    try: price = parse_amount(price_str)
    except: return await ctx.send("Invalid price (e.g. 500, 1k, 2.5m).")
    if price<=0: return await ctx.send("Positive price required.")
    items = json.loads(data.get('shop_items','{}'))
    if len(items)>=20: return await ctx.send("Shop full.")
    items[item] = price
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items=? WHERE user_id=?", (json.dumps(items), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Added '{item}' for {format_number(price)}{emoji}.")

@bot.command(name="removeshopitem", aliases=["rsi"])
@economy_check()
async def remove_shop_item(ctx, *, item: str):
    data = await get_user(ctx.author.id)
    if not data.get('shop_name'): return await ctx.send("No shop.")
    items = json.loads(data.get('shop_items','{}'))
    if item not in items: return await ctx.send("Item not found.")
    del items[item]
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items=? WHERE user_id=?", (json.dumps(items), ctx.author.id))
        await db.commit()
    await ctx.send(f"Removed '{item}'.")

@bot.command(name="myshop", aliases=["ms"])
@economy_check()
async def my_shop(ctx):
    data = await get_user(ctx.author.id)
    if not data.get('shop_name'): return await ctx.send("No shop.")
    items = json.loads(data.get('shop_items','{}'))
    status = "Open" if data.get('shop_open') else "Closed"
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    embed = discord.Embed(title=f"{data['shop_name']} ({status})", color=0x2ecc71)
    embed.description = "\n".join(f"**{it}**: {format_number(pr)}{emoji}" for it,pr in items.items()) if items else "No items."
    embed.set_footer(text=f"Owner: {ctx.author.display_name}")
    await ctx.send(embed=embed)

@bot.command(name="visitshop", aliases=["vs"])
@economy_check()
async def visit_shop(ctx, owner: discord.User):
    data = await get_user(owner.id)
    if not data.get('shop_name'): return await ctx.send("That user doesn't have a shop.")
    items = json.loads(data.get('shop_items','{}'))
    status = "Open" if data.get('shop_open') else "Closed"
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    embed = discord.Embed(title=f"{data['shop_name']} ({status})", color=0x2ecc71)
    embed.description = "\n".join(f"**{it}**: {format_number(pr)}{emoji}" for it,pr in items.items()) if items else "No items."
    embed.set_footer(text=f"Owner: {owner.display_name}")
    await ctx.send(embed=embed)

@bot.command(name="buyfromshop", aliases=["bfs"])
@economy_check()
async def buy_from_shop(ctx, seller: discord.User, *, item: str):
    sdata = await get_user(seller.id)
    if not sdata.get('shop_name') or not sdata.get('shop_open'):
        return await ctx.send(f"{seller.display_name}'s shop closed.")
    items = json.loads(sdata.get('shop_items','{}'))
    if item not in items: return await ctx.send("Item not found.")
    price = items[item]
    bdata = await get_user(ctx.author.id)
    if bdata['money'] < price: return await ctx.send(f"You need {format_number(price)} coins.")
    tax_rate=10; exempt=await is_tax_exempt(ctx.author.id)
    seller_earnings = price if exempt else price - int(price*tax_rate/100)
    await update_money(ctx.author.id, -price)
    await update_money(seller.id, seller_earnings)
    del items[item]
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items=? WHERE user_id=?", (json.dumps(items), seller.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    msg = f"Bought '{item}' for {format_number(price)}{emoji}."
    if not exempt: msg += f" Seller received {format_number(seller_earnings)}{emoji} after 10% tax."
    else: msg += " (Tax exempt)"
    await ctx.send(embed=discord.Embed(description=msg, color=0x2ecc71))

@bot.command(name="closeshop", aliases=["cls"])
@economy_check()
async def close_shop(ctx):
    data = await get_user(ctx.author.id)
    if not data.get('shop_name'): return await ctx.send("No shop.")
    new = 0 if data.get('shop_open') else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_open=? WHERE user_id=?", (new, ctx.author.id))
        await db.commit()
    await ctx.send(f"Shop is now {'open' if new else 'closed'}.")

@bot.command(name="globalmarket", aliases=["gm"])
@economy_check()
async def global_market(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, shop_name FROM users WHERE shop_open=1 AND shop_name IS NOT NULL LIMIT 20") as cur:
            shops = await cur.fetchall()
    if not shops: return await ctx.send("No open shops.")
    embed = discord.Embed(title="Global Market", color=0xe67e22)
    for uid, name in shops:
        try: u = await bot.fetch_user(uid); embed.add_field(name=name, value=f"Owner: {u.mention}", inline=False)
        except: embed.add_field(name=name, value="Owner unknown", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="buybusiness", aliases=["bb"])
@economy_check()
async def buy_business(ctx, biz_type: str):
    types = ["restaurant","casino","cafe"]
    if biz_type.lower() not in types: return await ctx.send(f"Choose: {', '.join(types)}")
    data = await get_user(ctx.author.id); cost=1000
    if data['money']<cost: return await ctx.send(f"Need {format_number(cost)} coins.")
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            if await cur.fetchone(): return await ctx.send("Already own a business.")
        await update_money(ctx.author.id, -cost)
        await db.execute("INSERT INTO businesses VALUES (?,?,?,?,?,0)", (ctx.author.id, biz_type.lower(), 1, datetime.now(timezone.utc).isoformat(), None))
        await db.commit()
    await ctx.send(f"Bought {biz_type} business!")

@bot.command(name="business", aliases=["biz"])
@economy_check()
async def business_info(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT business_type, level, reputation FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row: return await ctx.send("No business.")
    biz,lvl,rep = row; emoji = await get_setting(ctx.guild.id, "currency_emoji")
    base=50*lvl; total=int(base*(1+rep/100))
    embed = discord.Embed(title=f"{biz}", color=0x2ecc71)
    embed.add_field(name="Level", value=lvl, inline=True)
    embed.add_field(name="Reputation", value=rep, inline=True)
    embed.add_field(name="Income", value=f"{format_number(total)}{emoji}/hour", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="upgradebusiness", aliases=["ub"])
@economy_check()
async def upgrade_business(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row: return await ctx.send("No business.")
    lvl=row[0]; cost=500*lvl; data=await get_user(ctx.author.id)
    if data['money']<cost: return await ctx.send(f"Upgrade costs {format_number(cost)} coins.")
    await update_money(ctx.author.id, -cost)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE businesses SET level=level+1 WHERE user_id=?", (ctx.author.id,))
        await db.commit()
    await ctx.send(f"Upgraded to level {lvl+1}!")

@bot.command(name="collectprofits", aliases=["cp"])
@economy_check()
async def collect_profits(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level, last_collected, reputation FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row: return await ctx.send("No business.")
    lvl,last,rep = row; now=datetime.now(timezone.utc); last_dt=datetime.fromisoformat(last)
    hours=(now-last_dt).total_seconds()/3600
    if hours<1: return await ctx.send(f"Next collection in {int(60*(1-hours))} minutes.")
    base=int(50*lvl*hours); profit=int(base*(1+rep/100))
    await update_money(ctx.author.id, profit)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE businesses SET last_collected=?, reputation=reputation+1 WHERE user_id=?", (now.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Collected {format_number(profit)}{emoji}. Reputation +1.")

@bot.command(name="dailybonus", aliases=["db"])
@economy_check()
async def daily_bonus(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level, daily_bonus_collected, reputation FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row: return await ctx.send("No business.")
    lvl,last_bonus,rep = row; now=datetime.now(timezone.utc)
    if last_bonus and (now-datetime.fromisoformat(last_bonus)).total_seconds()<86400:
        return await ctx.send("Already claimed today.")
    bonus=int(500*lvl*(1+rep/100))
    await update_money(ctx.author.id, bonus)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE businesses SET daily_bonus_collected=? WHERE user_id=?", (now.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Daily bonus: {format_number(bonus)}{emoji}!")

@bot.command(name="sellbusiness", aliases=["sb"])
@economy_check()
async def sell_business(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level, reputation FROM businesses WHERE user_id=?", (ctx.author.id,)) as cur:
            row = await cur.fetchone()
    if not row: return await ctx.send("No business.")
    lvl,rep = row; value=int(500*lvl*(1+rep/200))
    await update_money(ctx.author.id, value)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM businesses WHERE user_id=?", (ctx.author.id,))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Sold for {format_number(value)}{emoji}.")

# ==================================================
# RELATIONSHIP COMMANDS
# ==================================================
async def is_family_member_local(uid, tid):
    async with aiosqlite.connect("hakari.db") as db:
        if await db_fetchone("SELECT 1 FROM children WHERE parent_id=? AND child_id=?", (uid, tid)): return True
        if await db_fetchone("SELECT 1 FROM children WHERE parent_id=? AND child_id=?", (tid, uid)): return True
    return False

@bot.command(name="date")
@economy_check()
async def date(ctx, user: discord.User):
    if user == ctx.author: return await ctx.send("Can't date yourself.")
    if await is_family_member_local(ctx.author.id, user.id): return await ctx.send("Cannot date a family member.")
    data = await get_user(ctx.author.id)
    if data.get('spouse_id'): return await ctx.send("Already married.")
    if data['money'] < 500: return await ctx.send("Need 500 coins.")
    await update_money(ctx.author.id, -500)
    gain = random.randint(50,150)
    await update_affection(user.id, gain)
    await ctx.send(f"Date with {user.mention}! +{gain} affection.")

@bot.command(name="marry")
@economy_check()
async def marry(ctx, user: discord.User):
    if user == ctx.author: return await ctx.send("Can't marry yourself.")
    if await is_family_member_local(ctx.author.id, user.id): return await ctx.send("Cannot marry a family member.")
    data = await get_user(ctx.author.id)
    if data.get('spouse_id'): return await ctx.send("Already married.")
    target = await get_user(user.id)
    if target.get('spouse_id'): return await ctx.send(f"{user.mention} is already married.")
    if data['money'] < 5000: return await ctx.send("Need 5000 coins.")
    if target.get('affection',0) < 1000: return await ctx.send(f"Need 1000 affection with {user.mention}.")
    await update_money(ctx.author.id, -5000)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?,?,?,?)",
                         (ctx.author.id, user.id, "marriage", datetime.now(timezone.utc).isoformat()))
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur: rid = (await cur.fetchone())[0]
    view = RequestView(ctx.author, user, "marriage", rid)
    embed = discord.Embed(title="Marriage Proposal", color=0x9b59b6)
    embed.add_field(name="From", value=ctx.author.mention)
    embed.add_field(name="Time", value="2 minutes")
    await ctx.send(f"{ctx.author.mention} proposed to {user.mention}!", embed=embed, view=view)

class RequestView(discord.ui.View):
    def __init__(self, from_user, to_user, req_type, req_id):
        super().__init__(timeout=120)
        self.from_user=from_user; self.to_user=to_user; self.req_type=req_type; self.req_id=req_id; self.completed=False
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, inter, btn):
        if inter.user.id != self.to_user.id: return await inter.response.send_message("Not for you!", ephemeral=True)
        if self.completed: return
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT from_id, request_type FROM requests WHERE id=?", (self.req_id,)) as cur:
                req = await cur.fetchone()
            if not req: await inter.response.edit_message(content="Expired.", view=None); self.completed=True; return
            fid, rtype = req
            if rtype=="marriage":
                await db.execute("UPDATE users SET spouse_id=? WHERE user_id=?", (self.to_user.id, fid))
                await db.execute("UPDATE users SET spouse_id=? WHERE user_id=?", (fid, self.to_user.id))
                await db.execute("DELETE FROM requests WHERE id=?", (self.req_id,)); await db.commit()
                await inter.response.edit_message(content=f"Married!", view=None)
            elif rtype=="adopt":
                await db.execute("INSERT INTO children (parent_id, child_id) VALUES (?,?)", (fid, self.to_user.id))
                await db.execute("UPDATE users SET parent_id=? WHERE user_id=?", (fid, self.to_user.id))
                await db.execute("DELETE FROM requests WHERE id=?", (self.req_id,)); await db.commit()
                await inter.response.edit_message(content=f"Adopted!", view=None)
        self.completed=True; self.stop()
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, inter, btn):
        if inter.user.id != self.to_user.id: return await inter.response.send_message("Not for you!", ephemeral=True)
        if self.completed: return
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("DELETE FROM requests WHERE id=?", (self.req_id,)); await db.commit()
        await inter.response.edit_message(content=f"Declined.", view=None); self.completed=True; self.stop()

@bot.command(name="divorce")
@economy_check()
async def divorce(ctx):
    data = await get_user(ctx.author.id)
    spouse = data.get('spouse_id')
    if not spouse: return await ctx.send("Not married.")
    if data['money'] < 2500: return await ctx.send("Need 2500 coins.")
    await update_money(ctx.author.id, -2500)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (ctx.author.id,))
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (spouse,))
        await db.commit()
    s = await bot.fetch_user(spouse)
    await ctx.send(f"Divorced {s.mention}.")

@bot.command(name="affection")
@economy_check()
async def affection(ctx, user: discord.User = None):
    target = user or ctx.author
    data = await get_user(target.id)
    aff = data.get('affection',0)
    if aff>=5000: level = "Eternal Bond"
    elif aff>=3500: level = "Soulmates"
    elif aff>=2000: level = "Lovers"
    elif aff>=1000: level = "Close Friends"
    elif aff>=500: level = "Friends"
    else: level = "Strangers"
    bar = "█"*min(20, aff//250) + "░"*(20-min(20, aff//250))
    embed = discord.Embed(title=f"{target.display_name}'s Affection", color=0xe91e63)
    embed.add_field(name="Level", value=level, inline=False)
    embed.add_field(name="Points", value=format_number(aff), inline=False)
    embed.add_field(name="Progress", value=f"`{bar}`", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="gift")
@economy_check()
async def gift(ctx, user: discord.User, amount_str: str):
    if amount_str.lower() == "all":
        data = await get_user(ctx.author.id)
        amount = data['money']
    elif amount_str.lower() == "half":
        data = await get_user(ctx.author.id)
        amount = data['money'] // 2
    else:
        try: amount = parse_amount(amount_str)
        except: return await ctx.send("Invalid amount.")
    if amount<=0 or user == ctx.author: return
    data = await get_user(ctx.author.id)
    if data['money'] < amount: return await ctx.send(f"You have {format_number(data['money'])} coins.")
    await update_money(ctx.author.id, -amount)
    await update_money(user.id, amount)
    gain = amount // 100
    if gain: await update_affection(user.id, gain)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    msg = f"Gifted {format_number(amount)}{emoji} to {user.mention}!"
    if gain: msg += f" (+{format_number(gain)} affection)"
    await ctx.send(msg)

@bot.command(name="adopt")
@economy_check()
async def adopt(ctx, user: discord.User):
    if user == ctx.author: return await ctx.send("Can't adopt yourself.")
    data = await get_user(ctx.author.id)
    if data['money'] < 2000: return await ctx.send("Need 2000 coins.")
    target = await get_user(user.id)
    if target.get('parent_id'): return await ctx.send(f"{user.mention} already has a parent.")
    await update_money(ctx.author.id, -2000)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?,?,?,?)",
                         (ctx.author.id, user.id, "adopt", datetime.now(timezone.utc).isoformat()))
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur: rid = (await cur.fetchone())[0]
    view = RequestView(ctx.author, user, "adopt", rid)
    embed = discord.Embed(title="Adoption Request", color=0x1abc9c)
    embed.add_field(name="From", value=ctx.author.mention)
    embed.add_field(name="Time", value="2 minutes")
    await ctx.send(f"{ctx.author.mention} wants to adopt {user.mention}!", embed=embed, view=view)

@bot.command(name="children")
@economy_check()
async def children(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT child_id FROM children WHERE parent_id=?", (ctx.author.id,)) as cur:
            kids = await cur.fetchall()
    if not kids: return await ctx.send("No children.")
    msg = f"{ctx.author.display_name}'s children:\n"
    for cid in kids:
        try: c = await bot.fetch_user(cid[0]); msg += f"- {c.mention}\n"
        except: msg += f"- User {cid[0]}\n"
    await ctx.send(msg)

@bot.command(name="family")
@economy_check()
async def family(ctx):
    data = await get_user(ctx.author.id)
    spouse = data.get('spouse_id'); parent = data.get('parent_id')
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT child_id FROM children WHERE parent_id=?", (ctx.author.id,)) as cur:
            kids = await cur.fetchall()
    msg = f"**{ctx.author.display_name}'s Family**\n\n"
    if spouse:
        try: s = await bot.fetch_user(spouse); msg += f"Spouse: {s.mention}\n"
        except: msg += f"Spouse: User {spouse}\n"
    else: msg += "Spouse: None\n"
    if parent:
        try: p = await bot.fetch_user(parent); msg += f"Parent: {p.mention}\n"
        except: msg += f"Parent: User {parent}\n"
    else: msg += "Parent: None\n"
    if kids:
        msg += "\nChildren:\n"
        for cid in kids:
            try: c = await bot.fetch_user(cid[0]); msg += f"- {c.mention}\n"
            except: msg += f"- User {cid[0]}\n"
    else: msg += "\nChildren: None"
    await ctx.send(msg)

@bot.command(name="leavefamily")
@economy_check()
async def leave_family(ctx):
    data = await get_user(ctx.author.id)
    parent = data.get('parent_id')
    if not parent: return await ctx.send("You don't have a parent to leave.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM children WHERE parent_id=? AND child_id=?", (parent, ctx.author.id))
        await db.execute("UPDATE users SET parent_id = NULL WHERE user_id = ?", (ctx.author.id,))
        await db.commit()
    await ctx.send(f"You have left your family. No longer a child of <@{parent}>.")

@bot.command(name="pending")
@economy_check()
async def pending(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT id, from_id, request_type FROM requests WHERE to_id=?", (ctx.author.id,)) as cur:
            reqs = await cur.fetchall()
    if not reqs: return await ctx.send("No pending requests.")
    msg = "Pending requests:\n"
    for rid, fid, rtype in reqs:
        try: u = await bot.fetch_user(fid); msg += f"`{rid}`: {u.mention} - {rtype}\n"
        except: msg += f"`{rid}`: User {fid} - {rtype}\n"
    await ctx.send(msg)

# ==================================================
# INVITE REWARD COMMANDS
# ==================================================
@bot.command(name="pricepool", aliases=["pp"])
@economy_check()
async def price_pool(ctx):
    threshold = await get_setting(ctx.guild.id, "invite_threshold")
    reward_str = await get_setting(ctx.guild.id, "invite_reward_amount")
    reward = int(reward_str)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    embed = discord.Embed(title="🏆 Invite Reward", color=0x9b59b6)
    embed.add_field(name="Requirement", value=f"{threshold} invites", inline=True)
    embed.add_field(name="Reward", value=f"{format_number(reward)} {emoji}", inline=True)
    embed.set_footer(text="Use .claim to learn how to claim your reward!")
    await ctx.send(embed=embed)

@bot.command(name="claim")
@economy_check()
async def claim(ctx):
    embed = discord.Embed(title="📨 How to Claim Your Invite Reward", color=0x9b59b6)
    embed.description = (
        "Make sure you invited people to **https://discord.gg/9QsSqQ3aRM**\n"
        "If you did, create a ticket in <#1503152520686731434>\n\n"
        "The owners will verify your invites and add them manually."
    )
    embed.set_footer(text="Invites are verified by server staff.")
    await ctx.send(embed=embed)

@bot.command(name="addinvites", aliases=["ai"])
@owner_only()
async def add_invites(ctx, user: discord.User, amount: int):
    if amount <= 0: return await ctx.send("Amount must be positive.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET invite_count = invite_count + ? WHERE user_id = ?", (amount, user.id))
        await db.commit()
    await ctx.send(f"Added {amount} invites to {user.mention}.")

@bot.command(name="glinv")
@economy_check()
async def global_invites(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, invite_count FROM users WHERE invite_count > 0 ORDER BY invite_count DESC") as cur:
            rows = await cur.fetchall()
    if not rows: return await ctx.send("No invite data yet.")
    per_page=10; total_pages=max(1,(len(rows)+per_page-1)//per_page)
    current_page=1
    async def build_embed(page):
        start=(page-1)*per_page; end=start+per_page
        page_entries=rows[start:end]
        embed = discord.Embed(title="📨 Invite Leaderboard", color=0x9b59b6)
        desc=""
        for i,(uid,count) in enumerate(page_entries, start+1):
            try: user = await bot.fetch_user(uid); mention=user.mention
            except: mention=f"<@{uid}>"
            desc += f"**{i}.** {mention}: **{count}** invites\n"
        embed.description=desc
        embed.set_footer(text=f"Page {page}/{total_pages} · {len(rows)} users")
        return embed
    embed=await build_embed(current_page)
    if total_pages==1: return await ctx.send(embed=embed)
    class LeaderboardView(discord.ui.View):
        def __init__(self): super().__init__(timeout=120); self.current_page=1; self.message = None
        @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
        async def prev(self, inter, btn):
            if inter.user != ctx.author: return await inter.response.send_message("Not your menu!", ephemeral=True)
            self.current_page=(self.current_page-1)%total_pages
            if self.current_page==0: self.current_page=total_pages
            await inter.response.edit_message(embed=await build_embed(self.current_page), view=self)
        @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
        async def nxt(self, inter, btn):
            if inter.user != ctx.author: return await inter.response.send_message("Not your menu!", ephemeral=True)
            self.current_page=(self.current_page+1)%total_pages
            if self.current_page==0: self.current_page=1
            await inter.response.edit_message(embed=await build_embed(self.current_page), view=self)
        async def on_timeout(self):
            try:
                for child in self.children: child.disabled=True
                if self.message:
                    await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass
    view = LeaderboardView()
    msg = await ctx.send(embed=embed, view=view); view.message=msg

@bot.command(name="setinvitereward", aliases=["sir"])
@owner_only()
async def set_invite_reward(ctx, invites: int, amount_str: str):
    try: amount = parse_amount(amount_str)
    except: return await ctx.send("Invalid amount.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, invite_threshold, invite_reward_amount) VALUES (?,?,?)",
                         (ctx.guild.id, invites, str(amount)))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Invite reward set: {invites} invites = {format_number(amount)}{emoji}")

# ==================================================
# HELP COMMANDS
# ==================================================
@bot.command(name="cmds")
async def cmds_command(ctx):
    """Show all commands"""
    try:
        emoji = await get_setting(ctx.guild.id, "currency_emoji")
        pages = [
            discord.Embed(title="📊 Economy Commands", color=0x3498db).add_field(name="💼 Economy", value="`.bal [@user]` - Check balance\n`.dep all/half/1k` - Deposit money\n`.with all/half/1k` - Withdraw money\n`.pay @user all/half/1k` - Pay someone", inline=False).add_field(name="💵 Income", value="`.daily` - Claim daily reward\n`.work` - Work for money (5m)\n`.sleep` - Sleep for money (8h)\n`.crime` - Commit crime (15m, 30% fail)", inline=False).add_field(name="🔫 Crime", value="`.rob @user` - Rob someone (1h, up to 50%)\n`.bankheist` - Start bank heist (2-10 players)", inline=False).add_field(name="🏦 Bank", value="`.interest` - View bank rate (5% per 24h)\n`.security 1-8` - Buy protection (10M base)", inline=False),
            discord.Embed(title="💳 Loan Commands", color=0x9b59b6).add_field(name="💳 Loans", value="`.loan <amount>` - Take loan (max 50k)\n`.repay all/half/amount` - Repay loan\n`.loaninfo` - View loan details\n\n• 10% interest per hour\n• Max loan: 50,000 coins", inline=False),
            discord.Embed(title="🎰 Gambling Commands", color=0xf1c40f).add_field(name="🎲 Classic Games", value="`.cf all/half/1k [heads/tails]` - Coin flip (2x)\n`.dice all/half/1k 1-6` - Dice (5x)\n`.rps all/half/1k` - Rock Paper Scissors\n`.highlow all/half/1k h/l` - High/Low (1.1x)", inline=False).add_field(name="🎰 Casino Games", value="`.slots all/half/1k` - Slot machine\n`.bj all/half/1k` - Blackjack (2.5x)\n`.roulette all/half/1k <bet>` - Roulette\n`.baccarat all/half/1k player/banker/tie` - Baccarat (1.2x)", inline=False).add_field(name="🎮 Mini Games", value="`.crash all/half/1k` - Crash (balanced odds)\n`.mines all/half/1k [1-19]` - Minesweeper\n`.tower all/half/1k` - Tower climb\n`.plinko all/half/1k [risk] [rows]` - Plinko\n`.wordle all/half/1k [easy/medium/hard]` - Wordle (5 tries)\n`.horserace all/half/1k A/B/C/D` - Horse race", inline=False),
            discord.Embed(title="🏦 Bank Heist", color=0xe74c3c).add_field(name="🏦 Heist", value="`.bankheist` - Start bank heist\n\n• 2-10 players needed\n• 3 minute join timer\n• Success: 20% + 2%/member (max 40%)\n• Success: split 100k\n• Fail: split 50k fine\n• 24h cooldown", inline=False),
            discord.Embed(title="🎟️ Lottery", color=0xf1c40f).add_field(name="🎟️ Lottery", value="`.lottery` - View lottery info\n`.buyticket <amount>` - Buy tickets (50k each)\n`.mytickets` - Check your tickets\n\n• More tickets = higher chance\n• Drawn every Sunday\n• Winner takes jackpot", inline=False),
            discord.Embed(title="🏪 Shop & Business", color=0x2ecc71).add_field(name="🏪 Shop", value="`.cs <name>` - Create shop\n`.asi <price> <item>` - Add item\n`.rsi <item>` - Remove item\n`.ms` - View your shop\n`.vs @user` - Visit shop\n`.bfs @user <item>` - Buy item\n`.cls` - Toggle shop open/closed\n`.gm` - Global market", inline=False).add_field(name="🏢 Business", value="`.bb restaurant/casino/cafe` - Buy business\n`.biz` - Business info\n`.ub` - Upgrade business\n`.cp` - Collect profits\n`.db` - Daily bonus\n`.sb` - Sell business", inline=False),
            discord.Embed(title="💕 Relationships", color=0xe91e63).add_field(name="💕 Relationships", value="`.date @user` - Date (500💰)\n`.marry @user` - Propose (5k💰)\n`.divorce` - Divorce (2.5k💰)\n`.affection [@user]` - Check affection\n`.gift @user all/half/1k` - Gift\n`.adopt @user` - Adopt (2k💰)\n`.children` - View children\n`.family` - Family tree\n`.leavefamily` - Leave family\n`.pending` - View requests\n`.topcouples` - Top couples", inline=False),
            discord.Embed(title="📨 Invites", color=0x9b59b6).add_field(name="📨 Invite System", value="`.inv [@user]` - Check invite stats (with PFP)\n`.ci [uses] [age]` - Create invite link\n`.lb i` - Invite leaderboard\n`.lb money` - Money leaderboard\n`.lb xp` - XP leaderboard\n`.pp` - View invite reward info\n`.claim` - How to claim rewards", inline=False).add_field(name="📊 Your Stats", value="Use `.inv` to see:\n• 🟢 Regular joins\n• 🔴 Left\n• 🟡 Fake accounts\n• 📊 Total\n\nProfile picture included!", inline=False),
            discord.Embed(title="📊 Progression", color=0x9b59b6).add_field(name="📈 Leveling", value="`.level` - Check your level & XP\n\n• Earn XP by chatting\n• Level up every 100 XP per level²\n• Milestone rewards every 5 levels!", inline=False).add_field(name="📋 Quests", value="`.tasks` - View daily & weekly quests\n`.badges` - View your badges\n`.bs <b1> <b2> <b3>` - Select showcase badges\n\nComplete quests for bonus coins!", inline=False),
            discord.Embed(title="📊 Leaderboards & Stats", color=0x9b59b6).add_field(name="🏆 Leaderboards", value="`.lb i` - Invite leaderboard\n`.lb money` - Money leaderboard\n`.lb xp` - XP leaderboard\n`.glb money` - Global richest\n`.glb xp` - Global top XP\n`.topcouples` - Top couples", inline=False).add_field(name="📊 Stats", value="`.stats` - Gambling stats (won/lost)\n`.inv [@user]` - Invite stats\n`.mytickets` - Lottery tickets", inline=False),
        ]
        view = HelpPaginator(ctx, pages)
        msg = await ctx.send(embed=pages[0], view=view)
        view.message = msg
    except Exception as e:
        await ctx.send(f"❌ Error loading help menu: {e}")
        print(f"Help error: {e}")

@bot.command(name="ccmds")
@owner_only()
async def ccmds_command(ctx):
    """Show owner commands"""
    try:
        pages = [
            discord.Embed(title="👑 Owner Commands - Money", color=0xe74c3c).add_field(name="💰 Money Management", value="`.addmoney @user <amount>` - Add money to user\n`.removemoney @user all/half/amount` - Remove money\n`.setmoney @user <amount>` - Set wallet balance\n`.addbank @user <amount>` - Add to bank\n`.removebank @user all/half/amount` - Remove from bank", inline=False).add_field(name="🔧 Utilities", value="`.avt @user` - Toggle tax exemption\n`.protect @user` - Protect from robs\n`.unprotect @user` - Remove protection\n`.sst @user` - Reset rob cooldown", inline=False),
            discord.Embed(title="👑 Owner Commands - Users", color=0xe74c3c).add_field(name="👥 User Management", value="`.blacklist @user` - Blacklist user\n`.whitelist @user` - Remove blacklist\n`.addaffection @user <amount>` - Add affection\n`.setaffection @user <amount>` - Set affection\n`.addinvites @user <amount>` - Add invites", inline=False).add_field(name="📢 Other", value="`.rewardlast <amount> [count]` - Reward recent chatters\n`.rewardlasteveryone <amount> [count]` - Reward all servers\n`.economywipe` - Wipe all money\n`.logs [limit]` - View action logs", inline=False),
            discord.Embed(title="👑 Owner Commands - Settings", color=0xe74c3c).add_field(name="⚙️ Server Settings", value="`.toggleeconomy` - Enable/disable economy\n`.togglerob` - Enable/disable robbery\n`.togglegambling` - Enable/disable gambling\n`.setdailyamount <amount>` - Set daily reward\n`.setcurrency <emoji>` - Set currency emoji\n`.setinvitereward <invites> <amount>` - Set invite reward\n`.setlotteryjackpot <amount>` - Set lottery jackpot", inline=False),
            discord.Embed(title="👑 Owner Commands - Bot", color=0xe74c3c).add_field(name="🤖 Bot Management", value="`.addowner @user/ID` - Add bot owner\n`.removeowner @user/ID` - Remove owner\n`.ownerlist` - List all owners\n`.servers` - List all servers\n`.ann <message>` - Announce to all servers", inline=False).add_field(name="🎟️ Lottery Management", value="`.forcedraw` - Force lottery draw\n`.setlotteryjackpot <amount>` - Set jackpot", inline=False),
        ]
        view = HelpPaginator(ctx, pages)
        msg = await ctx.send(embed=pages[0], view=view)
        view.message = msg
    except Exception as e:
        await ctx.send(f"❌ Error loading owner help: {e}")
        print(f"Owner help error: {e}")

@bot.command(name="commands", aliases=["commandlist"])
async def commands_cmd(ctx):
    """Alias for cmds"""
    await cmds_command(ctx)

class HelpPaginator(discord.ui.View):
    def __init__(self, ctx, pages):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.pages = pages
        self.current = 0
        self.message = None
        self.update_buttons()
    def update_buttons(self):
        self.clear_items()
        prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.primary, disabled=self.current==0)
        prev_btn.callback = self.prev_page
        self.add_item(prev_btn)
        page_btn = discord.ui.Button(label=f"📄 Page {self.current+1}/{len(self.pages)}", style=discord.ButtonStyle.secondary)
        page_btn.callback = self.open_page_modal
        self.add_item(page_btn)
        next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.primary, disabled=self.current==len(self.pages)-1)
        next_btn.callback = self.next_page
        self.add_item(next_btn)
    async def open_page_modal(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Not your menu!", ephemeral=True)
        modal = PageModal(self)
        await interaction.response.send_modal(modal)
    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Not your menu!", ephemeral=True)
        if self.current > 0:
            self.current -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current], view=self)
        else:
            await interaction.response.defer()
    async def next_page(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Not your menu!", ephemeral=True)
        if self.current < len(self.pages) - 1:
            self.current += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current], view=self)
        else:
            await interaction.response.defer()
    async def on_timeout(self):
        try:
            for child in self.children: child.disabled=True
            if self.message:
                await self.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

class PageModal(discord.ui.Modal):
    def __init__(self, paginator: HelpPaginator):
        super().__init__(title="Go to Page", timeout=60)
        self.paginator = paginator
        self.page_input = discord.ui.TextInput(
            label=f"Page number (1-{len(paginator.pages)})",
            placeholder="e.g. 2",
            min_length=1,
            max_length=2,
            required=True
        )
        self.add_item(self.page_input)
    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user != self.paginator.ctx.author:
            return await interaction.response.send_message("Not your menu!", ephemeral=True)
        try:
            page_num = int(self.page_input.value)
            if page_num < 1 or page_num > len(self.paginator.pages):
                return await interaction.response.send_message(f"❌ Please enter a number between 1 and {len(self.paginator.pages)}.", ephemeral=True)
            self.paginator.current = page_num - 1
            self.paginator.update_buttons()
            await interaction.response.edit_message(embed=self.paginator.pages[self.paginator.current], view=self.paginator)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)

class ServerPageModal(discord.ui.Modal):
    def __init__(self, view, total_pages, build_embed, ctx):
        super().__init__(title="Jump to Page", timeout=60)
        self.view = view
        self.total_pages = total_pages
        self.build_embed = build_embed
        self.ctx = ctx
        self.page_input = discord.ui.TextInput(
            label=f"Page number (1-{total_pages})",
            placeholder="e.g. 2",
            min_length=1,
            max_length=2,
            required=True
        )
        self.add_item(self.page_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Not your menu!", ephemeral=True)
        try:
            page_num = int(self.page_input.value)
            if page_num < 1 or page_num > self.total_pages:
                return await interaction.response.send_message(
                    f"❌ Please enter a number between 1 and {self.total_pages}.", 
                    ephemeral=True
                )
            self.view.current_page = page_num
            await interaction.response.edit_message(
                embed=await self.build_embed(page_num), 
                view=self.view
            )
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)

# ==================================================
# OWNER COMMANDS
# ==================================================
@bot.command(name="addmoney")
@owner_only()
async def addmoney(ctx, user: discord.User, amount_str: str):
    if amount_str.lower() in ("all","half"):
        return await ctx.send("Cannot use all/half for this command.")
    try: amt = parse_amount(amount_str)
    except: return await ctx.send("Invalid amount.")
    await update_money(user.id, amt)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Added {format_number(amt)}{emoji} to {user.mention}.")

@bot.command(name="removemoney")
@owner_only()
async def removemoney(ctx, user: discord.User, amount_str: str):
    cur = await get_user(user.id)
    total = cur['money'] + cur['bank']
    if amount_str.lower() == "all":
        amt = total
    elif amount_str.lower() == "half":
        amt = total // 2
    else:
        try: amt = parse_amount(amount_str)
        except: return await ctx.send("Invalid amount.")
    if amt <= 0:
        return await ctx.send("Amount must be positive.")
    if total == 0:
        return await ctx.send(f"{user.mention} has 0 coins total.")
    if amt > total:
        amt = total
    if cur['money'] >= amt:
        await update_money(user.id, -amt)
        removed_from = "wallet"
    else:
        taken_from_wallet = cur['money']
        remaining = amt - cur['money']
        await update_money(user.id, -cur['money'])
        await update_bank(user.id, -remaining)
        removed_from = f"wallet ({format_number(taken_from_wallet)}) and bank ({format_number(remaining)})"
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Removed {format_number(amt)}{emoji} from {user.mention} (from {removed_from}).")
    await log_action(ctx.author.id, "RemoveMoney", f"Removed {amt} from {user.id}")

@bot.command(name="setmoney")
@owner_only()
async def setmoney(ctx, user: discord.User, amount_str: str):
    try: amt = parse_amount(amount_str)
    except: return await ctx.send("Invalid amount.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = ? WHERE user_id = ?", (str(amt), user.id)); await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Set {user.mention}'s wallet to {format_number(amt)}{emoji}.")

@bot.command(name="addbank")
@owner_only()
async def addbank(ctx, user: discord.User, amount_str: str):
    try: amt = parse_amount(amount_str)
    except: return await ctx.send("Invalid amount.")
    await update_bank(user.id, amt)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Added {format_number(amt)}{emoji} to {user.mention}'s bank.")

@bot.command(name="removebank")
@owner_only()
async def removebank(ctx, user: discord.User, amount_str: str):
    cur = await get_user(user.id)
    bank = cur['bank']
    if amount_str.lower() == "all":
        amt = bank
    elif amount_str.lower() == "half":
        amt = bank // 2
    else:
        try: amt = parse_amount(amount_str)
        except: return await ctx.send("Invalid amount.")
    if amt <= 0:
        return await ctx.send("Amount must be positive.")
    if bank == 0:
        return await ctx.send(f"{user.mention} has 0 coins in bank.")
    if amt > bank:
        amt = bank
    await update_bank(user.id, -amt)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"Removed {format_number(amt)}{emoji} from {user.mention}'s bank.")
    await log_action(ctx.author.id, "RemoveBank", f"Removed {amt} from {user.id}")

@bot.command(name="avt")
@owner_only()
async def avt(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET tax_exempt = 1 - tax_exempt WHERE user_id = ?", (user.id,)); await db.commit()
    data = await get_user(user.id)
    status = "enabled" if data.get('tax_exempt',0) else "disabled"
    await ctx.send(f"Tax exemption {status} for {user.mention}.")

@bot.command(name="addaffection")
@owner_only()
async def addaffection(ctx, user: discord.User, amount: int):
    await update_affection(user.id, amount)
    await ctx.send(f"Added {amount} affection to {user.mention}.")
    await log_action(ctx.author.id, "AddAffection", f"{user.id} +{amount}")

@bot.command(name="setaffection")
@owner_only()
async def setaffection(ctx, user: discord.User, amount: int):
    await set_affection(user.id, amount)
    await ctx.send(f"Set {user.mention}'s affection to {amount}.")
    await log_action(ctx.author.id, "SetAffection", f"{user.id} ={amount}")

@bot.command(name="rewardlast")
@owner_only()
async def reward_last(ctx, amount_str: str, count: int = 1):
    try: amt = parse_amount(amount_str)
    except: return await ctx.send("Invalid amount.")
    guild_id = ctx.guild.id
    if guild_id not in recent_message_authors: return await ctx.send("No recent message data.")
    dq = recent_message_authors[guild_id]
    seen = set(); rewarded = []
    for uid in reversed(dq):
        if uid not in seen:
            seen.add(uid); rewarded.append(uid)
            if len(rewarded)==count: break
    if not rewarded: return await ctx.send("No eligible users.")
    async with aiosqlite.connect("hakari.db") as db:
        for uid in rewarded:
            async with db.execute("SELECT money FROM users WHERE user_id=?", (uid,)) as cur:
                row = await cur.fetchone()
            cur_money = int(row[0]) if row else 0
            await db.execute("UPDATE users SET money = ? WHERE user_id = ?", (str(cur_money + amt), uid))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    mentions = ', '.join(f"<@{uid}>" for uid in rewarded)
    await ctx.send(f"Added {format_number(amt)}{emoji} to the last {len(rewarded)} message authors: {mentions}")

@bot.command(name="rewardlasteveryone", aliases=["rle"])
@main_owner_only()
async def reward_last_everyone(ctx, amount_str: str, count: int = 10):
    try:
        amt = parse_amount(amount_str)
    except:
        return await ctx.send("Invalid amount.")
    if amt <= 0:
        return await ctx.send("Amount must be positive.")
    all_recent = {}
    now = datetime.now(timezone.utc)
    cutoff_time = now - timedelta(minutes=5)
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute(
            "SELECT user_id FROM users WHERE last_message IS NOT NULL AND last_message > ?",
            (cutoff_time.isoformat(),)
        ) as cur:
            rows = await cur.fetchall()
        for guild_id, dq in recent_message_authors.items():
            for uid in dq:
                all_recent[uid] = now
    eligible_users = []
    seen = set()
    for (uid,) in rows:
        if uid not in seen:
            eligible_users.append(uid)
            seen.add(uid)
    for uid in all_recent:
        if uid not in seen:
            eligible_users.append(uid)
            seen.add(uid)
    eligible_users = eligible_users[:count]
    if not eligible_users:
        return await ctx.send("❌ No eligible users found! Users must have sent a message within the last 5 minutes on any server.")
    rewarded_count = 0
    async with aiosqlite.connect("hakari.db") as db:
        for uid in eligible_users:
            try:
                async with db.execute("SELECT money FROM users WHERE user_id=?", (uid,)) as cur:
                    row = await cur.fetchone()
                cur_money = int(row[0]) if row else 0
                await db.execute("UPDATE users SET money = ? WHERE user_id = ?", (str(cur_money + amt), uid))
                rewarded_count += 1
            except:
                pass
        await db.commit()
    emoji = "💰"
    mentions = ', '.join(f"<@{uid}>" for uid in eligible_users[:5])
    if len(eligible_users) > 5:
        mentions += f" and {len(eligible_users) - 5} more..."
    embed = discord.Embed(title="🌍 Global Reward", color=0x2ecc71)
    embed.description = f"Rewarded **{rewarded_count}** recent chatters across all servers with **{format_number(amt)}{emoji}** each!"
    embed.add_field(name="Recipients", value=mentions, inline=False)
    embed.set_footer(text=f"Only users active within last 5 minutes were eligible")
    await ctx.send(embed=embed)
    await log_action(ctx.author.id, "RewardLastEveryone", f"Rewarded {rewarded_count} users with {amt} each across all servers")

async def resolve_user_id(target: str) -> int:
    if target.startswith('<@') and target.endswith('>'):
        target = target[2:-1]
        if target.startswith('!'): target = target[1:]
    try: return int(target)
    except ValueError: return None

@bot.command(name="addowner")
@owner_only()
@main_owner_only()
async def addowner(ctx, target: str):
    uid = await resolve_user_id(target)
    if uid is None: return await ctx.send("Invalid user. Use a ping (@user) or a numeric ID.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO owners (user_id, is_main) VALUES (?,0)", (uid,)); await db.commit()
    await ctx.send(f"Added <@{uid}> as owner.")

@bot.command(name="removeowner")
@owner_only()
@main_owner_only()
async def removeowner(ctx, target: str):
    uid = await resolve_user_id(target)
    if uid is None: return await ctx.send("Invalid user. Use a ping (@user) or a numeric ID.")
    if uid == MAIN_OWNER_ID: return await ctx.send("Cannot remove main owner.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM owners WHERE user_id=?", (uid,)); await db.commit()
    await ctx.send(f"Removed <@{uid}> from owners.")

@bot.command(name="ownerlist")
@owner_only()
async def ownerlist(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, is_main FROM owners") as cur: rows = await cur.fetchall()
    if not rows: return await ctx.send("No owners.")
    msg = "Bot Owners:\n"
    for uid, main in rows: msg += f"<@{uid}> - {'Main Owner' if main else 'Owner'}\n"
    await ctx.send(msg)

@bot.command(name="protect")
@owner_only()
async def protect(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET protected = 1 WHERE user_id=?", (user.id,)); await db.commit()
    await ctx.send(f"{user.mention} is now protected.")

@bot.command(name="unprotect")
@owner_only()
async def unprotect(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET protected = 0 WHERE user_id=?", (user.id,)); await db.commit()
    await ctx.send(f"{user.mention} is no longer protected.")

@bot.command(name="blacklist")
@owner_only()
async def blacklist(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET blacklisted = 1 WHERE user_id=?", (user.id,)); await db.commit()
    await ctx.send(f"{user.mention} has been blacklisted.")

@bot.command(name="whitelist")
@owner_only()
async def whitelist(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET blacklisted = 0 WHERE user_id=?", (user.id,)); await db.commit()
    await ctx.send(f"{user.mention} has been whitelisted.")

@bot.command(name="economywipe")
@owner_only()
async def economywipe(ctx):
    await ctx.send("Type `confirm` within 30 seconds to wipe all money and bank.")
    def check(m): return m.author == ctx.author and m.content.lower() == "confirm"
    try: await bot.wait_for("message", timeout=30, check=check)
    except: return await ctx.send("Cancelled.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = '0', bank = '0'"); await db.commit()
    await ctx.send("Economy wiped.")

@bot.command(name="toggleeconomy")
@owner_only()
async def toggle_economy(ctx):
    cur = await get_setting(ctx.guild.id, "economy_enabled"); new = 0 if cur else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, economy_enabled) VALUES (?,?)", (ctx.guild.id, new)); await db.commit()
    await ctx.send(f"Economy {'enabled' if new else 'disabled'}.")

@bot.command(name="togglerob")
@owner_only()
async def toggle_rob(ctx):
    cur = await get_setting(ctx.guild.id, "rob_enabled"); new = 0 if cur else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, rob_enabled) VALUES (?,?)", (ctx.guild.id, new)); await db.commit()
    await ctx.send(f"Rob {'enabled' if new else 'disabled'}.")

@bot.command(name="togglegambling")
@owner_only()
async def toggle_gambling(ctx):
    cur = await get_setting(ctx.guild.id, "gambling_enabled"); new = 0 if cur else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, gambling_enabled) VALUES (?,?)", (ctx.guild.id, new)); await db.commit()
    await ctx.send(f"Gambling {'enabled' if new else 'disabled'}.")

@bot.command(name="setdailyamount")
@owner_only()
async def setdaily(ctx, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, daily_amount) VALUES (?,?)", (ctx.guild.id, amount)); await db.commit()
    await ctx.send(f"Daily reward set to {format_number(amount)} coins.")

@bot.command(name="setcurrency")
@owner_only()
async def setcurrency(ctx, emoji: str):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, currency_emoji) VALUES (?,?)", (ctx.guild.id, emoji)); await db.commit()
    await ctx.send(f"Currency emoji set to {emoji}.")

@bot.command(name="skipstealingtime", aliases=["sst"])
@owner_only()
async def skip_stealing_time(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_rob = NULL WHERE user_id = ?", (user.id,)); await db.commit()
    await ctx.send(f"Reset robbery cooldown for {user.mention}.")

@bot.command(name="logs")
@owner_only()
async def logs(ctx, limit: int = 10):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT timestamp, user_id, action, details FROM logs ORDER BY id DESC LIMIT ?", (min(limit,20),)) as cur:
            rows = await cur.fetchall()
    if not rows: return await ctx.send("No logs.")
    msg = "Recent Logs:\n"
    for ts, uid, act, det in rows:
        msg += f"{ts[:16]} - <@{uid}>: {act} {det}\n"
        if len(msg) > 1900: break
    await ctx.send(msg)

@bot.command(name="ann")
@main_owner_only()
async def announce(ctx, *, message: str):
    """Announce to all servers - sends to the most active channel"""
    sent = 0
    for guild in bot.guilds:
        try:
            best_channel = None
            highest_messages = 0
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    try:
                        msg_count = 0
                        async for _ in channel.history(limit=50):
                            msg_count += 1
                        if msg_count > highest_messages:
                            highest_messages = msg_count
                            best_channel = channel
                    except:
                        pass
            if not best_channel:
                best_channel = guild.system_channel or guild.text_channels[0]
            if best_channel and best_channel.permissions_for(guild.me).send_messages:
                embed = discord.Embed(description=message, color=0xf1c40f)
                embed.set_author(name=f"{ctx.author.name} - Owner Of Bot", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
                embed.set_footer(text=f"📢 Official Announcement • {datetime.now(timezone.utc).strftime('%b %d, %Y')}")
                await best_channel.send(embed=embed)
                sent += 1
        except:
            pass
    embed = discord.Embed(title="📢 Announcement Sent", color=0x2ecc71)
    embed.description = f"Message sent to **{sent}/{len(bot.guilds)}** servers"
    embed.add_field(name="Content", value=message[:1024] if len(message) > 1024 else message, inline=False)
    embed.set_footer(text="Sent to the most active channel in each server")
    await ctx.send(embed=embed)

@bot.command(name="servers")
@main_owner_only()
async def servers_list(ctx):
    """Show all servers the bot is in, sorted by member count"""
    try:
        guilds_info = []
        for guild in bot.guilds:
            bot_count = sum(1 for m in guild.members if m.bot)
            human_count = guild.member_count - bot_count
            owner = guild.owner
            owner_name = str(owner) if owner else "Unknown"
            boost_level = guild.premium_tier
            boost_count = guild.premium_subscription_count
            text_channels = len(guild.text_channels)
            voice_channels = len(guild.voice_channels)
            created_at = guild.created_at.strftime("%b %d, %Y")
            guilds_info.append({
                'guild': guild,
                'name': guild.name,
                'id': guild.id,
                'members': guild.member_count,
                'humans': human_count,
                'bots': bot_count,
                'owner': owner_name,
                'owner_id': guild.owner_id,
                'boost_level': boost_level,
                'boost_count': boost_count,
                'text_channels': text_channels,
                'voice_channels': voice_channels,
                'total_channels': text_channels + voice_channels,
                'created_at': created_at,
                'icon_url': guild.icon.url if guild.icon else None,
                'description': guild.description or "No description",
                'features': guild.features,
                'vanity': guild.vanity_url_code,
            })
        guilds_info.sort(key=lambda x: x['members'], reverse=True)
        total_members = sum(g['members'] for g in guilds_info)
        total_humans = sum(g['humans'] for g in guilds_info)
        total_bots = sum(g['bots'] for g in guilds_info)
        per_page = 5
        total_pages = max(1, (len(guilds_info) + per_page - 1) // per_page)
        current_page = 1
        async def build_embed(page):
            start = (page - 1) * per_page
            end = start + per_page
            page_guilds = guilds_info[start:end]
            embed = discord.Embed(title=f"🌐 Bot Servers ({len(bot.guilds)} total)", color=0x3498db)
            embed.set_thumbnail(url=bot.user.avatar.url if bot.user.avatar else bot.user.default_avatar.url)
            desc = ""
            for i, ginfo in enumerate(page_guilds, start + 1):
                boost_emoji = {0: "⚪", 1: "🌱", 2: "🔮", 3: "👑"}.get(ginfo['boost_level'], "⚪")
                verified = "✅" if "VERIFIED" in ginfo['features'] else ""
                partnered = "🤝" if "PARTNERED" in ginfo['features'] else ""
                desc += f"**{i}.** `{ginfo['name']}`\n"
                desc += f"👑 Owner: `{ginfo['owner']}`\n"
                desc += f"👥 Members: **{ginfo['members']}** (👤 {ginfo['humans']} | 🤖 {ginfo['bots']})\n"
                desc += f"📺 Channels: {ginfo['total_channels']} (💬 {ginfo['text_channels']} | 🔊 {ginfo['voice_channels']})\n"
                desc += f"{boost_emoji} Boost: Level {ginfo['boost_level']} ({ginfo['boost_count']} boosts) {verified}{partnered}\n"
                desc += f"📅 Created: {ginfo['created_at']}\n"
                desc += f"🆔 ID: `{ginfo['id']}`\n"
                if ginfo['vanity']:
                    desc += f"🔗 Vanity: `{ginfo['vanity']}`\n"
                if ginfo['description'] != "No description":
                    desc += f"📝 {ginfo['description'][:100]}\n"
                desc += "\n"
            embed.description = desc
            embed.add_field(name="📊 Summary", value=f"**Servers:** {len(bot.guilds)}\n**Total Members:** {format_number(total_members)}\n**Humans:** {format_number(total_humans)}\n**Bots:** {format_number(total_bots)}\n**Avg Members:** {format_number(total_members // len(bot.guilds)) if bot.guilds else 0}", inline=True)
            if bot.shard_count:
                embed.add_field(name="🔧 Shard Info", value=f"**Shards:** {bot.shard_count}\n**Latency:** {round(bot.latency * 1000)}ms", inline=True)
            embed.set_footer(text=f"Page {page}/{total_pages} • Sorted by members • {len(guilds_info)} servers", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            embed.timestamp = datetime.now(timezone.utc)
            return embed
        embed = await build_embed(current_page)
        if total_pages == 1:
            return await ctx.send(embed=embed)
        class ServerLeaderboardView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=120)
                self.current_page = 1
                self.message = None
            @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
            async def prev(self, inter: discord.Interaction, btn: discord.ui.Button):
                if inter.user != ctx.author:
                    return await inter.response.send_message("Not your menu!", ephemeral=True)
                self.current_page = (self.current_page - 1) % total_pages
                if self.current_page == 0:
                    self.current_page = total_pages
                await inter.response.edit_message(embed=await build_embed(self.current_page), view=self)
            @discord.ui.button(label="📄 Jump", style=discord.ButtonStyle.secondary)
            async def jump(self, inter: discord.Interaction, btn: discord.ui.Button):
                if inter.user != ctx.author:
                    return await inter.response.send_message("Not your menu!", ephemeral=True)
                modal = ServerPageModal(self, total_pages, build_embed, ctx)
                await inter.response.send_modal(modal)
            @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
            async def nxt(self, inter: discord.Interaction, btn: discord.ui.Button):
                if inter.user != ctx.author:
                    return await inter.response.send_message("Not your menu!", ephemeral=True)
                self.current_page = (self.current_page + 1) % total_pages
                if self.current_page == 0:
                    self.current_page = 1
                await inter.response.edit_message(embed=await build_embed(self.current_page), view=self)
            async def on_timeout(self):
                try:
                    for child in self.children:
                        child.disabled = True
                    if self.message:
                        await self.message.edit(view=self)
                except (discord.NotFound, discord.HTTPException):
                    pass
        view = ServerLeaderboardView()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
    except Exception as e:
        await ctx.send(f"❌ Error loading server list: {e}")
        print(f"Server list error: {e}")

# ==================================================
# EVENTS
# ==================================================
@bot.event
async def on_ready():
    global custom_currency_emoji
    await init_db()
    loan_interest.start()
    bank_interest.start()
    lottery_draw.start()
    print("Caching invites for all guilds...")
    await cache_invites()
    # Fetch custom currency emoji
    emoji = bot.get_emoji(CUSTOM_CURRENCY_EMOJI_ID)
    if emoji:
        custom_currency_emoji = str(emoji)
    else:
        custom_currency_emoji = "💰"
    print(f"Currency emoji set to: {custom_currency_emoji}")
    print(f"{bot.user} ready. Tracking invites across {len(bot.guilds)} servers.")

@bot.event
async def on_message(message):
    if message.author.bot: return
    guild_id = message.guild.id if message.guild else None
    if guild_id:
        if guild_id not in recent_message_authors:
            recent_message_authors[guild_id] = deque(maxlen=100)
        recent_message_authors[guild_id].append(message.author.id)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.author.id,))
        await db.execute("UPDATE users SET daily_messages = daily_messages + 1, last_message = ? WHERE user_id = ?", 
                         (datetime.now(timezone.utc).isoformat(), message.author.id))
        await db.commit()
    await update_quest_progress(message.author.id, "messages", 1)
    new_lvl = await add_xp(message.author.id, random.randint(10,20))
    if new_lvl:
        if new_lvl % 5 == 0:
            multiplier = new_lvl // 5 - 1
            reward = 75000 * (2 ** multiplier)
            await update_money(message.author.id, reward)
            emoji = await get_setting(message.guild.id, "currency_emoji") if message.guild else "💰"
            lvl_msg = await message.channel.send(f"{message.author.mention} leveled up to level **{new_lvl}**! Milestone reward: +{format_number(reward)}{emoji}!")
        else:
            lvl_msg = await message.channel.send(f"{message.author.mention} leveled up to level **{new_lvl}**!")
        await asyncio.sleep(5)
        try: await lvl_msg.delete()
        except: pass
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    print(f"Error: {error}")

if __name__ == "__main__":
    asyncio.run(bot.start(TOKEN))
