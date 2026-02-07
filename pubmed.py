"""
PubMed paper fetching module using Biopython.
Replaces the Nature/Springer API with PubMed for broader coverage and reliability.
"""

from Bio import Entrez
from datetime import datetime, timedelta
import time
import pandas as pd


def _parse_pubmed_article(article):
    """
    Parse a PubMed article from XML format.
    
    Args:
        article: PubMed article from Entrez.read()
        
    Returns:
        dict: Parsed paper data or None if abstract is missing
    """
    try:
        medline_citation = article['MedlineCitation']
        article_data = medline_citation['Article']
        
        # Extract PMID
        pmid = str(medline_citation['PMID'])
        
        # Extract title
        title = article_data.get('ArticleTitle', '')
        
        # Extract abstract (if available)
        abstract = ''
        if 'Abstract' in article_data and 'AbstractText' in article_data['Abstract']:
            abstract_parts = article_data['Abstract']['AbstractText']
            if isinstance(abstract_parts, list):
                # Handle structured abstracts
                abstract = ' '.join(str(part) for part in abstract_parts)
            else:
                abstract = str(abstract_parts)
        
        # Skip papers without abstracts
        if not abstract or abstract == '':
            return None
        
        # Extract authors
        authors = []
        if 'AuthorList' in article_data:
            for author in article_data['AuthorList']:
                if 'LastName' in author and 'Initials' in author:
                    authors.append(f"{author['LastName']} {author['Initials']}")
                elif 'CollectiveName' in author:
                    authors.append(author['CollectiveName'])
        
        # Extract journal
        journal = article_data.get('Journal', {}).get('Title', '')
        
        # Extract publication date
        pub_date = ''
        if 'Journal' in article_data and 'JournalIssue' in article_data['Journal']:
            pub_date_info = article_data['Journal']['JournalIssue'].get('PubDate', {})
            year = pub_date_info.get('Year', '')
            month = pub_date_info.get('Month', '')
            day = pub_date_info.get('Day', '')
            pub_date = f"{year}-{month}-{day}".strip('-')
        
        # Extract DOI
        doi = ''
        if 'PubmedData' in article and 'ArticleIdList' in article['PubmedData']:
            for article_id in article['PubmedData']['ArticleIdList']:
                if hasattr(article_id, 'attributes') and article_id.attributes.get('IdType') == 'doi':
                    doi = str(article_id)
                    break
        
        return {
            'pmid': pmid,
            'title': title,
            'abstract': abstract,
            'authors': authors,
            'journal': journal,
            'publication_date': pub_date,
            'doi': doi,
            'url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        }
        
    except Exception as e:
        print(f"  Warning: Error parsing article: {e}")
        return None


def _fetch_pubmed_term(term, date_from, date_to, max_results=5000, journals=None):
    """
    Search PubMed for papers matching a search term and date range.
    
    Args:
        term (str): The search term
        date_from (str): Start date in YYYY-MM-DD format
        date_to (str): End date in YYYY-MM-DD format
        max_results (int): Maximum number of results to fetch
        journals (list): Optional list of journal names to restrict search to
        
    Returns:
        list: List of paper dictionaries with metadata
    """
    # Convert date format from YYYY-MM-DD to YYYY/MM/DD for PubMed
    start_date = datetime.strptime(date_from, '%Y-%m-%d')
    end_date = datetime.strptime(date_to, '%Y-%m-%d')
    date_query = f"{start_date.strftime('%Y/%m/%d')}:{end_date.strftime('%Y/%m/%d')}[pdat]"
    
    # Construct the query
    query = f"{term} AND {date_query}"
    
    # Add journal restriction if specified
    if journals:
        journal_query = " OR ".join([f'"{j}"[Journal]' for j in journals])
        query = f"{query} AND ({journal_query})"
    
    print(f"  Searching PubMed: {term}")
    if journals:
        print(f"  Restricted to journals: {', '.join(journals[:3])}{'...' if len(journals) > 3 else ''}")
    
    # Step 1: Search for IDs
    try:
        search_handle = Entrez.esearch(
            db="pubmed",
            term=query,
            retmax=max_results,
            sort="pub_date",
            usehistory="y"  # Store results on server for efficient fetching
        )
        search_results = Entrez.read(search_handle)
        search_handle.close()
        
        id_list = search_results["IdList"]
        count = int(search_results["Count"])
        
        print(f"  Found {count} total papers (fetching up to {max_results})")
        
        if not id_list:
            return []
        
    except Exception as e:
        print(f"  Error during search: {e}")
        return []
    
    # Step 2: Fetch details using efetch with XML format
    papers = []
    batch_size = 100  # Fetch in batches to avoid timeouts
    
    for i in range(0, len(id_list), batch_size):
        batch_ids = id_list[i:i + batch_size]
        
        try:
            fetch_handle = Entrez.efetch(
                db="pubmed",
                id=batch_ids,
                rettype="medline",
                retmode="xml"
            )
            records = Entrez.read(fetch_handle)
            fetch_handle.close()
            
            # Parse the XML results
            for article in records['PubmedArticle']:
                try:
                    paper_data = _parse_pubmed_article(article)
                    if paper_data:
                        papers.append(paper_data)
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"  Warning: Error fetching batch: {e}")
            continue
        
        # Be polite to NCBI servers
        time.sleep(0.34)  # NCBI allows 3 requests per second without API key
    
    print(f"  Retrieved {len(papers)} papers with abstracts")
    return papers


def fetch_pubmed_data(query, config):
    """
    Fetch research papers from PubMed for the configured time period.
    
    Args:
        query (list): List of search terms.
        config (dict): Configuration dictionary containing API settings.
        
    Returns:
        tuple: (papers_with_abstracts dict, today date, last_week date)
    """
    # Set email for NCBI (required by their API)
    email = config.get('api', {}).get('mailto', 'your_email@example.com')
    Entrez.email = email
    
    # Get the number of days to check from config, with a default of 7
    days_to_check = config.get("search", {}).get("days_to_check", 7)
    
    # Get publication names filter from config (optional)
    # Using same config key as nature.py for compatibility
    publication_names = config.get("search", {}).get("journals", None)
    journals = None
    if publication_names:
        if isinstance(publication_names, str):
            journals = [publication_names]
        else:
            journals = publication_names
    
    # Calculate dynamic date range
    today = datetime.now().date()
    last_week = today - timedelta(days=days_to_check)
    
    # Format dates as strings
    date_from = last_week.strftime('%Y-%m-%d')
    date_to = today.strftime('%Y-%m-%d')
    
    # Get max results per term
    max_results = config.get("search", {}).get("max_results_per_term", 5000)
    
    # Collect all papers
    all_papers = []
    
    for term in query:
        print(f"Searching PubMed for: {term}")
        
        # Fetch papers for this term
        term_papers = _fetch_pubmed_term(term, date_from, date_to, max_results, journals)
        all_papers.extend(term_papers)
        
        # Be polite to the API
        time.sleep(0.5)
    
    # If no records found, return empty
    if not all_papers:
        print("No papers found in PubMed")
        return {}, today, last_week
    
    # Convert to DataFrame for efficient deduplication
    df = pd.DataFrame(all_papers)
    
    # Deduplicate by PMID (most reliable) or title
    initial_count = len(df)
    df = df.drop_duplicates(subset=['pmid'])
    dedup_count = len(df)
    
    if initial_count > dedup_count:
        print(f"Removed {initial_count - dedup_count} duplicate papers")
    
    # Convert to expected output format
    papers_with_abstracts = {}
    
    for _, row in df.iterrows():
        title = row['title']
        abstract = row['abstract']
        
        # Determine URL - prefer DOI, fallback to PubMed URL
        url = None
        if row['doi']:
            url = f"https://doi.org/{row['doi']}"
        else:
            url = row['url']
        
        journal = row['journal']
        
        papers_with_abstracts[title] = {
            "abstract": abstract,
            "url": url,
            "journal": journal
        }
    
    print(f"Total unique papers: {len(papers_with_abstracts)}")
    
    return papers_with_abstracts, today, last_week
