"""
this is Gradio interface for visualize your 'living circles', it tells you where you SHOULD be living for higer hapniess score.

How to use:
1. select the nerest station from your university/company using dropdown menu
2. select the nerest station from your usual hangout places or your part-time job site, like "akihabara station"
3. input your max commute time for each location, like "30", "40"
4. click 'submit'

now go make a coffee as this can take VERY LONG if this is your first time running this program.

when the program is done. you will see a map with your 'living circles' and all stations that are within your commute time. the edge of the circle is the furthest point you can reach within your commute time.
cross sections of the 2 circles will be highlighted in yellow. this is where you SHOULD living. not where you can or where you want. but where you SHOULD.

the text output section will be giving you the list of stations within the cross section of the 2 circles. (by comparing the filted list of stations from the 2 circles, the overlaping station will be displayed)


"""

import gradio as gr
import get_transit_time as gt #   """Helper function to get transit time between two locations"""
from direction_API_demo import format_station_name as pretty_name #   """Helper function to format station names as <xxx station, prefecture> to pass to get_transit_time"""
from direction_API_demo import get_station_options as all_stations #   """Helper function to get unique stations names, unformated """
import overlay_plotter as op #   """Helper function to get coordinates for a station to drawing overlay on map"""
import sqlite3
import re
import folium
import html

def get_prefectures():
    conn = sqlite3.connect('Dataset/tokyo_rent.db')
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT prefecture FROM properties')
    prefectures = [row[0] for row in cursor.fetchall()]
    conn.close()
    return prefectures

def process_commute_circles(
    company_station: str, 
    hangout_station: str, 
    company_time: int, 
    hangout_time: int, 
    selected_prefectures: list
):
    _ = op.CirclePlotter()  # Initialize cache before processing
    # Format station names
    company_formatted = pretty_name(company_station)
    hangout_formatted = pretty_name(hangout_station)
    
    company_coords = op.CirclePlotter().get_location_coordinates(company_formatted)
    if not company_coords or isinstance(company_coords, str):
        return f"<div style='color:red'>Error: Invalid coordinates for '{html.escape(company_formatted)}'</div>", ""

    hangout_coords = op.CirclePlotter().get_location_coordinates(hangout_formatted)
    if not hangout_coords or isinstance(hangout_coords, str):
        return f"<div style='color:red'>Error: Invalid coordinates for '{html.escape(hangout_formatted)}'</div>", ""

    # Fetch filtered stations based on prefectures
    main_conn = sqlite3.connect('Dataset/tokyo_rent.db')
    main_cursor = main_conn.cursor()
    
    if selected_prefectures:
        query = '''
            SELECT DISTINCT station 
            FROM properties 
            WHERE prefecture IN ({})
        '''.format(','.join(['?'] * len(selected_prefectures)))
        main_cursor.execute(query, selected_prefectures)
    else:
        main_cursor.execute('SELECT DISTINCT station FROM properties')
    
    all_station_list = [row[0] for row in main_cursor.fetchall()]  # Keep filtered list
    main_conn.close()
    
    # Create station pairs using FILTERED stations
    station_pairs_company = [(company_formatted, pretty_name(station)) for station in all_station_list]
    station_pairs_hangout = [(hangout_formatted, pretty_name(station)) for station in all_station_list]
    
    # Rest of the function remains unchanged...
    
    # Process transit times and store results in cache
    cache_conn = sqlite3.connect('transit_cache.db')
    cache_cursor = cache_conn.cursor()
    
    print("Calculating transit times from company station...")
    company_results = gt.parallel_processing(station_pairs_company, gt.get_transit_time, num_workers=10)
    
    print("Calculating transit times from hangout station...")
    hangout_results = gt.parallel_processing(station_pairs_hangout, gt.get_transit_time, num_workers=10)
    
    # Clean up transit times in database    
    # Update duration using regex patterns for different time formats
    def parse_duration(transit_time):
        if not transit_time:
            return None

        # Define keywords for hours and minutes in various languages
        hour_keywords = {'hr', 'hour', 'hours', 'h', '時間', '小時', '小时', 'stunden', 'heure', 'ora', '시간'}#
        minute_keywords = {'min', 'minute', 'minutes', 'm', '分', '分钟', 'minuti', 'minuten', '분'}

        total_minutes = 0

        # Split into components: find all (number, unit) pairs
        pattern = r'(\d+)\s*([^\d\s]+)'
        matches = re.findall(pattern, transit_time, re.IGNORECASE)

        for number_str, unit in matches:
            number = int(number_str)
            unit_lower = unit.lower()

            # Check for hour keywords
            if any(keyword in unit_lower for keyword in hour_keywords):
                total_minutes += number * 60
            # Check for minute keywords
            elif any(keyword in unit_lower for keyword in minute_keywords):
                total_minutes += number
            else:
                # Fallback: Assume minutes if unit is unrecognized (e.g., numeric only like "30")
                total_minutes += number

        # Handle cases with standalone numbers (no units) after checking all matches
        if not matches:
            last_number = re.search(r'(\d+)\s*$', transit_time)
            if last_number:
                total_minutes += int(last_number.group(1))

        return total_minutes if total_minutes > 0 else None

    # Fetch all transit times
    cache_cursor.execute('SELECT uuid, transit_time FROM transit_cache WHERE duration IS NULL AND transit_time IS NOT NULL')
    transit_times = cache_cursor.fetchall()

    # Process and update durations
    for uuid, transit_time in transit_times:
        duration = parse_duration(transit_time)
        if duration is not None:
            cache_cursor.execute('UPDATE transit_cache SET duration = ? WHERE uuid = ?', (duration, uuid))

    # Commit changes
    cache_conn.commit()

    # Filter stations within commute time limits
    company_stations = cache_cursor.execute('''
        SELECT DISTINCT destination 
        FROM transit_cache 
        WHERE origin = ? AND duration <= ?
    ''', (company_formatted, company_time)).fetchall()
    
    hangout_stations = cache_cursor.execute('''
        SELECT DISTINCT destination 
        FROM transit_cache 
        WHERE origin = ? AND duration <= ?
    ''', (hangout_formatted, hangout_time)).fetchall()
    
    # Commit changes and close cache connection
    cache_conn.commit()
    cache_conn.close()
    
    # Find overlapping stations
    company_set = set(station[0] for station in company_stations)
    hangout_set = set(station[0] for station in hangout_stations)
    overlap_stations = company_set.intersection(hangout_set)

    # Extract raw station names from pretty_name formatted stations
    raw_station_names = [station.split(" Station")[0].strip() for station in overlap_stations]
    unique_raw_names = list(set(raw_station_names))

    # Query rent data
    rent_data = {}
    if unique_raw_names:
        main_conn = sqlite3.connect('Dataset/tokyo_rent.db')
        main_cursor = main_conn.cursor()
        query = '''
            SELECT station, cost_per_square 
            FROM properties 
            WHERE station IN ({})
        '''.format(','.join(['?']*len(unique_raw_names)))
        main_cursor.execute(query, unique_raw_names)
        rows = main_cursor.fetchall()
        main_conn.close()

        # Group costs by station
        from collections import defaultdict
        rent_data = defaultdict(list)
        for station, cost in rows:
            if cost is not None:
                rent_data[station].append(float(cost))

    # Collect stations with rent data and calculate statistics
    stations_with_rent = []
    for station in overlap_stations:
        raw_name = station.split(" Station")[0].strip()
        costs = rent_data.get(raw_name, [])

        stats = {'station': station}
        if costs:
            sorted_costs = sorted(costs)
            n = len(sorted_costs)

            # Calculate median
            if n % 2 == 1:
                median = sorted_costs[n//2]
            else:
                median = (sorted_costs[(n//2)-1] + sorted_costs[n//2])/2

            # Calculate quartiles
            q1 = sorted_costs[int(n*0.25)]
            q3 = sorted_costs[int(n*0.75)]

            stats.update({
                'median': median,
                'q1': q1,
                'q3': q3,
                'iqr': q3 - q1,
                'has_data': True
            })
        else:
            stats.update({
                'median': float('inf'),  # Push stations with no data to end
                'has_data': False
            })

        stations_with_rent.append(stats)

    # Sort by median ascending, then alphabetically
    stations_with_rent.sort(key=lambda x: (x['median'], x['station']))

    # Format output
    recommended_stations = []

    def get_farthest_station(center_address, stations):
        """Find the station with the maximum transit duration from the center."""
        max_duration = 0
        farthest_station = center_address
        cache_conn = sqlite3.connect('transit_cache.db')
        cache_cursor = cache_conn.cursor()
        for station in stations:
            station_name = station[0]
            # Retrieve transit duration from cache
            cache_cursor.execute('''
                SELECT duration FROM transit_cache 
                WHERE origin = ? AND destination = ?
            ''', (center_address, station_name))
            result = cache_cursor.fetchone()
            if result and result[0] is not None:
                duration = result[0]
                if duration > max_duration:
                    max_duration = duration
                    farthest_station = station_name
        cache_conn.close()
        return farthest_station

    # Get farthest stations for edges
    company_edge = get_farthest_station(company_formatted, company_stations)
    hangout_edge = get_farthest_station(hangout_formatted, hangout_stations)

    # Create CirclePlotters
    plotter1 = op.CirclePlotter(color="blue", opacity=0.6, center=company_formatted, edge=company_edge)
    plotter2 = op.CirclePlotter(color="pink", opacity=0.6, center=hangout_formatted, edge=hangout_edge)

    # Generate map with circles and overlap visualization
    try:
        # Initialize the map
        m = folium.Map(location=[company_coords['latitude'], company_coords['longitude']], zoom_start=12)
        
        # Add commute circles and overlap
        m = plotter1.plot(m)
        m = plotter2.plot(m)
        m = op.calculate_overlap(plotter1, plotter2, m)
        
        # ~~~~~ KEEP THIS MARKER CODE ~~~~~ (inside the try block)
        # Add markers for recommended stations with rent data
        for stats in stations_with_rent:
            station = stats['station']
            coords = op.CirclePlotter().get_location_coordinates(station)
            if coords and not isinstance(coords, str):
                # Prepare hover tooltip content
                if stats['has_data']:
                    tooltip_content = f"""
                        <div style='font-size: 14px;'>
                            <strong>{html.escape(station)}</strong><br>
                            Median Rent: ¥{stats['median']:.2f}/m²<br>
                            IQR: ¥{stats['iqr']:.2f} (Q1: ¥{stats['q1']:.2f}, Q3: ¥{stats['q3']:.2f})
                        </div>
                    """
                else:
                    tooltip_content = f"<div style='font-size: 14px;'>{html.escape(station)}<br>No rent data available</div>"
                
                folium.CircleMarker(
                    location=[coords['latitude'], coords['longitude']],
                    radius=6,
                    color='#FFA500',
                    weight=1,
                    fill=True,
                    fill_color='#FFA500',
                    fill_opacity=0.7,
                    tooltip=folium.Tooltip(tooltip_content, sticky=True),
                    zoom_on_click=False
                ).add_to(m)
        
        # Convert map to HTML for output
        map_html = f"<iframe srcdoc='{html.escape(m._repr_html_())}' style='width:100%;height:600px;border:none'></iframe>"
        recommended_text = "\n".join([s['station'] for s in stations_with_rent]) if stations_with_rent else "No overlapping stations found."
        
        return map_html, recommended_text
        
    except Exception as e:
        print(f"Error generating map: {str(e)}")
        # Fallback map with error message
        map_html = "<div style='color:red'>Error generating map. Showing default location.</div>"
        fallback_map = folium.Map(location=[35.6895, 139.6917], zoom_start=10)._repr_html_()
        map_html += f"<iframe srcdoc='{html.escape(fallback_map)}' style='width:100%;height:600px;border:none'></iframe>"
        return map_html, "Error: Could not generate station list."

def create_interface():
    stations = all_stations()
    prefectures = get_prefectures()  # Get prefecture options
    
    interface = gr.Interface(
        fn=process_commute_circles,
        inputs=[
            gr.Dropdown(choices=stations, label="Company/University Station"),
            gr.Dropdown(choices=stations, label="(Optional)Hangout/Part-time Job Station"),
            gr.Number(label="Max commute time to company (minutes)", value=30),
            gr.Number(label="Max commute time to 2nd most frequent visited station(minutes)", value=30),
            gr.Dropdown(choices=prefectures, 
                        label="(Speed Optimization) Search only these prefectures",
                        multiselect=True)  # New dropdown
        ],
        outputs=[
            gr.HTML(label="Map Visualization"),
            gr.Textbox(label="Recommended Stations by CP", lines=10)
        ],
        title="Where SHOULD you live?",
        description="Find the perfect area to live based on your commute patterns. based on commute/happnies index relashion and Housing burden rate. usually, you should aim sub 20% BHR and sub 30min commute time",
        examples=[
            ["Shibuya", "Akihabara", 30, 30, ["Tokyo"]],  # Updated example
            ["Shinjuku", "Hachiouji", 40, 35, ["Tokyo", "Chiba"]]
        ]
    )
    return interface



if __name__ == "__main__":
    gt.create_cache_db()  # Initialize cache database
    interface = create_interface()
    interface.launch(share=True)