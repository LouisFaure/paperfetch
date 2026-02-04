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
    
    # Create dictionary to store titles, abstracts, and URLs
    papers_with_abstracts = {}
    
    # Loop through each search term individually
    for term in query:
        # Define search parameters
        base_url = "https://api.crossref.org/works"
        params = {
            "query": term,
            "filter": f"from-pub-date:{last_week},until-pub-date:{today}",
            "mailto": config["api"]["mailto"],
        }
        
        # Make the request
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"Error fetching data for term '{term}': {e}")
            continue
        
        # Loop through items and collect those with abstracts
        for item in data.get("message", {}).get("items", []):
            title = item.get("title", ["No title"])[0]
            
            # Skip if we already have this paper (deduplication)
            if title in papers_with_abstracts:
                continue

            # Only include papers that have an abstract
            if "abstract" in item:
                abstract = item["abstract"]
                
                # Get URL from DOI (preferred) or URL field
                url = None
                if "DOI" in item:
                    url = f"https://doi.org/{item['DOI']}"
                elif "URL" in item:
                    url = item["URL"]
                
                # Get journal name from container-title
                journal = None
                if "container-title" in item and item["container-title"]:
                    journal = item["container-title"][0]
                
                # Store title, abstract, URL, and journal
                papers_with_abstracts[title] = {
                    "abstract": abstract,
                    "url": url,
                    "journal": journal
                }
    
    return papers_with_abstracts, today, last_week