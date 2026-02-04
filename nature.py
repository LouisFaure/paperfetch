from sprynger import Meta, init
from datetime import datetime, timedelta
import time
import requests # For catching status codes if needed

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
    
    # Create dictionary to store titles, abstracts, and URLs
    papers_with_abstracts = {}
    
    # Convert publication_names to set for efficient lookup and query construction
    journal_filter = None
    if publication_names:
        if isinstance(publication_names, str):
            # If single string, convert to list
            publication_names = [publication_names]
        publication_names_set = set(name.lower() for name in publication_names)
        
        # Construct journal filter for API query: (journal:"Nature" OR journal:"Nature Cancer" OR ...)
        journal_parts = [f'journal:"{name}"' for name in publication_names]
        journal_filter = f"({ ' OR '.join(journal_parts) })"
    else:
        publication_names_set = None

    # Loop through each search term individually to improve capture reliability
    for term in query:
        # Construct the query string with journal filter if available
        query_str = f'"{term}"'
        if journal_filter:
            query_str = f"{query_str} AND {journal_filter}"
            
        print(f"Searching Nature/Springer for: {query_str}")
        
        start = 1
        total_results = 1 # Initial value to enter the loop
        
        while start <= total_results:
            try:
                # Create Meta search object for the specific term and page
                meta = Meta(
                    query=query_str,
                    datefrom=date_from,
                    dateto=date_to,
                    nr_results=100,
                    start=start
                )
                
                # Update total results on the first call
                if start == 1:
                    total_results = getattr(meta.results, 'total', 0)
                    if total_results > 0:
                        print(f"  Found {total_results} total matches for this keyword in target journals.")
                    else:
                        print("  No matches found for this keyword in target journals.")
                        break
                
                # Loop through records and collect those with abstracts
                for record in meta:
                    title = record.title if record.title else "No title"
                    
                    # Skip if we already have this paper (deduplication)
                    if title in papers_with_abstracts:
                        continue
        
                    # Only include papers that have an abstract
                    if hasattr(record, 'abstract') and record.abstract:
                        # Double check journal filter (case-insensitive) just in case API returns fuzzy matches
                        if publication_names_set is not None:
                            if not hasattr(record, 'publicationName') or record.publicationName is None:
                                continue
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
                
                # Increment start for the next page
                start += 100
                
                # Safety break to avoid excessive fetching for extremely broad queries
                if start > 2000: 
                    print("  Reached safety limit of 2000 results for this keyword. Stopping.")
                    break
                    
                # Small delay to be polite to the API
                time.sleep(0.5)
                
            except Exception as e:
                if "403" in str(e):
                    print(f"  Rate limit or auth error (403) at start={start}. Waiting 5s...")
                    time.sleep(5)
                    # We could retry or break. Let's try to break to avoid getting fully blocked
                    break
                else:
                    print(f"  Error fetching page starting at {start}: {e}")
                    break
    
    return papers_with_abstracts, today, last_week