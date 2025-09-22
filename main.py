#!/usr/bin/env -S uv run --script
import requests
import tomllib
import os
import sys
from datetime import datetime, timedelta

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

# Calculate dynamic date range
today = datetime.now().date()
last_week = today - timedelta(days=7)

# Define search parameters
base_url = "https://api.crossref.org/works"
params = {
    "query": query,
    "filter": f"from-pub-date:{last_week},until-pub-date:{today}",
    "mailto": config["api"]["mailto"],
}

# Make the request
response = requests.get(base_url, params=params)
data = response.json()

# Create dictionary to store titles and abstracts
papers_with_abstracts = {}

# Loop through items and collect those with abstracts
for item in data["message"]["items"]:
    title = item.get("title", ["No title"])[0]
    
    # Only include papers that have an abstract
    if "abstract" in item:
        abstract = item["abstract"]
        papers_with_abstracts[title] = abstract

# Print the results
print(f"Found {len(papers_with_abstracts)} papers with abstracts:")
print("-" * 80)
for title, abstract in papers_with_abstracts.items():
    print(f"Title: {title}")
    print(f"Abstract: {abstract}")
    print("-" * 80)
    break  # Remove this break to print all papers

# Optionally, you can also return the dictionary for programmatic use
# print("\nDictionary of papers with abstracts:")
# print(papers_with_abstracts)
