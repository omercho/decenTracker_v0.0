import tweepy
import requests
import os
import json
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
import time
from config import BEARER_TOKEN

# Set up logging
logging.basicConfig(filename="bot.log", level=logging.INFO, format="%(asctime)s - %(message)s")

# Step 1: Set up the output directories
if not os.path.exists("tweets"):
    os.makedirs("tweets")

# Step 2: Read the list of accounts from accounts.txt
def read_accounts(file_path):
    accounts = []
    try:
        with open(file_path, "r") as f:
            for line in f:
                account = line.strip().replace(",", "").strip()  # Clean up usernames
                if account:  # Ignore empty lines
                    accounts.append(account)
    except FileNotFoundError:
        logging.error(f"Error: {file_path} not found.")
        exit(1)
    return accounts

# Step 3: Async function for downloading images
async def download_image_async(url, filename):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                with open(filename, "wb") as img_file:
                    img_file.write(await response.read())
                logging.info(f"Saved image: {filename}")

# Step 4: Fetch tweets using /2/tweets/search/recent
def fetch_tweets(accounts):
    # Initialize the Twitter API client
    client = tweepy.Client(bearer_token=BEARER_TOKEN)

    # Load cached tweet IDs
    cached_tweets_file = "cached_tweets.json"
    if os.path.exists(cached_tweets_file):
        with open(cached_tweets_file, "r") as f:
            cached_tweets = set(json.load(f))
    else:
        cached_tweets = set()

    # Calculate the start time (e.g., 15 minutes ago)
    start_time = (datetime.utcnow() - timedelta(minutes=15)).isoformat() + "Z"

    # Construct the query for all accounts
    query = " OR ".join([f"from:{account}" for account in accounts])

    try:
        # Fetch tweets
        response = client.search_recent_tweets(
            query=query,
            max_results=100,
            tweet_fields=["created_at", "attachments", "author_id"],
            expansions=["author_id", "attachments.media_keys"],
            media_fields=["url"],
            start_time=start_time
        )

        # Extract rate limit headers
        rate_limit_remaining = int(response.meta.get("x-rate-limit-remaining", 0))
        rate_limit_reset = int(response.meta.get("x-rate-limit-reset", 0))

        logging.info(f"Remaining requests: {rate_limit_remaining}, Reset time: {rate_limit_reset}")

        # Check if we're close to the rate limit
        if rate_limit_remaining <= 0:
            reset_time_utc = datetime.fromtimestamp(rate_limit_reset, tz=timezone.utc)
            local_timezone = timezone(timedelta(hours=3))  # Define GMT+3 timezone
            reset_time_local = reset_time_utc.astimezone(local_timezone)
            wait_time = (reset_time_local - datetime.now(local_timezone)).total_seconds() + 10  # Add buffer

            logging.warning(f"Rate limit exceeded. Waiting until {reset_time_local.strftime('%Y-%m-%d %H:%M:%S')} ({wait_time:.0f} seconds)...")
            time.sleep(max(wait_time, 0))
            return

        # Extract users and media from the includes field
        users = {user.id: user.username for user in response.includes.get("users", [])}
        media_dict = {media.media_key: media for media in response.includes.get("media", [])}

        # Collect all tweets into a single list
        tweets_list = []
        new_tweets_found = False

        if response.data:
            # Generate timestamp for the JSON file
            timestamp = datetime.now().strftime("%y%m%d_%H%M")

            tasks = []  # Store async image downloads

            for tweet in response.data:
                if tweet.id in cached_tweets:
                    continue

                # Resolve the username from the author_id
                author_username = users.get(tweet.author_id, "Unknown")
                tweet_url = f"https://twitter.com/{author_username}/status/{tweet.id}"

                # Prepare tweet metadata
                tweet_data = {
                    "accountID": author_username,
                    "tweet_url": tweet_url,
                    "text": tweet.text,
                    "image_path": None
                }

                # Check for media in the tweet
                if "attachments" in tweet.data and "media_keys" in tweet.data["attachments"]:
                    media_keys = tweet.data["attachments"]["media_keys"]
                    for media_key in media_keys:
                        media = media_dict.get(media_key)
                        if media and media.type == "photo":
                            image_url = media.url

                            # Generate a unique filename for the image
                            image_filename = f"tweets/{tweet.id}.jpg"

                            # Check if the image already exists
                            if not os.path.exists(image_filename):
                                tasks.append(download_image_async(image_url, image_filename))
                                tweet_data["image_path"] = image_filename
                            else:
                                logging.info(f"Image already exists: {image_filename}")
                            break  # Embed only the first image

                tweets_list.append(tweet_data)
                cached_tweets.add(tweet.id)
                new_tweets_found = True

            # Run async image downloads
            asyncio.run(asyncio.gather(*tasks))

        if tweets_list:
            json_filename = f"tweets/{timestamp}_all_tweets.json"
            with open(json_filename, "w") as f:
                json.dump({"tweets": tweets_list}, f, indent=4)
            logging.info(f"Saved tweet data: {json_filename}")

        if not new_tweets_found:
            logging.info("No new tweets found in the last 15 minutes.")

        # Save updated cache
        with open(cached_tweets_file, "w") as f:
            json.dump(list(cached_tweets), f)

    except tweepy.TooManyRequests as e:
        logging.error("TooManyRequests Exception Caught")
        headers = e.response.headers
        logging.error(f"Headers: {headers}")

        reset_time_utc = datetime.fromtimestamp(int(headers.get("x-rate-limit-reset", 0)), tz=timezone.utc)
        local_timezone = timezone(timedelta(hours=3))
        reset_time_local = reset_time_utc.astimezone(local_timezone)
        wait_time = (reset_time_local - datetime.now(local_timezone)).total_seconds() + 10

        logging.warning(f"Rate limit exceeded. Waiting until {reset_time_local.strftime('%Y-%m-%d %H:%M:%S')} ({wait_time:.0f} seconds)...")
        time.sleep(max(wait_time, 0))

    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)

# Step 5: Run the bot
if __name__ == "__main__":
    accounts = read_accounts("accounts.txt")
    logging.info(f"Accounts to track: {accounts}")

    try:
        while True:
            fetch_tweets(accounts)
            logging.info("Waiting before the next request...")
            time.sleep(900)
    except KeyboardInterrupt:
        logging.info("Bot stopped by user. Exiting gracefully.")