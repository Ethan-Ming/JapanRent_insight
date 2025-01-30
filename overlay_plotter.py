# overlay_plotter.py updated code
import folium
import gradio as gr
from geopy.exc import GeocoderTimedOut
from geopy.geocoders import Nominatim
import html
import csv
import os
import time
from math import radians, sin, cos, sqrt, atan2, degrees, asin

class CirclePlotter:
    """Create a map with circle overlays and intersection highlighting."""
    _geocoding_cache = {}
    _last_request_time = 0
    _cache_file = "geocoding_cache.csv"

    def __init__(self, color="red", opacity=0.6, center="", edge=""):
        # Load cache on first instance
        if not CirclePlotter._geocoding_cache:
            self._load_cache()
        # Rest of initialization remains the same
        self.color = color
        self.opacity = opacity
        # Handle center
        if center:
            self.center = self.get_location_coordinates(center)
            if self.center is None:
                self.center = {"latitude": 35.6762, "longitude": 139.6503}  # Default to Tokyo
        else:
            self.center = {"latitude": 35.6762, "longitude": 139.6503}
        # Handle edge
        if edge:
            self.edge = self.get_location_coordinates(edge)
            if self.edge is None:
                self.edge = {"latitude": 35.6762, "longitude": 139.6603}  # Default edge
        else:
            self.edge = {"latitude": 35.6762, "longitude": 139.6603}
        self.radius = None

    @classmethod
    def _load_cache(cls):
        try:
            with open(cls._cache_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cls._geocoding_cache[row["address"]] = {
                        "latitude": float(row["latitude"]),
                        "longitude": float(row["longitude"])
                    }
        except FileNotFoundError:
            pass

    @classmethod
    def _save_to_cache(cls, address, lat, lon):
        cls._geocoding_cache[address] = {"latitude": lat, "longitude": lon}
        file_exists = os.path.isfile(cls._cache_file)
        with open(cls._cache_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["address", "latitude", "longitude"])
            writer.writerow([address, lat, lon])

    def get_location_coordinates(self, address):
        # Check cache first
        if address in self._geocoding_cache:
            return self._geocoding_cache[address]
        
        max_retries = 3
        retry_delay = 2  # seconds between retries
        
        for attempt in range(max_retries):
            # Rate limit: 1 request per second
            elapsed = time.time() - self._last_request_time
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            
            try:
                geolocator = Nominatim(
                    user_agent="my_geocoding_app (contact@yourdomain.com)",  # Replace with valid email
                    timeout=10  # Increased timeout
                )
                location = geolocator.geocode(address)
                self._last_request_time = time.time()
                
                if location:
                    coords = {
                        "latitude": location.latitude,
                        "longitude": location.longitude
                    }
                    self._save_to_cache(address, coords["latitude"], coords["longitude"])
                    return coords
                return None
            except GeocoderTimedOut:
                if attempt < max_retries - 1:
                    print(f"Timeout geocoding: {address} (retry {attempt+1}/{max_retries})")
                    time.sleep(retry_delay)
                    continue
                else:
                    print(f"Timeout geocoding: {address} after {max_retries} retries")
                    return None
            except Exception as e:
                print(f"Geocoding error: {str(e)}")
                return None
        return None

    # Rest of the class remains unchanged (get_distance, plot, etc.)

    def get_distance(self, coord1, coord2):
        """Calculate distance between two coordinates using Haversine formula."""
        lon1, lat1 = map(float, coord1.split(','))
        lon2, lat2 = map(float, coord2.split(','))
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        return 6371000 * 2 * atan2(sqrt(a), sqrt(1-a))

    def get_bearing(self, coord1, coord2):
        """Calculate initial bearing between two coordinates."""
        lon1, lat1 = map(float, coord1.split(','))
        lon2, lat2 = map(float, coord2.split(','))
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlon = lon2 - lon1
        x = sin(dlon) * cos(lat2)
        y = cos(lat1)*sin(lat2) - sin(lat1)*cos(lat2)*cos(dlon)
        return degrees(atan2(x, y))

    def get_destination_point(self, coord, bearing, distance):
        """Calculate destination point from given coordinate, bearing, and distance."""
        lon, lat = map(float, coord.split(','))
        lat, lon = radians(lat), radians(lon)
        bearing = radians(bearing)
        angular_dist = distance / 6371000
        
        new_lat = asin(sin(lat)*cos(angular_dist) + 
                      cos(lat)*sin(angular_dist)*cos(bearing))
        new_lon = lon + atan2(sin(bearing)*sin(angular_dist)*cos(lat),
                            cos(angular_dist)-sin(lat)*sin(new_lat))
        return [degrees(new_lat), degrees(new_lon)]

    def plot(self, m=None):
        """Create or update map with circle overlay."""
        if m is None:
            m = folium.Map(location=[self.center['latitude'], self.center['longitude']], zoom_start=14)
        
        coord1 = f"{self.center['longitude']},{self.center['latitude']}"
        coord2 = f"{self.edge['longitude']},{self.edge['latitude']}"
        self.radius = self.get_distance(coord1, coord2) + 50
        
        folium.Circle(
            location=[self.center['latitude'], self.center['longitude']],
            radius=self.radius,
            color=self.color,
            fill=True,
            fillOpacity=self.opacity
        ).add_to(m)
        
        return m

def calculate_overlap(plotter1, plotter2, m):
    """Calculate and visualize overlapping region between two circles."""
    try:
        c1 = f"{plotter1.center['longitude']},{plotter1.center['latitude']}"
        c2 = f"{plotter2.center['longitude']},{plotter2.center['latitude']}"
        d = plotter1.get_distance(c1, c2)
        r1, r2 = plotter1.radius, plotter2.radius
        
        if d >= r1 + r2 or d <= abs(r1 - r2):
            return m  # No overlap
        
        # Calculate intersection points
        a = (r1**2 - r2**2 + d**2) / (2*d)
        h = sqrt(r1**2 - a**2)
        if h <= 0:
            return m
        
        bearing = plotter1.get_bearing(c1, c2)
        phi1 = degrees(atan2(h, a))
        phi2 = degrees(atan2(-h, a))
        
        # Get intersection coordinates
        p1 = plotter1.get_destination_point(c1, (bearing + phi1) % 360, r1)
        p2 = plotter1.get_destination_point(c1, (bearing + phi2) % 360, r1)
        
        # Generate arc points for circle1 from p1 to p2
        arc_points = []
        steps = 20
        # Correcting the direction to p1 to p2
        start_angle = (bearing + phi1) % 360
        end_angle = (bearing + phi2) % 360
        angle_diff = (end_angle - start_angle) % 360
        if angle_diff > 180:
            angle_diff -= 360  # Take the shorter path
        for i in range(steps + 1):
            angle = (start_angle + angle_diff * i / steps) % 360
            arc_points.append(plotter1.get_destination_point(c1, angle, r1))
        
        # Generate arc points for circle2 from p2 to p1
        c2_str = c2
        p1_str = f"{p1[1]},{p1[0]}"  # lon, lat for p1
        p2_str = f"{p2[1]},{p2[0]}"  # lon, lat for p2
        
        bearing_p1 = plotter2.get_bearing(c2_str, p1_str)
        bearing_p2 = plotter2.get_bearing(c2_str, p2_str)
        angle_diff_c2 = (bearing_p1 - bearing_p2) % 360
        if angle_diff_c2 > 180:
            angle_diff_c2 -= 360  # Take the shorter path
        
        for i in range(steps + 1):
            angle = (bearing_p2 + angle_diff_c2 * i / steps) % 360
            point = plotter2.get_destination_point(c2_str, angle, r2)
            arc_points.append(point)
        
        # Add overlap polygon
        folium.Polygon(
            locations=arc_points,
            color='purple',
            fill=True,
            fill_color='purple',
            fill_opacity=0.6,
            weight=1
        ).add_to(m)
        
        return m
    except Exception as e:
        print(f"Overlap calculation error: {e}")
        return m

def plot_two_circles(color1, opacity1, center1, edge1, color2, opacity2, center2, edge2):
    """Plot two circles with overlap highlighting."""
    try:
        plotter1 = CirclePlotter(color1, opacity1, center1, edge1)
        plotter2 = CirclePlotter(color2, opacity2, center2, edge2)
        
        m = plotter1.plot()
        m = plotter2.plot(m)
        m = calculate_overlap(plotter1, plotter2, m)
        
        # Adjust map bounds
        all_points = [
            [plotter1.center['latitude'], plotter1.center['longitude']],
            [plotter1.edge['latitude'], plotter1.edge['longitude']],
            [plotter2.center['latitude'], plotter2.center['longitude']],
            [plotter2.edge['latitude'], plotter2.edge['longitude']]
        ]
        m.fit_bounds(all_points)
        
        return f"<iframe srcdoc='{html.escape(m._repr_html_())}' style='width:100%;height:600px;border:none'></iframe>"
    except Exception as e:
        return f"<div style='color:red'>Error: {html.escape(str(e))}</div>"

if __name__ == "__main__":
    iface = gr.Interface(
        fn=plot_two_circles,
        inputs=[
            gr.Dropdown(["red", "blue", "green", "yellow"], label="Circle 1 Color", value="red"),
            gr.Slider(0.1, 1.0, 0.6, label="Circle 1 Opacity"),
            gr.Textbox(label="Circle 1 Center", placeholder="Tokyo Tower"),
            gr.Textbox(label="Circle 1 Edge", placeholder="Roppongi Hills"),
            gr.Dropdown(["red", "blue", "green", "yellow"], label="Circle 2 Color", value="blue"),
            gr.Slider(0.1, 1.0, 0.6, label="Circle 2 Opacity"),
            gr.Textbox(label="Circle 2 Center", placeholder="Shibuya Station"),
            gr.Textbox(label="Circle 2 Edge", placeholder="Yoyogi Park")
        ],
        outputs=gr.HTML(label="Map"),
        title="Dual Circle Plotter with Overlap Highlighting",
        description="Enter locations for two circles to display them with overlapping regions colored purple"
    )
    iface.launch()