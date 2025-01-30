# streamlit_app.py
import streamlit as st
import get_transit_time as gt
from direction_API_demo import format_station_name, get_station_options
import overlay_plotter as op
import sqlite3
import folium
import webui as wbi
from streamlit_folium import st_folium
from collections import defaultdict

# Add at the top of your file:
st.set_page_config(
    page_title="Where SHOULD you live?",
    layout="wide",
    initial_sidebar_state="expanded"
)



# Initialize cache database once
if 'db_initialized' not in st.session_state:
    gt.create_cache_db()
    st.session_state.db_initialized = True


if 'map' not in st.session_state:
    st.session_state.map = None
    
@st.cache_data
def get_prefectures():
    conn = sqlite3.connect('Dataset/tokyo_rent.db')
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT prefecture FROM properties')
    prefectures = [row[0] for row in cursor.fetchall()]
    conn.close()
    return prefectures

def get_farthest_station(center_address, stations):
    """Find the station with maximum transit duration from center"""
    max_duration = 0
    farthest_station = center_address
    cache_conn = sqlite3.connect('transit_cache.db')
    cache_cursor = cache_conn.cursor()
    
    for station in stations:
        station_name = station[0]
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

@st.cache_data
def process_commute_circles(company_station, hangout_station, company_time, hangout_time, selected_prefectures):
    plotter1 = op.CirclePlotter()
    company_formatted = format_station_name(company_station)
    hangout_formatted = format_station_name(hangout_station)

    # Coordinate validation
    company_coords = op.CirclePlotter().get_location_coordinates(company_formatted)
    if not company_coords or isinstance(company_coords, str):
        st.error(f"Invalid coordinates for {company_formatted}")
        return None

    hangout_coords = op.CirclePlotter().get_location_coordinates(hangout_formatted)
    if not hangout_coords or isinstance(hangout_coords, str):
        st.error(f"Invalid coordinates for {hangout_formatted}")
        return None

    # Database query for filtered stations
    conn = sqlite3.connect('Dataset/tokyo_rent.db')
    cursor = conn.cursor()
    
    if selected_prefectures:
        query = f'SELECT DISTINCT station FROM properties WHERE prefecture IN ({",".join(["?"]*len(selected_prefectures))})'
        cursor.execute(query, selected_prefectures)
    else:
        cursor.execute('SELECT DISTINCT station FROM properties')
    
    all_station_list = [row[0] for row in cursor.fetchall()]
    conn.close()

    # Generate station pairs
    station_pairs_company = [(company_formatted, format_station_name(station)) for station in all_station_list]
    station_pairs_hangout = [(hangout_formatted, format_station_name(station)) for station in all_station_list]

    # Process transit times
    company_results = gt.parallel_processing(station_pairs_company, gt.get_transit_time, num_workers=10)
    hangout_results = gt.parallel_processing(station_pairs_hangout, gt.get_transit_time, num_workers=10)

    # Get edge stations
    try:
        cache_conn = sqlite3.connect('transit_cache.db')
        cache_cursor = cache_conn.cursor()
        
        # Get stations within time limits
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
        
        cache_conn.close()

        # Find overlapping stations
        company_set = set(station[0] for station in company_stations)
        hangout_set = set(station[0] for station in hangout_stations)
        overlap_stations = company_set.intersection(hangout_set)

        # Query rent data
        rent_data = defaultdict(list)
        if overlap_stations:
            raw_names = [s.split(" Station")[0].strip() for s in overlap_stations]
            conn = sqlite3.connect('Dataset/tokyo_rent.db')
            cursor = conn.cursor()
            query = 'SELECT station, cost_per_square FROM properties WHERE station IN ({})'.format(','.join(['?']*len(raw_names)))
            cursor.execute(query, raw_names)
            for station, cost in cursor.fetchall():
                if cost: rent_data[station].append(float(cost))
            conn.close()

    except Exception as e:
        st.error(f"Database error: {str(e)}")
        return None

    # Create map visualization
    try:
        m = folium.Map(location=[company_coords['latitude'], company_coords['longitude']], zoom_start=12)
        
        # Get farthest stations for edges
        company_edge = get_farthest_station(company_formatted, company_stations)
        hangout_edge = get_farthest_station(hangout_formatted, hangout_stations)

        # Add circles
        plotter1 = op.CirclePlotter(color="blue", opacity=0.6, center=company_formatted, edge=company_edge)
        plotter2 = op.CirclePlotter(color="pink", opacity=0.6, center=hangout_formatted, edge=hangout_edge)
        
        m = plotter1.plot(m)
        m = plotter2.plot(m)
        m = op.calculate_overlap(plotter1, plotter2, m)

        # Add markers for recommended stations
        for station in overlap_stations:
            coords = op.CirclePlotter().get_location_coordinates(station)
            if not coords or isinstance(coords, str): continue
            
            raw_name = station.split(" Station")[0].strip()
            costs = rent_data.get(raw_name, [])
            tooltip = f"<strong>{station}</strong>"
            
            if costs:
                median = sorted(costs)[len(costs)//2]
                tooltip += f"<br>Median Rent: ¥{median:.2f}/m²"
            else:
                tooltip += "<br>No rent data"
            
            folium.CircleMarker(
                location=[coords['latitude'], coords['longitude']],
                radius=6,
                color='orange',
                fill=True,
                fill_color='orange',
                tooltip=tooltip
            ).add_to(m)

        return m

    except Exception as e:
        st.error(f"Error generating map: {str(e)}")
        return folium.Map(location=[35.6895, 139.6917], zoom_start=10)
# Add this import at the top
from webui import process_commute_circles as webui_process_commute_circles

# Streamlit UI
st.title("Where SHOULD you live?")
st.markdown("Find the perfect area to live based on your commute patterns. based on commute/happnies index relashion and Housing burden rate. is recommanded to aim sub 20% BHR and sub 30min commute time")

with st.form("input_form"):
    stations = get_station_options()
    prefectures = get_prefectures()
    
    col1, col2 = st.columns(2)
    with col1:
        company_station = st.selectbox("Company/University Station", stations)
        company_time = st.number_input("Max commute to company (min)", 30)
    with col2:
        hangout_station = st.selectbox("(Optional) Hangout/Part-time Station", stations)
        hangout_time = st.number_input("Max commute to 2nd location (min)", 30)
    
    selected_prefectures = st.multiselect(
        "(Speed Optimization) Search prefectures",
        prefectures
    )
    
    submitted = st.form_submit_button("Find Living Areas")

# Modify the map rendering section:
if submitted:
    try:
        with st.spinner("Calculating commute circles... This may take a while, go to do some chores"):
            # Get the map and station data from webui.py
            map_html, recommended_text = webui_process_commute_circles(
                company_station, 
                hangout_station,
                company_time,
                hangout_time,
                selected_prefectures
            )
            
            # Parse the recommended_text into a list of stations
            stations_list = recommended_text.split("\n")
            
            # Query rent data for the stations
            rent_data = []
            conn = sqlite3.connect('Dataset/tokyo_rent.db')
            cursor = conn.cursor()
            for station in stations_list:
                raw_name = station.split(" Station")[0].strip()
                cursor.execute('''
                    SELECT cost_per_square 
                    FROM properties 
                    WHERE station = ?
                ''', (raw_name,))
                costs = [row[0] for row in cursor.fetchall() if row[0] is not None]
                
                if costs:
                    sorted_costs = sorted(costs)
                    n = len(sorted_costs)
                    median = sorted_costs[n//2] if n % 2 == 1 else (sorted_costs[(n//2)-1] + sorted_costs[n//2])/2
                    q1 = sorted_costs[int(n*0.25)]
                    q3 = sorted_costs[int(n*0.75)]
                    iqr = q3 - q1
                    rent_data.append({
                        'station': station,
                        'median': median,
                        'iqr': iqr
                    })
            conn.close()
            
            # Sort by median rent in ascending order
            rent_data.sort(key=lambda x: x['median'])
            
            # Display the map
            st.subheader("Recommended Living Areas")
            st.components.v1.html(map_html, height=600)
            
            # Display the table
            st.subheader("Reachable Stations by Rent Median")
            if rent_data:
                # Convert to DataFrame for better display
                import pandas as pd
                df = pd.DataFrame(rent_data)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No rent data available for the recommended stations.")
                
    except Exception as e:
        st.error(f"Error rendering map or table: {str(e)}")