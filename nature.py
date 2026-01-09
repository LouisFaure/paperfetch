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
    
    # Get publication names filter from config (optional)
    publication_names = config.get("search", {}).get("springer_publication_names", None)

    # Calculate dynamic date range
    today = datetime.now().date()
    last_week = today - timedelta(days=days_to_check)
    
    # Format dates as strings
    date_from = last_week.strftime('%Y-%m-%d')
    date_to = today.strftime('%Y-%m-%d')
    
    # Build query string by joining terms with " OR "
    query_string = ' OR '.join([f'"{term}"' for term in query])
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
    
    # Convert publication_names to set for efficient lookup (if provided)
    if publication_names:
        if isinstance(publication_names, str):
            # If single string, convert to list
            publication_names = [publication_names]
        publication_names_set = set(name.lower() for name in publication_names)
    else:
        publication_names_set = None
    
    # Loop through records and collect those with abstracts
    for record in meta:
        title = record.title if record.title else "No title"
        
        # Only include papers that have an abstract
        if hasattr(record, 'abstract') and record.abstract:
            # Filter by publication name if specified
            if publication_names_set is not None:
                if not hasattr(record, 'publicationName') or record.publicationName is None:
                    continue
                # Case-insensitive comparison
                if record.publicationName.lower() not in publication_names_set:
                    continue
            
            abstract = record.abstract
            
            # Get URL from DOI (preferred)
            url = None
            if hasattr(record, 'doi') and record.doi:
                url = f"https://doi.org/{record.doi}"
            elif hasattr(record, 'url') and record.url:
                url = record.url
            
            # Get journal name from publicationName
            journal = None
            if hasattr(record, 'publicationName') and record.publicationName:
                journal = record.publicationName
            
            # Store title, abstract, URL, and journal
            papers_with_abstracts[title] = {
                "abstract": abstract,
                "url": url,
                "journal": journal
            }
    
    return papers_with_abstracts, today, last_week