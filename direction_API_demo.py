import gradio as gr
import sqlite3
import re 
import googlemaps
import folium
import numpy as np
from tqdm import tqdm
from datetime import datetime, timedelta
import time
from functools import lru_cache # we should save/load cache from local disk instead of RAM
from typing import List, Optional
import pytz
'''
this version of code use google api for getting transit time in tokyo, which is not supported due to licensing restrictions
but i'm arachiving this code for use with other cities in the future

'''

# Global variable declaration
Directions_API: Optional[googlemaps.Client] = None

class DatabaseConnection:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = None
        self.cursor = None

    def __enter__(self):
        self.connection = sqlite3.connect(self.db_path)
        self.cursor = self.connection.cursor()
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection:
            self.connection.close()

def set_api_key(api_key: str) -> str:
    """
    Set the Google Maps API key for the application.
    
    Args:
        api_key (str): Valid Google Maps API key
        
    Returns:
        str: Success message
    """
    global Directions_API
    try:
        Directions_API = googlemaps.Client(key=api_key)
        return "API Key set successfully!"
    except Exception as e:
        return f"Failed to set API key: {str(e)}"

def format_station_name(base_name: str) -> str:
    """
    Formats a station name based on data in the 'property' table.

    Args:
        base_name (str): The base name of the station.

    Returns:
        str: The formatted station name in the format "Station Station, Prefecture".
    """
    # Establish a connection to your database
    connection = sqlite3.connect("Dataset/tokyo_rent.db")  # Replace with your database path
    cursor = connection.cursor()
    try:
        # Query the database for the station and prefecture
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute(
            "SELECT station, prefecture FROM properties WHERE station = ?",
            (base_name,)
        )
        result = cursor.fetchone()

        # Check if the query returned a result
        if result:
            station, prefecture = result
            return f"{station} Station, {prefecture}"
        else:
            print(f"Station not found in the database: {base_name}")  # Add this line for debugging
            return f"Station not found: {base_name}"
    except sqlite3.Error as e:
        print(f"An error occurred while querying the database: {e}")  # Add this line for debugging
        return f"Database error: {e}"
    finally:
        # Ensure the connection is closed
        connection.close()

def get_departure_time() -> datetime:
    """Get departure time at 8 AM Tokyo time"""
    tokyo_tz = pytz.timezone('Asia/Tokyo')
    return datetime.now(tokyo_tz).replace(hour=8, minute=0, second=0, microsecond=0)

# Initialize station options
def get_station_options() -> List[str]:
    """Get all unique station names from the database."""
    with DatabaseConnection('Dataset/tokyo_rent.db') as cursor:
        cursor.execute('SELECT DISTINCT station FROM properties')
        return [row[0] for row in cursor.fetchall()]

all_station_options = get_station_options()

# create a function to get the loactions with dropdown meune for unique stations in sqlite database's 'stations' colume, user should select nearst station of their school/company, and the nearest station of their hangout place, then enter the walking distance from the station to the school/company and the walking distance from the station to the hangout place in mimutes as interger, and time they willing to spend on subway to reach the hangout place in minutes 'hangout_metro_time'  as interger,and time they willing to spend on subway to reach the company/school in minutes "daily_commute_time" as interger in sepreate input boxes. save as global variables

#calcufindlate reachable based on the user input, use google maps api to get all reachable metro stations within given minutes, for example if user enterted 'shijuku' and 'akihabar'. return all reachble stations from these 2 stations under each specified 'hangout_metro_time' and 'daily_commute_time' mimuntes. output text in gradio "loaction avaiblity" text output filed, this filed should contain the name list of stations reachable from the company station and the name of stations reachable from the hangout station, and the name of overlaping stations in yellow color.

def rate_limited_request(func):
    """Decorator to limit the rate of API requests."""
    def wrapper(*args, **kwargs):
        time.sleep(1)  # Wait 1 second between requests
        return func(*args, **kwargs)
    return wrapper

@rate_limited_request
@lru_cache(maxsize=6400) #"""Find all stations reachable within max_time minutes from start station."""
def find_reachable_stations(start_station, max_time):
    # ...
    formatted_origin = format_station_name(start_station)  # Format origin station
    reachable = set()  # Using a set to store reachable stations

    for target in tqdm(all_station_options, desc="Finding reachable stations"):
        try:
            formatted_destination = format_station_name(target)
            if formatted_destination is None:
                continue

            # Check if transit service exists between points
            if not check_transit_available(Directions_API, formatted_origin, formatted_destination, "8:00am"):
                continue

            directions = Directions_API.directions(formatted_origin, formatted_destination, mode="transit", departure_time="8:00am")
            duration = directions[0]['legs'][0]['duration']['value'] / 60
            if duration <= max_time and target != start_station:
                reachable.add(target)
        except Exception as e:
            if "ZERO_RESULTS" in str(e):
                continue
            print(f"Error getting directions from {formatted_origin} to {formatted_destination}: {e}, check if the depeture time is correct set at 8am JST time, or if the depeture adress is proproly formated like 'xxx station, <prefture>' ")
    return list(reachable)  # Returning a list of reachable stations


@rate_limited_request
@lru_cache(maxsize=6400)
def get_station_coords(station_name):
    # Add formatting here
    formatted_station = format_station_name(station_name)
    try:
        # Use formatted station name for geocoding
        geocode_result = Directions_API.geocode(formatted_station)
        if geocode_result and len(geocode_result) > 0:
            location = geocode_result[0]['geometry']['location']
            return location['lat'], location['lng']
        else:
            print(f"No geocode results for station: {formatted_station}")
            return None

    except Exception as e:
        print(f"Error getting coordinates for {formatted_station}: {e}")
        return None
@rate_limited_request
@lru_cache(maxsize=6400)
def analyze_locations(company_station, hangout_station, walking_distance_to_company, 
                     walking_distance_to_hangout, hangout_metro_time, daily_commute_time,
                     budget, room_size):
    if not 'Directions_API' in globals():
        return "Please set Google Maps API key first!", None

    # Get reachable stations
    # Remove leading and trailing whitespace from station names
    company_station = company_station.strip()
    hangout_station = hangout_station.strip()

    # Format station names using format_station_name function
    formatted_company_station = format_station_name(company_station)
    formatted_hangout_station = format_station_name(hangout_station)

    # Find reachable stations
    company_reachable = find_reachable_stations(formatted_company_station, daily_commute_time)
    hangout_reachable = find_reachable_stations(formatted_hangout_station, hangout_metro_time)


def reachble_stations_visualization(company_station, hangout_station, company_reachable, hangout_reachable):
    company_coords = get_station_coords(company_station)
    hangout_coords = get_station_coords(hangout_station)

    m = folium.Map(location=company_coords, zoom_start=13)

    # Company circle (blue)
    folium.Circle(
        company_coords,
        radius=5000,
        color='blue',
        fill=True,
        opacity=0.2,
        popup=f"Company: {company_station}"
    ).add_to(m)

    # Hangout circle (pink)
    folium.Circle(
        hangout_coords,
        radius=5000,
        color='pink',
        fill=True,
        opacity=0.2,
        popup=f"Hangout: {hangout_station}"
    ).add_to(m)

    # Add markers for overlapping stations
    overlap = set(company_reachable) & set(hangout_reachable)
    for station in overlap:
        coords = get_station_coords(station)
        sqlite3.Cursor.execute('SELECT AVG(price_per_sqm) FROM properties WHERE station = ?', (station,))
        avg_price = sqlite3.Cursor.fetchone()[0]

        folium.CircleMarker(
            coords,
            radius=5,
            color='red',
            fill=True,
            popup=f"{station}<br>Avg ¥{int(avg_price)}/m²"
        ).add_to(m)

    return m._repr_html_()



# Create Gradio interface
with gr.Blocks() as demo:
    with gr.Row():
        api_key_input = gr.Textbox(label="Enter Google Maps API Key")
        api_submit = gr.Button("Set API Key")

    with gr.Row():
        company_station = gr.Dropdown(choices=all_station_options, label="Company/School Station")
        hangout_station = gr.Dropdown(choices=all_station_options, label="Hangout Station")

    with gr.Row():
        walking_to_company = gr.Number(label="Walking time to Company (minutes)", value=15)
        walking_to_hangout = gr.Number(label="Walking time to Hangout (minutes)", value=15)

    with gr.Row():
        commute_time = gr.Number(label="Max transit time to Company (minutes)", value=30)
        hangout_time = gr.Number(label="Max transit time to Hangout (minutes)", value=30)

    with gr.Row():
        budget = gr.Number(label="Monthly Budget (¥)", value=150000)
        room_size = gr.Number(label="Desired Room Size (m²)", value=25)

    search_button = gr.Button("Search")
    output_text = gr.Textbox(label="Location Availability")
    map_output = gr.HTML(label="Map")

    api_submit.click(fn=set_api_key, inputs=[api_key_input], outputs=[output_text])
    search_button.click(
        fn=analyze_locations,
        inputs=[company_station, hangout_station, walking_to_company, walking_to_hangout, 
                hangout_time, commute_time, budget, room_size],
        outputs=[output_text, map_output]
    )



def check_transit_available(gmaps, origin, destination, departure_time):
    # Check if transit service exists between points
    distance_matrix = gmaps.distance_matrix(
        origins=origin,
        destinations=destination,
        mode="transit",
        departure_time=departure_time
    )

    if distance_matrix['rows'][0]['elements'][0]['status'] == 'ZERO_RESULTS':
        return False
    return True


@lru_cache(maxsize=1000)
def get_transit_time(origin: str, destination: str) -> dict:
    """Cache and get directions between stations"""
    if not Directions_API:
        raise ValueError("Google Maps API not initialized")

   # Get Tokyo timezone
    tokyo_tz = pytz.timezone('Asia/Tokyo')
    # Set departure time to 8 AM JST
    departure_time = datetime.now(tokyo_tz).replace(hour=8, minute=0, second=0, microsecond=0)
    
    formatted_origin = format_station_name(origin)
    formatted_destination = format_station_name(destination)
    
    print(f"Formatted origin: {formatted_origin}")  # Add this line for debugging
    print(f"Formatted destination: {formatted_destination}")  # Add this line for debugging

    if check_transit_available(Directions_API, origin, destination, departure_time):
            directions_result = Directions_API.directions(
            origin,
            destination,
            mode="transit",
            departure_time=departure_time
        )
    else:
        print("No transit service available, which is not possible, please trace check_transit_available function")
        directions_result = 0

        if directions_result:
        # Get first route
            route = directions_result[0]
            # Get total duration
            duration = route['legs'][0]['duration']['text']
            # Get steps for the journey
            steps = route['legs'][0]['steps']

            print(f"\nTransit from {formatted_origin} to {formatted_destination}:")
            print(f"Total duration: {duration}")
            print("\nRoute details:")

            for step in steps:
                if step['travel_mode'] == 'TRANSIT':
                    transit_details = step['transit_details']
                    line = transit_details['line']['name']
                    departure_stop = transit_details['departure_stop']['name']
                    arrival_stop = transit_details['arrival_stop']['name']
                    step_duration = step['duration']['text']
                    print(f"- Take {line} from {departure_stop} to {arrival_stop} ({step_duration})")
        else:
            print("No route found, did you check the deperture time property passed to the API?")
    
    try:
        return Directions_API.directions(
            origin=formatted_origin,
            destination=formatted_destination,
            mode="transit",
            departure_time=departure_time
        )
    except Exception as e:
        print(f"Error getting directions from {formatted_origin} to {formatted_destination}: {str(e)}")
        return None

if __name__ == "__main__":
    demo.launch()




