#!/usr/bin/env -S uv run --script
import tomllib
import os
import sys
import asyncio
import pickle
from mail import send_results_email, send_no_llm_processing_email
from crossref import fetch_crossref_data
from nature import fetch_nature_data
from llm import create_llm_client, process_papers_with_llm

# Check if config.toml exists
if not os.path.exists("config.toml"):
    print("Error: config.toml not found!")
    print("Please create a config.toml file following the structure in config_example.toml")
    sys.exit(1)

# Load configuration from TOML file
with open("config.toml", "rb") as f:
    config = tomllib.load(f)

# Get search query terms from command line or config file
if len(sys.argv) == 2:
    # Single command line argument: treat as one query term
    query = [sys.argv[1]]
elif len(sys.argv) > 2:
    # Multiple command line arguments: use all as query terms
    query = sys.argv[1:]
else:
    # No command line arguments: use query from config file
    query = config["search"]["query"]
    # If config query is a string, convert to list for consistency
    if isinstance(query, str):
        query = [query]

print(f"Search query terms: {query}")

# Fetch papers from CrossRef
print("Fetching papers from CrossRef...")
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