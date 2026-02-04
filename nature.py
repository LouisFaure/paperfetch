from sprynger import Meta, init
from datetime import datetime, timedelta
import time
import pandas as pd

def fetch_nature_data(query, config):
    """
    Fetch research papers from Nature/Springer API for the last week.
    
    Args:
        query (list): List of search terms.
        config (dict): Configuration dictionary containing API settings.
        
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
    publication_names_set = None
    if publication_names:
        if isinstance(publication_names, str):
            publication_names = [publication_names]
        # Normalize to lower case for filtering
        publication_names_set = set(name.lower() for name in publication_names)

    # Calculate dynamic date range
    today = datetime.now().date()
    last_week = today - timedelta(days=days_to_check)
    
    # Format dates as strings
    date_from = last_week.strftime('%Y-%m-%d')
    date_to = today.strftime('%Y-%m-%d')
    
    # Collect all potential records in a list of dicts first
    all_records = []
    
    for term in query:
        print(f"Searching Nature/Springer for: {term}")
        query_str = f'"{term}"'
        
        # Pagination disabled as requested - fetching single page
        try:
            # Create Meta search object
            # Using nr_results=500 to get a good batch without looping if API supports it, otherwise it might cap at 100
            meta = Meta(
                query=query_str,
                datefrom=date_from,
                dateto=date_to,
                nr_results=500,
                start=1
            )
            
            # Check total results
            if hasattr(meta, 'results') and hasattr(meta.results, 'total'):
                total_results = int(meta.results.total)
                print(f"  Found {total_results} total matches for '{term}' (fetching top results)")
            
            records_found = 0
            for record in meta:
                records_found += 1
                
                # Basic validity check (must have title)
                if not (hasattr(record, 'title') and record.title):
                     continue
                     
                # Extract fields
                rec_data = {
                    'title': record.title,
                    'abstract': getattr(record, 'abstract', None),
                    'publicationName': getattr(record, 'publicationName', None),
                    'doi': getattr(record, 'doi', None),
                    'url': getattr(record, 'url', None)
                }
                all_records.append(rec_data)
            
            # Be polite to the API
            time.sleep(0.2)
            
        except Exception as e:
            print(f"  Error fetching results for '{term}': {e}")

    # If no records found, return empty
    if not all_records:
        return {}, today, last_week

    # Convert to DataFrame for efficient processing
    df = pd.DataFrame(all_records)
    
    # Drop records without abstract
    df = df[df['abstract'].notna() & (df['abstract'] != '')]
    
    # Deduplicate by title (or doi if preferred, but title matches prev logic)
    # We can also drop duplicates by DOI if present to be safer
    df = df.drop_duplicates(subset=['title'])
    
    # Filter by journal if specified
    if publication_names_set:
        # Create a lowercase column for filtering
        df['pub_lower'] = df['publicationName'].apply(lambda x: x.lower() if isinstance(x, str) else '')
        # Check against the set
        # Since isin takes a list/set, this is efficient
        df = df[df['pub_lower'].isin(publication_names_set)]
    
    # Convert back to expected output format
    papers_with_abstracts = {}
    
    for _, row in df.iterrows():
        title = row['title']
        abstract = row['abstract']
        
        # Determine URL
        url = None
        if row['doi']:
            url = f"https://doi.org/{row['doi']}"
        elif row['url']:
            url = row['url']
            
        journal = row['publicationName']
        
        papers_with_abstracts[title] = {
            "abstract": abstract,
            "url": url,
            "journal": journal
        }
            
    return papers_with_abstracts, today, last_week