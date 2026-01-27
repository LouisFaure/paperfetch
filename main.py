#!/usr/bin/env -S uv run --script
import yaml
import os
import sys
import re

# Load .env file if it exists
def load_dotenv(path=".env"):
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_dotenv()

# Check if config.yaml exists
if not os.path.exists("config.yaml"):
    print("Error: config.yaml not found!")
    sys.exit(1)

def resolve_env_vars(obj):
    """Recursively resolve ${ENV_VAR} placeholders in config values."""
    if isinstance(obj, str):
        pattern = r'\$\{([^}]+)\}'
        match = re.match(pattern, obj)
        if match:
            env_var = match.group(1)
            value = os.environ.get(env_var)
            if value is None:
                print(f"Warning: Environment variable {env_var} is not set")
                return obj
            return value
        return obj
    elif isinstance(obj, dict):
        return {k: resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [resolve_env_vars(item) for item in obj]
    return obj

# Load configuration from YAML file
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

# Resolve environment variable placeholders
config = resolve_env_vars(config)

# Set HF_HOME before importing transformers or any other library that uses it
hf_home = config.get("model", {}).get("hf_home", None)
if hf_home is not None:
    os.environ['HF_HOME'] = hf_home

import asyncio
import pickle
import re
import html
from datetime import datetime, timedelta
from slack import send_results_to_slack, send_no_llm_processing_slack, delete_bot_messages
from crossref import fetch_crossref_data
from nature import fetch_nature_data
from llm import process_papers_with_llm
import llm


def clean_text(text):
    """Remove HTML tags and unescape entities."""
    if not text:
        return ""
    # Unescape HTML entities first so we can catch tags like &lt;i&gt;
    clean = html.unescape(text)
    # Remove HTML tags (including those with newlines)
    clean = re.sub(r'<[^>]*>', '', clean, flags=re.DOTALL)
    # Normalize whitespace
    clean = ' '.join(clean.split())
    return clean.strip()



async def main():
    """Main async function to orchestrate the paper processing."""
    
    # Check for preview and cache flags
    preview_mode = False
    if "--preview" in sys.argv:
        preview_mode = True
        sys.argv.remove("--preview")
        print("Preview mode enabled: Slack messages will be printed to stdout instead of sent.")
    
    cache_mode = False
    if "--cache" in sys.argv:
        cache_mode = True
        sys.argv.remove("--cache")
        print("Cache mode enabled: Using pickled results if available.")

    # Check for cleanup flag
    cleanup_minutes = None
    if "--cleanup" in sys.argv:
        try:
            idx = sys.argv.index("--cleanup")
            if idx + 1 < len(sys.argv):
                val = sys.argv[idx + 1]
                # Check if the next argument is a number
                if val.isdigit():
                    cleanup_minutes = int(val)
                    # Remove both arguments
                    sys.argv.pop(idx + 1)
                    sys.argv.pop(idx)
                else:
                    print("Error: --cleanup requires a numeric argument (minutes)")
                    return
            else:
                 print("Error: --cleanup requires a number of minutes")
                 return
        except ValueError:
            print("Error parsing --cleanup argument")
            return

    if cleanup_minutes is not None:
        print(f"Cleaning up bot messages from the last {cleanup_minutes} minutes...")
        delete_bot_messages(config, cleanup_minutes)
        return

    # Calculate dates (needed for slack message)
    days_to_check = config.get("search", {}).get("days_to_check", 7)
    today = datetime.now().date()
    last_week = today - timedelta(days=days_to_check)
    
    query = config["search"]["query"]
    # If config query is a string, convert to list for consistency
    if isinstance(query, str):
        query = [query]
    
    print(f"Search query terms: {query}")
    
    res = None
    
    # Try to load from cache
    if cache_mode:
        if os.path.exists("results.pkl"):
            try:
                with open("results.pkl", "rb") as f:
                    res = pickle.load(f)
                print("Successfully loaded results from results.pkl")
            except Exception as e:
                print(f"Error loading cache: {e}")
                print("Falling back to normal execution...")
                cache_mode = False
        else:
            print("Cache file results.pkl not found. Running full pipeline.")
            cache_mode = False
            
    # If not using cache (or cache failed), run the pipeline
    if not cache_mode:
        # Fetch papers from CrossRef
        print("Fetching papers from CrossRef...")
        # We can update our dates from the fetch function to be precise with what was fetched
        papers_with_abstracts, today, last_week = fetch_crossref_data(query, config)
        print(f"Found {len(papers_with_abstracts)} papers from CrossRef")
        
        # Fetch papers from Nature/Springer if enabled
        if config.get('api', {}).get('enable_springer', False):
            print("Fetching papers from Nature/Springer...")
            try:
                nature_papers, _, _ = fetch_nature_data(query, config)
                print(f"Found {len(nature_papers)} papers from Nature/Springer")
                
                # Merge Nature papers with CrossRef papers
                # Papers with the same title will be overwritten (Nature takes precedence)
                papers_with_abstracts.update(nature_papers)
                print(f"Total papers after merging: {len(papers_with_abstracts)}")
            except Exception as e:
                print(f"Error fetching from Nature/Springer: {e}")
                print("Continuing with CrossRef results only...")
        else:
            print("Nature/Springer search disabled in config")

        # Post-process: Clean HTML from titles and abstracts
        print("Cleaning HTML tags from titles and abstracts...")
        cleaned_papers = {}
        for title, data in papers_with_abstracts.items():
            clean_title = clean_text(title)
            data['abstract'] = clean_text(data.get('abstract', ''))
            data['journal'] = clean_text(data.get('journal', ''))
            cleaned_papers[clean_title] = data
        papers_with_abstracts = cleaned_papers

        # Check if LLM processing should be performed based on paper count
        max_papers_for_llm = config.get('search', {}).get('max_papers_for_llm', 10)
        paper_count = len(papers_with_abstracts)
        
        print(f"Found {paper_count} papers with abstracts")
        print(f"Maximum papers for LLM processing: {max_papers_for_llm}")
        
        if paper_count > max_papers_for_llm:
            print(f"Skipping LLM processing: {paper_count} papers exceeds limit of {max_papers_for_llm}")
            # Send notification about skipped LLM processing
            send_no_llm_processing_slack(
                papers_with_abstracts, 
                query, 
                today, 
                last_week, 
                config, 
                paper_count, 
                max_papers_for_llm, 
                preview=preview_mode
            )
            return
        
        # Batch process papers with local LLM
        res = await process_papers_with_llm(papers_with_abstracts, config)
        
        # Save results to pickle file for potential debugging / caching
        print("Saving results to results.pkl")
        with open("results.pkl", "wb") as f:
            pickle.dump(res, f)

    # Send results to Slack (if we have results)
    if res:
        send_results_to_slack(res, query, today, last_week, config, preview=preview_mode)
    else:
        print("No results to allow sending to Slack.")

# Run the async main function
if __name__ == "__main__":
    asyncio.run(main())