"""Verify period image sizes, formats, presentation, and stable variation."""
from io import BytesIO
from types import SimpleNamespace
import html
import unittest

from PIL import Image
import prompts
from retro_images import encode_period_image
from test_generation import functions_from_main


class RetroImageTests(unittest.TestCase):
    def test_processing_reduces_images_in_every_treatment(self):
        # A deterministic varied fixture exercises palette reduction and JPEG encoding.
        source = Image.new('RGB', (640, 480))
        source.putdata([
            ((x * 7) % 256, (y * 11) % 256, (x + y * 3) % 256)
            for y in range(480) for x in range(640)
        ])
        original = BytesIO()
        source.save(original, format='PNG')
        for treatment, asset in prompts.IMAGE_TREATMENTS.items():
            with self.subTest(treatment=treatment):
                encoded = encode_period_image(original.getvalue(), treatment)
                with Image.open(BytesIO(encoded)) as result:
                    self.assertEqual(result.size, asset['size'])
                    self.assertEqual(result.format, asset['format'])
                    if treatment == 'pixel':
                        self.assertEqual(result.mode, 'P')
                        self.assertLessEqual(len(result.getcolors()), 32)
                    if treatment == 'scan':
                        self.assertEqual(result.mode, 'L')

    def test_small_sources_are_not_upscaled(self):
        fixture = BytesIO()
        Image.new('RGB', (40, 30)).save(fixture, format='PNG')
        for treatment in prompts.IMAGE_TREATMENTS:
            with Image.open(BytesIO(encode_period_image(fixture.getvalue(), treatment))) as image:
                self.assertEqual(image.size, (40, 30))

    def test_treatments_are_stable_varied_and_appropriate_for_all_styles(self):
        self.assertEqual(set(prompts.STYLES), set(prompts.IMAGE_TREATMENTS_BY_STYLE))
        for style_id, choices in prompts.IMAGE_TREATMENTS_BY_STYLE.items():
            selected = [prompts.get_image_treatment(style_id, f'https://fictional.example/{i}') for i in range(100)]
            self.assertEqual(set(selected), set(choices))
            self.assertEqual(selected, [prompts.get_image_treatment(style_id, f'https://fictional.example/{i}') for i in range(100)])
        self.assertEqual(prompts.get_image_treatment('friendster', 'any-url'), 'snapshot')
        self.assertEqual(prompts.get_image_treatment('indie_zine', 'any-url'), 'scan')

    def test_html_image_prompt_and_loader_agree_on_presentation(self):
        ns = functions_from_main(
            'get_image_loader_script', prompts=prompts, html=html,
            get_image_url=lambda name: '/static/generated/' + name,
        )
        for treatment, asset in prompts.IMAGE_TREATMENTS.items():
            markup = prompts.build_webpage_prompt('personal', 'Title', 'Brief', 'personal_desktop', treatment)
            image = prompts.build_image_prompt('personal', 'Title', 'Brief', 'personal_desktop', treatment)
            script = ns['get_image_loader_script']('image.png', '/image-status/image.png', treatment)
            self.assertIn(asset['name'], markup)
            self.assertIn(asset['prompt'], image)
            self.assertIn(f"width:{asset['display_width']}px", script)
            self.assertEqual('image-rendering:pixelated' in script, treatment == 'pixel')
            self.assertNotIn('__IMAGE_', script)

    def test_status_accepts_pixel_pngs_and_rejects_invalid_paths(self):
        ns = functions_from_main(
            'image_status', re=__import__('re'),
            os=SimpleNamespace(path=SimpleNamespace(join=lambda *parts: '/'.join(parts), exists=lambda path: True)),
            app=SimpleNamespace(static_folder='static', route=lambda *args, **kwargs: lambda fn: fn),
            jsonify=lambda value: value,
            get_image_url=lambda name: '/static/generated/' + name,
        )
        for extension in ('png', 'jpg'):
            result = ns['image_status']('a' * 64 + '.' + extension)
            self.assertEqual(result['status'], 'ready')
        for invalid in ('../../secret.png', 'image.svg', 'a' * 64 + '.html'):
            self.assertEqual(ns['image_status'](invalid)[1], 404)


if __name__ == '__main__':
    unittest.main()
