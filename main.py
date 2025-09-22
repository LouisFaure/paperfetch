#!/usr/bin/env -S uv run --script
import requests
import tomllib
import os
import sys
from datetime import datetime, timedelta
from openai import OpenAI
import ast
import pickle

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

system_prompt_summarizer = {
    "role": "system",
    "content": """
    You are a scientific abstract summarizer.
    Your task is to extract key points from research paper abstracts and format them as a Python list of strings.
    Each bullet point should be concise, informative, and capture essential information.
    Always output exactly in this format: ['point 1', 'point 2', 'point 3'] with no additional text or explanations."""}


system_prompt_interest = {
    "role": "system", 
    "content": """
    You are a research relevance evaluator. Your task is to assess how well a research paper abstract matches a given query or research interest. Rate the relevance on a scale of 0-10 where:
- 0: Completely unrelated
- 1-3: Minimally related (tangential connection)
- 4-6: Moderately related (some overlap in topics/methods)
- 7-9: Highly related (direct relevance to query)
- 10: Perfectly aligned with the query

Output only a single integer between 0 and 10 with no additional text or explanation."""}


res = {}
# Print the results
print(f"Found {len(papers_with_abstracts)} papers with abstracts:")
print("-" * 80)
for title, abstract in papers_with_abstracts.items():
    # Retry logic: up to 3 attempts for each abstract
    max_attempts = 3
    success = False
    
    for attempt in range(max_attempts):
        try:
            response = client.chat.completions.create(
                model=config['api']['openai_model'],
                messages=[
                    system_prompt_summarizer,
                    {"role": "user", "content": "Summarize the following abstract into 3-5 key bullet points."
                     "Output only the Python list format:\n"
                     f"Title: {title}\n"
                     f"Abstract: {abstract}\n"
                     }]
            )

            output = response.choices[0].message.content
            # Safe conversion to list
            res[title] = ast.literal_eval(output)
            success = True
            break  # Success, exit retry loop
            
        except (ValueError, SyntaxError) as e:
            print(f"Attempt {attempt + 1}/{max_attempts} failed for '{title[:50]}...': {e}")
            if attempt == max_attempts - 1:
                res[title] = f"Failed to parse output after {max_attempts} attempts, skipping paper: {title}"
            # Continue to next attempt
        except Exception as e:
            print(f"Unexpected error on attempt {attempt + 1}/{max_attempts} for '{title[:50]}...': {e}")
            if attempt == max_attempts - 1:
                res[title] = f"Failed after {max_attempts} attempts due to unexpected error, skipping paper: {title}"
            # Continue to next attempt
    
    if success:
        # Now get the interest rating
        rating_attempts = 3
        rating_success = False
        
        for rating_attempt in range(rating_attempts):
            try:
                interest_response = client.chat.completions.create(
                    model=config['api']['openai_model'],
                    messages=[
                        system_prompt_interest,
                        {"role": "user", "content": f"Query: {query}\n\nAbstract: {abstract}\n\nRate the relevance of this abstract to the query."}
                    ]
                )
                
                interest_output = interest_response.choices[0].message.content.strip()
                # Parse as integer with validation
                interest_rating = int(interest_output)
                
                # Validate the rating is in expected range
                if 0 <= interest_rating <= 10:
                    # Store both summary and rating
                    if isinstance(res[title], list):  # Only if summarizer succeeded
                        res[title] = {
                            'summary': res[title],
                            'interest_rating': interest_rating
                        }
                    rating_success = True
                    break  # Success, exit retry loop
                else:
                    raise ValueError(f"Rating {interest_rating} is outside valid range 0-10")
                    
            except (ValueError, TypeError) as e:
                print(f"Interest rating attempt {rating_attempt + 1}/{rating_attempts} failed for '{title[:50]}...': {e}")
                if rating_attempt == rating_attempts - 1:
                    # Keep the summary but note rating failure
                    if isinstance(res[title], list):
                        res[title] = {
                            'summary': res[title],
                            'interest_rating': f"Failed to get rating after {rating_attempts} attempts"
                        }
                # Continue to next attempt
            except Exception as e:
                print(f"Unexpected error on interest rating attempt {rating_attempt + 1}/{rating_attempts} for '{title[:50]}...': {e}")
                if rating_attempt == rating_attempts - 1:
                    # Keep the summary but note rating failure
                    if isinstance(res[title], list):
                        res[title] = {
                            'summary': res[title],
                            'interest_rating': f"Failed to get rating due to unexpected error"
                        }
                # Continue to next attempt
        
        if rating_success:
            print(f"Successfully processed with rating: {title[:50]}...")
        else:
            print(f"Summary processed but rating failed: {title[:50]}...")

with open("results.pkl", "wb") as f:
    pickle.dump(res, f)


with open("results.pkl", "rb") as f:
    res = pickle.load(f)