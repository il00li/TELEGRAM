# Deploy to Render Instructions

## Required Files for Render Deployment:
1. `main.py` - Main bot application
2. `render_requirements.txt` - Python dependencies
3. `Procfile` - Deployment configuration
4. `runtime.txt` - Python version

## Environment Variables to Set in Render:
```
BOT_TOKEN=8071576925:AAGgx_Jkuu-mRpjdMKiOQCDkkVQskXQYhQo
ADMIN_ID=7251748706
PIXABAY_API_KEY=51444506-bffefcaf12816bd85a20222d1
```

## Steps to Deploy:

1. **Create New Web Service on Render**
   - Go to https://render.com
   - Click "New +" → "Web Service"
   - Connect your GitHub repository

2. **Configure Deployment Settings**
   - Build Command: `pip install -r render_requirements.txt`
   - Start Command: `gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 main:app`
   - Environment: Python 3
   - Python Version: 3.11.9

3. **Set Environment Variables**
   - Add the environment variables listed above
   - Make sure RENDER_EXTERNAL_URL is automatically set by Render

4. **Deploy**
   - Click "Create Web Service"
   - Wait for deployment to complete
   - Your bot will be accessible at the provided Render URL

## Webhook Setup:
The bot automatically configures its webhook URL using the RENDER_EXTERNAL_URL environment variable.

## Features Included:
- ✅ Mandatory channel subscription with Arabic ASCII art messages
- ✅ Multi-media search (Photos, Videos, Music, Vectors, Illustrations, GIFs)
- ✅ Navigation between search results with Previous/Next buttons
- ✅ Result selection with "اختيار🥇" button
- ✅ Admin panel with user management, statistics, and broadcasting
- ✅ SQLite database for user management and analytics
- ✅ Error handling with "كلماتك غريبة يا غلام" message for no results

## Testing:
1. Start a conversation with your bot on Telegram
2. Send /start command
3. Subscribe to required channels and verify
4. Try searching for images, videos, or music
5. Test admin features with /admin command (admin only)