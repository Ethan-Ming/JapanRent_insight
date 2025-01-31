# Where SHOULD You Live? - Optimizing Commute time and personal life Circles 🏙️🚉

  A friendly interface to visualize optimal residential areas based on commute times to your workplace/university and frequent destinations. Uses realtime transit data and rent statistics to recommend locations balancing convenience and affordability.

![Screen Shot 2025-01-30 at 18 03 38](https://github.com/user-attachments/assets/03a409d0-5e62-4d2d-8347-45b93039636c)



## Features ✨

- **Cost Saving**: Immediately see where gives you best bang for the bucks !
- <img width="1262" alt="Screen Shot 2025-01-31 at 11 26 25" src="https://github.com/user-attachments/assets/ce292cab-863d-4d70-bb9a-449ae6d243be" />
- **Dual Commute Visualization**: Input two key locations (e.g., workplace + hangout spot) and max commute times.
- **Living Circles Map**: Interactive Folium map showing:
  - Commute range circles from both locations
  - Overlap zones (ideal living areas)
  - Key housing statistics of this stations
  - ![Screen Shot 2025-01-31 at 11 26 14 Large](https://github.com/user-attachments/assets/8d9cdd7e-0242-418d-bed5-d4932c5b7c2e)

- **Rent Statistics**: Median, quartiles, and IQR for rent prices in overlapping zones.
- **Caching System**: SQLite database caches transit times to speed up repeated queries.
- **Prefecture Filtering**: Narrow search to specific administrative regions for faster results.

## Live Demo 🌐
- **[Check out the live demo here](https://japanrentinsight-mrdqsz8n4rd8sti5ffouxz.streamlit.app/)**.(only has shibuya,akihabara,shinjuku,Hachioji for preview purposes, for acutaul usage, consider insatll locally)

## Installation ⚙️

### Prerequisites
- Python 3.9+
- Chrome browser (for Selenium)
- [ChromeDriver](https://chromedriver.chromium.org/) (match your Chrome version)

### Steps
1. Clone repository:
   ```bash
   git clone https://github.com/Ethan-Ming/JapanRent_insight.git
   cd JapanRent_insight
2. Install dependencies:
    ```bash
    pip install -r requirements.txt
3. Set up databases (optional):
     Place tokyo_rent.db in /Dataset (you can perpere this using this tool https://github.com/Ethan-Ming/TokyoRentingBirdview/blob/main/Run_this/rent_scapping.py )
     Initial DB will be created automatically


### Usage 🖱️
1. Launch the app:
    ```bash
    streamlit run streamlit_app.py

2. Interface guide:
    🏢 Company/University Station: Primary commute location

    🎮 Hangout Station: Secondary frequent destination

    ⏱️ Commute Times: Max acceptable travel time (minutes)

    🗾 Prefecture Filter: Select regions to reduce search scope

3. Interpret results:

    Purple overlap zones on map indicate optimal areas

    Station list shows rent cost statistics

    Larger IQR = greater rent price variability

### Limitations ⚠️

-  Scope: Currently 50% of the rent info are from Tokyo

- Data Dependencies:

    - rent info cutoff at 2025-01-25, for newer knowleage requires perpare a newer tokyo_rent.db

    - Google Maps API dosen't support japan, this code use scraping which may break with UI changes

    - Performance: Initial runs may take 15-30 minutes due to transit time scraping

    - Browser Requirements: ChromeDriver must match installed Chrome version

    - Time Sensitivity: Transit times use your current timezone in respect of JST time


### Data Sources 📚
- Transit Data: Google Maps (via Selenium scraping)

- Rent Prices: [Real Estate Japan](https://realestate.co.jp/en/rent).

- Station Coordinates: OpenStreetMap.org, Google Maps

- Mapping: Folium + OpenStreetMap tiles
