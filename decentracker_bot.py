# decentracker_bot.py

import tweepy
import requests
import os
import json
from datetime import datetime, timedelta, timezone
import time
from config import BEARER_TOKEN

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
        print(f"Error: {file_path} not found.")
        exit(1)
    return accounts

# Step 3: Fetch tweets using /2/tweets/search/recent
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
    # Simplify the query by removing filters
    # query += " -is:retweet -is:reply"  # Commented out to reduce query complexity

    try:
        # Fetch tweets
        response = client.search_recent_tweets(
            query=query,
            max_results=100,  # Maximum tweets per request
            tweet_fields=["created_at", "attachments", "author_id"],  # Include author_id
            expansions=["author_id", "attachments.media_keys"],  # Include user and media details
            media_fields=["url"],
            start_time=start_time
        )

        # Log all headers for debugging
        print(f"x-rate-limit-limit: {response.meta.get('x-rate-limit-limit')}")
        print(f"x-rate-limit-remaining: {response.meta.get('x-rate-limit-remaining')}")
        print(f"x-rate-limit-reset: {response.meta.get('x-rate-limit-reset')}")

        # Extract rate limit headers
        rate_limit_remaining = int(response.meta.get("x-rate-limit-remaining", 0))
        rate_limit_reset = int(response.meta.get("x-rate-limit-reset", 0))

        print(f"Remaining requests: {rate_limit_remaining}, Reset time: {rate_limit_reset}")

        # Check if we're close to the rate limit
        if rate_limit_remaining <= 0:
            reset_time_utc = datetime.fromtimestamp(rate_limit_reset, tz=timezone.utc)
            local_timezone = timezone(timedelta(hours=3))  # Define GMT+3 timezone
            reset_time_local = reset_time_utc.astimezone(local_timezone)
            wait_time = (reset_time_local - datetime.now(local_timezone)).total_seconds() + 10  # Add buffer

            print(f"Rate limit exceeded. Waiting until {reset_time_local.strftime('%Y-%m-%d %H:%M:%S')} ({wait_time:.0f} seconds)...")
            time.sleep(max(wait_time, 0))  # Ensure non-negative wait time
            return

        # Extract users and media from the includes field
        users = {user.id: user.username for user in response.includes.get("users", [])}
        media_dict = {media.media_key: media for media in response.includes.get("media", [])}

        # Collect all tweets into a single list
        tweets_list = []
        new_tweets_found = False
        if response.data:
            # Generate timestamp for the JSON file
            timestamp = datetime.now().strftime("%y%m%d_%H%M")  # e.g., 250414_0145

            for tweet in response.data:
                # Skip cached tweets
                if tweet.id in cached_tweets:
                    continue

                # Resolve the username from the author_id
                author_username = users.get(tweet.author_id, "Unknown")
                tweet_url = f"https://twitter.com/{author_username}/status/{tweet.id}"

                # Prepare tweet metadata
                tweet_data = {
                    "accountID": author_username,  # Use the resolved username
                    "tweet_url": tweet_url,
                    "text": tweet.text,
                    "image_path": None  # Placeholder for image path
                }

                # Check for media in the tweet
                if "attachments" in tweet.data and "media_keys" in tweet.data["attachments"]:
                    media_keys = tweet.data["attachments"]["media_keys"]
                    for media_key in media_keys:
                        media = media_dict.get(media_key)
                        if media and media.type == "photo":
                            image_url = media.url

                            # Download the image
                            response_media = requests.get(image_url)
                            if response_media.status_code == 200:
                                # Generate a unique filename for the image
                                image_filename = f"tweets/{timestamp}_{tweet.id}.jpg"
                                
                                # Save the image as a .jpg file
                                with open(image_filename, "wb") as img_file:
                                    img_file.write(response_media.content)
                                print(f"Saved image: {image_filename}")
                                
                                # Update the tweet data with the image path
                                tweet_data["image_path"] = image_filename
                            break  # Embed only the first image

                # Add tweet to the list
                tweets_list.append(tweet_data)
                cached_tweets.add(tweet.id)
                new_tweets_found = True

        # Save tweets to a single JSON file
        if tweets_list:
            json_filename = f"tweets/{timestamp}_all_tweets.json"

            # Save tweet data to a JSON file
            tweets_data = {
                "tweets": tweets_list
            }
            with open(json_filename, "w") as f:
                json.dump(tweets_data, f, indent=4)
            print(f"Saved tweet data: {json_filename}")

        if not tweets_list:
            print("No new tweets found in the last 15 minutes.")

        # Save updated cache
        with open(cached_tweets_file, "w") as f:
            json.dump(list(cached_tweets), f)

    except tweepy.TooManyRequests as e:
        print("TooManyRequests Exception Caught")
        headers = e.response.headers
        print("Headers:", headers)

        rate_limit_remaining = int(headers.get("x-rate-limit-remaining", 0))
        rate_limit_reset = int(headers.get("x-rate-limit-reset", 0))

        if rate_limit_remaining > 0:
            print(f"Unexpected TooManyRequests error. Remaining requests: {rate_limit_remaining}")
            return  # Skip waiting if requests remain

        reset_time_utc = datetime.fromtimestamp(rate_limit_reset, tz=timezone.utc)
        local_timezone = timezone(timedelta(hours=3))  # Define GMT+3 timezone
        reset_time_local = reset_time_utc.astimezone(local_timezone)
        wait_time = (reset_time_local - datetime.now(local_timezone)).total_seconds() + 10  # Add buffer

        print(f"Rate limit exceeded. Waiting until {reset_time_local.strftime('%Y-%m-%d %H:%M:%S')} ({wait_time:.0f} seconds)...")
        time.sleep(max(wait_time, 0))  # Ensure non-negative wait time

    except tweepy.TweepyException as e:
        print(f"Tweepy error occurred: {e}")
        import traceback
        traceback.print_exc()

    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()

# Step 4: Run the bot
if __name__ == "__main__":
    # Read accounts from accounts.txt
    accounts = read_accounts("accounts.txt")
    print(f"Accounts to track: {accounts}")

    try:
        # Fetch tweets every 15 minutes
        while True:
            fetch_tweets(accounts)
            print("Waiting for the next request...")
            time.sleep(900)  # Default wait time (15 minutes)
    except KeyboardInterrupt:
        print("\nBot stopped by user. Exiting gracefully...")