"""Capture views - Handle audio capture and transcription requests."""

import json
import os
import tempfile
import uuid

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, TemplateView

from .models import CaptureEntry


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
        return context
