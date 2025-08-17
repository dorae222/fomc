
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Base URL for the FOMC calendars
BASE_URL = "https://www.federalreserve.gov"
CALENDAR_URL = urljoin(BASE_URL, "/monetarypolicy/fomccalendars.htm")

# Output directory for downloaded files
OUTPUT_DIR = "data/raw/2023_2025_crawled"
STATEMENTS_DIR = os.path.join(OUTPUT_DIR, "statements")
TRANSCRIPTS_DIR = os.path.join(OUTPUT_DIR, "transcripts")

def setup_directories():
    """Create output directories if they don't exist."""
    os.makedirs(STATEMENTS_DIR, exist_ok=True)
    os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

def download_file(url, folder, filename=None):
    """Download a file from a URL to a specified folder."""
    if not filename:
        filename = url.split('/')[-1]
    
    # Ensure filename is valid
    if not filename or '?' in filename:
        filename = "downloaded_file_" + url.split('/')[-2] + ".pdf"


    filepath = os.path.join(folder, filename)
    
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Successfully downloaded {url} to {filepath}")
        return filepath
    except requests.exceptions.RequestException as e:
        print(f"Failed to download {url}: {e}")
        return None

def get_soup(url):
    """Fetch a URL and return a BeautifulSoup object."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch {url}: {e}")
        return None

def main():
    """Main function to crawl and download FOMC documents."""
    setup_directories()
    
    print(f"Fetching calendar page: {CALENDAR_URL}")
    soup = get_soup(CALENDAR_URL)
    
    if not soup:
        print("Could not retrieve the main calendar page. Exiting.")
        return

    links = soup.find_all('a', href=True)
    print(f"Found {len(links)} links on the calendar page.")

    for link in links:
        href = link['href']
        link_text = link.get_text(strip=True)
        
        # Construct absolute URL
        absolute_url = urljoin(BASE_URL, href)

        # Filter for years 2023, 2024, 2025
        if not any(year in href for year in ["2023", "2024", "2025"]):
            continue

        # --- Download PDF Statements ---
        if ('monetary' in href and href.endswith('.pdf')) or ('statement' in link_text.lower() and href.endswith('.pdf')):
            # Heuristic to avoid downloading other monetary policy documents.
            # FOMC statements usually have a date in the filename like YYYYMMDD.
            if re.search(r'(2023|2024|2025)\d{4}', href):
                print(f"Found Statement PDF: {absolute_url}")
                download_file(absolute_url, STATEMENTS_DIR)

        # --- Download Press Conference Transcripts ---
        if "press conference" in link_text.lower() and href.endswith('.htm'):
            print(f"Found Press Conference page: {absolute_url}")
            transcript_soup = get_soup(absolute_url)
            if transcript_soup:
                # Find the link to the transcript PDF on the press conference page
                transcript_link = None
                for a in transcript_soup.find_all('a', href=True):
                    if a.get('href', '').endswith('.pdf') and 'transcript' in a.get_text(strip=True).lower():
                        transcript_link = a
                        break
                
                if transcript_link:
                    transcript_url = urljoin(BASE_URL, transcript_link['href'])
                    print(f"  Found Transcript PDF: {transcript_url}")
                    download_file(transcript_url, TRANSCRIPTS_DIR)
                else:
                    print(f"  No transcript PDF found on {absolute_url}")

if __name__ == "__main__":
    main()
