"""
Slack notification module for PaperFetch.

Sends paper notifications via Slack webhooks. Each high-relevance paper
(rating >= min_rating) is posted as a separate message to enable individual
emoji reactions for interest signaling.
"""

import httpx
from datetime import datetime


def send_paper_to_slack(paper_title: str, paper_data: dict, config: dict) -> bool:
    """
    Post a single paper notification to Slack.
    
    Args:
        paper_title: Title of the paper
        paper_data: Dictionary containing paper details (url, journal, interest_rating, summary)
        config: Configuration dictionary containing Slack settings
        
    Returns:
        bool: True if message posted successfully, False otherwise
    """
    webhook_url = config['slack']['webhook_url']
    
    # Build the message
    url = paper_data.get('url', '')
    journal = paper_data.get('journal', 'Unknown Journal')
    rating = paper_data.get('interest_rating', 'N/A')
    summary = paper_data.get('summary', [])
    abstract = paper_data.get('abstract', '')
    
    # Rating emoji based on score
    if isinstance(rating, int):
        if rating >= 9:
            rating_emoji = "🔥"
        elif rating >= 7:
            rating_emoji = "⭐"
        else:
            rating_emoji = "📊"
    else:
        rating_emoji = "❓"
    
    # Format title as link
    if url:
        title_text = f"<{url}|{paper_title}>"
    else:
        title_text = paper_title
    
    # Build key points if available
    key_points = ""
    if summary and isinstance(summary, list):
        key_points = "\n".join(f"• {point}" for point in summary)
    
    # Build the message text
    message_lines = [
        f"📄 *{title_text}*",
        f"🏷️ {journal} | {rating_emoji} Interest: {rating}/10",
    ]
    
    if key_points:
        message_lines.append("")
        message_lines.append("*Key Points:*")
        message_lines.append(key_points)
    
    # Add abstract in code block for collapsibility
    if abstract:
        message_lines.append("")
        message_lines.append("*Abstract:*")
        message_lines.append(f"```{abstract}```")
    
    message_text = "\n".join(message_lines)
    
    # Post to Slack
    payload = {
        "text": message_text,
        "unfurl_links": False,
        "unfurl_media": False
    }
    
    try:
        response = httpx.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Failed to post paper to Slack: {e}")
        return False


def send_results_to_slack(results: dict, query, today, last_week, config: dict) -> int:
    """
    Send paper results to Slack, filtering by minimum rating.
    
    Posts one message per paper with rating >= min_rating from config.
    
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
        # Post a summary message
        _post_summary_message(
            config,
            f"📚 *PaperFetch Results*\n"
            f"Query: {query_str}\n"
            f"Date range: {last_week} to {today}\n"
            f"Papers found: {len(results)}\n"
            f"Papers meeting threshold (≥{min_rating}): 0"
        )
        return 0
    
    # Post header message
    query_str = ' '.join(query) if isinstance(query, list) else query
    header = (
        f"📚 *PaperFetch Results*\n"
        f"Query: {query_str}\n"
        f"Date range: {last_week} to {today}\n"
        f"Papers with rating ≥{min_rating}: {len(high_rated_papers)} of {len(results)} total\n"
        f"React with 👀 to show interest!"
    )
    _post_summary_message(config, header)
    
    # Post each paper
    success_count = 0
    for title, data, rating in high_rated_papers:
        if send_paper_to_slack(title, data, config):
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
    max_papers_for_llm: int
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
    
    return _post_summary_message(config, message)


def _post_summary_message(config: dict, message: str) -> bool:
    """
    Post a summary/header message to Slack.
    
    Args:
        config: Configuration dictionary
        message: Message text to post
        
    Returns:
        bool: True if posted successfully
    """
    webhook_url = config['slack']['webhook_url']
    
    payload = {
        "text": message,
        "unfurl_links": False,
        "unfurl_media": False
    }
    
    try:
        response = httpx.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Failed to post summary to Slack: {e}")
        return False
