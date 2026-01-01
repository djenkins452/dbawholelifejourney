"""
Life Module - Enhanced Google Calendar Integration

Syncs events between Life module and Google Calendar with configurable options.
"""

import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# Check for required dependencies
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    logger.warning("Google Calendar integration not available. Install: pip install google-auth google-auth-oauthlib google-api-python-client")


class GoogleCalendarService:
    """
    Service for Google Calendar integration.
    """

    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self):
        if not GOOGLE_AVAILABLE:
            raise ImportError(
                "Google Calendar integration requires: "
                "pip install google-auth google-auth-oauthlib google-api-python-client"
            )

        self.client_id = getattr(settings, 'GOOGLE_CALENDAR_CLIENT_ID', None)
        self.client_secret = getattr(settings, 'GOOGLE_CALENDAR_CLIENT_SECRET', None)
        self.redirect_uri = getattr(settings, 'GOOGLE_CALENDAR_REDIRECT_URI', None)

        # Log configuration for debugging OAuth issues
        logger.info(f"Google Calendar OAuth - Redirect URI: {self.redirect_uri}")

        if not all([self.client_id, self.client_secret, self.redirect_uri]):
            logger.error(
                f"Google Calendar not configured - "
                f"client_id: {'set' if self.client_id else 'missing'}, "
                f"client_secret: {'set' if self.client_secret else 'missing'}, "
                f"redirect_uri: {'set' if self.redirect_uri else 'missing'}"
            )
            raise ValueError(
                "Google Calendar settings not configured. "
                "Add GOOGLE_CALENDAR_CLIENT_ID, GOOGLE_CALENDAR_CLIENT_SECRET, "
                "and GOOGLE_CALENDAR_REDIRECT_URI to settings.py"
            )
    
    def get_authorization_url(self, state=None):
        """Get the OAuth2 authorization URL."""
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri],
                }
            },
            scopes=self.SCOPES,
        )
        flow.redirect_uri = self.redirect_uri
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=state,
            prompt='consent',
        )
        
        return authorization_url, state
    
    def exchange_code_for_credentials(self, code):
        """Exchange authorization code for credentials."""
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri],
                }
            },
            scopes=self.SCOPES,
        )
        flow.redirect_uri = self.redirect_uri
        flow.fetch_token(code=code)
        
        credentials = flow.credentials
        return {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': list(credentials.scopes),
            'expiry': credentials.expiry.isoformat() if credentials.expiry else None,
        }
    
    def get_calendar_service(self, credentials_dict):
        """Get a Calendar API service object."""
        credentials = Credentials(
            token=credentials_dict['token'],
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri=credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=credentials_dict.get('client_id', self.client_id),
            client_secret=credentials_dict.get('client_secret', self.client_secret),
            scopes=credentials_dict.get('scopes', self.SCOPES),
        )
        
        return build('calendar', 'v3', credentials=credentials)
    
    def list_calendars(self, credentials_dict):
        """List user's calendars."""
        service = self.get_calendar_service(credentials_dict)
        
        try:
            calendar_list = service.calendarList().list().execute()
            return calendar_list.get('items', [])
        except HttpError as e:
            logger.error(f"Error listing calendars: {e}")
            return []
    
    def get_events(self, credentials_dict, calendar_id='primary', time_min=None, time_max=None, max_results=500):
        """Get events from a Google Calendar."""
        service = self.get_calendar_service(credentials_dict)
        
        if time_min is None:
            time_min = timezone.now()
        if time_max is None:
            time_max = time_min + timedelta(days=30)
        
        # Ensure timezone info
        if time_min.tzinfo is None:
            time_min = timezone.make_aware(time_min)
        if time_max.tzinfo is None:
            time_max = timezone.make_aware(time_max)
        
        try:
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat(),
                timeMax=time_max.isoformat(),
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            return events_result.get('items', [])
        except HttpError as e:
            logger.error(f"Error getting events: {e}")
            return []
    
    def create_event(self, credentials_dict, event_data, calendar_id='primary'):
        """Create an event in Google Calendar."""
        service = self.get_calendar_service(credentials_dict)
        
        try:
            event = service.events().insert(
                calendarId=calendar_id,
                body=event_data
            ).execute()
            return event
        except HttpError as e:
            logger.error(f"Error creating event: {e}")
            return None
    
    def update_event(self, credentials_dict, event_id, event_data, calendar_id='primary'):
        """Update an event in Google Calendar."""
        service = self.get_calendar_service(credentials_dict)
        
        try:
            event = service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event_data
            ).execute()
            return event
        except HttpError as e:
            logger.error(f"Error updating event: {e}")
            return None
    
    def delete_event(self, credentials_dict, event_id, calendar_id='primary'):
        """Delete an event from Google Calendar."""
        service = self.get_calendar_service(credentials_dict)
        
        try:
            service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            return True
        except HttpError as e:
            logger.error(f"Error deleting event: {e}")
            return False


class CalendarSyncService:
    """
    Service for syncing events between Life module and Google Calendar.
    """
    
    def __init__(self, user):
        self.user = user
        self.google_service = GoogleCalendarService()
    
    def life_event_to_google(self, life_event):
        """Convert a LifeEvent to Google Calendar event format."""
        event = {
            'summary': life_event.title,
            'description': life_event.description,
            'location': life_event.location,
        }
        
        if life_event.is_all_day:
            event['start'] = {'date': life_event.start_date.isoformat()}
            end_date = life_event.end_date or life_event.start_date
            # Google all-day events end date is exclusive, so add 1 day
            end_date = end_date + timedelta(days=1)
            event['end'] = {'date': end_date.isoformat()}
        else:
            start_datetime = datetime.combine(
                life_event.start_date,
                life_event.start_time or datetime.min.time()
            )
            end_datetime = datetime.combine(
                life_event.end_date or life_event.start_date,
                life_event.end_time or life_event.start_time or datetime.min.time()
            )
            
            # Default to 1 hour duration if no end time
            if end_datetime <= start_datetime:
                end_datetime = start_datetime + timedelta(hours=1)
            
            tz_name = str(timezone.get_current_timezone())
            event['start'] = {
                'dateTime': start_datetime.isoformat(),
                'timeZone': tz_name,
            }
            event['end'] = {
                'dateTime': end_datetime.isoformat(),
                'timeZone': tz_name,
            }
        
        return event
    
    def google_event_to_life(self, google_event):
        """Convert a Google Calendar event to LifeEvent data."""
        start = google_event.get('start', {})
        end = google_event.get('end', {})
        
        is_all_day = 'date' in start
        
        if is_all_day:
            start_date = datetime.fromisoformat(start['date']).date()
            end_date = datetime.fromisoformat(end.get('date', start['date'])).date()
            # Google all-day end date is exclusive
            if end_date > start_date:
                end_date = end_date - timedelta(days=1)
            start_time = None
            end_time = None
        else:
            start_str = start.get('dateTime', '')
            end_str = end.get('dateTime', start_str)
            
            # Handle various datetime formats
            start_datetime = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            end_datetime = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            
            start_date = start_datetime.date()
            end_date = end_datetime.date()
            start_time = start_datetime.time()
            end_time = end_datetime.time()
        
        return {
            'title': google_event.get('summary', 'Untitled Event'),
            'description': google_event.get('description', ''),
            'location': google_event.get('location', ''),
            'start_date': start_date,
            'start_time': start_time,
            'end_date': end_date if end_date != start_date else None,
            'end_time': end_time,
            'is_all_day': is_all_day,
            'external_id': google_event['id'],
            'external_source': 'google',
        }
    
    def sync_to_google(self, life_event, credentials_dict, calendar_id='primary'):
        """Sync a single LifeEvent to Google Calendar."""
        event_data = self.life_event_to_google(life_event)
        
        if life_event.external_id and life_event.external_source == 'google':
            # Update existing event
            result = self.google_service.update_event(
                credentials_dict,
                life_event.external_id,
                event_data,
                calendar_id
            )
        else:
            # Create new event
            result = self.google_service.create_event(
                credentials_dict,
                event_data,
                calendar_id
            )
        
        if result:
            life_event.external_id = result['id']
            life_event.external_source = 'google'
            life_event.save(update_fields=['external_id', 'external_source', 'updated_at'])
            return result['id']
        
        return None
    
    def sync_to_google_bulk(self, credentials_dict, calendar_id='primary', days_past=0, days_ahead=30, event_types=None):
        """
        Export multiple LifeEvents to Google Calendar.
        
        Args:
            credentials_dict: Google credentials
            calendar_id: Target calendar
            days_past: How many days in the past to include
            days_ahead: How many days in the future to include
            event_types: List of event types to include (None = all)
        
        Returns:
            Number of events exported
        """
        from apps.life.models import LifeEvent
        
        today = timezone.now().date()
        start_date = today - timedelta(days=days_past)
        end_date = today + timedelta(days=days_ahead)
        
        # Get events to export
        queryset = LifeEvent.objects.filter(
            user=self.user,
            start_date__gte=start_date,
            start_date__lte=end_date,
        )
        
        # Filter by event types if specified
        if event_types:
            queryset = queryset.filter(event_type__in=event_types)
        
        exported_count = 0
        
        for event in queryset:
            result = self.sync_to_google(event, credentials_dict, calendar_id)
            if result:
                exported_count += 1
        
        return exported_count
    
    def sync_from_google(self, credentials_dict, calendar_id='primary', days_past=0, days_ahead=30):
        """
        Import events from Google Calendar.
        
        Args:
            credentials_dict: Google credentials
            calendar_id: Source calendar
            days_past: How many days in the past to include
            days_ahead: How many days in the future to include
        
        Returns:
            tuple: (created_count, updated_count)
        """
        from apps.life.models import LifeEvent
        
        today = timezone.now()
        time_min = today - timedelta(days=days_past)
        time_max = today + timedelta(days=days_ahead)
        
        google_events = self.google_service.get_events(
            credentials_dict,
            calendar_id,
            time_min,
            time_max
        )
        
        created_count = 0
        updated_count = 0
        
        with transaction.atomic():
            for g_event in google_events:
                # Skip cancelled events
                if g_event.get('status') == 'cancelled':
                    continue
                
                event_data = self.google_event_to_life(g_event)
                
                # Check if event already exists
                existing = LifeEvent.objects.filter(
                    user=self.user,
                    external_id=g_event['id'],
                    external_source='google'
                ).first()
                
                if existing:
                    # Update existing event
                    for key, value in event_data.items():
                        setattr(existing, key, value)
                    existing.save()
                    updated_count += 1
                else:
                    # Create new event
                    LifeEvent.objects.create(
                        user=self.user,
                        event_type='personal',  # Default type for imported events
                        **event_data
                    )
                    created_count += 1
        
        return created_count, updated_count