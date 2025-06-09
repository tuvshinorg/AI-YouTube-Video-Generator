import feedparser
import sqlite3
import re
import json
import os
import random
from html import unescape
from datetime import datetime
from bs4 import BeautifulSoup
import requests
import logging
from ollama import chat
from pydantic import BaseModel, ValidationError
import subprocess

# Define the schema for the scenes


class SceneInfo(BaseModel):
    scene: int
    image: str
    text: str


class SceneList(BaseModel):
    scenes: list[SceneInfo]


class TitleDescriptionResponse(BaseModel):
    title: str
    description: str


class songResponse(BaseModel):
    genre: str


# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/root/AI-YouTube-Video-Generator/logs/feed.log"),
    ],
)


def clean_text(html_text):
    """Clean HTML and unwanted characters from text."""
    text = re.sub(r"<[^>]+>", "", html_text)  # Remove HTML tags
    text = re.sub(r"http\S+|www\.\S+", "", text)  # Remove URLs
    text = re.sub(r"\s+", " ", text)  # Remove multiple spaces/newlines
    text = unescape(text)  # Unescape HTML entities
    text = re.sub(r"^unbfacts:\s*", "", text)  # Remove specific prefixes
    return text.strip()

def fetch_snopes_feeds():
    """Fetch and process RSS feeds."""
    print("Starting RSS feed processing")

    rss_url = "https://www.snopes.com/feed/"
    feed = feedparser.parse(rss_url)

    if feed.bozo:
        print(f"Feed parsing error: {feed.bozo_exception}")
        return

    print(f"Fetched {len(feed.entries)} entries from RSS feed")

    conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
    c = conn.cursor()
    new_entries = 0

    try:
        for entry in feed.entries:
            try:
                link = entry.get("link")
                if not link:
                    print("Skipping entry with missing link")
                    continue

                response = requests.get(link)
                if response.status_code != 200:
                    print(
                        f"Failed to fetch URL content: {link} (Status {response.status_code})"
                    )
                    continue

                soup = BeautifulSoup(response.text, "html.parser")
                content_element = soup.select_one("#article-content")
                if not content_element:
                    print(f"No content found for URL: {link}")
                    continue

                text = clean_text(content_element.get_text(strip=True))
                c.execute("SELECT rssText FROM RSS WHERE rssText = ?", (text,))
                if c.fetchone():
                    print(f"Text already exists in the database for URL: {link}")
                    continue

                published_date = entry.get(
                    "published", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                c.execute(
                    """INSERT INTO RSS (rssGroup, rssText, rssStamp) VALUES (?, ?, ?)""",
                    ("snopes", text, published_date),
                )
                conn.commit()
                new_entries += 1
                print(f"Inserted new entry for URL: {link}")

            except Exception as e:
                print(f"Error processing entry: {e}", exc_info=True)

        print(f"Inserted {new_entries} new entries into the database")

    except Exception as e:
        print(f"Fatal error in feed processing: {e}", exc_info=True)

    finally:
        conn.close()



def fetch_news_feeds():
    """Fetch and process the first 5 RSS feed items from news sites."""
    logging.info("Starting RSS feed processing")
    
    # List of potential feeds to try
    feeds_to_try = [
        {
            "url": "https://www.dailymail.co.uk/articles.rss",
            "name": "dailymailv2",
            "content_selector": "#content > div.articleWide.cleared > div.alpha"
        }
    ]
    
    # Browser-like headers to avoid being blocked
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0'
    }
    
    feed = None
    feed_info = None
    
    # Try each feed until one works
    for potential_feed in feeds_to_try:
        try:
            logging.info(f"Trying to fetch feed from {potential_feed['name']}")
            response = requests.get(potential_feed['url'], headers=headers, timeout=10)
            
            if response.status_code != 200:
                logging.warning(f"Failed to fetch {potential_feed['name']} feed: {response.status_code}")
                continue
                
            # Parse the feed
            feed = feedparser.parse(response.content)
            
            if feed.bozo and feed.bozo_exception and not feed.entries:
                logging.warning(f"Error parsing {potential_feed['name']} feed: {feed.bozo_exception}")
                continue
                
            if not feed.entries:
                logging.warning(f"No entries found in {potential_feed['name']} feed")
                continue
                
            # If we got here, the feed is working
            feed_info = potential_feed
            logging.info(f"Successfully parsed {feed_info['name']} feed with {len(feed.entries)} entries")
            break
            
        except Exception as e:
            logging.warning(f"Error with {potential_feed['name']}: {e}")
    
    if not feed or not feed_info:
        logging.error("All feeds failed to parse properly")
        return False
    
    conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
    c = conn.cursor()
    new_entries = 0
    
    try:
        for entry in feed.entries[:5]:  # Fetch only the first 5 items
            try:
                link = entry.get("link")
                if not link:
                    logging.warning("Skipping entry with missing link")
                    continue
                
                # Get the full article content
                article_response = requests.get(link, headers=headers, timeout=10)
                if article_response.status_code != 200:
                    logging.warning(
                        f"Failed to fetch URL content: {link} (Status {article_response.status_code})"
                    )
                    continue
                
                # Use BeautifulSoup to extract content
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(article_response.content, 'html.parser')
                
                title = entry.get("title", "").strip()
                content_text = ""
                
                # First try to use the exact selector
                content_element = soup.select_one(feed_info['content_selector'])
                
                if content_element:
                    logging.info(f"Found content using exact selector for {link}")
                    content_text = content_element.get_text(separator=' ', strip=True)
                else:
                    # Fallback to class-based searches
                    logging.info(f"Exact selector failed, trying fallbacks for {link}")
                    
                    # Try some common content class names
                    for class_name in ['content-inner', 'entry-content', 'article-content', 'post-content']:
                        content_div = soup.find(class_=class_name)
                        if content_div:
                            content_text = content_div.get_text(separator=' ', strip=True)
                            logging.info(f"Found content using class '{class_name}' for {link}")
                            break
                
                # If still no content, fall back to feed description/summary
                if not content_text:
                    content_text = entry.get("description", "") or entry.get("summary", "")
                    if content_text:
                        content_soup = BeautifulSoup(content_text, 'html.parser')
                        content_text = content_soup.get_text(separator=' ', strip=True)
                        logging.info(f"Using feed description/summary for {link}")
                
                # Clean and combine the text
                text = clean_text(f"{title} {content_text}")
                
                # Only insert if we have meaningful content
                if len(text.strip()) < 20:  # Skip if too short
                    logging.warning(f"Content too short for {link}, skipping")
                    continue
                
                c.execute("SELECT rssText FROM RSS WHERE rssText = ?", (text,))
                if c.fetchone():
                    logging.info(f"Text already exists in the database for URL: {link}")
                    continue
                
                published_date = entry.get(
                    "published", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                c.execute(
                    """INSERT INTO RSS (rssGroup, rssText, rssStamp) VALUES (?, ?, ?)""",
                    (feed_info['name'], text, published_date),
                )
                conn.commit()
                new_entries += 1
                logging.info(f"Inserted new entry from {feed_info['name']} for URL: {link}")
            
            except Exception as e:
                logging.error(f"Error processing entry: {e}", exc_info=True)
        
        logging.info(f"Inserted {new_entries} new entries into the database")
        return new_entries > 0
    
    except Exception as e:
        logging.error(f"Fatal error in feed processing: {e}", exc_info=True)
        return False
    
    finally:
        conn.close()


def get_rss_if_not_in_seed():
    """Retrieve the first RSS entry not present in the seed table."""
    conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
    c = conn.cursor()

    query = """
    SELECT rss.rssId, rss.rssGroup, rss.rssText, rss.rssStamp
    FROM rss
    LEFT JOIN seed ON rss.rssId = seed.rssId
    WHERE seed.rssId IS NULL
    LIMIT 1
    """
    c.execute(query)
    result = c.fetchone()

    conn.close()

    if result:
        rss_id, rss_group, rss_text, rss_stamp = result
        try:
            rss_text_json = json.loads(rss_text)
            rss_array = {
                "rssId": rss_id,
                "rssGroup": rss_group,
                "rssText": rss_text_json[:5],
                "rssStamp": rss_stamp,
            }
        except json.JSONDecodeError:
            rss_array = {
                "rssId": rss_id,
                "rssGroup": rss_group,
                "rssText": rss_text,
                "rssStamp": rss_stamp,
            }
        return rss_array

    logging.info("No new RSS entry found.")
    return None


def process_rss_to_seed(rss_array, max_retries=3):
    """Process RSS entry and insert into seed and scene tables with retry mechanism."""
    try:
        if not rss_array:
            logging.info("No valid RSS entry to process.")
            return

        attribute = rss_array["rssText"]
        # Improved prompt with clearer instructions and formatting example
        base_prompt = f"""Generate a surprising YouTube video script from this text: '{attribute}'.
        IMPORTANT REQUIREMENTS:
        1. The output MUST have EXACTLY 6 scenes - no more, no less.
        2. Each scene MUST be a separate object in a JSON array.
        3. Each 'scene' object MUST have:
           - Key 'scene' with value as scene number (1 through 6)
           - Key 'image' with value as text description for AI image generation
           - Key 'text' with value as narration text for the scene
        4. The 6th scene MUST be a creative way to say 'subscribe and like our video'
        """
        # Check if ollama service is running
        try:
            subprocess.check_output(["pgrep", "ollama"])
            ollama_was_running = True
        except subprocess.CalledProcessError:
            ollama_was_running = False
            # Start ollama if not running
            subprocess.Popen(
                ["service", "ollama", "start"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logging.info("Started ollama service")
            # Give it a moment to start up
            import time

            time.sleep(2)

        # Implement retry logic
        retry_count = 0
        valid_response = False

        while not valid_response and retry_count < max_retries:
            # Use ollama client to interact with the model
            response = chat(
                model="llama3.2:latest",
                messages=[{"role": "user", "content": base_prompt}],
                format=SceneList.model_json_schema(),
            )

            try:
                # Parse the response
                validated_data = SceneList.model_validate_json(response.message.content)

                # Validate that there are exactly 6 scenes
                if len(validated_data.scenes) == 6:
                    # Check that scene numbers are 1 through 6
                    scene_numbers = [scene.scene for scene in validated_data.scenes]
                    if sorted(scene_numbers) == list(range(1, 7)):
                        valid_response = True
                        logging.info(
                            f"Valid response with 6 scenes obtained after {retry_count} retries"
                        )
                    else:
                        logging.warning(
                            f"Scene numbers not sequential 1-6: {scene_numbers}. Retrying..."
                        )
                else:
                    logging.warning(
                        f"Received {len(validated_data.scenes)} scenes instead of 6. Retrying..."
                    )

            except Exception as validate_error:
                logging.error(f"Validation error: {validate_error}")

            # Increment retry counter if validation failed
            if not valid_response:
                retry_count += 1
                logging.info(f"Retrying prompt, attempt {retry_count}/{max_retries}")
                # Small delay before retry
                time.sleep(1)

        # If we've exhausted retries and still don't have a valid response, log and exit
        if not valid_response:
            logging.error(f"Failed to get valid response after {max_retries} attempts")
            return

        # If we reached here, we have a valid response with 6 scenes
        conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
        cursor = conn.cursor()

        try:
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                "INSERT INTO seed (rssId, seedPrompt, seedTitle, seedDescription, seedSong, seedCreatedDate, seedTransitionStamp, seedMixStamp, seedRenderStamp, seedUploadStamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rss_array["rssId"],
                    base_prompt,  # Store the actual prompt used, including any retries
                    "not loaded",
                    "not loaded",
                    "not loaded",
                    current_date,
                    "0000-00-00 00:00:00",
                    "0000-00-00 00:00:00",
                    "0000-00-00 00:00:00",
                    "0000-00-00 00:00:00",
                ),
            )
            seed_id = cursor.lastrowid

            for scene in validated_data.scenes:
                cursor.execute(
                    "INSERT INTO scene (seedId, sceneNumber, sceneImage, sceneText, sceneCreatedDate) VALUES (?, ?, ?, ?, ?)",
                    (
                        seed_id,
                        scene.scene,
                        scene.image,
                        scene.text,
                        current_date,
                    ),
                )

                cursor.execute(
                    "INSERT INTO task (seedId, sceneNumber, sceneImageDate, sceneAudioDate, sceneClipDate, sceneSubtitleDate) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        seed_id,
                        scene.scene,
                        "0000-00-00 00:00:00",
                        "0000-00-00 00:00:00",
                        "0000-00-00 00:00:00",
                        "0000-00-00 00:00:00",
                    ),
                )

            conn.commit()
            logging.info("Successfully inserted all scenes and tasks")

        except sqlite3.Error as e:
            logging.error(f"Database error: {e}")
            conn.rollback()

        finally:
            conn.close()

        # Stop ollama if we started it (it wasn't already running)
        if not ollama_was_running:
            subprocess.run(
                ["service", "ollama", "stop"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logging.info("Stopped ollama service")

    except Exception as e:
        # If anything goes wrong, ensure we still try to stop ollama if we started it
        if "ollama_was_running" in locals() and not ollama_was_running:
            try:
                subprocess.run(
                    ["ollama", "stop"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                logging.info("Stopped ollama service after error")
            except Exception as stop_error:
                logging.error(f"Failed to stop ollama after error: {stop_error}")

        logging.error(f"Unexpected error: {e}", exc_info=True)


def generate_title_description(rss_array):
    """Generate YouTube title and description using Ollama's chat API and structured output"""
    if not rss_array:
        logging.info("No valid RSS entry to process.")
        return

    conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
    cursor = conn.cursor()

    try:
        # Extract the seed text and rssId from the input array
        seed_text = rss_array["rssText"]
        rss_id = rss_array["rssId"]

        # Create the seed prompt for Ollama
        seed_prompt = f"""
        I want YouTube video title and description in JSON format only from this text '{seed_text}'. Do not include any text or explanations.
        """

        try:
            subprocess.check_output(["pgrep", "ollama"])
            ollama_was_running = True
        except subprocess.CalledProcessError:
            ollama_was_running = False
            # Start ollama if not running
            subprocess.Popen(
                ["service", "ollama", "start"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logging.info("Started ollama service")
            # Give it a moment to start up
            import time

            time.sleep(2)

        # Use the Ollama chat API to generate the title and description
        response = chat(
            "llama3.2:latest",
            messages=[{"role": "user", "content": seed_prompt}],
            format=TitleDescriptionResponse.model_json_schema(),
        )

        # Parse the structured JSON response using Pydantic
        try:
            parsed_response = TitleDescriptionResponse.model_validate_json(
                response.message.content
            )

            title = parsed_response.title
            description = parsed_response.description

            print(f"Generated Title: {title}")
            print(f"Generated Description: {description}")

            # Update the seed table with the generated title and description
            cursor.execute(
                "UPDATE seed SET seedTitle = ?, seedDescription = ? WHERE rssId = ?",
                (title, description, rss_id),
            )
            conn.commit()
            logging.info("Seed Title and Description successfully inserted!")

        except ValidationError as e:
            logging.error(f"Validation error in Ollama's response: {e}")
            return

    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)

    finally:
        conn.close()

    # Stop ollama if we started it (it wasn't already running)
    if not ollama_was_running:
        subprocess.run(
            ["service", "ollama", "stop"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logging.info("Stopped ollama service")


def get_random_mp3(directory_path):
    # Check if directory exists
    if not os.path.exists(directory_path):
        return f"Error: Directory '{directory_path}' does not exist."

    # Get all mp3 files in the directory
    mp3_files = [
        file for file in os.listdir(directory_path) if file.lower().endswith(".mp3")
    ]

    # Check if there are any mp3 files
    if not mp3_files:
        return f"No MP3 files found in '{directory_path}'."

    # Select a random mp3 file
    random_mp3 = random.choice(mp3_files)

    # Return the full path to the file
    return os.path.join(directory_path, random_mp3)


def choose_song(rss_array):
    """choose background song"""
    if not rss_array:
        logging.info("No valid RSS entry to process.")
        return

    conn = sqlite3.connect("/root/AI-YouTube-Video-Generator/main.db")
    cursor = conn.cursor()

    try:
        # Extract the seed text and rssId from the input array
        seed_text = rss_array["rssText"]
        rss_id = rss_array["rssId"]

        # Create the seed prompt for Ollama
        seed_prompt = f"""
        I want YouTube video background music from this text '{seed_text}'. choose one of those genres (bright|calm|dark|dramatic|funky|happy|inspirational|sad).
        """

        try:
            subprocess.check_output(["pgrep", "ollama"])
            ollama_was_running = True
        except subprocess.CalledProcessError:
            ollama_was_running = False
            # Start ollama if not running
            subprocess.Popen(
                ["service", "ollama", "start"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logging.info("Started ollama service")
            # Give it a moment to start up
            import time

            time.sleep(2)

        # Use the Ollama chat API to generate the title and description
        response = chat(
            "llama3.2",
            messages=[{"role": "user", "content": seed_prompt}],
            format=songResponse.model_json_schema(),
        )

        # Parse the structured JSON response using Pydantic
        try:
            parsed_response = songResponse.model_validate_json(response.message.content)

            song = parsed_response.genre

            print(f"Choose song genre: {song}")

            mp3 = get_random_mp3(f"/root/AI-YouTube-Video-Generator/song/{song}/")

            # Update the seed table with the generated title and description
            cursor.execute(
                "UPDATE seed SET seedSong = ? WHERE rssId = ?",
                (mp3, rss_id),
            )
            conn.commit()
            logging.info("Seed song successfully inserted!")

        except ValidationError as e:
            logging.error(f"Validation error in Ollama's response: {e}")
            return

    except Exception as e:

        logging.error(f"folder error: {e}")

        mp3 = get_random_mp3(f"/root/AI-YouTube-Video-Generator/song/calm/")

        # Update the seed table with the generated title and description
        cursor.execute(
            "UPDATE seed SET seedSong = ? WHERE rssId = ?",
            (mp3, rss_id),
        )
        conn.commit()
        logging.info("Seed song successfully inserted!")

    finally:
        conn.close()

    # Stop ollama if we started it (it wasn't already running)
    if not ollama_was_running:
        subprocess.run(
            ["service", "ollama", "stop"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        logging.info("Stopped ollama service")


if __name__ == "__main__":
    logging.info("=== Starting application ===")
    # fetch_news_feeds()
    fetch_snopes_feeds()
    rss_entry = get_rss_if_not_in_seed()
    process_rss_to_seed(rss_entry)
    generate_title_description(rss_entry)
    choose_song(rss_entry)
