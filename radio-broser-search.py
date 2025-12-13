import requests
import urllib.parse
from urllib.parse import urlparse
import os

# Configuration
TARGET_COUNTRY = "Romania"
OUTPUT_FILE = f"Radio Browser - {TARGET_COUNTRY}.m3u"
# Read from Environment Variable (for GitHub Actions) or use fallback (for local run)
LOGO_DEV_TOKEN = os.getenv("LOGO_DEV_TOKEN", "pk_b0RiC-anSWOcvgBmS9Qy7Q")

def get_logo_from_website(website_url):
    """
    Uses img.logo.dev to get a logo from the station's website domain.
    """
    if not website_url:
        return None
        
    try:
        parsed = urlparse(website_url)
        domain = parsed.netloc
        
        if domain.startswith("www."):
            domain = domain[4:]
            
        generic_domains = ["facebook.com", "instagram.com", "twitter.com", "youtube.com", "t.co", "goo.gl", "shoutcast.com", "zeno.fm"]
        if any(g in domain for g in generic_domains):
            return None
            
        if domain:
            return f"https://img.logo.dev/{domain}?token={LOGO_DEV_TOKEN}"
            
    except Exception:
        pass
    return None


print(f"Fetching stations for {TARGET_COUNTRY} from Radio Browser API...")

try:
    # Use the country-specific endpoint for efficiency
    encoded_country = urllib.parse.quote(TARGET_COUNTRY)
    url = f"http://de1.api.radio-browser.info/json/stations/bycountry/{encoded_country}"
    
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    
    if r.status_code == 200:
        data = r.json()
        print(f"Found {len(data)} stations in {TARGET_COUNTRY}.")
        
        # Sort by popularity (clickcount) descending
        print("Sorting stations by popularity (clickcount)...")
        data.sort(key=lambda x: int(x.get('clickcount', 0)), reverse=True)

        # Open file ONCE with UTF-8 encoding
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as file:
            file.write("#EXTM3U\n")

            for item in data:
                try:
                    name = item.get('name', 'Unknown').strip()
                    logo = item.get('favicon', '').strip()
                    url = item.get('url_resolved', '').strip()
                    homepage = item.get('homepage', '').strip()
                    state = item.get('state', '').strip()
                    
                    # Fallback for logo if favicon is missing
                    if not logo and homepage:
                        logo = get_logo_from_website(homepage)
                        
                    # Fallback if no logo at all (neither favicon nor from website)
                    if not logo:
                        safe_title = name.replace(" ", "+")
                        logo = f"https://ui-avatars.com/api/?name={safe_title}&background=random&color=fff&size=128"

                    display_title = name
                    if state:
                        display_title += f" - {state}"
                    
                    if url:
                        file.write(f'#EXTINF:-1 group-title="{TARGET_COUNTRY}" radio="true" tvg-logo="{logo}",{display_title}\n')
                        file.write(f"{url}\n")
                except Exception:
                    continue
                    
        print(f"Done! Saved to {OUTPUT_FILE}")

except Exception as e:
    print(f"Error: {e}")
