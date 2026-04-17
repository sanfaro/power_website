import json
import logging
import os
import time
from urllib.parse import urlparse

import requests

# -----------------------------------------------------------------------------
# Configuration & Setup
# -----------------------------------------------------------------------------
JSON_FILE = 'tools.json'
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REQUEST_TIMEOUT = 5  # seconds
RATE_LIMIT_DELAY = 0.5  # seconds between API calls

# Configure basic logging to track the bot's progress in GitHub Actions
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def get_headers() -> dict:
    """Build request headers, injecting the GitHub token if available."""
    headers = {
        'User-Agent': 'CyberSec-Arsenal-Bot/1.0',
        'Accept': 'application/vnd.github.v3+json'
    }
    if GITHUB_TOKEN:
        headers['Authorization'] = f'token {GITHUB_TOKEN}'
    return headers

# -----------------------------------------------------------------------------
# Core Functions
# -----------------------------------------------------------------------------
def check_health(url: str) -> str:
    """
    Perform a lightweight HEAD request to check if a URL is still alive.
    Returns 'active' if the server responds gracefully, otherwise 'offline'.
    """
    try:
        response = requests.head(
            url, 
            headers=get_headers(), 
            timeout=REQUEST_TIMEOUT, 
            allow_redirects=True
        )
        # Consider anything under 400 as a healthy response
        if response.status_code < 400:
            return "active"
        
        # If HEAD fails (some strict servers block it), fallback to GET
        if response.status_code in (403, 405):
            fallback = requests.get(url, headers=get_headers(), timeout=REQUEST_TIMEOUT, stream=True)
            if fallback.status_code < 400:
                return "active"
                
    except requests.RequestException:
        pass  # DNS failures, timeouts, or connection drops
        
    return "offline"

def fetch_github_stars(url: str) -> int | None:
    """
    Extract the repository path from a GitHub URL and fetch its current star count.
    Returns the integer count, or None if it's not a valid GitHub repo.
    """
    parsed_url = urlparse(url)
    
    # We only care about standard github.com repository links
    if parsed_url.netloc != "github.com":
        return None
        
    # Extract 'username/repo' from the URL path
    path_parts = parsed_url.path.strip('/').split('/')
    if len(path_parts) < 2:
        return None
        
    repo_path = f"{path_parts[0]}/{path_parts[1]}"
    api_url = f"https://api.github.com/repos/{repo_path}"
    
    try:
        response = requests.get(api_url, headers=get_headers(), timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            repo_data = response.json()
            return repo_data.get('stargazers_count')
    except requests.RequestException:
        logging.warning(f"Failed to fetch stars for {repo_path}")
        
    return None

# -----------------------------------------------------------------------------
# Main Execution
# -----------------------------------------------------------------------------
def update_database():
    """Main pipeline: load DB, verify links, fetch metadata, and save."""
    if not os.path.exists(JSON_FILE):
        logging.error(f"Database file '{JSON_FILE}' not found. Aborting.")
        return

    # Load existing tools
    with open(JSON_FILE, 'r', encoding='utf-8') as file:
        try:
            tools = json.load(file)
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON format in '{JSON_FILE}': {e}")
            return

    logging.info(f"Starting health check and metadata sync for {len(tools)} tools...")

    # Process each tool
    for tool in tools:
        name = tool.get('name', 'Unknown Tool')
        url = tool.get('url')
        
        if not url:
            logging.warning(f"Skipping '{name}' - No URL provided.")
            continue
            
        logging.info(f"Scanning: {name}...")
        
        # 1. Update Health Status
        tool['status'] = check_health(url)
        
        # 2. Update GitHub Stars (if applicable)
        stars = fetch_github_stars(url)
        if stars is not None:
            tool['stars'] = stars
            
        # Be a good internet citizen: rate-limit our API calls
        time.sleep(RATE_LIMIT_DELAY)

    # Save the enriched data back to the file
    with open(JSON_FILE, 'w', encoding='utf-8') as file:
        json.dump(tools, file, indent=2, ensure_ascii=False)
        
    logging.info("Database successfully updated and saved.")

if __name__ == "__main__":
    update_database()