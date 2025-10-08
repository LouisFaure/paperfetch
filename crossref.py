import requests
from datetime import datetime, timedelta

def fetch_crossref_data(query, config):
    """
    Fetch research papers from CrossRef API for the last week.
    
    Args:
        query (list): List of search terms to be joined with space
        config (dict): Configuration dictionary containing API settings
        
    Returns:
        tuple: (papers_with_abstracts dict, today date, last_week date)
    """
    # Get the number of days to check from config, with a default of 7
    days_to_check = config.get("search", {}).get("days_to_check", 7)

    # Calculate dynamic date range
    today = datetime.now().date()
    last_week = today - timedelta(days=days_to_check)
    
    # Build query string by joining terms with space
    query_string = ' '.join(query)
    
    # Define search parameters
    base_url = "https://api.crossref.org/works"
    params = {
        "query": query_string,
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