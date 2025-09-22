import requests
from datetime import datetime, timedelta

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