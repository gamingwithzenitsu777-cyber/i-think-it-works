import os
import json
import asyncio
import re
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

try:
    from samp_py.client import SampClient
except ImportError:
    SampClient = None

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
CONFIG_FILE = "config.json"
WHITELIST_ROLE_ID = 1551301308223463576

# SA-MP auto-whitelist settings. Give the CITIZEN role ID later by replacing 0.
CITIZEN_ROLE_ID = 0
SAMP_WHITELIST_CHANNEL_ID = 0
# The bot uses SA-MP RCON to run the whitelist command. Keep the RCON password in .env.
SAMP_RCON_PASSWORD = os.getenv("SAMP_RCON_PASSWORD", "").strip()
# Change this to the actual whitelist command used by your gamemode.
# Example: whitelist add {name}
SAMP_WHITELIST_COMMAND = os.getenv("SAMP_WHITELIST_COMMAND", "whitelist add {name}").strip()
# OCRP whitelist plugin expects this command via OnRconCommand.
# The plugin stores names in scriptfiles/ocrp_whitelist.txt.
# Keep the Discord bot token in .env; never put it in the SA-MP plugin.

DEFAULT_CONFIG = {
    "welcome_channel": None,
    "leave_channel": None,
    "announcement_channel": None,
    "status_channel": None,
    "status_message": None,
    "whitelist_channel": None,
    "whitelist_review_channel": None,
    "whitelist_acceptance_channel": None,
    "samp_whitelist_channel": None,
    "igwh_message_channel": None,
    "ig_ban_log_channel": None,
    "ig_unban_log_channel": None,
    "ig_unban_apply_channel": None,
    "ig_jail_log_channel": None,
    "ig_warn_log_channel": None,
    "ig_cooldown_log_channel": None,
    "ig_same_ip_whitelist_channel": None,
    "samp_whitelisted_names": [],
    "samp_ip": "",
    "samp_port": 7777
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = DEFAULT_CONFIG.copy()
        cfg.update(data)
        return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

config = load_config()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class OCRPBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        self.add_view(WhitelistView())
        if not status_loop.is_running():
            status_loop.start()

bot = OCRPBot()

def channel_from_config(key):
    cid = config.get(key)
    return bot.get_channel(int(cid)) if cid else None

def base_embed(title, description="", color=discord.Color.blurple()):
    e = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )
    e.set_footer(text="OCRP BOT")
    return e

async def get_samp_status():
    ip = str(config.get("samp_ip", "")).strip()
    port = int(config.get("samp_port", 7777))

    if not ip or SampClient is None:
        return False, 0, 0, []

    try:
        async with SampClient(address=ip, port=port) as client:
            if not await client.is_online():
                return False, 0, 0, []

            info = await client.get_server_info()
            clients = await client.get_server_clients()

            names = []
            for player in clients or []:
                name = getattr(player, "name", None)
                if name:
                    names.append(str(name))

            return True, int(info.players), int(info.max_players), names
    except Exception as exc:
        print(f"SA-MP query error: {exc}")
        return False, 0, 0, []


def make_status_components(online_ok, online, maxplayers, names):
    """
    TRUE Discord Components V2 status message.
    This intentionally does NOT use discord.Embed.
    Requires a recent discord.py version with Components V2 support.
    """
    ip = config.get("samp_ip") or "Not configured"
    port = config.get("samp_port", 7777)

    if online_ok:
        player_count = max(0, int(online))
        max_count = max(0, int(maxplayers))

        if max_count > 0:
            percent = min(100, int((player_count / max_count) * 100))
            filled = min(10, round(percent / 10))
            bar = "▰" * filled + "▱" * (10 - filled)
            player_value = f"**{player_count}/{max_count}**  `{bar}` **{percent}%**"
        else:
            player_value = f"**{player_count}**"

        status_text = (
            "## 🎮 OCRP • SERVER STATUS\n"
            "🟢 **ONLINE**\n"
            "*Server is online and responding normally.*"
        )

        info_text = (
            f"### 👥 Players\n{player_value}\n\n"
            f"### 🌐 Server Address\n`{ip}:{port}`\n\n"
            "### 🔄 Auto Refresh\n`30 seconds`"
        )

        if names:
            player_lines = []
            for index, name in enumerate(names, start=1):
                line = f"`{index:02}`  {name}"
                player_lines.append(line)

            # Components V2 text displays are kept comfortably below Discord's limit.
            player_text = "\n".join(player_lines)
            if len(player_text) > 3900:
                player_text = player_text[:3890] + "\n…"

            players_text = f"### 👤 Online Players\n{player_text}"
        else:
            players_text = "### 👤 Online Players\n`No players online`"

    else:
        status_text = (
            "## 🎮 OCRP • SERVER STATUS\n"
            "🔴 **OFFLINE**\n"
            "*Server is offline or unreachable.*"
        )

        info_text = (
            "### 👥 Players\n**0**\n\n"
            f"### 🌐 Server Address\n`{ip}:{port}`\n\n"
            "### 📡 Connection\n`UNREACHABLE`"
        )

        players_text = "### 👤 Online Players\n`Server is offline or unreachable.`"

    # Components V2 UI: Container + TextDisplay + Separators.
    container = discord.ui.Container(
        discord.ui.TextDisplay(status_text),
        discord.ui.Separator(),
        discord.ui.TextDisplay(info_text),
        discord.ui.Separator(),
        discord.ui.TextDisplay(players_text),
        discord.ui.Separator(),
        discord.ui.TextDisplay(
            "*OCRP BOT • SA-MP STATUS • AUTO REFRESH 30S*"
        )
    )

    layout = discord.ui.LayoutView(timeout=None)
    layout.add_item(container)
    return layout

async def update_status():
    channel = channel_from_config("status_channel")
    if not channel:
        return

    ok, players, maxplayers, names = await get_samp_status()
    components = make_status_components(ok, players, maxplayers, names)

    msg = None
    mid = config.get("status_message")
    if mid:
        try:
            msg = await channel.fetch_message(int(mid))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
            msg = None

    try:
        if msg:
            try:
                # Components V2 messages use LayoutView, not a `components=`
                # keyword on Message.edit(). If the stored message is an older
                # embed, replace it with a fresh Components V2 message.
                await msg.edit(view=components)
            except (TypeError, discord.HTTPException):
                try:
                    await msg.delete()
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
                msg = await channel.send(view=components)
                config["status_message"] = str(msg.id)
                save_config(config)
        else:
            msg = await channel.send(view=components)
            config["status_message"] = str(msg.id)
            save_config(config)
    except (TypeError, discord.HTTPException) as exc:
        print(f"Status Components V2 update error: {exc}")

@tasks.loop(seconds=30)
async def status_loop():
    await update_status()

@status_loop.before_loop
async def before_status_loop():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} | OCRP BOT")
    print("Slash commands synced.")
    print("SA-MP status refresh: every 30 seconds")

@bot.event
async def on_message(message: discord.Message):
    # Auto SA-MP whitelist: a user sends only their in-game name in the configured channel.
    if message.author.bot:
        return

    configured_channel_id = config.get("samp_whitelist_channel") or SAMP_WHITELIST_CHANNEL_ID
    try:
        configured_channel_id = int(configured_channel_id or 0)
    except (TypeError, ValueError):
        configured_channel_id = 0

    if configured_channel_id and message.channel.id == configured_channel_id:
        ingame_name = message.content.strip()

        # Ignore empty/multi-line messages and Discord commands.
        if ingame_name and "\n" not in ingame_name and "\r" not in ingame_name and not ingame_name.startswith("/"):
            await process_samp_whitelist_request(message, ingame_name)

    await bot.process_commands(message)


async def process_samp_whitelist_request(message: discord.Message, ingame_name: str):
    if not config.get("samp_ip"):
        await message.channel.send("❌ SA-MP server IP is not configured. Use `/setup-samp` first.")
        return

    if SampClient is None:
        await message.channel.send("❌ `samp_py` is not installed, so SA-MP RCON is unavailable.")
        return

    if not SAMP_RCON_PASSWORD:
        await message.channel.send("❌ SA-MP RCON password is not configured in the bot's `.env` file.")
        return

    # SA-MP RP name format must be exactly Firstname_Lastname.
    if not re.fullmatch(r"[A-Z][a-z]+_[A-Z][a-z]+", ingame_name):
        await message.channel.send(
            "❌ **Invalid in-game name format.**\n"
            "Please use exactly: `Firstname_Lastname`\n"
            "Example: `John_Doe`\n"
            "Both names must start with a capital letter and the remaining letters must be lowercase."
        )
        return

    if len(ingame_name) > 24:
        await message.channel.send(
            "❌ **Invalid in-game name.** Please keep it within the SA-MP name length limit."
        )
        return

    guild = message.guild
    if guild is None:
        return

    # The player MUST enter the SA-MP server first.
    # We verify that the exact RP name is currently online before allowing
    # the whitelist request.
    try:
        async with SampClient(
            address=str(config["samp_ip"]),
            port=int(config.get("samp_port", 7777)),
        ) as client:
            if not await client.is_online():
                await message.channel.send(
                    "❌ **SA-MP server is currently offline.**\n"
                    "Enter the server first and come back here."
                )
                return

            clients = await client.get_server_clients()
            online_names = []
            for player in clients or []:
                player_name = getattr(player, "name", None)
                if player_name:
                    online_names.append(str(player_name))

    except Exception as exc:
        print(f"SA-MP player check error for {ingame_name}: {exc}")
        await message.channel.send(
            "❌ I couldn't check the SA-MP server right now. Please try again in a moment."
        )
        return

    if not any(name == ingame_name for name in online_names):
        await message.channel.send(
            f"❌ **{ingame_name} is not currently in the SA-MP server.**\n"
            "Please **enter the server first**, join with your in-game name, "
            "and then come back and send your name here."
        )
        return

    member = message.author

    citizen_role = guild.get_role(CITIZEN_ROLE_ID) if CITIZEN_ROLE_ID else None
    if citizen_role is None:
        await message.channel.send(
            "❌ The **CITIZEN** role ID is not configured yet. "
            "Set `CITIZEN_ROLE_ID` in the bot file first."
        )
        return

    if citizen_role >= guild.me.top_role:
        await message.channel.send(
            "❌ I cannot assign the **CITIZEN** role. Move that role below the bot's highest role."
        )
        return

    # Keep a persistent record too, so the bot can reject a name that it
    # has already successfully whitelisted.
    whitelisted_names = config.get("samp_whitelisted_names", [])
    if not isinstance(whitelisted_names, list):
        whitelisted_names = []

    if ingame_name.lower() in {str(n).lower() for n in whitelisted_names}:
        await message.channel.send(
            "❌ **THIS ACCOUNT IS ALREADY WHITELIST. GET ANOTHER NAME.**"
        )
        return

    rcon_command = SAMP_WHITELIST_COMMAND.replace("{name}", ingame_name)

    try:
        async with SampClient(
            address=str(config["samp_ip"]),
            port=int(config.get("samp_port", 7777)),
            rcon_password=SAMP_RCON_PASSWORD,
        ) as client:
            response = await client.send_rcon_command(rcon_command)

        response_text = "\n".join(str(line) for line in (response or []))
        lower_response = response_text.lower()

        # Different gamemodes use different wording for an already-whitelisted
        # account, so handle the common responses.
        already_words = (
            "already whitelist",
            "already whitelisted",
            "already on whitelist",
            "already in whitelist",
            "account already",
            "already exists",
            "is already",
        )
        if any(word in lower_response for word in already_words):
            await message.channel.send(
                "❌ **THIS ACCOUNT IS ALREADY WHITELIST. GET ANOTHER NAME.**"
            )
            return

        failure_words = (
            "invalid rcon",
            "incorrect rcon",
            "bad rcon",
            "unknown command",
            "command not found",
            "error:",
        )
        if any(word in lower_response for word in failure_words):
            print(f"SA-MP whitelist RCON response for {ingame_name}: {response_text}")
            await message.channel.send(
                "❌ SA-MP rejected the whitelist command. "
                "Check `SAMP_WHITELIST_COMMAND` and the server RCON setup."
            )
            return

        # Record the successfully processed account before assigning the role.
        if ingame_name not in whitelisted_names:
            whitelisted_names.append(ingame_name)
        config["samp_whitelisted_names"] = whitelisted_names
        save_config(config)

        await member.add_roles(citizen_role, reason=f"SA-MP whitelist for {ingame_name}")

        # Success messages are sent ONLY to the channel configured with /igwh-message.
        success_channel = channel_from_config("igwh_message_channel")
        if success_channel is None:
            print("SA-MP whitelist succeeded, but /igwh-message has not been configured.")
            return

        await success_channel.send(
            f"HEY {member.mention} YOU GOT WHITELIST IN SA-MP ENJOY YOUR RP 🥳"
        )

    except discord.Forbidden:
        await message.channel.send(
            "❌ I couldn't give you the **CITIZEN** role. "
            "Check my Manage Roles permission and role position."
        )
    except Exception as exc:
        print(f"SA-MP auto-whitelist error for {ingame_name}: {exc}")
        await message.channel.send(
            "❌ I couldn't complete the SA-MP whitelist right now. Please contact staff."
        )


@bot.event
async def on_member_join(member):
    channel = channel_from_config("welcome_channel")
    if not channel:
        return

    embed = base_embed(
        "👋 WELCOME TO OCRP",
        f"Welcome {member.mention}!\n\nWe're glad to have you here. Enjoy the server!",
        discord.Color.green()
    )
    embed.add_field(name="👤 Member", value=member.mention, inline=True)
    embed.add_field(name="👥 Members", value=str(member.guild.member_count), inline=True)
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    if member.guild.icon:
        embed.set_author(name=member.guild.name, icon_url=member.guild.icon.url)

    await channel.send(embed=embed)

@bot.event
async def on_member_remove(member):
    channel = channel_from_config("leave_channel")
    if not channel:
        return

    embed = base_embed(
        "🚪 MEMBER LEFT",
        f"**{member}** has left the server.",
        discord.Color.red()
    )
    embed.add_field(name="👤 User", value=str(member), inline=True)
    embed.add_field(name="🆔 ID", value=str(member.id), inline=True)
    embed.add_field(name="👥 Members", value=str(member.guild.member_count), inline=True)
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)

    await channel.send(embed=embed)

@bot.tree.command(name="setup-welcome", description="Set the welcome channel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_welcome(interaction: discord.Interaction, channel: discord.TextChannel):
    config["welcome_channel"] = str(channel.id)
    save_config(config)
    await interaction.response.send_message(f"✅ Welcome channel set to {channel.mention}.", ephemeral=True)

@bot.tree.command(name="setup-leave", description="Set the leave channel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_leave(interaction: discord.Interaction, channel: discord.TextChannel):
    config["leave_channel"] = str(channel.id)
    save_config(config)
    await interaction.response.send_message(f"✅ Leave channel set to {channel.mention}.", ephemeral=True)

@bot.tree.command(name="setup-status", description="Set the SA-MP status channel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_status(interaction: discord.Interaction, channel: discord.TextChannel):
    config["status_channel"] = str(channel.id)
    config["status_message"] = None
    save_config(config)
    await interaction.response.send_message(
        f"✅ SA-MP status channel set to {channel.mention}. The Components V2 status message will refresh every 30 seconds.",
        ephemeral=True
    )
    await update_status()

@bot.tree.command(name="setup-samp", description="Set the SA-MP server IP and port.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_samp(interaction: discord.Interaction, ip: str, port: int = 7777):
    if not 1 <= port <= 65535:
        await interaction.response.send_message("❌ Port must be between 1 and 65535.", ephemeral=True)
        return
    config["samp_ip"] = ip.strip()
    config["samp_port"] = port
    save_config(config)
    await interaction.response.send_message(
        f"✅ SA-MP server set to `{config['samp_ip']}:{port}`.",
        ephemeral=True
    )
    await update_status()

@bot.tree.command(name="igwh-message", description="Set the channel where SA-MP whitelist success messages are sent.")
@app_commands.checks.has_permissions(manage_guild=True)
async def igwh_message(interaction: discord.Interaction, channel: discord.TextChannel):
    config["igwh_message_channel"] = str(channel.id)
    save_config(config)
    await interaction.response.send_message(
        f"✅ SA-MP whitelist success messages will be sent only in {channel.mention}.",
        ephemeral=True
    )

@bot.tree.command(name="status", description="Show the current SA-MP server status.")
async def status_command(interaction: discord.Interaction):
    await interaction.response.defer()
    ok, players, maxplayers, names = await get_samp_status()
    await interaction.followup.send(view=make_status_components(ok, players, maxplayers, names))

@bot.tree.command(name="announcement", description="Send a professional Components V2 announcement.")
@app_commands.checks.has_permissions(manage_guild=True)
async def announcement(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    message: str,
):
    # Components V2 announcement: the channel is selected directly in the command,
    # so no /setup-announcement command or saved announcement channel is needed.
    announcement_text = (
        f"# 📢 {title}\n\n"
        f"{message}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "**OCRP • ANNOUNCEMENT**"
    )

    container = discord.ui.Container(
        discord.ui.TextDisplay(announcement_text)
    )
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)

    await channel.send(view=view)
    await interaction.response.send_message(
        f"✅ Announcement sent to {channel.mention}.",
        ephemeral=True,
    )

@bot.tree.command(name="say", description="Send a plain text message to a selected channel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def say_command(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    message: str,
):
    """Send a normal message to any selected channel."""
    try:
        await channel.send(message, allowed_mentions=discord.AllowedMentions.none())
        await interaction.response.send_message(
            f"✅ Message sent to {channel.mention}.",
            ephemeral=True,
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            f"❌ I don't have permission to send messages in {channel.mention}.",
            ephemeral=True,
        )
    except discord.HTTPException as exc:
        print(f"Say command error: {exc}")
        await interaction.response.send_message(
            "❌ Failed to send the message.",
            ephemeral=True,
        )


# /embed create is a Components V2 command. It intentionally does NOT use
# discord.Embed, so the output is a real Discord Components V2 message.
embed_group = app_commands.Group(name="embed", description="Create Components V2 messages.")


@embed_group.command(name="create", description="Create a Components V2 embed-style message.")
@app_commands.checks.has_permissions(manage_guild=True)
async def embed_create(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    title: str,
    description: str,
    footer: str = "OCRP BOT",
):
    """Create an embed-style Components V2 message."""
    # Keep the layout simple and reliable: Components V2 Container + TextDisplay.
    content = f"# {title}\n\n{description}"
    if footer.strip():
        content += f"\n\n━━━━━━━━━━━━━━━━━━━━\n*{footer.strip()}*"

    container = discord.ui.Container(
        discord.ui.TextDisplay(content)
    )
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)

    try:
        await channel.send(view=view)
        await interaction.response.send_message(
            f"✅ Components V2 embed created in {channel.mention}.",
            ephemeral=True,
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            f"❌ I don't have permission to send Components V2 messages in {channel.mention}.",
            ephemeral=True,
        )
    except discord.HTTPException as exc:
        print(f"Components V2 embed create error: {exc}")
        await interaction.response.send_message(
            "❌ Failed to create the Components V2 message.",
            ephemeral=True,
        )


bot.tree.add_command(embed_group)



# ---------------- IN-GAME MODERATION LOGS ----------------

IG_LOG_KEYS = {
    "ban": "ig_ban_log_channel",
    "unban": "ig_unban_log_channel",
    "unban_apply": "ig_unban_apply_channel",
    "jail": "ig_jail_log_channel",
    "warn": "ig_warn_log_channel",
    "cooldown": "ig_cooldown_log_channel",
    "same_ip": "ig_same_ip_whitelist_channel",
}

async def send_ig_log(kind: str, title: str, fields: list[tuple[str, str]], color: discord.Color):
    key = IG_LOG_KEYS[kind]
    channel = channel_from_config(key)
    if channel is None:
        return False

    embed = base_embed(title, color=color)
    for name, value in fields:
        embed.add_field(name=name, value=value, inline=False)
    await channel.send(embed=embed)
    return True

@bot.tree.command(name="setup-ingame-logs", description="Set the channels for SA-MP in-game moderation logs.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_ingame_logs(
    interaction: discord.Interaction,
    ban_log: discord.TextChannel = None,
    unban_log: discord.TextChannel = None,
    unban_apply: discord.TextChannel = None,
    jail_log: discord.TextChannel = None,
    warn_log: discord.TextChannel = None,
    player_cooldown: discord.TextChannel = None,
    same_ip_whitelist: discord.TextChannel = None,
):
    values = {
        "ig_ban_log_channel": ban_log,
        "ig_unban_log_channel": unban_log,
        "ig_unban_apply_channel": unban_apply,
        "ig_jail_log_channel": jail_log,
        "ig_warn_log_channel": warn_log,
        "ig_cooldown_log_channel": player_cooldown,
        "ig_same_ip_whitelist_channel": same_ip_whitelist,
    }
    for key, channel in values.items():
        if channel is not None:
            config[key] = str(channel.id)
    save_config(config)

    configured = []
    for key, channel in values.items():
        if channel is not None:
            configured.append(f"{key.replace('ig_', '').replace('_channel', '').replace('_', ' ').title()}: {channel.mention}")
    text = "\n".join(configured) if configured else "No channels were changed."
    await interaction.response.send_message("✅ **IN-GAME LOG CHANNELS UPDATED**\n" + text, ephemeral=True)


def staff_log_footer(interaction: discord.Interaction):
    return f"Staff: {interaction.user.mention} • ID: {interaction.user.id}"

@bot.tree.command(name="igban", description="Create an SA-MP BAN-LOG entry.")
@app_commands.checks.has_permissions(manage_guild=True)
async def igban(interaction: discord.Interaction, player: str, reason: str, duration: str = "Permanent"):
    ok = await send_ig_log("ban", "🛑 • || BAN-LOG", [
        ("👤 Player", f"`{player}`"),
        ("⏱️ Duration", duration),
        ("📝 Reason", reason),
        ("🛡️ Staff", staff_log_footer(interaction)),
    ], discord.Color.red())
    if not ok:
        await interaction.response.send_message("❌ BAN-LOG channel is not configured. Use `/setup-ingame-logs`.", ephemeral=True)
        return
    await interaction.response.send_message("✅ BAN-LOG recorded.", ephemeral=True)

@bot.tree.command(name="igunban", description="Create an SA-MP UNBAN-LOG entry.")
@app_commands.checks.has_permissions(manage_guild=True)
async def igunban(interaction: discord.Interaction, player: str, reason: str = "Unbanned"):
    ok = await send_ig_log("unban", "🛑 • || UNBAN-LOG", [
        ("👤 Player", f"`{player}`"),
        ("📝 Reason", reason),
        ("🛡️ Staff", staff_log_footer(interaction)),
    ], discord.Color.green())
    if not ok:
        await interaction.response.send_message("❌ UNBAN-LOG channel is not configured. Use `/setup-ingame-logs`.", ephemeral=True)
        return
    await interaction.response.send_message("✅ UNBAN-LOG recorded.", ephemeral=True)

@bot.tree.command(name="unban-apply", description="Create an SA-MP UNBAN-APPLY entry.")
@app_commands.checks.has_permissions(manage_guild=True)
async def unban_apply(interaction: discord.Interaction, player: str, reason: str):
    ok = await send_ig_log("unban_apply", "🛑 • || UNBAN-APPLY", [
        ("👤 Player", f"`{player}`"),
        ("📝 Appeal / Reason", reason),
        ("📨 Submitted by", staff_log_footer(interaction)),
    ], discord.Color.orange())
    if not ok:
        await interaction.response.send_message("❌ UNBAN-APPLY channel is not configured. Use `/setup-ingame-logs`.", ephemeral=True)
        return
    await interaction.response.send_message("✅ UNBAN-APPLY recorded.", ephemeral=True)

@bot.tree.command(name="igjail", description="Create an SA-MP JAIL-LOG entry.")
@app_commands.checks.has_permissions(manage_guild=True)
async def igjail(interaction: discord.Interaction, player: str, reason: str, duration: str):
    ok = await send_ig_log("jail", "🛑 • || JAIL-LOG", [
        ("👤 Player", f"`{player}`"),
        ("⏱️ Duration", duration),
        ("📝 Reason", reason),
        ("🛡️ Staff", staff_log_footer(interaction)),
    ], discord.Color.orange())
    if not ok:
        await interaction.response.send_message("❌ JAIL-LOG channel is not configured. Use `/setup-ingame-logs`.", ephemeral=True)
        return
    await interaction.response.send_message("✅ JAIL-LOG recorded.", ephemeral=True)

@bot.tree.command(name="igwarn", description="Create an SA-MP warning log entry.")
@app_commands.checks.has_permissions(manage_guild=True)
async def igwarn(interaction: discord.Interaction, player: str, reason: str):
    ok = await send_ig_log("warn", "⚠️ • || FRP-WARN", [
        ("👤 Player", f"`{player}`"),
        ("📝 Reason", reason),
        ("🛡️ Staff", staff_log_footer(interaction)),
    ], discord.Color.yellow())
    if not ok:
        await interaction.response.send_message("❌ WARN log channel is not configured. Use `/setup-ingame-logs`.", ephemeral=True)
        return
    await interaction.response.send_message("✅ Warning log recorded.", ephemeral=True)

@bot.tree.command(name="igcooldown", description="Create a PLAYER-COOL-DOWN log entry.")
@app_commands.checks.has_permissions(manage_guild=True)
async def igcooldown(interaction: discord.Interaction, player: str, reason: str, duration: str):
    ok = await send_ig_log("cooldown", "🔴 • || PLAYER-COOL-DOWN", [
        ("👤 Player", f"`{player}`"),
        ("⏱️ Duration", duration),
        ("📝 Reason", reason),
        ("🛡️ Staff", staff_log_footer(interaction)),
    ], discord.Color.red())
    if not ok:
        await interaction.response.send_message("❌ PLAYER-COOL-DOWN channel is not configured. Use `/setup-ingame-logs`.", ephemeral=True)
        return
    await interaction.response.send_message("✅ Player cooldown recorded.", ephemeral=True)

@bot.tree.command(name="same-ip-whitelist", description="Create a SAME-IP-WHITELIST log entry.")
@app_commands.checks.has_permissions(manage_guild=True)
async def same_ip_whitelist(interaction: discord.Interaction, player: str, linked_account: str, note: str = ""):
    ok = await send_ig_log("same_ip", "2️⃣ • || SAME-IP-WHITELIST", [
        ("👤 Player", f"`{player}`"),
        ("🔗 Linked Account", f"`{linked_account}`"),
        ("📝 Note", note or "No note provided."),
        ("🛡️ Staff", staff_log_footer(interaction)),
    ], discord.Color.blurple())
    if not ok:
        await interaction.response.send_message("❌ SAME-IP-WHITELIST channel is not configured. Use `/setup-ingame-logs`.", ephemeral=True)
        return
    await interaction.response.send_message("✅ SAME-IP-WHITELIST recorded.", ephemeral=True)

@bot.tree.command(name="config", description="Show the current OCRP BOT configuration.")
@app_commands.checks.has_permissions(manage_guild=True)
async def config_command(interaction: discord.Interaction):
    def mention(key):
        cid = config.get(key)
        return f"<#{cid}>" if cid else "Not set"

    samp = f"{config.get('samp_ip') or 'Not set'}:{config.get('samp_port', 7777)}"
    embed = base_embed("⚙️ OCRP BOT CONFIGURATION", color=discord.Color.blurple())
    embed.add_field(name="👋 Welcome", value=mention("welcome_channel"), inline=True)
    embed.add_field(name="🚪 Leave", value=mention("leave_channel"), inline=True)
    embed.add_field(name="🎮 SA-MP Status", value=mention("status_channel"), inline=True)
    embed.add_field(name="📋 Whitelist Panel", value=mention("whitelist_channel"), inline=True)
    embed.add_field(name="🛡️ Whitelist Review", value=mention("whitelist_review_channel"), inline=True)
    embed.add_field(name="📣 Whitelist Acceptance", value=mention("whitelist_acceptance_channel"), inline=True)
    embed.add_field(name="🤖 SA-MP Auto Whitelist", value=mention("samp_whitelist_channel") if config.get("samp_whitelist_channel") else (f"<#{SAMP_WHITELIST_CHANNEL_ID}>" if SAMP_WHITELIST_CHANNEL_ID else "Not set"), inline=True)
    embed.add_field(name="📨 IG Whitelist Message", value=mention("igwh_message_channel"), inline=True)
    embed.add_field(name="🛑 BAN-LOG", value=mention("ig_ban_log_channel"), inline=True)
    embed.add_field(name="🛑 UNBAN-LOG", value=mention("ig_unban_log_channel"), inline=True)
    embed.add_field(name="🛑 UNBAN-APPLY", value=mention("ig_unban_apply_channel"), inline=True)
    embed.add_field(name="🛑 JAIL-LOG", value=mention("ig_jail_log_channel"), inline=True)
    embed.add_field(name="⚠️ FRP-WARN", value=mention("ig_warn_log_channel"), inline=True)
    embed.add_field(name="🔴 PLAYER-COOL-DOWN", value=mention("ig_cooldown_log_channel"), inline=True)
    embed.add_field(name="2️⃣ SAME-IP-WHITELIST", value=mention("ig_same_ip_whitelist_channel"), inline=True)
    embed.add_field(name="🌐 SA-MP Server", value=f"`{samp}`", inline=True)
    embed.add_field(name="🔄 Refresh", value="**30 seconds**", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

async def command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ You need **Manage Server** permission to use this command."
    else:
        print(f"Command error: {error}")
        msg = "❌ Something went wrong while using this command."

    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)

for cmd in list(bot.tree.get_commands()):
    pass

bot.tree.on_error = command_error


class WhitelistContinueView(discord.ui.View):
    def __init__(self, first_answers):
        super().__init__(timeout=300)
        self.first_answers = first_answers

    @discord.ui.button(
        label="CONTINUE TO QUESTIONS 6–8",
        style=discord.ButtonStyle.primary,
        emoji="➡️"
    )
    async def continue_application(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_modal(WhitelistStepTwo(self.first_answers))
            self.stop()
        except (discord.HTTPException, ValueError) as exc:
            print(f"Whitelist step-two modal error: {exc}")
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ I couldn't open the next whitelist form. Please try the whitelist button again.",
                    ephemeral=True
                )


class WhitelistStepOne(discord.ui.Modal, title="OCRP WHITELIST APPLICATION • 1/2"):
    occ_name = discord.ui.TextInput(label="1. What's your OCC name?", placeholder="Enter your OCC / real name", max_length=100, required=True)
    age = discord.ui.TextInput(label="2. How old are you?", placeholder="Enter your age", max_length=3, required=True)
    metagaming = discord.ui.TextInput(label="3. What is Meta Gaming?", placeholder="Explain in your own words", style=discord.TextStyle.paragraph, max_length=1000, required=True)
    powergaming = discord.ui.TextInput(label="4. What is Power Gaming?", placeholder="Explain in your own words", style=discord.TextStyle.paragraph, max_length=1000, required=True)
    rdm = discord.ui.TextInput(label="5. What is RDM?", placeholder="Explain in your own words", style=discord.TextStyle.paragraph, max_length=1000, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        answers = {
            "occ_name": str(self.occ_name),
            "age": str(self.age),
            "metagaming": str(self.metagaming),
            "powergaming": str(self.powergaming),
            "rdm": str(self.rdm)
        }

        # Discord does not reliably allow opening another modal directly
        # from a modal-submit interaction. Show a Continue button instead.
        await interaction.response.send_message(
            "✅ Part 1 saved! Tap the button below to continue with questions 6–8.",
            view=WhitelistContinueView(answers),
            ephemeral=True
        )


class WhitelistReviewView(discord.ui.View):
    def __init__(self, applicant_id: int):
        super().__init__(timeout=None)
        self.applicant_id = int(applicant_id)

        accept = discord.ui.Button(
            label="ACCEPT",
            style=discord.ButtonStyle.success,
            emoji="✅",
            custom_id=f"ocrp_whitelist_accept_{self.applicant_id}"
        )
        reject = discord.ui.Button(
            label="DECLINE",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            custom_id=f"ocrp_whitelist_decline_{self.applicant_id}"
        )

        accept.callback = self.accept_callback
        reject.callback = self.decline_callback
        self.add_item(accept)
        self.add_item(reject)

    async def accept_callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ You need **Manage Server** permission to accept whitelist applications.",
                ephemeral=True
            )
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ This can only be used in a server.", ephemeral=True)
            return

        role = interaction.guild.get_role(WHITELIST_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                f"❌ Whitelist role `{WHITELIST_ROLE_ID}` was not found in this server.",
                ephemeral=True
            )
            return

        member = interaction.guild.get_member(self.applicant_id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(self.applicant_id)
            except discord.NotFound:
                await interaction.response.send_message(
                    "❌ The applicant is no longer in the server.",
                    ephemeral=True
                )
                return
            except discord.HTTPException:
                await interaction.response.send_message(
                    "❌ I couldn't find the applicant right now.",
                    ephemeral=True
                )
                return

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "❌ I cannot assign this role. Move the whitelist role **below OCRP BOT's highest role** in Server Settings → Roles.",
                ephemeral=True
            )
            return

        try:
            await member.add_roles(
                role,
                reason=f"OCRP whitelist accepted by {interaction.user} ({interaction.user.id})"
            )

            acceptance_channel = channel_from_config("whitelist_acceptance_channel")
            if acceptance_channel is not None:
                try:
                    await acceptance_channel.send(f"THE {member.mention} GOT DC WHITELIST")
                except discord.Forbidden:
                    pass


            embed = interaction.message.embeds[0] if interaction.message.embeds else base_embed(
                "📋 OCRP WHITELIST APPLICATION"
            )
            embed.color = discord.Color.green()
            embed.add_field(
                name="✅ APPLICATION ACCEPTED",
                value=f"Accepted by {interaction.user.mention}\nRole assigned: {role.mention}",
                inline=False
            )

            for item in self.children:
                item.disabled = True

            await interaction.response.edit_message(embed=embed, view=self)
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Discord denied the role assignment. Make sure OCRP BOT has **Manage Roles** and its highest role is above the whitelist role.",
                ephemeral=True
            )
        except discord.HTTPException as exc:
            print(f"Whitelist role assignment error: {exc}")
            await interaction.response.send_message(
                "❌ Failed to assign the whitelist role.",
                ephemeral=True
            )

    async def decline_callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ You need **Manage Server** permission to decline whitelist applications.",
                ephemeral=True
            )
            return

        embed = interaction.message.embeds[0] if interaction.message.embeds else base_embed(
            "📋 OCRP WHITELIST APPLICATION"
        )
        embed.color = discord.Color.red()
        embed.add_field(
            name="❌ APPLICATION DECLINED",
            value=f"Declined by {interaction.user.mention}",
            inline=False
        )

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)


class WhitelistStepTwo(discord.ui.Modal, title="OCRP WHITELIST APPLICATION • 2/2"):
    vdm = discord.ui.TextInput(label="6. What is VDM?", placeholder="Explain in your own words", style=discord.TextStyle.paragraph, max_length=1000, required=True)
    occ = discord.ui.TextInput(label="7. What is OCC?", placeholder="Explain in your own words", style=discord.TextStyle.paragraph, max_length=1000, required=True)
    agree = discord.ui.TextInput(label="8. Agree to rules and terms? (YES/NO)", placeholder="Type YES or NO", max_length=3, required=True)

    def __init__(self, first_answers):
        super().__init__()
        self.first_answers = first_answers

    async def on_submit(self, interaction: discord.Interaction):
        agreement = str(self.agree).strip().lower()
        if agreement not in {"yes", "no"}:
            await interaction.response.send_message("❌ For question 8, please answer **YES** or **NO**.", ephemeral=True)
            return
        review_channel = channel_from_config("whitelist_review_channel")
        if not review_channel:
            await interaction.response.send_message("❌ Whitelist review channel is not configured. Ask an administrator to use `/setup-whitelist-review`.", ephemeral=True)
            return
        embed = base_embed("📋 OCRP WHITELIST APPLICATION", f"Application submitted by {interaction.user.mention}", discord.Color.blurple())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="👤 Applicant", value=interaction.user.mention, inline=False)
        embed.add_field(name="1️⃣ OCC Name", value=self.first_answers["occ_name"], inline=False)
        embed.add_field(name="2️⃣ Age", value=self.first_answers["age"], inline=True)
        embed.add_field(name="3️⃣ Meta Gaming", value=self.first_answers["metagaming"], inline=False)
        embed.add_field(name="4️⃣ Power Gaming", value=self.first_answers["powergaming"], inline=False)
        embed.add_field(name="5️⃣ RDM", value=self.first_answers["rdm"], inline=False)
        embed.add_field(name="6️⃣ VDM", value=str(self.vdm), inline=False)
        embed.add_field(name="7️⃣ OCC", value=str(self.occ), inline=False)
        embed.add_field(name="8️⃣ Rules & Terms", value="✅ YES" if agreement == "yes" else "❌ NO", inline=False)
        embed.add_field(name="🆔 User ID", value=str(interaction.user.id), inline=False)
        embed.set_footer(text="OCRP BOT • Whitelist Application")
        try:
            await review_channel.send(embed=embed, view=WhitelistReviewView(interaction.user.id))
            await interaction.response.send_message("✅ **Whitelist application submitted successfully!**\nYour application has been sent to the staff team for review.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to send applications in the review channel.", ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message("❌ Failed to submit your application. Please try again later.", ephemeral=True)


class WhitelistView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="APPLY FOR WHITELIST", style=discord.ButtonStyle.success, emoji="📋", custom_id="ocrp_whitelist_apply")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WhitelistStepOne())


@bot.tree.command(name="setup-samp-whitelist", description="Set the channel where players send their SA-MP in-game name for automatic whitelist.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_samp_whitelist(interaction: discord.Interaction, channel: discord.TextChannel):
    config["samp_whitelist_channel"] = str(channel.id)
    save_config(config)
    await interaction.response.send_message(
        f"✅ SA-MP auto-whitelist channel set to {channel.mention}.\nSend only your in-game name there to trigger the whitelist process.",
        ephemeral=True
    )


@bot.tree.command(name="setup-whitelist", description="Set the whitelist application channel and post the panel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_whitelist(interaction: discord.Interaction, channel: discord.TextChannel):
    config["whitelist_channel"] = str(channel.id)
    save_config(config)
    embed = base_embed("📋 OCRP WHITELIST", "**Whitelist applications are now open.**\n\nClick the button below and answer all 8 questions honestly.", discord.Color.blurple())
    embed.add_field(name="📝 Questions", value="1. What's your OCC name?\n2. How old are you?\n3. What is Meta Gaming?\n4. What is Power Gaming?\n5. What is RDM?\n6. What is VDM?\n7. What is OCC?\n8. Do you agree to our rules and terms? (YES/NO)", inline=False)
    embed.set_footer(text="OCRP BOT • Whitelist System")
    try:
        await channel.send(embed=embed, view=WhitelistView())
        await interaction.response.send_message(f"✅ Whitelist panel posted in {channel.mention}.", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I cannot send messages in that channel.", ephemeral=True)


@bot.tree.command(name="setup-whitelist-acceptance", description="Set the channel for whitelist acceptance messages.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_whitelist_acceptance(interaction: discord.Interaction, channel: discord.TextChannel):
    config["whitelist_acceptance_channel"] = str(channel.id)
    save_config(config)
    await interaction.response.send_message(
        f"✅ Whitelist acceptance channel set to {channel.mention}.",
        ephemeral=True
    )


@bot.tree.command(name="setup-whitelist-review", description="Set the staff channel for whitelist applications.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setup_whitelist_review(interaction: discord.Interaction, channel: discord.TextChannel):
    config["whitelist_review_channel"] = str(channel.id)
    save_config(config)
    await interaction.response.send_message(f"✅ Whitelist review channel set to {channel.mention}.", ephemeral=True)

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Put your bot token in the .env file.")

bot.run(TOKEN)
