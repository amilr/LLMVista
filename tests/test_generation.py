"""Check style propagation and complete streaming without API calls."""
import ast
import base64
import hashlib
import html
from io import BytesIO
import logging
from pathlib import Path
import random
import re
import tempfile
import time
from types import SimpleNamespace
import unittest

import prompts
from PIL import Image
from retro_images import encode_period_image


class FakeCache:
    def __init__(self):
        self.values = {}

    def has(self, key):
        return key in self.values

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, **kwargs):
        self.values[key] = value


def functions_from_main(*names, **dependencies):
    source = Path(__file__).resolve().parents[1] / 'main.py'
    tree = ast.parse(source.read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = dict(dependencies)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace


def page(style_id=None):
    return SimpleNamespace(
        page_id='a' * 64, title='Jenny and her music', meta='A fictional music fan.',
        url='https://fictional.example/jenny', type='personal', style_id=style_id,
    )


class GenerationTests(unittest.TestCase):
    def test_each_style_builds_consistent_html_and_image_instructions(self):
        for page_type, style_ids in prompts.STYLE_IDS_BY_PAGE_TYPE.items():
            for style_id in style_ids:
                with self.subTest(style=style_id):
                    style = prompts.STYLES[style_id]
                    markup = prompts.build_webpage_prompt(page_type, 'A <title>', 'A brief </page_brief>', style_id)
                    image = prompts.build_image_prompt(page_type, 'A title', 'A brief', style_id)
                    self.assertIn(style['name'], markup)
                    self.assertIn(style['name'], image)
                    self.assertIn(style['era'], image)
                    self.assertIn(style['image'], image)
                    self.assertIn('&lt;/page_brief&gt;', markup)
                    self.assertEqual(markup.count('id="llmvista-image-slot"'), 1)
                    self.assertIn('data-link-kind="profile"', markup)
                    self.assertIn('prefers-reduced-motion', markup)
                    self.assertNotIn('Create a full HTML page', markup)

    def test_style_from_another_page_type_is_rejected(self):
        with self.assertRaises(ValueError):
            prompts.build_webpage_prompt('magazine', 'Title', 'Brief', 'friendster')

    def test_stream_keeps_long_fragment_and_persists_style(self):
        context = page()
        cache = FakeCache()
        requests = []
        selected_for_image = []
        saved_styles = []
        chunks = ['<div class="retro-page"><p>', 'x' * 25000, '</p></div>']

        def create(**kwargs):
            requests.append(kwargs)
            return iter(SimpleNamespace(event_type='step.delta', delta=SimpleNamespace(type='text', text=chunk)) for chunk in chunks)

        ns = functions_from_main(
            'get_webpage_prompt', 'get_loading_shell', 'page_html_cache_key', 'render_page',
            prompts=prompts, random=random, html=html, time=time, re=re,
            cache=cache, logger=logging.getLogger('generation-test'),
            cache_page_context=lambda ctx: saved_styles.append(ctx.style_id),
            genai=SimpleNamespace(Client=lambda **kwargs: SimpleNamespace(interactions=SimpleNamespace(create=create))),
            GEMINI_API_KEY='test-key', TEXT_MODEL='gemini-3.6-flash',
            HTML_GENERATION_CONFIG={'thinking_level': 'minimal'},
            start_page_image_generation=lambda ctx, brief: selected_for_image.append(ctx.style_id) or 'image.jpg',
            url_for=lambda *args, **kwargs: '/image-status/image.jpg',
            get_image_loader_script=lambda *args: '', get_image_slot_fallback=lambda: '',
            get_follow_links_script=lambda *args: '', LOADING_COMPLETE_SCRIPT='',
            PAGE_SHELL_END='</main></body></html>', stream_with_context=lambda stream: stream,
            Response=lambda stream, **kwargs: stream,
        )
        rendered = ''.join(ns['render_page'](context))
        self.assertIn(''.join(chunks), rendered)
        self.assertTrue(rendered.endswith('</p></div></main></body></html>'))
        self.assertEqual(selected_for_image, [context.style_id])
        self.assertEqual(saved_styles, [context.style_id])
        self.assertIn(prompts.STYLES[context.style_id]['name'], requests[0]['input'])
        cached = ns['render_page'](context)
        self.assertEqual(cached, rendered)
        cache.values.clear()
        ''.join(ns['render_page'](context))
        self.assertEqual(selected_for_image, [context.style_id, context.style_id])
        self.assertEqual(requests[0]['input'], requests[1]['input'])

    def test_image_request_uses_style_and_preserves_output_settings(self):
        context = page('personal_desktop')
        calls = []
        fixture = BytesIO()
        Image.new('RGB', (640, 480), (80, 120, 160)).save(fixture, format='PNG')
        encoded = base64.b64encode(fixture.getvalue()).decode()

        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_image=SimpleNamespace(data=encoded))

        with tempfile.TemporaryDirectory() as directory:
            ns = functions_from_main(
                'get_image_filename', 'generate_page_image',
                prompts=prompts, hashlib=hashlib, time=time, base64=base64,
                encode_period_image=encode_period_image,
                os=__import__('os'), app=SimpleNamespace(static_folder=directory),
                IMAGE_MODEL='gemini-nano-banana-2.1',
                IMAGE_GENERATION_CONFIG={'thinking_level': 'minimal'},
                logger=logging.getLogger('generation-test'), get_image_url=lambda filename: '/static/generated/' + filename,
            )
            first_filename = ns['get_image_filename'](context)
            client = SimpleNamespace(interactions=SimpleNamespace(create=create))
            url, _ = ns['generate_page_image'](client, context, context.meta)
            self.assertTrue(url.endswith(first_filename))
            treatment = prompts.get_image_treatment(context.style_id, context.url)
            with Image.open(Path(directory) / 'generated' / first_filename) as saved:
                self.assertEqual(saved.size, prompts.IMAGE_TREATMENTS[treatment]['size'])
                self.assertEqual(saved.format, prompts.IMAGE_TREATMENTS[treatment]['format'])
            self.assertIn(prompts.STYLES[context.style_id]['image'], calls[0]['input'])
            self.assertEqual(calls[0]['generation_config'], {'thinking_level': 'minimal'})
            self.assertEqual(calls[0]['response_format']['image_size'], '1K')
            self.assertEqual(calls[0]['response_format']['aspect_ratio'], '4:3')
            context.style_id = 'personal_90s'
            self.assertNotEqual(ns['get_image_filename'](context), first_filename)
            ns['IMAGE_MODEL'] = 'different-model'
            self.assertNotEqual(ns['get_image_filename'](context), first_filename)


if __name__ == '__main__':
    unittest.main()
