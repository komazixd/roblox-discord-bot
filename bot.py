import discord
from discord import app_commands
from discord.ext import tasks
import requests
import json
import os

TOKEN = os.getenv('DISCORD_BOT_TOKEN')  # Put your token in env var for safety

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

DATA_FILE = 'botdata.json'

# Load or init data
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r') as f:
        data = json.load(f)
else:
    data = {
        "guild_settings": {},
        "last_states": {}
    }

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# Roblox API helpers
def get_group_users(group_id):
    users = {}
    cursor = None
    while True:
        url = f"https://groups.roblox.com/v1/groups/{group_id}/users?limit=100"
        if cursor:
            url += f"&cursor={cursor}"
        r = requests.get(url)
        if r.status_code != 200:
            break
        js = r.json()
        for entry in js.get("data", []):
            user = entry['user']
            users[user['userId']] = {
                "username": user['name'],
                "rank": entry['role']['rank'],
                "rank_name": entry['role']['name']
            }
        cursor = js.get("nextPageCursor")
        if not cursor:
            break
    return users

def get_username(user_id):
    r = requests.get(f"https://users.roblox.com/v1/users/{user_id}")
    if r.status_code == 200:
        return r.json().get("name")
    else:
        return f"User {user_id}"

# ---------- Commands ----------

@tree.command(name="help", description="Show bot commands and usage")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Roblox Group Monitor Bot Help", color=discord.Color.blue())
    embed.add_field(name="/setgroup <group_id>", value="Set the Roblox group ID to monitor in this server", inline=False)
    embed.add_field(name="/setchannel", value="Set the channel where notifications will be sent", inline=False)
    embed.add_field(name="/sniper add <discord_user> <roblox_username>", value="Start stalking Roblox user, linked to Discord user", inline=False)
    embed.add_field(name="/sniper remove <discord_user>", value="Stop stalking Roblox user linked to Discord user", inline=False)
    embed.add_field(name="/sniper list", value="List all active snipers", inline=False)
    embed.add_field(name="/ping", value="Check bot latency", inline=False)
    embed.add_field(name="/serverinfo", value="Show info about this server", inline=False)
    embed.add_field(name="/muuz", value="Say a funny Muuz message", inline=False)
    embed.add_field(name="/say <text>", value="Make the bot say something", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="setgroup", description="Set the Roblox group ID to monitor")
@app_commands.describe(group_id="Roblox Group ID")
async def setgroup_command(interaction: discord.Interaction, group_id: int):
    guild_id = str(interaction.guild.id)
    settings = data["guild_settings"].setdefault(guild_id, {})
    settings["group_id"] = group_id
    save_data()
    await interaction.response.send_message(f"✅ Set group ID to `{group_id}` for this server.", ephemeral=True)

@tree.command(name="setchannel", description="Set the channel to send notifications in")
async def setchannel_command(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    settings = data["guild_settings"].setdefault(guild_id, {})
    settings["channel_id"] = interaction.channel.id
    save_data()
    await interaction.response.send_message(f"✅ This channel is now set for notifications.", ephemeral=True)

# Sniper group commands
class Sniper(app_commands.Group):
    def __init__(self):
        super().__init__(name="sniper", description="Manage Roblox user snipers")

    @app_commands.command(name="add", description="Start stalking a Roblox user linked to a Discord user")
    @app_commands.describe(discord_user="Mention Discord user", roblox_username="Roblox username")
    async def add(self, interaction: discord.Interaction, discord_user: discord.Member, roblox_username: str):
        guild_id = str(interaction.guild.id)
        settings = data["guild_settings"].setdefault(guild_id, {})
        snipers = settings.setdefault("snipers", {})

        r = requests.get(f"https://api.roblox.com/users/get-by-username?username={roblox_username}")
        if r.status_code != 200 or 'Id' not in r.json():
            await interaction.response.send_message("❌ Roblox username not found.", ephemeral=True)
            return
        roblox_id = r.json()["Id"]
        if roblox_id == 0:
            await interaction.response.send_message("❌ Roblox username not found.", ephemeral=True)
            return

        snipers[str(discord_user.id)] = {
            "roblox_id": roblox_id,
            "roblox_username": roblox_username
        }
        save_data()
        await interaction.response.send_message(f"✅ Now stalking Roblox user `{roblox_username}` for {discord_user.mention}", ephemeral=True)

    @app_commands.command(name="remove", description="Stop stalking Roblox user linked to a Discord user")
    @app_commands.describe(discord_user="Discord user to remove sniper for")
    async def remove(self, interaction: discord.Interaction, discord_user: discord.Member):
        guild_id = str(interaction.guild.id)
        settings = data["guild_settings"].get(guild_id, {})
        snipers = settings.get("snipers", {})
        if str(discord_user.id) in snipers:
            del snipers[str(discord_user.id)]
            save_data()
            await interaction.response.send_message(f"✅ Stopped stalking Roblox user for {discord_user.mention}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ No sniper found for {discord_user.mention}", ephemeral=True)

    @app_commands.command(name="list", description="List all active snipers")
    async def list_snipers(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        settings = data["guild_settings"].get(guild_id, {})
        snipers = settings.get("snipers", {})
        if not snipers:
            await interaction.response.send_message("No active snipers.", ephemeral=True)
            return
        msg = ""
        for did, roblox_info in snipers.items():
            member = interaction.guild.get_member(int(did))
            mention = member.mention if member else f"<@{did}>"
            msg += f"{mention} → `{roblox_info['roblox_username']}`\n"
        await interaction.response.send_message(msg, ephemeral=True)

tree.add_command(Sniper())

# Fun and utility commands

@tree.command(name="ping", description="Check bot latency")
async def ping_command(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! Latency: {latency}ms", ephemeral=True)

@tree.command(name="serverinfo", description="Show info about this server")
async def serverinfo_command(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"Server Info: {guild.name}", color=discord.Color.green())
    embed.add_field(name="Member Count", value=str(guild.member_count))
    embed.add_field(name="Server ID", value=str(guild.id))
    embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="muuz", description="Say a funny Muuz message")
@app_commands.describe(message="What Muuz says")
async def muuz_command(interaction: discord.Interaction, message: str):
    responses = [
        "am muuz elisa lol feet piktur",
        "muuz says hi 👋",
        "muuz is watching you 👀",
        "muuz loves Roblox and feet pics 😜",
        "muuz approves this message ✅"
    ]
    # You can also just echo the message like a fun parrot
    # But let’s randomly pick a response if message includes "feet"
    if "feet" in message.lower():
        response = responses[0]
    else:
        response = responses[1]
    await interaction.response.send_message(f"🗣️ Muuz says: {response}")

@tree.command(name="say", description="Make the bot say something")
@app_commands.describe(text="Text to say")
async def say_command(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

# ---------- Monitoring Task ----------

@tasks.loop(seconds=60)
async def monitor_groups():
    for guild_id, settings in data["guild_settings"].items():
        group_id = settings.get("group_id")
        channel_id = settings.get("channel_id")
        snipers = settings.get("snipers", {})

        if not group_id or not channel_id:
            continue

        channel = bot.get_channel(channel_id)
        if not channel:
            continue

        last_state = data["last_states"].get(guild_id, {}).get("members", {})

        try:
            current_state = get_group_users(group_id)
        except Exception as e:
            print(f"Error fetching group {group_id}: {e}")
            continue

        last_state = {int(k): v for k, v in last_state.items()}

        last_user_ids = set(last_state.keys())
        current_user_ids = set(current_state.keys())

        joined = current_user_ids - last_user_ids
        left = last_user_ids - current_user_ids
        rank_changed = []

        for uid in current_user_ids & last_user_ids:
            if current_state[uid]["rank"] != last_state[uid]["rank"]:
                rank_changed.append(uid)

        for uid in joined:
            info = current_state[uid]
            await channel.send(f"✅ **{info['username']}** has **joined** the group with rank `{info['rank_name']}`.")

        for uid in left:
            uname = get_username(uid)
            await channel.send(f"❌ **{uname}** has **left** the group.")

        for uid in rank_changed:
            info = current_state[uid]
            old_rank_name = last_state[uid].get("rank_name", "unknown")
            await channel.send(f"⚠️ **{info['username']}** rank changed from `{old_rank_name}` to `{info['rank_name']}`.")

        # Update last state
        data["last_states"].setdefault(guild_id, {})["members"] = current_state
        save_data()

        # Sniper monitoring
        for discord_id, roblox_info in snipers.items():
            roblox_id = roblox_info["roblox_id"]
            roblox_name = roblox_info["roblox_username"]

            if roblox_id in current_state:
                rank = current_state[roblox_id]["rank_name"]
                await channel.send(f"👁️ Sniper: Roblox user `{roblox_name}` ({roblox_id}) is currently in the group with rank `{rank}`.")
            else:
                await channel.send(f"👁️ Sniper: Roblox user `{roblox_name}` ({roblox_id}) is **not** in the group.")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await tree.sync()
    monitor_groups.start()

bot.run(TOKEN)
