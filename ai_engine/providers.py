"""Gemini provider adapter. Keep provider-specific code isolated here."""

import time
from io import BytesIO

from django.conf import settings
from PIL import Image, ImageOps

from .prompts import build_triage_prompt


def generate_with_gemini(*, title, description, image=None, images=None, generate_report=False):
    """Return the provider's raw text response; callers must validate it."""
    # Lazy import keeps the app usable when the optional provider package is absent.
    from google import genai
    from google.genai import errors, types

    image_set = list(images or [])
    if image is not None:
        image_set.insert(0, image)
    if len(image_set) > 5:
        raise ValueError("Gemini triage supports at most five report photos.")
    prompt = build_triage_prompt(title=title, description=description, generate_report=generate_report)
    parts = [types.Part.from_text(text=prompt)]
    for image in image_set:
        # UploadedFile objects are consumed again by Issue.save(); always read
        # from the start and leave them ready for Django's subsequent save.
        image.seek(0)
        try:
            image_bytes = image.read()
            with Image.open(BytesIO(image_bytes)) as opened_image:
                image_format = opened_image.format
                orientation = opened_image.getexif().get(274, 1)
                if orientation not in (None, 1):
                    oriented_image = ImageOps.exif_transpose(opened_image)
                    normalized = BytesIO()
                    save_options = {}
                    if image_format == "JPEG":
                        oriented_image = oriented_image.convert("RGB")
                        save_options = {
                            "quality": 95,
                            "exif": oriented_image.getexif().tobytes(),
                        }
                    elif image_format == "WEBP":
                        save_options = {"quality": 95}
                    oriented_image.save(normalized, format=image_format, **save_options)
                    image_bytes = normalized.getvalue()
                mime_type = {
                    "JPEG": "image/jpeg",
                    "PNG": "image/png",
                    "GIF": "image/gif",
                    "WEBP": "image/webp",
                }[image_format]
            parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
        finally:
            image.seek(0)

    # Keep the written report and optional visual evidence together in one
    # user turn so Gemini receives a single, explicitly multimodal request.
    contents = types.Content(role="user", parts=parts)

    timeout_seconds = max(1, min(settings.AI_TIMEOUT_SECONDS, 30))
    timeout_ms = timeout_seconds * 1000
    for attempt in range(2):
        try:
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
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        thinking_config=types.ThinkingConfig(
                            thinking_level="low" if generate_report else "medium"
                        ),
                    ),
                )
            break
        except errors.ServerError as exc:
            # Gemini can return transient availability/deadline errors under
            # load. Retry once; each request keeps the configured timeout.
            if exc.code not in (503, 504) or attempt == 1:
                raise
            time.sleep(0.25)

    return response.text
