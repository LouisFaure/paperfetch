# paperpetch

PaperFetch is an automated research paper discovery and analysis tool that searches for recent academic papers, processes them with AI for intelligent summarization and relevance scoring, and delivers the results via email.

## Features

- 🔍 **Multi-Source Paper Discovery**: Searches CrossRef API and optionally Nature/Springer databases for papers published in the last week
- 🤖 **AI-Powered Analysis**: Uses LLM to summarize papers and rate their relevance to your research interests
- 📧 **Email Delivery**: Sends beautifully formatted HTML email reports with paper summaries and ratings
- ⚡ **Concurrent Processing**: Efficiently processes multiple papers simultaneously
- 🛡️ **Smart Rate Limiting**: Configurable limits to prevent excessive API usage
- 🔄 **Retry Logic**: Robust error handling with automatic retries for API calls
- 🔎 **Flexible Query Syntax**: Supports both list-based and string-based queries with multi-term search

## Prerequisites

- Python 3.13 or higher
- [UV package manager](https://docs.astral.sh/uv/) (recommended) or pip
- Access to an OpenAI-compatible API (OpenAI, local LLM server, etc.)
- Email account with SMTP access (Gmail, etc.)
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

[email]
# Email configuration for sending results
smtp_server = "smtp.gmail.com"
smtp_port = 587
sender_email = "your.email@gmail.com"
# For Gmail, use an App Password instead of your regular password
sender_password = "your_app_password_here"
recipient_email = "recipient@example.com"
subject_prefix = "PaperFetch Results"
```

### Gmail Setup

For Gmail users:
1. Enable 2-factor authentication
2. Generate an App Password: Google Account → Security → 2-Step Verification → App passwords
3. Use the App Password in the `sender_password` field

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

### Custom Query

Override the config query with command-line arguments:

**Single search term:**
```bash
uv run main.py "quantum computing"
```

**Multiple search terms:**
```bash
uv run main.py "single-cell" "tissue ecosystem"
```

When using multiple command-line arguments, each term is treated separately and joined appropriately for each API:
- **CrossRef**: Terms joined with spaces (e.g., `single-cell tissue ecosystem`)
- **Nature/Springer**: Terms joined with AND logic (e.g., `"single-cell" AND "tissue ecosystem"`)

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

### Successful Processing Email
- Papers sorted by AI-generated relevance scores
- Color-coded ratings (red: 0-3, orange: 4-6, green: 7-10)
- Bullet-point summaries of key findings
- Direct links to papers via DOI

### Rate-Limited Email
- List of paper titles with links
- Explanation of why AI processing was skipped
- Suggestions for configuration adjustments

## File Structure

```
PaperFetch/
├── main.py              # Main script and orchestration
├── crossref.py          # CrossRef API interaction
├── nature.py            # Nature/Springer API interaction
├── llm.py              # AI processing and summarization
├── mail.py             # Email formatting and sending
├── config_example.toml  # Configuration template
├── config.toml         # Your configuration (not in git)
├── pyproject.toml      # Project dependencies
└── README.md           # This file
```

## Contribution

This project was entirely vibe coded using Claude
