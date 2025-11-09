import os
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from markupsafe import Markup

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def scrape_google_reviews(cottage_url):
    """
    Scrape Google reviews from the cottage's URL.
    Note: This is a simplified version. In production, you'd need to handle Google's dynamic content.
    """
    try:
        response = requests.get(cottage_url)
        soup = BeautifulSoup(response.text, 'html.parser')
        # This is a simplified example. You'd need to adjust the selectors based on the actual structure
        reviews = soup.find_all('div', class_='review')
        review_texts = []
        for review in reviews:
            text = review.get_text().strip()
            if text:
                review_texts.append(text)
        return review_texts
    except Exception as e:
        print(f"Error scraping reviews: {e}")
        return []

def generate_review_summary(cottage_name, reviews):
    """
    Generate an AI summary of the reviews using OpenAI's API
    """
    if not reviews:
        return "No reviews available for AI summary generation."
    
    # Combine reviews into a single text
    reviews_text = "\n".join(reviews)
    
    try:
        # Create the prompt for the AI
        prompt = f"""Please analyze these reviews for {cottage_name} and create a comprehensive HTML summary.
        Focus on common themes, highlights, and potential concerns.
        Format the response in HTML with proper tags for structure.
        Reviews:
        {reviews_text}"""

        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4",  # or "gpt-3.5-turbo" for a more economical option
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes vacation cottage reviews and creates structured, balanced summaries."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )

        # Get the generated summary
        summary = response.choices[0].message.content

        # Ensure it's safe HTML and return
        return Markup(summary)

    except Exception as e:
        print(f"Error generating AI summary: {e}")
        return "Error generating AI review summary. Please try again later."

def update_cottage_review_summary(db, cottage_id):
    """
    Update the AI review summary for a specific cottage
    """
    try:
        # Get cottage details
        cursor = db.cursor()
        cottage = cursor.execute(
            'SELECT name, url FROM cottages WHERE id = ?',
            (cottage_id,)
        ).fetchone()

        if not cottage:
            return False, "Cottage not found"

        # Scrape reviews
        reviews = scrape_google_reviews(cottage['url'])
        
        # Generate summary
        summary = generate_review_summary(cottage['name'], reviews)

        # Update database
        cursor.execute(
            'UPDATE cottages SET ai_review_summary = ? WHERE id = ?',
            (summary, cottage_id)
        )
        db.commit()

        return True, "Review summary updated successfully"

    except Exception as e:
        return False, f"Error updating review summary: {e}"