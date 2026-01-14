"""Capture views - Handle audio capture and transcription requests."""

import json
import logging
import os
import tempfile
import uuid

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from .models import CaptureEntry
from .storage import (
    generate_upload_presigned_url,
    is_storage_configured,
    CaptureStorageError,
    CaptureStorageNotConfiguredError,
)
from .cloudinary_storage import (
    is_cloudinary_configured,
    upload_audio as cloudinary_upload_audio,
    CloudinaryStorageError,
)

logger = logging.getLogger(__name__)


class CaptureRecordView(LoginRequiredMixin, TemplateView):
    """
    Browser-based audio recording interface.

    Provides a mobile-first UI for recording audio directly in the browser
    using the MediaRecorder API. Records in webm format for best compatibility.
    """

    template_name = "capture/capture_record.html"


class CaptureUploadView(LoginRequiredMixin, View):
    """
    Handle audio file uploads with validation.

    Supports both direct uploads for small files and chunked uploads for
    large files (up to 60MB). Validates file type and size server-side.
    """

    MAX_FILE_SIZE = 60 * 1024 * 1024  # 60MB
    ACCEPTED_EXTENSIONS = ['.mp3', '.m4a', '.wav', '.webm']
    ACCEPTED_MIME_TYPES = [
        'audio/mpeg',
        'audio/mp4',
        'audio/wav',
        'audio/webm',
        'audio/x-m4a',
    ]

    # Store chunked upload sessions (in production, use Redis/cache)
    _upload_sessions = {}

    def get(self, request):
        """Render upload form."""
        return TemplateView.as_view(
            template_name="capture/capture_upload.html"
        )(request)

    def post(self, request):
        """Handle file upload or chunked upload operations."""
        content_type = request.content_type

        # Handle JSON requests (chunked upload init/complete)
        if content_type == 'application/json':
            try:
                data = json.loads(request.body)
                action = data.get('action')

                if action == 'init_chunked':
                    return self._init_chunked_upload(request, data)
                elif action == 'complete_chunked':
                    return self._complete_chunked_upload(request, data)
                else:
                    return JsonResponse({'error': 'Invalid action'}, status=400)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Handle chunk upload
        if 'chunk' in request.FILES:
            return self._upload_chunk(request)

        # Handle direct file upload
        if 'file' in request.FILES:
            return self._upload_direct(request)

        return JsonResponse({'error': 'No file provided'}, status=400)

    def _validate_file(self, file):
        """Validate file type and size."""
        # Check file size
        if file.size > self.MAX_FILE_SIZE:
            return False, 'File too large. Maximum size is 60MB.'

        # Check file extension
        ext = os.path.splitext(file.name)[1].lower()
        if ext not in self.ACCEPTED_EXTENSIONS:
            return False, 'Invalid file type. Accepted formats: MP3, M4A, WAV, WebM.'

        # Check content type
        if file.content_type not in self.ACCEPTED_MIME_TYPES:
            # Some browsers may send different content types, so also check extension
            if ext not in self.ACCEPTED_EXTENSIONS:
                return False, 'Invalid file type. Accepted formats: MP3, M4A, WAV, WebM.'

        return True, None

    def _upload_direct(self, request):
        """Handle direct file upload for small files."""
        file = request.FILES['file']

        is_valid, error = self._validate_file(file)
        if not is_valid:
            return JsonResponse({'success': False, 'error': error}, status=400)

        # Create capture entry
        entry = CaptureEntry.objects.create(
            user=request.user,
            title=os.path.splitext(file.name)[0],
            status=CaptureEntry.STATUS_UPLOADING,
        )

        # TODO: Upload to S3 in future task
        # For now, just mark as ready and return success

        entry.status = CaptureEntry.STATUS_READY
        entry.save()

        return JsonResponse({
            'success': True,
            'entry_id': str(entry.id),
            'redirect_url': reverse('capture:list')
        })

    def _init_chunked_upload(self, request, data):
        """Initialize a chunked upload session."""
        filename = data.get('filename')
        filesize = data.get('filesize')
        total_chunks = data.get('total_chunks')

        if not all([filename, filesize, total_chunks]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        # Validate file size
        if filesize > self.MAX_FILE_SIZE:
            return JsonResponse({'error': 'File too large. Maximum size is 60MB.'}, status=400)

        # Validate file extension
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.ACCEPTED_EXTENSIONS:
            return JsonResponse({
                'error': 'Invalid file type. Accepted formats: MP3, M4A, WAV, WebM.'
            }, status=400)

        # Create session
        session_id = str(uuid.uuid4())
        temp_dir = tempfile.mkdtemp()

        self._upload_sessions[session_id] = {
            'user_id': request.user.id,
            'filename': filename,
            'filesize': filesize,
            'total_chunks': total_chunks,
            'uploaded_chunks': set(),
            'temp_dir': temp_dir,
        }

        return JsonResponse({
            'success': True,
            'session_id': session_id
        })

    def _upload_chunk(self, request):
        """Handle chunk upload."""
        chunk = request.FILES.get('chunk')
        chunk_index = request.POST.get('chunk_index')
        session_id = request.POST.get('session_id')

        if not all([chunk, chunk_index is not None, session_id]):
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        session = self._upload_sessions.get(session_id)
        if not session:
            return JsonResponse({'error': 'Invalid session'}, status=400)

        # Verify user owns this session
        if session['user_id'] != request.user.id:
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        try:
            chunk_index = int(chunk_index)
        except ValueError:
            return JsonResponse({'error': 'Invalid chunk index'}, status=400)

        # Save chunk to temp file
        chunk_path = os.path.join(session['temp_dir'], f'chunk_{chunk_index}')
        with open(chunk_path, 'wb') as f:
            for c in chunk.chunks():
                f.write(c)

        session['uploaded_chunks'].add(chunk_index)

        return JsonResponse({
            'success': True,
            'chunk_index': chunk_index
        })

    def _complete_chunked_upload(self, request, data):
        """Complete a chunked upload by assembling chunks."""
        session_id = data.get('session_id')

        if not session_id:
            return JsonResponse({'error': 'Missing session_id'}, status=400)

        session = self._upload_sessions.get(session_id)
        if not session:
            return JsonResponse({'error': 'Invalid session'}, status=400)

        # Verify user owns this session
        if session['user_id'] != request.user.id:
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        # Verify all chunks uploaded
        if len(session['uploaded_chunks']) != session['total_chunks']:
            return JsonResponse({
                'error': f"Missing chunks. Expected {session['total_chunks']}, got {len(session['uploaded_chunks'])}"
            }, status=400)

        # Create capture entry
        entry = CaptureEntry.objects.create(
            user=request.user,
            title=os.path.splitext(session['filename'])[0],
            status=CaptureEntry.STATUS_UPLOADING,
        )

        # TODO: Assemble chunks and upload to S3 in future task
        # For now, clean up temp files and mark as ready

        # Clean up temp files
        try:
            import shutil
            shutil.rmtree(session['temp_dir'])
        except Exception:
            pass

        # Remove session
        del self._upload_sessions[session_id]

        entry.status = CaptureEntry.STATUS_READY
        entry.save()

        return JsonResponse({
            'success': True,
            'entry_id': str(entry.id),
            'redirect_url': reverse('capture:list')
        })


class CaptureListView(LoginRequiredMixin, ListView):
    """
    List all capture entries for the current user.

    Shows recordings, transcripts, and summaries ordered by most recent first.
    """

    model = CaptureEntry
    template_name = "capture/capture_list.html"
    context_object_name = "entries"
    paginate_by = 20

    def get_queryset(self):
        """Filter entries to current user, ordered by creation date."""
        return CaptureEntry.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        """Add additional context for the template."""
        context = super().get_context_data(**kwargs)
        user_entries = CaptureEntry.objects.filter(user=self.request.user)
        context['total_count'] = user_entries.count()
        context['ready_count'] = user_entries.filter(
            status=CaptureEntry.STATUS_READY
        ).count()
        context['now'] = timezone.now()
        return context


class CaptureDetailView(LoginRequiredMixin, DetailView):
    """
    Display a single capture entry with its summary and audio player.

    Shows the structured BLUF summary with proper section styling,
    audio playback controls, and metadata (title, date, duration, category).
    Only entries belonging to the current user can be accessed.
    """

    model = CaptureEntry
    template_name = "capture/capture_detail.html"
    context_object_name = "entry"

    def get_queryset(self):
        """Filter entries to current user for security."""
        return CaptureEntry.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        """Add additional context for the template."""
        context = super().get_context_data(**kwargs)
        entry = self.object

        # Calculate days remaining for audio file (7 day retention)
        # Negative value means expired, None means no expiration date set
        if entry.audio_expires_at:
            days_remaining = (entry.audio_expires_at - timezone.now()).days
            context['days_remaining'] = days_remaining
        else:
            context['days_remaining'] = None

        # Format duration as MM:SS
        if entry.duration_seconds:
            minutes = entry.duration_seconds // 60
            seconds = entry.duration_seconds % 60
            context['formatted_duration'] = f"{minutes}:{seconds:02d}"
        else:
            context['formatted_duration'] = None

        return context


class CaptureSubmitView(LoginRequiredMixin, View):
    """
    Handle audio submission with S3 presigned URL generation.

    This view supports two actions:
    1. 'get_upload_url': Generate a presigned S3 URL for direct browser upload
    2. 'confirm_upload': Confirm that upload completed and advance to transcribing

    Frontend workflow:
    1. POST with action='get_upload_url' -> returns presigned URL + entry_id
    2. Frontend uploads directly to S3 using presigned URL
    3. POST with action='confirm_upload' + entry_id -> status changes to 'transcribing'
    """

    ACCEPTED_CONTENT_TYPES = [
        'audio/mpeg',
        'audio/mp4',
        'audio/wav',
        'audio/webm',
        'audio/x-m4a',
        'audio/ogg',
        'audio/aac',
        'audio/x-caf',
        'audio/3gpp',
        'audio/3gpp2',
        'video/mp4',  # Some browsers report audio as video/mp4
    ]

    def post(self, request):
        """Handle submission actions."""
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        action = data.get('action')

        if action == 'get_upload_url':
            return self._get_upload_url(request, data)
        elif action == 'confirm_upload':
            return self._confirm_upload(request, data)
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)

    def _get_upload_url(self, request, data):
        """
        Generate a presigned S3 URL for uploading audio.

        Creates a CaptureEntry with status='uploading' and returns:
        - upload_url: Presigned S3 PUT URL
        - entry_id: UUID of the created entry for status polling
        - audio_expires_at: When the audio will be auto-deleted
        """
        # Validate inputs
        content_type = data.get('content_type', 'audio/webm')
        filename = data.get('filename', '')
        title = data.get('title', '')
        duration_seconds = data.get('duration_seconds')

        # Extract base content type (strip codec parameters like "audio/webm;codecs=opus")
        base_content_type = content_type.split(';')[0].strip()

        if base_content_type not in self.ACCEPTED_CONTENT_TYPES:
            logger.warning(f"Rejected content type: {content_type} (base: {base_content_type})")
            return JsonResponse({
                'error': 'Invalid content type. Accepted: MP3, M4A, WAV, WebM, OGG.'
            }, status=400)

        # Check if Cloudinary is configured (preferred)
        if is_cloudinary_configured():
            logger.info("Using Cloudinary for audio storage")
            return self._cloudinary_upload_response(request, data)

        # Check if S3 storage is configured
        if not is_storage_configured():
            logger.warning("No storage configured, falling back to mock mode")
            return self._mock_upload_response(request, data)

        try:
            # Generate presigned upload URL
            upload_data = generate_upload_presigned_url(
                user_id=str(request.user.id),
                content_type=content_type,
                filename=filename,
            )

            # Create CaptureEntry with uploading status
            entry = CaptureEntry.objects.create(
                user=request.user,
                title=title or os.path.splitext(filename)[0] if filename else '',
                status=CaptureEntry.STATUS_UPLOADING,
                audio_expires_at=upload_data['audio_expires_at'],
                duration_seconds=duration_seconds,
            )

            # Store the S3 key in audio_file_url temporarily (will be updated on confirm)
            # We'll construct the full URL after confirmation
            entry.audio_file_url = upload_data['key']
            entry.save()

            logger.info(f"Created capture entry {entry.id} for user {request.user.email}")

            return JsonResponse({
                'success': True,
                'entry_id': str(entry.id),
                'upload_url': upload_data['url'],
                'upload_key': upload_data['key'],
                'audio_expires_at': upload_data['audio_expires_at'].isoformat(),
            })

        except CaptureStorageNotConfiguredError as e:
            logger.error(f"S3 storage not configured: {e}")
            return JsonResponse({
                'error': 'Storage not configured. Please contact support.'
            }, status=503)
        except CaptureStorageError as e:
            logger.error(f"S3 storage error: {e}")
            return JsonResponse({
                'error': 'Failed to generate upload URL. Please try again.'
            }, status=500)

    def _confirm_upload(self, request, data):
        """
        Confirm that the S3 upload completed successfully.

        Updates the entry status to 'transcribing' and triggers async processing.
        The processing pipeline (transcription -> summarization) runs in a background thread.
        """
        entry_id = data.get('entry_id')

        if not entry_id:
            return JsonResponse({'error': 'Missing entry_id'}, status=400)

        try:
            entry = CaptureEntry.objects.get(id=entry_id, user=request.user)
        except CaptureEntry.DoesNotExist:
            return JsonResponse({'error': 'Entry not found'}, status=404)

        # Verify entry is in uploading status
        if entry.status != CaptureEntry.STATUS_UPLOADING:
            return JsonResponse({
                'error': f'Entry is not in uploading status (current: {entry.status})'
            }, status=400)

        # Update status to transcribing
        entry.status = CaptureEntry.STATUS_TRANSCRIBING
        entry.save()

        logger.info(f"Confirmed upload for entry {entry.id}, status now: transcribing")

        # Trigger async processing in a background thread
        # This prevents blocking the HTTP response while processing occurs
        import threading
        from apps.capture.tasks import process_capture_entry

        def run_processing():
            try:
                result = process_capture_entry(str(entry.id))
                if result['success']:
                    logger.info(f"Entry {entry.id} processing completed successfully")
                else:
                    logger.warning(f"Entry {entry.id} processing failed: {result.get('message')}")
            except Exception as e:
                logger.exception(f"Entry {entry.id} processing thread error: {e}")

        thread = threading.Thread(target=run_processing, daemon=True)
        thread.start()

        return JsonResponse({
            'success': True,
            'entry_id': str(entry.id),
            'status': entry.status,
            'redirect_url': reverse('capture:list'),
        })

    def _cloudinary_upload_response(self, request, data):
        """
        Return response indicating Cloudinary upload mode.

        In this mode, the frontend will upload the audio directly to
        a server endpoint that handles Cloudinary upload.
        """
        from datetime import timedelta

        filename = data.get('filename', '')
        title = data.get('title', '')
        duration_seconds = data.get('duration_seconds')
        content_type = data.get('content_type', 'audio/webm')

        # Determine title
        if title:
            entry_title = title
        elif filename:
            entry_title = os.path.splitext(filename)[0]
        else:
            entry_title = 'Recording'

        # Create entry in uploading status
        entry = CaptureEntry.objects.create(
            user=request.user,
            title=entry_title,
            status=CaptureEntry.STATUS_UPLOADING,
            audio_expires_at=timezone.now() + timedelta(days=7),
            duration_seconds=duration_seconds,
        )

        logger.info(f"Created capture entry {entry.id} for Cloudinary upload")

        return JsonResponse({
            'success': True,
            'entry_id': str(entry.id),
            'upload_mode': 'cloudinary',
            'upload_url': reverse('capture:cloudinary_upload', kwargs={'entry_id': entry.id}),
        })

    def _mock_upload_response(self, request, data):
        """
        Provide a mock response when no storage is configured.

        This allows development/testing without cloud storage.
        Creates an entry that goes directly to 'ready' status.
        """
        from datetime import timedelta

        filename = data.get('filename', '')
        title = data.get('title', '')
        duration_seconds = data.get('duration_seconds')

        # Determine title: use provided title, or extract from filename, or default
        if title:
            entry_title = title
        elif filename:
            entry_title = os.path.splitext(filename)[0]
        else:
            entry_title = 'Recording'

        # Create entry that's immediately ready (no real upload)
        entry = CaptureEntry.objects.create(
            user=request.user,
            title=entry_title,
            status=CaptureEntry.STATUS_READY,
            audio_expires_at=timezone.now() + timedelta(days=7),
            duration_seconds=duration_seconds,
        )

        logger.info(f"Created mock capture entry {entry.id} (no storage configured)")

        return JsonResponse({
            'success': True,
            'entry_id': str(entry.id),
            'upload_url': None,  # No upload needed in mock mode
            'mock_mode': True,
            'redirect_url': reverse('capture:list'),
        })


class CaptureCloudinaryUploadView(LoginRequiredMixin, View):
    """
    Handle audio file upload to Cloudinary.

    Accepts POST with multipart form data containing the audio file.
    Uploads to Cloudinary and updates the CaptureEntry with the URL.
    """

    MAX_FILE_SIZE = 60 * 1024 * 1024  # 60MB

    def post(self, request, entry_id):
        """Upload audio file to Cloudinary."""
        # Get the entry
        try:
            entry = CaptureEntry.objects.get(id=entry_id, user=request.user)
        except CaptureEntry.DoesNotExist:
            return JsonResponse({'error': 'Entry not found'}, status=404)

        # Verify entry is in uploading status
        if entry.status != CaptureEntry.STATUS_UPLOADING:
            return JsonResponse({
                'error': f'Entry is not in uploading status (current: {entry.status})'
            }, status=400)

        # Get the audio file
        audio_file = request.FILES.get('audio')
        if not audio_file:
            return JsonResponse({'error': 'No audio file provided'}, status=400)

        # Validate file size
        if audio_file.size > self.MAX_FILE_SIZE:
            return JsonResponse({
                'error': 'File too large. Maximum size is 60MB.'
            }, status=400)

        try:
            # Upload to Cloudinary
            result = cloudinary_upload_audio(
                file_data=audio_file,
                user_id=str(request.user.id),
                filename=audio_file.name,
                content_type=audio_file.content_type,
            )

            # Update entry with Cloudinary URL
            entry.audio_file_url = result['url']
            entry.audio_expires_at = result['audio_expires_at']
            if result.get('duration_seconds'):
                entry.duration_seconds = result['duration_seconds']
            entry.status = CaptureEntry.STATUS_TRANSCRIBING
            entry.save()

            logger.info(f"Uploaded audio to Cloudinary for entry {entry.id}")

            # Trigger async processing
            import threading
            from apps.capture.tasks import process_capture_entry

            def run_processing():
                try:
                    proc_result = process_capture_entry(str(entry.id))
                    if proc_result['success']:
                        logger.info(f"Entry {entry.id} processing completed successfully")
                    else:
                        logger.warning(f"Entry {entry.id} processing failed: {proc_result.get('message')}")
                except Exception as e:
                    logger.exception(f"Entry {entry.id} processing thread error: {e}")

            thread = threading.Thread(target=run_processing, daemon=True)
            thread.start()

            return JsonResponse({
                'success': True,
                'entry_id': str(entry.id),
                'status': entry.status,
            })

        except CloudinaryStorageError as e:
            logger.error(f"Cloudinary upload failed for entry {entry.id}: {e}")
            entry.status = CaptureEntry.STATUS_FAILED
            entry.error_message = str(e)
            entry.save()
            return JsonResponse({
                'error': 'Failed to upload audio. Please try again.'
            }, status=500)


class CaptureUpdateTitleView(LoginRequiredMixin, View):
    """
    AJAX endpoint for updating capture entry title.

    Accepts POST with JSON body containing 'title' field.
    Validates title length (max 200 chars) and returns success/error response.
    """

    MAX_TITLE_LENGTH = 200

    def post(self, request, pk):
        """Update the entry title."""
        try:
            entry = CaptureEntry.objects.get(id=pk, user=request.user)
        except CaptureEntry.DoesNotExist:
            return JsonResponse({'error': 'Entry not found'}, status=404)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        title = data.get('title', '').strip()

        # Validate title length
        if len(title) > self.MAX_TITLE_LENGTH:
            return JsonResponse({
                'error': f'Title too long. Maximum {self.MAX_TITLE_LENGTH} characters allowed.'
            }, status=400)

        # Update title
        entry.title = title
        entry.save(update_fields=['title', 'updated_at'])

        logger.info(f"Updated title for entry {entry.id} to: {title[:50]}...")

        return JsonResponse({
            'success': True,
            'title': entry.title,
            'message': 'Title updated successfully'
        })


class CaptureUpdateCategoryView(LoginRequiredMixin, View):
    """
    AJAX endpoint for updating capture entry category and subcategory.

    Accepts POST with JSON body containing 'category' and optional 'subcategory' fields.
    Validates that category/subcategory are valid choices and subcategory matches category.
    """

    # Map categories to their valid subcategories
    CATEGORY_SUBCATEGORIES = {
        CaptureEntry.CATEGORY_FAITH: [
            CaptureEntry.SUBCATEGORY_SERMON,
            CaptureEntry.SUBCATEGORY_BIBLE_STUDY,
            CaptureEntry.SUBCATEGORY_DEVOTIONAL,
        ],
        CaptureEntry.CATEGORY_ORGANIZE: [
            CaptureEntry.SUBCATEGORY_MEETING,
            CaptureEntry.SUBCATEGORY_NOTES,
            CaptureEntry.SUBCATEGORY_PERSONAL,
        ],
    }

    def post(self, request, pk):
        """Update the entry category and subcategory."""
        try:
            entry = CaptureEntry.objects.get(id=pk, user=request.user)
        except CaptureEntry.DoesNotExist:
            return JsonResponse({'error': 'Entry not found'}, status=404)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        category = data.get('category', '').strip()
        subcategory = data.get('subcategory', '').strip()

        # Validate category (can be empty to clear)
        valid_categories = [c[0] for c in CaptureEntry.CATEGORY_CHOICES]
        if category and category not in valid_categories:
            return JsonResponse({
                'error': f'Invalid category. Valid options: {", ".join(valid_categories)}'
            }, status=400)

        # Validate subcategory matches category
        if subcategory:
            if not category:
                return JsonResponse({
                    'error': 'Cannot set subcategory without a category'
                }, status=400)

            valid_subcategories = self.CATEGORY_SUBCATEGORIES.get(category, [])
            if subcategory not in valid_subcategories:
                return JsonResponse({
                    'error': f'Invalid subcategory for {category}. Valid options: {", ".join(valid_subcategories)}'
                }, status=400)

        # Update category and subcategory
        entry.category = category
        entry.subcategory = subcategory if category else ''  # Clear subcategory if no category
        entry.save(update_fields=['category', 'subcategory', 'updated_at'])

        logger.info(f"Updated category for entry {entry.id} to: {category}/{subcategory}")

        return JsonResponse({
            'success': True,
            'category': entry.category,
            'category_display': entry.get_category_display() if entry.category else '',
            'subcategory': entry.subcategory,
            'subcategory_display': entry.get_subcategory_display() if entry.subcategory else '',
            'message': 'Category updated successfully'
        })


class CaptureStatusView(LoginRequiredMixin, View):
    """
    Get the status of a capture entry for polling.

    Returns the current status, user-friendly messages, and progress indicators.
    Used by frontend to show processing status during upload/transcription/summarization.
    """

    # Map status to user-friendly messages and progress percentage
    STATUS_INFO = {
        CaptureEntry.STATUS_UPLOADING: {
            'message': 'Uploading',
            'description': 'Uploading your recording...',
            'progress': 25,
        },
        CaptureEntry.STATUS_TRANSCRIBING: {
            'message': 'Transcribing',
            'description': 'Converting speech to text...',
            'progress': 50,
        },
        CaptureEntry.STATUS_SUMMARIZING: {
            'message': 'Summarizing',
            'description': 'Generating AI summary...',
            'progress': 75,
        },
        CaptureEntry.STATUS_READY: {
            'message': 'Ready',
            'description': 'Your recording is ready!',
            'progress': 100,
        },
        CaptureEntry.STATUS_FAILED: {
            'message': 'Failed',
            'description': 'Processing failed',
            'progress': 0,
        },
    }

    def get(self, request, entry_id):
        """Get entry status with user-friendly messages and progress."""
        try:
            entry = CaptureEntry.objects.get(id=entry_id, user=request.user)
        except CaptureEntry.DoesNotExist:
            return JsonResponse({'error': 'Entry not found'}, status=404)

        # Get status info
        status_info = self.STATUS_INFO.get(entry.status, {
            'message': entry.status.title(),
            'description': 'Processing...',
            'progress': 0,
        })

        response_data = {
            'entry_id': str(entry.id),
            'status': entry.status,
            'status_message': status_info['message'],
            'status_description': status_info['description'],
            'progress': status_info['progress'],
            'title': entry.title,
        }

        # Add status-specific data
        if entry.status == CaptureEntry.STATUS_FAILED:
            response_data['error_message'] = entry.error_message
        elif entry.status == CaptureEntry.STATUS_READY:
            response_data['summary'] = entry.summary
            response_data['transcript'] = entry.transcript[:500] if entry.transcript else ''
            response_data['category'] = entry.category
            response_data['subcategory'] = entry.subcategory
            # Include redirect URL for frontend to navigate to detail view after ready
            response_data['redirect_url'] = reverse('capture:detail', kwargs={'pk': entry.id})

        return JsonResponse(response_data)


class CaptureDownloadPDFView(LoginRequiredMixin, View):
    """
    Generate and download a Word document summary of a capture entry.

    Creates a branded DOCX document containing the title, metadata,
    summary, and transcript of the capture entry.

    Note: Named "PDF" for URL compatibility but generates Word docs
    since WeasyPrint has system dependency issues on Railway.
    """

    def get(self, request, pk):
        """Generate and return Word document for the capture entry."""
        from django.http import HttpResponse

        from .services.docx_generator import generate_docx, get_docx_filename

        try:
            entry = CaptureEntry.objects.get(id=pk, user=request.user)
        except CaptureEntry.DoesNotExist:
            return JsonResponse({'error': 'Entry not found'}, status=404)

        # Only allow document generation for ready entries
        if entry.status != CaptureEntry.STATUS_READY:
            return JsonResponse(
                {'error': 'Entry is not ready for document generation'},
                status=400
            )

        try:
            # Generate Word document
            docx_bytes = generate_docx(entry)
            filename = get_docx_filename(entry)

            # Create response with DOCX
            content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            response = HttpResponse(docx_bytes, content_type=content_type)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Content-Length'] = len(docx_bytes)

            logger.info(f"DOCX downloaded for entry {entry.id} by user {request.user.email}")

            return response

        except Exception as e:
            logger.exception(f"Document generation failed for entry {pk}: {e}")
            error_msg = str(e) if str(e) else type(e).__name__
            return JsonResponse(
                {'error': f'Failed to generate document: {error_msg}'},
                status=500
            )


class CaptureEmailView(LoginRequiredMixin, View):
    """
    Send a capture entry summary via email with PDF attachment.

    Accepts POST with JSON body containing:
    - recipient_email: Email address to send to
    - message: Optional personal message from sender

    Returns JSON with success/error status.
    """

    def post(self, request, pk):
        """Send capture entry via email."""
        from .services.email import send_capture_email

        # Get the capture entry
        try:
            entry = CaptureEntry.objects.get(id=pk, user=request.user)
        except CaptureEntry.DoesNotExist:
            return JsonResponse({'error': 'Entry not found'}, status=404)

        # Only allow email for ready entries
        if entry.status != CaptureEntry.STATUS_READY:
            return JsonResponse(
                {'error': 'Entry is not ready for sharing'},
                status=400
            )

        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        recipient_email = data.get('recipient_email', '').strip()
        message = data.get('message', '').strip()

        # Validate recipient email
        if not recipient_email:
            return JsonResponse({'error': 'Recipient email is required'}, status=400)

        # Send the email
        result = send_capture_email(
            capture_entry=entry,
            recipient_email=recipient_email,
            sender_user=request.user,
            message=message if message else None,
        )

        if result['success']:
            logger.info(
                f"Email sent for entry {entry.id} by user {request.user.email} "
                f"to {recipient_email}"
            )
            return JsonResponse({
                'success': True,
                'message': f'Email sent to {recipient_email}'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Failed to send email')
            }, status=400)


class CaptureDeleteView(LoginRequiredMixin, View):
    """
    Delete a capture entry.

    Accepts POST requests and deletes the entry permanently.
    For AJAX requests, returns JSON response.
    For regular requests, redirects to the list page.
    """

    def post(self, request, pk):
        """Delete capture entry."""
        # Get the capture entry
        try:
            entry = CaptureEntry.objects.get(id=pk, user=request.user)
        except CaptureEntry.DoesNotExist:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Entry not found'}, status=404)
            from django.shortcuts import get_object_or_404
            get_object_or_404(CaptureEntry, id=pk, user=request.user)

        entry_title = entry.title or 'Untitled Recording'
        entry_id = entry.id

        # Delete the entry (hard delete since CaptureEntry doesn't use soft delete)
        entry.delete()

        logger.info(f"Capture entry {entry_id} deleted by user {request.user.email}")

        # For AJAX requests, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f'"{entry_title}" deleted'
            })

        # For regular requests, redirect
        from django.contrib import messages
        from django.shortcuts import redirect
        messages.success(request, f'"{entry_title}" deleted.')
        return redirect('capture:list')
