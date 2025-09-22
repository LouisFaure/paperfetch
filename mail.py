import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

def send_results_email(results, query, today, last_week, config):
    """
    Format research results and send them via email.
    
    Args:
        results (dict): Processed paper results with summaries and ratings
        query (str): Search query used
        today (date): Today's date
        last_week (date): Last week's date
        config (dict): Configuration dictionary containing email settings
        
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    def format_email_content(results, query, today, last_week, config):
        """Format the research results into HTML email content. Includes researcher interests from config if present."""
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; margin-top: 30px; }}
                .paper {{ margin-bottom: 30px; padding: 15px; border: 1px solid #ecf0f1; border-radius: 5px; }}
                .title {{ font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }}
                .title a {{ color: #2c3e50; text-decoration: none; border-bottom: 1px dotted #3498db; }}
                .title a:hover {{ color: #3498db; text-decoration: none; border-bottom: 1px solid #3498db; }}
                .interest {{ background-color: #3498db; color: white; padding: 3px 8px; border-radius: 3px; font-size: 12px; margin-bottom: 10px; display: inline-block; }}
                .bullet-points {{ margin-left: 20px; }}
                .bullet-points li {{ margin-bottom: 5px; line-height: 1.4; }}
                .summary {{ margin-top: 15px; }}
                .query-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ecf0f1; font-size: 12px; color: #7f8c8d; }}
            </style>
        </head>
        <body>
            <h1>PaperFetch Results</h1>
            
            <div class="query-info">
                <strong>Search Query:</strong> {query}<br>
                <strong>Date Range:</strong> {last_week} to {today}<br>
                <strong>Papers Found:</strong> {len(results)}
            </div>
        """
        
        # Sort papers by interest rating (highest first)
        sorted_papers = []
        for title, data in results.items():
            if isinstance(data, dict) and 'interest_rating' in data:
                if isinstance(data['interest_rating'], int):
                    sorted_papers.append((title, data, data['interest_rating']))
                else:
                    # Handle failed ratings by putting them at the end
                    sorted_papers.append((title, data, -1))
            else:
                # Handle papers without proper structure
                sorted_papers.append((title, data, -1))
        
        # Sort by interest rating (descending)
        sorted_papers.sort(key=lambda x: x[2], reverse=True)
        
        for title, data, rating in sorted_papers:
            html_content += f'<div class="paper">'
            
            # Make title clickable if URL is available
            if isinstance(data, dict) and data.get('url'):
                html_content += f'<div class="title"><a href="{data["url"]}" target="_blank">{title}</a></div>'
            else:
                html_content += f'<div class="title">{title}</div>'
            
            if isinstance(data, dict):
                # Display interest rating
                if isinstance(data.get('interest_rating'), int):
                    rating_color = "#e74c3c" if rating < 4 else "#f39c12" if rating < 7 else "#27ae60"
                    html_content += f'<div class="interest" style="background-color: {rating_color};">Interest Rating: {rating}/10</div>'
                else:
                    html_content += f'<div class="interest" style="background-color: #95a5a6;">Interest Rating: {data.get("interest_rating", "N/A")}</div>'
                
                # Display bullet points
                if 'summary' in data and isinstance(data['summary'], list):
                    html_content += '<div class="summary"><strong>Key Points:</strong></div>'
                    html_content += '<ul class="bullet-points">'
                    for point in data['summary']:
                        html_content += f'<li>{point}</li>'
                    html_content += '</ul>'
                else:
                    html_content += f'<div class="summary">Summary not available</div>'
            else:
                # Handle error cases
                html_content += f'<div class="summary" style="color: #e74c3c;">{data}</div>'
            
            html_content += '</div>'
        
        # Add researcher interests info if present in config
        researcher_interests = config.get('search', {}).get('researcher_interests')
        researcher_html = f"<br><strong>Researcher interests used for rating:</strong> {researcher_interests}" if researcher_interests else ""
        
        html_content += f"""
            <div class="footer">
                Generated by PaperFetch on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{researcher_html}
            </div>
        </body>
        </html>
        """
        
        return html_content

    def send_email(subject, html_content, config):
        """Send an email with the formatted results."""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = config['email']['sender_email']
            msg['To'] = config['email']['recipient_email']
            msg['Subject'] = subject
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Connect to server and send email
            with smtplib.SMTP(config['email']['smtp_server'], config['email']['smtp_port']) as server:
                server.starttls()
                server.login(config['email']['sender_email'], config['email']['sender_password'])
                server.send_message(msg)
            
            print(f"Email sent successfully to {config['email']['recipient_email']}")
            return True
            
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

    # Check if there are valid results to email
    if results and any(isinstance(data, dict) for data in results.values()):
        # Create email subject with query and date
        subject = f"{config['email']['subject_prefix']}: {query} ({today})"
        
        # Format email content (pass config so formatter can include researcher_interests)
        html_content = format_email_content(results, query, today, last_week, config)
        
        # Send email
        email_sent = send_email(subject, html_content, config)
        
        if email_sent:
            print("\n" + "="*80)
            print("EMAIL SENT SUCCESSFULLY!")
            print("="*80)
        else:
            print("\n" + "="*80)
            print("EMAIL SENDING FAILED - Check your email configuration")
            print("="*80)
            print("\nFormatted results preview:")
            print(f"Subject: {subject}")
            print("HTML content generated successfully")
        
        return email_sent
    else:
        print("\n" + "="*80)
        print("NO VALID RESULTS TO EMAIL")
        print("="*80)
        return False

def send_no_llm_processing_email(papers_with_abstracts, query, today, last_week, config, paper_count, max_papers_for_llm):
    """
    Send an email explaining that LLM processing was skipped due to too many papers.
    
    Args:
        papers_with_abstracts (dict): Dictionary of paper titles and abstracts
        query (str): Search query used
        today (date): Today's date
        last_week (date): Last week's date
        config (dict): Configuration dictionary containing email settings
        paper_count (int): Number of papers found
        max_papers_for_llm (int): Maximum allowed papers for LLM processing
    """
    def format_no_llm_email_content(papers_with_abstracts, query, today, last_week, paper_count, max_papers_for_llm, config):
        """Format email content when LLM processing is skipped. Includes researcher_interests if present in config."""
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                .warning {{ background-color: #f39c12; color: white; padding: 15px; border-radius: 5px; margin: 20px 0; }}
                .query-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .paper-list {{ margin: 20px 0; }}
                .paper-title {{ margin: 10px 0; padding: 8px; background-color: #ecf0f1; border-radius: 3px; }}
                .paper-title a {{ color: #2c3e50; text-decoration: none; }}
                .footer {{ margin-top: 30px; padding-top: 15px; border-top: 1px solid #ecf0f1; font-size: 12px; color: #7f8c8d; }}
            </style>
        </head>
        <body>
            <h1>PaperFetch Results - LLM Processing Skipped</h1>
            
            <div class="warning">
                <strong>⚠️ LLM Processing Skipped</strong><br>
                Found {paper_count} papers, which exceeds the configured limit of {max_papers_for_llm} papers for LLM processing.<br>
                To enable LLM processing, either reduce the search scope or increase the 'max_papers_for_llm' value in your config.toml file.
            </div>
            
            <div class="query-info">
                <strong>Search Query:</strong> {query}<br>
                <strong>Date Range:</strong> {last_week} to {today}<br>
                <strong>Papers Found:</strong> {paper_count}<br>
                <strong>LLM Processing Limit:</strong> {max_papers_for_llm}
            </div>
            
            <h2>Found Papers (Titles Only)</h2>
            <div class="paper-list">
        """
        
        # List all paper titles with URLs if available
        for title, paper_data in papers_with_abstracts.items():
            if paper_data.get('url'):
                html_content += f'<div class="paper-title"><a href="{paper_data["url"]}" target="_blank">{title}</a></div>'
            else:
                html_content += f'<div class="paper-title">{title}</div>'
        
        # Add researcher interests info if present in config
        researcher_interests = config.get('search', {}).get('researcher_interests')
        researcher_html = f"<br><strong>Researcher interests used for rating:</strong> {researcher_interests}" if researcher_interests else ""
        
        html_content += f"""
            </div>
            
            <div class="footer">
                Generated by PaperFetch on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                LLM processing was skipped to prevent excessive API usage.{researcher_html}
            </div>
        </body>
        </html>
        """
        
        return html_content

    def send_email(subject, html_content, config):
        """Send an email with the formatted results."""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = config['email']['sender_email']
            msg['To'] = config['email']['recipient_email']
            msg['Subject'] = subject
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Connect to server and send email
            with smtplib.SMTP(config['email']['smtp_server'], config['email']['smtp_port']) as server:
                server.starttls()
                server.login(config['email']['sender_email'], config['email']['sender_password'])
                server.send_message(msg)
            
            print(f"Email sent successfully to {config['email']['recipient_email']}")
            return True
            
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False

    # Create email subject
    subject = f"{config['email']['subject_prefix']}: LLM Skipped - {paper_count} papers found ({query}) ({today})"
    
    # Format email content
    html_content = format_no_llm_email_content(papers_with_abstracts, query, today, last_week, paper_count, max_papers_for_llm, config)
    
    # Send email
    email_sent = send_email(subject, html_content, config)
    
    if email_sent:
        print("\n" + "="*80)
        print("EMAIL SENT SUCCESSFULLY!")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("EMAIL SENDING FAILED - Check your email configuration")
        print("="*80)
    
    return email_sent
