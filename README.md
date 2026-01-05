# GA Multi MCP

A Model Context Protocol (MCP) server for querying Google Analytics 4 data across multiple properties. Designed for use with LLM agents and the Programmatic Tool Calling (PTC) framework.

## Features

- **Multi-Property Support**: Query analytics across multiple GA4 properties in one call
- **Fuzzy Name Matching**: Reference properties by name or partial match, not just IDs
- **Natural Language Dates**: Use "yesterday", "7daysAgo", "last week" instead of dates
- **Property Discovery**: Auto-discover all accessible GA4 properties
- **Real-time Data**: Query live traffic data (last 30 minutes)
- **Intelligent Caching**: Minimize API calls with configurable TTL caching
- **LLM-Optimized**: Structured outputs designed for AI agent consumption

## Quick Start

**New to this?** See the step-by-step [Getting Started Guide](GETTING_STARTED.md).

## Installation

### Using uv (Recommended)

[uv](https://docs.astral.sh/uv/) is the fastest way to install and run:

```bash
# Install from GitHub
uv tool install git+https://github.com/heygoodgame/ga-multi-mcp.git

# Run after installing
ga-multi-mcp
```

### From Source

```bash
git clone https://github.com/heygoodgame/ga-multi-mcp.git
cd ga-multi-mcp

# Using uv (recommended)
uv sync
uv run ga-multi-mcp

# Or using pip
pip install -e .
```

## Google Cloud Setup

1. **Create a Service Account**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing
   - Navigate to "IAM & Admin" > "Service Accounts"
   - Create a service account with a descriptive name

2. **Enable APIs**
   - Enable "Google Analytics Data API"
   - Enable "Google Analytics Admin API"

3. **Download Credentials**
   - Create a JSON key for the service account
   - Save the file securely (e.g., `~/.config/ga-service-account.json`)

4. **Grant Access in GA4**
   - In Google Analytics, go to Admin > Property Access Management
   - Add the service account email with "Viewer" role
   - Repeat for each property you want to query

## Configuration

Set the following environment variables:

```bash
# Required: Path to your service account JSON
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"

# Optional: Custom settings
export GA_CACHE_TTL=300                    # Cache TTL in seconds (default: 300)
export GA_PROPERTY_CACHE_TTL=3600          # Property list cache TTL (default: 3600)
export GA_FUZZY_THRESHOLD=0.6              # Fuzzy match threshold 0.0-1.0 (default: 0.6)
export GA_DEFAULT_LIMIT=1000               # Default query row limit (default: 1000)
export GA_PROPERTY_ALIASES='{"myblog": ["blog", "personal site"]}'  # Custom aliases (JSON)
```

## Usage

### Running the Server

```bash
# Direct execution
python -m ga_multi_mcp

# Or using the CLI
ga-multi-mcp
```

### MCP Client Configuration

Add to your MCP client configuration (e.g., Claude Desktop, Cursor):

```json
{
  "mcpServers": {
    "ga-multi": {
      "command": "ga-multi-mcp",
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/service-account.json"
      }
    }
  }
}
```

> **Note:** This assumes you've installed with `uv tool install`. If running from source, use `"command": "uv"` with `"args": ["run", "ga-multi-mcp"]` and set the working directory.

### PTC Framework Configuration

For use with [open-ptc-agent](https://github.com/Chen-zexi/open-ptc-agent):

```yaml
# config.yaml
mcp_servers:
  - name: ga-multi
    enabled: true
    description: Google Analytics 4 multi-property querying
    instruction: |
      Use list_properties first to discover available properties.
      Supports fuzzy matching on property names.
    transport: stdio
    command: python
    args: ["-m", "ga_multi_mcp"]
    env:
      GOOGLE_APPLICATION_CREDENTIALS: ${GA_SERVICE_ACCOUNT_PATH}
```

## Available Tools

### `list_properties`

List all accessible GA4 properties.

```python
# Example output
{
  "properties": [
    {"id": "123456789", "name": "myblog", "display_name": "My Blog"},
    {"id": "987654321", "name": "myapp", "display_name": "My App"}
  ],
  "count": 2
}
```

### `search_properties`

Search for properties by name with fuzzy matching.

```python
# Input
search_properties(query="blog")

# Output
{
  "matches": [
    {"property_id": "123456789", "display_name": "My Blog", "confidence": 0.85}
  ],
  "best_match": {...}
}
```

### `query_analytics`

Query GA4 analytics for a single property.

```python
# Input
query_analytics(
    property="my blog",  # Fuzzy matched
    metrics=["activeUsers", "sessions"],
    start_date="7daysAgo",
    end_date="today",
    dimensions=["date", "country"]
)

# Output
{
  "property_id": "123456789",
  "property_name": "My Blog",
  "date_range": {"start_date": "2024-01-08", "end_date": "2024-01-15"},
  "rows": [
    {"date": "20240115", "country": "United States", "activeUsers": 150, "sessions": 200},
    ...
  ],
  "row_count": 42
}
```

### `query_multiple_properties`

Query metrics across multiple properties for comparison.

```python
# Input
query_multiple_properties(
    properties=["blog", "app", "store"],
    metrics=["activeUsers", "sessions"],
    start_date="last week",
    end_date="today"
)

# Output
{
  "results": [
    {"property_name": "My Blog", "data": [...]},
    {"property_name": "My App", "data": [...]},
    {"property_name": "My Store", "data": [...]}
  ],
  "summary": {
    "totals": {"activeUsers": 5000, "sessions": 8000}
  }
}
```

### `get_property_metadata`

Get available dimensions and metrics for a property.

```python
# Input
get_property_metadata(property="my blog")

# Output
{
  "dimensions": [
    {"api_name": "date", "ui_name": "Date"},
    {"api_name": "country", "ui_name": "Country"},
    ...
  ],
  "metrics": [
    {"api_name": "activeUsers", "ui_name": "Active users"},
    ...
  ],
  "custom_dimensions": [...],
  "custom_metrics": [...]
}
```

### `query_realtime`

Query real-time data (last 30 minutes).

```python
# Input
query_realtime(
    property="my blog",
    metrics=["activeUsers"],
    dimensions=["country"]
)

# Output
{
  "property_name": "My Blog",
  "lookback_minutes": 30,
  "rows": [
    {"country": "United States", "activeUsers": 25},
    {"country": "United Kingdom", "activeUsers": 10}
  ]
}
```

### `get_cache_status` / `clear_cache`

Manage the internal cache.

## Common Metrics & Dimensions

### Popular Metrics
- `activeUsers` - Users active in the period
- `sessions` - Total sessions
- `screenPageViews` - Page/screen views
- `eventCount` - Total events
- `bounceRate` - Bounce rate
- `averageSessionDuration` - Avg session length
- `newUsers` - New users

### Popular Dimensions
- `date` - Date (YYYYMMDD)
- `country` - Country name
- `city` - City name
- `deviceCategory` - desktop/mobile/tablet
- `browser` - Browser name
- `operatingSystem` - OS name
- `pagePath` - Page URL path
- `sessionSource` - Traffic source

## Date Formats

Supported date formats:
- ISO: `2024-01-15`
- US: `01/15/2024`
- Relative: `today`, `yesterday`
- Days ago: `7daysAgo`, `30daysago`
- Weeks ago: `1weekAgo`, `2weeksago`
- Months ago: `1monthAgo`, `3monthsago`
- Named: `last week`, `last month`, `this week`, `this month`, `ytd`

## Troubleshooting

### "Property not found"
- Use `list_properties` to see available properties
- Check service account has viewer access in GA4
- Try `search_properties` with partial name

### "Failed to initialize GA client"
- Verify `GOOGLE_APPLICATION_CREDENTIALS` path is correct
- Check service account JSON file exists and is valid
- Ensure APIs are enabled in Google Cloud Console

### Rate Limiting
- GA4 API has quotas (default: 100 requests/100 seconds)
- Use caching (enabled by default)
- Batch queries with `query_multiple_properties`

## License

MIT License - see [LICENSE](LICENSE) file.

## Contributing

Contributions welcome! Please open an issue or PR on GitHub.
