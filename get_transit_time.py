import logging
from typing import Optional, Tuple, List, Callable
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from urllib.parse import quote
from datetime import datetime
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed

def create_cache_db():
    conn = sqlite3.connect('transit_cache.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transit_cache (
        uuid INTEGER PRIMARY KEY AUTOINCREMENT,       
        origin TEXT,
        destination TEXT,
        depart_time TEXT,  
        transit_time TEXT,
        duration INTEGER
    )
''') # use TEXT to handle None values for other applactions

    conn.commit()
    conn.close()

create_cache_db()

def check_transit_cache(origin: str, destination: str, depart_time: Optional[int]) -> Optional[str]:
    """
    Check if transit time exists in cache.
    
    Args:
        origin (str): Starting location
        destination (str): Ending location
        depart_time (Optional[int]): Departure time
        
    Returns:
        Optional[str]: Cached transit time if found, None otherwise
    """
    conn = sqlite3.connect('transit_cache.db')
    cursor = conn.cursor()
    try:
        # Convert depart_time to string to match DB schema
        depart_time_str = str(depart_time) if depart_time is not None else None
        
        cursor.execute('''
            SELECT transit_time FROM transit_cache
            WHERE origin = ? 
            AND destination = ? 
            AND (depart_time = ? OR (depart_time IS NULL AND ? IS NULL))
            AND transit_time IS NOT NULL
        ''', (origin, destination, depart_time_str, depart_time_str))
        
        result = cursor.fetchone()
        return result[0] if result else None
    finally:
        conn.close()

def get_transit_time(origin: str, destination: str, depart_time: Optional[int] = None) -> Tuple[str, Optional[str], Optional[int], str]:
    # Convert depart_time to string to match DB schema
    depart_time_str = str(depart_time) if depart_time is not None else None
    
    # First check the cache
    cached_result = check_transit_cache(origin, destination, depart_time)
    if cached_result:
        return origin, destination, depart_time, cached_result

    # Initialize database connection for storing new results
    conn = sqlite3.connect('transit_cache.db')
    cursor = conn.cursor()
    
    try:
        # Construct URL with encoded parameters
        base_url = "https://www.google.com/maps/dir/"
        url = f"{base_url}{quote(origin)}/{quote(destination)}/data=!4m2!4m1!3e3"
    
        # Add departure time parameter if specified
        if depart_time is not None:
            # Convert departure time to Unix timestamp for today
            today = datetime.now().replace(hour=depart_time, minute=0, second=0, microsecond=0)
            timestamp = int(today.timestamp())
            url = f"{base_url}{quote(origin)}/{quote(destination)}/data=!4m2!4m1!3e3!5m1!2b1!3b1!6e0!7e2!8j{timestamp}"

        # Add more Chrome options to match the working version
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")  # Run in headless mode
        chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
        chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
        chrome_options.add_argument("--disable-gpu")  # Disable GPU acceleration
        chrome_options.add_argument("--window-size=1920x1080")  # Set window size
        chrome_options.add_argument("--disable-extensions")  # Disable extensions

        # Set up the driver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Navigate to the URL
        driver.get(url)
        
        # Wait for the transit time element to be present
        wait = WebDriverWait(driver, 5)
        transit_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".Fk3sm.fontHeadlineSmall")))
        
        if transit_element:
            transit_time = transit_element.text.strip()
            
            # Now cursor and conn are defined
            cursor.execute('''
                INSERT INTO transit_cache (origin, destination, depart_time, transit_time)
                VALUES (?, ?, ?, ?)
            ''', (origin, destination, depart_time_str, transit_time))
            conn.commit()
            
            driver.quit()
            return origin, destination, depart_time, transit_time
        else:
            driver.quit()
            return origin, destination, depart_time, None
        
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return origin, destination, depart_time, None
    finally:
        cursor.close()
        conn.close()

def parallel_processing(locations: List[Tuple[str, str]], 
                       transit_function: Callable[[str, str, Optional[int]], Tuple[str, Optional[str], Optional[int], str]] = get_transit_time, 
                       num_workers: int = 5,
                       depart_time: Optional[int] = None) -> List[Tuple[str, Optional[str], Optional[int], str]]:
    """
    Process multiple transit requests in parallel with cache checking.

    Args:
        locations (List[Tuple[str, str]]): List of tuples containing (origin, destination).
        transit_function (Callable): The function to call for each origin-destination pair.
        num_workers (int): Number of concurrent workers.
        depart_time (Optional[int]): Optional departure time for transit checks.

    Returns:
        List[Tuple[Optional[str], str]]: List of results from the transit function.
    """
    results = []
    uncached_locations = []

    print("\nProcessing transit requests...")
    print("-" * 50)

    # First batch process all cache checks
    for origin, destination in locations:
        cached_result = check_transit_cache(origin, destination, depart_time)
        if cached_result:
            print(f"💪 CACHE HIT: {origin} → {destination} = {cached_result}")
            results.append((origin, destination, depart_time, cached_result))
        else:
            print(f"😅 CACHE MISS: {origin} → {destination} (will fetch live)")
            uncached_locations.append((origin, destination))

    # Then process only uncached requests in parallel
    if uncached_locations:
        print(f"\nFetching {len(uncached_locations)} uncached results in parallel...")
        print("-" * 50)
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_location = {
                executor.submit(transit_function, origin, destination, depart_time): (origin, destination)
                for origin, destination in uncached_locations
            }
            
            for future in as_completed(future_to_location):
                origin, destination = future_to_location[future]
                try:
                    result = future.result()
                    
                    # Extract transit time from the result
                    transit_time = result[3]
                    
                    if transit_time:
                        print(f"✅LIVE FETCH: {origin} → {destination} = {transit_time}")
                    else:
                        print(f"❌ FETCH FAILED: {origin} → {destination}")
                    
                    results.append(result)
                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    print(f"✗ ERROR: {origin} → {destination} ({error_msg})")
                    logging.error(f"Error processing {origin} to {destination}: {str(e)}")
                    results.append((origin, destination, depart_time, None))

    print("\nProcessing complete!")
    print(f"Total requests: {len(locations)}")
    print(f"Cache hits: {len(locations) - len(uncached_locations)}")
    print(f"Live fetches: {len(uncached_locations)}")
    print("-" * 50)

    return results


# Example usage
if __name__ == "__main__":
    locations = [
        ("Akihabara Station,tokyo", "Harajuku Station,tokyo"),
        ("Shibuya Station,tokyo", "Shinjuku Station,tokyo"),
        ("Tokyo Tower,tokyo", "meji shrine,tokyo")
    ]
    
    # Test with parallel processing for getting transit times
    transit_results = parallel_processing(locations, get_transit_time, num_workers=5)
    
    for origin, destination, (transit_time, debug_info) in transit_results:
        print(f"Transit time from {origin} to {destination}: {transit_time}")
        print("\nDebug Information:")
        print(debug_info)
