import sys
import requests
import concurrent.futures
from urllib.parse import urlparse
import time

# Configuration
TIMEOUT_SECONDS = 3  # Maximum time to wait for a stream to respond
MAX_WORKERS = 50     # Number of parallel checks (increase for speed, decrease for stability)

def is_stream_playable(url):
    """
    Rigorously tests if a URL is a valid audio stream.
    Checks: DNS/Connection, HTTP Status, Content-Type headers.
    """
    headers = {
        "User-Agent": "VLC/3.0.18 LibVLC/3.0.18" # Mimic a real player
    }
    
    try:
        # 1. Try HEAD request first (lighter)
        r = requests.head(url, headers=headers, timeout=TIMEOUT_SECONDS, allow_redirects=True)
        
        # If HEAD fails with 405 (Method Not Allowed) or similar, try GET
        if r.status_code == 405 or r.status_code == 404:
            r = requests.get(url, headers=headers, stream=True, timeout=TIMEOUT_SECONDS)
            r.close() # Close connection immediately, we just need headers
            
        # 2. Check Status Code
        if r.status_code >= 400:
            return False, f"Status {r.status_code}"

        # 3. Check Content-Type (The rigorous part)
        content_type = r.headers.get('Content-Type', '').lower()
        
        # Valid audio mime types
        valid_types = ['audio', 'ogg', 'video/mp2t', 'application/octet-stream'] 
        # video/mp2t is common for HLS streams (.m3u8)
        # application/octet-stream is generic but often used for audio
        
        is_audio = any(t in content_type for t in valid_types) 
        
        if not is_audio:
            # Trap for "Stream Offline" HTML pages returning 200 OK
            if 'text/html' in content_type:
                return False, "HTML Page (Not Audio)"
            return False, f"Invalid Type: {content_type}"

        return True, "OK"

    except requests.exceptions.Timeout:
        return False, "Timeout"
    except requests.exceptions.ConnectionError:
        return False, "Connection Error"
    except Exception as e:
        return False, str(e)

def parse_m3u(file_path):
    """Parses M3U file into a list of dicts."""
    entries = []
    current_entry = {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith("#EXTINF"):
                current_entry['extinf'] = line
            elif line.startswith("#") and not line.startswith("#EXTM3U"):
                # Preserve other tags like #EXTGRP if present
                if 'tags' not in current_entry:
                    current_entry['tags'] = []
                current_entry['tags'].append(line)
            elif not line.startswith("#"):
                current_entry['url'] = line
                if 'extinf' in current_entry: # Only add if we have metadata
                    entries.append(current_entry)
                current_entry = {} # Reset
                
    except Exception as e:
        print(f"Error reading file: {e}")
        return []
        
    return entries

def validate_m3u_file(input_file):
    print(f"Reading {input_file}...")
    entries = parse_m3u(input_file)
    
    if not entries:
        print("No entries found or file error.")
        return

    print(f"Found {len(entries)} streams. Validating with {MAX_WORKERS} threads...")
    print(f"This might take about {len(entries) // MAX_WORKERS * TIMEOUT_SECONDS / 60:.1f} minutes.")

    valid_entries = []
    dead_entries = 0
    
    start_time = time.time()
    
    # Use ThreadPoolExecutor for parallel processing
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Create a dictionary to map futures to entries
        future_to_entry = {executor.submit(is_stream_playable, entry['url']): entry for entry in entries}
        
        completed = 0
        total = len(entries)
        
        for future in concurrent.futures.as_completed(future_to_entry):
            entry = future_to_entry[future]
            completed += 1
            
            # Simple progress bar
            if completed % 50 == 0:
                print(f"Progress: {completed}/{total} ({completed/total*100:.1f}%)")
            
            try:
                is_valid, reason = future.result()
                if is_valid:
                    valid_entries.append(entry)
                else:
                    dead_entries += 1
                    # Optional: Print dead streams
                    # print(f"DEAD: {entry['url']} -> {reason}")
            except Exception as exc:
                dead_entries += 1

    duration = time.time() - start_time
    
    # Write output
    output_file = input_file.replace(".m3u", "_validated.m3u")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for entry in valid_entries:
            f.write(f"{entry['extinf']}\n")
            if 'tags' in entry:
                for tag in entry['tags']:
                    f.write(f"{tag}\n")
            f.write(f"{entry['url']}\n")
            
    print("-" * 30)
    print(f"Validation Complete in {duration:.1f} seconds.")
    print(f"Total Streams: {len(entries)}")
    print(f"Working Streams: {len(valid_entries)}")
    print(f"Dead Streams: {dead_entries}")
    print(f"Saved clean playlist to: {output_file}")
    print("-" * 30)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_m3u.py <filename.m3u>")
        print("Example: python validate_m3u.py \"Radio Browser - Romania.m3u\"")
    else:
        validate_m3u_file(sys.argv[1])
