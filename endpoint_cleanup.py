import os
import requests
from datetime import datetime, timedelta
import logging
import argparse
import json
import uuid

def setup_argparse():
    parser = argparse.ArgumentParser(description='Clean up disconnected Trend Micro endpoints.')
    parser.add_argument('--api-key', help='Trend Micro Vision One API key (optional if set in environment)')
    parser.add_argument('--days', type=int, default=7, help='Number of days to look back for disconnected endpoints (default: 7)')
    return parser

def setup_logging():
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Create a timestamp for the log file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = f'logs/endpoint_cleanup_{timestamp}.log'
    
    # Configure file handler only (no StreamHandler)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file)  # Only log to file
        ]
    )
    
    return log_file

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

def get_disconnected_agents():
    try:
        # Remove the PARAMS filter since we'll handle filtering in our code
        response = requests.get(API_URL, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        return data.get("items", [])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        return []

def confirm_removal(agents, agent_guids):
    """Ask for confirmation before removing agents."""
    print("\n⚠️  WARNING: You are about to remove the following agents:")
    for agent, guid in zip(agents, agent_guids):
        print(f"- {agent[0]} (Last seen: {agent[1]}) [GUID: {guid}]")
    
    print(f"\nTotal agents to remove: {len(agents)}")
    confirmation = input("\n⚠️  Are you sure you want to remove these agents? (yes/no): ").lower()
    return confirmation == 'yes'

def is_valid_uuid(val):
    """Validate UUID format"""
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

def remove_endpoints(api_key, endpoint_ids):
    """Remove specified endpoints with error handling."""
    url = "https://api.xdr.trendmicro.com/v3.0/endpointSecurity/endpoints/delete"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Validate GUIDs first
    valid_guids = [guid for guid in endpoint_ids if is_valid_uuid(guid)]
    if len(valid_guids) != len(endpoint_ids):
        invalid_count = len(endpoint_ids) - len(valid_guids)
        print(f"⚠️  Warning: {invalid_count} invalid GUIDs were removed from the request")
        logging.warning(f"{invalid_count} invalid GUIDs were removed from the request")
    
    # Split into chunks of 100 to avoid API limits
    chunk_size = 100
    for i in range(0, len(valid_guids), chunk_size):
        chunk = valid_guids[i:i + chunk_size]
        payload = [{"agentGuid": str(guid)} for guid in chunk]
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            
            # Log the request details (only to file)
            logging.info(f"Request URL: {url}")
            logging.info(f"Payload: {json.dumps(payload, indent=2)}")
            
            # If there's an error, try to get detailed error message
            if not response.ok:
                try:
                    error_json = response.json()
                    if 'error' in error_json:
                        error = error_json['error']
                        error_msg = (f"Error removing agents {i} to {i+len(chunk)}\n"
                                   f"Status code: {response.status_code}\n"
                                   f"Error code: {error.get('code')}\n"
                                   f"Message: {error.get('message')}\n"
                                   f"Inner error: {error.get('innererror', {}).get('message', 'None')}\n"
                                   f"Trace ID: {error.get('innererror', {}).get('code', 'None')}")
                    else:
                        error_msg = (f"Error removing agents {i} to {i+len(chunk)}\n"
                                   f"Status code: {response.status_code}\n"
                                   f"Error details: {error_json}")
                except ValueError:
                    error_msg = (f"Error removing agents {i} to {i+len(chunk)}\n"
                                f"Status code: {response.status_code}\n"
                                f"Error details: {response.text or 'No error details available'}")
                
                logging.error(error_msg)
                print(f"❌ {error_msg}")
                return False
            
            print(f"✅ Successfully removed {len(chunk)} agents")
            logging.info(f"Successfully removed {len(chunk)} agents")
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            logging.error(error_msg)
            print(f"❌ {error_msg}")
            return False
    return True

def main():
    # Setup argument parser
    parser = setup_argparse()
    args = parser.parse_args()
    
    # Setup logging
    log_file = setup_logging()
    logging.info("Starting endpoint cleanup process")
    
    # Try to get API key from environment variable first, then argument
    api_key = os.environ.get('TREND_MICRO_API_KEY')
    if not api_key and args.api_key:
        api_key = args.api_key
    
    if not api_key:
        print("Error: No API key provided. Set TREND_MICRO_API_KEY environment variable or use --api-key")
        return
    
    # Calculate the cutoff date
    cutoff_date = datetime.now() - timedelta(days=args.days)
    logging.info(f"Looking for endpoints disconnected before: {cutoff_date.strftime('%Y-%m-%d')}")
    
    # Get all agents (not just disconnected)
    agents = get_disconnected_agents()
    
    # Filter agents
    eligible_agents = []
    filtered_agents = []
    agent_guids = []  # New list to store GUIDs
    
    # Process and log all agents (only to file)
    for agent in agents:
        endpoint_name = agent.get('endpointName', '')
        edr_sensor = agent.get('edrSensor', {})
        edr_status = edr_sensor.get('connectivity', 'Unknown')
        last_connected = edr_sensor.get('lastConnectedDateTime', 'Unknown')
        agent_guid = agent.get('agentGuid', '')  # Get the GUID
        
        if (endpoint_name.lower().startswith('ip-') and '-' in endpoint_name and 
            edr_status.lower() == 'disconnected' and 
            last_connected != 'Unknown'):
            try:
                last_connected_date = datetime.strptime(last_connected, "%Y-%m-%dT%H:%M:%S")
                if last_connected_date < cutoff_date:
                    eligible_agents.append(agent)
                    filtered_agents.append([endpoint_name, last_connected, edr_status])
                    agent_guids.append(agent_guid)  # Store the GUID
                else:
                    logging.info(f"Skipping recently disconnected endpoint: {endpoint_name} "
                               f"(Last Connected: {last_connected})")
            except ValueError:
                logging.info(f"Skipping endpoint with invalid date format: {endpoint_name} "
                           f"(Last Connected: {last_connected})")
        else:
            logging.info(f"Skipping ineligible endpoint: {endpoint_name} "
                        f"(Status: {edr_status}, Last Connected: {last_connected})")
    
    # Create summary message
    summary = "\n=== Endpoint Cleanup Summary ===\n"
    summary += f"Total agents processed: {len(agents)}\n"
    summary += f"Eligible for removal: {len(eligible_agents)}\n"
    summary += f"Not eligible: {len(agents) - len(eligible_agents)}\n"
    summary += f"Looking back {args.days} days (before {cutoff_date.strftime('%Y-%m-%d')})\n"
    summary += f"Detailed log file: {log_file}"
    
    # Log to file and print to terminal
    logging.info(summary)
    print(summary)
    
    if not eligible_agents:
        no_eligible_msg = "\n❌ No eligible agents found"
        logging.info(no_eligible_msg)
        print(no_eligible_msg)
        return
    
    # Confirmation and removal process
    print(f"\nProceeding with {len(agent_guids)} eligible agents...")
    if confirm_removal(filtered_agents, agent_guids):
        print("\nProceeding with removal...")
        if remove_endpoints(API_KEY, agent_guids):
            print("\n✅ Agent removal process completed successfully")
        else:
            print("\n❌ Some errors occurred during removal")
    else:
        print("\nRemoval cancelled")
        # Add section in log file for eligible agents that weren't removed
        logging.info("\n=== Eligible Agents Not Removed ===")
        for agent, guid in zip(filtered_agents, agent_guids):
            logging.info(f"Agent: {agent[0]}")
            logging.info(f"    GUID: {guid}")
            logging.info(f"    Last Connected: {agent[1]}")
            logging.info(f"    Status: {agent[2]}")
        logging.info(f"Total eligible agents not removed: {len(filtered_agents)}")

if __name__ == "__main__":
    main()
