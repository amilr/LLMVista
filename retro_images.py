"""Encode generated assets at the small sizes used by the fictional web."""
from io import BytesIO

from PIL import Image, ImageEnhance, ImageOps

from prompts import IMAGE_TREATMENTS


def encode_period_image(image_bytes, treatment):
    asset = IMAGE_TREATMENTS[treatment]
    with Image.open(BytesIO(image_bytes)) as source:
        image = ImageOps.exif_transpose(source).convert('RGB')
    # Never enlarge a small source; the browser doubles pixel graphics crisply.
    image.thumbnail(
        asset['size'],
        Image.Resampling.NEAREST if treatment == 'pixel' else Image.Resampling.LANCZOS,
    )
    if treatment == 'pixel':
        image = image.quantize(colors=32, dither=Image.Dither.NONE)
    elif treatment == 'scan':
        image = ImageOps.grayscale(image)
    elif treatment == 'snapshot':
        image = ImageEnhance.Color(image).enhance(0.85)
        image = ImageEnhance.Sharpness(image).enhance(0.65)

    output = BytesIO()
    options = {'optimize': True}
    if asset['format'] == 'JPEG':
        options.update(quality=asset['quality'], progressive=False)
    image.save(output, format=asset['format'], **options)
    return output.getvalue()
