"""
Comprehensive Vision Analysis Service.

Provides deep, "Claude-level" image analysis for any image uploaded
in the WLJ ecosystem. Unlike the scan-specific VisionService (which
routes to 12 categories), this service produces rich natural-language
descriptions, object identification, text detection, and contextual
insights that feed into CoS context.
"""

import hashlib
import json
import logging
import time

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

logger = logging.getLogger(__name__)

COMPREHENSIVE_VISION_PROMPT = """You are a detailed image analyst for "Whole Life Journey", a personal wellness and life management app.

Analyze this image thoroughly and return a comprehensive JSON description. Be specific and detailed — describe what you actually see, not what you assume.

RULES:
1. NEVER identify people or faces. If people are visible, describe their activity without identifying them.
2. Be factual and observational. Describe what is visible.
3. If text is visible (labels, signs, documents), transcribe it accurately.
4. Note colors, brands, conditions, quantities where visible.
5. Think about what this image tells us about the person's life context.

Return ONLY valid JSON with this exact schema:
{
  "summary": "1-2 sentence high-level description of what's in the image",
  "detailed_description": "Rich paragraph describing everything visible in detail — objects, setting, text, colors, condition, spatial relationships",
  "objects_identified": [
    {"label": "object name", "details": "specific attributes like brand, color, size, condition"}
  ],
  "text_detected": "Any visible text, labels, or writing transcribed here. Empty string if none.",
  "context_clues": "What this image suggests about the person's current activity, environment, or situation",
  "category": "best-fit category from: food, medicine, supplement, fitness, pet, recipe, document, inventory, home, outdoors, work, travel, social, creative, other",
  "relevance_tags": ["3-6 short tags for search indexing, e.g. kitchen, morning, workout"],
  "actionable_insights": ["Practical observations, e.g. 'Medicine bottle shows refill date of March 15'"]
}"""


class ComprehensiveVisionService:
    """Comprehensive image analysis using OpenAI Vision API."""

    def __init__(self):
        self.client = None
        self.model = getattr(settings, "OPENAI_VISION_MODEL", "gpt-4o")

    @property
    def is_available(self) -> bool:
        return bool(getattr(settings, "OPENAI_API_KEY", None))

    def _get_client(self):
        if self.client is None:
            from openai import OpenAI
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return self.client

    def analyze(self, *, image_base64, mime_type, user, source_type,
                source_object=None):
        """
        Analyze an image and persist results to ImageAnalysis.

        Args:
            image_base64: Base64-encoded image data (no data URI prefix).
            mime_type: MIME type (e.g., 'image/jpeg').
            user: User who uploaded the image.
            source_type: One of ImageAnalysis.SOURCE_CHOICES values.
            source_object: Optional Django model instance to link via GenericFK.

        Returns:
            ImageAnalysis instance (saved), or None on failure.
        """
        from apps.scan.models import ImageAnalysis
        from .image_utils import compute_image_hash, resize_for_vision

        if not self.is_available:
            logger.warning("Vision API not available — skipping analysis")
            return None

        # Dedup check
        image_hash = compute_image_hash(image_base64)
        recent_cutoff = timezone.now() - timezone.timedelta(hours=24)
        existing = ImageAnalysis.objects.filter(
            user=user,
            image_hash=image_hash,
            status="completed",
            created_at__gte=recent_cutoff,
        ).first()
        if existing:
            logger.info("Dedup hit for image hash %s — reusing analysis %s",
                        image_hash[:12], existing.pk)
            return existing

        # Resize for cost optimization
        optimized_base64 = resize_for_vision(image_base64, mime_type)

        # Build the GenericFK fields
        ct = None
        obj_id = None
        if source_object:
            ct = ContentType.objects.get_for_model(source_object)
            obj_id = source_object.pk

        # Create pending record
        analysis = ImageAnalysis.objects.create(
            user=user,
            source_type=source_type,
            content_type=ct,
            object_id=obj_id,
            image_hash=image_hash,
            status="analyzing",
            model_used=self.model,
        )

        start_time = time.time()

        try:
            client = self._get_client()
            media_type = mime_type or "image/jpeg"
            data_uri = f"data:{media_type};base64,{optimized_base64}"

            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": COMPREHENSIVE_VISION_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analyze this image comprehensively.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": data_uri,
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                max_tokens=1500,
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            processing_time_ms = int((time.time() - start_time) * 1000)

            # Telemetry
            try:
                usage = getattr(response, "usage", None)
                if usage:
                    from apps.owner_finance.services.telemetry import log_llm_usage
                    log_llm_usage(
                        user=user,
                        feature="VISION_COMPREHENSIVE",
                        model_name=self.model,
                        input_tokens=getattr(usage, "prompt_tokens", 0),
                        output_tokens=getattr(usage, "completion_tokens", 0),
                    )
                    analysis.input_tokens = getattr(usage, "prompt_tokens", 0)
                    analysis.output_tokens = getattr(usage, "completion_tokens", 0)
            except Exception:
                pass

            # Parse response
            content = response.choices[0].message.content
            result = json.loads(content)

            analysis.summary = result.get("summary", "")
            analysis.detailed_description = result.get("detailed_description", "")
            analysis.category = result.get("category", "other")
            analysis.confidence = result.get("confidence")
            analysis.objects_identified = result.get("objects_identified", [])
            analysis.text_detected = result.get("text_detected", "")
            analysis.context_clues = result.get("context_clues", "")
            analysis.relevance_tags = result.get("relevance_tags", [])
            analysis.actionable_insights = result.get("actionable_insights", [])
            analysis.raw_response = result
            analysis.processing_time_ms = processing_time_ms
            analysis.status = "completed"

            # Build denormalized search text
            search_parts = [
                analysis.summary,
                analysis.detailed_description,
                analysis.text_detected,
                analysis.context_clues,
                " ".join(analysis.relevance_tags),
            ]
            for obj in analysis.objects_identified:
                search_parts.append(obj.get("label", ""))
                search_parts.append(obj.get("details", ""))
            analysis.search_text = " ".join(p for p in search_parts if p)

            analysis.save()
            logger.info(
                "Comprehensive analysis completed for %s (source=%s, %dms)",
                analysis.pk, source_type, processing_time_ms,
            )
            return analysis

        except json.JSONDecodeError as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error("Vision analysis JSON parse error: %s", e)
            analysis.status = "failed"
            analysis.processing_time_ms = processing_time_ms
            analysis.save(update_fields=["status", "processing_time_ms", "updated_at"])
            return analysis

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error("Vision analysis error: %s", e, exc_info=True)
            analysis.status = "failed"
            analysis.processing_time_ms = processing_time_ms
            analysis.save(update_fields=["status", "processing_time_ms", "updated_at"])
            return analysis


# Module-level singleton
comprehensive_vision_service = ComprehensiveVisionService()
