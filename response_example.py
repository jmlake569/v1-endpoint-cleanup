import os
import requests
import logging
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Retrieve API key from environment variable
API_KEY = os.getenv("TREND_MICRO_API_KEY")
if not API_KEY:
    raise ValueError("TREND_MICRO_API_KEY environment variable is not set.")

# Set API endpoint and headers
API_URL = "https://api.xdr.trendmicro.com/v3.0/endpointSecurity/endpoints"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

def fetch_raw_data():
    try:
        response = requests.get(API_URL, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        logging.info("Successfully fetched raw data from the API.")
        return data
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching data: {e}")
        return None

def main():
    raw_data = fetch_raw_data()
    if raw_data:
        # Print the raw data
        print("Raw Data from API:")
        print(raw_data)
        
        # Save the raw data to a JSON file
        with open('raw_data.json', 'w') as json_file:
            json.dump(raw_data, json_file, indent=4)
        logging.info("Raw data has been dumped into raw_data.json.")

if __name__ == "__main__":
    main()