import os
import json
import asyncio
# import gspread
# from re import split
# import interactions
import discord
# from dotenv import load_dotenv
from discord.ext import commands
# from google.oauth2 import service_account
# from googleapiclient.discovery import build
# from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
import pytz
import re
# from apscheduler.schedulers.asyncio import AsyncIOScheduler
from PIL import Image, ImageDraw, ImageFont
import tempfile
import time

# load_dotenv()

intents = discord.Intents.all()
activity = discord.Game(name="$help")
bot = commands.Bot(command_prefix='$',
                   help_command=None,
                   description='生活中必不可少的司君.',
                   activity = activity,
                   status=discord.Status.idle,
                   intents=intents)

lastCheckIn = set()


@bot.event
async def on_ready():
    await bot.sync_commands()
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')
    await bot.get_channel(422851664781770753).send("Bot is online")

# Initialize an empty dictionary to store user IDs and names
user_data = {}
# Load the dictionary from a JSON file at startup for persistence
try:
    with open("user_data.json", "r") as file:
        user_data = json.load(file)
except (FileNotFoundError, json.JSONDecodeError):
    user_data = {}

def calculate_skill_sum(skill_components):
    return sum(skill_components)


def calculate_skill_multi(skill_components):
    a, b, c, d, e = skill_components
    multiplier = (100 + a) + (b + c + d + e) / 5
    return 0.01 * multiplier


#-----------------Time conversion--------------
#get EDT time
def get_current_edt_time():
    edt = pytz.timezone('US/Eastern')
    return datetime.now(edt)


# Define the time zones
TIME_ZONES = {
    "EDT": pytz.timezone("America/New_York"),
    "CDT": pytz.timezone("America/Chicago"),
    "PDT": pytz.timezone("America/Los_Angeles"),
    "JST": pytz.timezone("Asia/Tokyo")
}


def convert_time_slot_to_timezones(start_hour, end_hour, source_tz,
                                   target_timezones):
    """
    Convert a time slot (start_hour-end_hour) to specified target time zones in 'HH-HH' format,
    ensuring the end hour is displayed consistently without overlaps.
    """
    # Adjust end_hour for internal handling of 24-hour rollover
    internal_end_hour = 0 if end_hour == 24 else end_hour
    next_day = (end_hour == 24)

    # Convert start and end times separately
    start_time = source_tz.localize(
        datetime.combine(datetime.today(),
                         datetime.min.time()).replace(hour=start_hour))
    end_time = source_tz.localize(
        datetime.combine(datetime.today(),
                         datetime.min.time()).replace(hour=internal_end_hour))
    if next_day:
        end_time += timedelta(
            days=1)  # Adjust to the next day if end_hour was 24

    # Convert start and end times independently to each target timezone
    converted_slots = {}
    for tz_name, tz in target_timezones.items():
        # Convert start and end times separately
        start_converted = start_time.astimezone(tz).strftime("%H")
        end_converted = "24" if end_hour == 0 else end_time.astimezone(
            tz).strftime("%H")

        # Ensure the slot remains as "start_hour-end_hour"
        converted_slots[tz_name] = f"{start_converted}-{end_converted}"

    return converted_slots


def generate_time_slots_for_first_day():
    slots = []
    slot_duration = timedelta(hours=1)

    # Start at 18:00 of the current day
    start_time = datetime.strptime("18", "%H")

    for hour in range(6):
        end_slot = (start_time + slot_duration).time()
        end_hour_str = "24" if end_slot.hour == 0 else end_slot.strftime('%H')
        slot_str = f"{start_time.strftime('%H')}-{end_hour_str}"
        slots.append(slot_str)
        start_time += slot_duration

    return slots


def generate_time_slots_for_days(n):
    all_slots = []
    slot_duration = timedelta(hours=1)

    for day in range(n):
        start_time = datetime.strptime("00", "%H") + timedelta(days=day)
        start_time = pytz.timezone('US/Eastern').localize(
            start_time)  # Localize to EDT

        for hour in range(24):
            end_slot = (start_time + slot_duration).time()
            end_hour_str = "24" if end_slot.hour == 0 else end_slot.strftime(
                '%H')
            slot_str = f"{start_time.strftime('%H')}-{end_hour_str}"

            # Append a single row with slots for CST, PDT, and JST in separate columns
            all_slots.append(slot_str)
            start_time += slot_duration

    return all_slots


##################################################################
##################################################################
######################INITIALIZE SPREADSHEET######################
##################################################################
##################################################################
# Load or initialize the spreadsheet ID storage
SPREADSHEET_FILE = 'spreadsheet_id.json'
if os.path.exists(SPREADSHEET_FILE):
    with open(SPREADSHEET_FILE, 'r') as f:
        spreadsheet_data = json.load(f)
else:
    spreadsheet_data = {}

SERVICE_ACCOUNT_FILE = 'tsukasabot-433122-5dd878777318.json'
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
# credentials = service_account.Credentials.from_service_account_file(
#     SERVICE_ACCOUNT_FILE, scopes=SCOPES)
# sheets_service = build('sheets', 'v4', credentials=credentials)
# drive_service = build('drive', 'v3', credentials=credentials)
# gc = gspread.authorize(credentials)


#spreadsheet_id = None


@bot.command(name='sheet', help='Create a new Google Sheet')
async def create_sheet(ctx):
    global spreadsheet_data
    guild_id = str(ctx.guild.id)

    if guild_id in spreadsheet_data:
        await ctx.reply("A Google Sheet already exists for this server.")
        return

    #await ctx.reply("请提供你的gmail:", ephemeral=True)

    def check(m):
        return m.author == ctx.author and isinstance(m.channel,
                                                     discord.DMChannel)

    try:
        dm_channel = await ctx.author.create_dm()
        await dm_channel.send("Please enter your email:")

        email_msg = await bot.wait_for('message', check=check, timeout=60)
        user_email = email_msg.content.strip()

        sheet_title = "活动班表"
        spreadsheet_body = {'properties': {'title': sheet_title}}
        sheet = sheets_service.spreadsheets().create(
            body=spreadsheet_body, fields='spreadsheetId').execute()
        spreadsheet_id = sheet.get('spreadsheetId')

        # Set up the first sheet with headers
        headers = [["ID", "暱称", "身份", "综合力", "技能总和", "倍率"]]
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="Sheet1!A1:F1",
            valueInputOption="RAW",
            body={
                "values": headers
            }).execute()

        # Create second sheet named "schedule"
        requests = [{"addSheet": {"properties": {"title": "schedule"}}}]
        batch_update_request_body = {'requests': requests}

        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=batch_update_request_body).execute()

        # Set the headers for the schedule sheet
        headers_schedule = [[
            "EST", "CST", "PST", "JST", "Runner", "P2", "P3", "P4", "P5"
        ]]
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="schedule!B1:K1",
            valueInputOption="RAW",
            body={
                "values": headers_schedule
            }).execute()

        permission = {
            'type': 'user',
            'role': 'writer',
            'emailAddress': user_email
        }
        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body=permission,
            fields='id',
        ).execute()

        # Save the new spreadsheet ID

        spreadsheet_data[guild_id] = spreadsheet_id

        with open(SPREADSHEET_FILE, 'w') as f:
            json.dump(spreadsheet_data, f)

        await dm_channel.send(
            f"New Google Sheet created: {sheet_title}\nSpreadsheet ID: {spreadsheet_id}\nAccess it here: https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        )
    except asyncio.TimeoutError:
        await dm_channel.send("You took too long to respond. Please try again."
                              )
    except Exception as e:
        await dm_channel.send(f"An error occurred: {str(e)}")


#add person to edit sheet
@bot.command(name='edit', help='Request email for editing permissions')
async def request_email(ctx):
    global spreadsheet_data
    global drive_service
    # Step 1: Send a DM to the user to ask for their email
    try:
        dm_channel = await ctx.author.create_dm()
        await dm_channel.send(
            "Please provide your email address to gain editing permissions on the schedule."
        )
    except discord.Forbidden:
        await ctx.reply(
            "DM request blocked. Please enable DMs from server members.")
        return

    # Step 2: Define a check to verify that the message comes from the same user and is in DM
    def check(msg):
        return msg.author == ctx.author and isinstance(msg.channel,
                                                       discord.DMChannel)

    # Step 3: Wait for the user's email response
    try:
        msg = await bot.wait_for("message", check=check,
                                 timeout=60)  # Wait for 1 minute
    except asyncio.TimeoutError:
        await dm_channel.send(
            "You took too long to respond. Please try again by typing `$edit`."
        )
        return

    email = msg.content.strip()

    # Validate the email address format
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        await dm_channel.send(
            "The email address format is invalid. Please use a valid email address."
        )
        return

    # Step 4: Add the email to Google Sheets permissions
    try:
        # Build the Google Drive API client
        #drive_service = build('drive', 'v3', credentials=credentials)  # Assuming `sheets_service` already has credentials

        # Get the file ID of the Google Sheet (replace with your sheet ID)
        spreadsheet_id = spreadsheet_data.get(str(ctx.guild.id))
        if not spreadsheet_id:
            await ctx.reply(
                "No Google Sheet found for this server. Please create one using $sheet."
            )
            return

        # Add the email as an editor
        drive_service.permissions().create(fileId=spreadsheet_id,
                                           body={
                                               'type': 'user',
                                               'role': 'writer',
                                               'emailAddress': email
                                           },
                                           fields='id').execute()

        await dm_channel.send(
            f"Access granted! {email} now has editing permissions on the Google Sheet."
        )
    except HttpError as error:
        await dm_channel.send(f"An error occurred: {error}")
    except Exception as e:
        await dm_channel.send(f"Failed to add permissions: {str(e)}")


@bot.command()
async def 倍率(ctx, a: int, b: int, c: int, d: int, e: int):
    overall_skill = a + b + c + d + e
    multiplier = calculate_skill_multi([a, b, c, d, e])
    await ctx.reply(f'内部值: {overall_skill}，倍率: {multiplier:.2f}，实效值：{int((multiplier - 1) * 100)}%')
    
@bot.command()
async def isv(ctx, a: int, b: int, c: int, d: int, e: int):
    overall_skill = a + b + c + d + e
    multiplier = calculate_skill_multi([a, b, c, d, e])
    await ctx.reply(f'ISV total: {overall_skill}, ISV: {multiplier:.2f}, ISV in game：{int((multiplier - 1) * 100)}%')



#update names in schedule
#Function to update all instances of the old name in the schedule sheet
def update_name_in_sheet(spreadsheet_id, sheet_name, old_name, new_name, sheets_service):
    # Fetch the entire schedule sheet data
    range_to_search = f"{sheet_name}!A:Z"  # Adjust range if the sheet is larger
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_to_search
    ).execute()

    # Track all cell locations to update
    updates = []
    rows = result.get("values", [])
    
    for row_index, row in enumerate(rows):
        for col_index, cell_value in enumerate(row):
            if cell_value == old_name:
                # Track the cell's A1 notation (e.g., A1, B2)
                cell_location = f"{sheet_name}!{chr(65 + col_index)}{row_index + 1}"
                updates.append({
                    "range": cell_location,
                    "values": [[new_name]]
                })

    # Perform batch update to replace all occurrences of the old name
    if updates:
        sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": updates
            }
        ).execute()
        return True
    return False

#register user profile
@bot.command(name='reg', aliases = ["r"], help='Register or update user profile')
async def reg(ctx, *, skill_info: str):
    global spreadsheet_data
    global user_data

    guild_id = str(ctx.guild.id)
    spreadsheet_id = spreadsheet_data.get(guild_id)

    user_id = str(ctx.message.author.id)
    old_name = user_data.get(user_id, ctx.author.display_name)  # Default to current display name if not found



    if not spreadsheet_id:
        await ctx.reply("Please first type $sheet to create a Google Sheet.")
        return

    # Parse user input
    components = skill_info.split()
    if len(components) != 8:
        await ctx.reply("Wrong format. \n Please register using: Nickname h/r(helper/runner) Power Skill(Leader + 4 member cards) \n E.g. $reg Tsukasa h 33.5 150 150 150 150 150")
        return

    name, role, power, *skills = components
    


    try:
        skills = [int(x) for x in skills]
    except ValueError:
        await ctx.reply("Wrong ISV. Please provide 5 skills.")
        return

    skill_sum = calculate_skill_sum(skills)
    skill_mult = calculate_skill_multi(skills)

    # Prepare the user profile data
    user_profile = [user_id, name, role, power, skill_sum, skill_mult]

    # Update the dictionary with the new name
    user_data[user_id] = name
    
    # Save the updated dictionary to a JSON file for persistence
    with open("user_data.json", "w") as file:
        json.dump(user_data, file)


    try:
        # Fetch existing profiles to find the user's row if it exists
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=
            "Sheet1!A2:F"  # Adjusted range to cover the columns with user profiles
        ).execute()
        values = result.get('values', [])
        
                # Update all instances of the old name in the schedule sheet
        print(f"old name: {old_name}")
        print(f"new name: {name}")
        if update_name_in_sheet(spreadsheet_id, "schedule", old_name, name, sheets_service):
            pass
        else:
            pass

        # Find the row if the user already has a profile
        user_row = None
        for i, row in enumerate(values,
                                start=2):  # Start from row 2 in Google Sheets
            if row and row[0] == user_id:
                user_row = i
                break

        # Update or append the user profile
        if user_row:
            # Update existing profile in the found row
            range_to_update = f"Sheet1!A{user_row}:F{user_row}"
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_to_update,
                valueInputOption="RAW",
                body={
                    "values": [user_profile]
                }).execute()
            await ctx.reply(
                f"Updated successfully！:tada:\nName: {name}\nType: {role}\nPower: {power}\nISV total: {skill_sum}\nISV: {skill_mult:.2f}"
            )
        else:
            # Append new profile if user doesn't exist
            sheets_service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range="Sheet1!A2:F",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={
                    "values": [user_profile]
                }).execute()
            await ctx.reply(
                f"Registered successfully！:tada:\nName: {name}\nType: {role}\nPower: {power}\nISV total: {skill_sum}\nISV: {skill_mult:.2f}"
            )



    except Exception as e:
        await ctx.reply(f"Cannot be written to Google Sheet: {str(e)}")

#Update user displayed name
@bot.command(name = "rename", help = "rename nickname")
async def rename(ctx, new_name:str):
    global user_data
    global spreadsheet_data
    
    guild_id = str(ctx.guild.id)
    spreadsheet_id = spreadsheet_data[guild_id]
    
    # Retrieve user's current stored name
    user_id = str(ctx.author.id)
    old_name = user_data.get(user_id, ctx.author.display_name)  # Default to current display name if not found

# Update the name in user_data dictionary and save to JSON
    user_data[user_id] = new_name
    with open("user_data.json", "w") as file:
        json.dump(user_data, file)
        
    # Update all instances of the old name in the schedule sheet
    if update_name_in_sheet(spreadsheet_id, "schedule", old_name, new_name, sheets_service):
        update_name_in_sheet(spreadsheet_id,"Sheet1",old_name, new_name, sheets_service)
        await ctx.reply(f"You name '{old_name}' have been updated to '{new_name}'.")
    else:
        await ctx.reply(f"No occurrences of '{old_name}' were registered.")
        


# Update the name in user_data dictionary and save to JSON
    user_data[user_id] = new_name
    with open("user_data.json", "w") as file:
        json.dump(user_data, file)
        
    # Update all instances of the old name in the schedule sheet
    if update_name_in_sheet(spreadsheet_id, "schedule", old_name, new_name, sheets_service):
        update_name_in_sheet(spreadsheet_id,"Sheet1",old_name, new_name, sheets_service)
        await ctx.reply(f"You name '{old_name}' have been updated to '{new_name}'.")
    else:
        await ctx.reply(f"No occurrences of '{old_name}' were registered.")

@bot.command()
async def greet(ctx):
    await ctx.reply(":laughing:天翔けるペガサスと書き、天馬！世界を司ると書き、司！その名も━━天馬司！:wave:")


@bot.command()
async def cat(ctx):
    await ctx.reply("https://media.giphy.com/media/JIX9t2j0ZTN9S/giphy.gif")


#------------------------------Create schedule sheet-----------------------
###########################################################################
def get_user_name_by_id(id, spreadsheet_id, sheets_service):
    profile_range = "Sheet1!A:B"
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=profile_range).execute()

    profiles = result.get('values', [])

    for row in profiles:
        if row and row[0] == id:
            return row[1]

    return None


def get_user_id_by_name(name, spreadsheet_id, sheets_service):
    profile_range = "Sheet1!A:B"
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=profile_range).execute()

    profiles = result.get('values', [])

    for row in profiles:
        if row and row[1] == name:
            id = row[0]
            #id = str(int(float(id)))
            return id

    return None


def update_schedule_sheet(spreadsheet_id, sheets_service, n):
    # Generate the schedule slots (in EDT) with "HH-HH" format
    schedule_slots = generate_time_slots_for_first_day(
    )  # List of slot strings e.g., "18-19"
    schedule_slots2 = generate_time_slots_for_days(n)  # Additional days' slots

    today_date = get_current_edt_time()
    body_values = []

    for day in range(n):
        # Calculate date for the schedule
        current_date = today_date + timedelta(days=day)
        date_str = current_date.strftime("%m-%d")

        # Choose slots based on day
        if day == 0:
            slots = schedule_slots
        else:
            start_index = (day - 1) * (len(schedule_slots2) // n)
            end_index = start_index + (len(schedule_slots2) // n)
            slots = schedule_slots2[start_index:end_index]

        # Add date only in the first row for each day
        date_added = False
        for slot in slots:
            # Parse slot into start and end hours
            start_hour, end_hour = map(int, slot.split("-"))

            # Convert the time slot to all specified time zones
            converted_slots = convert_time_slot_to_timezones(
                start_hour, end_hour, TIME_ZONES["EDT"], TIME_ZONES)

            # Append date and converted time slots to the schedule row
            row = [
                date_str if not date_added else
                "",  # Date in Column A only on the first row
                converted_slots["EDT"],  # EDT slot in Column B
                converted_slots["CDT"],  # CDT slot in Column C
                converted_slots["PDT"],  # PDT slot in Column D
                converted_slots["JST"]  # JST slot in Column E
            ]
            body_values.append(row)
            date_added = True  # Only add date once per day

    # Write data to Google Sheets
    range_name = "schedule!A2:E"  # Range adjusted to include multiple time zones
    result = sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="RAW",
        body={
            "values": body_values
        }).execute()

    print(f"{result.get('updatedCells')} cells updated.")


@bot.command(name='create_schedule',
             help='Generate schedule and add it to Google Sheet')
async def add_schedule(ctx, n: int):
    global spreadsheet_data

    guild_id = str(ctx.guild.id)
    if (guild_id not in (spreadsheet_data)):
        await ctx.reply(
            "No Google Sheet found for this server.Please create one using $sheet."
        )
        return

    spreadsheet_id = (spreadsheet_data[guild_id])
    print(spreadsheet_id)
    print(guild_id)

    # Update sheet with new schedule
    update_schedule_sheet(spreadsheet_id, sheets_service, n)

#delete google sheet
@bot.command(name='delete', help='Delete schedule')
async def delete_schedule(ctx):
    global spreadsheet_data
    global drive_service
    guild_id = str(ctx.guild.id)
    
    if (guild_id not in (spreadsheet_data)):
        await ctx.reply(
            "No Google Sheet to delete for this server."
        )
        return
    spreadsheet_id = (spreadsheet_data[guild_id])
    
    try:
        # Open the Google Sheet and delete all sheets (tabs) within it
        spreadsheet = gc.open_by_key(spreadsheet_id)
        worksheet_list = spreadsheet.worksheets()  # Get all worksheets (tabs) within the spreadsheet

        # Open the Google Sheets file and get its file metadata using Google Drive API
        file = drive_service.files().get(fileId=spreadsheet_id).execute()

        # Delete the Google Sheets file from Google Drive
        drive_service.files().delete(fileId=spreadsheet_id).execute()

        # Optionally, remove the reference to the spreadsheet from your local data
        del spreadsheet_data[guild_id]
        
        with open(SPREADSHEET_FILE, 'w') as f:
            json.dump(spreadsheet_data, f)

        await ctx.reply("The Google Sheet has been deleted successfully.")
    except Exception as e:
            # Handle errors (e.g., if the sheet can't be found or permissions are incorrect)
            await ctx.reply(f"An error occurred while deleting the schedule: {e}")

#-------------------------add slot------------------------
# Helper function to determine the target date based on the offset string
def get_date_based_on_offset(offset_str):
    """Calculate the date based on the offset (e.g., 't+1' means tomorrow)."""
    if offset_str == 't':
        return get_current_edt_time()  # Current date
    elif offset_str.startswith('t+'):
        try:
            days_ahead = int(offset_str.split('+')[1])
            return get_current_edt_time() + timedelta(days=days_ahead)
        except ValueError:
            return None  # Invalid format for days ahead
    else:
        return None  # Invalid format


def find_time_slot_row(date_str, time_slot, sheet_data):
    """Finds the row index of the specified date and time slot in the sheet data."""
    for row_index, row in enumerate(sheet_data):
        if row[0] == date_str and len(row) > 1 and row[1] == time_slot:
            return row_index
    return None  # Time slot not found


@bot.command(name='add',
             aliases=["a", "+"],
             help='Add user to a range of time slots consecutively')
async def add_user(ctx, *args):
    global spreadsheet_data

    guild_id = str(ctx.guild.id)

    if guild_id not in spreadsheet_data:
        await ctx.reply(
            "No Google Sheet found for this server. Please create one using $sheet."
        )
        return

    spreadsheet_id = spreadsheet_data[guild_id]
    user_id = str(ctx.message.author.id)
    user_name = get_user_name_by_id(user_id, spreadsheet_id, sheets_service)

    if user_name is None:
        await ctx.reply("Register your team first using $reg.")
        return

    # Parse the arguments: check if the first argument is a time range
    if len(args) == 1:
        date_offset = "t"
        time_range = args[0]
    elif len(args) == 2:
        date_offset, time_range = args
    else:
        await ctx.reply(
            "Invalid command format. Use `$a <time-period>` or `$a t+<n> <time-period>`."
        )
        return

    # Calculate the target date based on the date offset (e.g., 't+1' means tomorrow)
    target_date = get_date_based_on_offset(date_offset)

    if target_date is None:
        await ctx.reply(
            "Invalid date format. Use 't' for today or 't+<n>' for days ahead."
        )
        return

    date_str = target_date.strftime(
        "%m-%d")  # Format date to match Google Sheets format

    # Parse the time range (e.g., 10-15) into start and end hours
    try:
        start_time_str, end_time_str = time_range.split('-')
        num_slot = int(end_time_str)-int(start_time_str)
        start_time = datetime.strptime(start_time_str, "%H")
        
        #print("number of slots to fill:", num_slot)
        #end_time = datetime.strptime(end_time_str,"%H")
        #pritn("end time: ", end_time)

    except ValueError:
        await ctx.reply(
            "Invalid time range format. Please use <start_time>-<end_time> (e.g., 10-15)."
        )
        return

    # if start_time >= end_time:
    #     await ctx.reply("Start time must be earlier than end time.")
    #     return

    # Find the row for the specified date in column A
    sheet_range = "schedule!A:B"
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=sheet_range).execute()

    values = result.get('values', [])
    date_row_start = None
    for i, row in enumerate(values):
        if row and row[0] == date_str:
            date_row_start = i + 1  # A2 is the first row we check, so add 2 for Google Sheets indexing
            break

    if date_row_start is None:
        await ctx.reply(f"No entries found for date {date_str}.")
        return

    # Add the individual time slots between start_time and end_time
    current_time = start_time
    new_date = target_date + timedelta(days=1)
    new_date = new_date.strftime("%m-%d")

    next_time = current_time + timedelta(hours=1)
    time_slot = f"{current_time.strftime('%H')}-{next_time.strftime('%H')}"

    row_number = None
    for i in range(date_row_start - 1,
                       len(values)):  # Adjust for 0-based index
            row = values[i]
            if row and row[
                    0] == new_date:  # Stop if a new date is found in column A
                break
            if row and len(row) > 1 and row[
                    1] == time_slot:  # Check column B for time slot
                row_number = i + 1  # Convert to 1-based index for Google Sheets
                break

    if row_number is None:
        await ctx.reply(
            f"Time slot {time_slot} not found for date {date_str}.")
        return    
    
# Find the first slot
# then find the first available column
# go to next slot
#find the fist available column
    for slot in range(1,num_slot+1):

        # Find the next available column starting from F (index 6) in the located row
        sheet_range_row = f"schedule!G{row_number}:Z{row_number}"
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=sheet_range_row).execute()

        result2 = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"schedule!B{row_number}").execute()

        timepoint = result2.get('values',[])

        current_values = result.get('values', [])
        print(f"current values: {current_values}")
        col_index = None
        if current_values:
            current_values = current_values[0]
            print(f"current values: {current_values}")
            for j, value in enumerate(current_values, start=7):
                print(j)
                print(value)
                if value == "":
                    col_index = j
                    break
                if value == user_name:
                    #col_index = None
                    await ctx.reply(
                        f"You have already added on {date_str} at {''.join(timepoint[0])}."
                    )
                    return
                if value and value!="":  # Empty cell found
                    col_index = j + 1
                

        else:
            col_index = 7

        if col_index is None:
            await ctx.reply(
                f"Error: Cannot add {user_name} on {date_str} at {time_range}. Please check your time period. "
            )
            return

        # Update the found cell with the user's name
        cell = f"schedule!{chr(64+col_index)}{row_number}"
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=cell,
            valueInputOption="RAW",
            body={
                "values": [[user_name]]
            }).execute()

        # Move to the next time slot
        row_number += 1


    await ctx.reply(
        f"{user_name} added to schedule on {date_str} for time slots {time_range}."
    )


#-------------------------Remove user from schedule--------------------------------


@bot.command(
    name='rm',
    aliases=["sub", "-"],
    help=
    'Remove user from a specified date and time slot or range of time slots')
async def remove_user(ctx, *args):
    global spreadsheet_data

    guild_id = str(ctx.guild.id)

    if guild_id not in spreadsheet_data:
        await ctx.reply(
            "No Google Sheet found for this server. Please create one using $sheet."
        )
        return

    spreadsheet_id = spreadsheet_data[guild_id]
    user_id = str(ctx.message.author.id)
    user_name = get_user_name_by_id(user_id, spreadsheet_id, sheets_service)

    if user_name is None:
        await ctx.reply("Register your team first using $reg.")
        return

    # Parse the arguments: check if the first argument is a time range
    if len(args) == 1:
        date_offset = "t"
        time_range = args[0]
    elif len(args) == 2:
        date_offset, time_range = args
    else:
        await ctx.reply(
            "Invalid command format. Use `$rm <time-period>` or `$rm t+<n> <time-period>`."
        )
        return

    # Calculate the target date based on the date offset (e.g., 't+1' means tomorrow)
    target_date = get_date_based_on_offset(date_offset)

    if target_date is None:
        await ctx.reply(
            "Invalid date format. Use 't' for today or 't+<n>' for days ahead."
        )
        return

    date_str = target_date.strftime(
        "%m-%d")  # Format date to match Google Sheets format

    # Parse the time range (e.g., 10-15) into start and end hours
    try:
        start_time_str, end_time_str = time_range.split('-')
        num_slot = int(end_time_str)-int(start_time_str)
        start_time = datetime.strptime(start_time_str, "%H")
        #end_time = datetime.strptime(end_time_str, "%H")
    except ValueError:
        await ctx.reply(
            "Invalid time range format. Please use <start_time>-<end_time> (e.g., 10-15)."
        )
        return

    # if start_time >= end_time:
    #     await ctx.reply("Start time must be earlier than end time.")
    #     return

    # Find the row for the specified date in column A
    sheet_range = "schedule!A:B"
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=sheet_range).execute()

    values = result.get('values', [])
    date_row_start = None
    for i, row in enumerate(values):
        if row and row[0] == date_str:
            date_row_start = i + 1  # A2 is the first row we check, so add 2 for Google Sheets indexing
            break

    if date_row_start is None:
        await ctx.reply(f"No entries found for date {date_str}.")
        return

    # Remove the individual time slots between start_time and end_time
    current_time = start_time
    new_date = target_date + timedelta(days=1)
    new_date = new_date.strftime("%m-%d")

    next_time = current_time + timedelta(hours=1)
    time_slot = f"{current_time.strftime('%H')}-{next_time.strftime('%H')}"
    
    row_number = None
    for i in range(date_row_start - 1,
                    len(values)):  # Adjust for 0-based index
        row = values[i]
        if row and len(row) > 1 and row[1] == time_slot:  # Check column B for time slot
            row_number = i + 1  # Convert to 1-based index for Google Sheets
            break

    if row_number is None:
        await ctx.reply(
            f"Time slot {time_slot} not found for date {date_str}.")
        return


    for slot in range(1,num_slot+1):     
        print("time slot:", time_slot)

        # Find the column containing the user's name
        print("row number: ", row_number)
        sheet_range_row = f"schedule!G{row_number}:J{row_number}"
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=sheet_range_row).execute()

        current_values = result.get('values', [])
        print("current values: ", current_values)
        col_index = None
        if current_values:
            current_values = current_values[0]
            for j, value in enumerate(current_values, start=7):
                if value == user_name:  # Find the user's name
                    col_index = j
                    break
        else:
            await ctx.reply(
                f"No columns found for time slot {time_slot} at {date_str}.")
            return

        if col_index is None:
            await ctx.reply(f"{user_name} is not in the time slot {time_slot}.")
            return

        # Clear the user's name from the cell
        cell = f"schedule!{chr(64 + col_index)}{row_number}"
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=cell,
            valueInputOption="RAW",
            body={
                "values": [[""]]
            }).execute()

        # Move to the next time slot
        row_number +=1

    await ctx.reply(
        f"{user_name} removed from schedule on {date_str} for time slots {time_range}."
    )


#------------------------Send current schedule when requested----------------------
def get_sheet_row_count(spreadsheet_id, sheet_name):
    # Define the range to cover all rows in the sheet
    sheet_range = f"{sheet_name}!B:B"  # This checks column A, assuming every row has a value in column A
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=sheet_range).execute()

    values = result.get("values", [])
    return len(values)


    # Main function to retrieve data from the Google Sheet based on date
def get_sheet_data(spreadsheet_id, date):
    date_row_start = 0
    date_row_end = 0

    current_date = date.strftime("%m-%d")
    #print("Current date:", current_date)

    new_date = date + timedelta(days=1)
    new_date_str = new_date.strftime("%m-%d")

    sheet_range = "schedule"  # Adjust as necessary
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=sheet_range).execute()
    values = result.get("values", [])

    # Check if there is data
    if not values:
        return []

        # The first row is the header
    header = values[0]
    matching_rows = [header]  # Start with the header row included

    # Get total number of rows
    nrows = get_sheet_row_count(spreadsheet_id, "schedule")

    # Find start and end rows
    for i, row in enumerate(
            values[1:],
            start=2):  # Start from 2 to match Google Sheets indexing
        if row and row[0] == current_date and date_row_start == 0:
            date_row_start = i
        if row and row[0] == new_date_str:
            date_row_end = i - 1
            break

    # If new_date wasn't found, use the last row as end
    if date_row_end == 0:
        date_row_end = nrows

        # Define the range to retrieve rows between date_row_start and date_row_end
    sheet_range_now = f"schedule!A{date_row_start}:J{date_row_end}"

    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=sheet_range_now).execute()
    values = result.get("values", [])

    # Extend matching_rows with the retrieved rows
    matching_rows.extend(values)

    return matching_rows

def get_row_ranges(spreadsheet_id, date):
    date_row_start = 0
    date_row_end = 0

    current_date = date.strftime("%m-%d")
    #print("Current date:", current_date)

    new_date = date + timedelta(days=1)
    new_date_str = new_date.strftime("%m-%d")

    sheet_range = "schedule"  # Adjust as necessary
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=sheet_range).execute()
    values = result.get("values", [])

    # Check if there is data
    if not values:
        return []

        # The first row is the header
    header = values[0]
    matching_rows = [header]  # Start with the header row included

    # Get total number of rows
    nrows = get_sheet_row_count(spreadsheet_id, "schedule")

    # Find start and end rows
    for i, row in enumerate(
            values[1:],
            start=2):  # Start from 2 to match Google Sheets indexing
        if row and row[0] == current_date and date_row_start == 0:
            date_row_start = i
        if row and row[0] == new_date_str:
            date_row_end = i - 1
            break

    # If new_date wasn't found, use the last row as end
    if date_row_end == 0:
        date_row_end = nrows

        # Define the range to retrieve rows between date_row_start and date_row_end
    sheet_range_now = f"schedule!A{date_row_start}:J{date_row_end}"
    
    return sheet_range_now


#---------------------------Generate image to send to discord-----------------
# Function to retrieve Google Sheets cell formatting (optional)
def get_sheet_formatting(spreadsheet_id, sheet_id, sheets_service,range):
    # Request cell formatting information from Google Sheets
    result = sheets_service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(data(rowData(values(userEnteredFormat(backgroundColor,textFormat)))))",
        ranges=[f"{sheet_id}!A1:J1", range]  # Adjust range as needed
    ).execute()

    # Extract background and text color data
    color_map = {}
    try:
        # Process each range result separately
        for sheet_data in result["sheets"][0]["data"]:
            row_data = sheet_data.get("rowData", [])
            for row_index, row in enumerate(row_data):
                for col_index, cell in enumerate(row.get("values", [])):
                    # Extract colors
                    bg_color = cell.get("userEnteredFormat", {}).get("backgroundColor", {})
                    text_color = cell.get("userEnteredFormat", {}).get("textFormat", {}).get("foregroundColor", {})

                    # Convert colors to RGB tuples (scaled to 255)
                    background_rgb = (
                        int(bg_color.get("red", 1) * 255),
                        int(bg_color.get("green", 1) * 255),
                        int(bg_color.get("blue", 1) * 255)
                    )
                    text_rgb = (
                        int(text_color.get("red", 0) * 255),
                        int(text_color.get("green", 0) * 255),
                        int(text_color.get("blue", 0) * 255)
                    )

                    # Store colors in color_map with an adjusted row index for each range
                    # Adjust row_index to reflect the actual row number in the sheet
                    if sheet_data == result["sheets"][0]["data"][0]:  # First range (A1:J1)
                        adjusted_row_index = row_index
                    else:  # Second range (A2:J10)
                        adjusted_row_index = row_index + 1  # Adjust based on range offset

                    color_map[(adjusted_row_index, col_index)] = {"background": background_rgb, "text": text_rgb}

    except KeyError as e:
        print(f"Error accessing formatting data: {e}")

    return color_map


# Helper function to create an image from the Google Sheet data
def create_image_from_data(data, highlight_colors):
    # Basic settings for image
    try:
        font = ImageFont.truetype("www/fonts/NotoSansSC-Regular.ttf", 18)
    except IOError:
        font = ImageFont.load_default()

    row_height = 30  # Increase for better spacing
    col_width = 120  # Adjust column width for readability
    padding = 10
    header_color = (200, 200, 255)  # Light blue for header
    line_color = (0, 0, 0)  # Black lines for table grid

    # Calculate image size
    image_width = col_width * len(data[0]) + padding * 2
    image_height = row_height * len(data) + padding * 2
    max_columns = max(len(row) for row in data)  # Find the longest row in data

    # Create a blank image with white background
    image = Image.new("RGB", (image_width, image_height), "white")
    draw = ImageDraw.Draw(image)

    # Draw the table data onto the image with borders
    for i, row in enumerate(data):
        y = i * row_height + padding

        # Set header background color
        if i == 0:
            draw.rectangle([padding, y, image_width - padding, y + row_height],
                           fill=header_color)

        for j in range(max_columns):  # Ensure we iterate over all columns, even empty ones
            x = j * col_width + padding
            cell_text = str(row[j]) if j < len(row) and row[j] is not None else ""

            # Determine cell background and text colors
            cell_colors = highlight_colors.get((i, j), {"background": "white", "text": "black"})
            fill_color = cell_colors["background"]
            text_color = cell_colors["text"]

            # Draw cell background color
            draw.rectangle([x, y, x + col_width, y + row_height],
                           fill=fill_color,
                           outline=line_color)

            # Measure text size to center it
            bbox = draw.textbbox((0, 0), cell_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x + (col_width - text_width) / 2
            text_y = y + (row_height - text_height) / 2

            # Draw text with specified color
            draw.text((text_x, text_y), cell_text, fill=text_color, font=font)

            # Draw the border around each cell
            draw.rectangle([x, y, x + col_width, y + row_height], outline=line_color)

    # Use tempfile to create a temporary file path for the image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
        image_path = tmp_file.name
    image.save(image_path)
    return image_path



#$s to retrive current date image
@bot.command(name="schedule",
             aliases=["s"],
             help="Retrieve the Google Sheet table as an image")
async def send_sheet_image(ctx, *args):

    global spreadsheet_data
    guild_id = str(ctx.guild.id)
    spreadsheet_id = spreadsheet_data[guild_id]

    if not spreadsheet_id:
        await ctx.reply(
            "Please create a Google Sheet first using the $sheet command.")
        return

    if not args:
        # If no argument is passed, append the default value 't'
        args = ('t', )

    # Convert the tuple to a string if needed
    if isinstance(args, tuple):
        args = args[0]

    # Calculate the target date based on the date offset (e.g., 't+1' means tomorrow)
    target_date = get_date_based_on_offset(args)
    date_str = target_date.strftime("%m-%d")
    #print(date_str)

    # Retrieve data from Google Sheets
    data = get_sheet_data(spreadsheet_id, target_date)
    if not data:
        await ctx.reply(f"No schedule on {date_str}.")
        return

    schedule_rows = get_row_ranges(spreadsheet_id,target_date)
    bg_color = get_sheet_formatting(spreadsheet_id, "schedule", sheets_service,schedule_rows)
    
    image_path = create_image_from_data(data, bg_color)
    # Send the image in Discord
    with open(image_path, "rb") as f:
        picture = discord.File(f)
        await ctx.reply(f"Here is the current schedule for {date_str}:", file=picture)

    # Clean up the temporary file after sending
    os.remove(image_path)


# -----------------------Send alert 15mins ahead-----------------------

# Set up timezone
TIMEZONE = pytz.timezone('US/Eastern')

# Store alert settings and status
alert_settings = {}
alerting_active = False

# Dictionary to track alerted slots
alerted_slots = {}

@bot.command(
    name='alert',
    help='Set an alert for a specified channel and time before an event')
async def set_alert(ctx, channel: discord.TextChannel, mins: int):
    global alert_settings, alerting_active

    guild_id = str(ctx.guild.id)
    alert_settings[guild_id] = {
        'channel': channel.id,
        'mins': mins,
        'guild_id': guild_id
    }

    if not alerting_active:
        alerting_active = True
        bot.loop.create_task(send_alerts())

    await ctx.reply(
        f"Reminder set for {mins} minutes before schedules in {channel.mention}.")



async def send_alerts():
    global alerting_active
    global spreadsheet_data

    last_known_date_str = None
    while alerting_active:
        now = datetime.now(TIMEZONE).replace(second=0,
                                             microsecond=0,
                                             tzinfo=None)
        print("now:", now)

        for guild_id, settings in alert_settings.items():
            alert_channel_id = settings['channel']
            alert_minutes = settings['mins']
            channel = bot.get_channel(alert_channel_id)
            guild_id = settings['guild_id']

            # Initialize separate alerted slots for each guild if not already done
            if guild_id not in alerted_slots:
                alerted_slots[guild_id] = {}

            if channel:
                # Get schedule from Google Sheets
                sheet_range = "schedule!A2:B"
                result = sheets_service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_data[guild_id],
                    range=sheet_range).execute()
                values = result.get('values', [])

                nearest_slot = None
                nearest_start_time = None

                # Identify the nearest upcoming time slot
                for row in values:
                    if len(row) < 2:
                        continue

                    date_str, time_period = row[0], row[1]
                    start_time_str, end_time_string = time_period.split('-')

                    # Check if `date_str` contains date information
                    if "-" in date_str:  # Basic check to see if it's a date format
                        last_known_date_str = date_str.strip(
                        )  # Update the last known date

                    # If `last_known_date_str` is None, skip this iteration as we have no valid date
                    if not last_known_date_str:
                        continue

                    event_datetime = datetime.strptime(
                        f"2024-{last_known_date_str} {start_time_str}:00",
                        '%Y-%m-%d %H:%M').replace(tzinfo=None)
                    print("event date time: ", event_datetime)

                    if event_datetime > now:
                        nearest_slot = row
                        nearest_start_time = event_datetime
                        break

                print("nearest slot:", nearest_slot)
                print("nearest start time:", nearest_start_time)

                print("diff: ",
                      (nearest_start_time - timedelta(minutes=alert_minutes)))

                if nearest_slot and nearest_start_time:
                    if now >= nearest_start_time - timedelta(
                            minutes=alert_minutes):

                        # Prevent sending alert if it has already been sent for this time slot
                        event_time_key = f"{nearest_start_time}"

                        if event_time_key not in alerted_slots[guild_id]:
                            row_number = values.index(nearest_slot) + 2
                            sheet_range_row = f"schedule!G{row_number}:J{row_number}"
                            result = sheets_service.spreadsheets().values().get(
                                spreadsheetId=spreadsheet_data[guild_id],
                                range=sheet_range_row).execute()
                            user_names = result.get('values', [])[0]

                            # Collect user mentions
                            user_mentions = [
                                f"<@{get_user_id_by_name(name, spreadsheet_data[guild_id], sheets_service)}>"
                                for name in user_names if name
                            ]
                            
                            newSet = set(user_mentions)
                            
                            user_mentions = [x for x in user_mentions if x not in lastCheckIn]
                            lastCheckIn = newSet

                            if user_mentions:
                                message = f"{' '.join(user_mentions)} Your upcoming schedule is in {alert_minutes} minutes! Please react/reply to check in."
                                await channel.send(message)

                            #Mark the time slot as alerted for this guild
                            alerted_slots[guild_id][event_time_key] = True

                        print("Alert sent for:", event_time_key)

        # Wait for 10 minutes before checking again
        await asyncio.sleep(120)  # Sleep for 10 minutes (600 seconds)



@bot.command(name='stop_alerts', help='Stop the alert task')
async def stop_alerts(ctx):
    global alerting_active
    alerting_active = False
    await ctx.reply("Alert task stopped.")

# Event listener for new messages
@bot.event
async def on_message(message):
    
    print(f"Message from {message.author}: {message.content}")
    
    # Avoid responding to the bot's own messages
    if message.author.bot:
        return

    # Check if the channel name starts with "g1-"
    if message.channel.name.startswith("g1-"):
        # Regex to find a 5-digit number in the message
        match = re.fullmatch(r"\d{5}", message.content.strip())
        if match:
            try:
                # Update the channel name to the 5-digit number
                new_name = match.group()
                await message.channel.edit(name=f"g1-{new_name}")
                # Create a success embed
                embed = discord.Embed(
                    title="Room Updated",
                    description=f"Room code updated to `{new_name}`.",
                    color=discord.Color.green()
                )
                await message.channel.send(embed=embed)
            except discord.Forbidden:
                # Create a permissions error embed
                embed = discord.Embed(
                    title="Error: Forbidden",
                    description="I lack permissions to change the channel name.",
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed)
            except discord.HTTPException as e:
                # Create a failure embed for HTTP exceptions
                embed = discord.Embed(
                    title="Error",
                    description=f"Failed to update channel name: {e}",
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed)
                
    else:
        await bot.process_commands(message)

#------------------------HELP Documentation------------------------


# Basic commands and schedule commands as separate pages
def get_basic_commands_embed():
    embed = discord.Embed(
        title="Basic Commands",
        description="> command prefix: $\n",
        color=0xffd438,
        timestamp=datetime.now()
    )
    icon = discord.File("www/images/tsukasa_sleep.png", filename="tsukasa_sleep.png")
    
    embed.set_author(name="Help")
    #embed.add_field(name = chr(173), value = chr(173))
    embed.add_field(name="Calculate ISV",
                value="※ `$isv` `<Skill(leader+4 members)>` \n E.g. `$isv 150 150 150 150 150`.",
                inline=False)
    embed.add_field(name="Register profile",
                value="※ `$reg` `<Nickname>` `<h/r(helper/runner)>` `<Power>` `<Skill(leader+4 members)>`\nE.g. `$reg Tsukasa h 33.5 150 150 150 150 150`\nRegisters or updates your profile.",
                inline=False)
    embed.add_field(name="Rename",
                value="※ `$rename` `<Nickname>` \n E.g. `$rename Kemokemo`\nUpdate your name on schedule.",
                inline=False)
    # embed.add_field(name="Generate schedule",
    #             value="※ `$sheet`\nGenerate a google sheet for this server.\n※ `$edit`\nDMs you to request your email, then adds it with write permissions to the Google Sheet.\n※ `$create_schedule <days>`\nCreates a new schedule with time slots for the specified number of days.",
    #             inline=False)

    embed.set_footer(text="ツカサ ロボ 2024",
                 icon_url="attachment://tsukasa_sleep.png")
    return embed

def get_schedule_management_embed():
    embed = discord.Embed(
        title="Schedule Management",
        description="> command prefix: $\n All schedule are set on __**EST**__ timezone",
        color=0xffd438,
        timestamp=datetime.now()
        
    )
    icon = discord.File("www/images/tsukasa_sleep.png", filename="tsukasa_sleep.png")
    embed.set_author(name="Help")
    #embed.add_field(name = chr(173), value = chr(173))
    embed.add_field(name="Add time slot",
                value="※ ` $add <time-period>`\nAdds you to a specified time slot on the schedule.\nE.g. `$add 21-23`, `$+ t+1 4-6`",
                inline=False)
    embed.add_field(name="Remove time slot",
                value="※ `$rm <time-period>`\nRemoves you from a specified time slot on the schedule.\nE.g. `$rm 21-23`, `$- t+1 4-6`",
                inline=False)
    embed.add_field(name="Obtain schedule",
                value="※ `$s <date-index>`\nRequests the schedule for a specific date. If no date is specified, return today's schedule.\nE.g. `$s t+1`",
                inline=False)
    # embed.add_field(name="Schedule reminder",
    #             value="※ `$s alarm <channel> <minutes>`\nSet up a reminder to remind scheduled supporters to check-in in <minutes>.",
    #             inline=False)
    
    embed.set_footer(text="ツカサ ロボ 2024",
                 icon_url="attachment://tsukasa_sleep.png")
    return embed
    
# Define a View with buttons for pagination
class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.current_page = 0
        self.pages = [get_basic_commands_embed(), get_schedule_management_embed()]

    @discord.ui.button(label="Basic Commands", style=discord.ButtonStyle.primary, custom_id="basic_commands")
    async def basic_commands_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Show Basic Commands page
        self.current_page = 0
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @discord.ui.button(label="Schedule Management", style=discord.ButtonStyle.primary, custom_id="schedule_management")
    async def schedule_management_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Show Schedule Management page
        self.current_page = 1
        await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

# Help command with pagination

@bot.command(name='help', aliases=['h'], help='Displays all available commands and their documentation.')
async def help_command(ctx):
    icon = discord.File("www/images/tsukasa_sleep.png", filename="tsukasa_sleep.png")
    view = HelpView()
    await ctx.reply(embed=view.pages[0], view=view, file= icon)
    
bot.load_extension('commands.Hours')
bot.run(os.getenv('DISCORD_TOKEN'))
