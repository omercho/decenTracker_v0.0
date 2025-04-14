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