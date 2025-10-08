from sprynger import Meta, init
from datetime import datetime, timedelta

def fetch_nature_data(query, config):
    """
    Fetch research papers from Nature/Springer API for the last week.
    
    Args:
        query (list): List of search terms to be joined with " AND "
        config (dict): Configuration dictionary containing API settings
        
    Returns:
        tuple: (papers_with_abstracts dict, today date, last_week date)
    """
    # Initialize Springer API
    api_key = config.get('api', {}).get('springer_api_key', False)
    init(api_key=api_key)
    
    # Get the number of days to check from config, with a default of 7
    days_to_check = config.get("search", {}).get("days_to_check", 7)

    # Calculate dynamic date range
    today = datetime.now().date()
    last_week = today - timedelta(days=days_to_check)
    
    # Format dates as strings
    date_from = last_week.strftime('%Y-%m-%d')
    date_to = today.strftime('%Y-%m-%d')
    
    # Build query string by joining terms with " AND "
    query_string = ' AND '.join([f'"{term}"' for term in query])
    print(f"Nature/Springer query string: {query_string}")
    
    # Create Meta search object
    meta = Meta(
        query=query_string,
        datefrom=date_from,
        dateto=date_to,
        nr_results=100
    )
    
    # Create dictionary to store titles, abstracts, and URLs
    papers_with_abstracts = {}
    
    # Loop through records and collect those with abstracts
    for record in meta:
        title = record.title if record.title else "No title"
        
        # Only include papers that have an abstract
        if hasattr(record, 'abstract') and record.abstract:
            abstract = record.abstract
            
            # Get URL from DOI (preferred)
            url = None
            if hasattr(record, 'doi') and record.doi:
                url = f"https://doi.org/{record.doi}"
            elif hasattr(record, 'url') and record.url:
                url = record.url
            
            # Store title, abstract, and URL
            papers_with_abstracts[title] = {
                "abstract": abstract,
                "url": url
            }
    
    return papers_with_abstracts, today, last_week