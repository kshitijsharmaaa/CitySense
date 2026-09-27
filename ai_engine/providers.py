"""Gemini provider adapter. Keep provider-specific code isolated here."""

from io import BytesIO

from django.conf import settings
from PIL import Image

from .prompts import build_triage_prompt


def generate_with_gemini(*, title, description, image=None):
    """Return the provider's raw text response; callers must validate it."""
    # Lazy import keeps the app usable when the optional provider package is absent.
    from google import genai
    from google.genai import types

    prompt = build_triage_prompt(title=title, description=description)
    parts = [types.Part.from_text(text=prompt)]
    if image is not None:
        # UploadedFile objects are consumed again by Issue.save(); always read
        # from the start and leave them ready for Django's subsequent save.
        image.seek(0)
        try:
            image_bytes = image.read()
            with Image.open(BytesIO(image_bytes)) as opened_image:
                mime_type = {
                    "JPEG": "image/jpeg",
                    "PNG": "image/png",
                    "GIF": "image/gif",
                    "WEBP": "image/webp",
                }[opened_image.format]
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
        finally:
            image.seek(0)

    # Keep the written report and optional visual evidence together in one
    # user turn so Gemini receives a single, explicitly multimodal request.
    contents = types.Content(role="user", parts=parts)

    timeout_seconds = max(1, min(settings.AI_TIMEOUT_SECONDS, 30))
    timeout_ms = timeout_seconds * 1000
    with genai.Client(
        api_key=settings.AI_API_KEY,
        http_options=types.HttpOptions(
            timeout=timeout_ms,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    ) as client:
        response = client.models.generate_content(
            model=settings.AI_MODEL,
            contents=contents,
        )

    return response.text
