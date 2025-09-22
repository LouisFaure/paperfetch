#!/usr/bin/env -S uv run --script
import tomllib
import os
import sys
import asyncio
import pickle
from mail import send_results_email, send_no_llm_processing_email
from crossref import fetch_crossref_data
from llm import create_llm_client, process_papers_with_llm

# Check if config.toml exists
if not os.path.exists("config.toml"):
    print("Error: config.toml not found!")
    print("Please create a config.toml file following the structure in config_example.toml")
    sys.exit(1)

# Load configuration from TOML file
with open("config.toml", "rb") as f:
    config = tomllib.load(f)

# Determine query source: command line argument or TOML config
if len(sys.argv) > 1:
    query = sys.argv[1]
else:
    query = config["search"]["query"]

# Fetch papers from CrossRef
papers_with_abstracts, today, last_week = fetch_crossref_data(query, config)

async def main():
    """Main async function to orchestrate the paper processing."""
    # Check if LLM processing should be performed based on paper count
    max_papers_for_llm = config.get('search', {}).get('max_papers_for_llm', 10)
    paper_count = len(papers_with_abstracts)
    
    print(f"Found {paper_count} papers with abstracts")
    print(f"Maximum papers for LLM processing: {max_papers_for_llm}")
    
    if paper_count > max_papers_for_llm:
        print(f"Skipping LLM processing: {paper_count} papers exceeds limit of {max_papers_for_llm}")
        # Send email with explanation about skipped LLM processing
        send_no_llm_processing_email(papers_with_abstracts, query, today, last_week, config, paper_count, max_papers_for_llm)
        return
    
    # Create LLM client
    client = create_llm_client(config)
    res = await process_papers_with_llm(papers_with_abstracts, query, client, config)
    # Save results to pickle file for potential debugging
    with open("results.pkl", "wb") as f:
        pickle.dump(res, f)

    # Send results via email
    send_results_email(res, query, today, last_week, config)


# Run the async main function
if __name__ == "__main__":
    asyncio.run(main())