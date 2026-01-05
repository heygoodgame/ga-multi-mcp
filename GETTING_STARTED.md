# Getting Started with GA Multi MCP

This guide walks you through setting up the GA Multi MCP server locally after cloning the repo.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A Google Cloud account
- Access to Google Analytics 4 properties

## Step 1: Install

**Option A: Install directly from GitHub (recommended)**
```bash
uv tool install git+https://github.com/heygoodgame/ga-multi-mcp.git
```

**Option B: Clone and install locally**
```bash
git clone https://github.com/heygoodgame/ga-multi-mcp.git
cd ga-multi-mcp
uv tool install -e .
```

Verify installation:
```bash
ga-multi-mcp --help
```

## Step 2: Create Google Service Account

### 2.1 Create a Google Cloud Project (if needed)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top
3. Click "New Project"
4. Name it (e.g., "GA MCP Server") and create

### 2.2 Enable Required APIs

1. Go to [APIs & Services > Library](https://console.cloud.google.com/apis/library)
2. Search for and enable:
   - **Google Analytics Data API**
   - **Google Analytics Admin API**

### 2.3 Create Service Account

1. Go to [IAM & Admin > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Click **"+ Create Service Account"**
3. Fill in:
   - Name: `ga-mcp-reader`
   - ID: `ga-mcp-reader` (auto-filled)
4. Click **"Create and Continue"**
5. Skip the optional permissions (click "Continue")
6. Click **"Done"**

### 2.4 Download Credentials JSON

1. Click on your new service account
2. Go to the **"Keys"** tab
3. Click **"Add Key" > "Create new key"**
4. Choose **JSON** format
5. Click **"Create"**
6. Save the downloaded file securely, e.g.:
   ```
   ~/.config/ga-service-account.json
   ```

### 2.5 Grant Access in Google Analytics

1. Go to [Google Analytics](https://analytics.google.com/)
2. For each property you want to query:
   - Click **Admin** (gear icon)
   - Under Property, click **"Property Access Management"**
   - Click **"+"** > **"Add users"**
   - Enter your service account email (e.g., `ga-mcp-reader@your-project.iam.gserviceaccount.com`)
   - Set role to **"Viewer"**
   - Click **"Add"**

## Step 3: Configure Your MCP Client

Choose **one** of the following options:

---

### Option A: Claude Code (.mcp.json)

Create a `.mcp.json` file in your project directory:

```json
{
  "mcpServers": {
    "ga-multi": {
      "command": "ga-multi-mcp",
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/path/to/your/ga-service-account.json"
      }
    }
  }
}
```

Replace `/path/to/your/ga-service-account.json` with the actual path (e.g., `~/.config/ga-service-account.json` won't work - use the full path like `/Users/yourname/.config/ga-service-account.json`).

Then restart Claude Code or start a new session.

---

### Option B: Claude Desktop

Edit your Claude Desktop config file:

**macOS:**
```bash
code ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

Add the server configuration:

```json
{
  "mcpServers": {
    "ga-multi": {
      "command": "ga-multi-mcp",
      "env": {
        "GOOGLE_APPLICATION_CREDENTIALS": "/full/path/to/ga-service-account.json"
      }
    }
  }
}
```

If the file already has other servers, add `ga-multi` to the existing `mcpServers` object.

Then restart Claude Desktop.

---

## Step 4: Test It

In Claude Code or Claude Desktop, try:

> "List my Google Analytics properties"

Or:

> "Show me the active users for the last 7 days across all my GA properties"

## Troubleshooting

### "Configuration error: Google credentials path required"

- Ensure `GOOGLE_APPLICATION_CREDENTIALS` is set in your config
- Use the **full absolute path** (not `~` or relative paths)

### "Credentials file not found"

- Verify the JSON file exists at the specified path
- Check file permissions

### "Failed to discover properties" / Empty property list

- Verify APIs are enabled in Google Cloud Console
- Check that the service account email has Viewer access in GA4
- Wait a few minutes after granting access (can take time to propagate)

### "Property not found"

- Use `list_properties` first to see available properties
- Try `search_properties` with a partial name
- Property names are fuzzy-matched, but need some similarity

## Next Steps

- See [README.md](README.md) for full tool documentation
- Check [.env.example](.env.example) for advanced configuration options
