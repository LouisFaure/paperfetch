# paperpetch

PaperFetch is an automated research paper discovery and analysis tool that searches for recent academic papers, processes them with AI for intelligent summarization and relevance scoring, and delivers the results via Slack.

## Features

- 🔍 **Multi-Source Paper Discovery**: Searches CrossRef API and optionally Nature/Springer databases for papers published in the last week
- 🤖 **AI-Powered Analysis**: Uses LLM to summarize papers and rate their relevance to your research interests
- 💬 **Slack Notifications**: Posts high-relevance papers (rating ≥7) to a Slack channel, one message per paper for easy reactions
- ⚡ **Concurrent Processing**: Efficiently processes multiple papers simultaneously
- 🛡️ **Smart Rate Limiting**: Configurable limits to prevent excessive API usage
- 🔄 **Retry Logic**: Robust error handling with automatic retries for API calls
- 🔎 **Flexible Query Syntax**: Supports both list-based and string-based queries with multi-term search

## Prerequisites

- Python 3.13 or higher
- [UV package manager](https://docs.astral.sh/uv/) (recommended) or pip
- Access to an OpenAI-compatible API (OpenAI, local LLM server, etc.)
- Slack workspace with an incoming webhook URL
- (Optional) Springer API key for Nature/Springer database access

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/LouisFaure/paperfetch.git
   cd paperfetch
   ```

2. **Install dependencies**:
   
   With UV (recommended):
   ```bash
   uv sync
   ```
   
   With pip:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

1. **Copy the example configuration**:
   ```bash
   cp config_example.toml config.toml
   ```

2. **Edit `config.toml`** with your settings:

```toml
# PaperFetch Configuration File

[search]
# The search query to use for finding papers
# Can be a list of terms or a single string (for backward compatibility)
# When using a list, terms are joined with spaces for CrossRef and with " AND " for Nature/Springer
query = ["single-cell", "tissue ecosystem"]
# Alternative single string format (deprecated but still supported):
# query = "single-cell tissue ecosystem"

# Optional: a short text describing the researcher's current interests.
# If provided, PaperFetch will include this text alongside the query when asking the LLM
# to rate relevance. Example: "causal inference, interpretability, healthcare"
researcher_interests = """
I am currently developing a VAE model for scRNASeq that enhances interpretability. 
I am interested in causal inference, health data, cancer research"""
# Maximum number of papers to process with LLM (set to 0 to disable LLM processing entirely)
max_papers_for_llm = 100
# Number of days to check for new papers (default is 7)
days_to_check = 7

[api]
# Email address for CrossRef API requests (required for polite usage)
mailto = "your.email@example.com"
# OpenAI API key or compatible API key
openai_api = "sk-your-api-key-here"
# API base URL (use OpenAI's URL or your local server)
openai_url = "https://api.openai.com/v1"
# Model name to use for processing
openai_model = "gpt-4o-mini"
# Number of attemps for LLM calls
max_attempts = 3
# Check or not SSL (use at your own risk!)
ssl_verify = true

# Nature/Springer API configuration (optional)
# Set enable_springer to true to also search Nature/Springer databases
enable_springer = false
springer_api_key = "your_springer_api_key_here"

[slack]
# Bot User OAuth Token (starts with xoxb-)
# Get this from your Slack App settings > OAuth & Permissions
bot_token = "xoxb-your-bot-token"
# Channel ID to post messages to (e.g. C012345678)
# You can find this in the channel details in Slack
channel_id = "C012345678"
# Minimum interest rating to post (papers with rating >= this will be posted)
min_rating = 7
```

### Slack Bot Setup

To set up Slack notifications:
1. Go to [Slack API Apps](https://api.slack.com/apps) and create a new app
2. go to **OAuth & Permissions** in the sidebar
3. Add the following **Bot Token Scopes**:
   - `chat:write` (to post messages)
   - `chat:write.public` (to post to any public channel without joining)
   - `links:read` (optional, for link unfurling)
4. Install the App to your Workspace
5. Copy the **Bot User OAuth Token** (starts with `xoxb-`) to `config.toml`
6. Get the **Channel ID** (right-click channel > Copy Link, the ID is the last part e.g., `C012345678`) and add it to `config.toml`

### Nature/Springer API Setup (Optional)

To enable searching Nature and Springer journals:
1. Register for a Springer API key at [Springer Developer Portal](https://dev.springernature.com/)
2. Add your API key to `config.toml` under `[api]` section:
   ```toml
   enable_springer = true
   springer_api_key = "your_springer_api_key_here"
   ```
3. When enabled, PaperFetch will search both CrossRef and Nature/Springer databases and merge the results

## Usage

### Basic Usage

Run with the query from your config file:
```bash
uv run main.py
```

Or with UV script syntax:
```bash
uv run --script main.py
```


### Testing & Dry Run

Preview what would be sent to Slack without actually sending any messages. This is useful for testing queries or settings.

**Run a dry run:**
```bash
uv run test_slack_message.py
```

**Use cached results:**
If you've already run a search (either via `main.py` or the test script), results are saved to `results.pkl`. You can re-run the rating/filtering step on these cached papers without re-fetching from APIs or using LLM credits:
```bash
uv run test_slack_message.py --cached
```

**Run a connection test:**
Verify your Slack credentials by posting a temporary test message (auto-deleted after 1 minute):
```bash
uv run test_slack_post_delete.py
```

### What Happens

1. **Paper Discovery**: 
   - Searches CrossRef for papers published in the last 7 days matching your query
   - If enabled, also searches Nature/Springer databases
   - Merges results from both sources (duplicates by title are handled)
2. **AI Analysis**: For each paper (up to your configured limit):
   - Generates 3-5 key bullet points summarizing the abstract
   - Rates relevance on a scale of 0-10. If you provide `search.researcher_interests` in `config.toml`, the LLM will rate relevance using both the query and your described researcher interests (preferred when present).
3. **Email Report**: Sends an HTML email with:
   - Papers sorted by relevance rating
   - Clickable titles linking to the papers
   - Color-coded interest ratings
   - Bullet-point summaries
4. **Backup**: Saves results to `results.pkl` for debugging

### Rate Limiting

If more papers are found than your `max_papers_for_llm` setting, the tool will:
- Skip AI processing to avoid excessive API costs
- Send an email with just the paper titles and links
- Suggest adjusting your search scope or increasing the limit

## Output

### Slack Notifications (Rating ≥7)
- One message per high-relevance paper
- Clickable title linking to the paper
- Interest rating with emoji
- Key points summary
- Collapsible abstract in code block
- React with 👀 to show interest

### Rate-Limited Notification
- Summary message with paper count
- List of paper titles (first 20) with links
- Explanation of why AI processing was skipped

## File Structure

```
PaperFetch/
├── main.py              # Main script and orchestration
├── crossref.py          # CrossRef API interaction
├── nature.py            # Nature/Springer API interaction
├── llm.py              # AI processing and summarization
├── slack.py            # Slack webhook notifications
├── config_example.toml  # Configuration template
├── config.toml         # Your configuration (not in git)
├── pyproject.toml      # Project dependencies
└── README.md           # This file
```

## Contribution

This project was entirely vibe coded using Claude
