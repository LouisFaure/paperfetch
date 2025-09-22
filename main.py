#!/usr/bin/env -S uv run --script
import requests
import tomllib
import os
import sys

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

# Define search parameters
base_url = "https://api.crossref.org/works"
params = {
    "query": query,
    "filter": "from-pub-date:2025-09-15,until-pub-date:2025-09-22",
    "mailto": config["api"]["mailto"],
}

# Make the request
response = requests.get(base_url, params=params)
data = response.json()

# Loop through items and check if abstract is present
for item in data["message"]["items"]:
    title = item.get("title", ["No title"])[0]
    doi = item.get("DOI", "No DOI")
    has_abstract = "abstract" in item

    print(f"Title: {title}")
    print(f"DOI: {doi}")
    print(f"Abstract {'FOUND ✅' if has_abstract else 'missing ❌'}")
    print("-" * 80)
