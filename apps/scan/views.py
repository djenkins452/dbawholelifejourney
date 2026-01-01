"""
Scan Views - Camera scanning and image analysis.

Security Features:
- LoginRequiredMixin on all views
- CSRF protection via Django middleware
- Rate limiting per user and IP
- File validation (size, type, magic bytes)
- AI consent verification
- No image storage (in-memory only)
"""

import base64
import logging
import time
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.help.mixins import HelpContextMixin

from .models import ScanConsent, ScanLog
from .services import vision_service

logger = logging.getLogger(__name__)

# Rate limiting settings
RATE_LIMIT_PER_HOUR = getattr(settings, 'SCAN_RATE_LIMIT_PER_HOUR', 30)
RATE_LIMIT_IP_PER_HOUR = getattr(settings, 'SCAN_RATE_LIMIT_IP_PER_HOUR', 60)

# File validation settings
MAX_IMAGE_SIZE_MB = getattr(settings, 'SCAN_MAX_IMAGE_MB', 10)
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}

# Magic bytes for file type verification
MAGIC_BYTES = {
    b'\xff\xd8\xff': 'jpeg',
    b'\x89PNG': 'png',
    b'RIFF': 'webp',  # RIFF....WEBP
}


def get_client_ip(request):
    """
    Get client IP from request, handling proxies safely.

    Security: Only trust X-Forwarded-For from trusted proxies.
    In production, Railway sets this header.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # Take the first IP (client IP)
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip


def check_rate_limit(user, client_ip):
    """
    Check if user/IP is within rate limits.

    Returns:
        tuple: (allowed: bool, retry_after: int or None)
    """
    # Check user rate limit
    user_key = f"scan_rate_user_{user.id}"
    user_count = cache.get(user_key, 0)

    if user_count >= RATE_LIMIT_PER_HOUR:
        # Calculate retry-after (rough estimate)
        return False, 3600  # 1 hour

    # Check IP rate limit
    ip_key = f"scan_rate_ip_{client_ip}"
    ip_count = cache.get(ip_key, 0)

    if ip_count >= RATE_LIMIT_IP_PER_HOUR:
        return False, 3600

    # Increment counters
    cache.set(user_key, user_count + 1, timeout=3600)
    cache.set(ip_key, ip_count + 1, timeout=3600)

    return True, None


def validate_image_data(image_data: str) -> tuple:
    """
    Validate base64 image data.

    Args:
        image_data: Base64-encoded image (may include data URI prefix)

    Returns:
        tuple: (valid: bool, error_message: str or None, decoded_data: bytes or None, format: str or None)
    """
    # Remove data URI prefix if present
    if ',' in image_data:
        # Format: data:image/jpeg;base64,/9j/4AAQ...
        header, image_data = image_data.split(',', 1)

        # Extract MIME type from header
        if ';base64' in header:
            mime_part = header.split(';')[0]
            if ':' in mime_part:
                mime_type = mime_part.split(':')[1]
                if mime_type not in ALLOWED_MIME_TYPES:
                    return False, f"Invalid image type: {mime_type}", None, None

    # Decode base64
    try:
        decoded = base64.b64decode(image_data)
    except Exception:
        return False, "Invalid base64 encoding", None, None

    # Check size
    if len(decoded) > MAX_IMAGE_SIZE_BYTES:
        size_mb = len(decoded) / (1024 * 1024)
        return False, f"Image too large ({size_mb:.1f}MB). Max {MAX_IMAGE_SIZE_MB}MB.", None, None

    # Check magic bytes
    detected_format = None
    for magic, fmt in MAGIC_BYTES.items():
        if decoded[:len(magic)] == magic:
            detected_format = fmt
            break

    if not detected_format:
        # Special check for WEBP (RIFF....WEBP)
        if decoded[:4] == b'RIFF' and decoded[8:12] == b'WEBP':
            detected_format = 'webp'

    if not detected_format:
        return False, "Unrecognized image format. Use JPEG, PNG, or WebP.", None, None

    return True, None, decoded, detected_format


class ScanHomeView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    """
    Main scan page with camera interface.
    """

    template_name = "scan/scan_page.html"
    help_context_id = "SCAN_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Check if user has general AI consent
        has_ai_consent = (
            hasattr(user, 'preferences') and
            user.preferences.ai_enabled and
            user.preferences.ai_data_consent
        )
        context['has_ai_consent'] = has_ai_consent

        # Check if user has specific scan consent
        has_scan_consent = ScanConsent.objects.filter(user=user).exists()
        context['has_scan_consent'] = has_scan_consent

        # Service availability
        context['vision_available'] = vision_service.is_available

        # Recent scans for history
        context['recent_scans'] = ScanLog.objects.filter(
            user=user,
            status=ScanLog.STATUS_SUCCESS
        )[:5]

        return context


class ScanConsentView(LoginRequiredMixin, View):
    """
    Record user consent for scan feature.
    """

    def post(self, request):
        """Record consent and redirect to scan page."""
        user = request.user

        # Create or update consent
        ScanConsent.objects.update_or_create(
            user=user,
            defaults={
                'consent_version': '1.0',
                'consented_at': timezone.now()
            }
        )

        messages.success(
            request,
            "You can now use the camera scan feature."
        )

        return redirect('scan:home')


class ScanAnalyzeView(LoginRequiredMixin, View):
    """
    API endpoint to analyze an uploaded image.

    Accepts POST with JSON body containing base64 image data.
    Returns JSON with analysis results and suggested actions.
    """

    def post(self, request):
        """Analyze uploaded image."""
        user = request.user
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # Security Check 1: AI Consent
        if not self._check_ai_consent(user):
            return JsonResponse({
                'error': 'AI consent required',
                'error_code': 'NO_CONSENT',
                'request_id': request_id
            }, status=403)

        # Security Check 2: Scan Consent
        if not ScanConsent.objects.filter(user=user).exists():
            return JsonResponse({
                'error': 'Scan consent required',
                'error_code': 'NO_SCAN_CONSENT',
                'request_id': request_id
            }, status=403)

        # Security Check 3: Rate Limiting
        client_ip = get_client_ip(request)
        allowed, retry_after = check_rate_limit(user, client_ip)

        if not allowed:
            # Log rate limit hit
            ScanLog.objects.create(
                user=user,
                request_id=request_id,
                status=ScanLog.STATUS_RATE_LIMITED,
                error_code='RATE_LIMITED'
            )

            response = JsonResponse({
                'error': 'Too many requests. Please try again later.',
                'error_code': 'RATE_LIMITED',
                'request_id': request_id
            }, status=429)
            response['Retry-After'] = str(retry_after)
            return response

        # Get image data from request
        try:
            import json
            body = json.loads(request.body)
            image_data = body.get('image')
        except (json.JSONDecodeError, KeyError):
            image_data = request.POST.get('image')

        if not image_data:
            return JsonResponse({
                'error': 'No image provided',
                'error_code': 'NO_IMAGE',
                'request_id': request_id
            }, status=400)

        # Security Check 5: Validate Image
        valid, error_msg, decoded_data, image_format = validate_image_data(image_data)

        if not valid:
            return JsonResponse({
                'error': error_msg,
                'error_code': 'INVALID_IMAGE',
                'request_id': request_id
            }, status=400)

        # Create scan log entry
        scan_log = ScanLog.objects.create(
            user=user,
            request_id=request_id,
            status=ScanLog.STATUS_PENDING,
            image_size_kb=len(decoded_data) // 1024,
            image_format=image_format
        )

        # Security Check 4: Vision Service Available
        if not vision_service.is_available:
            scan_log.mark_failed(
                error_code='SERVICE_UNAVAILABLE',
                processing_time_ms=int((time.time() - start_time) * 1000)
            )
            return JsonResponse({
                'error': 'Vision service is not available',
                'error_code': 'SERVICE_UNAVAILABLE',
                'request_id': request_id
            }, status=503)

        # Clean base64 for API call (remove data URI prefix if present)
        clean_base64 = image_data
        if ',' in clean_base64:
            clean_base64 = clean_base64.split(',', 1)[1]

        # Analyze the image
        try:
            result = vision_service.analyze_image(
                image_base64=clean_base64,
                request_id=request_id,
                image_format=image_format
            )

            processing_time_ms = int((time.time() - start_time) * 1000)

            if result.error:
                scan_log.mark_failed(
                    error_code='ANALYSIS_ERROR',
                    processing_time_ms=processing_time_ms
                )
            else:
                scan_log.mark_success(
                    category=result.top_category,
                    confidence=result.confidence,
                    items=result.items,
                    processing_time_ms=processing_time_ms
                )

            # Store image in session for potential attachment to created items
            # This allows the scanned image to be saved to inventory/etc.
            # Session will auto-expire, and image is only stored temporarily
            scan_image_key = f'scan_image_{request_id}'
            request.session[scan_image_key] = image_data  # Keep original with data URI
            request.session.modified = True

            # Clear local variables from memory (session has its own copy)
            del decoded_data
            del clean_base64

            # Add scan_image_key to response so frontend can pass it to action URLs
            response_data = result.to_dict()
            response_data['scan_image_key'] = scan_image_key

            return JsonResponse(response_data)

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Scan {request_id} failed: {e}")

            scan_log.mark_failed(
                error_code='UNEXPECTED_ERROR',
                processing_time_ms=processing_time_ms
            )

            return JsonResponse({
                'error': 'An error occurred. Please try again.',
                'error_code': 'UNEXPECTED_ERROR',
                'request_id': request_id
            }, status=500)

    def _check_ai_consent(self, user) -> bool:
        """Check if user has consented to AI processing."""
        if not hasattr(user, 'preferences'):
            return False
        prefs = user.preferences
        return prefs.ai_enabled and prefs.ai_data_consent


class ScanRecordActionView(LoginRequiredMixin, View):
    """
    Record what action the user took after a scan.

    This is optional analytics to understand feature usage.
    """

    def post(self, request, request_id):
        """Record the action taken."""
        user = request.user

        try:
            scan_log = ScanLog.objects.get(
                request_id=request_id,
                user=user
            )
        except ScanLog.DoesNotExist:
            return JsonResponse({
                'error': 'Scan not found'
            }, status=404)

        action_id = request.POST.get('action_id', '')
        if action_id:
            scan_log.record_action(action_id)

        return JsonResponse({'status': 'recorded'})


class ScanHistoryView(LoginRequiredMixin, TemplateView):
    """
    View scan history.
    """

    template_name = "scan/history.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Get user's scan history
        context['scans'] = ScanLog.objects.filter(
            user=user
        ).order_by('-created_at')[:50]

        # Stats
        successful = ScanLog.objects.filter(
            user=user,
            status=ScanLog.STATUS_SUCCESS
        )
        context['total_scans'] = successful.count()

        # Category breakdown
        from django.db.models import Count
        context['category_counts'] = successful.values('category').annotate(
            count=Count('id')
        ).order_by('-count')

        return context


class BarcodeLookupView(LoginRequiredMixin, View):
    """
    API endpoint to look up a barcode and return nutritional information.

    Accepts POST with JSON body containing barcode string.
    Returns JSON with product information or not_found status.
    """

    def post(self, request):
        """Look up a barcode."""
        from .services import barcode_service
        from urllib.parse import quote

        user = request.user
        request_id = str(uuid.uuid4())

        # Security Check 1: AI Consent (required for AI fallback)
        has_ai_consent = self._check_ai_consent(user)

        # Get barcode from request
        try:
            import json as json_module
            body = json_module.loads(request.body)
            barcode = body.get('barcode', '')
        except (json_module.JSONDecodeError, KeyError):
            barcode = request.POST.get('barcode', '')

        if not barcode:
            return JsonResponse({
                'error': 'No barcode provided',
                'error_code': 'NO_BARCODE',
                'request_id': request_id
            }, status=400)

        # Look up the barcode
        result = barcode_service.lookup(
            barcode=barcode,
            use_ai=has_ai_consent  # Only use AI if user has consented
        )

        # Build URL for food entry creation if found
        if result.found:
            # Build query params for food entry form
            url_params = []
            if result.food_name:
                url_params.append(f'food_name={quote(result.food_name)}')
            if result.brand:
                url_params.append(f'food_brand={quote(result.brand)}')
            if result.calories is not None:
                url_params.append(f'total_calories={result.calories}')
            if result.protein_g is not None:
                url_params.append(f'total_protein_g={result.protein_g}')
            if result.carbohydrates_g is not None:
                url_params.append(f'total_carbohydrates_g={result.carbohydrates_g}')
            if result.fat_g is not None:
                url_params.append(f'total_fat_g={result.fat_g}')
            if result.fiber_g is not None:
                url_params.append(f'total_fiber_g={result.fiber_g}')
            if result.sugar_g is not None:
                url_params.append(f'total_sugar_g={result.sugar_g}')
            if result.saturated_fat_g is not None:
                url_params.append(f'total_saturated_fat_g={result.saturated_fat_g}')
            if result.serving_size is not None:
                url_params.append(f'serving_size={result.serving_size}')
            if result.serving_unit:
                url_params.append(f'serving_unit={quote(result.serving_unit)}')
            if result.description:
                url_params.append(f'notes={quote(result.description)}')

            # Set source as barcode
            url_params.append('entry_source=barcode')
            url_params.append(f'barcode={quote(barcode)}')

            # Build the food entry URL
            food_entry_url = reverse('health:food_entry_create')
            if url_params:
                food_entry_url += '?' + '&'.join(url_params)

            response_data = result.to_dict()
            response_data['request_id'] = request_id
            response_data['food_entry_url'] = food_entry_url

            # If this was an AI result, optionally save it to the database
            if result.source == 'ai' and has_ai_consent:
                saved_id = barcode_service.save_to_database(result)
                if saved_id:
                    response_data['saved_to_database'] = True
                    response_data['food_item_id'] = saved_id

            # Log the barcode scan
            ScanLog.objects.create(
                user=user,
                request_id=request_id,
                status=ScanLog.STATUS_SUCCESS,
                category='barcode',
                confidence=result.confidence,
                items_json=[{
                    'label': result.food_name,
                    'barcode': barcode,
                    'source': result.source
                }]
            )

            return JsonResponse(response_data)

        else:
            # Log the failed lookup
            ScanLog.objects.create(
                user=user,
                request_id=request_id,
                status=ScanLog.STATUS_SUCCESS,  # Request succeeded, just no match
                category='barcode',
                confidence=0.0,
                items_json=[{
                    'barcode': barcode,
                    'source': 'not_found'
                }]
            )

            return JsonResponse({
                'found': False,
                'barcode': barcode,
                'request_id': request_id,
                'message': 'Product not found. You can add it manually.'
            })

    def _check_ai_consent(self, user) -> bool:
        """Check if user has consented to AI processing."""
        if not hasattr(user, 'preferences'):
            return False
        prefs = user.preferences
        return prefs.ai_enabled and prefs.ai_data_consent


class ProductLookupView(LoginRequiredMixin, View):
    """
    API endpoint to look up a product barcode and return product information.

    Accepts POST with JSON body containing barcode string.
    Returns JSON with product information for inventory form pre-fill.
    """

    def post(self, request):
        """Look up a product barcode."""
        from .services import product_lookup_service
        from urllib.parse import quote

        user = request.user
        request_id = str(uuid.uuid4())

        # Security Check: AI Consent (required for AI fallback)
        has_ai_consent = self._check_ai_consent(user)

        # Get barcode from request
        try:
            import json as json_module
            body = json_module.loads(request.body)
            barcode = body.get('barcode', '')
        except (json_module.JSONDecodeError, KeyError):
            barcode = request.POST.get('barcode', '')

        if not barcode:
            return JsonResponse({
                'error': 'No barcode provided',
                'error_code': 'NO_BARCODE',
                'request_id': request_id
            }, status=400)

        # Look up the product
        result = product_lookup_service.lookup(
            barcode=barcode,
            use_ai=has_ai_consent
        )

        # Build URL for inventory creation if found
        if result.found:
            # Build query params for inventory form
            url_params = []
            if result.product_name:
                url_params.append(f'name={quote(result.product_name)}')
            if result.brand:
                url_params.append(f'brand={quote(result.brand)}')
            if result.category:
                url_params.append(f'category={quote(result.category)}')
            if result.model_number:
                url_params.append(f'model_number={quote(result.model_number)}')
            if result.description:
                url_params.append(f'description={quote(result.description)}')
            if result.msrp:
                url_params.append(f'purchase_price={result.msrp}')
                url_params.append(f'estimated_value={result.msrp}')

            # Set source tracking
            url_params.append('source=barcode_scan')
            url_params.append(f'barcode={quote(barcode)}')

            # Build the inventory creation URL
            inventory_url = reverse('life:inventory_create')
            if url_params:
                inventory_url += '?' + '&'.join(url_params)

            response_data = result.to_dict()
            response_data['request_id'] = request_id
            response_data['inventory_url'] = inventory_url

            # Log the product scan
            ScanLog.objects.create(
                user=user,
                request_id=request_id,
                status=ScanLog.STATUS_SUCCESS,
                category='inventory_item',
                confidence=result.confidence,
                items_json=[{
                    'label': result.product_name,
                    'barcode': barcode,
                    'source': result.source
                }]
            )

            return JsonResponse(response_data)

        else:
            # Log the failed lookup
            ScanLog.objects.create(
                user=user,
                request_id=request_id,
                status=ScanLog.STATUS_SUCCESS,
                category='inventory_item',
                confidence=0.0,
                items_json=[{
                    'barcode': barcode,
                    'source': 'not_found'
                }]
            )

            return JsonResponse({
                'found': False,
                'barcode': barcode,
                'request_id': request_id,
                'message': 'Product not found. You can add it manually.'
            })

    def _check_ai_consent(self, user) -> bool:
        """Check if user has consented to AI processing."""
        if not hasattr(user, 'preferences'):
            return False
        prefs = user.preferences
        return prefs.ai_enabled and prefs.ai_data_consent


class MedicineLookupView(LoginRequiredMixin, View):
    """
    API endpoint to look up a medicine barcode and return medicine information.

    Accepts POST with JSON body containing barcode string.
    Returns JSON with medicine information for medicine form pre-fill.
    """

    def post(self, request):
        """Look up a medicine barcode."""
        from .services import medicine_lookup_service
        from urllib.parse import quote

        user = request.user
        request_id = str(uuid.uuid4())

        # Security Check: AI Consent (required for AI fallback)
        has_ai_consent = self._check_ai_consent(user)

        # Get barcode from request
        try:
            import json as json_module
            body = json_module.loads(request.body)
            barcode = body.get('barcode', '')
        except (json_module.JSONDecodeError, KeyError):
            barcode = request.POST.get('barcode', '')

        if not barcode:
            return JsonResponse({
                'error': 'No barcode provided',
                'error_code': 'NO_BARCODE',
                'request_id': request_id
            }, status=400)

        # Look up the medicine
        result = medicine_lookup_service.lookup_by_barcode(
            barcode=barcode,
            use_ai=has_ai_consent
        )

        # Build URL for medicine creation if found
        if result.found:
            # Build query params for medicine form
            url_params = []
            if result.medicine_name:
                url_params.append(f'name={quote(result.medicine_name)}')
            if result.strength:
                url_params.append(f'dose={quote(result.strength)}')
            if result.purpose:
                url_params.append(f'purpose={quote(result.purpose)}')
            if result.dosage_form:
                url_params.append(f'notes={quote(f"Form: {result.dosage_form}")}')

            # Set source tracking
            url_params.append('source=barcode_scan')
            url_params.append(f'barcode={quote(barcode)}')

            # Build the medicine creation URL
            medicine_url = reverse('health:medicine_create')
            if url_params:
                medicine_url += '?' + '&'.join(url_params)

            response_data = result.to_dict()
            response_data['request_id'] = request_id
            response_data['medicine_url'] = medicine_url

            # Log the medicine scan
            ScanLog.objects.create(
                user=user,
                request_id=request_id,
                status=ScanLog.STATUS_SUCCESS,
                category='medicine',
                confidence=result.confidence,
                items_json=[{
                    'label': result.medicine_name,
                    'barcode': barcode,
                    'source': result.source
                }]
            )

            return JsonResponse(response_data)

        else:
            # Log the failed lookup
            ScanLog.objects.create(
                user=user,
                request_id=request_id,
                status=ScanLog.STATUS_SUCCESS,
                category='medicine',
                confidence=0.0,
                items_json=[{
                    'barcode': barcode,
                    'source': 'not_found'
                }]
            )

            return JsonResponse({
                'found': False,
                'barcode': barcode,
                'request_id': request_id,
                'message': 'Medicine not found. You can add it manually.'
            })

    def _check_ai_consent(self, user) -> bool:
        """Check if user has consented to AI processing."""
        if not hasattr(user, 'preferences'):
            return False
        prefs = user.preferences
        return prefs.ai_enabled and prefs.ai_data_consent
