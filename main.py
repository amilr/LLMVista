import os
import base64
import hashlib
import html
import logging
import re
import time
from threading import Lock, Thread
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, render_template, request, session, Response, stream_with_context, redirect, url_for
from flask_caching import Cache
from pydantic import BaseModel
from google import genai
from dotenv import load_dotenv
import prompts
from retro_images import encode_period_image
import random
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

CACHE_TIMEOUT = 600
MAX_FOLLOW_DEPTH = 5
TEXT_MODEL = 'gemini-3.6-flash'
IMAGE_MODEL = 'gemini-nano-banana-2.1'
SEARCH_GENERATION_CONFIG = {'thinking_level': 'minimal'}
HTML_GENERATION_CONFIG = {'thinking_level': 'minimal'}
IMAGE_GENERATION_CONFIG = {'thinking_level': 'minimal'}

load_dotenv()

LOG_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
LOG_FILE = os.path.join(LOG_DIRECTORY, 'llmvista.log')
LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'

os.makedirs(LOG_DIRECTORY, exist_ok=True)
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format=LOG_FORMAT,
)
logger = logging.getLogger('llmvista')
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO').upper())
if not any(getattr(handler, 'baseFilename', None) == LOG_FILE for handler in logger.handlers):
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=3,
        encoding='utf-8',
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(file_handler)

app = Flask(__name__)
app.config['SECRET_KEY'] = (
    os.getenv('APP_SECRET_KEY') or os.getenv('CACHE_SECRET_KEY')
)
app.config["CACHE_TYPE"] = "SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"] = CACHE_TIMEOUT

cache = Cache(app)
image_jobs = {}
image_jobs_lock = Lock()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

class SearchResult(BaseModel):
    title: str
    meta: str
    url: str
    type: str

class SearchResults(BaseModel):
    items: List[SearchResult]


class PageContext(SearchResult):
    page_id: str
    parent_id: Optional[str] = None
    depth: int = 0
    link_label: Optional[str] = None
    style_id: Optional[str] = None


def page_context_cache_key(page_id):
    return 'page_context:{}'.format(page_id)


def page_html_cache_key(page_id):
    return 'page_html:{}'.format(page_id)


def make_page_id(*parts):
    return hashlib.sha256('\n'.join(parts).encode('utf-8')).hexdigest()


def cache_page_context(page_context):
    cache.set(
        page_context_cache_key(page_context.page_id),
        page_context.model_dump_json(),
        timeout=CACHE_TIMEOUT,
    )


def get_page_context(page_id):
    serialized = cache.get(page_context_cache_key(page_id))
    return PageContext.model_validate_json(serialized) if serialized else None


def clean_follow_value(value, limit):
    value = re.sub(r'\s+', ' ', value or '').strip()
    return value[:limit]


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

def get_webpage_prompt(page_type, title, content, style_id=None, image_treatment=None):
    style_ids = prompts.STYLE_IDS_BY_PAGE_TYPE.get(page_type)
    if not style_ids:
        return None
    style_id = style_id or random.choice(style_ids)
    return prompts.build_webpage_prompt(page_type, title, content, style_id, image_treatment)



def get_loading_shell(title):
    safe_title = html.escape(title)
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{}</title>
  <style>
    body {{ margin: 0; background: #f5f5f5; color: #222; font-family: Arial, sans-serif; }}
    #llmvista-loading {{ padding: 28px; text-align: center; }}
    #llmvista-loading strong {{ display: block; margin-bottom: 8px; }}
    .llmvista-spinner {{ width: 22px; height: 22px; margin: 0 auto; border: 3px solid #ccc; border-top-color: #555; border-radius: 50%; animation: llmvista-spin .8s linear infinite; }}
    @keyframes llmvista-spin {{ to {{ transform: rotate(360deg); }} }}
  </style>
</head>
<body>
  <div id="llmvista-loading"><strong>Building this page…</strong><div class="llmvista-spinner"></div></div>
  <main id="llmvista-page">
""".format(safe_title)


LOADING_COMPLETE_SCRIPT = """<script>
  document.getElementById('llmvista-loading')?.remove();
</script>
"""
PAGE_SHELL_END = "</main></body></html>"


def get_follow_links_script(page_id):
    return """<script>
document.addEventListener('click', (event) => {
  const link = event.target.closest?.('a');
  if (!link || !link.closest('#llmvista-page') || link.dataset.linkKind === 'ui') return;
  const href = (link.getAttribute('href') || '').trim();
  if (/^(mailto:|tel:|javascript:|data:)/i.test(href)) return;
  if (href.startsWith('#') && href.length > 1) {
    let anchor = href.slice(1);
    try { anchor = decodeURIComponent(anchor); } catch (_) {}
    if (document.getElementById(anchor) || document.getElementsByName(anchor).length) return;
  }
  if (!href && !link.dataset.linkKind) return;

  const label = (link.textContent || link.getAttribute('title') || href).trim();
  if (!label) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const query = new URLSearchParams({
    parent: '__PAGE_ID__',
    label: label.slice(0, 160),
    target: href.slice(0, 300),
    kind: link.dataset.linkKind || 'related',
  });
  window.location.assign('/follow?' + query.toString());
}, true);
</script>
""".replace('__PAGE_ID__', page_id)


def get_image_filename(search_result):
    treatment = prompts.get_image_treatment(search_result.style_id, search_result.url)
    extension = 'png' if prompts.IMAGE_TREATMENTS[treatment]['format'] == 'PNG' else 'jpg'
    return '{}.{}'.format(
        hashlib.sha256('\n'.join((
            search_result.url, search_result.style_id or '', IMAGE_MODEL,
            prompts.IMAGE_POLICY_VERSION, treatment,
        )).encode('utf-8')).hexdigest(), extension,
    )


def get_image_url(image_filename):
    return '{}/generated/{}'.format(app.static_url_path or '/static', image_filename)


def get_image_loader_script(image_filename, status_url, image_treatment='compressed'):
    safe_status_url = html.escape(status_url, quote=True)
    safe_image_url = html.escape(get_image_url(image_filename), quote=True)
    asset = prompts.IMAGE_TREATMENTS[image_treatment]
    image_style = 'display:block;width:{}px;max-width:100%;height:auto;margin:0 auto;'.format(
        asset['display_width']
    )
    if image_treatment == 'pixel':
        image_style += 'image-rendering:pixelated;'
    script = """<script>
(() => {
  const statusUrl = '__STATUS_URL__';
  const imageUrl = '__IMAGE_URL__';
  const checkImage = async () => {
    const slot = document.getElementById('llmvista-image-slot');
    if (!slot) {
      window.setTimeout(checkImage, 100);
      return;
    }
    try {
      const response = await fetch(statusUrl, { cache: 'no-store' });
      const result = await response.json();
      if (result.status === 'ready') {
        slot.innerHTML = '<img src="' + imageUrl + '" alt="__IMAGE_ALT__" style="__IMAGE_STYLE__">';
        return;
      }
      if (result.status === 'failed') {
        slot.remove();
        return;
      }
    } catch (error) {
      console.debug('Image status check failed', error);
    }
    window.setTimeout(checkImage, 1000);
  };
  checkImage();
})();
</script>
"""
    return script.replace('__STATUS_URL__', safe_status_url).replace(
        '__IMAGE_URL__', safe_image_url
    ).replace('__IMAGE_STYLE__', image_style).replace(
        '__IMAGE_ALT__', 'Generated ' + asset['name']
    )


def get_image_slot_fallback():
    return """<script>
  if (!document.getElementById('llmvista-image-slot')) {
    const slot = document.createElement('aside');
    slot.id = 'llmvista-image-slot';
    slot.textContent = 'Generated illustration';
    slot.style.cssText = 'margin:18px auto;max-width:720px;text-align:center;color:#666;font:12px Arial,sans-serif;';
    document.getElementById('llmvista-page').append(slot);
  }
</script>
"""


def generate_page_image(client, search_result, content, image_filename=None):
    """Generate and save one local illustration for a generated page.

    Returning a local static URL means the HTML model does not need to invent or
    depend on an external image URL.
    """
    started_at = time.perf_counter()
    image_filename = image_filename or get_image_filename(search_result)
    image_directory = os.path.join(app.static_folder, 'generated')
    image_path = os.path.join(image_directory, image_filename)

    if os.path.exists(image_path):
        elapsed = time.perf_counter() - started_at
        logger.info('image cache hit url=%s duration=%.2fs', search_result.url, elapsed)
    else:
        logger.info('image generation started url=%s model=%s', search_result.url, IMAGE_MODEL)
        image_prompt = prompts.build_image_prompt(
            search_result.type, search_result.title, content, search_result.style_id,
            prompts.get_image_treatment(search_result.style_id, search_result.url),
        )

        try:
            image_response = client.interactions.create(
                model=IMAGE_MODEL,
                input=image_prompt,
                generation_config=IMAGE_GENERATION_CONFIG,
                response_format={
                    'type': 'image',
                    'mime_type': 'image/jpeg',
                    'aspect_ratio': '4:3',
                    'image_size': '1K',
                },
                store=False,
            )
            image_data = image_response.output_image.data
            if not image_data:
                return None, time.perf_counter() - started_at

            treatment = prompts.get_image_treatment(search_result.style_id, search_result.url)
            image_bytes = encode_period_image(base64.b64decode(image_data), treatment)

            os.makedirs(image_directory, exist_ok=True)
            with open(image_path, 'wb') as image_file:
                image_file.write(image_bytes)
        except Exception as error:
            # A page remains usable if image generation is unavailable or blocked.
            elapsed = time.perf_counter() - started_at
            logger.exception(
                'image generation failed url=%s duration=%.2fs error=%s',
                search_result.url, elapsed, error,
            )
            return None, elapsed

        elapsed = time.perf_counter() - started_at
        logger.info('image generation finished url=%s duration=%.2fs', search_result.url, elapsed)

    return get_image_url(image_filename), elapsed


def generate_page_image_in_background(search_result, content, image_filename):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        image_url, duration = generate_page_image(
            client, search_result, content, image_filename=image_filename
        )
        status = 'ready' if image_url else 'failed'
    except Exception:
        logger.exception('background image job failed url=%s', search_result.url)
        status = 'failed'
        duration = None

    with image_jobs_lock:
        image_jobs[image_filename] = {'status': status}
    logger.info(
        'background image job finished url=%s status=%s duration=%s',
        search_result.url,
        status,
        '{:.2f}s'.format(duration) if duration is not None else 'unknown',
    )


def start_page_image_generation(search_result, content):
    image_filename = get_image_filename(search_result)
    image_path = os.path.join(app.static_folder, 'generated', image_filename)
    if os.path.exists(image_path):
        return image_filename

    with image_jobs_lock:
        job = image_jobs.get(image_filename)
        if job and job['status'] == 'pending':
            return image_filename
        image_jobs[image_filename] = {'status': 'pending'}

    Thread(
        target=generate_page_image_in_background,
        args=(search_result, content, image_filename),
        daemon=True,
        name='page-image-{}'.format(image_filename[:8]),
    ).start()
    logger.info('background image job started url=%s model=%s', search_result.url, IMAGE_MODEL)
    return image_filename

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
    request_started_at = time.perf_counter()
    topic = request.form['topic']

    if not topic.strip():
        return redirect(url_for('home'))
    
    # Create a cache key based on the topic
    cache_key = f'search_results:{topic}'
    
    # Check if this topic's results are already in the cache
    if cache.has(cache_key):
        # Use cached results
        search_results_json = cache.get(cache_key)
        search_results = SearchResults.model_validate_json(search_results_json).items
        logger.info('search cache hit topic=%r duration=%.2fs', topic, time.perf_counter() - request_started_at)
    else:
        # Generate new results
        client = genai.Client(api_key=GEMINI_API_KEY)
        llm_started_at = time.perf_counter()
        logger.info('search generation started topic=%r model=%s', topic, TEXT_MODEL)
        interaction = client.interactions.create(
            model=TEXT_MODEL,
            input=prompts.GEN_RESULTS.format(topic),
            response_format=[{
                'type': 'text',
                'mime_type': 'application/json',
                'schema': SearchResults.model_json_schema(),
            }],
            store=False,
            generation_config=SEARCH_GENERATION_CONFIG,
        )
        results = SearchResults.model_validate_json(interaction.output_text)
        search_results = results.items
        logger.info(
            'search generation finished topic=%r duration=%.2fs total=%.2fs',
            topic,
            time.perf_counter() - llm_started_at,
            time.perf_counter() - request_started_at,
        )
        
        # Store results in cache
        cache.set(cache_key, results.model_dump_json())
    
    # Save the cache key in session to retrieve it later
    session['search_results_key'] = cache_key

    return render_template('search.html', results=search_results)


@app.route('/image-status/<image_filename>', methods=['GET'])
def image_status(image_filename):
    if not re.fullmatch(r'[0-9a-f]{64}\.(?:jpg|png)', image_filename):
        return jsonify({'status': 'failed'}), 404

    image_path = os.path.join(app.static_folder, 'generated', image_filename)
    if os.path.exists(image_path):
        return jsonify({'status': 'ready', 'url': get_image_url(image_filename)})

    with image_jobs_lock:
        job = image_jobs.get(image_filename)
    if job and job['status'] == 'failed':
        return jsonify({'status': 'failed'})
    return jsonify({'status': 'pending'}), 202

@app.route('/go', methods=['GET'])
def go():
    url = request.args.get('url')
    cache_key = session.get('search_results_key')
    if not cache_key or not cache.has(cache_key):
        return "Search results expired, please search again", 404

    search_results_json = cache.get(cache_key)
    search_results = SearchResults.model_validate_json(search_results_json)
    search_result = next((result for result in search_results.items if result.url == url), None)
    cache.set(cache_key, search_results_json, timeout=CACHE_TIMEOUT)
    if not search_result:
        return "URL not found in search results", 404

    page_id = make_page_id('root', search_result.url)
    page_context = get_page_context(page_id) or PageContext(
        **search_result.model_dump(),
        page_id=page_id,
    )
    cache_page_context(page_context)
    return render_page(page_context)


@app.route('/follow', methods=['GET'])
def follow():
    parent_id = request.args.get('parent', '')
    link_label = clean_follow_value(request.args.get('label', ''), 160)
    link_target = clean_follow_value(request.args.get('target', ''), 300)
    link_kind = clean_follow_value(request.args.get('kind', 'related'), 32).lower()
    if not re.fullmatch(r'[0-9a-f]{64}', parent_id) or not link_label:
        return 'Invalid link', 400

    parent = get_page_context(parent_id)
    if not parent:
        return 'This page context has expired. Please search again.', 404
    if parent.depth >= MAX_FOLLOW_DEPTH:
        return 'You have reached the end of this link trail. Please start a new search.', 400

    child_id = make_page_id(parent.page_id, link_kind, link_label, link_target)
    child = get_page_context(child_id)
    if not child:
        child_type = {
            'profile': 'friendster',
            'friendster': 'friendster',
            'forum': 'forum',
            'journal': 'journal',
            'magazine': 'magazine',
            'personal': 'personal',
        }.get(link_kind, parent.type)
        child = PageContext(
            page_id=child_id,
            parent_id=parent.page_id,
            depth=parent.depth + 1,
            link_label=link_label,
            title=link_label,
            meta=(
                'A related fictional page reached from "{}". The visitor followed '
                'the link "{}" ({}) from {}. Preserve relevant people, places, '
                'events, and era, but make this page a distinct destination.'
            ).format(parent.title, link_label, link_target or 'linked page', parent.meta),
            url='follow://{}'.format(child_id),
            type=child_type,
        )
        cache_page_context(child)
        logger.info(
            'follow link created parent=%s child=%s kind=%s label=%r',
            parent.page_id[:8], child.page_id[:8], link_kind, link_label,
        )
    else:
        logger.info('follow link context cache hit child=%s', child.page_id[:8])
    return render_page(child)


def render_page(page_context):
    request_started_at = time.perf_counter()
    search_result = page_context
    url = page_context.url
    url_key = page_html_cache_key(page_context.page_id)
    if cache.has(url_key):
        logger.info('page cache hit page=%s duration=%.2fs', page_context.page_id[:8], time.perf_counter() - request_started_at)
        return cache.get(url_key)

    # Persist one design so HTML, background images, and later renders agree.
    if not page_context.style_id:
        page_context.style_id = random.choice(prompts.STYLE_IDS_BY_PAGE_TYPE[page_context.type])
    cache_page_context(page_context)

    # Create streaming response
    def generate_html():
        page_started_at = time.perf_counter()
        # Send immediately so the browser can render before model calls finish.
        loading_shell = get_loading_shell(search_result.title)
        yield loading_shell
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # The HTML model writes the page content directly from this brief. This
        # replaces the former separate article-generation call.
        page_brief = search_result.meta
        image_treatment = prompts.get_image_treatment(search_result.style_id, search_result.url)
        logger.info('page composition started url=%s', url)
        prompt = get_webpage_prompt(
            search_result.type, search_result.title, page_brief, search_result.style_id,
            image_treatment,
        )
        image_filename = start_page_image_generation(search_result, page_brief)
        image_status_url = url_for('image_status', image_filename=image_filename)
        image_loader_script = get_image_loader_script(image_filename, image_status_url, image_treatment)
        image_slot_fallback = get_image_slot_fallback()
        follow_links_script = get_follow_links_script(page_context.page_id)
        # The visible loading shell has done its job; reveal generated content.
        yield LOADING_COMPLETE_SCRIPT
        yield image_loader_script
        yield follow_links_script
        
        # Stream the response chunks
        html_buffer = ""
        html_started_at = time.perf_counter()
        first_html_token_duration = None
        logger.info('html generation started url=%s model=%s', url, TEXT_MODEL)
        for event in client.interactions.create(
            model=TEXT_MODEL,
            input=prompt,
            stream=True,
            store=False,
            generation_config=HTML_GENERATION_CONFIG,
        ):
            if event.event_type == 'step.delta' and event.delta:
                if getattr(event.delta, 'type', None) != 'text':
                    continue

                chunk_text = getattr(event.delta, 'text', None)
                if not chunk_text:
                    continue

                if first_html_token_duration is None:
                    first_html_token_duration = time.perf_counter() - html_started_at
                    logger.info('html first token url=%s duration=%.2fs', url, first_html_token_duration)

                logger.debug('html stream chunk received url=%s chars=%d', url, len(chunk_text))
                
                # The prompt asks for a fragment. Strip document wrappers as a
                # safeguard if a model ignores that instruction.
                chunk_text = re.sub(
                    r'</?(?:!doctype|html|head|body)[^>]*>',
                    '',
                    chunk_text,
                    flags=re.IGNORECASE,
                ).replace('```html', '').replace('```HTML', '').replace('```', '')

                if not chunk_text:
                    continue

                html_buffer += chunk_text

                # Let the model finish its fragment, including all closing tags.
                yield chunk_text

        # Use a footer slot only when the model omitted the requested placement.
        yield image_slot_fallback
        yield PAGE_SHELL_END
        
        html_duration = time.perf_counter() - html_started_at
        timings = {
            'html_stream': html_duration,
        }
        slowest_step, slowest_duration = max(timings.items(), key=lambda item: item[1])
        logger.info(
            'page generation finished url=%s total=%.2fs image=background '
            'html_stream=%.2fs first_html_token=%s slowest=%s(%.2fs) html_bytes=%d',
            url,
            time.perf_counter() - page_started_at,
            html_duration,
            '{:.2f}s'.format(first_html_token_duration) if first_html_token_duration is not None else 'none',
            slowest_step,
            slowest_duration,
            len(html_buffer),
        )
        
        # Cache a complete document so repeat visits return immediately.
        final_html = (
            loading_shell + LOADING_COMPLETE_SCRIPT + image_loader_script + follow_links_script + html_buffer
            + image_slot_fallback + PAGE_SHELL_END
        )
        cache.set(url_key, final_html)
    
    return Response(
        stream_with_context(generate_html()),
        mimetype='text/html',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )

if __name__ == '__main__':
    app.run(debug=True)

    
  
