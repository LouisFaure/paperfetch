#!/usr/bin/env -S uv run --script
import tomllib
import os
import sys

# Load configuration from TOML file
with open("config.toml", "rb") as f:
    config = tomllib.load(f)

# Set HF_HOME before importing transformers or any other library that uses it
hf_home = config["local"].get("hf_home", None)
if hf_home is not None:
    os.environ['HF_HOME'] = hf_home

import asyncio
import pickle
from datetime import datetime, timedelta
from slack import send_results_to_slack, send_no_llm_processing_slack, delete_bot_messages
from crossref import fetch_crossref_data
from nature import fetch_nature_data
from llm import create_llm_client, process_papers_with_llm
import llm

# Check if config.toml exists
if not os.path.exists("config.toml"):
    print("Error: config.toml not found!")
    print("Please create a config.toml file following the structure in config_example.toml")
    sys.exit(1)



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

        # Check if LLM processing should be performed based on paper count
        max_papers_for_llm = config.get('search', {}).get('max_papers_for_llm', 10)
        paper_count = len(papers_with_abstracts)
        
        print(f"Found {paper_count} papers with abstracts")
        print(f"Maximum papers for LLM processing: {max_papers_for_llm}")
        
        if paper_count > max_papers_for_llm:
            print(f"Skipping LLM processing: {paper_count} papers exceeds limit of {max_papers_for_llm}")
            # Send email with explanation about skipped LLM processing
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
        
        # Check for local mode flag
        local_mode = False
        if "--local" in sys.argv:
            local_mode = True
            sys.argv.remove("--local")
            print("Local mode enabled: Using local LLM.")


        # Create LLM client or load local model
        client = None
        local_pipe = None
        
        if local_mode:
            local_pipe = llm.load_local_model(config)
        else:
            client = create_llm_client(config)
            
        res = await process_papers_with_llm(papers_with_abstracts, query, client, config, local_pipe=local_pipe)
        
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