#!/usr/bin/env -S uv run --script
import requests
import tomllib
import os
import sys
import asyncio
from datetime import datetime, timedelta
from openai import AsyncOpenAI
import ast
import pickle
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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

def fetch_crossref_data(query, config):
    """
    Fetch research papers from CrossRef API for the last week.
    
    Args:
        query (str): Search query for papers
        config (dict): Configuration dictionary containing API settings
        
    Returns:
        tuple: (papers_with_abstracts dict, today date, last_week date)
    """
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
    
    # Create dictionary to store titles, abstracts, and URLs
    papers_with_abstracts = {}
    
    # Loop through items and collect those with abstracts
    for item in data["message"]["items"]:
        title = item.get("title", ["No title"])[0]
        
        # Only include papers that have an abstract
        if "abstract" in item:
            abstract = item["abstract"]
            
            # Get URL from DOI (preferred) or URL field
            url = None
            if "DOI" in item:
                url = f"https://doi.org/{item['DOI']}"
            elif "URL" in item:
                url = item["URL"]
            
            # Store title, abstract, and URL
            papers_with_abstracts[title] = {
                "abstract": abstract,
                "url": url
            }
    
    return papers_with_abstracts, today, last_week

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
    res = await process_papers_with_llm(papers_with_abstracts, query, client, config)
    # Save results to pickle file for potential debugging
    with open("results.pkl", "wb") as f:
        pickle.dump(res, f)

    # Send results via email
    send_results_email(res, query, today, last_week, config)

def send_results_email(results, query, today, last_week, config):
    """
    Format research results and send them via email.
    
    Args:
        results (dict): Processed paper results with summaries and ratings
        query (str): Search query used
        today (date): Today's date
        last_week (date): Last week's date
        config (dict): Configuration dictionary containing email settings
        
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    def format_email_content(results, query, today, last_week):
        """Format the research results into HTML email content."""
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; margin-top: 30px; }}
                .paper {{ margin-bottom: 30px; padding: 15px; border: 1px solid #ecf0f1; border-radius: 5px; }}
                .title {{ font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }}
                .title a {{ color: #2c3e50; text-decoration: none; border-bottom: 1px dotted #3498db; }}
                .title a:hover {{ color: #3498db; text-decoration: none; border-bottom: 1px solid #3498db; }}
                .interest {{ background-color: #3498db; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px; margin-bottom: 10px; display: inline-block; }}
                .bullet-points {{ margin-left: 20px; }}
                .bullet-points li {{ margin-bottom: 5px; line-height: 1.4; }}
                .summary {{ margin-top: 15px; }}
                .query-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ecf0f1; font-size: 12px; color: #7f8c8d; }}
            </style>
        </head>
        <body>
            <h1>PaperFetch Results</h1>
            
            <div class="query-info">
                <strong>Search Query:</strong> {query}<br>
                <strong>Date Range:</strong> {last_week} to {today}<br>
                <strong>Papers Found:</strong> {len(results)}
            </div>
        """
        
        # Sort papers by interest rating (highest first)
        sorted_papers = []
        for title, data in results.items():
            if isinstance(data, dict) and 'interest_rating' in data:
                if isinstance(data['interest_rating'], int):
                    sorted_papers.append((title, data, data['interest_rating']))
                else:
                    # Handle failed ratings by putting them at the end
                    sorted_papers.append((title, data, -1))
            else:
                # Handle papers without proper structure
                sorted_papers.append((title, data, -1))
        
        # Sort by interest rating (descending)
        sorted_papers.sort(key=lambda x: x[2], reverse=True)
        
        for title, data, rating in sorted_papers:
            html_content += f'<div class="paper">'
            
            # Make title clickable if URL is available
            if isinstance(data, dict) and data.get('url'):
                html_content += f'<div class="title"><a href="{data["url"]}" target="_blank">{title}</a></div>'
            else:
                html_content += f'<div class="title">{title}</div>'
            
            if isinstance(data, dict):
                # Display interest rating
                if isinstance(data.get('interest_rating'), int):
                    rating_color = "#e74c3c" if rating < 4 else "#f39c12" if rating < 7 else "#27ae60"
                    html_content += f'<div class="interest" style="background-color: {rating_color};">Interest Rating: {rating}/10</div>'
                else:
                    html_content += f'<div class="interest" style="background-color: #95a5a6;">Interest Rating: {data.get("interest_rating", "N/A")}</div>'
                
                # Display bullet points
                if 'summary' in data and isinstance(data['summary'], list):
                    html_content += '<div class="summary"><strong>Key Points:</strong></div>'
                    html_content += '<ul class="bullet-points">'
                    for point in data['summary']:
                        html_content += f'<li>{point}</li>'
                    html_content += '</ul>'
                else:
                    html_content += f'<div class="summary">Summary not available</div>'
            else:
                # Handle error cases
                html_content += f'<div class="summary" style="color: #e74c3c;">{data}</div>'
            
            html_content += '</div>'
        
        html_content += f"""
            <div class="footer">
                Generated by PaperFetch on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </div>
        </body>
        </html>
        """
        
        return html_content

    def send_email(subject, html_content, config):
        """Send an email with the formatted results."""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = config['email']['sender_email']
            msg['To'] = config['email']['recipient_email']
            msg['Subject'] = subject
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Connect to server and send email
            with smtplib.SMTP(config['email']['smtp_server'], config['email']['smtp_port']) as server:
                server.starttls()
                server.login(config['email']['sender_email'], config['email']['sender_password'])
                server.send_message(msg)
            
            print(f"Email sent successfully to {config['email']['recipient_email']}")
            return True
            
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

    # Check if there are valid results to email
    if results and any(isinstance(data, dict) for data in results.values()):
        # Create email subject with query and date
        subject = f"{config['email']['subject_prefix']}: {query} ({today})"
        
        # Format email content
        html_content = format_email_content(results, query, today, last_week)
        
        # Send email
        email_sent = send_email(subject, html_content, config)
        
        if email_sent:
            print("\n" + "="*80)
            print("EMAIL SENT SUCCESSFULLY!")
            print("="*80)
        else:
            print("\n" + "="*80)
            print("EMAIL SENDING FAILED - Check your email configuration")
            print("="*80)
            print("\nFormatted results preview:")
            print(f"Subject: {subject}")
            print("HTML content generated successfully")
        
        return email_sent
    else:
        print("\n" + "="*80)
        print("NO VALID RESULTS TO EMAIL")
        print("="*80)
        return False

# Run the async main function
if __name__ == "__main__":
    asyncio.run(main())