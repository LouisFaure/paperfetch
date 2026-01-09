"""
Slack notification module for PaperFetch.

Sends paper notifications via Slack Web API. Each high-relevance paper
(rating >= min_rating) is posted as a separate message to enable individual
emoji reactions for interest signaling.
"""

from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def get_slack_client(config: dict) -> tuple[WebClient, str]:
    """
    Initialize Slack client and get channel ID from config.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        tuple: (WebClient instance, channel_id string)
    """
    token = config['slack'].get('bot_token')
    channel_id = config['slack'].get('channel_id')
    
    if not token or not channel_id:
        print("Error: Missing 'bot_token' or 'channel_id' in [slack] config.")
        return None, None
        
    import ssl
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    return WebClient(token=token, ssl=ssl_context), channel_id


def send_paper_to_slack(paper_title: str, paper_data: dict, config: dict, preview: bool = False) -> bool:
    """
    Post a single paper notification to Slack.
    
    Only shows title (linked), journal, and rating.
    
    Args:
        paper_title: Title of the paper
        paper_data: Dictionary containing paper details (url, journal, interest_rating)
        config: Configuration dictionary containing Slack settings
        
    Returns:
        bool: True if message posted successfully, False otherwise
    """
    client = None
    if not preview:
        client, channel_id = get_slack_client(config)
        if not client:
            return False

    
    # Extract data
    url = paper_data.get('url', '')
    journal = paper_data.get('journal', 'Unknown Journal')
    rating = paper_data.get('interest_rating', 'N/A')
    
    # Rating emoji based on score
    if isinstance(rating, int):
        rating_emoji = "🔥" if rating >= 9 else "⭐" if rating >= 7 else "📊"
    else:
        rating_emoji = "❓"
    
    # Format title as link
    if url:
        title_text = f"<{url}|{paper_title}>"
    else:
        title_text = paper_title
    
    # Build plain text message
    message = f"📄 *{title_text}*\n🏷️ {journal}  |  {rating_emoji} *{rating}/10*"
    
    if preview:
        print(message)
        return True
    
    try:
        response = client.chat_postMessage(
            channel=channel_id,
            text=message,
            unfurl_links=False,
            unfurl_media=False
        )
        return response["ok"]
    except SlackApiError as e:
        print(f"Failed to post paper to Slack: {e.response['error']}")
        return False


def save_results_to_file(high_rated_papers: list, query, today, last_week) -> str:
    """
    Save detailed paper results to a markdown file.
    
    Args:
        high_rated_papers: List of (title, data, rating) tuples
        query: Search query used
        today: Today's date
        last_week: Last week's date
        
    Returns:
        str: Path to the saved file
    """
    query_str = ' '.join(query) if isinstance(query, list) else query
    filename = f"papers_{today}.md"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"# PaperFetch Results\n\n")
        f.write(f"**Query:** {query_str}\n\n")
        f.write(f"**Date range:** {last_week} to {today}\n\n")
        f.write(f"**Papers:** {len(high_rated_papers)}\n\n")
        f.write("---\n\n")
        
        for title, data, rating in high_rated_papers:
            url = data.get('url', '')
            journal = data.get('journal', 'Unknown')
            summary = data.get('summary', [])
            abstract = data.get('abstract', '')
            
            # Title with link
            if url:
                f.write(f"## [{title}]({url})\n\n")
            else:
                f.write(f"## {title}\n\n")
            
            f.write(f"**Journal:** {journal} | **Rating:** {rating}/10\n\n")
            
            # Key points
            if summary and isinstance(summary, list):
                f.write("### Key Points\n\n")
                for point in summary:
                    f.write(f"- {point}\n")
                f.write("\n")
            
            # Abstract
            if abstract:
                f.write("### Abstract\n\n")
                f.write(f"{abstract}\n\n")
            
            f.write("---\n\n")
    
    print(f"Detailed results saved to: {filename}")
    return filename


def send_results_to_slack(results: dict, query, today, last_week, config: dict, preview: bool = False) -> int:
    """
    Send paper results to Slack, filtering by minimum rating.
    
    Args:
        results: Dictionary of paper titles to paper data
        query: Search query used (list of terms or single string)
        today: Today's date
        last_week: Last week's date
        config: Configuration dictionary containing Slack settings
        
    Returns:
        int: Number of papers successfully posted
    """
    min_rating = config['slack'].get('min_rating', 7)
    
    # Filter and sort papers by rating
    high_rated_papers = []
    for title, data in results.items():
        if isinstance(data, dict) and isinstance(data.get('interest_rating'), int):
            if data['interest_rating'] >= min_rating:
                high_rated_papers.append((title, data, data['interest_rating']))
    
    # Sort by rating (highest first)
    high_rated_papers.sort(key=lambda x: x[2], reverse=True)
    
    if not high_rated_papers:
        query_str = ' '.join(query) if isinstance(query, list) else query
        print(f"No papers with rating >= {min_rating} to post to Slack")
        _post_summary_message(
            config,
            f"📚 *PaperFetch Results*\n"
            f"Query: {query_str}\n"
            f"Date range: {last_week} to {today}\n"
            f"Papers found: {len(results)}\n"
            f"Papers meeting threshold (≥{min_rating}): 0",
            preview=preview
        )
        return 0
    
    # Save detailed results to file
    save_results_to_file(high_rated_papers, query, today, last_week)
    
    # Post header message
    query_str = ' '.join(query) if isinstance(query, list) else query
    header = (
        f"📚 *PaperFetch Results*\n"
        f"Query: {query_str}\n"
        f"Date range: {last_week} to {today}\n"
        f"Papers with rating ≥{min_rating}: {len(high_rated_papers)} of {len(results)} total\n"
        f"React with 👀 to show interest!"
    )
    _post_summary_message(config, header, preview=preview)
    
    # Post each paper (compact - title and metadata only)
    success_count = 0
    for title, data, rating in high_rated_papers:
        if send_paper_to_slack(title, data, config, preview=preview):
            success_count += 1
            print(f"Posted to Slack (rating {rating}): {title[:50]}...")
        else:
            print(f"Failed to post to Slack: {title[:50]}...")
    
    print(f"\n{'='*80}")
    print(f"SLACK NOTIFICATIONS SENT: {success_count}/{len(high_rated_papers)} papers")
    print(f"{'='*80}")
    
    return success_count


def send_no_llm_processing_slack(
    papers_with_abstracts: dict, 
    query, 
    today, 
    last_week, 
    config: dict, 
    paper_count: int, 
    max_papers_for_llm: int,
    preview: bool = False
) -> bool:
    """
    Send a Slack message explaining that LLM processing was skipped.
    
    Args:
        papers_with_abstracts: Dictionary of paper titles and abstracts
        query: Search query used
        today: Today's date
        last_week: Last week's date
        config: Configuration dictionary
        paper_count: Number of papers found
        max_papers_for_llm: Maximum allowed papers for LLM processing
        
    Returns:
        bool: True if message posted successfully
    """
    query_str = ' '.join(query) if isinstance(query, list) else query
    
    message = (
        f"⚠️ *PaperFetch - LLM Processing Skipped*\n\n"
        f"Found {paper_count} papers, which exceeds the configured limit of {max_papers_for_llm}.\n"
        f"To enable LLM processing, reduce the search scope or increase `max_papers_for_llm` in config.\n\n"
        f"*Query:* {query_str}\n"
        f"*Date range:* {last_week} to {today}\n\n"
        f"*Papers found (titles only):*\n"
    )
    
    # Add paper titles (limit to avoid message being too long)
    paper_lines = []
    for i, (title, paper_data) in enumerate(papers_with_abstracts.items()):
        if i >= 20:  # Limit to 20 papers in the message
            paper_lines.append(f"... and {paper_count - 20} more papers")
            break
        url = paper_data.get('url', '')
        if url:
            paper_lines.append(f"• <{url}|{title}>")
        else:
            paper_lines.append(f"• {title}")
    
    message += "\n".join(paper_lines)
    
    return _post_summary_message(config, message, preview=preview)


def _post_summary_message(config: dict, message: str, preview: bool = False) -> bool:
    """
    Post a summary/header message to Slack.
    
    Args:
        config: Configuration dictionary
        message: Message text to post
        
    Returns:
        bool: True if posted successfully
    """
    if preview:
        print("--- [PREVIEW] Summary Message ---")
        print(message)
        print("-------------------------------")
        return True

    client, channel_id = get_slack_client(config)
    if not client:
        return False
    
    try:
        client.chat_postMessage(
            channel=channel_id,
            text=message,
            unfurl_links=False,
            unfurl_media=False
        )
        return True
    except SlackApiError as e:
        print(f"Failed to post summary to Slack: {e.response['error']}")
        return False
