# Trend Micro Vision One Endpoint Cleanup

A Python script to identify and remove disconnected endpoints from Trend Micro Vision One that match specific criteria.

## Description

This script processes Trend Micro Vision One endpoints and identifies candidates for removal based on the following criteria:
- Hostname starts with "ec2-"
- EDR sensor status is "disconnected"
- Has been disconnected longer than the specified number of days (argument)

## Prerequisites

- Python 3.8 or higher
- Trend Micro Vision One API key with the following permissions:
  - Endpoint Inventory:
    - View
    - Remove endpoints
- Required Python packages:
  ```bash
  pip install requests urllib3 logging
  ```

## Configuration

The script requires a Trend Micro Vision One API key, which can be provided in two ways:

1. Environment variable (Recommended):
  ```bash
  export TREND_MICRO_API_KEY='your-api-key-here'
  ```

2. Command line argument:
  ```bash
  python endpoint_cleanup.py --api-key your-api-key-here
  ```

## Usage

Run the script with optional arguments:
```bash
python endpoint_cleanup.py [--api-key API_KEY] [--days DAYS] [--dry-run]
```

Arguments:
- `--api-key`: Trend Micro Vision One API key (optional if set in environment)
- `--days`: Number of days to look back for disconnected endpoints (default: 7)
- `--dry-run`: Perform a dry run to see what would be removed without making any changes

Examples:
```bash
# Use default 7 days lookback
python endpoint_cleanup.py

# Look back 30 days
python endpoint_cleanup.py --days 30

# Perform a dry run with 14 days lookback
python endpoint_cleanup.py --days 14 --dry-run

# Specify API key and perform dry run
python endpoint_cleanup.py --api-key your-key-here --dry-run
```

The script will:
1. Process all endpoints
2. Log detailed information to a timestamped file in the `logs` directory
3. Display a summary in the terminal
4. In dry run mode:
   - Show eligible endpoints that would be removed
   - No actual changes are made
   - Provide detailed logging for review
5. In normal mode:
   - Show eligible endpoints for removal
   - Prompt for confirmation before removing any endpoints
   - Execute removal if confirmed

## Output

### Terminal Output
- Summary of processed endpoints
- Count of eligible and ineligible endpoints
- Location of detailed log file
- In dry run mode:
  - List of endpoints that would be removed
  - No confirmation prompt
- In normal mode:
  - Confirmation prompts with endpoint details
  - Removal status updates

### Log File
- Detailed information about each endpoint processed
- Reasons for ineligibility
- Complete operation history
- API request payloads and responses
- Summary information
- List of eligible endpoints (removed or not, depending on mode)

## Log Files

Log files are stored in the `logs` directory with the naming format:
```
logs/endpoint_cleanup_YYYYMMDD_HHMMSS.log
```

## Error Handling

The script includes error handling for:
- Missing API key
- API connection issues
- Invalid endpoint data
- Invalid UUID formats
- API response errors with detailed messages
- Request/response logging for debugging