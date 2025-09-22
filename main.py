#!/usr/bin/env -S uv run --script
import requests
import tomllib
import os
import sys
from datetime import datetime, timedelta
from openai import OpenAI
import ast

# Check if config.toml exists
if not os.path.exists("config.toml"):
    print("Error: config.toml not found!")
    print("Please create a config.toml file following the structure in config_example.toml")
    sys.exit(1)

# Load configuration from TOML file
with open("config.toml", "rb") as f:
    config = tomllib.load(f)

client = OpenAI(
    base_url=config['api']['openai_url'],
    api_key=config['api']['openai_api'] 
)

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

system_prompt = {"role": "system", "content": "You are a scientific abstract summarizer." 
         "Your task is to extract key points from research paper abstracts and format them as a Python list of strings."
         "Each bullet point should be concise, informative, and capture essential information."
         "Always output exactly in this format: ['point 1', 'point 2', 'point 3'] with no additional text or explanations."}



res = {}
# Print the results
print(f"Found {len(papers_with_abstracts)} papers with abstracts:")
print("-" * 80)
for title, abstract in papers_with_abstracts.items():
    response = client.chat.completions.create(
    model=config['api']['openai_model'],
    messages=[
        system_prompt,
        {"role": "user", "content": "Summarize the following abstract into 3-5 key bullet points." 
         "Output only the Python list format:\n"
         f"Title: {title}\n"
         f"Abstract: {abstract}\n"
         }]
    )

    output = response.choices[0].message.content
    # Safe conversion to list
    try:
        res[title] = ast.literal_eval(output)
    except (ValueError, SyntaxError) as e:
        print(f"Error parsing output: {e}")