# decenTracker v0.0

A Python bot to fetch tweets from Twitter accounts and save them as JSON files with associated images.

## Features
- Fetches tweets from multiple Twitter accounts.
- Saves tweet data (text, URLs) and associated images in JSON format.
- Handles rate limits with adaptive waiting logic.
- Downloads images concurrently using asyncio.

## Setup Instructions
1. Install dependencies:
   ```bash
   pip install tweepy requests

2. Add your Twitter accounts to accounts.txt.
3. Set your Twitter Bearer Token in config.py.

Usage
Run the bot: python decentracker_bot.py

Notes
Uses the Twitter API v2.
Requires a Twitter Developer account.