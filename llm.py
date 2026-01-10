import asyncio
import ast
import re
from openai import AsyncOpenAI
import httpx
from transformers import pipeline


def create_llm_client(config):
    """Create and return an AsyncOpenAI client with the given configuration."""
    return AsyncOpenAI(
        base_url=config['api']['openai_url'],
        api_key=config['api']['openai_api'],
        http_client = httpx.AsyncClient(verify=config['api'].get('ssl_verify', True))
    )


def load_local_model(config):
    """Load the local text-generation pipeline."""
    print("Loading local model...")
    model_name = config.get('local', {}).get('model', "google/gemma-3-12b-it-qat-q4_0-unquantized")
    print(f"Using model: {model_name}")
    pipe = pipeline("text-generation", model=model_name)
    print("Model loaded successfully.\n")
    return pipe


def extract_final_response(text):
    """Filter out thinking tokens from model output."""
    if 'assistantfinal' in text:
        return text.split('assistantfinal', 1)[-1].strip()
    elif 'assistant' in text.lower():
        match = re.search(r'(?:assistant(?:final)?[:\s]*)(.*)', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return text


def extract_rating(text):
    """Extract a single integer rating from text."""
    clean = extract_final_response(text)
    # Find all integers in the response
    numbers = re.findall(r'\b(\d+)\b', clean)
    for num in numbers:
        val = int(num)
        if 0 <= val <= 10:
            return val
    return None


async def process_papers_with_llm(papers_with_abstracts, query, client, config, local_pipe=None):
    """
    Process papers using LLM for summarization and interest rating concurrently.
    
    Args:
        papers_with_abstracts (dict): Dictionary of paper titles and abstracts
        query (str): Search query for relevance rating
        client: AsyncOpenAI client instance (or None if local_pipe is used)
        config (dict): Configuration dictionary
        local_pipe: Optional local transformers pipeline
        
    Returns:
        dict: Processed results with summaries and interest ratings
    """
    # Shared System Prompts
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
        journal = paper_data.get("journal")  # Preserve journal if present
        
        # --- PREPARE MESSAGES ---
        
        # 1. Summary Messages
        summary_messages = [
            system_prompt_summarizer,
            {"role": "user", "content": "Summarize the following abstract into 3-5 key bullet points."
             "Output only the Python list format:\n"
             f"Title: {title}\n"
             f"Abstract: {abstract}\n"
             }
        ]
        
        # 2. Rating Messages
        researcher_interests = config.get('search', {}).get('researcher_interests')
        if researcher_interests:
            user_prompt_header = f"Researcher interests: {researcher_interests}\n\nQuery: {query}\n\n"
            user_instructions = "Please rate the relevance of the following abstract to the researcher's interests and the query."
        else:
            user_prompt_header = f"Query: {query}\n\n"
            user_instructions = "Rate the relevance of this abstract to the query."
            
        rating_messages = [
            system_prompt_interest,
            {"role": "user", "content": user_prompt_header + f"Abstract: {abstract}\n\n{user_instructions}"}
        ]

        summary_result = None
        interest_rating = None
        
        # --- LOCAL MODEL PATH ---
        if local_pipe:
            # Summarization
            try:
                # Using to_thread for the blocking pipe call
                output = await asyncio.to_thread(
                    local_pipe, summary_messages, max_new_tokens=512, do_sample=False
                )
                
                generated = output[0]['generated_text']
                if isinstance(generated, list):
                    assistant_response = generated[-1]['content'] if generated else ""
                else:
                    assistant_response = generated
                
                clean_response = extract_final_response(assistant_response)
                
                # Try to parse as python list
                try:
                    summary_result = ast.literal_eval(clean_response)
                    # Verify it's a list
                    if not isinstance(summary_result, list):
                        raise ValueError("Not a list")
                except Exception:
                    # Fallback if it's not a python list but bullet points (local model quirk handling)
                    # or if ast fail
                     summary_result = [line.strip().lstrip('-•*').strip() for line in clean_response.split('\n') if line.strip()]
                     summary_result = [s for s in summary_result if len(s) > 5]

            except Exception as e:
                print(f"Local summary failed for '{title[:50]}...': {e}")
                summary_result = ["Failed to summarize locally"]

            # Rating
            try:
                output_rating = await asyncio.to_thread(
                    local_pipe, rating_messages, max_new_tokens=512, do_sample=False
                )
                
                generated_rating = output_rating[0]['generated_text']
                if isinstance(generated_rating, list):
                    resp_rating = generated_rating[-1]['content'] if generated_rating else ""
                else:
                    resp_rating = generated_rating
                
                interest_rating = extract_rating(resp_rating)
                
            except Exception as e:
                print(f"Local rating failed for '{title[:50]}...': {e}")
                interest_rating = None
                
            # Fallback if extraction failed
            if interest_rating is None:
                interest_rating = "Failed to get local rating"

        # --- API MODEL PATH ---
        else:
            # Summarization with retry logic
            max_attempts = config['api'].get('max_attempts', 3)
            
            for attempt in range(max_attempts):
                try:
                    response = await client.chat.completions.create(
                        model=config['api']['openai_model'],
                        messages=summary_messages
                    )

                    output = response.choices[0].message.content
                    summary_result = ast.literal_eval(output)
                    break  # Success, exit retry loop
                    
                except (ValueError, SyntaxError) as e:
                    print(f"Summary attempt {attempt + 1}/{max_attempts} failed for '{title[:50]}...': {e}")
                    if attempt == max_attempts - 1:
                        summary_result = [f"Failed to parse output after {max_attempts} attempts: {e}"]
                except Exception as e:
                    print(f"Unexpected error on summary attempt {attempt + 1}/{max_attempts} for '{title[:50]}...': {e}")
                    if attempt == max_attempts - 1:
                        summary_result = [f"Failed after {max_attempts} attempts due to unexpected error"]
            
            if summary_result is None:
               summary_result = ["Failed to get summary"]

            # Interest rating with retry logic
            rating_attempts = 3
            interest_rating = None

            for rating_attempt in range(rating_attempts):
                try:
                    interest_response = await client.chat.completions.create(
                        model=config['api']['openai_model'],
                        messages=rating_messages
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
            'url': url,
            'journal': journal
        }
        
        if isinstance(interest_rating, int):
            print(f"Successfully processed with rating {interest_rating}: {title[:50]}...")
        else:
            print(f"Summary processed but rating failed: {title[:50]}... ({interest_rating})")
        
        return title, result
    
    # Process all papers concurrently using asyncio.gather()
    tasks = []
    
    for title, paper_data in papers_with_abstracts.items():
        tasks.append(process_single_paper(title, paper_data))
    
    # Execute tasks based on concurrency setting
    use_async = config.get('local', {}).get('use_async', True) if local_pipe else True
    
    if use_async:
        print("Processing papers asynchronously...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
    else:
        print("Processing papers sequentially (async disabled)...")
        results = []
        for i, task in enumerate(tasks):
            print(f"Processing paper {i+1}/{len(tasks)}...")
            try:
                # We await each task sequentially
                res = await task
                results.append(res)
            except Exception as e:
                results.append(e)
    
    # Build results dictionary
    res = {}
    for result in results:
        if isinstance(result, Exception):
            print(f"Task failed with exception: {result}")
            continue
        title, paper_result = result
        res[title] = paper_result
    
    return res