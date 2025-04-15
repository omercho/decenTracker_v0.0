import tweepy
import snscrape.modules.twitter as sntwitter
import requests
import os
import json
from datetime import datetime, timedelta, timezone
import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)

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

# Step 3: Fetch tweets using Twitter API
def fetch_tweets_tweepy(accounts):
    # Initialize the Twitter API client
    client = tweepy.Client(bearer_token=BEARER_TOKEN)

    # Calculate the start time (e.g., 15 minutes ago)
    start_time = (datetime.utcnow() - timedelta(minutes=15)).isoformat() + "Z"

    # Construct the query for all accounts
    query = " OR ".join([f"from:{account}" for account in accounts])
    query += " -is:retweet -is:reply"  # Exclude retweets and replies

    try:
        # Fetch tweets
        response = client.search_recent_tweets(
            query=query,
            max_results=100,  # Maximum tweets per request
            tweet_fields=["created_at", "attachments", "author_id"],  # Include author_id
            expansions=["author_id", "attachments.media_keys"],  # Include user and media details
            media_fields=["url"],
            start_time=start_time,
        )

        # Log rate limit headers
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
            time.sleep(max(wait_time, 0))  # Ensure non-negative wait time
            return []

        # Extract users and media from the includes field
        users = {user.id: user.username for user in response.includes.get("users", [])}
        media_dict = {media.media_key: media for media in response.includes.get("media", [])}

        # Collect all tweets into a single list
        tweets_list = []
        if response.data:
            for tweet in response.data:
                # Resolve the username from the author_id
                author_username = users.get(tweet.author_id, "Unknown")
                tweet_url = f"https://twitter.com/{author_username}/status/{tweet.id}"

                # Prepare tweet metadata
                tweet_data = {
                    "accountID": author_username,  # Use the resolved username
                    "tweet_url": tweet_url,
                    "text": tweet.text,
                    "image_path": None,  # Placeholder for image path
                }

                # Check for media in the tweet
                if "attachments" in tweet.data and "media_keys" in tweet.data["attachments"]:
                    media_keys = tweet.data["attachments"]["media_keys"]
                    for media_key in media_keys:
                        media = media_dict.get(media_key)
                        if media and media.type == "photo":
                            image_url = media.url

                            # Generate a unique filename for the image
                            timestamp = datetime.now().strftime("%y%m%d_%H%M")
                            image_filename = f"tweets/{timestamp}_{tweet.id}.jpg"

                            # Download the image
                            response_media = requests.get(image_url)
                            if response_media.status_code == 200:
                                with open(image_filename, "wb") as img_file:
                                    img_file.write(response_media.content)
                                logging.info(f"Saved image: {image_filename}")
                                
                                # Update the tweet data with the image path
                                tweet_data["image_path"] = image_filename
                            break  # Embed only the first image

                # Add tweet to the list
                tweets_list.append(tweet_data)

        return tweets_list

    except tweepy.TooManyRequests as e:
        logging.warning("Rate limit exceeded. Waiting until the reset time...")
        headers = e.response.headers
        rate_limit_reset = int(headers.get("x-rate-limit-reset", 0))
        reset_time_utc = datetime.fromtimestamp(rate_limit_reset, tz=timezone.utc)
        local_timezone = timezone(timedelta(hours=3))  # Define GMT+3 timezone
        reset_time_local = reset_time_utc.astimezone(local_timezone)
        wait_time = (reset_time_local - datetime.now(local_timezone)).total_seconds() + 10  # Add buffer

        logging.warning(f"Waiting until {reset_time_local.strftime('%Y-%m-%d %H:%M:%S')} ({wait_time:.0f} seconds)...")
        time.sleep(max(wait_time, 0))
        return []

    except tweepy.TweepyException as e:
        logging.error(f"Tweepy error occurred: {e}")
        return []

    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return []

# Step 4: Fetch tweets using snscrape
def fetch_tweets_snscrape(accounts):
    tweets_list = []
    for account in accounts:
        try:
            logging.info(f"Fetching tweets for account: {account} using snscrape")
            for i, tweet in enumerate(sntwitter.TwitterUserScraper(account).get_items()):
                if i >= 100:  # Limit to 100 tweets
                    break

                # Prepare tweet metadata
                tweet_data = {
                    "accountID": account,
                    "tweet_url": tweet.url,
                    "text": tweet.content,
                    "image_path": None,  # Placeholder for image path
                }

                # Check for media in the tweet
                if tweet.media and isinstance(tweet.media, list):
                    for media in tweet.media:
                        if hasattr(media, "previewUrl") and media.previewUrl:
                            image_url = media.previewUrl

                            # Generate a unique filename for the image
                            timestamp = datetime.now().strftime("%y%m%d_%H%M")
                            image_filename = f"tweets/{timestamp}_{tweet.id}.jpg"

                            # Download the image
                            response_media = requests.get(image_url)
                            if response_media.status_code == 200:
                                with open(image_filename, "wb") as img_file:
                                    img_file.write(response_media.content)
                                logging.info(f"Saved image: {image_filename}")
                                
                                # Update the tweet data with the image path
                                tweet_data["image_path"] = image_filename
                            break  # Embed only the first image

                # Add tweet to the list
                tweets_list.append(tweet_data)

        except Exception as e:
            logging.error(f"Error fetching tweets for account {account}: {e}")
            continue

    return tweets_list

# Step 5: Save tweets to a JSON file
def save_tweets(tweets_list):
    if not tweets_list:
        logging.info("No new tweets found.")
        return

    # Generate timestamp for the JSON file
    timestamp = datetime.now().strftime("%y%m%d_%H%M")
    json_filename = f"tweets/{timestamp}_all_tweets.json"

    # Save tweet data to a JSON file
    tweets_data = {"tweets": tweets_list}
    with open(json_filename, "w") as f:
        json.dump(tweets_data, f, indent=4)
    logging.info(f"Saved tweet data: {json_filename}")

# Step 6: Main function
def main():
    # Read accounts from accounts.txt
    accounts = read_accounts("accounts.txt")
    logging.info(f"Accounts to track: {accounts}")

    while True:
        try:
            # Fetch tweets using Twitter API
            tweets_list = fetch_tweets_tweepy(accounts)

            # If Twitter API fails, fall back to snscrape
            if not tweets_list:
                logging.warning("Twitter API failed. Falling back to snscrape.")
                tweets_list = fetch_tweets_snscrape(accounts)

            # Save tweets
            save_tweets(tweets_list)

            # Wait before the next request
            logging.info("Waiting before the next request...")
            time.sleep(900)  # Default wait time (15 minutes)

        except KeyboardInterrupt:
            logging.info("Bot stopped by user. Exiting gracefully...")
            break

# Step 7: Run the bot
if __name__ == "__main__":
    from config import BEARER_TOKEN  # Import your Twitter API Bearer Token
    main()