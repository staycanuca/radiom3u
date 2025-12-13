import os
import sys
import time
import re
import requests
import hashlib
import logging
from datetime import datetime

# --- CONFIGURATION ---
TARGET_COUNTRY = "Romania"  # Set the target country here
OUTPUT_FILE = f"{TARGET_COUNTRY}.m3u"
PLACES_URL = "https://radio.garden/api/ara/content/places"

# --- HELPER FUNCTIONS ---

def setup_logging():
    """
    Configures logging to output to console.
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

def get_places(target_country):
    """
    Fetches all places and filters them by the target country.
    Returns a list of dicts: [{'id': '...', 'title': '...', 'geo': [...]}]
    """
    logging.info("Fetching list of all places...")
    try:
        resp = requests.get(PLACES_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        places_list = data.get('data', {}).get('list', [])
        
        filtered_places = [
            p for p in places_list 
            if p.get('country') == target_country
        ]
        
        logging.info(f"Found {len(filtered_places)} places in {target_country}.")
        return filtered_places
        
    except Exception as e:
        logging.error(f"Failed to fetch places: {e}")
        return []

def get_deterministic_id(unique_string):
    """
    Generates a consistent integer ID starting with 300.
    """
    hash_object = hashlib.md5(unique_string.encode())
    hex_dig = hash_object.hexdigest()
    int_val = int(hex_dig, 16)
    short_id = str(int_val)[:6]
    return f"300{short_id}"

def extract_id_from_url(url_path):
    """
    Parses URL to return the last segment (ID).
    """
    try:
        parts = url_path.strip("/").split("/")
        return parts[-1]
    except Exception:
        return None

# --- NEW FUNCTION TO RESOLVE REDIRECT ---
def get_final_stream_url(initial_url, channel_id):
    """
    Executes a HEAD request on the initial stream URL to follow the 302 redirect
    and extract the final, playable stream URL from the 'location' header.
    
    Returns the final URL or the initial URL if resolution fails.
    """
    headers = {
        # Mimicking browser to ensure successful stream resolution
        "Accept": "*/*",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    }
    
    try:
        # Use HEAD request and prevent automatic redirects
        resp = requests.head(initial_url, headers=headers, allow_redirects=False, timeout=10)
        
        # Check for 302 Found status code
        if resp.status_code == 302:
            final_url = resp.headers.get("location") # Extract the location header 
            if final_url:
                logging.info(f"Resolved stream URL for {channel_id}: {final_url}")
                return final_url
            else:
                logging.warning(f"302 status but no 'location' header for {channel_id}. Falling back to initial URL.")
        else:
            logging.warning(f"Unexpected status code {resp.status_code} for {channel_id}. Falling back to initial URL.")
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to resolve final stream URL for {channel_id}: {e}")
        
    # Fallback to the initial, unredirected URL
    return initial_url

from urllib.parse import urlparse
import os

LOGO_DEV_TOKEN = os.getenv("LOGO_DEV_TOKEN", "pk_b0RiC-anSWOcvgBmS9Qy7Q")

# --- PROCESS HANDLERS ---

def get_logo_from_website(website_url):
    """
    Uses Clearbit Logo API to get a logo from the station's website domain.
    """
    if not website_url:
        return None
        
    try:
        # Extract domain (e.g., "http://www.radiozu.ro" -> "radiozu.ro")
        parsed = urlparse(website_url)
        domain = parsed.netloc
        
        # Remove 'www.' if present
        if domain.startswith("www."):
            domain = domain[4:]
            
        # Filter out generic social media domains to avoid getting Facebook/Insta logos
        generic_domains = ["facebook.com", "instagram.com", "twitter.com", "youtube.com", "t.co", "goo.gl"]
        if any(g in domain for g in generic_domains):
            return None
            
        if domain:
            # Using img.logo.dev as requested
            return f"https://img.logo.dev/{domain}?token={LOGO_DEV_TOKEN}"
            
    except Exception:
        pass
    return None

def get_channel_info(page, channel_unique_id, place_name=""):
    """
    Extracts relevant info for M3U and resolves the stream URL.
    """
    title = page.get("title", "Unknown Station")
    place = page.get("place", {}).get("title", place_name)
    country = page.get("country", {}).get("title", TARGET_COUNTRY)
    website = page.get("website", "")
    
    # Construct the initial stream URL
    initial_stream_url = f"https://radio.garden/api/ara/content/listen/{channel_unique_id}/channel.mp3"
    
    # RESOLVE THE FINAL STREAM URL
    final_stream_url = get_final_stream_url(initial_stream_url, channel_unique_id)
    
    # GET LOGO FROM CLEARBIT
    logo_url = get_logo_from_website(website)
    
    # Fallback: Use a generic icon if no website logo found
    if not logo_url:
        # Using a reliable placeholder service with initials or text
        safe_title = title.replace(" ", "+")
        logo_url = f"https://ui-avatars.com/api/?name={safe_title}&background=random&color=fff&size=128"

    return {
        "title": title,
        "stream_url": final_stream_url,
        "logo_url": logo_url,
        "group_title": country,
        "city": place
    }

def fetch_stations_from_place(place_id, place_name):
    """
    Fetches stations for a specific place ID.
    """
    url = f"https://radio.garden/api/ara/content/page/{place_id}/channels"
    stations = []
    
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return []
            
        data = resp.json()
        content_list = data.get("data", {}).get("content", [])
        
        for section in content_list:
            items = section.get("items", [])
            for item in items:
                page = item.get("page", {})
                if page.get("type") == "channel":
                    raw_url = page.get("url", "")
                    channel_id = extract_id_from_url(raw_url)
                    if channel_id:
                        info = get_channel_info(page, channel_id, place_name)
                        stations.append(info)
                        
    except Exception as e:
        logging.warning(f"Error fetching stations for {place_name}: {e}")

    return stations


def process_full_country_scan(target_country):
    """
    Scans all places in the country and aggregates stations.
    """
    places = get_places(target_country)
    if not places:
        logging.warning(f"No places found for {target_country}.")
        return []
    
    all_stations = []
    total_places = len(places)
    
    for idx, place in enumerate(places, 1):
        place_name = place.get('title')
        place_id = place.get('id')
        
        logging.info(f"[{idx}/{total_places}] Scanning: {place_name}...")
        
        stations = fetch_stations_from_place(place_id, place_name)
        if stations:
            all_stations.extend(stations)
            
        # Optional: slight delay to be nice to the API
        # time.sleep(0.1) 
        
    return all_stations

def save_to_m3u(stations, filename):
    """
    Saves the list of stations to an M3U file.
    """
    # Remove duplicates based on title and stream_url
    unique_stations = {}
    for s in stations:
        key = (s['title'], s['stream_url'])
        if key not in unique_stations:
            unique_stations[key] = s
            
    final_list = list(unique_stations.values())
    
    # Sort alphabetically by title since Radio Garden doesn't provide popularity metrics
    final_list.sort(key=lambda x: x['title'])
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for station in final_list:
            # Format: #EXTINF:-1 group-title="Country" tvg-logo="LogoURL",Title - City
            display_title = f"{station['title']}" if station['city'] else station['title']
            
            line_info = f'#EXTINF:-1 group-title="{station["group_title"]}" tvg-logo="{station["logo_url"]}",{display_title}'
            f.write(line_info + "\n")
            f.write(station['stream_url'] + "\n")
    
    logging.info(f"Successfully saved {len(final_list)} unique stations to {filename}")

# --- EXECUTION ENTRY POINT ---

def main_job():
    """
    Main function.
    """
    setup_logging()
    
    logging.info(f"Starting FULL scan job for country: {TARGET_COUNTRY}")
    
    stations = process_full_country_scan(TARGET_COUNTRY)
    
    if stations:
        save_to_m3u(stations, OUTPUT_FILE)
    else:
        logging.warning("No stations found.")

    logging.info("Job complete.")


if __name__ == "__main__":
    try:
        main_job()
    except Exception as e:
        logging.error(f"FATAL ERROR: An unexpected error occurred: {e}")
        sys.exit(1)
