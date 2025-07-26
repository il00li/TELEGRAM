# Overview

This project is a comprehensive Telegram bot that provides image, video, and music search functionality using the Pixabay API. The bot features mandatory channel subscription, admin controls, and user management. Users must subscribe to required channels before using the bot, and can search for various media types with navigation between results. Built using Python with python-telegram-bot library (v20.7) and Flask for webhook handling.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

The application follows a monolithic architecture with the following key components:

## Backend Architecture
- **Python-based Telegram Bot**: Built using the `python-telegram-bot` library
- **SQLite Database**: Local file-based database for user management and statistics
- **Flask Webhook Server**: Handles incoming Telegram webhook requests
- **Pixabay API Integration**: Third-party service for image search functionality

## Threading Model
- **Main Thread**: Runs the Telegram bot application
- **Background Thread**: Runs the Flask webhook server
- **Async/Await**: Used for handling Telegram bot operations

# Key Components

## Database Layer
- **Database Class**: Manages SQLite connections and operations
- **Users Table**: Stores user information, ban status, and search statistics
- **Schema**: Tracks user_id, username, names, join dates, ban status, and search counts

## Bot Handlers
- **Command Handlers**: Process user commands like `/start`
- **Callback Query Handlers**: Handle inline keyboard interactions
- **Message Handlers**: Process text messages and search requests

## External API Integration
- **Pixabay API**: Provides image search functionality
- **Error Handling**: Manages API rate limits and failures

## Admin Features
- **User Management**: Ban/unban functionality for administrators
- **Statistics**: Track user activity and search patterns

# Data Flow

1. **User Interaction**: Users send messages or commands to the Telegram bot
2. **Webhook Processing**: Flask server receives webhook from Telegram
3. **Request Routing**: Bot handlers process different types of requests
4. **Database Operations**: User data and statistics are stored/retrieved
5. **External API Calls**: Image searches are forwarded to Pixabay API
6. **Response Generation**: Results are formatted and sent back to users

# External Dependencies

## Core Libraries
- **python-telegram-bot (v20.7)**: Telegram Bot API wrapper with async support
- **Flask**: Web framework for webhook handling
- **requests**: HTTP client for Pixabay API calls
- **sqlite3**: Database operations (built-in)

## Third-party Services
- **Telegram Bot API**: Message delivery and bot functionality
- **Pixabay API**: Image, video, and music search service

## Bot Features
- **Mandatory Channel Subscription**: Users must subscribe to channels before using bot
- **Multi-media Search**: Support for photos, illustrations, vectors, videos, music, and GIFs
- **Search Result Navigation**: Previous/next buttons with result selection
- **Admin Panel**: Complete user and channel management
- **Statistics Tracking**: User activity and search analytics
- **Broadcasting**: Admin can send messages to all users

## Admin Features
- **User Management**: Ban/unban users by ID
- **Channel Management**: Add/remove mandatory subscription channels
- **Statistics Dashboard**: View user counts, search statistics
- **Broadcast Messages**: Send notifications to all active users

## Configuration
- **Bot Token**: 8071576925:AAGgx_Jkuu-mRpjdMKiOQCDkkVQskXQYhQo
- **Admin ID**: 7251748706
- **Pixabay API Key**: 51444506-bffefcaf12816bd85a20222d1
- **Database**: SQLite file stored locally
- **Default Channel**: @Ili8_8ill (pre-configured)

# Deployment Strategy

## Current Setup
- **Single File Application**: All functionality contained in `main.py`
- **Local SQLite Database**: Data persistence through file-based database
- **Webhook Mode**: Designed to receive updates via HTTP webhooks
- **Threading**: Concurrent handling of bot operations and webhook server

## Recommendations for Production
- **Environment Variables**: Move sensitive data (tokens, API keys) to environment variables
- **Database Migration**: Consider PostgreSQL for better scalability
- **Error Handling**: Implement comprehensive error handling and logging
- **Health Checks**: Add monitoring and health check endpoints
- **Security**: Implement webhook verification and rate limiting

## Scalability Considerations
- **Database**: Current SQLite setup limits concurrent access
- **Memory**: In-memory operations may need optimization for high user loads
- **API Limits**: Pixabay API rate limiting needs to be handled gracefully