import os
from flask import Flask, render_template, request, session, Response, stream_with_context
from flask_caching import Cache
from pydantic import BaseModel
from google import genai
import prompts
import random
from datetime import datetime, timedelta
from typing import List, Tuple

CACHE_TIMEOUT = 300

app = Flask(__name__)
app.secret_key = os.getenv('APP_SECRET_KEY')
app.config["SECRET_KEY"] = os.getenv('CACHE_SECRET_KEY')
app.config["CACHE_TYPE"] = "SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"] = CACHE_TIMEOUT

cache = Cache(app)

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

class SearchResult(BaseModel):
    title: str
    meta: str
    url: str
    type: str

class SearchResults(BaseModel):
    items: List[SearchResult]


def generate_random_date() -> Tuple[str, str]:
    start_date = datetime(1995, 1, 1)
    end_date = datetime(2005, 12, 31)
    
    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.days
    random_days = random.randrange(days_between_dates)
    
    random_date = start_date + timedelta(days=random_days)
    return random_date.strftime("%Y-%m-%d"), random_date.strftime("%Y")

def get_meta_prompt(page_type, title, topic):
    if page_type == 'journal':
        return prompts.META_JOURNAL.format(title, topic)
    elif page_type == 'magazine':
        return prompts.META_EZINE.format(title, topic)
    elif page_type == 'forum':
        return prompts.META_FORUM.format(title, topic)
    elif page_type == 'personal':
        return prompts.META_PERSONAL.format(title, topic)
    else:
        return None

def get_webpage_prompt(page_type, title, content):
    if page_type == 'journal':
        prompt = random.choice([
            prompts.JOURNAL_1,
            prompts.JOURNAL_2,
            prompts.JOURNAL_3
            ])
    elif page_type == 'magazine':
        prompt = random.choice([
            prompts.EZINE_1,
            prompts.EZINE_2
            ])
    elif page_type == 'forum':
        prompt = random.choice([
            prompts.FORUM_1
            ])
    elif page_type == 'personal':
        prompt = random.choice([
            prompts.PERSONAL_1,
            prompts.PERSONAL_2
            ])
    else:
        return None
    
    return prompt.format(content, title)

def get_html(text):
    start_marker = "<html"
    end_marker = "</html>"
    start_index = text.find(start_marker)
    if start_index != -1:
        # Find the closing > of the opening html tag
        tag_end = text.find(">", start_index)
        if tag_end != -1:
            end_index = text.find(end_marker) + len(end_marker)
            if end_index != -1:
                return text[start_index:end_index]
    return text


@app.route('/', methods=['GET'])
def home():
    return render_template('index.html')


@app.route('/search', methods=['POST'])
def search():
    topic = request.form['topic']
    
    # Create a cache key based on the topic
    cache_key = f'search_results:{topic}'
    
    # Check if this topic's results are already in the cache
    if cache.has(cache_key):
        # Use cached results
        search_results_json = cache.get(cache_key)
        search_results = SearchResults.model_validate_json(search_results_json).items
        print("Using cached search results for:", topic)
    else:
        # Generate new results
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompts.GEN_RESULTS.format(topic),
            config={
                'response_mime_type': 'application/json',
                'response_schema': SearchResults,
            }
        )
        
        results = response.parsed
        search_results = results.items
        print("Generated new search results for:", topic)
        
        # Store results in cache
        cache.set(cache_key, results.model_dump_json())
    
    # Save the cache key in session to retrieve it later
    session['search_results_key'] = cache_key

    return render_template('search.html', results=search_results)

@app.route('/go', methods=['GET'])
def go():
    url = request.args.get('url')
    
    # Get cache key from session and retrieve results from cache
    cache_key = session.get('search_results_key')
    if not cache_key or not cache.has(cache_key):
        return "Search results expired, please search again", 404
    
    search_results_json = cache.get(cache_key)
    search_results = SearchResults.model_validate_json(search_results_json)
    search_result = next((result for result in search_results.items if result.url == url), None)

    # reset search results to extend timeout
    cache.set(cache_key, search_results_json, timeout=CACHE_TIMEOUT)

    if not search_result:
        return "URL not found in search results", 404
    
    url_key = f'url:{url}'
    if cache.has(url_key):
        return cache.get(url_key)

    metaprompt = get_meta_prompt(search_result.type, search_result.title, search_result.meta)
    
    # Create streaming response
    def generate_html():
        # First yield a basic HTML structure to start with
        yield ''
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Get content generation parameters
        meta_response = client.models.generate_content(
            model='gemini-2.0-flash-lite',
            contents=metaprompt
        )
        gen_prompt = meta_response.text
        prompt = get_webpage_prompt(search_result.type, search_result.title, gen_prompt)
        
        # Stream the response chunks
        html_buffer = ""
        html_started = False
        html_ended = False
        for chunk in client.models.generate_content_stream(
            model='gemini-2.0-flash-lite',
            contents=prompt
        ):
            if html_ended:
                break

            if hasattr(chunk, 'text'):
                chunk_text = chunk.text

                print('In : {}'.format(chunk_text))
                
                if "<html" in chunk_text:
                    start_index = chunk_text.find("<html")
                    chunk_text = chunk_text[start_index:]
                    html_started = True
                elif "</html>" in chunk_text:
                    end_index = chunk_text.find("</html>") + len("</html>")
                    chunk_text = chunk_text[:end_index]
                    html_ended = True
                
                if not html_started:
                    continue

                print('Out: {}'.format(chunk_text))
                html_buffer += chunk_text

                if len(html_buffer) > 20000:
                    break
                
                # Check if we have complete HTML tags to send
                # This is a simple approach - you might need more sophisticated parsing
                yield chunk_text
        
        print("HTML buffer length:", len(html_buffer))
        
        # Cache the final result
        final_html = get_html(html_buffer)
        cache.set(url_key, final_html)
    
    return Response(stream_with_context(generate_html()), mimetype='text/html')

if __name__ == '__main__':
    app.run(debug=True)


