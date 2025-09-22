#!/usr/bin/env -S uv run --script
import tomllib
import os
import sys
import asyncio
from openai import AsyncOpenAI
import ast
import pickle
from mail import send_results_email, send_no_llm_processing_email
from crossref import fetch_crossref_data

# Check if config.toml exists
if not os.path.exists("config.toml"):
    print("Error: config.toml not found!")
    print("Please create a config.toml file following the structure in config_example.toml")
    sys.exit(1)

# Load configuration from TOML file
with open("config.toml", "rb") as f:
    config = tomllib.load(f)

client = AsyncOpenAI(
    base_url=config['api']['openai_url'],
    api_key=config['api']['openai_api']
)



# Determine query source: command line argument or TOML config
if len(sys.argv) > 1:
    query = sys.argv[1]
else:
    query = config["search"]["query"]

# Fetch papers from CrossRef
papers_with_abstracts, today, last_week = fetch_crossref_data(query, config)

async def process_papers_with_llm(papers_with_abstracts, query, client, config):
    """
    Process papers using LLM for summarization and interest rating concurrently.
    
    Args:
        papers_with_abstracts (dict): Dictionary of paper titles and abstracts
        query (str): Search query for relevance rating
        client: AsyncOpenAI client instance
        config (dict): Configuration dictionary
        
    Returns:
        dict: Processed results with summaries and interest ratings
    """
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

    async def process_single_paper(title, paper_data):
        """Process a single paper with LLM summarization and interest rating."""
        abstract = paper_data["abstract"]
        url = paper_data["url"]
        
        # Summarization with retry logic
        max_attempts = 3
        summary_result = None
        
        for attempt in range(max_attempts):
            try:
                response = await client.chat.completions.create(
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
                summary_result = ast.literal_eval(output)
                break  # Success, exit retry loop
                
            except (ValueError, SyntaxError) as e:
                print(f"Summary attempt {attempt + 1}/{max_attempts} failed for '{title[:50]}...': {e}")
                if attempt == max_attempts - 1:
                    return title, f"Failed to parse output after {max_attempts} attempts, skipping paper: {title}"
            except Exception as e:
                print(f"Unexpected error on summary attempt {attempt + 1}/{max_attempts} for '{title[:50]}...': {e}")
                if attempt == max_attempts - 1:
                    return title, f"Failed after {max_attempts} attempts due to unexpected error, skipping paper: {title}"
        
        if summary_result is None:
            return title, f"Failed to get summary after {max_attempts} attempts"
        
        # Interest rating with retry logic
        rating_attempts = 3
        interest_rating = None
        
        for rating_attempt in range(rating_attempts):
            try:
                interest_response = await client.chat.completions.create(
                    model=config['api']['openai_model'],
                    messages=[
                        system_prompt_interest,
                        {"role": "user", "content": f"Query: {query}\n\nAbstract: {abstract}\n\nRate the relevance of this abstract to the query."}
                    ]
                )
                
                interest_output = interest_response.choices[0].message.content.strip()
                interest_rating = int(interest_output)
                
                # Validate the rating is in expected range
                if 0 <= interest_rating <= 10:
                    break  # Success, exit retry loop
                else:
                    raise ValueError(f"Rating {interest_rating} is outside valid range 0-10")
                    
            except (ValueError, TypeError) as e:
                print(f"Interest rating attempt {rating_attempt + 1}/{rating_attempts} failed for '{title[:50]}...': {e}")
                if rating_attempt == rating_attempts - 1:
                    interest_rating = f"Failed to get rating after {rating_attempts} attempts"
            except Exception as e:
                print(f"Unexpected error on interest rating attempt {rating_attempt + 1}/{rating_attempts} for '{title[:50]}...': {e}")
                if rating_attempt == rating_attempts - 1:
                    interest_rating = f"Failed to get rating due to unexpected error"
        
        # Return structured result
        result = {
            'summary': summary_result,
            'interest_rating': interest_rating,
            'url': url
        }
        
        if isinstance(interest_rating, int):
            print(f"Successfully processed with rating {interest_rating}: {title[:50]}...")
        else:
            print(f"Summary processed but rating failed: {title[:50]}...")
        
        return title, result

    # Print the results
    print(f"Found {len(papers_with_abstracts)} papers with abstracts:")
    print("-" * 80)
    
    # Process all papers concurrently using asyncio.gather()
    tasks = []
    for title, paper_data in papers_with_abstracts.items():
        tasks.append(process_single_paper(title, paper_data))
    
    # Execute all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Build results dictionary
    res = {}
    for result in results:
        if isinstance(result, Exception):
            print(f"Task failed with exception: {result}")
            continue
        title, paper_result = result
        res[title] = paper_result
    
    return res

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
    
    res = await process_papers_with_llm(papers_with_abstracts, query, client, config)
    # Save results to pickle file for potential debugging
    with open("results.pkl", "wb") as f:
        pickle.dump(res, f)

    # Send results via email
    send_results_email(res, query, today, last_week, config)


# Run the async main function
if __name__ == "__main__":
    asyncio.run(main())