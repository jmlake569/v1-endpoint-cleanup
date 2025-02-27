import os
import requests
from datetime import datetime, timedelta
import logging
import argparse
import json
import uuid
import time

def setup_argparse():
    parser = argparse.ArgumentParser(description='Clean up disconnected Trend Micro endpoints.')
    parser.add_argument('--api-key', help='Trend Micro Vision One API key (optional if set in environment)')
    parser.add_argument('--days', type=int, default=7, help='Number of days to look back for disconnected endpoints (default: 7)')
    parser.add_argument('--dry-run', action='store_true', help='Perform a dry run without actually removing endpoints')
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
    """Get all agents using pagination."""
    all_items = []
    next_link = API_URL
    
    try:
        while next_link:
            logging.info(f"Fetching data from: {next_link}")
            response = requests.get(next_link, headers=HEADERS)
            response.raise_for_status()
            data = response.json()
            
            # Add items from current page
            items = data.get("items", [])
            all_items.extend(items)
            
            # Check for next page using nextLink from JSON response
            next_link = data.get("nextLink")
            
            # Add a small delay between requests
            if next_link:
                time.sleep(1)
                
            logging.info(f"Retrieved {len(items)} items. Total so far: {len(all_items)}")
            
        logging.info(f"Completed fetching all {len(all_items)} items")
        return all_items
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Error fetching data: {str(e)}"
        logging.error(error_msg)
        print(f"❌ {error_msg}")
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
    """Remove specified endpoints with error handling and verification."""
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
    
    successful_removals = 0
    failed_removals = []
    
    # Split into chunks of 100 to avoid API limits
    chunk_size = 100
    for i in range(0, len(valid_guids), chunk_size):
        chunk = valid_guids[i:i + chunk_size]
        # Make sure we're sending the payload in the correct format
        payload = {"agentGuids": [{"agentGuid": str(guid)} for guid in chunk]}
        
        try:
            # Log the request details for debugging
            logging.info(f"Sending delete request for chunk {i//chunk_size + 1}")
            logging.info(f"Request URL: {url}")
            logging.info(f"Payload: {json.dumps(payload, indent=2)}")
            
            response = requests.post(url, headers=headers, json=payload)
            time.sleep(1)  # Add delay after deletion request
            
            if response.ok:
                # Verify the removal by checking if endpoints still exist
                verification_failures = []
                for guid in chunk:
                    verify_url = f"{API_URL}/{guid}"
                    try:
                        verify_response = requests.get(verify_url, headers=headers)
                        time.sleep(0.2)  # Add delay between verification requests
                        if verify_response.status_code == 404:
                            successful_removals += 1
                        else:
                            verification_failures.append(guid)
                            failed_removals.append(guid)
                    except requests.exceptions.RequestException as e:
                        logging.error(f"Verification failed for GUID {guid}: {str(e)}")
                        verification_failures.append(guid)
                        failed_removals.append(guid)
                
                if verification_failures:
                    logging.warning(f"Failed to verify removal of {len(verification_failures)} endpoints in chunk")
                    print(f"⚠️  Warning: {len(verification_failures)} endpoints may not have been removed properly")
            else:
                try:
                    error_json = response.json()
                    error = error_json.get('error', {})
                    error_msg = (f"Error removing agents {i} to {i+len(chunk)}\n"
                               f"Status code: {response.status_code}\n"
                               f"Error code: {error.get('code')}\n"
                               f"Message: {error.get('message')}\n"
                               f"Inner error: {error.get('innererror', {}).get('message', 'None')}\n"
                               f"Trace ID: {error.get('innererror', {}).get('code', 'None')}")
                except ValueError:
                    error_msg = (f"Error removing agents {i} to {i+len(chunk)}\n"
                               f"Status code: {response.status_code}\n"
                               f"Error details: {response.text or 'No error details available'}")
                
                logging.error(error_msg)
                print(f"❌ {error_msg}")
                failed_removals.extend(chunk)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Request failed: {str(e)}"
            logging.error(error_msg)
            print(f"❌ {error_msg}")
            failed_removals.extend(chunk)
    
    # Final summary
    if successful_removals > 0:
        print(f"✅ Successfully removed and verified {successful_removals} agents")
        logging.info(f"Successfully removed and verified {successful_removals} agents")
    
    if failed_removals:
        print(f"❌ Failed to remove {len(failed_removals)} agents")
        logging.error(f"Failed to remove the following GUIDs: {json.dumps(failed_removals, indent=2)}")
        return False
    
    return successful_removals > 0

def main():
    # Setup argument parser
    parser = setup_argparse()
    args = parser.parse_args()
    
    # Setup logging
    log_file = setup_logging()
    logging.info("Starting endpoint cleanup process")
    
    if args.dry_run:
        logging.info("DRY RUN MODE ENABLED - No endpoints will be removed")
        print("\n🔍 DRY RUN MODE - No endpoints will be removed")
    
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
    agent_guids = []
    
    # Process and log all agents (only to file)
    for agent in agents:
        endpoint_name = agent.get('endpointName', '')
        edr_sensor = agent.get('edrSensor', {})
        edr_status = edr_sensor.get('connectivity', 'Unknown')
        last_connected = edr_sensor.get('lastConnectedDateTime', 'Unknown')
        agent_guid = agent.get('agentGuid', '')  # Get the GUID
        
        if (edr_status.lower() == 'disconnected' and last_connected != 'Unknown'):
            try:
                last_connected_date = datetime.strptime(last_connected, "%Y-%m-%dT%H:%M:%S")
                if last_connected_date < cutoff_date:
                    agent_guid = agent.get('agentGuid', '')
                    logging.debug(f"Found eligible agent: {endpoint_name}")
                    logging.debug(f"GUID: {agent_guid}")
                    logging.debug(f"Last Connected: {last_connected}")
                    logging.debug(f"Status: {edr_status}")
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
    if args.dry_run:
        summary += "\nDRY RUN MODE - No endpoints will be removed"
    
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
    
    # In dry run mode, show what would be removed but don't ask for confirmation
    if args.dry_run:
        print("\n🔍 The following endpoints would be removed in a real run:")
        for agent, guid in zip(filtered_agents, agent_guids):
            print(f"- {agent[0]} (Last seen: {agent[1]}) [GUID: {guid}]")
        print("\n✨ Dry run completed. Use the command without --dry-run to perform actual removal.")
        
        # Add section in log file for eligible agents
        logging.info("\n=== Dry Run - Eligible Agents for Removal ===")
        for agent, guid in zip(filtered_agents, agent_guids):
            logging.info(f"Agent: {agent[0]}")
            logging.info(f"    GUID: {guid}")
            logging.info(f"    Last Connected: {agent[1]}")
            logging.info(f"    Status: {agent[2]}")
        logging.info(f"Total eligible agents for removal: {len(filtered_agents)}")
        return
    
    # Normal run - proceed with confirmation and removal
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
