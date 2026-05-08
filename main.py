import discord
from discord.ext import commands, tasks
import aiosqlite
import json
import random
import asyncio
import re
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
# HELPER FUNCTIONS
# ==================================================
def parse_amount(amount_str: str):
    if amount_str.lower() == "all":
        return "all"
    amount_str = amount_str.lower().strip()
    if amount_str.endswith('k'):
        return int(float(amount_str[:-1]) * 1000)
    elif amount_str.endswith('m'):
        return int(float(amount_str[:-1]) * 1000000)
    elif amount_str.endswith('b'):
        return int(float(amount_str[:-1]) * 1000000000)
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
    """Check if target is family member (spouse, parent, child)"""
    user_data = await get_user(user_id)
    target_data = await get_user(target_id)
    
    # Check if married
    if user_data[17] == target_id or target_data[17] == user_id:
        return True
    
    # Check if parent-child relationship
    if user_data[18] == target_id or target_data[18] == user_id:
        return True
    
    # Check if children relationship
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM children WHERE parent_id = ? AND child_id = ?", (user_id, target_id)) as cursor:
            if await cursor.fetchone():
                return True
        async with db.execute("SELECT 1 FROM children WHERE parent_id = ? AND child_id = ?", (target_id, user_id)) as cursor:
            if await cursor.fetchone():
                return True
    
    return False

# ==================================================
# DATABASE SETUP
# ==================================================
async def init_db():
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute('CREATE TABLE IF NOT EXISTS owners (user_id INTEGER PRIMARY KEY, is_main INTEGER DEFAULT 0)')
        await db.execute("INSERT OR IGNORE INTO owners (user_id, is_main) VALUES (?, 1)", (MAIN_OWNER_ID,))
        
        await db.execute('''
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
            )
        ''')
        
        await db.execute('CREATE TABLE IF NOT EXISTS children (parent_id INTEGER, child_id INTEGER, PRIMARY KEY (parent_id, child_id))')
        await db.execute('CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY AUTOINCREMENT, from_id INTEGER, to_id INTEGER, request_type TEXT, timestamp TEXT, amount INTEGER DEFAULT 0)')
        await db.execute('CREATE TABLE IF NOT EXISTS businesses (user_id INTEGER PRIMARY KEY, business_type TEXT, level INTEGER DEFAULT 1, last_collected TIMESTAMP)')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS guild_settings (
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
            )
        ''')
        
        await db.execute('CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, user_id INTEGER, action TEXT, details TEXT)')
        await db.commit()
        
        for guild in bot.guilds:
            await db.execute('INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)', (guild.id,))
        await db.commit()
    print("✅ Database ready!")

# ==================================================
# LOAN INTEREST TASK (Every hour)
# ==================================================
@tasks.loop(hours=1)
async def loan_interest():
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, loan_amount, loan_taken_at FROM users WHERE loan_amount > 0") as cursor:
            users = await cursor.fetchall()
        for user_id, loan_amount, loan_taken_at in users:
            if loan_taken_at:
                interest = int(loan_amount * 0.10)
                new_loan = loan_amount + interest
                await db.execute("UPDATE users SET loan_amount = ? WHERE user_id = ?", (new_loan, user_id))
        await db.commit()
    print("✅ Loan interest calculated")

@loan_interest.before_loop
async def before_loan_interest():
    await bot.wait_until_ready()

# ==================================================
# BANK INTEREST TASK (Daily)
# ==================================================
@tasks.loop(hours=24)
async def bank_interest():
    async with aiosqlite.connect("hakari.db") as db:
        interest_rate = await get_setting(0, "interest_rate") if bot.guilds else 5
        async with db.execute("SELECT user_id, bank, last_interest FROM users WHERE bank > 0") as cursor:
            users = await cursor.fetchall()
        for user_id, bank, last_interest in users:
            if last_interest:
                last = datetime.fromisoformat(last_interest)
                if datetime.utcnow() - last < timedelta(hours=20):
                    continue
            amount_to_interest = min(bank, 50000)
            interest = int(amount_to_interest * (interest_rate / 100))
            if interest > 0:
                await db.execute("UPDATE users SET bank = bank + ?, last_interest = ? WHERE user_id = ?", 
                                (interest, datetime.utcnow().isoformat(), user_id))
        await db.commit()
    print("✅ Bank interest added")

@bank_interest.before_loop
async def before_bank_interest():
    await bot.wait_until_ready()

# ==================================================
# HELPER FUNCTIONS
# ==================================================
async def is_owner(user_id: int) -> bool:
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM owners WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def is_main_owner(user_id: int) -> bool:
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT is_main FROM owners WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row and row[0] == 1

async def get_user(user_id: int):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row
            await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor2:
                return await cursor2.fetchone()

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
        async with db.execute(f"SELECT {setting} FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
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

async def is_blacklisted(user_id: int) -> bool:
    data = await get_user(user_id)
    return data[7] == 1 if data else False

async def is_protected(user_id: int) -> bool:
    data = await get_user(user_id)
    return data[6] == 1 if data else False

async def add_xp(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.execute("UPDATE users SET xp = xp + ?, total_xp = total_xp + ? WHERE user_id = ?", (amount, amount, user_id))
        await db.commit()
        async with db.execute("SELECT total_xp, level FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                total_xp, level = row
                new_level = int((total_xp / 100) ** 0.5)
                if new_level > level:
                    await db.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_level, user_id))
                    await db.commit()
                    return new_level
    return None

async def get_bet_amount(ctx, amount_str, check_balance=True):
    data = await get_user(ctx.author.id)
    if amount_str.lower() == "all":
        amount = data[1]
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return None, "❌ Invalid amount! Use 500, 1k, 2.5m, or 'all'"
    if amount <= 0:
        return None, "❌ Amount must be positive!"
    if check_balance and data[1] < amount:
        return None, f"❌ You have {format_number(data[1])} coins!"
    return amount, None

def economy_check():
    async def predicate(ctx):
        if await get_setting(ctx.guild.id, "economy_enabled") == 0:
            await ctx.send("❌ Economy disabled!")
            return False
        if await is_blacklisted(ctx.author.id):
            await ctx.send("❌ You are blacklisted!")
            return False
        return True
    return commands.check(predicate)

def owner_only():
    async def predicate(ctx):
        if await is_owner(ctx.author.id):
            return True
        await ctx.send("❌ No permission!")
        return False
    return commands.check(predicate)

def main_owner_only():
    async def predicate(ctx):
        if await is_main_owner(ctx.author.id):
            return True
        await ctx.send("❌ Only main owner can use this!")
        return False
    return commands.check(predicate)

# ==================================================
# PAYMENT VIEW - SENDER CONFIRMS FIRST
# ==================================================
class PaymentSenderView(discord.ui.View):
    def __init__(self, sender, recipient, amount, emoji):
        super().__init__(timeout=60)
        self.sender = sender
        self.recipient = recipient
        self.amount = amount
        self.emoji = emoji
        self.completed = False

    @discord.ui.button(label="✅ Confirm Send", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.sender.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        
        sender_data = await get_user(self.sender.id)
        if sender_data[1] < self.amount:
            await interaction.response.edit_message(content=f"❌ You no longer have enough coins! You have {format_number(sender_data[1])}{self.emoji}", view=None)
            self.completed = True
            return
        
        view = PaymentRecipientView(self.sender, self.recipient, self.amount, self.emoji)
        embed = discord.Embed(title="💸 Payment Request", color=discord.Color.blue())
        embed.add_field(name="From", value=self.sender.mention, inline=True)
        embed.add_field(name="Amount", value=f"{format_number(self.amount)}{self.emoji}", inline=True)
        embed.add_field(name="⏱️ Time", value="60 seconds", inline=True)
        
        await interaction.response.edit_message(content=f"✅ You confirmed sending {format_number(self.amount)}{self.emoji} to {self.recipient.mention}. Waiting for recipient to accept...", view=None)
        
        await interaction.channel.send(f"💸 {self.recipient.mention}, {self.sender.mention} wants to send you {format_number(self.amount)}{self.emoji}. Do you accept?", embed=embed, view=view)
        self.completed = True
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.sender.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        await interaction.response.edit_message(content=f"❌ Payment cancelled.", view=None)
        self.completed = True
        self.stop()

    async def on_timeout(self):
        if not self.completed:
            channel = self.sender.dm_channel or await self.sender.create_dm()
            await channel.send(f"⏰ Payment confirmation for {format_number(self.amount)}{self.emoji} to {self.recipient.mention} expired.")

class PaymentRecipientView(discord.ui.View):
    def __init__(self, sender, recipient, amount, emoji):
        super().__init__(timeout=60)
        self.sender = sender
        self.recipient = recipient
        self.amount = amount
        self.emoji = emoji
        self.completed = False

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.recipient.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        
        sender_data = await get_user(self.sender.id)
        if sender_data[1] < self.amount:
            await interaction.response.edit_message(content=f"❌ {self.sender.mention} no longer has enough coins!", view=None)
            self.completed = True
            return
        
        await update_money(self.sender.id, -self.amount)
        await update_money(self.recipient.id, self.amount)
        await interaction.response.edit_message(content=f"✅ {self.sender.mention} paid {format_number(self.amount)}{self.emoji} to {self.recipient.mention}!", view=None)
        self.completed = True
        self.stop()

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.recipient.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        await interaction.response.edit_message(content=f"❌ {self.recipient.mention} declined the payment.", view=None)
        self.completed = True
        self.stop()

    async def on_timeout(self):
        if not self.completed:
            channel = self.recipient.dm_channel or await self.recipient.create_dm()
            await channel.send(f"⏰ Payment request from {self.sender.mention} to {self.recipient.mention} expired.")

# ==================================================
# REQUEST VIEW (Marry/Adopt) - IN CHANNEL
# ==================================================
class RequestView(discord.ui.View):
    def __init__(self, from_user, to_user, request_type, request_id):
        super().__init__(timeout=120)
        self.from_user = from_user
        self.to_user = to_user
        self.request_type = request_type
        self.request_id = request_id
        self.completed = False

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.to_user.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        
        async with aiosqlite.connect("hakari.db") as db:
            async with db.execute("SELECT from_id, request_type FROM requests WHERE id = ?", (self.request_id,)) as cursor:
                req = await cursor.fetchone()
            if not req:
                await interaction.response.edit_message(content="❌ Request no longer exists.", view=None)
                self.completed = True
                return
            from_id, req_type = req
            if req_type == "marriage":
                await db.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (self.to_user.id, from_id))
                await db.execute("UPDATE users SET spouse_id = ? WHERE user_id = ?", (from_id, self.to_user.id))
                await db.execute("DELETE FROM requests WHERE id = ?", (self.request_id,))
                await db.commit()
                await interaction.response.edit_message(content=f"💕 {self.from_user.mention} and {self.to_user.mention} are now married! 🎉", view=None)
            elif req_type == "adopt":
                await db.execute("INSERT INTO children (parent_id, child_id) VALUES (?, ?)", (from_id, self.to_user.id))
                await db.execute("UPDATE users SET parent_id = ? WHERE user_id = ?", (from_id, self.to_user.id))
                await db.execute("DELETE FROM requests WHERE id = ?", (self.request_id,))
                await db.commit()
                await interaction.response.edit_message(content=f"👶 {self.from_user.mention} adopted {self.to_user.mention}!", view=None)
        self.completed = True
        self.stop()

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.to_user.id:
            return await interaction.response.send_message("Not for you!", ephemeral=True)
        if self.completed:
            return
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("DELETE FROM requests WHERE id = ?", (self.request_id,))
            await db.commit()
        await interaction.response.edit_message(content=f"❌ {self.to_user.mention} declined the {self.request_type} request.", view=None)
        self.completed = True
        self.stop()

    async def on_timeout(self):
        if not self.completed:
            async with aiosqlite.connect("hakari.db") as db:
                await db.execute("DELETE FROM requests WHERE id = ?", (self.request_id,))
                await db.commit()
            channel = self.to_user.dm_channel or await self.to_user.create_dm()
            await channel.send(f"⏰ {self.request_type.capitalize()} request from {self.from_user.mention} expired.")

# ==================================================
# BLACKJACK VIEW
# ==================================================
class BlackjackView(discord.ui.View):
    def __init__(self, ctx, amount, player_hand, dealer_hand, bet):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.amount = amount
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.bet = bet
        self.game_over = False
        self.emoji = None
        self.stand_clicked = False
        self.start_time = datetime.utcnow()

    def card_to_emoji(self, card):
        emojis = {2: "🃒", 3: "🃓", 4: "🃔", 5: "🃕", 6: "🃖", 7: "🃗", 8: "🃘", 9: "🃙", 10: "🃚", 11: "🃑"}
        return emojis.get(card, "🃟")

    async def get_hand_value(self, hand):
        value = sum(hand)
        aces = hand.count(11)
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    async def get_embed(self):
        remaining = 120 - (datetime.utcnow() - self.start_time).total_seconds()
        mins = int(max(0, remaining) // 60)
        secs = int(max(0, remaining) % 60)
        
        player_value = await self.get_hand_value(self.player_hand)
        player_cards = " ".join([self.card_to_emoji(card) for card in self.player_hand])
        
        if not self.stand_clicked and len(self.dealer_hand) == 2:
            dealer_display = f"{self.card_to_emoji(self.dealer_hand[0])} ?"
            dealer_value_display = "?"
        else:
            dealer_display = " ".join([self.card_to_emoji(card) for card in self.dealer_hand])
            dealer_value = await self.get_hand_value(self.dealer_hand)
            dealer_value_display = str(dealer_value)
        
        embed = discord.Embed(title=f"{self.ctx.author.display_name}'s Blackjack", color=0x2ecc71)
        embed.add_field(name="Your Hand", value=f"{player_cards}\n**{player_value}**", inline=False)
        embed.add_field(name="Dealer", value=f"{dealer_display}\n**{dealer_value_display}**", inline=False)
        embed.add_field(name="💰 Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
        embed.add_field(name="⏱️ Time", value=f"{mins}m {secs}s", inline=True)
        return embed

    async def end_game(self, result, win_amount=0):
        player_cards = " ".join([self.card_to_emoji(card) for card in self.player_hand])
        dealer_cards = " ".join([self.card_to_emoji(card) for card in self.dealer_hand])
        player_value = await self.get_hand_value(self.player_hand)
        dealer_value = await self.get_hand_value(self.dealer_hand)
        
        embed = discord.Embed(title=f"{self.ctx.author.display_name}'s Blackjack - Game Over", color=0xe74c3c)
        embed.add_field(name="Your Hand", value=f"{player_cards}\n**{player_value}**", inline=False)
        embed.add_field(name="Dealer's Hand", value=f"{dealer_cards}\n**{dealer_value}**", inline=False)
        
        if result == "win":
            await update_money(self.ctx.author.id, win_amount)
            embed.add_field(name="Result", value=f"✅ You won {format_number(win_amount)}{self.emoji}!", inline=False)
        elif result == "lose":
            embed.add_field(name="Result", value=f"❌ You lost {format_number(self.bet)}{self.emoji}!", inline=False)
        elif result == "push":
            await update_money(self.ctx.author.id, self.bet)
            embed.add_field(name="Result", value=f"🤝 Push!", inline=False)
        elif result == "blackjack":
            winnings = int(self.bet * 2.5)
            await update_money(self.ctx.author.id, winnings)
            embed.add_field(name="Result", value=f"🎉 BLACKJACK! Won {format_number(winnings)}{self.emoji}!", inline=False)
        else:
            embed.add_field(name="Result", value=f"⏰ Timeout! Lost {format_number(self.bet)}{self.emoji}.", inline=False)
        
        await self.ctx.send(embed=embed)
        self.game_over = True
        self.stop()

    async def update_message(self, interaction):
        remaining = 120 - (datetime.utcnow() - self.start_time).total_seconds()
        mins = int(max(0, remaining) // 60)
        secs = int(max(0, remaining) % 60)
        
        player_value = await self.get_hand_value(self.player_hand)
        player_cards = " ".join([self.card_to_emoji(card) for card in self.player_hand])
        
        if not self.stand_clicked and len(self.dealer_hand) == 2:
            dealer_display = f"{self.card_to_emoji(self.dealer_hand[0])} ?"
            dealer_value_display = "?"
        else:
            dealer_display = " ".join([self.card_to_emoji(card) for card in self.dealer_hand])
            dealer_value = await self.get_hand_value(self.dealer_hand)
            dealer_value_display = str(dealer_value)
        
        embed = discord.Embed(title=f"{self.ctx.author.display_name}'s Blackjack", color=0x2ecc71)
        embed.add_field(name="Your Hand", value=f"{player_cards}\n**{player_value}**", inline=False)
        embed.add_field(name="Dealer", value=f"{dealer_display}\n**{dealer_value_display}**", inline=False)
        embed.add_field(name="💰 Bet", value=f"{format_number(self.bet)} {self.emoji}", inline=True)
        embed.add_field(name="⏱️ Time", value=f"{mins}m {secs}s", inline=True)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return
        cards = [2,3,4,5,6,7,8,9,10,10,10,10,11]
        self.player_hand.append(random.choice(cards))
        if await self.get_hand_value(self.player_hand) > 21:
            await self.end_game("lose")
            await interaction.message.delete()
            return
        await self.update_message(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return
        self.stand_clicked = True
        player_value = await self.get_hand_value(self.player_hand)
        while await self.get_hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11]))
        dealer_value = await self.get_hand_value(self.dealer_hand)
        if dealer_value > 21 or player_value > dealer_value:
            await self.end_game("win", int(self.bet * 2))
        elif player_value < dealer_value:
            await self.end_game("lose")
        else:
            await self.end_game("push", self.bet)
        await interaction.message.delete()
        self.stop()

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.danger)
    async def double_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return
        self.bet *= 2
        self.player_hand.append(random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11]))
        if await self.get_hand_value(self.player_hand) > 21:
            await self.end_game("lose")
            await interaction.message.delete()
            return
        await self.stand_button.callback(interaction, button)

    async def on_timeout(self):
        if not self.game_over:
            await self.end_game("timeout")

# ==================================================
# MINES VIEW - FIXED (No cashout without revealing)
# ==================================================
class MinesView(discord.ui.View):
    def __init__(self, ctx, bet, mines_count, multiplier, emoji):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.bet = bet
        self.mines_count = mines_count
        self.multiplier = multiplier
        self.emoji = emoji
        self.revealed = [False] * 20
        self.mine_positions = set(random.sample(range(20), mines_count))
        self.game_over = False
        self.safe_reveals = 0
        self.start_time = datetime.utcnow()
        for i in range(20):
            btn = discord.ui.Button(label="⬛", style=discord.ButtonStyle.secondary, row=i//5, custom_id=f"mine_{i}")
            btn.callback = self.make_callback(i)
            self.add_item(btn)
        self.cashout_btn = discord.ui.Button(label="💰 Cashout", style=discord.ButtonStyle.success, row=4)
        self.cashout_btn.callback = self.cashout_callback
        self.add_item(self.cashout_btn)
        self.quit_btn = discord.ui.Button(label="❌ Quit", style=discord.ButtonStyle.danger, row=4)
        self.quit_btn.callback = self.quit_callback
        self.add_item(self.quit_btn)

    def make_callback(self, pos):
        async def callback(interaction: discord.Interaction):
            if interaction.user != self.ctx.author:
                return
            if self.game_over or self.revealed[pos]:
                return
            self.revealed[pos] = True
            if pos in self.mine_positions:
                self.game_over = True
                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.custom_id and child.custom_id.startswith("mine_"):
                        tile_pos = int(child.custom_id.split("_")[1])
                        if tile_pos in self.mine_positions:
                            child.label = "💣"
                            child.style = discord.ButtonStyle.danger
                        elif self.revealed[tile_pos]:
                            child.label = "💎"
                            child.style = discord.ButtonStyle.success
                        child.disabled = True
                await interaction.response.edit_message(content=f"💥 BOOM! You hit a mine! You lost {format_number(self.bet)}{self.emoji}.", view=self)
                await update_money(self.ctx.author.id, -self.bet)
                self.stop()
            else:
                self.safe_reveals += 1
                self.multiplier = round(1.02 * (25 / (25 - self.mines_count)) ** (1 + self.safe_reveals*0.1), 2)
                self.multiplier = min(self.multiplier, 100)
                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.custom_id == f"mine_{pos}":
                        child.label = "💎"
                        child.style = discord.ButtonStyle.success
                        child.disabled = True
                        break
                
                remaining = 120 - (datetime.utcnow() - self.start_time).total_seconds()
                mins = int(max(0, remaining) // 60)
                secs = int(max(0, remaining) % 60)
                
                board_display = ""
                for i in range(20):
                    if self.revealed[i]:
                        board_display += "💎 "
                    else:
                        board_display += "⬛ "
                    if (i+1) % 5 == 0:
                        board_display += "\n"
                
                embed = discord.Embed(title="💣 Minesweeper", color=discord.Color.gold())
                embed.add_field(name="Board", value=board_display, inline=False)
                embed.add_field(name="Mines", value=f"{self.mines_count} bombs", inline=True)
                embed.add_field(name="Multiplier", value=f"{self.multiplier}x", inline=True)
                embed.add_field(name="Cashout", value=f"{format_number(int(self.bet * self.multiplier))} {self.emoji}", inline=True)
                embed.add_field(name="⏱️ Time", value=f"{mins}m {secs}s", inline=True)
                await interaction.response.edit_message(embed=embed, view=self)
        return callback

    async def cashout_callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return
        if self.game_over:
            return
        if self.safe_reveals == 0:
            return await interaction.response.send_message("❌ You must reveal at least one tile before cashing out!", ephemeral=True)
        
        winnings = int(self.bet * self.multiplier)
        await update_money(self.ctx.author.id, winnings)
        await interaction.response.edit_message(content=f"💰 You cashed out and won {format_number(winnings)}{self.emoji}!", view=None)
        self.game_over = True
        self.stop()

    async def quit_callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author or self.game_over:
            return
        await interaction.response.edit_message(content=f"❌ You quit. Lost {format_number(self.bet)}{self.emoji}.", view=None)
        self.game_over = True
        self.stop()

    async def on_timeout(self):
        if not self.game_over:
            await self.ctx.send(f"⏰ {self.ctx.author.mention} took too long! Lost {format_number(self.bet)}{self.emoji}.")

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

    @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
    async def prev(self, interaction, btn):
        if interaction.user != self.ctx.author:
            return
        self.page = (self.page - 1) % len(self.pages)
        await self.update(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def nxt(self, interaction, btn):
        if interaction.user != self.ctx.author:
            return
        self.page = (self.page + 1) % len(self.pages)
        await self.update(interaction)

    @discord.ui.button(label="❌", style=discord.ButtonStyle.danger)
    async def close(self, interaction, btn):
        if interaction.user != self.ctx.author:
            return
        await interaction.message.delete()

@bot.command(name="cmds", aliases=["commands"])
async def show_commands(ctx):
    owner = await is_owner(ctx.author.id)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    
    pages = [
        discord.Embed(title=f"💰 Economy Commands (1/7)", color=discord.Color.blue()).add_field(
            name="Commands", 
            value=f"`.balance` / `.bal` - Check balance\n"
                  f"`.daily` - Claim {emoji}1500 (need 10 messages)\n"
                  f"`.work` - Work for {emoji}150-300 (5 min)\n"
                  f"`.sleep` - Sleep for {emoji}2000-2500 (8h)\n"
                  f"`.crime` - Commit crime {emoji}200-800 (15 min)\n"
                  f"`.deposit <amount/all>` - Deposit\n"
                  f"`.withdraw <amount/all>` - Withdraw (max 50k)\n"
                  f"`.pay <@user> <amount/all>` - Send (both confirm)\n"
                  f"`.rob <@user>` - Rob (1h cooldown)\n"
                  f"`.interest` - Check bank interest", 
            inline=False
        ),
        discord.Embed(title=f"🏦 Loan Commands (2/7)", color=discord.Color.purple()).add_field(
            name="Commands", 
            value=f"`.loan <amount>` - Borrow money (10% hourly interest)\n"
                  f"`.repay <amount/all/half>` - Repay your loan\n"
                  f"`.loaninfo` - Check loan status", 
            inline=False
        ),
        discord.Embed(title=f"🎰 Gambling Games (3/7)", color=discord.Color.gold()).add_field(
            name="Games (use 'all' or 1k, 2.5m)", 
            value=f"`.cf <amount> [heads/tails]` - Coinflip\n"
                  f"`.slots <amount>` - Slot machine\n"
                  f"`.bj <amount>` - Blackjack\n"
                  f"`.crash <amount>` - Crash game\n"
                  f"`.mines <amount> <mines>` - Mines (must reveal 1 tile to cashout)\n"
                  f"`.tower <amount> <floors>` - Tower", 
            inline=False
        ),
        discord.Embed(title=f"🛒 Shop & Business (4/7)", color=discord.Color.green()).add_field(
            name="Commands", 
            value="`.createshop <name>` - Create shop\n"
                  "`.addshopitem <price> <item>` - Add item\n"
                  "`.removeshopitem <item>` - Remove\n"
                  "`.myshop` - View shop\n"
                  "`.visitshop <@user>` - Visit shop\n"
                  "`.buyfromshop <@user> <item>` - Buy\n"
                  "`.closeshop` - Open/close\n"
                  "`.globalmarket` - All shops\n"
                  "`.buybusiness <type>` - Buy business\n"
                  "`.business` - View\n"
                  "`.upgradebusiness` - Upgrade\n"
                  "`.collectprofits` - Collect\n"
                  "`.sellbusiness` - Sell", 
            inline=False
        ),
        discord.Embed(title=f"💕 Relationships (5/7)", color=discord.Color.pink()).add_field(
            name="Commands", 
            value="`.date <@user>` - Go on date (no family members!)\n"
                  "`.marry <@user>` - Propose\n"
                  "`.divorce` - Divorce\n"
                  "`.affection` - Check love\n"
                  "`.gift <@user> <amount>` - Gift coins\n"
                  "`.adopt <@user>` - Adopt\n"
                  "`.children` - List\n"
                  "`.family` - Family tree", 
            inline=False
        ),
        discord.Embed(title=f"📊 Leaderboards (6/7)", color=discord.Color.purple()).add_field(
            name="Commands", 
            value="`.glb money` / `.glb xp` - Global\n"
                  "`.slb money` / `.slb xp` - Server\n"
                  "`.topcouples` - Top couples\n"
                  "`.level` / `.rank` - Your rank", 
            inline=False
        ),
    ]
    
    if owner:
        pages.append(discord.Embed(title=f"👑 Owner Commands (7/7)", color=discord.Color.red()).add_field(
            name="Commands", 
            value="`.addowner <id>` - Add owner\n"
                  "`.removeowner <id>` - Remove owner\n"
                  "`.ownerlist` - List owners\n"
                  "`.addmoney <@user> <amount>` - Add money\n"
                  "`.removemoney <@user> <amount>` - Remove\n"
                  "`.setmoney <@user> <amount>` - Set\n"
                  "`.addbank <@user> <amount>` - Add bank\n"
                  "`.removebank <@user> <amount>` - Remove bank\n"
                  "`.protect <@user>` - Protect\n"
                  "`.unprotect <@user>` - Unprotect\n"
                  "`.blacklist <@user>` - Blacklist\n"
                  "`.whitelist <@user>` - Whitelist\n"
                  "`.economywipe` - Wipe economy\n"
                  "`.toggleeconomy` / `.togglerob` / `.togglegambling`\n"
                  "`.setdailyamount` / `.setsleepamount` / `.setworkamount` / `.setcrimeamount`\n"
                  "`.setinterestrate` / `.setloaninterest`\n"
                  "`.setmaxwithdraw`\n"
                  "`.setcurrency <emoji>`\n"
                  "`.logs` - View logs", 
            inline=False
        ))
    
    await ctx.send(embed=pages[0], view=CommandsView(ctx, pages))

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
    embed.add_field(name="Total", value=f"{format_number(data[1] + data[2])}{emoji}", inline=True)
    if data[22] > 0:
        embed.add_field(name="⚠️ Active Loan", value=f"{format_number(data[22])}{emoji}", inline=True)
    embed.set_footer(text=f"Level {data[4]} | {data[5]} XP")
    await ctx.send(embed=embed)

@bot.command(name="daily")
@economy_check()
async def daily(ctx):
    data = await get_user(ctx.author.id)
    if data[8]:
        last = datetime.fromisoformat(data[8])
        if datetime.utcnow() - last < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Already claimed! Try again in {remaining.seconds//3600}h")
    needed = await get_setting(ctx.guild.id, "daily_messages_needed")
    if data[13] < needed:
        return await ctx.send(f"❌ Need {needed - data[13]} more messages today!")
    amount = await get_setting(ctx.guild.id, "daily_amount")
    await update_money(ctx.author.id, amount)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_daily = ?, daily_messages = 0 WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Daily reward claimed! +{format_number(amount)}{emoji}")

@bot.command(name="work")
@economy_check()
async def work(ctx):
    data = await get_user(ctx.author.id)
    if data[9]:
        last = datetime.fromisoformat(data[9])
        if datetime.utcnow() - last < timedelta(minutes=5):
            remaining = timedelta(minutes=5) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Try again in {remaining.seconds//60}m")
    min_amt = await get_setting(ctx.guild.id, "work_amount_min")
    max_amt = await get_setting(ctx.guild.id, "work_amount_max")
    earnings = random.randint(min_amt, max_amt)
    await update_money(ctx.author.id, earnings)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_work = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"💼 You worked and earned {format_number(earnings)}{emoji}!")

@bot.command(name="sleep")
@economy_check()
async def sleep(ctx):
    data = await get_user(ctx.author.id)
    if data[11]:
        last = datetime.fromisoformat(data[11])
        if datetime.utcnow() - last < timedelta(hours=8):
            remaining = timedelta(hours=8) - (datetime.utcnow() - last)
            return await ctx.send(f"😴 Try again in {remaining.seconds//3600}h")
    min_amt = await get_setting(ctx.guild.id, "sleep_amount_min")
    max_amt = await get_setting(ctx.guild.id, "sleep_amount_max")
    earnings = random.randint(min_amt, max_amt)
    await update_money(ctx.author.id, earnings)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_sleep = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"😴 You slept and woke up with {format_number(earnings)}{emoji}!")

@bot.command(name="crime")
@economy_check()
async def crime(ctx):
    data = await get_user(ctx.author.id)
    if data[12]:
        last = datetime.fromisoformat(data[12])
        if datetime.utcnow() - last < timedelta(minutes=15):
            remaining = timedelta(minutes=15) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Try again in {remaining.seconds//60}m")
    crimes = [{"name": "Pickpocketing", "rate": 0.7}, {"name": "Store robbery", "rate": 0.55}, {"name": "Bank heist", "rate": 0.4}]
    crime = random.choice(crimes)
    success = random.random() < crime["rate"]
    min_amt = await get_setting(ctx.guild.id, "crime_amount_min")
    max_amt = await get_setting(ctx.guild.id, "crime_amount_max")
    reward = random.randint(min_amt, max_amt)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if success:
        await update_money(ctx.author.id, reward)
        await ctx.send(f"🦹 {crime['name']} successful! +{format_number(reward)}{emoji}!")
    else:
        penalty = reward // 2
        if data[1] >= penalty:
            await update_money(ctx.author.id, -penalty)
            await ctx.send(f"🚔 Caught! Lost {format_number(penalty)}{emoji}!")
        else:
            await ctx.send(f"🚔 Caught! You went to jail!")
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
            return await ctx.send("❌ Invalid amount!")
    if amount <= 0 or amount > data[1]:
        return await ctx.send(f"❌ You have {format_number(data[1])} coins!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = money - ?, bank = bank + ? WHERE user_id = ?", (amount, amount, ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Deposited {format_number(amount)}{emoji}!")

@bot.command(name="withdraw", aliases=["with"])
@economy_check()
async def withdraw(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    max_withdraw = await get_setting(ctx.guild.id, "max_withdraw")
    if amount_str.lower() == "all":
        amount = min(data[2], max_withdraw)
        if data[2] > max_withdraw:
            await ctx.send(f"⚠️ Max withdraw is {format_number(max_withdraw)}. Withdrawing {format_number(amount)} (you have {format_number(data[2])} in bank)")
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return await ctx.send("❌ Invalid amount!")
    if amount <= 0:
        return
    if amount > max_withdraw:
        return await ctx.send(f"❌ Max withdraw is {format_number(max_withdraw)} per transaction!")
    if amount > data[2]:
        return await ctx.send(f"❌ You have {format_number(data[2])} coins in bank!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = money + ?, bank = bank - ? WHERE user_id = ?", (amount, amount, ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Withdrew {format_number(amount)}{emoji}!")

@bot.command(name="pay")
@economy_check()
async def pay(ctx, target: discord.User, amount_str: str):
    if target == ctx.author:
        return await ctx.send("❌ Can't pay yourself!")
    
    try:
        if amount_str.lower() == "all":
            sender_data = await get_user(ctx.author.id)
            amount = sender_data[1]
        else:
            amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount! Use 500, 1k, 2.5m, or 'all'")
    
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive!")
    
    sender_data = await get_user(ctx.author.id)
    if sender_data[1] < amount:
        return await ctx.send(f"❌ You have {format_number(sender_data[1])} coins!")
    
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    
    # Send confirmation to sender first
    view = PaymentSenderView(ctx.author, target, amount, emoji)
    embed = discord.Embed(title="💸 Confirm Payment", color=discord.Color.blue())
    embed.add_field(name="To", value=target.mention, inline=True)
    embed.add_field(name="Amount", value=f"{format_number(amount)}{emoji}", inline=True)
    embed.add_field(name="⏱️ Time", value="60 seconds", inline=True)
    embed.set_footer(text="Click confirm to send this payment")
    
    await ctx.send(f"{ctx.author.mention}, you are about to send {format_number(amount)}{emoji} to {target.mention}. Confirm?", embed=embed, view=view)

@bot.command(name="rob")
@economy_check()
async def rob(ctx, target: discord.User):
    if target == ctx.author:
        return
    if await get_setting(ctx.guild.id, "rob_enabled") == 0:
        return await ctx.send("❌ Rob disabled!")
    if await is_protected(target.id):
        return await ctx.send(f"❌ {target.mention} is protected!")
    target_data = await get_user(target.id)
    if target_data[1] < 100:
        return await ctx.send(f"❌ {target.mention} is too poor!")
    data = await get_user(ctx.author.id)
    if data[10]:
        last = datetime.fromisoformat(data[10])
        if datetime.utcnow() - last < timedelta(hours=1):
            remaining = timedelta(hours=1) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Try again in {remaining.seconds//3600}h")
    
    percent = random.uniform(1, 15)
    steal = int(target_data[1] * (percent / 100))
    steal = max(50, min(steal, target_data[1]))
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await update_money(target.id, -steal)
    await update_money(ctx.author.id, steal)
    await ctx.send(f"✅ Robbed {target.mention} for {format_number(steal)}{emoji} ({percent:.1f}% of their wallet)!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_rob = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()

# ==================================================
# LOAN COMMANDS
# ==================================================
@bot.command(name="loan")
@economy_check()
async def loan_cmd(ctx, amount_str: str):
    try:
        amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount! Use 500, 1k, 2.5m")
    if amount <= 0:
        return
    data = await get_user(ctx.author.id)
    if data[22] > 0:
        return await ctx.send(f"❌ You have an active loan of {format_number(data[22])} coins! Repay it first with `.repay all`")
    if data[23]:
        last = datetime.fromisoformat(data[23])
        if datetime.utcnow() - last < timedelta(hours=1):
            remaining = timedelta(hours=1) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Try again in {remaining.seconds//60}m")
    loan_interest = await get_setting(ctx.guild.id, "loan_interest")
    await update_money(ctx.author.id, amount)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET loan_amount = ?, loan_taken_at = ? WHERE user_id = ?", (amount, datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"🏦 Loan approved! +{format_number(amount)}{emoji}\n⚠️ {loan_interest}% interest per hour! Repay with `.repay`")

@bot.command(name="repay")
@economy_check()
async def repay_cmd(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    loan = data[22]
    if loan <= 0:
        return await ctx.send("❌ You have no active loan!")
    if amount_str.lower() == "all":
        amount = loan
    elif amount_str.lower() == "half":
        amount = loan // 2
    else:
        try:
            amount = parse_amount(amount_str)
        except:
            return
    if amount <= 0:
        return
    if data[1] < amount:
        return await ctx.send(f"❌ You have {format_number(data[1])} coins!")
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
        await ctx.send(f"✅ Loan fully repaid! Paid {format_number(amount)}{emoji}. You are debt-free! 🎉")
    else:
        await ctx.send(f"✅ Repaid {format_number(amount)}{emoji}. Remaining: {format_number(new_loan)}{emoji}")

@bot.command(name="loaninfo")
@economy_check()
async def loan_info_cmd(ctx):
    data = await get_user(ctx.author.id)
    loan = data[22]
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if loan <= 0:
        embed = discord.Embed(title="🏦 Loan Status", color=discord.Color.green())
        embed.add_field(name="Active Loan", value="None", inline=False)
        embed.add_field(name="How to get a loan", value="`.loan <amount>`", inline=False)
        embed.add_field(name="Warning", value="10% interest every hour!", inline=False)
        await ctx.send(embed=embed)
    else:
        taken = data[23]
        if taken:
            taken_time = datetime.fromisoformat(taken)
            hours = (datetime.utcnow() - taken_time).total_seconds() / 3600
            total_due = int(loan * (1.10 ** hours))
        else:
            total_due = loan
        embed = discord.Embed(title="🏦 Loan Status", color=discord.Color.red())
        embed.add_field(name="Original Loan", value=f"{format_number(loan)}{emoji}", inline=True)
        embed.add_field(name="Current Due", value=f"{format_number(total_due)}{emoji}", inline=True)
        embed.add_field(name="Interest Rate", value="10% per hour", inline=True)
        await ctx.send(embed=embed)

# ==================================================
# GAMBLING COMMANDS
# ==================================================
@bot.command(name="bj", aliases=["blackjack"])
@economy_check()
async def blackjack(ctx, amount_str: str):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    cards = [2,3,4,5,6,7,8,9,10,10,10,10,11]
    player = [random.choice(cards), random.choice(cards)]
    dealer = [random.choice(cards), random.choice(cards)]
    player_val = sum(player)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if player_val == 21:
        winnings = int(amount * 2.5)
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🎉 BLACKJACK! Won {format_number(winnings)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        view = BlackjackView(ctx, amount, player, dealer, amount)
        view.emoji = emoji
        embed = await view.get_embed()
        await ctx.send(embed=embed, view=view)

@bot.command(name="mines")
@economy_check()
async def mines_command(ctx, amount_str: str, mines: int = 5):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return
    if mines < 1 or mines > 19:
        return await ctx.send("❌ Mines must be 1-19!")
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    multiplier = round(1.02 * (25 / (25 - mines)) ** 1.2, 2)
    multiplier = min(multiplier, 100)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    view = MinesView(ctx, amount, mines, multiplier, emoji)
    embed = discord.Embed(title="💣 Minesweeper", color=discord.Color.gold())
    embed.add_field(name="Board", value="⬛ ⬛ ⬛ ⬛ ⬛\n⬛ ⬛ ⬛ ⬛ ⬛\n⬛ ⬛ ⬛ ⬛ ⬛\n⬛ ⬛ ⬛ ⬛ ⬛", inline=False)
    embed.add_field(name="Mines", value=f"{mines} bombs", inline=True)
    embed.add_field(name="Multiplier", value=f"{multiplier}x", inline=True)
    embed.add_field(name="Cashout", value=f"{format_number(int(amount * multiplier))} {emoji}", inline=True)
    embed.add_field(name="⏱️ Time", value="2 minutes", inline=True)
    embed.set_footer(text="Reveal tiles to increase multiplier. Must reveal at least 1 to cashout!")
    await ctx.send(embed=embed, view=view)
    await update_money(ctx.author.id, -amount)

@bot.command(name="cf", aliases=["coinflip"])
@economy_check()
async def coinflip(ctx, amount_str: str, choice: str = None):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    if choice and choice.lower() not in ["heads", "tails"]:
        return
    result = random.choice(["heads", "tails"])
    win = (choice and choice.lower() == result) if choice else random.choice([True, False])
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
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    emojis = ["🍒", "🍋", "🍊", "🍉", "⭐", "💎"]
    r1, r2, r3 = random.choice(emojis), random.choice(emojis), random.choice(emojis)
    mult = 0
    if r1 == r2 == r3:
        mult = 3 if r1 == "💎" else 2
    elif r1 == r2 or r2 == r3 or r1 == r3:
        mult = 0.5
    winnings = int(amount * mult)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if winnings > amount:
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🎰 `[{r1}] [{r2}] [{r3}]`\n🎉 JACKPOT! Won {format_number(winnings)}{emoji}!")
    elif mult > 0:
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🎰 `[{r1}] [{r2}] [{r3}]`\n✅ Won {format_number(winnings)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        await ctx.send(f"🎰 `[{r1}] [{r2}] [{r3}]`\n❌ Lost {format_number(amount)}{emoji}.")

@bot.command(name="crash")
@economy_check()
async def crash(ctx, amount_str: str):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    mult = round(random.uniform(1.01, 100), 2)
    win = random.random() < 0.5
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if win:
        winnings = int(amount * mult)
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"📈 Crash at {mult}x! Won {format_number(winnings)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        await ctx.send(f"💥 Crashed at {mult}x! Lost {format_number(amount)}{emoji}!")

@bot.command(name="tower")
@economy_check()
async def tower(ctx, amount_str: str, floors: int = 5):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return
    if floors < 3 or floors > 12:
        return
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    mult = round(1.5 ** floors, 2)
    win = random.random() < (0.9 - (floors * 0.03))
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if win:
        winnings = int(amount * mult)
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🏗️ Tower ({floors} floors) - Reached top! Won {format_number(winnings)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        await ctx.send(f"🏗️ CRASH at floor {random.randint(2, floors)}! Lost {format_number(amount)}{emoji}!")

# ==================================================
# SHOP & BUSINESS COMMANDS
# ==================================================
@bot.command(name="createshop")
@economy_check()
async def create_shop(ctx, *, name: str):
    data = await get_user(ctx.author.id)
    if data[14]:
        return await ctx.send("❌ You already have a shop!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_name = ?, shop_open = 1 WHERE user_id = ?", (name, ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Shop '{name}' created! Use `.addshopitem <price> <item>`")

@bot.command(name="addshopitem")
@economy_check()
async def add_shop_item(ctx, price: int, *, item: str):
    if price <= 0:
        return
    data = await get_user(ctx.author.id)
    if not data[14]:
        return
    if not data[16]:
        return await ctx.send("❌ Shop closed! `.closeshop` to open")
    items = json.loads(data[15]) if data[15] else {}
    if len(items) >= 20:
        return await ctx.send("❌ Shop full! Max 20 items")
    items[item] = price
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Added '{item}' for {format_number(price)}{emoji}!")

@bot.command(name="myshop")
@economy_check()
async def my_shop(ctx):
    data = await get_user(ctx.author.id)
    if not data[14]:
        return
    items = json.loads(data[15]) if data[15] else {}
    status = "Open" if data[16] else "Closed"
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    msg = f"🏪 **{data[14]}** ({status})\n\n"
    if items:
        for item, price in items.items():
            msg += f"• {item}: {format_number(price)}{emoji}\n"
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
    await ctx.send(f"✅ Shop is now {'open' if new else 'closed'}!")

@bot.command(name="buyfromshop")
@economy_check()
async def buy_from_shop(ctx, seller: discord.User, *, item: str):
    seller_data = await get_user(seller.id)
    if not seller_data[14] or not seller_data[16]:
        return await ctx.send(f"❌ {seller.display_name}'s shop is closed!")
    items = json.loads(seller_data[15]) if seller_data[15] else {}
    if item not in items:
        return
    price = items[item]
    buyer = await get_user(ctx.author.id)
    if buyer[1] < price:
        return await ctx.send(f"❌ Need {format_number(price)} coins!")
    await update_money(ctx.author.id, -price)
    await update_money(seller.id, price)
    del items[item]
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), seller.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Bought '{item}' for {format_number(price)}{emoji}!")

@bot.command(name="globalmarket")
@economy_check()
async def global_market(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, shop_name FROM users WHERE shop_open = 1 AND shop_name IS NOT NULL LIMIT 20") as cursor:
            shops = await cursor.fetchall()
    if not shops:
        return await ctx.send("No open shops found!")
    msg = "🌍 **Global Market**\n\n"
    for uid, name in shops:
        try:
            user = await bot.fetch_user(uid)
            msg += f"• {name} - {user.display_name}\n"
        except:
            msg += f"• {name}\n"
    await ctx.send(msg)

@bot.command(name="buybusiness")
@economy_check()
async def buy_business(ctx, biz: str):
    types = ["restaurant", "casino", "cafe"]
    if biz.lower() not in types:
        return
    data = await get_user(ctx.author.id)
    cost = 1000
    if data[1] < cost:
        return
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            if await cursor.fetchone():
                return await ctx.send("❌ You already own a business!")
        await update_money(ctx.author.id, -cost)
        await db.execute("INSERT INTO businesses (user_id, business_type, level, last_collected) VALUES (?, ?, ?, ?)", 
                        (ctx.author.id, biz.lower(), 1, datetime.utcnow().isoformat()))
        await db.commit()
    await ctx.send(f"✅ Bought a {biz} business!")

@bot.command(name="business")
@economy_check()
async def business_info(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT business_type, level FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return
    biz, level = row
    await ctx.send(f"🏪 **{biz} business**\nLevel: {level}\nIncome: {format_number(50 * level)} coins/hour")

@bot.command(name="upgradebusiness")
@economy_check()
async def upgrade_business(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return
    level = row[0]
    cost = 500 * level
    data = await get_user(ctx.author.id)
    if data[1] < cost:
        return await ctx.send(f"❌ Upgrade costs {format_number(cost)} coins!")
    await update_money(ctx.author.id, -cost)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE businesses SET level = level + 1 WHERE user_id = ?", (ctx.author.id,))
        await db.commit()
    await ctx.send(f"✅ Business upgraded to level {level + 1}!")

@bot.command(name="collectprofits")
@economy_check()
async def collect_profits(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level, last_collected FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return
    level, last = row
    now = datetime.utcnow()
    last_time = datetime.fromisoformat(last)
    hours = (now - last_time).total_seconds() / 3600
    if hours < 1:
        remaining = 3600 - (now - last_time).total_seconds()
        return await ctx.send(f"⏰ Next collection in {int(remaining//60)} minutes!")
    profit = int(50 * level * min(hours, 24))
    await update_money(ctx.author.id, profit)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE businesses SET last_collected = ? WHERE user_id = ?", (now.isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Collected {format_number(profit)}{emoji}!")

@bot.command(name="sellbusiness")
@economy_check()
async def sell_business(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return
    value = 500 * row[0]
    await update_money(ctx.author.id, value)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM businesses WHERE user_id = ?", (ctx.author.id,))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Sold business for {format_number(value)}{emoji}!")

# ==================================================
# RELATIONSHIP COMMANDS WITH FAMILY CHECK
# ==================================================
@bot.command(name="date")
@economy_check()
async def date_cmd(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("❌ Can't date yourself!")
    
    # Check if target is family member
    if await is_family_member(ctx.author.id, user.id):
        return await ctx.send("❌ You cannot date a family member! (spouse, parent, or child)")
    
    data = await get_user(ctx.author.id)
    if data[17]:
        return await ctx.send("❌ You're already married! Divorce first with `.divorce`")
    if data[1] < 500:
        return await ctx.send("❌ Need 500 coins for a date!")
    
    await update_money(ctx.author.id, -500)
    gain = random.randint(50, 150)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET affection = affection + ? WHERE user_id = ?", (gain, user.id))
        await db.commit()
    await ctx.send(f"💕 Date with {user.mention}! +{gain} affection!")

@bot.command(name="marry")
@economy_check()
async def marry_cmd(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("❌ Can't marry yourself!")
    
    # Check if target is family member
    if await is_family_member(ctx.author.id, user.id):
        return await ctx.send("❌ You cannot marry a family member! (spouse, parent, or child)")
    
    data = await get_user(ctx.author.id)
    if data[17]:
        return await ctx.send("❌ Already married!")
    target = await get_user(user.id)
    if target[17]:
        return await ctx.send(f"❌ {user.mention} is already married!")
    if data[1] < 5000:
        return await ctx.send("❌ Need 5000 coins!")
    if target[19] < 1000:
        return await ctx.send(f"❌ Need 1000 affection with {user.mention}!")
    
    await update_money(ctx.author.id, -5000)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?, ?, 'marriage', ?)", 
                        (ctx.author.id, user.id, datetime.utcnow().isoformat()))
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cursor:
            rid = (await cursor.fetchone())[0]
    
    view = RequestView(ctx.author, user, "marriage", rid)
    embed = discord.Embed(title="💍 Marriage Proposal", color=discord.Color.purple())
    embed.add_field(name="From", value=ctx.author.mention, inline=True)
    embed.add_field(name="To", value=user.mention, inline=True)
    embed.add_field(name="⏱️ Time", value="2 minutes", inline=True)
    await ctx.send(f"💍 {ctx.author.mention} proposed to {user.mention}!", embed=embed, view=view)

@bot.command(name="divorce")
@economy_check()
async def divorce_cmd(ctx):
    data = await get_user(ctx.author.id)
    spouse = data[17]
    if not spouse:
        return
    if data[1] < 2500:
        return await ctx.send("❌ Need 2500 coins for divorce!")
    await update_money(ctx.author.id, -2500)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (ctx.author.id,))
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (spouse,))
        await db.commit()
    s = await bot.fetch_user(spouse)
    await ctx.send(f"💔 Divorced {s.mention}!")

@bot.command(name="affection")
@economy_check()
async def affection_cmd(ctx, user: discord.User = None):
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
    bar = "█" * min(20, aff // 250) + "░" * (20 - min(20, aff // 250))
    embed = discord.Embed(title=f"💕 {target.display_name}'s Affection", color=discord.Color.pink())
    embed.add_field(name="Level", value=level, inline=False)
    embed.add_field(name="Points", value=format_number(aff), inline=False)
    embed.add_field(name="Progress", value=f"`{bar}`", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="gift")
@economy_check()
async def gift_cmd(ctx, user: discord.User, amount_str: str):
    try:
        amount = parse_amount(amount_str)
    except:
        return
    if amount <= 0 or user == ctx.author:
        return
    data = await get_user(ctx.author.id)
    if data[1] < amount:
        return
    await update_money(ctx.author.id, -amount)
    await update_money(user.id, amount)
    gain = amount // 100
    if gain > 0:
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET affection = affection + ? WHERE user_id = ?", (gain, user.id))
            await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"🎁 Gifted {format_number(amount)}{emoji} to {user.mention}!" + (f" (+{format_number(gain)} affection)" if gain else ""))

@bot.command(name="adopt")
@economy_check()
async def adopt_cmd(ctx, user: discord.User):
    if user == ctx.author:
        return
    data = await get_user(ctx.author.id)
    if data[1] < 2000:
        return await ctx.send("❌ Need 2000 coins!")
    target = await get_user(user.id)
    if target[18]:
        return await ctx.send(f"❌ {user.mention} already has a parent!")
    
    await update_money(ctx.author.id, -2000)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?, ?, 'adopt', ?)", 
                        (ctx.author.id, user.id, datetime.utcnow().isoformat()))
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cursor:
            rid = (await cursor.fetchone())[0]
    
    view = RequestView(ctx.author, user, "adopt", rid)
    embed = discord.Embed(title="👶 Adoption Request", color=discord.Color.teal())
    embed.add_field(name="From", value=ctx.author.mention, inline=True)
    embed.add_field(name="To", value=user.mention, inline=True)
    embed.add_field(name="⏱️ Time", value="2 minutes", inline=True)
    await ctx.send(f"👶 {ctx.author.mention} wants to adopt {user.mention}!", embed=embed, view=view)

@bot.command(name="children")
@economy_check()
async def children_cmd(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT child_id FROM children WHERE parent_id = ?", (ctx.author.id,)) as cursor:
            kids = await cursor.fetchall()
    if not kids:
        return await ctx.send("No children!")
    msg = f"👶 {ctx.author.display_name}'s children:\n"
    for kid in kids:
        try:
            k = await bot.fetch_user(kid[0])
            msg += f"• {k.mention}\n"
        except:
            msg += f"• User {kid[0]}\n"
    await ctx.send(msg)

@bot.command(name="family")
@economy_check()
async def family_cmd(ctx):
    data = await get_user(ctx.author.id)
    spouse = data[17]
    parent = data[18]
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT child_id FROM children WHERE parent_id = ?", (ctx.author.id,)) as cursor:
            kids = await cursor.fetchall()
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
        for kid in kids:
            try:
                k = await bot.fetch_user(kid[0])
                msg += f"• {k.mention}\n"
            except:
                msg += f"• User {kid[0]}\n"
    else:
        msg += "\n👶 Children: None"
    await ctx.send(msg)

@bot.command(name="pending")
@economy_check()
async def pending_cmd(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT id, from_id, request_type FROM requests WHERE to_id = ?", (ctx.author.id,)) as cursor:
            reqs = await cursor.fetchall()
    if not reqs:
        return
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
async def global_leaderboard(ctx, category: str = "money"):
    if category not in ["money", "xp"]:
        return
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
        return
    msg = f"**{title}**\n\n"
    for i, (uid, val) in enumerate(rows, 1):
        try:
            u = await bot.fetch_user(uid)
            name = u.display_name
        except:
            name = f"User {uid}"
        msg += f"{i}. {name}: {format_number(val)}{' coins' if category=='money' else ' XP'}\n"
    await ctx.send(msg)

@bot.command(name="serverleaderboard", aliases=["slb"])
@economy_check()
async def server_leaderboard(ctx, category: str = "money"):
    if category not in ["money", "xp"]:
        return
    members = [m for m in ctx.guild.members if not m.bot]
    data = []
    async with aiosqlite.connect("hakari.db") as db:
        for m in members:
            async with db.execute("SELECT money, bank, total_xp FROM users WHERE user_id = ?", (m.id,)) as cursor:
                row = await cursor.fetchone()
            if row:
                if category == "money":
                    data.append((m, row[0] + row[1]))
                else:
                    data.append((m, row[4]))
    data.sort(key=lambda x: x[1], reverse=True)
    top = data[:10]
    if not top:
        return
    title = f"📊 Server {'Richest' if category=='money' else 'Top XP'} - {ctx.guild.name}"
    msg = f"**{title}**\n\n"
    for i, (m, val) in enumerate(top, 1):
        msg += f"{i}. {m.display_name}: {format_number(val)}{' coins' if category=='money' else ' XP'}\n"
    await ctx.send(msg)

@bot.command(name="topcouples")
@economy_check()
async def top_couples(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, spouse_id, affection FROM users WHERE spouse_id IS NOT NULL ORDER BY affection DESC LIMIT 10") as cursor:
            couples = await cursor.fetchall()
    if not couples:
        return
    msg = "💕 **Top Couples**\n\n"
    for i, (uid, sid, aff) in enumerate(couples, 1):
        try:
            u = await bot.fetch_user(uid)
            s = await bot.fetch_user(sid)
            msg += f"{i}. {u.display_name} & {s.display_name}: {format_number(aff)} ❤️\n"
        except:
            continue
    await ctx.send(msg)

@bot.command(name="level", aliases=["rank"])
@economy_check()
async def level_cmd(ctx):
    data
