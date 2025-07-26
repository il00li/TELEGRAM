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
BOT_TOKEN = "8071576925:AAGgx_Jkuu-mRpjdMKiOQCDkkVQskXQYhQo"
ADMIN_ID = 7251748706
PIXABAY_API_KEY = "51444506-bffefcaf12816bd85a20222d1"
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
        ''', (user_id, username, first_name, last_name, datetime.now().isoformat(), user_id))
        
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
        ''', (user_id, query, search_type, results, index))
        
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
            # Map search types to Pixabay parameters
            type_mapping = {
                "photo": {"image_type": "photo"},
                "illustration": {"image_type": "illustration"},
                "vector": {"image_type": "vector"},
                "gif": {"image_type": "all", "category": "computer"},
                "video": {},
                "music": {}
            }
            
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
                params.update(type_mapping.get(search_type, {}))
            
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
        db.add_user(user_id, user.username, user.first_name, user.last_name)
        
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
🎧 | اشترك في القنوات اولا """
        
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
        
        await query.answer()
        
        # Check if user is banned
        if db.is_user_banned(user_id):
            await query.edit_message_text("❌ أنت محظور من استخدام هذا البوت")
            return
        
        if data == "verify_subscription":
            await self.verify_subscription(update, context)
        elif data == "start_search":
            await self.start_search_process(update, context)
        elif data == "search_type_menu":
            await self.show_search_type_menu(update, context)
        elif data.startswith("set_type_"):
            search_type = data.replace("set_type_", "")
            db.set_user_session(user_id, search_type=search_type)
            await self.show_search_type_menu(update, context)
        elif data == "start_typed_search":
            await self.start_search_process(update, context, typed=True)
        elif data == "back_to_main":
            await self.show_main_menu(update, context)
        elif data == "next_result":
            await self.navigate_results(update, context, direction="next")
        elif data == "prev_result":
            await self.navigate_results(update, context, direction="prev")
        elif data == "select_result":
            await self.select_current_result(update, context)
        elif data.startswith("admin_"):
            await self.handle_admin_callback(update, context)
    
    async def verify_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Verify user subscription to mandatory channels"""
        user_id = update.effective_user.id
        mandatory_channels = db.get_mandatory_channels()
        
        if not mandatory_channels:
            await self.show_main_menu(update, context)
            return
        
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
    
    async def start_search_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE, typed: bool = False):
        """Start the search process"""
        user_id = update.effective_user.id
        
        if typed:
            session = db.get_user_session(user_id)
            if session and session.get("type"):
                search_type = session["type"]
                await update.callback_query.edit_message_text(
                    f"أرسل كلمة البحث للبحث عن {search_type}:"
                )
            else:
                await update.callback_query.edit_message_text("أرسل كلمة البحث:")
        else:
            await update.callback_query.edit_message_text("أرسل كلمة البحث:")
        
        # Set user state to waiting for query
        context.user_data["waiting_for_query"] = True
        context.user_data["search_typed"] = typed
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        user_id = update.effective_user.id
        
        # Check if user is banned
        if db.is_user_banned(user_id):
            await update.message.reply_text("❌ أنت محظور من استخدام هذا البوت")
            return
        
        # Check if waiting for search query
        if context.user_data.get("waiting_for_query"):
            await self.process_search_query(update, context)
            return
        
        # Check if waiting for admin input
        if context.user_data.get("waiting_for_admin_input"):
            await self.handle_admin_input(update, context)
            return
        
        # Default response
        await update.message.reply_text("استخدم /start لبدء استخدام البوت")
    
    async def process_search_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process search query and show results"""
        user_id = update.effective_user.id
        query_text = update.message.text
        
        # Clear waiting state
        context.user_data["waiting_for_query"] = False
        
        # Determine search type
        search_type = "photo"  # default
        if context.user_data.get("search_typed"):
            session = db.get_user_session(user_id)
            if session and session.get("type"):
                search_type = session["type"]
        
        # Show loading message
        loading_msg = await update.message.reply_text("🔍 جاري البحث...")
        
        # Search Pixabay
        results = pixabay.search(query_text, search_type)
        
        if not results["hits"]:
            ascii_art = """   ¯\\_(ツ)_/¯
    كلماتك غريبة يا غلام"""
            await loading_msg.edit_text(ascii_art)
            return
        
        # Save search to database
        db.increment_search_count(user_id)
        db.add_search_history(user_id, query_text, search_type, len(results["hits"]))
        
        # Save results to session
        db.set_user_session(user_id, query_text, search_type, json.dumps(results["hits"]), 0)
        
        # Show first result
        await self.show_search_result(loading_msg, user_id, 0)
    
    async def show_search_result(self, message, user_id: int, index: int):
        """Show a search result with navigation buttons"""
        session = db.get_user_session(user_id)
        if not session or not session["results"]:
            await message.edit_text("لا توجد نتائج")
            return
        
        results = json.loads(session["results"])
        if index >= len(results) or index < 0:
            return
        
        result = results[index]
        
        # Update session index
        db.set_user_session(user_id, session["query"], session["type"], session["results"], index)
        
        # Create navigation keyboard
        keyboard = []
        nav_row = []
        
        if index > 0:
            nav_row.append(InlineKeyboardButton("«", callback_data="prev_result"))
        
        nav_row.append(InlineKeyboardButton(f"{index + 1}/{len(results)}", callback_data="noop"))
        
        if index < len(results) - 1:
            nav_row.append(InlineKeyboardButton("»", callback_data="next_result"))
        
        keyboard.append(nav_row)
        keyboard.append([InlineKeyboardButton("اختيار🥇", callback_data="select_result")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Format result message based on type
        if session["type"] == "video":
            caption = f"🎬 **{result.get('tags', 'فيديو')}**\n"
            caption += f"👀 المشاهدات: {result.get('views', 0):,}\n"
            caption += f"⏱ المدة: {result.get('duration', 0)} ثانية\n"
            caption += f"🔗 [رابط التحميل]({result['videos']['medium']['url']})"
            
            try:
                await message.edit_text(caption, reply_markup=reply_markup, parse_mode='Markdown')
            except:
                await message.edit_text(caption, reply_markup=reply_markup)
                
        elif session["type"] == "music":
            caption = f"🎵 **{result.get('tags', 'موسيقى')}**\n"
            caption += f"👀 المشاهدات: {result.get('views', 0):,}\n"
            caption += f"⏱ المدة: {result.get('duration', 0)} ثانية\n"
            caption += f"🔗 [رابط التحميل]({result['audio']['mp3']})"
            
            try:
                await message.edit_text(caption, reply_markup=reply_markup, parse_mode='Markdown')
            except:
                await message.edit_text(caption, reply_markup=reply_markup)
        else:
            # Image types (photo, illustration, vector, gif)
            image_url = result.get('webformatURL', result.get('largeImageURL', ''))
            caption = f"🖼 **{result.get('tags', 'صورة')}**\n"
            caption += f"👀 المشاهدات: {result.get('views', 0):,}\n"
            caption += f"💖 الإعجابات: {result.get('likes', 0):,}\n"
            caption += f"📥 التحميلات: {result.get('downloads', 0):,}"
            
            try:
                if hasattr(message, 'edit_caption'):
                    await message.edit_caption(caption=caption, reply_markup=reply_markup, parse_mode='Markdown')
                else:
                    # Delete old message and send new one with photo
                    await message.delete()
                    await message.reply_photo(
                        photo=image_url,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Error showing image result: {e}")
                try:
                    await message.edit_text(caption, reply_markup=reply_markup, parse_mode='Markdown')
                except:
                    await message.edit_text(caption, reply_markup=reply_markup)
    
    async def navigate_results(self, update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str):
        """Navigate through search results"""
        user_id = update.effective_user.id
        session = db.get_user_session(user_id)
        
        if not session or not session["results"]:
            return
        
        current_index = session["index"]
        results = json.loads(session["results"])
        
        if direction == "next" and current_index < len(results) - 1:
            new_index = current_index + 1
        elif direction == "prev" and current_index > 0:
            new_index = current_index - 1
        else:
            await update.callback_query.answer("لا توجد نتائج أخرى في هذا الاتجاه")
            return
        
        await self.show_search_result(update.callback_query, user_id, new_index)
    
    async def select_current_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Select current result and remove navigation buttons"""
        user_id = update.effective_user.id
        session = db.get_user_session(user_id)
        
        if not session or not session["results"]:
            return
        
        results = json.loads(session["results"])
        current_result = results[session["index"]]
        
        # Remove keyboard and show selected result
        if session["type"] in ["video", "music"]:
            caption = f"✅ **تم الاختيار**\n\n"
            if session["type"] == "video":
                caption += f"🎬 {current_result.get('tags', 'فيديو')}\n"
                caption += f"🔗 [رابط التحميل]({current_result['videos']['medium']['url']})"
            else:
                caption += f"🎵 {current_result.get('tags', 'موسيقى')}\n"
                caption += f"🔗 [رابط التحميل]({current_result['audio']['mp3']})"
            
            await update.callback_query.edit_message_text(caption, parse_mode='Markdown')
        else:
            # For images, keep the photo but remove keyboard
            caption = f"✅ **تم الاختيار**\n\n🖼 {current_result.get('tags', 'صورة')}"
            try:
                await update.callback_query.edit_message_caption(
                    caption=caption, 
                    parse_mode='Markdown'
                )
            except:
                await update.callback_query.edit_message_caption(caption=caption)
        
        await update.callback_query.answer("✅ تم اختيار النتيجة")
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin command"""
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await update.message.reply_text("❌ ليس لديك صلاحية للوصول إلى هذا الأمر")
            return
        
        keyboard = [
            [InlineKeyboardButton("👤 إدارة المستخدمين", callback_data="admin_users")],
            [InlineKeyboardButton("📢 إدارة القنوات الإجبارية", callback_data="admin_channels")],
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
            [InlineKeyboardButton("📢 إرسال إشعار", callback_data="admin_broadcast")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔧 **لوحة التحكم الإدارية**\n\nاختر العملية التي تريد تنفيذها:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin callback queries"""
        query = update.callback_query
        data = query.data
        user_id = update.effective_user.id
        
        if user_id != ADMIN_ID:
            await query.answer("❌ ليس لديك صلاحية")
            return
        
        if data == "admin_users":
            await self.show_user_management(update, context)
        elif data == "admin_channels":
            await self.show_channel_management(update, context)
        elif data == "admin_stats":
            await self.show_statistics(update, context)
        elif data == "admin_broadcast":
            await self.start_broadcast(update, context)
        elif data == "admin_ban_user":
            await self.start_ban_user(update, context)
        elif data == "admin_unban_user":
            await self.start_unban_user(update, context)
        elif data == "admin_add_channel":
            await self.start_add_channel(update, context)
        elif data == "admin_remove_channel":
            await self.start_remove_channel(update, context)
    
    async def show_user_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user management options"""
        keyboard = [
            [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban_user")],
            [InlineKeyboardButton("✅ إلغاء حظر مستخدم", callback_data="admin_unban_user")],
            [InlineKeyboardButton("🔙 الرجوع", callback_data="admin_back")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            "👤 **إدارة المستخدمين**\n\nاختر العملية:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_channel_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show channel management options"""
        channels = db.get_mandatory_channels()
        
        text = "📢 **إدارة القنوات الإجبارية**\n\n"
        text += f"عدد القنوات الحالية: {len(channels)}\n\n"
        
        if channels:
            text += "القنوات المضافة:\n"
            for i, channel in enumerate(channels, 1):
                text += f"{i}. @{channel['username']} (`{channel['id']}`)\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ إضافة قناة", callback_data="admin_add_channel")],
            [InlineKeyboardButton("➖ إزالة قناة", callback_data="admin_remove_channel")],
            [InlineKeyboardButton("🔙 الرجوع", callback_data="admin_back")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def show_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot statistics"""
        stats = db.get_statistics()
        
        text = "📊 **إحصائيات البوت**\n\n"
        text += f"👥 إجمالي المستخدمين: {stats['total_users']:,}\n"
        text += f"🔍 إجمالي عمليات البحث: {stats['total_searches']:,}\n"
        text += f"📢 القنوات الإجبارية: {stats['mandatory_channels']}\n"
        text += f"🚫 المستخدمون المحظورون: {stats['banned_users']}\n"
        text += f"📅 تاريخ التحديث: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        keyboard = [[InlineKeyboardButton("🔙 الرجوع", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def start_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start broadcast message process"""
        await update.callback_query.edit_message_text(
            "📢 **إرسال إشعار**\n\nأرسل الرسالة التي تريد إرسالها لجميع المستخدمين:"
        )
        
        context.user_data["waiting_for_admin_input"] = "broadcast"
    
    async def start_ban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start ban user process"""
        await update.callback_query.edit_message_text(
            "🚫 **حظر مستخدم**\n\nأرسل معرف المستخدم (User ID) أو اسم المستخدم (@username):"
        )
        
        context.user_data["waiting_for_admin_input"] = "ban_user"
    
    async def start_unban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start unban user process"""
        await update.callback_query.edit_message_text(
            "✅ **إلغاء حظر مستخدم**\n\nأرسل معرف المستخدم (User ID) أو اسم المستخدم (@username):"
        )
        
        context.user_data["waiting_for_admin_input"] = "unban_user"
    
    async def start_add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start add channel process"""
        await update.callback_query.edit_message_text(
            "➕ **إضافة قناة إجبارية**\n\nأرسل معرف القناة أو اسم المستخدم (@channel_username):"
        )
        
        context.user_data["waiting_for_admin_input"] = "add_channel"
    
    async def start_remove_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start remove channel process"""
        await update.callback_query.edit_message_text(
            "➖ **إزالة قناة إجبارية**\n\nأرسل معرف القناة أو اسم المستخدم (@channel_username):"
        )
        
        context.user_data["waiting_for_admin_input"] = "remove_channel"
    
    async def handle_admin_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin input for various operations"""
        input_type = context.user_data.get("waiting_for_admin_input")
        input_text = update.message.text
        
        context.user_data["waiting_for_admin_input"] = None
        
        if input_type == "broadcast":
            await self.execute_broadcast(update, context, input_text)
        elif input_type == "ban_user":
            await self.execute_ban_user(update, context, input_text)
        elif input_type == "unban_user":
            await self.execute_unban_user(update, context, input_text)
        elif input_type == "add_channel":
            await self.execute_add_channel(update, context, input_text)
        elif input_type == "remove_channel":
            await self.execute_remove_channel(update, context, input_text)
    
    async def execute_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE, message_text: str):
        """Execute broadcast to all users"""
        conn = sqlite3.connect(db.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE is_banned = 0')
        users = cursor.fetchall()
        conn.close()
        
        success_count = 0
        failed_count = 0
        
        status_msg = await update.message.reply_text(f"📢 جاري الإرسال إلى {len(users)} مستخدم...")
        
        for user_id_tuple in users:
            user_id = user_id_tuple[0]
            try:
                await self.bot.send_message(user_id, message_text)
                success_count += 1
            except TelegramError:
                failed_count += 1
            
            # Update status every 10 users
            if (success_count + failed_count) % 10 == 0:
                await status_msg.edit_text(
                    f"📢 الإرسال جاري...\n✅ نجح: {success_count}\n❌ فشل: {failed_count}"
                )
        
        await status_msg.edit_text(
            f"📢 **اكتمل الإرسال**\n\n✅ تم الإرسال بنجاح: {success_count}\n❌ فشل الإرسال: {failed_count}",
            parse_mode='Markdown'
        )
    
    async def execute_ban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        """Execute user ban"""
        try:
            # Try to parse as user ID first
            if user_input.isdigit():
                user_id = int(user_input)
            elif user_input.startswith('@'):
                # Get user ID from username (this requires the user to have interacted with the bot)
                username = user_input[1:]
                conn = sqlite3.connect(db.db_name)
                cursor = conn.cursor()
                cursor.execute('SELECT user_id FROM users WHERE username = ?', (username,))
                result = cursor.fetchone()
                conn.close()
                
                if not result:
                    await update.message.reply_text("❌ لم يتم العثور على المستخدم في قاعدة البيانات")
                    return
                
                user_id = result[0]
            else:
                await update.message.reply_text("❌ تنسيق غير صحيح. استخدم معرف المستخدم أو @username")
                return
            
            db.ban_user(user_id)
            await update.message.reply_text(f"✅ تم حظر المستخدم {user_id} بنجاح")
            
        except Exception as e:
            logger.error(f"Error banning user: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء حظر المستخدم")
    
    async def execute_unban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        """Execute user unban"""
        try:
            # Try to parse as user ID first
            if user_input.isdigit():
                user_id = int(user_input)
            elif user_input.startswith('@'):
                # Get user ID from username
                username = user_input[1:]
                conn = sqlite3.connect(db.db_name)
                cursor = conn.cursor()
                cursor.execute('SELECT user_id FROM users WHERE username = ?', (username,))
                result = cursor.fetchone()
                conn.close()
                
                if not result:
                    await update.message.reply_text("❌ لم يتم العثور على المستخدم في قاعدة البيانات")
                    return
                
                user_id = result[0]
            else:
                await update.message.reply_text("❌ تنسيق غير صحيح. استخدم معرف المستخدم أو @username")
                return
            
            db.unban_user(user_id)
            await update.message.reply_text(f"✅ تم إلغاء حظر المستخدم {user_id} بنجاح")
            
        except Exception as e:
            logger.error(f"Error unbanning user: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء إلغاء حظر المستخدم")
    
    async def execute_add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE, channel_input: str):
        """Execute add mandatory channel"""
        try:
            # Extract channel ID and username
            if channel_input.startswith('@'):
                channel_username = channel_input[1:]
                # Try to get channel info
                try:
                    chat = await self.bot.get_chat(channel_input)
                    channel_id = str(chat.id)
                except TelegramError as e:
                    await update.message.reply_text(f"❌ لا يمكن الوصول إلى القناة: {e}")
                    return
            elif channel_input.startswith('-') or channel_input.isdigit():
                channel_id = channel_input
                try:
                    chat = await self.bot.get_chat(channel_id)
                    channel_username = chat.username or f"channel_{channel_id}"
                except TelegramError as e:
                    await update.message.reply_text(f"❌ لا يمكن الوصول إلى القناة: {e}")
                    return
            else:
                await update.message.reply_text("❌ تنسيق غير صحيح. استخدم @channel_username أو معرف القناة")
                return
            
            db.add_mandatory_channel(channel_id, channel_username, ADMIN_ID)
            await update.message.reply_text(f"✅ تم إضافة القناة @{channel_username} كقناة إجبارية")
            
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء إضافة القناة")
    
    async def execute_remove_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE, channel_input: str):
        """Execute remove mandatory channel"""
        try:
            # Extract channel ID
            if channel_input.startswith('@'):
                channel_username = channel_input[1:]
                # Find channel ID by username
                channels = db.get_mandatory_channels()
                channel_id = None
                for channel in channels:
                    if channel['username'] == channel_username:
                        channel_id = channel['id']
                        break
                
                if not channel_id:
                    await update.message.reply_text("❌ لم يتم العثور على القناة في قائمة القنوات الإجبارية")
                    return
            else:
                channel_id = channel_input
            
            db.remove_mandatory_channel(channel_id)
            await update.message.reply_text(f"✅ تم إزالة القناة من قائمة القنوات الإجبارية")
            
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء إزالة القناة")
    
    async def run_webhook(self, port: int = 5000):
        """Run bot using webhook for deployment"""
        webhook_url = os.getenv('WEBHOOK_URL', f'https://your-app.onrender.com/{BOT_TOKEN}')
        
        await self.application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"]
        )
        
        # Start webhook server
        await self.application.initialize()
        await self.application.start()
        
        logger.info(f"Bot started with webhook: {webhook_url}")
        
        # Keep the application running
        await self.application.updater.start_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=BOT_TOKEN,
            webhook_url=webhook_url
        )
    
    async def run_polling(self):
        """Run bot using polling for local development"""
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("Bot started with polling")
        
        # Keep the application running
        await self.application.updater.idle()

# Flask app for webhook handling
app = Flask(__name__)
bot_instance = None

@app.route('/')
def health_check():
    return {"status": "Bot is running", "timestamp": datetime.now().isoformat()}

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook_handler():
    if bot_instance:
        update = Update.de_json(request.get_json(), bot_instance.bot)
        asyncio.create_task(bot_instance.application.process_update(update))
    return 'OK'

def signal_handler(sig, frame):
    logger.info('Shutting down gracefully...')
    sys.exit(0)

async def main():
    global bot_instance
    
    # Handle graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize bot
    bot_instance = TelegramBot(BOT_TOKEN)
    
    # Check if running on Render or locally
    if os.getenv('RENDER'):
        # Running on Render - use webhook
        logger.info("Starting bot with webhook for Render deployment...")
        
        # Start Flask app in a separate thread
        def run_flask():
            app.run(host='0.0.0.0', port=5000, debug=False)
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # Set up webhook
        await bot_instance.run_webhook(port=5000)
    else:
        # Running locally - use polling
        logger.info("Starting bot with polling for local development...")
        await bot_instance.run_polling()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
