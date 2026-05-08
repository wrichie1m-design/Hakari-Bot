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
# HELPER FUNCTIONS FOR SHORT NUMBERS
# ==================================================
def parse_amount(amount_str: str) -> int:
    """Convert short numbers like 1k, 1.5k, 2.5m to actual integers"""
    if amount_str.lower() == "all":
        return "all"
    
    amount_str = amount_str.lower().strip()
    
    # Check for k (thousands)
    if amount_str.endswith('k'):
        num = float(amount_str[:-1])
        return int(num * 1000)
    # Check for m (millions)
    elif amount_str.endswith('m'):
        num = float(amount_str[:-1])
        return int(num * 1000000)
    # Check for b (billions)
    elif amount_str.endswith('b'):
        num = float(amount_str[:-1])
        return int(num * 1000000000)
    else:
        return int(float(amount_str))

def format_number(num: int) -> str:
    """Format large numbers as 1k, 2.5m, etc."""
    if num >= 1_000_000_000:
        return f"{num/1_000_000_000:.1f}b".replace('.0b', 'b')
    elif num >= 1_000_000:
        return f"{num/1_000_000:.1f}m".replace('.0m', 'm')
    elif num >= 1_000:
        return f"{num/1_000:.1f}k".replace('.0k', 'k')
    else:
        return str(num)

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
                gang TEXT
            )
        ''')
        
        await db.execute('CREATE TABLE IF NOT EXISTS children (parent_id INTEGER, child_id INTEGER, PRIMARY KEY (parent_id, child_id))')
        await db.execute('CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY AUTOINCREMENT, from_id INTEGER, to_id INTEGER, request_type TEXT, timestamp TEXT)')
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

async def set_money(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def set_bank(user_id: int, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET bank = ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def log_action(user_id: int, action: str, details: str = ""):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO logs (timestamp, user_id, action, details) VALUES (?, ?, ?, ?)", (datetime.utcnow().isoformat(), user_id, action, details))
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
        "currency_emoji": "💰"
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
    """Parse bet amount with support for 'all' and short numbers (1k, 2.5m)"""
    data = await get_user(ctx.author.id)
    
    if amount_str.lower() == "all":
        amount = data[1]
    else:
        try:
            amount = parse_amount(amount_str)
        except (ValueError, TypeError):
            return None, "❌ Please enter a valid number (e.g., 500, 1k, 2.5m, all)"
    
    if amount <= 0:
        return None, "❌ Amount must be positive!"
    if check_balance and data[1] < amount:
        return None, f"❌ You don't have {format_number(amount)} {await get_setting(ctx.guild.id, 'currency_emoji')}! You have {format_number(data[1])}."
    return amount, None

def economy_check():
    async def predicate(ctx):
        if await get_setting(ctx.guild.id, "economy_enabled") == 0:
            await ctx.send("❌ Economy is disabled!")
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
        await ctx.send("❌ You don't have permission!")
        return False
    return commands.check(predicate)

def main_owner_only():
    async def predicate(ctx):
        if await is_main_owner(ctx.author.id):
            return True
        await ctx.send("❌ Only the main owner can use this!")
        return False
    return commands.check(predicate)

# ==================================================
# BANK INTEREST TASK
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
            earning_limit = 50000
            amount_to_interest = min(bank, earning_limit)
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
# PAYMENT VIEW
# ==================================================
class PaymentView(discord.ui.View):
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
            return
        if self.completed:
            return
        await interaction.response.edit_message(content=f"❌ {self.recipient.mention} declined the payment.", view=None)
        self.completed = True
        self.stop()

    async def on_timeout(self):
        if not self.completed:
            await self.recipient.send(f"⏰ Payment request from {self.sender.mention} for {format_number(self.amount)}{self.emoji} expired.")

# ==================================================
# REQUEST VIEW (Marry/Adopt)
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
            return
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
            return
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
            await self.to_user.send(f"⏰ {self.request_type.capitalize()} request from {self.from_user.mention} expired.")

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
        embed.add_field(name="⏱️ Time Left", value=f"{mins}m {secs}s", inline=True)
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
            embed.add_field(name="Result", value=f"🤝 Push! Your {format_number(self.bet)}{self.emoji} returned.", inline=False)
        elif result == "blackjack":
            winnings = int(self.bet * 2.5)
            await update_money(self.ctx.author.id, winnings)
            embed.add_field(name="Result", value=f"🎉 BLACKJACK! You won {format_number(winnings)}{self.emoji}!", inline=False)
        else:
            embed.add_field(name="Result", value=f"⏰ Timeout! You lost {format_number(self.bet)}{self.emoji}.", inline=False)
        
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
        embed.add_field(name="⏱️ Time Left", value=f"{mins}m {secs}s", inline=True)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, row=0)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return
        cards = [2,3,4,5,6,7,8,9,10,10,10,10,11]
        self.player_hand.append(random.choice(cards))
        player_value = await self.get_hand_value(self.player_hand)
        if player_value > 21:
            await self.end_game("lose")
            await interaction.message.delete()
            return
        await self.update_message(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success, row=0)
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return
        self.stand_clicked = True
        player_value = await self.get_hand_value(self.player_hand)
        while await self.get_hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11]))
        dealer_value = await self.get_hand_value(self.dealer_hand)
        if dealer_value > 21 or player_value > dealer_value:
            winnings = int(self.bet * 2)
            await self.end_game("win", winnings)
        elif player_value < dealer_value:
            await self.end_game("lose")
        else:
            await self.end_game("push", self.bet)
        await interaction.message.delete()
        self.stop()

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.danger, row=0)
    async def double_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return
        self.bet *= 2
        cards = [2,3,4,5,6,7,8,9,10,10,10,10,11]
        self.player_hand.append(random.choice(cards))
        player_value = await self.get_hand_value(self.player_hand)
        if player_value > 21:
            await self.end_game("lose")
            await interaction.message.delete()
            return
        await self.stand_button.callback(interaction, button)

    async def on_timeout(self):
        if not self.game_over:
            await self.end_game("timeout")
            await self.ctx.send(f"⏰ {self.ctx.author.mention} took too long! Game over.")

# ==================================================
# MINES VIEW
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
            btn = discord.ui.Button(label="⬜", style=discord.ButtonStyle.secondary, row=i//5, custom_id=f"mine_{i}")
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
                await interaction.response.edit_message(content=f"💥 BOOM! You lost {format_number(self.bet)}{self.emoji}.", view=None)
                await update_money(self.ctx.author.id, -self.bet)
                self.stop()
            else:
                self.safe_reveals += 1
                self.multiplier = round(1.02 * (25 / (25 - self.mines_count)) ** (1 + self.safe_reveals*0.1), 2)
                self.multiplier = min(self.multiplier, 100)
                remaining = 120 - (datetime.utcnow() - self.start_time).total_seconds()
                mins = int(max(0, remaining) // 60)
                secs = int(max(0, remaining) % 60)
                board_display = ""
                for i in range(20):
                    board_display += "💎 " if self.revealed[i] else "⬜ "
                    if (i+1) % 5 == 0:
                        board_display += "\n"
                cashout_value = int(self.bet * self.multiplier)
                embed = discord.Embed(title="💣 Minesweeper", color=discord.Color.gold())
                embed.add_field(name="Board", value=board_display, inline=False)
                embed.add_field(name="Mines", value=f"{self.mines_count} bombs", inline=True)
                embed.add_field(name="Multiplier", value=f"{self.multiplier}x", inline=True)
                embed.add_field(name="Cashout", value=f"{format_number(cashout_value)} {self.emoji}", inline=True)
                embed.add_field(name="⏱️ Time Left", value=f"{mins}m {secs}s", inline=True)
                await interaction.response.edit_message(embed=embed, view=self)
        return callback

    async def cashout_callback(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author or self.game_over:
            return
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
        discord.Embed(title=f"💰 Economy Commands (1/6)", color=discord.Color.blue()).add_field(
            name="Commands", 
            value=f"`.balance` / `.bal` - Check balance\n"
                  f"`.daily` - Claim {emoji}1500 (need 10 messages)\n"
                  f"`.work` - Work for {emoji}150-300 (5 min)\n"
                  f"`.sleep` - Sleep for {emoji}2000-2500 (8h)\n"
                  f"`.crime` - Commit crime {emoji}200-800 (15 min)\n"
                  f"`.deposit <amount/all>` - Deposit\n"
                  f"`.withdraw <amount/all>` - Withdraw (max 50k)\n"
                  f"`.pay <@user> <amount/all>` - Send (confirmation)\n"
                  f"`.rob <@user>` - Rob (1h cooldown, 1%-50% steal)\n"
                  f"`.interest` - Check bank interest rate\n"
                  f"**Short numbers**: 1k = 1000, 2.5m = 2,500,000", 
            inline=False
        ),
        discord.Embed(title=f"🎰 Gambling Games (2/6)", color=discord.Color.gold()).add_field(
            name="Games (use 'all' or short numbers like 1k)", 
            value=f"`.cf <amount> [heads/tails]` - Coinflip\n"
                  f"`.slots <amount>` - Slot machine\n"
                  f"`.bj <amount>` - Blackjack\n"
                  f"`.crash <amount>` - Crash game\n"
                  f"`.mines <amount> <mines>` - Minesweeper (20 tiles, 1-19 mines)\n"
                  f"`.tower <amount> <floors>` - Tower (3-12 floors)", 
            inline=False
        ),
        discord.Embed(title=f"🛒 Shop & Business (3/6)", color=discord.Color.green()).add_field(
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
        discord.Embed(title=f"💕 Relationships (4/6)", color=discord.Color.pink()).add_field(
            name="Commands", 
            value="`.date <@user>` - Go on date\n"
                  "`.marry <@user>` - Propose (sends request)\n"
                  "`.divorce` - Divorce\n"
                  "`.affection` - Check love\n"
                  "`.gift <@user> <amount>` - Gift coins\n"
                  "`.adopt <@user>` - Adopt (sends request)\n"
                  "`.children` - List\n"
                  "`.family` - Family tree\n"
                  "`.pending` - View requests", 
            inline=False
        ),
        discord.Embed(title=f"📊 Leaderboards (5/6)", color=discord.Color.purple()).add_field(
            name="Commands", 
            value="`.glb money` / `.glb xp` - Global\n"
                  "`.slb money` / `.slb xp` - Server\n"
                  "`.topcouples` - Top couples\n"
                  "`.level` / `.rank` - Your rank", 
            inline=False
        ),
    ]
    
    if owner:
        pages.append(discord.Embed(title=f"👑 Owner Commands (6/6)", color=discord.Color.red()).add_field(
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
                  "`.protectedlist` - List protected\n"
                  "`.blacklist <@user>` - Blacklist\n"
                  "`.whitelist <@user>` - Whitelist\n"
                  "`.economywipe` - Wipe economy\n"
                  "`.toggleeconomy` / `.togglerob` / `.togglegambling`\n"
                  "`.setdailyamount` / `.setsleepamount` / `.setworkamount` / `.setcrimeamount`\n"
                  "`.setinterestrate <percent>` - Set bank interest\n"
                  "`.setmaxwithdraw <amount>` - Set max withdraw\n"
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
    interest_rate = await get_setting(ctx.guild.id, "interest_rate")
    embed = discord.Embed(title=f"{target.display_name}'s Balance", color=discord.Color.teal())
    embed.add_field(name="Wallet", value=f"{format_number(data[1])}{emoji}", inline=True)
    embed.add_field(name="Bank", value=f"{format_number(data[2])}{emoji}", inline=True)
    embed.add_field(name="Total", value=f"{format_number(data[1] + data[2])}{emoji}", inline=True)
    embed.set_footer(text=f"Level {data[4]} | Bank earns {interest_rate}% daily (max 50k)")
    await ctx.send(embed=embed)

@bot.command(name="interest")
@economy_check()
async def check_interest(ctx):
    interest_rate = await get_setting(ctx.guild.id, "interest_rate")
    data = await get_user(ctx.author.id)
    bank = data[2]
    earning_limit = 50000
    amount_earning = min(bank, earning_limit)
    daily_interest = int(amount_earning * (interest_rate / 100))
    embed = discord.Embed(title="🏦 Bank Interest", color=discord.Color.gold())
    embed.add_field(name="Interest Rate", value=f"{interest_rate}% daily", inline=True)
    embed.add_field(name="Max Earning Balance", value="50,000 coins", inline=True)
    embed.add_field(name="Your Bank", value=f"{format_number(bank)} coins", inline=True)
    embed.add_field(name="Amount Earning Interest", value=f"{format_number(amount_earning)} coins", inline=True)
    embed.add_field(name="Daily Interest", value=f"{format_number(daily_interest)} coins", inline=True)
    await ctx.send(embed=embed)

@bot.command(name="daily")
@economy_check()
async def daily(ctx):
    data = await get_user(ctx.author.id)
    if data[8]:
        last = datetime.fromisoformat(data[8])
        if datetime.utcnow() - last < timedelta(hours=24):
            remaining = timedelta(hours=24) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Already claimed! Try again in {remaining.seconds//3600}h {(remaining.seconds%3600)//60}m")
    needed = await get_setting(ctx.guild.id, "daily_messages_needed")
    if data[13] < needed:
        return await ctx.send(f"❌ You need {needed - data[13]} more messages today!")
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
            return await ctx.send(f"⏰ Try again in {remaining.seconds//60}m {remaining.seconds%60}s")
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
    crimes = [{"name": "Pickpocketing", "success_rate": 0.7}, {"name": "Store robbery", "success_rate": 0.55}, {"name": "Bank heist", "success_rate": 0.4}, {"name": "Street hustle", "success_rate": 0.8}, {"name": "Mugging", "success_rate": 0.6}]
    crime_data = random.choice(crimes)
    success = random.random() < crime_data["success_rate"]
    min_amt = await get_setting(ctx.guild.id, "crime_amount_min")
    max_amt = await get_setting(ctx.guild.id, "crime_amount_max")
    reward = random.randint(min_amt, max_amt)
    penalty = reward // 2
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_crime = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if success:
        await update_money(ctx.author.id, reward)
        await ctx.send(f"🦹 {crime_data['name']} successful! +{format_number(reward)}{emoji}!")
    else:
        if data[1] >= penalty:
            await update_money(ctx.author.id, -penalty)
            await ctx.send(f"🚔 Caught! Lost {format_number(penalty)}{emoji}!")
        else:
            await ctx.send(f"🚔 Caught! You went to jail!")

@bot.command(name="deposit")
@economy_check()
async def deposit(ctx, amount_str: str):
    data = await get_user(ctx.author.id)
    if amount_str.lower() == "all":
        amount = data[1]
    else:
        try:
            amount = parse_amount(amount_str)
        except ValueError:
            return await ctx.send("❌ Invalid amount! Use numbers like 500, 1k, 2.5m, or 'all'")
    if amount <= 0 or amount > data[1]:
        return await ctx.send(f"❌ You have {format_number(data[1])} coins in wallet.")
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
            await ctx.send(f"⚠️ Max withdraw is {format_number(max_withdraw)}. Withdrawing {format_number(amount)} (you have {format_number(data[2])} in bank).")
    else:
        try:
            amount = parse_amount(amount_str)
        except ValueError:
            return await ctx.send("❌ Invalid amount! Use numbers like 500, 1k, 2.5m, or 'all'")
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive!")
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
    try:
        amount = parse_amount(amount_str) if amount_str.lower() != "all" else "all"
        if amount == "all":
            data = await get_user(ctx.author.id)
            amount = data[1]
        if amount <= 0:
            return await ctx.send("❌ Amount must be positive!")
    except:
        return await ctx.send("❌ Invalid amount! Use numbers like 500, 1k, 2.5m, or 'all'")
    if target == ctx.author:
        return await ctx.send("❌ Can't pay yourself!")
    data = await get_user(ctx.author.id)
    if data[1] < amount:
        return await ctx.send(f"❌ You have {format_number(data[1])} coins!")
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    view = PaymentView(ctx.author, target, amount, emoji)
    await ctx.send(f"💸 Payment request sent to {target.mention} for {format_number(amount)}{emoji}! They have 60 seconds to respond.")
    await target.send(f"💸 {ctx.author.mention} wants to send you {format_number(amount)}{emoji}. Do you accept?", view=view)

@bot.command(name="rob")
@economy_check()
async def rob(ctx, target: discord.User):
    if target == ctx.author:
        return await ctx.send("❌ Can't rob yourself!")
    if await get_setting(ctx.guild.id, "rob_enabled") == 0:
        return await ctx.send("❌ Rob disabled!")
    if await is_protected(target.id):
        return await ctx.send(f"❌ {target.mention} is protected!")
    target_data = await get_user(target.id)
    if target_data[1] < 100:
        return await ctx.send(f"❌ {target.mention} is too poor to rob!")
    data = await get_user(ctx.author.id)
    if data[10]:
        last = datetime.fromisoformat(data[10])
        if datetime.utcnow() - last < timedelta(hours=1):
            remaining = timedelta(hours=1) - (datetime.utcnow() - last)
            return await ctx.send(f"⏰ Try again in {remaining.seconds//3600}h {(remaining.seconds%3600)//60}m")
    
    # Steal 1% to 50% of target's wallet with weighted probability (higher % = rarer)
    # Random distribution: 1-10% common (60% chance), 11-30% uncommon (30% chance), 31-50% rare (10% chance)
    rand = random.random()
    if rand < 0.6:
        percent = random.uniform(1, 10)
    elif rand < 0.9:
        percent = random.uniform(11, 30)
    else:
        percent = random.uniform(31, 50)
    
    steal = int(target_data[1] * (percent / 100))
    steal = max(50, min(steal, target_data[1]))
    
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await update_money(target.id, -steal)
    await update_money(ctx.author.id, steal)
    await ctx.send(f"✅ You robbed {target.mention} for **{format_number(steal)}{emoji}** ({percent:.1f}% of their wallet)!")
    await log_action(ctx.author.id, "Rob Success", f"Target: {target.id}, Amount: {steal}, Percent: {percent:.1f}%")
    
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET last_rob = ? WHERE user_id = ?", (datetime.utcnow().isoformat(), ctx.author.id))
        await db.commit()

# ==================================================
# GAMBLING COMMANDS
# ==================================================
@bot.command(name="bj", aliases=["blackjack"])
@economy_check()
async def blackjack(ctx, amount_str: str):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return await ctx.send("❌ Gambling disabled!")
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    cards = [2,3,4,5,6,7,8,9,10,10,10,10,11]
    player_hand = [random.choice(cards), random.choice(cards)]
    dealer_hand = [random.choice(cards), random.choice(cards)]
    player_value = sum(player_hand)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if player_value == 21:
        winnings = int(amount * 2.5)
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🎉 BLACKJACK! You won {format_number(winnings)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        view = BlackjackView(ctx, amount, player_hand, dealer_hand, amount)
        view.emoji = emoji
        embed = await view.get_embed()
        await ctx.send(embed=embed, view=view)

@bot.command(name="mines")
@economy_check()
async def mines_command(ctx, amount_str: str, mines: int = 5):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return await ctx.send("❌ Gambling disabled!")
    if mines < 1 or mines > 19:
        return await ctx.send("❌ Mines must be 1-19!")
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    multiplier = round(1.02 * (25 / (25 - mines)) ** 1.2, 2)
    multiplier = min(multiplier, 100)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    view = MinesView(ctx, amount, mines, multiplier, emoji)
    board_display = "⬜ ⬜ ⬜ ⬜ ⬜\n⬜ ⬜ ⬜ ⬜ ⬜\n⬜ ⬜ ⬜ ⬜ ⬜\n⬜ ⬜ ⬜ ⬜ ⬜"
    embed = discord.Embed(title="💣 Minesweeper", color=discord.Color.gold())
    embed.add_field(name="Board", value=board_display, inline=False)
    embed.add_field(name="Mines", value=f"{mines} bombs", inline=True)
    embed.add_field(name="Multiplier", value=f"{multiplier}x", inline=True)
    embed.add_field(name="Cashout", value=f"{format_number(int(amount * multiplier))} {emoji}", inline=True)
    embed.add_field(name="⏱️ Time Left", value="2 minutes", inline=True)
    await ctx.send(embed=embed, view=view)
    await update_money(ctx.author.id, -amount)

@bot.command(name="cf", aliases=["coinflip"])
@economy_check()
async def coinflip(ctx, amount_str: str, choice: str = None):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return await ctx.send("❌ Gambling disabled!")
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    if choice and choice.lower() not in ["heads", "tails"]:
        return await ctx.send("❌ Choose heads or tails!")
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
        return await ctx.send("❌ Gambling disabled!")
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    emojis = ["🍒", "🍋", "🍊", "🍉", "⭐", "💎"]
    reel1, reel2, reel3 = random.choice(emojis), random.choice(emojis), random.choice(emojis)
    multiplier = 0
    if reel1 == reel2 == reel3:
        multiplier = 3 if reel1 == "💎" else (2 if reel1 in ["⭐", "🍒"] else 1.5)
    elif reel1 == reel2 or reel2 == reel3 or reel1 == reel3:
        multiplier = 0.5
    winnings = int(amount * multiplier)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if winnings > amount:
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🎰 `[{reel1}] [{reel2}] [{reel3}]`\n🎉 JACKPOT! Won {format_number(winnings)}{emoji}!")
    elif multiplier > 0:
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🎰 `[{reel1}] [{reel2}] [{reel3}]`\n✅ Won {format_number(winnings)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        await ctx.send(f"🎰 `[{reel1}] [{reel2}] [{reel3}]`\n❌ Lost {format_number(amount)}{emoji}.")

@bot.command(name="crash")
@economy_check()
async def crash(ctx, amount_str: str):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return await ctx.send("❌ Gambling disabled!")
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    multiplier = round(random.uniform(1.01, 100), 2)
    win = random.random() < 0.5
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if win:
        winnings = int(amount * multiplier)
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"📈 Crash at {multiplier}x! Won {format_number(winnings)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        await ctx.send(f"💥 Crashed at {multiplier}x! Lost {format_number(amount)}{emoji}!")

@bot.command(name="tower")
@economy_check()
async def tower(ctx, amount_str: str, floors: int = 5):
    if await get_setting(ctx.guild.id, "gambling_enabled") == 0:
        return await ctx.send("❌ Gambling disabled!")
    if floors < 3 or floors > 12:
        return await ctx.send("❌ Floors must be 3-12!")
    amount, error = await get_bet_amount(ctx, amount_str)
    if error:
        return await ctx.send(error)
    multiplier = round(1.5 ** floors, 2)
    win = random.random() < (0.9 - (floors * 0.03))
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    if win:
        winnings = int(amount * multiplier)
        await update_money(ctx.author.id, winnings)
        await ctx.send(f"🏗️ Tower ({floors} floors) - Reached top! Won {format_number(winnings)}{emoji}!")
    else:
        await update_money(ctx.author.id, -amount)
        await ctx.send(f"🏗️ CRASH! Lost {format_number(amount)}{emoji}!")

# ==================================================
# SHOP & BUSINESS COMMANDS (SIMPLIFIED BUT WORKING)
# ==================================================
@bot.command(name="createshop")
@economy_check()
async def create_shop(ctx, *, name: str):
    data = await get_user(ctx.author.id)
    if data[14]:
        return await ctx.send("❌ You already have a shop!")
    if len(name) > 50:
        return await ctx.send("❌ Shop name too long!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_name = ?, shop_open = 1 WHERE user_id = ?", (name, ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Shop '{name}' created! Use `.addshopitem <price> <item>` to add items.")

@bot.command(name="addshopitem")
@economy_check()
async def add_shop_item(ctx, price: int, *, item: str):
    if price <= 0:
        return await ctx.send("❌ Price must be positive!")
    data = await get_user(ctx.author.id)
    if not data[14]:
        return await ctx.send("❌ You don't have a shop!")
    if not data[16]:
        return await ctx.send("❌ Your shop is closed! Use `.closeshop` to open it.")
    items = json.loads(data[15]) if data[15] else {}
    if len(items) >= 20:
        return await ctx.send("❌ Your shop is full! Max 20 items.")
    items[item] = price
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), ctx.author.id))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Added '{item}' for {format_number(price)}{emoji}!")

@bot.command(name="removeshopitem")
@economy_check()
async def remove_shop_item(ctx, *, item: str):
    data = await get_user(ctx.author.id)
    if not data[14]:
        return await ctx.send("❌ You don't have a shop!")
    items = json.loads(data[15]) if data[15] else {}
    if item not in items:
        return await ctx.send("❌ Item not found!")
    del items[item]
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_items = ? WHERE user_id = ?", (json.dumps(items), ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Removed '{item}'!")

@bot.command(name="myshop")
@economy_check()
async def my_shop(ctx):
    data = await get_user(ctx.author.id)
    if not data[14]:
        return await ctx.send("❌ You don't have a shop!")
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
        return await ctx.send("❌ You don't have a shop!")
    new_status = 0 if data[16] else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET shop_open = ? WHERE user_id = ?", (new_status, ctx.author.id))
        await db.commit()
    await ctx.send(f"✅ Shop is now {'open' if new_status else 'closed'}!")

@bot.command(name="buyfromshop")
@economy_check()
async def buy_from_shop(ctx, seller: discord.User, *, item: str):
    seller_data = await get_user(seller.id)
    if not seller_data[14] or not seller_data[16]:
        return await ctx.send(f"❌ {seller.display_name}'s shop is closed!")
    items = json.loads(seller_data[15]) if seller_data[15] else {}
    if item not in items:
        return await ctx.send("❌ Item not found!")
    price = items[item]
    buyer_data = await get_user(ctx.author.id)
    if buyer_data[1] < price:
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
async def buy_business(ctx, business_type: str):
    types = ["restaurant", "casino", "cafe", "nightclub", "gym"]
    if business_type.lower() not in types:
        return await ctx.send(f"Types: {', '.join(types)}")
    data = await get_user(ctx.author.id)
    cost = 1000
    if data[1] < cost:
        return await ctx.send(f"❌ Need {format_number(cost)} coins!")
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT 1 FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            if await cursor.fetchone():
                return await ctx.send("❌ You already own a business!")
        await update_money(ctx.author.id, -cost)
        await db.execute("INSERT INTO businesses (user_id, business_type, level, last_collected) VALUES (?, ?, ?, ?)", (ctx.author.id, business_type.lower(), 1, datetime.utcnow().isoformat()))
        await db.commit()
    await ctx.send(f"✅ Bought a {business_type} business!")

@bot.command(name="business")
@economy_check()
async def business_info(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT business_type, level FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return await ctx.send("❌ You don't own a business!")
    biz_type, level = row
    await ctx.send(f"🏪 **Your {biz_type} business**\nLevel: {level}\nIncome: {format_number(50 * level)} coins/hour")

@bot.command(name="upgradebusiness")
@economy_check()
async def upgrade_business(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT level FROM businesses WHERE user_id = ?", (ctx.author.id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        return await ctx.send("❌ You don't own a business!")
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
        return await ctx.send("❌ You don't own a business!")
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
        return await ctx.send("❌ You don't own a business!")
    value = 500 * row[0]
    await update_money(ctx.author.id, value)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM businesses WHERE user_id = ?", (ctx.author.id,))
        await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Sold business for {format_number(value)}{emoji}!")

# ==================================================
# RELATIONSHIP COMMANDS
# ==================================================
@bot.command(name="date")
@economy_check()
async def date_cmd(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("❌ Can't date yourself!")
    data = await get_user(ctx.author.id)
    if data[17]:
        return await ctx.send("❌ Already married!")
    if data[1] < 500:
        return await ctx.send("❌ Need 500 coins for a date!")
    await update_money(ctx.author.id, -500)
    affection_gain = random.randint(50, 150)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET affection = affection + ? WHERE user_id = ?", (affection_gain, user.id))
        await db.commit()
    await ctx.send(f"💕 Date with {user.mention}! +{affection_gain} affection!")

@bot.command(name="marry")
@economy_check()
async def marry_cmd(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("❌ Can't marry yourself!")
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
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?, ?, 'marriage', ?)", (ctx.author.id, user.id, datetime.utcnow().isoformat()))
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cursor:
            req_id = (await cursor.fetchone())[0]
    view = RequestView(ctx.author, user, "marriage", req_id)
    embed = discord.Embed(title="💍 Marriage Proposal", color=discord.Color.purple())
    embed.add_field(name="From", value=ctx.author.mention, inline=True)
    embed.add_field(name="To", value=user.mention, inline=True)
    embed.add_field(name="Time Left", value="2 minutes", inline=True)
    await user.send(embed=embed, view=view)
    await ctx.send(f"💍 Marriage proposal sent to {user.mention}!")

@bot.command(name="divorce")
@economy_check()
async def divorce_cmd(ctx):
    data = await get_user(ctx.author.id)
    spouse_id = data[17]
    if not spouse_id:
        return await ctx.send("❌ Not married!")
    if data[1] < 2500:
        return await ctx.send("❌ Need 2500 coins for divorce!")
    await update_money(ctx.author.id, -2500)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (ctx.author.id,))
        await db.execute("UPDATE users SET spouse_id = NULL WHERE user_id = ?", (spouse_id,))
        await db.commit()
    spouse = await bot.fetch_user(spouse_id)
    await ctx.send(f"💔 Divorced {spouse.mention}!")

@bot.command(name="affection")
@economy_check()
async def affection_cmd(ctx, user: discord.User = None):
    target = user or ctx.author
    data = await get_user(target.id)
    affection = data[19]
    if affection >= 5000:
        level = "👑 Eternal Bond"
    elif affection >= 3500:
        level = "❤️ Soulmates"
    elif affection >= 2000:
        level = "💜 Lovers"
    elif affection >= 1000:
        level = "💙 Close Friends"
    elif affection >= 500:
        level = "💚 Friends"
    elif affection >= 100:
        level = "💛 Acquaintances"
    else:
        level = "💔 Strangers"
    bar = "█" * min(20, affection // 250) + "░" * (20 - min(20, affection // 250))
    embed = discord.Embed(title=f"💕 {target.display_name}'s Affection", color=discord.Color.pink())
    embed.add_field(name="Level", value=level, inline=False)
    embed.add_field(name="Points", value=f"{format_number(affection)}", inline=False)
    embed.add_field(name="Progress", value=f"`{bar}`", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="gift")
@economy_check()
async def gift_cmd(ctx, user: discord.User, amount_str: str):
    try:
        amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount! Use numbers like 500, 1k, 2.5m")
    if amount <= 0:
        return await ctx.send("❌ Amount must be positive!")
    if user == ctx.author:
        return await ctx.send("❌ Can't gift yourself!")
    data = await get_user(ctx.author.id)
    if data[1] < amount:
        return await ctx.send(f"❌ You have {format_number(data[1])} coins!")
    await update_money(ctx.author.id, -amount)
    await update_money(user.id, amount)
    affection_gain = amount // 100
    if affection_gain > 0:
        async with aiosqlite.connect("hakari.db") as db:
            await db.execute("UPDATE users SET affection = affection + ? WHERE user_id = ?", (affection_gain, user.id))
            await db.commit()
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    msg = f"🎁 Gifted {format_number(amount)}{emoji} to {user.mention}!"
    if affection_gain:
        msg += f" (+{format_number(affection_gain)} affection)"
    await ctx.send(msg)

@bot.command(name="adopt")
@economy_check()
async def adopt_cmd(ctx, user: discord.User):
    if user == ctx.author:
        return await ctx.send("❌ Can't adopt yourself!")
    data = await get_user(ctx.author.id)
    if data[1] < 2000:
        return await ctx.send("❌ Need 2000 coins!")
    target = await get_user(user.id)
    if target[18]:
        return await ctx.send(f"❌ {user.mention} already has a parent!")
    await update_money(ctx.author.id, -2000)
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT INTO requests (from_id, to_id, request_type, timestamp) VALUES (?, ?, 'adopt', ?)", (ctx.author.id, user.id, datetime.utcnow().isoformat()))
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cursor:
            req_id = (await cursor.fetchone())[0]
    view = RequestView(ctx.author, user, "adopt", req_id)
    embed = discord.Embed(title="👶 Adoption Request", color=discord.Color.teal())
    embed.add_field(name="From", value=ctx.author.mention, inline=True)
    embed.add_field(name="To", value=user.mention, inline=True)
    embed.add_field(name="Time Left", value="2 minutes", inline=True)
    await user.send(embed=embed, view=view)
    await ctx.send(f"👶 Adoption request sent to {user.mention}!")

@bot.command(name="children")
@economy_check()
async def children_cmd(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT child_id FROM children WHERE parent_id = ?", (ctx.author.id,)) as cursor:
            children = await cursor.fetchall()
    if not children:
        return await ctx.send("No children!")
    msg = f"👶 {ctx.author.display_name}'s children:\n"
    for child_id in children:
        try:
            child = await bot.fetch_user(child_id[0])
            msg += f"• {child.mention}\n"
        except:
            msg += f"• User {child_id[0]}\n"
    await ctx.send(msg)

@bot.command(name="family")
@economy_check()
async def family_cmd(ctx):
    data = await get_user(ctx.author.id)
    spouse_id = data[17]
    parent_id = data[18]
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT child_id FROM children WHERE parent_id = ?", (ctx.author.id,)) as cursor:
            children = await cursor.fetchall()
    msg = f"👨‍👩‍👧‍👦 **{ctx.author.display_name}'s Family**\n\n"
    if spouse_id:
        try:
            spouse = await bot.fetch_user(spouse_id)
            msg += f"💑 Spouse: {spouse.mention}\n"
        except:
            msg += f"💑 Spouse: User {spouse_id}\n"
    else:
        msg += "💑 Spouse: None\n"
    if parent_id:
        try:
            parent = await bot.fetch_user(parent_id)
            msg += f"👪 Parent: {parent.mention}\n"
        except:
            msg += f"👪 Parent: User {parent_id}\n"
    else:
        msg += "👪 Parent: None\n"
    if children:
        msg += "\n👶 Children:\n"
        for child_id in children:
            try:
                child = await bot.fetch_user(child_id[0])
                msg += f"• {child.mention}\n"
            except:
                msg += f"• User {child_id[0]}\n"
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
        return await ctx.send("No pending requests!")
    msg = "📬 Pending requests:\n"
    for rid, fid, rtype in reqs:
        try:
            user = await bot.fetch_user(fid)
            msg += f"`{rid}`: {user.mention} - {rtype}\n"
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
        return await ctx.send("Use: `.glb money` or `.glb xp`")
    async with aiosqlite.connect("hakari.db") as db:
        if category == "money":
            async with db.execute("SELECT user_id, money+bank as total FROM users ORDER BY total DESC LIMIT 10") as cursor:
                rows = await cursor.fetchall()
            title = "🌍 Global Richest"
            suffix = " coins"
        else:
            async with db.execute("SELECT user_id, total_xp FROM users ORDER BY total_xp DESC LIMIT 10") as cursor:
                rows = await cursor.fetchall()
            title = "🌍 Global Top XP"
            suffix = " XP"
    if not rows:
        return await ctx.send("No data yet!")
    msg = f"**{title}**\n\n"
    for i, (uid, val) in enumerate(rows, 1):
        try:
            user = await bot.fetch_user(uid)
            name = user.display_name
        except:
            name = f"User {uid}"
        msg += f"{i}. {name}: {format_number(val)}{suffix}\n"
    await ctx.send(msg)

@bot.command(name="serverleaderboard", aliases=["slb"])
@economy_check()
async def server_leaderboard(ctx, category: str = "money"):
    if category not in ["money", "xp"]:
        return await ctx.send("Use: `.slb money` or `.slb xp`")
    members = [m for m in ctx.guild.members if not m.bot]
    data_list = []
    async with aiosqlite.connect("hakari.db") as db:
        for member in members:
            async with db.execute("SELECT money, bank, total_xp FROM users WHERE user_id = ?", (member.id,)) as cursor:
                row = await cursor.fetchone()
            if row:
                if category == "money":
                    data_list.append((member, row[0] + row[1]))
                else:
                    data_list.append((member, row[4]))
    data_list.sort(key=lambda x: x[1], reverse=True)
    top = data_list[:10]
    if not top:
        return await ctx.send("No data yet!")
    title = f"📊 Server {'Richest' if category=='money' else 'Top XP'} - {ctx.guild.name}"
    suffix = " coins" if category == "money" else " XP"
    msg = f"**{title}**\n\n"
    for i, (member, val) in enumerate(top, 1):
        msg += f"{i}. {member.display_name}: {format_number(val)}{suffix}\n"
    await ctx.send(msg)

@bot.command(name="topcouples")
@economy_check()
async def top_couples(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, spouse_id, affection FROM users WHERE spouse_id IS NOT NULL ORDER BY affection DESC LIMIT 10") as cursor:
            couples = await cursor.fetchall()
    if not couples:
        return await ctx.send("No couples yet!")
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
    data = await get_user(ctx.author.id)
    level = data[4]
    xp = data[5]
    next_level_xp = ((level + 1) ** 2) * 100
    needed = next_level_xp - xp
    if level > 0:
        bar_length = min(20, int((xp - (level ** 2 * 100)) / (next_level_xp - (level ** 2 * 100)) * 20))
    else:
        bar_length = min(20, int(xp / 100 * 20))
    bar = "█" * max(0, bar_length) + "░" * (20 - max(0, bar_length))
    await ctx.send(f"📊 **{ctx.author.display_name}**\nLevel: {level}\nXP: {format_number(xp)}/{format_number(next_level_xp)}\nProgress: `{bar}`\nNeeded: {format_number(needed)} XP")

# ==================================================
# OWNER COMMANDS
# ==================================================
@bot.command(name="addowner")
@owner_only()
async def add_owner_cmd(ctx, user_id: int):
    if not await is_main_owner(ctx.author.id):
        return await ctx.send("❌ Only main owner can add owners!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO owners (user_id, is_main) VALUES (?, 0)", (user_id,))
        await db.commit()
    await ctx.send(f"✅ Added <@{user_id}> as owner!")

@bot.command(name="removeowner")
@owner_only()
async def remove_owner_cmd(ctx, user_id: int):
    if not await is_main_owner(ctx.author.id):
        return await ctx.send("❌ Only main owner can remove owners!")
    if user_id == MAIN_OWNER_ID:
        return await ctx.send("❌ Cannot remove main owner!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("DELETE FROM owners WHERE user_id = ?", (user_id,))
        await db.commit()
    await ctx.send(f"✅ Removed <@{user_id}> from owners!")

@bot.command(name="ownerlist")
@owner_only()
async def owner_list_cmd(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id, is_main FROM owners") as cursor:
            owners = await cursor.fetchall()
    msg = "👑 **Bot Owners**\n\n"
    for uid, is_main in owners:
        role = "👑 Main Owner" if is_main else "🔹 Owner"
        msg += f"• <@{uid}> - {role}\n"
    await ctx.send(msg)

@bot.command(name="addmoney")
@owner_only()
async def add_money_cmd(ctx, user: discord.User, amount_str: str):
    try:
        amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount! Use numbers like 500, 1k, 2.5m")
    await update_money(user.id, amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Added {format_number(amount)}{emoji} to {user.mention}!")
    await log_action(ctx.author.id, "Add Money", f"Target: {user.id}, Amount: {amount}")

@bot.command(name="removemoney")
@owner_only()
async def remove_money_cmd(ctx, user: discord.User, amount_str: str):
    try:
        amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount! Use numbers like 500, 1k, 2.5m")
    await update_money(user.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Removed {format_number(amount)}{emoji} from {user.mention}!")
    await log_action(ctx.author.id, "Remove Money", f"Target: {user.id}, Amount: {amount}")

@bot.command(name="setmoney")
@owner_only()
async def set_money_cmd(ctx, user: discord.User, amount_str: str):
    try:
        amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount! Use numbers like 500, 1k, 2.5m")
    await set_money(user.id, amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Set {user.mention}'s balance to {format_number(amount)}{emoji}!")

@bot.command(name="addbank")
@owner_only()
async def add_bank_cmd(ctx, user: discord.User, amount_str: str):
    try:
        amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount! Use numbers like 500, 1k, 2.5m")
    await update_bank(user.id, amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Added {format_number(amount)}{emoji} to {user.mention}'s bank!")

@bot.command(name="removebank")
@owner_only()
async def remove_bank_cmd(ctx, user: discord.User, amount_str: str):
    try:
        amount = parse_amount(amount_str)
    except:
        return await ctx.send("❌ Invalid amount! Use numbers like 500, 1k, 2.5m")
    await update_bank(user.id, -amount)
    emoji = await get_setting(ctx.guild.id, "currency_emoji")
    await ctx.send(f"✅ Removed {format_number(amount)}{emoji} from {user.mention}'s bank!")

@bot.command(name="protect")
@owner_only()
async def protect_cmd(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET protected = 1 WHERE user_id = ?", (user.id,))
        await db.commit()
    await ctx.send(f"✅ {user.mention} is now protected from robbery!")

@bot.command(name="unprotect")
@owner_only()
async def unprotect_cmd(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET protected = 0 WHERE user_id = ?", (user.id,))
        await db.commit()
    await ctx.send(f"✅ {user.mention} is no longer protected!")

@bot.command(name="protectedlist")
@owner_only()
async def protected_list_cmd(ctx):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT user_id FROM users WHERE protected = 1") as cursor:
            users = await cursor.fetchall()
    if not users:
        return await ctx.send("No protected users!")
    msg = "🛡️ **Protected Users**\n\n"
    for uid in users:
        msg += f"• <@{uid[0]}>\n"
    await ctx.send(msg)

@bot.command(name="blacklist")
@owner_only()
async def blacklist_cmd(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET blacklisted = 1 WHERE user_id = ?", (user.id,))
        await db.commit()
    await ctx.send(f"✅ {user.mention} has been blacklisted!")

@bot.command(name="whitelist")
@owner_only()
async def whitelist_cmd(ctx, user: discord.User):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET blacklisted = 0 WHERE user_id = ?", (user.id,))
        await db.commit()
    await ctx.send(f"✅ {user.mention} has been whitelisted!")

@bot.command(name="economywipe")
@owner_only()
async def economy_wipe_cmd(ctx):
    await ctx.send("⚠️ **WARNING** - This will reset EVERYONE'S money and bank to 0!\nType `confirm` within 30 seconds to proceed.")
    def check(m): return m.author == ctx.author and m.content.lower() == "confirm"
    try:
        await bot.wait_for("message", timeout=30, check=check)
    except asyncio.TimeoutError:
        return await ctx.send("❌ Economy wipe cancelled.")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("UPDATE users SET money = 0, bank = 0")
        await db.commit()
    await ctx.send("✅ Economy has been wiped!")
    await log_action(ctx.author.id, "Economy Wipe", "Full wipe performed")

@bot.command(name="toggleeconomy")
@owner_only()
async def toggle_economy_cmd(ctx):
    current = await get_setting(ctx.guild.id, "economy_enabled")
    new = 0 if current else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, economy_enabled) VALUES (?, ?)", (ctx.guild.id, new))
        await db.commit()
    await ctx.send(f"✅ Economy commands {'enabled' if new else 'disabled'}!")

@bot.command(name="togglerob")
@owner_only()
async def toggle_rob_cmd(ctx):
    current = await get_setting(ctx.guild.id, "rob_enabled")
    new = 0 if current else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, rob_enabled) VALUES (?, ?)", (ctx.guild.id, new))
        await db.commit()
    await ctx.send(f"✅ Rob command {'enabled' if new else 'disabled'}!")

@bot.command(name="togglegambling")
@owner_only()
async def toggle_gambling_cmd(ctx):
    current = await get_setting(ctx.guild.id, "gambling_enabled")
    new = 0 if current else 1
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, gambling_enabled) VALUES (?, ?)", (ctx.guild.id, new))
        await db.commit()
    await ctx.send(f"✅ Gambling commands {'enabled' if new else 'disabled'}!")

@bot.command(name="setdailyamount")
@owner_only()
async def set_daily_cmd(ctx, amount: int):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, daily_amount) VALUES (?, ?)", (ctx.guild.id, amount))
        await db.commit()
    await ctx.send(f"✅ Daily reward set to {format_number(amount)} coins!")

@bot.command(name="setsleepamount")
@owner_only()
async def set_sleep_cmd(ctx, min_amount: int, max_amount: int):
    if min_amount > max_amount:
        return await ctx.send("❌ Min cannot be greater than max!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, sleep_amount_min, sleep_amount_max) VALUES (?, ?, ?)", (ctx.guild.id, min_amount, max_amount))
        await db.commit()
    await ctx.send(f"✅ Sleep reward set to {format_number(min_amount)}-{format_number(max_amount)} coins!")

@bot.command(name="setworkamount")
@owner_only()
async def set_work_cmd(ctx, min_amount: int, max_amount: int):
    if min_amount > max_amount:
        return await ctx.send("❌ Min cannot be greater than max!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, work_amount_min, work_amount_max) VALUES (?, ?, ?)", (ctx.guild.id, min_amount, max_amount))
        await db.commit()
    await ctx.send(f"✅ Work reward set to {format_number(min_amount)}-{format_number(max_amount)} coins!")

@bot.command(name="setcrimeamount")
@owner_only()
async def set_crime_cmd(ctx, min_amount: int, max_amount: int):
    if min_amount > max_amount:
        return await ctx.send("❌ Min cannot be greater than max!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, crime_amount_min, crime_amount_max) VALUES (?, ?, ?)", (ctx.guild.id, min_amount, max_amount))
        await db.commit()
    await ctx.send(f"✅ Crime reward set to {format_number(min_amount)}-{format_number(max_amount)} coins!")

@bot.command(name="setinterestrate")
@owner_only()
async def set_interest_rate_cmd(ctx, percent: int):
    if percent < 0 or percent > 50:
        return await ctx.send("❌ Interest rate must be between 0 and 50!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, interest_rate) VALUES (?, ?)", (ctx.guild.id, percent))
        await db.commit()
    await ctx.send(f"✅ Bank interest rate set to {percent}% daily!")

@bot.command(name="setmaxwithdraw")
@owner_only()
async def set_max_withdraw_cmd(ctx, amount: int):
    if amount < 1000:
        return await ctx.send("❌ Max withdraw must be at least 1000!")
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, max_withdraw) VALUES (?, ?)", (ctx.guild.id, amount))
        await db.commit()
    await ctx.send(f"✅ Max withdraw set to {format_number(amount)} coins per transaction!")

@bot.command(name="setcurrency")
@owner_only()
async def set_currency_cmd(ctx, emoji: str):
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, currency_emoji) VALUES (?, ?)", (ctx.guild.id, emoji))
        await db.commit()
    await ctx.send(f"✅ Currency emoji set to {emoji}!")

@bot.command(name="logs")
@owner_only()
async def logs_cmd(ctx, limit: int = 10):
    async with aiosqlite.connect("hakari.db") as db:
        async with db.execute("SELECT timestamp, user_id, action, details FROM logs ORDER BY id DESC LIMIT ?", (min(limit, 20),)) as cursor:
            logs = await cursor.fetchall()
    if not logs:
        return await ctx.send("No logs found!")
    msg = "📜 **Recent Logs**\n\n"
    for ts, uid, act, det in logs:
        msg += f"• {ts[:16]} - <@{uid}>: {act} {det}\n"
        if len(msg) > 1900:
            break
    await ctx.send(msg)

# ==================================================
# EVENTS
# ==================================================
@bot.event
async def on_ready():
    await init_db()
    bank_interest.start()
    print(f"✅ Logged in as {bot.user}")
    print(f"✅ Ready on {len(bot.guilds)} servers")
    print(f"✅ Main Owner ID: {MAIN_OWNER_ID}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    async with aiosqlite.connect("hakari.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.author.id,))
        await db.execute("UPDATE users SET daily_messages = daily_messages + 1 WHERE user_id = ?", (message.author.id,))
        await db.commit()
    
    xp_gain = random.randint(10, 20)
    new_level = await add_xp(message.author.id, xp_gain)
    if new_level:
        level_msg = await message.channel.send(f"🎉 {message.author.mention} leveled up to level {new_level}!")
        await asyncio.sleep(5)
        await level_msg.delete()
    
    await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission!")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument!")
    else:
        print(f"Error: {error}")

# ==================================================
# RUN BOT
# ==================================================
if __name__ == "__main__":
    bot.run(TOKEN)
