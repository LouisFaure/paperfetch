# paperpetch

PaperFetch is an automated research paper discovery and analysis tool that searches for recent academic papers, processes them with AI for intelligent summarization and relevance scoring, and delivers the results via email.

## Features

- 🔍 **Automated Paper Discovery**: Searches CrossRef API for papers published in the last week
- 🤖 **AI-Powered Analysis**: Uses LLM to summarize papers and rate their relevance to your research interests
- 📧 **Email Delivery**: Sends beautifully formatted HTML email reports with paper summaries and ratings
- ⚡ **Concurrent Processing**: Efficiently processes multiple papers simultaneously
- 🛡️ **Smart Rate Limiting**: Configurable limits to prevent excessive API usage
- 🔄 **Retry Logic**: Robust error handling with automatic retries for API calls

## Prerequisites

- Python 3.13 or higher
- [UV package manager](https://docs.astral.sh/uv/) (recommended) or pip
- Access to an OpenAI-compatible API (OpenAI, local LLM server, etc.)
- Email account with SMTP access (Gmail, etc.)

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
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
query = "machine learning neural networks"
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

### Configuration Details

#### Search Settings
- **`query`**: The search terms used to find papers on CrossRef
- **`max_papers_for_llm`**: Maximum number of papers to process with AI. Set to 0 to disable LLM processing entirely and just get paper lists

#### API Settings
- **`mailto`**: Your email address (required by CrossRef for rate limiting)
- **`openai_api`**: Your API key for the LLM service
- **`openai_url`**: Base URL for the API (supports OpenAI and compatible services)
- **`openai_model`**: Model name to use (e.g., `gpt-4o-mini`, `gpt-4`, or local model names)

#### Email Settings
- **`smtp_server`**: SMTP server address
- **`smtp_port`**: SMTP port (587 for TLS, 465 for SSL)
- **`sender_email`**: Email address to send from
- **`sender_password`**: Email password or app-specific password
- **`recipient_email`**: Email address to receive results
- **`subject_prefix`**: Prefix for email subjects

### Gmail Setup

For Gmail users:
1. Enable 2-factor authentication
2. Generate an App Password: Google Account → Security → 2-Step Verification → App passwords
3. Use the App Password in the `sender_password` field

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

Override the config query with a command-line argument:
```bash
uv run main.py "quantum computing algorithms"
```

### What Happens

1. **Paper Discovery**: Searches CrossRef for papers published in the last 7 days matching your query
2. **AI Analysis**: For each paper (up to your configured limit):
   - Generates 3-5 key bullet points summarizing the abstract
   - Rates relevance to your query on a scale of 0-10
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
├── llm.py              # AI processing and summarization
├── mail.py             # Email formatting and sending
├── config_example.toml  # Configuration template
├── config.toml         # Your configuration (not in git)
├── pyproject.toml      # Project dependencies
└── README.md           # This file
```

## Contribution

This project was entirely vibe coded using Claude