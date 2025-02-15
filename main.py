import os
from flask import Flask, render_template, request, session
from flask_caching import Cache
from pydantic import BaseModel
from google import genai
import prompts
import random
from datetime import datetime, timedelta
from typing import List, Tuple

app = Flask(__name__)
app.secret_key = os.getenv('APP_SECRET_KEY')
app.config["SECRET_KEY"] = os.getenv('CACHE_SECRET_KEY')
app.config["CACHE_TYPE"] = "SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"] = 300

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
            prompts.PERSONAL_1
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
    print(search_results)

    session['search_results'] = results.model_dump_json()

    return render_template('search.html', results=search_results)


@app.route('/go', methods=['GET'])
def go():
    url = request.args.get('url')
    search_results = SearchResults.model_validate_json(session['search_results'])
    search_result = next(result for result in search_results.items if result.url == url)
    print(search_result)

    all_keys = list(cache.cache._cache.keys())  # Access internal dict
    print("Cached keys:", all_keys)

    url_key = f'url:{url}'
    if cache.has(url_key):
        return cache.get(url_key)

    metaprompt = get_meta_prompt(search_result.type, search_result.title, search_result.meta)

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model='gemini-2.0-flash-lite-preview-02-05',
        contents=metaprompt
    )

    gen_prompt = response.text
    
    prompt = get_webpage_prompt(search_result.type, search_result.title, gen_prompt)
    print(prompt)
    
    response = client.models.generate_content(
        model='gemini-2.0-flash-lite-preview-02-05',
        contents=prompt
    )
    
    result = response.text

    html = get_html(result)
    cache.set(url_key, html)

    return html

if __name__ == '__main__':
    app.run(debug=True)


