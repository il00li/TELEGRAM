import logging
import sqlite3
import asyncio
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError
import threading
from flask import Flask, request
import signal
import sys

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8071576925:AAGgx_Jkuu-mRpjdMKiOQCDkkVQskXQYhQo")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "7251748706"))
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "51444506-bffefcaf12816bd85a20222d1")
PIXABAY_API_URL = "https://pixabay.com/api/"

# Database setup
class Database:
    def __init__(self, db_name='bot_database.db'):
        self.db_name = db_name
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                join_date TEXT,
                is_banned INTEGER DEFAULT 0,
                search_count INTEGER DEFAULT 0
            )
        ''')
        
        # Mandatory channels table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mandatory_channels (
                channel_id TEXT PRIMARY KEY,
                channel_username TEXT,
                added_by INTEGER,
                added_date TEXT
            )
        ''')
        
        # Search history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query TEXT,
                search_type TEXT,
                timestamp TEXT,
                results_count INTEGER
            )
        ''')
        
        # User sessions table for managing search states
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                user_id INTEGER PRIMARY KEY,
                current_query TEXT,
                current_type TEXT,
                current_results TEXT,
                current_index INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Add or update user in database"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name, join_date, search_count)
            VALUES (?, ?, ?, ?, ?, COALESCE((SELECT search_count FROM users WHERE user_id = ?), 0))
        ''', (user_id, username or "", first_name or "", last_name or "", datetime.now().isoformat(), user_id))
        
        conn.commit()
        conn.close()
    
    def is_user_banned(self, user_id: int) -> bool:
        """Check if user is banned"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result and result[0] == 1
    
    def ban_user(self, user_id: int):
        """Ban a user"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
    
    def unban_user(self, user_id: int):
        """Unban a user"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
    
    def add_mandatory_channel(self, channel_id: str, channel_username: str, added_by: int):
        """Add mandatory channel"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO mandatory_channels 
            (channel_id, channel_username, added_by, added_date)
            VALUES (?, ?, ?, ?)
        ''', (channel_id, channel_username, added_by, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def remove_mandatory_channel(self, channel_id: str):
        """Remove mandatory channel"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM mandatory_channels WHERE channel_id = ?', (channel_id,))
        
        conn.commit()
        conn.close()
    
    def get_mandatory_channels(self) -> List[Dict]:
        """Get all mandatory channels"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('SELECT channel_id, channel_username FROM mandatory_channels')
        results = cursor.fetchall()
        
        conn.close()
        return [{"id": r[0], "username": r[1]} for r in results]
    
    def increment_search_count(self, user_id: int):
        """Increment user's search count"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE users SET search_count = search_count + 1 WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
    
    def add_search_history(self, user_id: int, query: str, search_type: str, results_count: int):
        """Add search to history"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO search_history (user_id, query, search_type, timestamp, results_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, query, search_type, datetime.now().isoformat(), results_count))
        
        conn.commit()
        conn.close()
    
    def get_statistics(self) -> Dict:
        """Get bot statistics"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Total users
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        # Total searches
        cursor.execute('SELECT SUM(search_count) FROM users')
        total_searches = cursor.fetchone()[0] or 0
        
        # Mandatory channels count
        cursor.execute('SELECT COUNT(*) FROM mandatory_channels')
        mandatory_channels_count = cursor.fetchone()[0]
        
        # Banned users count
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
        banned_users = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_users": total_users,
            "total_searches": total_searches,
            "mandatory_channels": mandatory_channels_count,
            "banned_users": banned_users
        }
    
    def set_user_session(self, user_id: int, query: str = None, search_type: str = None, results: str = None, index: int = 0):
        """Set user session data"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_sessions 
            (user_id, current_query, current_type, current_results, current_index)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, query or "", search_type or "", results or "", index))
        
        conn.commit()
        conn.close()
    
    def get_user_session(self, user_id: int) -> Optional[Dict]:
        """Get user session data"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        cursor.execute('SELECT current_query, current_type, current_results, current_index FROM user_sessions WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            return {
                "query": result[0],
                "type": result[1],
                "results": result[2],
                "index": result[3]
            }
        return None

# Initialize database
db = Database()

class PixabayAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = PIXABAY_API_URL
    
    def search(self, query: str, search_type: str = "photo", per_page: int = 20) -> Dict:
        """Search Pixabay API"""
        try:
            params = {
                "key": self.api_key,
                "q": query,
                "per_page": per_page,
                "safesearch": "true"
            }
            
            # Use different endpoints for video and music
            if search_type == "video":
                url = "https://pixabay.com/api/videos/"
            elif search_type == "music":
                url = "https://pixabay.com/api/music/"
            else:
                url = self.base_url
                if search_type == "vector":
                    params["image_type"] = "vector"
                elif search_type == "illustration":
                    params["image_type"] = "illustration"
                elif search_type == "photo":
                    params["image_type"] = "photo"
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Pixabay API error: {e}")
            return {"hits": [], "total": 0}

# Initialize Pixabay API
pixabay = PixabayAPI(PIXABAY_API_KEY)

class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.bot = Bot(token)
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup command and callback handlers"""
        # Add error handler
        self.application.add_error_handler(self.error_handler)
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("admin", self.admin_command))
        
        # Callback query handlers
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        
        # Message handlers
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        user_id = user.id
        
        # Add user to database
        db.add_user(user_id, user.username or "", user.first_name or "", user.last_name or "")
        
        # Check if user is banned
        if db.is_user_banned(user_id):
            await update.message.reply_text("❌ أنت محظور من استخدام هذا البوت")
            return
        
        # Check subscription to mandatory channels
        mandatory_channels = db.get_mandatory_channels()
        
        if not mandatory_channels:
            # No mandatory channels, proceed directly
            await self.show_main_menu(update, context)
            return
        
        # Check subscription status
        unsubscribed_channels = []
        for channel in mandatory_channels:
            try:
                member = await self.bot.get_chat_member(channel["id"], user_id)
                if member.status in ['left', 'kicked']:
                    unsubscribed_channels.append(channel)
            except TelegramError:
                unsubscribed_channels.append(channel)
        
        if unsubscribed_channels:
            await self.show_subscription_message(update, context, unsubscribed_channels)
        else:
            await self.show_main_menu(update, context)
    
    async def show_subscription_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, channels: List[Dict]):
        """Show subscription requirement message"""
        ascii_art = """   (•_•)  
  <)   )╯  
   /   \\  
🎧 | اشترك في القنوات اولا"""
        
        # Create keyboard with channel buttons
        keyboard = []
        for channel in channels:
            keyboard.append([InlineKeyboardButton(
                f"📢 {channel['username']}", 
                url=f"https://t.me/{channel['username']}"
            )])
        
        # Add verify button
        keyboard.append([InlineKeyboardButton("تحقق | Verify ✅", callback_data="verify_subscription")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=ascii_art,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=ascii_art,
                reply_markup=reply_markup
            )
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu after successful verification"""
        ascii_art = """(⊙_☉)  
  /|\\
  / \\
هل تريد بدء بحث؟!"""
        
        keyboard = [
            [InlineKeyboardButton("بدء البحث 🎧", callback_data="start_search")],
            [InlineKeyboardButton("نوع البحث💐", callback_data="search_type_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=ascii_art,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=ascii_art,
                reply_markup=reply_markup
            )
    
    async def show_search_type_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show search type selection menu"""
        user_id = update.effective_user.id
        session = db.get_user_session(user_id) or {}
        current_type = session.get("type", "photo")
        
        search_types = [
            ("photo", "صور"),
            ("illustration", "رسوم توضيحية"),
            ("vector", "فيكتور"),
            ("video", "فيديو"),
            ("music", "موسيقى"),
            ("gif", "صور متحركة")
        ]
        
        keyboard = []
        for type_key, type_name in search_types:
            marker = "👻" if type_key == current_type else ""
            keyboard.append([InlineKeyboardButton(
                f"{type_name} {marker}", 
                callback_data=f"set_type_{type_key}"
            )])
        
        keyboard.append([InlineKeyboardButton(
            f"بدء البحث عن {dict(search_types)[current_type]} 🔍", 
            callback_data="start_typed_search"
        )])
        keyboard.append([InlineKeyboardButton("🔙 الرجوع", callback_data="back_to_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            text="اختر نوع البحث:",
            reply_markup=reply_markup
        )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        data = query.data
        user_id = update.effective_user.id
        
        # Handle callback query answer with error handling
        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"Failed to answer callback query: {e}")
            # Continue processing even if answer fails
        
        # Check if user is banned
        if db.is_user_banned(user_id):
            await query.edit_message_text("❌ أنت محظور من استخدام هذا البوت")
            return
        
        if data == "verify_subscription":
            # Re-check subscription
            mandatory_channels = db.get_mandatory_channels()
            unsubscribed_channels = []
            
            for channel in mandatory_channels:
                try:
                    member = await self.bot.get_chat_member(channel["id"], user_id)
                    if member.status in ['left', 'kicked']:
                        unsubscribed_channels.append(channel)
                except TelegramError:
                    unsubscribed_channels.append(channel)
            
            if unsubscribed_channels:
                await self.show_subscription_message(update, context, unsubscribed_channels)
            else:
                await self.show_main_menu(update, context)
        
        elif data == "start_search":
            await query.edit_message_text("أرسل كلمة البحث:")
            context.user_data["waiting_for_search"] = True
        
        elif data == "search_type_menu":
            await self.show_search_type_menu(update, context)
        
        elif data.startswith("set_type_"):
            search_type = data.replace("set_type_", "")
            db.set_user_session(user_id, search_type=search_type)
            await self.show_search_type_menu(update, context)
        
        elif data == "start_typed_search":
            session = db.get_user_session(user_id)
            if session and session.get("type"):
                await query.edit_message_text(f"أرسل كلمة البحث عن {session['type']}:")
                context.user_data["waiting_for_search"] = True
                context.user_data["search_type"] = session["type"]
            else:
                await query.edit_message_text("حدد نوع البحث أولاً")
        
        elif data == "back_to_main":
            await self.show_main_menu(update, context)
        
        elif data.startswith("nav_"):
            await self.handle_navigation(update, context, data)
        
        elif data == "select_result":
            await self.select_result(update, context)
        
        elif data.startswith("admin_"):
            if user_id == ADMIN_ID:
                await self.handle_admin_callback(update, context, data)
        
        elif data in ["add_channel", "remove_channel"]:
            if user_id == ADMIN_ID:
                await self.handle_admin_callback(update, context, data)
    
    async def handle_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle navigation between search results"""
        user_id = update.effective_user.id
        session = db.get_user_session(user_id)
        
        if not session or not session["results"]:
            await update.callback_query.edit_message_text("لا توجد نتائج للتنقل فيها")
            return
        
        results = json.loads(session["results"])
        current_index = session["index"]
        
        if data == "nav_next":
            new_index = (current_index + 1) % len(results)
        elif data == "nav_prev":
            new_index = (current_index - 1) % len(results)
        else:
            return
        
        # Update session with new index
        db.set_user_session(user_id, session["query"], session["type"], session["results"], new_index)
        
        # Show new result
        await self.show_search_result(update, context, results, new_index, edit_message=True)
    
    async def select_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Select current result and remove navigation buttons"""
        user_id = update.effective_user.id
        session = db.get_user_session(user_id)
        
        if not session or not session["results"]:
            await update.callback_query.edit_message_text("لا توجد نتائج محددة")
            return
        
        results = json.loads(session["results"])
        current_index = session["index"]
        result = results[current_index]
        search_type = session.get("type", "photo")
        
        # Prepare final caption
        final_caption = f"✅ تم الاختيار\n🏷️ {result.get('tags', 'غير محدد')}"
        
        chat_id = update.callback_query.message.chat_id
        
        try:
            # Delete the message with navigation buttons
            await update.callback_query.message.delete()
            
            # Send the selected media without navigation buttons
            if search_type == "video" and result.get('videos'):
                video_url = result['videos'].get('medium', {}).get('url', '')
                if video_url:
                    await self.bot.send_video(
                        chat_id=chat_id,
                        video=video_url,
                        caption=final_caption
                    )
                else:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=f"{final_caption}\n❌ فيديو غير متوفر"
                    )
            elif search_type == "music":
                music_url = result.get('previewURL') or result.get('webformatURL', '')
                if music_url:
                    await self.bot.send_audio(
                        chat_id=chat_id,
                        audio=music_url,
                        caption=final_caption
                    )
                else:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=f"{final_caption}\n🎵 موسيقى غير متوفرة للتشغيل"
                    )
            elif search_type == "gif":
                gif_url = result.get('webformatURL', '')
                if gif_url and gif_url.lower().endswith('.gif'):
                    await self.bot.send_animation(
                        chat_id=chat_id,
                        animation=gif_url,
                        caption=final_caption
                    )
                else:
                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=gif_url,
                        caption=final_caption
                    )
            else:
                # For photos, illustrations, vectors
                photo_url = result.get('webformatURL', '')
                if photo_url:
                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_url,
                        caption=final_caption
                    )
                else:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=f"{final_caption}\n❌ صورة غير متوفرة"
                    )
                    
        except Exception as e:
            logger.error(f"Error sending selected media: {e}")
            # Fallback to editing the message
            fallback_text = f"{final_caption}\n"
            if result.get('webformatURL'):
                fallback_text += f"🔗 {result['webformatURL']}"
            elif result.get('videos'):
                video_url = result['videos'].get('medium', {}).get('url', '')
                if video_url:
                    fallback_text += f"🎬 {video_url}"
            
            await update.callback_query.edit_message_text(text=fallback_text)
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        # Handle specific callback query errors
        if "Query is too old" in str(context.error) or "query id is invalid" in str(context.error):
            logger.info("Callback query timeout - ignoring old query")
            return
        
        # For other errors, try to send a message to the user if possible
        try:
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="حدث خطأ مؤقت. حاول مرة أخرى."
                )
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        if not update.message or not update.message.text:
            return
            
        user_id = update.effective_user.id
        
        # Check if user is banned
        if db.is_user_banned(user_id):
            await update.message.reply_text("❌ أنت محظور من استخدام هذا البوت")
            return
        
        # Handle admin actions first
        if user_id == ADMIN_ID and context.user_data.get("admin_action"):
            await self.handle_admin_message(update, context)
            return
        
        if context.user_data.get("waiting_for_search"):
            query_text = update.message.text
            search_type = context.user_data.get("search_type", "photo")
            
            # Clear waiting state
            context.user_data["waiting_for_search"] = False
            context.user_data.pop("search_type", None)
            
            # Perform search
            await self.perform_search(update, context, query_text, search_type)
    
    async def perform_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str, search_type: str):
        """Perform search on Pixabay"""
        user_id = update.effective_user.id
        
        # Send searching message
        search_msg = await update.message.reply_text("🔍 جاري البحث...")
        
        # Search Pixabay
        results = pixabay.search(query, search_type)
        
        if not results.get("hits"):
            await search_msg.edit_text("""   ¯\\_(ツ)_/¯
    كلماتك غريبة يا غلام""")
            return
        
        hits = results["hits"]
        
        # Save search data
        db.increment_search_count(user_id)
        db.add_search_history(user_id, query, search_type, len(hits))
        db.set_user_session(user_id, query, search_type, json.dumps(hits), 0)
        
        # Show first result
        await self.show_search_result(update, context, hits, 0, search_msg)
    
    async def show_search_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE, results: List[Dict], index: int, message=None, edit_message=False):
        """Show search result with navigation"""
        result = results[index]
        
        # Create navigation keyboard
        keyboard = [
            [
                InlineKeyboardButton("« السابق", callback_data="nav_prev"),
                InlineKeyboardButton("التالي »", callback_data="nav_next")
            ],
            [InlineKeyboardButton("اختيار🥇", callback_data="select_result")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Prepare caption text
        caption_text = f"النتيجة {index + 1} من {len(results)}\n"
        caption_text += f"🏷️ {result.get('tags', 'غير محدد')}"
        
        # Get the current session to determine search type
        user_id = update.effective_user.id
        session = db.get_user_session(user_id)
        search_type = session.get("type", "photo") if session else "photo"
        
        # Determine chat context
        if edit_message and update.callback_query:
            chat_id = update.callback_query.message.chat_id
            message_id = update.callback_query.message.message_id
        elif message:
            chat_id = message.chat_id
            message_id = message.message_id
        else:
            chat_id = update.message.chat_id
            message_id = None
        
        try:
            # Delete the old message if it exists
            if edit_message and update.callback_query:
                await update.callback_query.message.delete()
            elif message:
                await message.delete()
            
            # Send media based on type
            if search_type == "video" and result.get('videos'):
                video_url = result['videos'].get('medium', {}).get('url', '')
                if video_url:
                    await self.bot.send_video(
                        chat_id=chat_id,
                        video=video_url,
                        caption=caption_text,
                        reply_markup=reply_markup
                    )
                else:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=f"{caption_text}\n❌ فيديو غير متوفر",
                        reply_markup=reply_markup
                    )
            elif search_type == "music":
                # For music, send as audio if available, otherwise show info
                music_url = result.get('previewURL') or result.get('webformatURL', '')
                if music_url:
                    await self.bot.send_audio(
                        chat_id=chat_id,
                        audio=music_url,
                        caption=caption_text,
                        reply_markup=reply_markup
                    )
                else:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=f"{caption_text}\n🎵 موسيقى غير متوفرة للتشغيل",
                        reply_markup=reply_markup
                    )
            elif search_type == "gif":
                # For GIFs, try to send as animation
                gif_url = result.get('webformatURL', '')
                if gif_url and gif_url.lower().endswith('.gif'):
                    await self.bot.send_animation(
                        chat_id=chat_id,
                        animation=gif_url,
                        caption=caption_text,
                        reply_markup=reply_markup
                    )
                else:
                    # Fallback to photo if not a proper GIF
                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=gif_url,
                        caption=caption_text,
                        reply_markup=reply_markup
                    )
            else:
                # For photos, illustrations, vectors
                photo_url = result.get('webformatURL', '')
                if photo_url:
                    await self.bot.send_photo(
                        chat_id=chat_id,
                        photo=photo_url,
                        caption=caption_text,
                        reply_markup=reply_markup
                    )
                else:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=f"{caption_text}\n❌ صورة غير متوفرة",
                        reply_markup=reply_markup
                    )
                    
        except Exception as e:
            logger.error(f"Error sending media: {e}")
            # Fallback to text message with URL
            fallback_text = f"{caption_text}\n"
            if result.get('webformatURL'):
                fallback_text += f"🔗 {result['webformatURL']}"
            elif result.get('videos'):
                video_url = result['videos'].get('medium', {}).get('url', '')
                if video_url:
                    fallback_text += f"🎬 {video_url}"
            
            await self.bot.send_message(
                chat_id=chat_id,
                text=fallback_text,
                reply_markup=reply_markup
            )
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin commands"""
        if not update.message:
            return
            
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ ليس لديك صلاحية للوصول للوحة الإدارة")
            return
        
        keyboard = [
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
            [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban")],
            [InlineKeyboardButton("✅ إلغاء حظر مستخدم", callback_data="admin_unban")],
            [InlineKeyboardButton("📢 إدارة القنوات", callback_data="admin_channels")],
            [InlineKeyboardButton("📤 إرسال إشعار", callback_data="admin_broadcast")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔧 لوحة التحكم الإدارية",
            reply_markup=reply_markup
        )
    
    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Handle admin callback queries"""
        query = update.callback_query
        if not query:
            return
            
        if data == "admin_stats":
            stats = db.get_statistics()
            stats_text = f"""📊 إحصائيات البوت:

👥 عدد المستخدمين: {stats['total_users']}
🔍 عدد عمليات البحث: {stats['total_searches']}
📢 القنوات الإجبارية: {stats['mandatory_channels']}
🚫 المستخدمون المحظورون: {stats['banned_users']}"""
            
            await query.edit_message_text(stats_text)
        
        elif data == "admin_ban":
            await query.edit_message_text("أرسل معرف المستخدم لحظره:")
            context.user_data["admin_action"] = "ban_user"
        
        elif data == "admin_unban":
            await query.edit_message_text("أرسل معرف المستخدم لإلغاء حظره:")
            context.user_data["admin_action"] = "unban_user"
        
        elif data == "admin_channels":
            channels = db.get_mandatory_channels()
            if channels:
                channels_text = "📢 القنوات الإجبارية:\n\n"
                for i, channel in enumerate(channels, 1):
                    channels_text += f"{i}. @{channel['username']} ({channel['id']})\n"
            else:
                channels_text = "لا توجد قنوات إجبارية"
            
            keyboard = [
                [InlineKeyboardButton("➕ إضافة قناة", callback_data="add_channel")],
                [InlineKeyboardButton("➖ حذف قناة", callback_data="remove_channel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(channels_text, reply_markup=reply_markup)
        
        elif data == "admin_broadcast":
            await query.edit_message_text("أرسل الرسالة للبث لجميع المستخدمين:")
            context.user_data["admin_action"] = "broadcast"
        
        elif data == "add_channel":
            await query.edit_message_text("أرسل معرف القناة (مثال: @channel_name):")
            context.user_data["admin_action"] = "add_channel"
        
        elif data == "remove_channel":
            await query.edit_message_text("أرسل معرف القناة لحذفها:")
            context.user_data["admin_action"] = "remove_channel"
    
    async def handle_admin_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin messages"""
        if not update.message or not update.message.text:
            return
            
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            return
        
        action = context.user_data.get("admin_action")
        text = update.message.text
        
        if action == "ban_user":
            try:
                target_user_id = int(text)
                db.ban_user(target_user_id)
                await update.message.reply_text(f"✅ تم حظر المستخدم {target_user_id}")
            except ValueError:
                await update.message.reply_text("❌ معرف المستخدم غير صحيح")
            context.user_data.pop("admin_action", None)
        
        elif action == "unban_user":
            try:
                target_user_id = int(text)
                db.unban_user(target_user_id)
                await update.message.reply_text(f"✅ تم إلغاء حظر المستخدم {target_user_id}")
            except ValueError:
                await update.message.reply_text("❌ معرف المستخدم غير صحيح")
            context.user_data.pop("admin_action", None)
        
        elif action == "add_channel":
            if text.startswith("@"):
                channel_username = text[1:]  # Remove @
                channel_id = text
                db.add_mandatory_channel(channel_id, channel_username, user_id)
                await update.message.reply_text(f"✅ تم إضافة القناة {text}")
            else:
                await update.message.reply_text("❌ يجب أن يبدأ معرف القناة بـ @")
            context.user_data.pop("admin_action", None)
        
        elif action == "remove_channel":
            db.remove_mandatory_channel(text)
            await update.message.reply_text(f"✅ تم حذف القناة {text}")
            context.user_data.pop("admin_action", None)
        
        elif action == "broadcast":
            # Get all users
            conn = sqlite3.connect(db.db_name)
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE is_banned = 0')
            users = cursor.fetchall()
            conn.close()
            
            success_count = 0
            for user_tuple in users:
                try:
                    await self.bot.send_message(chat_id=user_tuple[0], text=text)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send message to {user_tuple[0]}: {e}")
            
            await update.message.reply_text(f"✅ تم إرسال الرسالة لـ {success_count} مستخدم")
            context.user_data.pop("admin_action", None)

# Initialize bot
bot = TelegramBot(BOT_TOKEN)

# Check if we're running on Render (webhook mode only)
def is_render_environment():
    """Check if running on Render platform"""
    return os.environ.get('RENDER_EXTERNAL_URL') is not None or os.environ.get('RENDER') is not None

async def main():
    """Main function - Render webhook mode only"""
    logger.info("🚀 Starting Pixabay Bot - Render Deployment Only")
    
    # Only proceed if we're on Render
    if not is_render_environment():
        logger.error("❌ This bot is configured to run only on Render.com")
        logger.error("❌ Please deploy this bot to Render.com to use it")
        return
    
    # Initialize bot
    await bot.bot.initialize()
    await bot.application.initialize()
    logger.info("🤖 Bot initialized")
    
    # Set webhook for Render deployment
    webhook_url = "https://telegram-oihp.onrender.com/webhook"
    
    try:
        # Delete existing webhook first
        await bot.bot.delete_webhook()
        await asyncio.sleep(1)
        
        # Set new webhook
        result = await bot.bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"]
        )
        
        if result:
            logger.info(f"✅ Webhook set successfully: {webhook_url}")
        else:
            logger.error(f"❌ Failed to set webhook: {webhook_url}")
            
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
    
    await bot.application.start()
    logger.info("🚀 Bot started successfully in webhook mode on Render")
    
    # Start Flask webhook server
    from flask import Flask, request
    app = Flask(__name__)
    
    @app.route('/webhook', methods=['POST'])
    def webhook():
        """Handle webhook requests"""
        try:
            update_data = request.get_json(force=True)
            if not update_data:
                logger.warning("Received empty webhook data")
                return 'OK'
                
            logger.info(f"Received webhook update: {update_data.get('update_id', 'unknown')}")
            
            try:
                update = Update.de_json(update_data, bot.bot)
                if update:
                    # Handle the update in a new thread to avoid blocking
                    def process_update():
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(bot.application.process_update(update))
                            loop.close()
                        except Exception as e:
                            logger.error(f"Error processing update in thread: {e}")
                    
                    thread = threading.Thread(target=process_update, daemon=True)
                    thread.start()
                    
            except Exception as e:
                logger.error(f"Error creating update object: {e}")
                
            return 'OK', 200
            
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return 'Error', 500
    
    @app.route('/', methods=['GET'])
    def home():
        """Home page for Render deployment"""
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Pixabay Search Bot - Render Only</title>
            <meta charset="UTF-8">
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f0f2f5; }
                .container { max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                h1 { color: #2c3e50; }
                .ascii { font-family: monospace; white-space: pre; margin: 20px 0; }
                .feature { margin: 10px 0; padding: 10px; background: #ecf0f1; border-radius: 5px; }
                .status { color: #27ae60; font-weight: bold; }
                .platform { color: #8e44ad; font-weight: bold; margin: 10px 0; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 Pixabay Search Bot</h1>
                <div class="ascii">   (•_•)  
          <)   )╯  
           /   \\  
        🎧 | Running on Render Only!</div>
                
                <div class="status">✅ Bot Status: Online</div>
                <div class="platform">🚀 Deployed on Render.com</div>
                <div class="platform">🔗 Webhook: https://telegram-oihp.onrender.com/webhook</div>
                
                <h3>Features:</h3>
                <div class="feature">🔍 Multi-media Search (Photos, Videos, Music, GIFs)</div>
                <div class="feature">📢 Mandatory Channel Subscription</div>
                <div class="feature">⬅️➡️ Navigate Between Results</div>
                <div class="feature">🔧 Admin Panel (Ban/Unban, Statistics, Broadcasting)</div>
                <div class="feature">📊 User Analytics & Search Tracking</div>
                
                <p>Find the bot on Telegram and send <code>/start</code> to begin!</p>
            </div>
        </body>
        </html>
        '''
    
    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint"""
        return 'OK'
    
    # Run Flask server
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

if __name__ == '__main__':
    if is_render_environment():
        asyncio.run(main())
    else:
        print("❌ هذا البوت مخصص للعمل على Render.com فقط")
        print("❌ يرجى نشر البوت على Render.com لاستخدامه") 
``'
