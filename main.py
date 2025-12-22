import sys
import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import json
import asyncio
import shutil
import re
from collections import defaultdict

def resolve_reference(expression: str, data1: dict, self_planet: dict = None):
    if expression.startswith("@"):
        expression = "ref/" + expression[1:]

    if not expression.startswith("ref/"):
        return try_cast(expression)

    expr = expression[4:]
    match = re.match(r"([A-Za-z0-9\-\_]+)\.([A-Za-z0-9_]+)(.*)", expr)
    if not match:
        return expression

    index, field, rest = match.groups()

    # Handle @self keyword
    if index.lower() == "self":
        if not self_planet:
            return "[MissingSelf]"
        planet = self_planet
    else:
        if index not in data1:
            return f"[MissingRef:{index}]"
        planet = data1[index]

    if field not in planet:
        return f"[MissingField:{index}.{field}]"

    base_value = planet[field]
    rest = rest.strip()
    if rest.startswith("+"):
        parts = re.findall(r"\+ *'([^']*)'|\+ *\"([^\"]*)\"", rest)
        for single_quote, double_quote in parts:
            extra = single_quote or double_quote
            base_value = f"{base_value}{extra}"

    return try_cast(str(base_value))



#----GET GRADE FUNCTION MODULARIZED IN BUILD 1.26-----
def get_user_grade(user_id: str):
    target_id = str(user_id)
    if target_id not in allowedIds:
        return 50.0, 0
    entry = allowedIds[target_id]
    if isinstance(entry, bool):
        entry = {"Contributions": 0, "Grade": 100.0}
        allowedIds[target_id] = entry
        save_enrolled(allowedIds)
    grade = float(entry.get("Grade", 100.0))
    contrib = int(entry.get("Contributions", 0))
    return grade, contrib

#----SEARCH FUNCTION MODULARIZED IN BUILD 1.24------

def conditionSearch(msg, data, try_cast):
    tokens = re.findall(r'\((.*?)\)|\b(and|or)\b', msg, flags=re.IGNORECASE)
    if not tokens:
        return {"error": "⚠️ No valid search conditions found."}

    logic_sequence = []
    for token in tokens:
        cond = token[0] if token[0] else token[1]
        logic_sequence.append(cond.strip())

    operators = {
        "==": lambda a, b: str(a).lower() == str(b).lower() if isinstance(a, str) or isinstance(b, str) else a == b,
        "=":  lambda a, b: str(a).lower() == str(b).lower() if isinstance(a, str) or isinstance(b, str) else a == b,
        "!=": lambda a, b: str(a).lower() != str(b).lower() if isinstance(a, str) or isinstance(b, str) else a != b,
        "~=": lambda a, b: str(a).lower() != str(b).lower() if isinstance(a, str) or isinstance(b, str) else a != b,
        "<":  lambda a, b: a < b,
        ">":  lambda a, b: a > b,
        "<=": lambda a, b: a <= b,
        "=<": lambda a, b: a <= b,
        ">=": lambda a, b: a >= b,
        "=>": lambda a, b: a >= b,
        "<>": lambda a, b: a != b,
        "is": lambda a, b: str(a).lower() == str(b).lower() if isinstance(a, str) or isinstance(b, str) else a == b,
        "are": lambda a, b: str(a).lower() == str(b).lower() if isinstance(a, str) or isinstance(b, str) else a == b,
        "arent": lambda a, b: str(a).lower() != str(b).lower() if isinstance(a, str) or isinstance(b, str) else a != b,
        "isnt": lambda a, b: str(a).lower() != str(b).lower() if isinstance(a, str) or isinstance(b, str) else a != b,
        "over": lambda a, b: a > b,
        "under": lambda a, b: a < b,
        "has": lambda a, b: str(b).lower() in str(a).lower(),
        "lacks": lambda a, b: str(b).lower() not in str(a).lower(),
        "@": lambda a, b: str(b).lower() in str(a).lower(),
        "#": lambda a, b: str(b).lower() not in str(a).lower(),
    }

    parsed_conditions = []
    planet_count_condition = None

    for cond in logic_sequence:
        if cond.lower() in ["and", "or"]:
            parsed_conditions.append(cond.lower())
            continue

        parts = cond.split()
        if len(parts) < 3:
            return {"error": f"⚠️ Invalid condition format: `{cond}`"}

        field = parts[0]
        op = parts[1]
        val = " ".join(parts[2:])

        op = op.lower()
        if op not in operators:
            return {"error": f"⚠️ Invalid operator `{op}` in condition `{cond}`"}

        val = try_cast(val)

        if field.lower() == "planetcount":
            try:
                val = int(val)
            except Exception:
                return {"error": f"⚠️ Invalid number for PlanetCount: `{val}`"}
            planet_count_condition = (field.lower(), op, val)
        else:
            parsed_conditions.append((field.lower(), op, val))

    planet_counts = defaultdict(int)
    for p in data.values():
        if p.get("IsMoon"):
            continue
        index = p.get("Index")
        if not index:
            continue
        parts = str(index).split("-")
        if len(parts) < 2:
            continue
        sid = p.get("StarID") or try_cast(parts[0])
        if sid is not None:
            planet_counts[str(sid)] += 1

    matches = []
    for index, planet in data.items():
        normalized_planet = {k.lower(): v for k, v in planet.items()}

        if "starid" not in normalized_planet:
            normalized_planet["starid"] = try_cast(str(index).split("-")[0])
        if "planetid" not in normalized_planet:
            normalized_planet["planetid"] = try_cast(str(index).split("-")[1])

        sid = normalized_planet.get("starid")
        if not normalized_planet.get("ismoon", False):
            count = planet_counts.get(str(sid), planet_counts.get(int(sid), 0))
            normalized_planet["planetcount"] = count
            planet["PlanetCount"] = count
        else:
            normalized_planet["planetcount"] = 0

        results, logic_ops = [], []

        for cond in parsed_conditions:
            if isinstance(cond, str) and cond in ["and", "or"]:
                logic_ops.append(cond)
                continue

            field, op, val = cond
            planet_val = normalized_planet.get(field)
            try:
                res = operators[op](planet_val, val)
            except Exception:
                res = False
            results.append(res)

        if results:
            combined = results[0]
            for i in range(1, len(results)):
                op = logic_ops[i - 1] if i - 1 < len(logic_ops) else "and"
                combined = (combined and results[i]) if op == "and" else (combined or results[i])
            if not combined:
                continue

        if planet_count_condition:
            _, op, val = planet_count_condition
            if not operators[op](normalized_planet["planetcount"], val):
                continue

        matches.append((index, planet))

    return {
        "matches": matches,
        "parsed_conditions": [c for c in parsed_conditions if not isinstance(c, str)],
        "planet_count_condition": planet_count_condition,
    }


#-----------------------


load_dotenv()
token = os.getenv("DISCORD_TOKEN")
ALLOWED_GUILD_ID = int(os.getenv("ALLOWED_GUILD_ID"))

def in_allowed_guild():
    async def predicate(ctx):
        if ctx.guild is None or ctx.guild.id != ALLOWED_GUILD_ID:
            await ctx.reply("❌ This bot can only be used in the official server.")
            return False
        return True
    return commands.check(predicate)

def is_allowed_user():
    async def predicate(ctx):
        user_id = str(ctx.author.id)
        if user_id not in allowedIds:
            await ctx.reply(f"{ctx.author.mention} ❌ You are not entitled to use this bot.\n"
                           f"You may submit a permission form to get access in #get-access !")
            return False
        return True
    return commands.check(predicate)

#------------------------------------

#-----------UHH BACKUP STUFF ETC------
def make_daily_backup(overwrite: bool = False):
    today = datetime.now().strftime("%Y-%m-%d")
    backup_dir = os.path.join("backups", today)
    if os.path.exists(backup_dir) and not overwrite:
        print(f"⚠️ Backup for {today} already exists. Skipping (use overwrite=True to replace).")
        return
    os.makedirs(backup_dir, exist_ok=True)
    files_to_backup = ["data.json", "allowedIds.json"]
    for file in files_to_backup:
        if os.path.exists(file):
            dest = os.path.join(backup_dir, file)
            shutil.copy2(file, dest)
            print(f"Backed up {file} > {dest}")
    print(f"Daily backup completed for {today}{' (overwritten)' if overwrite else ''}.")

def cleanup_old_backups(days_to_keep=15):
    backup_root = "backups"
    now = datetime.now()

    if not os.path.exists(backup_root):
        return

    for folder in os.listdir(backup_root):
        path = os.path.join(backup_root, folder)
        try:
            folder_date = datetime.strptime(folder, "%Y-%m-%d")
            if (now - folder_date).days > days_to_keep:
                shutil.rmtree(path)
                print(f"Deleted old backup: {path}")
        except ValueError:
            continue

async def backup_loop():
    while True:
        make_daily_backup()
        cleanup_old_backups(15) # wait fortnite days until cleanup 😂
        print("Next backup in 24 hours")
        await asyncio.sleep(24 * 60 * 60) # wait 24 hours llolll

#------ OTHER STUFF

def try_cast(value: str):
    if value != str(value):
        return value
    val_lower = value.strip().lower()

    if val_lower in ["true","True", "yes", "on", "enabled", "Yes", "YES", "devious"]:
        return True
    if val_lower in ["false","False", "no", "off", "disabled", "No", "NO", "pandemonium"]:
        return False

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value.strip()


def load_data():
    try:
        with open("data.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

def load_ids():
    try:
        with open("allowedIds.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_enrolled(allowedIds):
    with open("allowedIds.json", "w") as f:
        json.dump(allowedIds, f, indent=4)

# ----------------------------

data = {}
allowedIds = {}

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix='x!', intents=intents, help_command=None)

# ----------------------------

@bot.event
async def on_ready():
    global data, allowedIds
    data = load_data()
    allowedIds = load_ids()
    bot.status = discord.Status.idle
    bot.activity = discord.Activity(type=discord.ActivityType.listening, name="x!help")
    make_daily_backup()
    cleanup_old_backups(15)

    bot.loop.create_task(backup_loop())

    print(f"Logged in as {bot.user}")

@bot.event
async def on_command_error(ctx, error):
    print(f"⚠️⚠️⚠️⚠️ Command error: {error}")
    await ctx.reply(f"❌❌❌ Error: {error} ❌❌❌")

from datetime import datetime, timedelta, UTC

@bot.event
async def on_member_join(member: discord.Member):
    now = datetime.now(UTC)

    account_age = now - member.created_at

    min_age = timedelta(days=30)

    if account_age < min_age:
        try:
            try:
                await member.send(
                    f"❌ Your account is too new to join **{member.guild.name}**.\n"
                    f"Accounts must be at least 30 days old. Please try again later."
                )
            except discord.Forbidden:
                pass

            await member.ban(reason="Account younger than 30 days", delete_message_days=0)
            print(f"[AutoBan] Banned {member} - account age {account_age.days} days")

            log_channel = discord.utils.get(member.guild.text_channels, name="discord-mod-stuff")
            if log_channel:
                await log_channel.send(
                    f"💥 **Auto-ban:** {member.mention} ({member}) banned for new account "
                    f"({account_age.days} days old)"
                )

        except Exception as e:
            print(f"[AutoBan Error] Failed to ban {member}: {e}")


@bot.check
async def globally_block_dms(ctx):
    return ctx.guild is not None

ALLOWED_CHANNEL_ID = 1424170884460970144

@bot.check
async def only_in_allowed_channel(ctx):
    if ctx.guild is None:
        return False
    adminRole = ctx.guild.get_role(adminRoleId)
    if ctx.channel.id != ALLOWED_CHANNEL_ID and ctx.channel.id != 1426586804600967298 and adminRole not in ctx.author.roles:
        await ctx.reply(f"❌ Commands can only be used in <#{ALLOWED_CHANNEL_ID}> and <#{1426586804600967298}> (for Russians).")
        return False

    return True

@bot.event
async def on_message_delete(message):
    if message.channel.id != 1424170884460970144:
        return
    if message.author.bot:
        return
    if message.author.id == 1104487278308495492:
        return
    content = message.content or "*[no text - possibly embed/image]*"
    resend_text = (
        f"🧠 Message by **{message.author}** was deleted:\n"
        f"```{content}```\n"
        f"User ID: `{message.author.id}`\n"
        f"Mention: <@{message.author.id}>\n"
    )
    await message.channel.send(resend_text)

# ----------------------------

async def checkAllowed(id, ctx):
    if str(id) in allowedIds:
        return True
    else:
        await ctx.reply(f"{ctx.author.mention} You are not entitled to use this bot.\nYou may submit a permission form to use the bot in in <#{1424161875389579314}> !")
        return False

adminRoleId:int = 1424503991349547138

# ----------------------------

@bot.command()
@in_allowed_guild()
@is_allowed_user()
async def add(ctx, *, msg):
    planet_entries = msg.split("|")
    added, skipped = [], []

    for entry in planet_entries:
        args = entry.strip().split()
        if not args:
            continue

        index = args[0]
        parts = index.split("-")
        if len(parts) < 2:
            await ctx.reply(f"⚠️ Invalid ID `{index}` - must be in format `0000-1` or `0000-1-1`.")
            continue

        starId = try_cast(parts[0])
        planetId = try_cast(parts[1])
        isMoon = len(parts) == 3

        if index in data:
            skipped.append(index)
            continue

        name = try_cast(args[1]) if len(args) > 1 else f"Unnamed {index}"

        data[index] = {
            "Index": index,
            "Name": name,
            "StarID": starId,
            "PlanetID": planetId,
            "IsMoon": isMoon
        }

        added.append(f"{index} ({name})")

    if added:
        save_data(data)

    reply = ""
    if added:
        reply += f"✅ Added {len(added)} planet(s): " + ", ".join(added) + "\n"
    if skipped:
        reply += f"⚠️ Skipped {len(skipped)} existing planet(s): " + ", ".join(skipped)
    await ctx.reply(reply or "⚠️ No valid planets were added.")

@bot.command()
async def get(ctx, index: str):
    planet = data.get(index)
    if not planet:
        await ctx.reply(f"❌ No planet found with index `{index}`.")
        return

    pretty = json.dumps(planet, indent=4)
    await ctx.reply(f"```\n{pretty}\n```")

@bot.command()
@is_allowed_user()
@in_allowed_guild()
async def rem(ctx, *, msg):
    user_id = ctx.author.id
    planetsToRemove = msg.split()
    warnings = []
    removedCount = 0
    total_contribution_loss = 0
    total_grade_loss = 0
    for index in planetsToRemove:
        planet = data.get(index)
        if not planet:
            warnings.append(f"⚠️ No planet found with index `{index}`, skipping.")
            continue
        fields_count = len(planet)
        contribution_loss = max(fields_count - 5, 0)
        grade_loss = max((fields_count - 5) // 2, 0)
        total_contribution_loss += contribution_loss
        total_grade_loss += grade_loss
        del data[index]
        removedCount += 1
    save_data(data)
    reply_text = f"✅ {removedCount} planet(s) successfully removed."
    if warnings:
        reply_text += "\n" + "\n".join(warnings)
    await ctx.reply(reply_text)
    user_info = allowedIds.get(str(user_id))
    if not user_info:
        return
    user_info["Contributions"] = max(user_info.get("Contributions", 0) - total_contribution_loss, 0)
    user_info["Grade"] = max(user_info.get("Grade", 0) - total_grade_loss, 0)


@bot.command()
@in_allowed_guild()
async def leaderboard(ctx, page: int = 1):
    if not isinstance(allowedIds, dict) or not allowedIds:
        await ctx.reply("❌ No users found in leaderboard data.")
        return
    sorted_users = sorted(
        allowedIds.items(),
        key=lambda item: (
            item[1].get("Contributions", 0),
            item[1].get("Grade", 50.0)
        ),
    reverse=True
    )

    users_per_page = 5
    total_pages = (len(sorted_users) + users_per_page - 1) // users_per_page

    if page < 1 or page > total_pages:
        await ctx.reply(f"⚠️ Invalid page number. There are {total_pages} page(s) available.")
        return

    start_idx = (page - 1) * users_per_page
    end_idx = start_idx + users_per_page
    page_users = sorted_users[start_idx:end_idx]

    leaderboard_lines = []
    for rank, (user_id, info) in enumerate(page_users, start=start_idx + 1):
        member = ctx.guild.get_member(int(user_id))
        username = member.name if member else f"User {user_id}"

        if rank == 1:
            medal = "👑"
        elif rank == 2:
            medal = "🥈"
        elif rank == 3:
            medal = "🥉"
        else:
            medal = ""
        leaderboard_lines.append(
            f"{rank}: {medal} {username} - Contributions: {info['Contributions']}, Grade {info['Grade']}"
        )

    await ctx.reply("\n".join(leaderboard_lines))

@bot.command()
@in_allowed_guild()
@is_allowed_user()
async def edit(ctx, *, msg: str):
    user_id = str(ctx.author.id)

    planet_edits = [chunk.strip() for chunk in msg.split("|") if chunk.strip()]
    if not planet_edits:
        await ctx.reply("⚠️ Usage: `x!edit <PlanetID> (Field = Value)` or multiple like `x!edit 0001-1 (...) | 0001-2 (...)`")
        return

    all_replies = []
    total_valid_edits = 0
    total_duplicates = 0
    unchanged_attempts = 0

    warnless_fields = ["Hematite","Malachite","Petroleum","Coal","Gold","Sulfur","Cerussite","Lime","Quartz","Saltpeter","Bauxite","Tektite",
                       "Tag", "Life", "Note", "Oceans", "Atmosphere", "Tectonics", "Moons", "Name", "Trees"]

    for edit_chunk in planet_edits:
        match = re.match(r"^(\S+)\s+(.+)$", edit_chunk.strip())
        if not match:
            all_replies.append(f"⚠️ Invalid syntax: `{edit_chunk}` - use `<PlanetID> (Field = Value)`")
            continue

        index, rest = match.groups()
        planet = data.get(index)

        if not planet:
            parts = index.split("-")
            if len(parts) < 2:
                all_replies.append(f"❌ Invalid index `{index}`. Format should be like `0000-1`.")
                continue

            planet = {
                "Index": index,
                "StarID": try_cast(parts[0]),
                "PlanetID": try_cast(parts[1]),
                "IsMoon": len(parts) == 3,
                "Name": "Unnamed"
            }
            data[index] = planet
            all_replies.append(f"⚠️ Planet doesn't exist, creating: `{index}`")

        edits = re.findall(r'\(([^()]+)\)', rest)
        if not edits:
            all_replies.append(f"⚠️ No valid edits found for `{index}`. Use parentheses like `(Field = Value)`.")
            continue

        protected_fields = {"StarID", "PlanetID", "PlanetCount", "Index", "IsMoon"}
        changed = []
        warns = []
        seen_fields = set()
        duplicate_fields = 0
        valid_edits = 0

        for edit in edits:
            parts = edit.strip().split("=", 1)
            if len(parts) != 2:
                warns.append(f"⚠️ Invalid edit format: `{edit}`. Use `(Field = Value)`.")
                continue

            key = parts[0].strip()
            raw_value = parts[1].strip().strip("'\"")
            key = key.capitalize()

            if key in seen_fields:
                duplicate_fields += 1
                continue
            seen_fields.add(key)

            if key in protected_fields:
                warns.append(f"❌ `{key}` is a protected field and cannot be modified.")
                continue

            value = resolve_reference(raw_value, data, self_planet=planet)

            if key in planet:
                old_value = planet[key]
                if raw_value == "/DEL":
                    del planet[key]
                    changed.append(f"🗑️ `{key}` deleted (was `{old_value}`)")
                    valid_edits += 1
                else:
                    if old_value == value:
                        unchanged_attempts += 1  # <-- penalize for trying to set the same value
                        warns.append(f"⚠️ `{key}` already has the value `{value}` - grade penalized.")
                    else:
                        planet[key] = value
                        changed.append(f"✏️ `{key}`: `{old_value}` → `{value}`")
                        valid_edits += 1
            else:
                if raw_value == "/DEL":
                    warns.append(f"⚠️ Tried to delete nonexistent field `{key}` - skipped.")
                else:
                    planet[key] = value
                    if key not in warnless_fields:
                        warns.append(f"⚠️ New custom field `{key}` created with value `{value}`")
                    valid_edits += 1

        data[index] = planet
        save_data(data)

        total_valid_edits += valid_edits
        total_duplicates += duplicate_fields

        reply_lines = [f"✅ Edited planet `{index}` successfully."]
        if changed:
            reply_lines.append("\n**Changes:**\n" + "\n".join(changed))
        if warns:
            reply_lines.append("\n**Warnings:**\n" + "\n".join(warns))
        all_replies.append("\n".join(reply_lines))

    user_info = allowedIds[user_id]
    user_info["Contributions"] += total_valid_edits
    user_info["Grade"] = max(0.0, min(100.0, user_info["Grade"] + 1.0 - (total_duplicates*2.0) - (unchanged_attempts*1.5)))
    allowedIds[user_id] = user_info
    save_enrolled(allowedIds)

    summary = []
    if total_valid_edits > 0:
        summary.append(f"\n📈 +{total_valid_edits} contributions total.")
    if total_duplicates > 0:
        summary.append(f"⚠️ {total_duplicates} duplicate field(s) detected - grade penalized.")
    if unchanged_attempts > 0:
        summary.append(f"⚠️ {unchanged_attempts} unchanged edit(s) attempted - grade penalized.")
    summary.append(f"🎓 Grade now `{allowedIds.get(user_id, {}).get('Grade', 0):.1f}`")

    await ctx.reply("\n\n".join(all_replies + summary))

@bot.command()
async def perc(ctx, one = 0, two = 1):
    await ctx.reply(f"{round(one/two * 100, 4)}%")

@bot.command()
@in_allowed_guild()
async def search(ctx, *, msg: str):
    results = conditionSearch(msg, data, try_cast)

    if "error" in results:
        await ctx.reply(results["error"])
        return

    matches = results["matches"]
    total_found = len(matches)

    if not matches:
        await ctx.reply("❌ No planets matched the search conditions.")
        return

    maxResultCount = 1000
    grade, contribs = get_user_grade(ctx.author.id)
    if grade < 75.0:
        maxResultCount = 500
    if grade < 50.0:
        maxResultCount = 32
    if grade < 25.0:
        maxResultCount = 1
    if grade < 1.0:
        await ctx.reply(f"❌ Your current grade ({grade}) is too low to use this command.")
        return

    if str(ctx.author.id) not in allowedIds:
        maxResultCount = 32

    limited_matches = matches[:maxResultCount]

    filename = f"search_results_{ctx.author.id}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Total results: {total_found}\n")
        if total_found > maxResultCount:
            f.write(f"(⚠️ Only first {maxResultCount} results are shown.)\n")

        if grade < 75.0:
            f.write(f"⚠️ Your grade affected the amount of results shown.\n")
        if str(ctx.author.id) not in allowedIds:
            f.write(f"⚠️ Not enrolled: only 32 results shown\n")

        f.write("\nSearch conditions:\n")
        for cond in results["parsed_conditions"]:
            if isinstance(cond, tuple):
                field, op, val = cond
                f.write(f"- {field} {op} {val}\n")
        if results["planet_count_condition"]:
            _, op, val = results["planet_count_condition"]
            f.write(f"- PlanetCount {op} {val}\n")

        f.write("\nMatching planets:\n")
        for index, planet in limited_matches:
            header = f"--- Planet {index} ---"
            f.write(f"\n{header}\n{json.dumps(planet, indent=4)}\n")

    await ctx.reply(file=discord.File(filename))
    os.remove(filename)

@bot.command()
@in_allowed_guild()
async def count(ctx, *, msg: str = None):
    if msg is None:
        await ctx.reply(f"{len(data)} planets are currently in the database.")
        return

    results = conditionSearch(msg, data, try_cast)

    if "error" in results:
        await ctx.reply(results["error"])
        return

    matches = results["matches"]
    counted = len(matches)

    if not matches:
        await ctx.reply("❌ 0 planets matching your conditions were found. Remember that fields are case sensitive.")
        return

    unique_stars = {planet.get("StarID") for _, planet, _ in matches if planet.get("StarID")}
    star_count = len(unique_stars)

    summary_lines = []
    for cond in results["parsed_conditions"]:
        if isinstance(cond, tuple):
            field, op, val = cond
            if field.lower() != "planetcount":
                summary_lines.append(f"`{field} {op} {val}`")
    if results.get("planet_count_condition"):
        _, op, val = results["planet_count_condition"]
        summary_lines.append(f"`PlanetCount {op} {val}`")

    summary_text = ", ".join(summary_lines) if summary_lines else "No specific filters"
    await ctx.reply(f"✅ `{counted}` planets matched your conditions.\n"
                    f"Unique stars matched: `{star_count}`\n"
                    f"Filters: {summary_text}")

@bot.command()
@in_allowed_guild()
async def hi(ctx):
    await ctx.reply(f'{ctx.author.mention}')
    await asyncio.sleep(1)
    await ctx.reply(f'{ctx.author.mention}')
    await asyncio.sleep(1)
    await ctx.reply(f'{ctx.author.mention} Sory')
    await asyncio.sleep(1)
    await ctx.reply(f'{ctx.author.mention} I love your videos')
    await asyncio.sleep(1)
    await ctx.reply(f'{ctx.author.mention} Bye')

@bot.command()
@in_allowed_guild()
async def ping(ctx):
    latency_ms = round(bot.latency * 1000)
    await ctx.reply(f'✅ Pong. Latency is **{latency_ms}ms**.\nBuild 1.33')

@bot.command()
@in_allowed_guild()
async def pong(ctx):
    await ctx.reply(f'🥱 No')

@bot.command()
async def getGrade(ctx, user_id: str = None):
    if not user_id:
        target_id = str(ctx.author.id)
    else:
        target_id = str(user_id)
    if target_id not in allowedIds:
        await ctx.reply(f"⚠️ User ID `{target_id}` is not enrolled.")
        return
    grade, contrib = get_user_grade(target_id)
    await ctx.reply(f"🗣️ **User:** <@{target_id}>\n📃 **Grade:** {grade:.2f}\n📈 **Contributions:** {contrib}")


# ---- ADMIN ONLY CMDS: -----
@bot.command()
async def setGrade(ctx, user_id: str, new_grade: str, new_contribs: str = "null"):
    adminRole = ctx.guild.get_role(adminRoleId)
    if adminRole not in ctx.author.roles:
        await ctx.reply("❌ You do not have permission to use this command.")
        return
    target_id = str(user_id)
    contrib_value = None
    if target_id not in allowedIds:
        await ctx.reply(f"⚠️ User ID `{target_id}` is not enrolled.")
        return
    try:
        grade_value = float(new_grade)
        if new_contribs != "null":
            contrib_value = int(new_contribs)
    except ValueError:
        await ctx.reply("⚠️ Grade must be a numeric value. Contribution count must be an integer.")
        return
    if grade_value < 0 or grade_value > 100:
        await ctx.reply("⚠️ Grade must be between **0** and **100.**")
        return
    if contrib_value and contrib_value < 0:
        await ctx.reply("⚠️ Contributions cannot go lower than 0.")
        return
    if isinstance(allowedIds[target_id], bool):
        allowedIds[target_id] = {"Contributions": 0, "Grade": 50.0}
    allowedIds[target_id]["Grade"] = grade_value
    if contrib_value:
        allowedIds[target_id]["Contributions"] = contrib_value
    save_enrolled(allowedIds)
    await ctx.reply(
        f"✅ Set grade for <@{target_id}> to **{grade_value:.2f}**"
        + (f", Contributions set to {contrib_value}" if contrib_value else "")
    )

@bot.command()
async def enroll(ctx, *, msg: str):
    adminRole = ctx.guild.get_role(adminRoleId)
    if adminRole not in ctx.author.roles:
        await ctx.reply("❌ You are not allowed to enroll users.")
        return
    args = msg.split()
    if not args:
        await ctx.reply("⚠️ Please provide at least one user ID to enroll.")
        return
    updated = []
    skipped = []
    for arg in args:
        target_id = str(arg)
        existing = allowedIds.get(target_id)
        if isinstance(existing, dict):
            skipped.append(target_id)
            continue
        allowedIds[target_id] = {
            "Contributions": 0,
            "Grade": 100.0
        }
        updated.append(target_id)
    if updated:
        save_enrolled(allowedIds)
        mentions = " ".join(f"<@{uid}>" for uid in updated)
        await ctx.reply(f"✅ Enrolled/Fixed data for the following users:\n{mentions}")
    if skipped:
        mentions = " ".join(f"<@{uid}>" for uid in skipped)
        await ctx.reply(f"⚠️ The following users are already enrolled:\n{mentions}")


@bot.command()
async def unroll(ctx, *, msg):
    user_id = str(ctx.author.id)
    adminRole = ctx.guild.get_role(adminRoleId)
    if adminRole in ctx.author.roles:
        args = msg.split()
        for i in range(len(args)):
            idx = int(args[i])
            target_id = str(idx)
            if target_id in allowedIds:
                del allowedIds[target_id]

                save_enrolled(allowedIds)
                await ctx.reply(f"✅ Deleted User ID `{target_id}` from the bot's allowed list. Mention : <@{target_id}>")
            else:
                await ctx.reply(f"⚠️ User ID `{target_id}` is not in the allowed list.")

    else:
        await ctx.reply("❌ You are not allowed to unenroll users.")

@bot.command()
async def backup(ctx):
    user_id = str(ctx.author.id)
    adminRole = ctx.guild.get_role(adminRoleId)
    if adminRole in ctx.author.roles:
        make_daily_backup(True)
        await ctx.reply(f"✅ Created a backup for {datetime.now().strftime('%Y-%m-%d')}")
    else:
        await ctx.reply("❌ You are not allowed to backup data.")

@bot.command()
async def restart(ctx):
    adminRole = ctx.guild.get_role(adminRoleId)
    if adminRole in ctx.author.roles:
        await ctx.reply(f"✅ Exiting `main.py` process: `{datetime.now()}`\nThe bot should restart in about ~5 seconds.")
        print("Triggered shutdown")
        await bot.close()
        os._exit(0)
    else:
        await ctx.reply("❌ You are not allowed to restart the bot.")


@bot.command()
async def revert(ctx, date):
    user_id = str(ctx.author.id)
    adminRole = ctx.guild.get_role(adminRoleId)
    if adminRole not in ctx.author.roles:
        await ctx.reply("❌ You are not allowed to revert data.")
        return
    backup_dir = os.path.join("backups", date)
    data_file = "data.json"
    backup_file = os.path.join(backup_dir, data_file)
    if not os.path.exists(backup_file):
        await ctx.reply(f"⚠️ No backup found for `{date}`.")
        return
    try:
        shutil.copy(backup_file, data_file)
        load_data()
        await ctx.reply(f"✅ Successfully reverted data to backup from `{date}`.")
    except Exception as e:
        await ctx.reply(f"❌ Failed to revert data: `{e}`")

@bot.command()
async def ls(ctx, folder):
    adminRole = ctx.guild.get_role(adminRoleId)
    if adminRole not in ctx.author.roles:
        await ctx.reply("❌ You are not allowed to view data.")
        return
    base_dir = str(os.path.abspath(os.path.dirname(__file__)))
    requested_path = str(os.path.abspath(os.path.join(base_dir, folder)))
    if not requested_path.startswith(base_dir):
        await ctx.reply("❌ Access denied: outside script directory.")
        return
    if not os.path.exists(requested_path):
        await ctx.reply(f"⚠️ No `{folder}` folder found.")
        return
    if not os.path.isdir(requested_path):
        await ctx.reply(f"⚠️ `{folder}` is not a folder.")
        return
    backups = sorted(os.listdir(requested_path))
    if not backups:
        await ctx.reply(f"❌ No items in `{folder}`.")
    else:
        await ctx.reply(f"✅ Items in `{folder}`:\n" + "\n".join(backups))


@bot.command()
async def weight(ctx, file):
    user_id = str(ctx.author.id)
    adminRole = ctx.guild.get_role(adminRoleId)
    if adminRole not in ctx.author.roles:
        await ctx.reply("❌ You are not allowed to use this command.")
        return
    if not os.path.exists(file):
        await ctx.reply(f"⚠️ {file} not found.")
        return
    fileSize = os.path.getsize(file)
    if file == "backups":
        list = sorted(os.listdir("backups"))
        for i in list:
            slist = sorted(os.listdir("backups/" + i))
            for v in slist:
                fileSize += os.path.getsize("backups/" + i + "/" + v)
    await ctx.reply(f"✅ {file} takes {round(fileSize/1000/1000, 2)} MB of space.")

@bot.command()
@in_allowed_guild()
async def findreplace(ctx, *, msg: str):
    adminRole = ctx.guild.get_role(adminRoleId)
    if adminRole not in ctx.author.roles:
        await ctx.reply("❌ Only the admins are allowed to use this command, for it is very powerful.")
        return

    if "|" not in msg:
        await ctx.reply("⚠️ Missing `|` separator. Use format like `(Field == Value)` AND `(Field2 > 1)` | (Field NewValue)")
        return

    find_part, replace_part = map(str.strip, msg.split("|", 1))

    results = conditionSearch(find_part, data, try_cast)

    if "error" in results:
        await ctx.reply(results["error"])
        return

    matches = results["matches"]
    if not matches:
        await ctx.reply("❌ No planets matched the find conditions.")
        return

    replace_conditions = re.findall(r'\((.*?)\)', replace_part)
    if not replace_conditions:
        await ctx.reply("⚠️ No valid replace conditions found. Example: `(Atmosphere Toxic)` `(Gummite 3)`")
        return

    changes_summary = []
    for field_pair in replace_conditions:
        parts = field_pair.strip().split(" ", 1)
        if len(parts) != 2:
            await ctx.reply(f"⚠️ Invalid replace pair `{field_pair}`. Format must be `(Field NewValue)`")
            return
        field, new_val = parts
        new_val = resolve_reference(new_val, data)

        changes_summary.append((field, new_val))

    msgFirst = await ctx.reply("✅ Find conditions parsed. Processing replacements... please wait.")

    edited_count = 0
    for _, planet, _ in matches:
        for field, new_val in changes_summary:
            new_val = resolve_reference(new_val, data, self_planet=planet)
            if new_val == "/DEL":
                planet.pop(field, None)
            else:
                planet[field] = new_val
        edited_count += 1

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    await msgFirst.delete()
    await ctx.reply(
        f"✅ Edited `{edited_count}` matching planets.\n\n"
        f"Changes applied:\n" +
        "\n".join([f"- {f}: {v}" for f, v in changes_summary])
    )

@bot.command()
async def scrape(ctx):
    adminRole = ctx.guild.get_role(adminRoleId)
    if adminRole not in ctx.author.roles:
        await ctx.reply("❌ Only the admins are allowed to use this command, for it is very powerful.")
        return

    data_path = "data.json"
    users_path = "allowedIds.json"
    if not os.path.exists(data_path):
        await ctx.reply("⚠️ Couldn't find the file.")
        return
    if not os.path.exists(users_path):
        await ctx.reply("⚠️ Couldn't find user data.")
        return
    try:
        await ctx.author.send(
            "heres bots data",
            file=discord.File(data_path)
        )
        await ctx.author.send(
            "heres user data",
            file=discord.File(users_path)
        )
        await ctx.reply("✅ Sent data to your DMs.")

    except discord.Forbidden:
        await ctx.reply("⚠️ Your DMs are closed.")

    except Exception as e:
        await ctx.reply(f"❌ Error: `{e}`")

@bot.command()
async def batch(ctx):
    adminRole = ctx.guild.get_role(adminRoleId)
    if adminRole not in ctx.author.roles:
        await ctx.reply("❌ Only the admins are allowed to use this command, for it is very powerful.")
        return
    if not ctx.message.attachments:
        await ctx.reply("⚠️ Please attach a JSON file containing planet data.")
        return
    attachment = ctx.message.attachments[0]
    if not attachment.filename.endswith(".json"):
        await ctx.reply("⚠️ The attached file must be a `.json` file.")
        return
    await ctx.reply("⏳ Processing batch import...")
    try:
        file_bytes = await attachment.read()
        file_data = file_bytes.decode("utf-8")

        import_data = json.loads(file_data)
        if not isinstance(import_data, dict):
            await ctx.reply("❌ Invalid JSON structure - expected an object (dictionary) at the root.")
            return
        added = 0
        updated = 0

        for index, planet_data in import_data.items():
            if not isinstance(planet_data, dict):
                continue

            if index in data:
                data[index].update(planet_data)
                updated += 1
            else:
                data[index] = planet_data
                added += 1

        save_data(data)
        await ctx.reply(
            f"✅ Batch import completed successfully!\n"
            f"* Created: `{added}` planets\n"
            f"* Updated: `{updated}` planets"
        )
    except json.JSONDecodeError as e:
        await ctx.reply(f"❌ Failed to parse JSON: {e}")
    except Exception as e:
        await ctx.reply(f"❌ An unexpected error occurred: `{type(e).__name__}` - {e}")


@bot.command()
async def help(ctx, admin = False):
    replyMessage = (
        "### Help\n"
        "Note: this bot uses spaces between arguments for most commands except x!edit.\n"
    )

    adminRole = ctx.guild.get_role(adminRoleId)
    if admin:
        if not adminRole in ctx.author.roles:
            await ctx.reply("❌ You're not an admin!")
            return
        replyMessage += (
            "\n**Admin Commands:**\n"
            "`x!enroll <user ids>` - Add users to allowed editor list.\n"
            "`x!unroll <user ids>` - Remove users from allowed editor list.\n"
            "`x!backup` - Creates or overwrites today’s backup.\n"
            "`x!revert <date>` - Reverts bot data to a certain date within the last 15 days (restart required).\n"
            "`x!ls <folder>` - Lists all items in a folder in the bot’s directory.\n"
            "`x!weight <item>` - Replies with the amount of space in megabytes a file takes. Works with the backup folder but not others.\n"
            "`x!findreplace <conditions> | <field newValue> ...` - Finds all planets matching conditions and changes specified fields to new values.\n"
            "`x!restart` - Stops the bot, and with a valid config on the current host's end may restart it automatically.\n"
            "`x!scrape` - Sends all of the bot's data into your DMs.\n"
            "`x!setGrade <userId> <grade> <contributions?>` - Sets a user's grade to a specific value between 0.0 and 100.0\n"
        )
    else:
        replyMessage += (
        "**Commands:**\n"
        "`x!add <id>|<id2> and so on` - Add a planet, or multiple using | as a separator for different planets.\n"
        "`x!get <id>` - Get planet info.\n"
        "`x!edit <id> (Field = Value) (Name = 'something') ... and so on` - Edit a planet.\n"
        "   * x!edit allows for editing multiple planets using | as the separator. Pass /DEL into a field to delete it.\n"
        "`x!search <conditions>` - Returns planets that match all of your conditions.\n"
        "`x!rem <id> ... and so on` - Removes a planet, or multiple planets.\n"
        "`x!count <conditions?>` - Tells you the amount of planets matching your conditions or amount of all planets if no conditions are specified.\n"
        "`x!ping` - Returns the latency and checks if the bot works.\n"
        "`x!getGrade <userId>` - Returns the amount of contributions a user made and their 'grade' (which is a system of limits for users with bad edit score)\n"
        "`x!leaderboard <pageNumber>` - Returns the leaderboard of contributors, 5 users per page.\n"
    )
    await ctx.reply(replyMessage)

bot.run(token, log_handler=handler, log_level=logging.DEBUG)

sys.exit(0)
