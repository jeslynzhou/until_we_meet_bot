import asyncio
import json
from datetime import datetime

import os
from dotenv import load_dotenv

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, CallbackQueryHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()  # load variables from .env file

# ---------------------
# Global variables
# ---------------------
EVENTS_FILE = "events.json"
events = []
bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")

# Conversation states
EVENT_NAME, EVENT_DATE, START_DATE, DELETE_EVENT, DELETE_BUTTON = range(5)

# ---------------------
# Helper functions
# ---------------------
def save_events():
    with open(EVENTS_FILE, "w") as f:
        json.dump(events, f)

def load_events():
    global events
    try:
        with open(EVENTS_FILE, "r") as f:
            events = json.load(f)
    except FileNotFoundError:
        events = []

def countdown(event_date, start_date=None):
    today = datetime.now().date()
    event = datetime.strptime(event_date, "%Y-%m-%d").date()
    days_left = (event - today).days

    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        total_days = (event - start).days
        percentage = round((total_days - days_left) / total_days * 100, 2)
    else:
        percentage = None

    return days_left, percentage

async def send_reminder(chat_id, event):
    days_left, pct = countdown(event["event_date"], event.get("start_date"))
    text = f"🎉 {event['event_name']} is in {days_left} days! ({pct}% passed)"
    await bot.send_message(chat_id=chat_id, text=text)

# ---------------------
# Menu & Navigation
# ---------------------
async def start(update, context):
    keyboard = [
        ["➕ Add Event", "📋 List Events"],
        ["🗑 Delete Event", "❌ Cancel"]
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, resize_keyboard=True, one_time_keyboard=False
    )
    await update.message.reply_text("Welcome! Choose an option:", reply_markup=reply_markup)

async def handle_menu_choice(update, context):
    choice = update.message.text

    if choice == "➕ Add Event":
        return await start_add_event(update, context)
    elif choice == "📋 List Events":
        return await list_events(update, context)
    elif choice == "🗑 Delete Event":
        return await delete_event_menu(update, context)
    elif choice == "❌ Cancel":
        await update.message.reply_text("Cancelled.")
        return ConversationHandler.END

# ---------------------
# Add Event Conversation
# ---------------------
async def start_add_event(update, context):
    await update.message.reply_text("Enter the event name:")
    return EVENT_NAME

async def get_event_name(update, context):
    context.user_data['event_name'] = update.message.text
    await update.message.reply_text("Enter the event date (YYYY-MM-DD):")
    return EVENT_DATE

async def get_event_date(update, context):
    context.user_data['event_date'] = update.message.text

    # Ask for start date with inline buttons
    keyboard = [
        [InlineKeyboardButton("Skip", callback_data="skip")],
        [InlineKeyboardButton("Custom date", callback_data="custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Do you want to set a start date?", reply_markup=reply_markup)
    return START_DATE

async def start_date_button(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "skip":
        context.user_data['start_date'] = None
        new_event = {
            "chat_id": update.effective_chat.id,
            "event_name": context.user_data['event_name'],
            "event_date": context.user_data['event_date'],
            "start_date": None
        }
        events.append(new_event)
        save_events()
        await query.edit_message_text(f"Event '{new_event['event_name']}' added successfully!")
        return ConversationHandler.END

    elif query.data == "custom":
        await query.edit_message_text("Enter the start date (YYYY-MM-DD):")
        return START_DATE

async def get_start_date(update, context):
    context.user_data['start_date'] = update.message.text
    new_event = {
        "chat_id": update.effective_chat.id,
        "event_name": context.user_data['event_name'],
        "event_date": context.user_data['event_date'],
        "start_date": context.user_data['start_date']
    }
    events.append(new_event)
    save_events()
    await update.message.reply_text(f"Event '{new_event['event_name']}' added successfully!")
    return ConversationHandler.END

# ---------------------
# List Events
# ---------------------
async def list_events(update, context: ContextTypes.DEFAULT_TYPE):
    if not events:
        await update.message.reply_text("No events found.")
        return

    messages = []
    for e in events:
        days_left, pct = countdown(e["event_date"], e.get("start_date"))
        messages.append(f"{e['event_name']}: {days_left} days left ({pct}% passed)")
    await update.message.reply_text("\n".join(messages))

# ---------------------
# Delete Events
# ---------------------
async def delete_event_menu(update, context):
    if not events:
        await update.message.reply_text("No events to delete.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(e['event_name'], callback_data=str(i))] for i, e in enumerate(events)]
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Select an event to delete:", reply_markup=reply_markup)
    return DELETE_BUTTON

async def delete_event_button(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END

    index = int(query.data)
    deleted_event = events.pop(index)
    save_events()
    await query.edit_message_text(f"Deleted event: {deleted_event['event_name']}")
    return ConversationHandler.END

async def delete_event_command(update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Enter the name of the event to delete:")
        return DELETE_EVENT

    event_name = " ".join(context.args)
    for i, e in enumerate(events):
        if e['event_name'].lower() == event_name.lower():
            deleted_event = events.pop(i)
            save_events()
            await update.message.reply_text(f"Deleted event: {deleted_event['event_name']}")
            return ConversationHandler.END

    await update.message.reply_text(f"No event found with name '{event_name}'.")
    return ConversationHandler.END

async def delete_event_by_name(update, context):
    name_input = update.message.text.strip()
    for i, e in enumerate(events):
        if e['event_name'].lower() == name_input.lower():
            deleted_event = events.pop(i)
            save_events()
            await update.message.reply_text(f"Deleted event: {deleted_event['event_name']}")
            return ConversationHandler.END

    await update.message.reply_text(f"No event found with name '{name_input}'. Try again or type /cancel.")
    return DELETE_EVENT

# ---------------------
# Cancel handler
# ---------------------
async def cancel(update, context):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

# ---------------------
# Main async function
# ---------------------
async def main():
    global bot
    load_events()

    # Create bot instance
    app = ApplicationBuilder().token(bot_token).build()
    bot = app.bot

    # Add Event Conversation
    add_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Add Event$"), start_add_event)],
        states={
            EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_event_name)],
            EVENT_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_event_date)],
            START_DATE: [CallbackQueryHandler(start_date_button),
                         MessageHandler(filters.TEXT & ~filters.COMMAND, get_start_date)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    # Delete Event Conversation
    delete_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🗑 Delete Event$"), delete_event_menu),
                      CommandHandler("delete", delete_event_command)],
        states={
            DELETE_BUTTON: [CallbackQueryHandler(delete_event_button)],
            DELETE_EVENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_event_by_name)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(add_conv)
    app.add_handler(delete_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_choice))
    app.add_handler(CommandHandler("listevents", list_events))

    # Scheduler for daily reminders at 9 AM
    scheduler = AsyncIOScheduler()
    scheduler.start()
    for e in events:
        scheduler.add_job(send_reminder, 'cron', hour=9, args=[e["chat_id"], e])

    print("Bot started...")
    await app.run_polling()

# ---------------------
# Entry point
# ---------------------
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
