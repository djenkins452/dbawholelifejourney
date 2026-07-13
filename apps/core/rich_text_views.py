"""
Image upload endpoint for the WLJ Rich Text Editor.

ONE upload path for every module's editor. Request-path safe: it only validates
and saves a file to the default storage (Cloudinary in prod / local FS in dev)
and returns the URL — no heavy compute, no intelligence calls. User-scoped and
login-gated so uploads are permission-checked.
"""
from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.core.models import RichTextImage

logger = logging.getLogger(__name__)

# 10 MB — generous for screenshots/photos, bounded to protect storage.
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
}


@login_required
@require_POST
def rich_text_image_upload(request):
    """Accept a single multipart image and return its stored URL as JSON.

    Response: 200 ``{"url": "…"}`` on success; 400 ``{"error": "…"}`` otherwise.
    """
    upload = request.FILES.get("image") or request.FILES.get("file")
    if upload is None:
        return JsonResponse({"error": "No image provided."}, status=400)

    if upload.size and upload.size > MAX_IMAGE_BYTES:
        return JsonResponse(
            {"error": "Image is too large (max 10 MB)."}, status=400
        )

    content_type = (getattr(upload, "content_type", "") or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        return JsonResponse(
            {"error": "Unsupported image type."}, status=400
        )

    # Verify the bytes really are a decodable image (defense in depth) before
    # trusting the client-declared content type.
    try:
        from PIL import Image as PILImage

        upload.seek(0)
        PILImage.open(upload).verify()
        upload.seek(0)
    except Exception:
        return JsonResponse({"error": "File is not a valid image."}, status=400)

    try:
        obj = RichTextImage.objects.create(
            user=request.user,
            image=upload,
            source_label=(request.POST.get("source_label", "") or "")[:100],
        )
    except Exception:
        logger.exception("Rich text image upload failed for user %s", request.user.pk)
        return JsonResponse({"error": "Upload failed. Please try again."}, status=400)

    return JsonResponse({"url": obj.image.url, "id": obj.pk})
