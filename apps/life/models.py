"""
Life Module Models

The Life module serves as the daily operating layer of a person's life.
It helps organize time, responsibilities, and household details with
a calm, long-term focus.
"""

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.models import UserOwnedModel

import json


# =============================================================================
# Projects
# =============================================================================

class Project(UserOwnedModel):
    """
    Long-running, meaningful efforts.
    
    Projects are about meaning, not speed. They can represent
    home projects, trips, learning goals, family legacy work, etc.
    """
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]
    
    PRIORITY_CHOICES = [
        ('now', 'Now'),
        ('soon', 'Soon'),
        ('someday', 'Someday'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(
        blank=True,
        help_text="What is this project about?"
    )
    purpose = models.TextField(
        blank=True,
        help_text="Why does this project matter to you?"
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='someday'
    )
    
    # Dates
    start_date = models.DateField(null=True, blank=True)
    target_date = models.DateField(
        null=True, 
        blank=True,
        help_text="When would you like to complete this?"
    )
    completed_date = models.DateField(null=True, blank=True)
    
    # Organization
    category = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g., Home, Travel, Learning, Family"
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags for organization"
    )
    
    # Optional cover image
    cover_image = models.ImageField(
        upload_to='life/projects/',
        blank=True,
        null=True
    )
    
    # Reflection after completion
    reflection = models.TextField(
        blank=True,
        help_text="What did you learn? How did it go?"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Project"
        verbose_name_plural = "Projects"
    
    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('life:project_detail', kwargs={'pk': self.pk})
    
    @property
    def is_overdue(self):
        if self.target_date and self.status == 'active':
            return self.target_date < timezone.now().date()
        return False
    
    @property
    def task_count(self):
        return self.tasks.count()
    
    @property
    def completed_task_count(self):
        return self.tasks.filter(is_completed=True).count()
    
    @property
    def progress_percentage(self):
        total = self.task_count
        if total == 0:
            return 0
        return int((self.completed_task_count / total) * 100)


# =============================================================================
# Tasks
# =============================================================================

class Task(UserOwnedModel):
    """
    Simple, human-prioritized tasks.

    Tasks can stand alone or belong to a project.
    Priority is automatically determined based on due date:
    - Now: Due today or overdue
    - Soon: Due within 7 days
    - Someday: No due date or due date > 7 days away
    """

    PRIORITY_CHOICES = [
        ('now', 'Now'),
        ('soon', 'Soon'),
        ('someday', 'Someday'),
    ]

    EFFORT_CHOICES = [
        ('quick', 'Quick (< 15 min)'),
        ('small', 'Small (< 1 hour)'),
        ('medium', 'Medium (1-3 hours)'),
        ('large', 'Large (half day+)'),
    ]

    title = models.CharField(max_length=300)
    notes = models.TextField(blank=True)

    # Organization
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='tasks',
        null=True,
        blank=True
    )

    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='someday'
    )
    effort = models.CharField(
        max_length=20,
        choices=EFFORT_CHOICES,
        blank=True
    )

    # Dates
    due_date = models.DateField(null=True, blank=True)
    
    # Completion
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Recurrence
    is_recurring = models.BooleanField(default=False)
    recurrence_pattern = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g., 'daily', 'weekly', 'monthly', 'yearly'"
    )
    
    class Meta:
        ordering = ['is_completed', 'priority', '-created_at']
        verbose_name = "Task"
        verbose_name_plural = "Tasks"
    
    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('life:task_detail', kwargs={'pk': self.pk})
    
    def mark_complete(self):
        """
        Mark task as completed.
        If recurring, automatically creates the next occurrence.
        """
        self.is_completed = True
        self.completed_at = timezone.now()
        self.save(update_fields=['is_completed', 'completed_at', 'updated_at'])
        
        # Handle recurrence
        if self.is_recurring and self.recurrence_pattern:
            from apps.life.services.recurrence import RecurrenceService
            RecurrenceService.process_completed_recurring_task(self)
    
    def mark_incomplete(self):
        """Mark task as not completed."""
        self.is_completed = False
        self.completed_at = None
        self.save(update_fields=['is_completed', 'completed_at', 'updated_at'])
    
    @property
    def is_overdue(self):
        if self.due_date and not self.is_completed:
            return self.due_date < timezone.now().date()
        return False

    def calculate_priority(self):
        """
        Calculate priority based on due date.

        Returns:
            str: 'now' if due today or overdue,
                 'soon' if due within 7 days,
                 'someday' if no due date or due > 7 days away
        """
        from datetime import timedelta

        if not self.due_date:
            return 'someday'

        today = timezone.now().date()
        days_until_due = (self.due_date - today).days

        if days_until_due <= 0:
            # Due today or overdue
            return 'now'
        elif days_until_due <= 7:
            # Due within the next 7 days
            return 'soon'
        else:
            # Due more than 7 days away
            return 'someday'

    def save(self, *args, **kwargs):
        """Override save to auto-calculate priority based on due date."""
        # Auto-calculate priority unless we're only updating specific fields
        update_fields = kwargs.get('update_fields')
        if update_fields is None or 'due_date' in update_fields:
            self.priority = self.calculate_priority()
            # If update_fields is specified, add priority to it
            if update_fields is not None and 'priority' not in update_fields:
                kwargs['update_fields'] = list(update_fields) + ['priority']
        super().save(*args, **kwargs)


# =============================================================================
# Life Events (Calendar)
# =============================================================================

class LifeEvent(UserOwnedModel):
    """
    Calendar events for personal, family, and household dates.
    
    Time is the backbone of the Life Module.
    """
    
    EVENT_TYPE_CHOICES = [
        ('personal', 'Personal'),
        ('family', 'Family'),
        ('household', 'Household'),
        ('faith', 'Faith'),
        ('health', 'Health'),
        ('work', 'Work'),
        ('social', 'Social'),
        ('travel', 'Travel'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
        default='personal'
    )
    
    # Timing
    start_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    is_all_day = models.BooleanField(default=False)
    
    # Location
    location = models.CharField(max_length=300, blank=True)
    
    # Recurrence
    is_recurring = models.BooleanField(default=False)
    recurrence_pattern = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g., 'daily', 'weekly', 'monthly', 'yearly'"
    )
    recurrence_end_date = models.DateField(null=True, blank=True)
    
    # Linking
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        related_name='events',
        null=True,
        blank=True
    )
    
    # External calendar sync
    external_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="ID from external calendar (Google, Outlook)"
    )
    external_source = models.CharField(
        max_length=50,
        blank=True,
        help_text="Source calendar provider"
    )
    
    # Reminders
    reminder_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minutes before event to send reminder"
    )
    
    class Meta:
        ordering = ['start_date', 'start_time']
        verbose_name = "Life Event"
        verbose_name_plural = "Life Events"
    
    def __str__(self):
        return f"{self.title} ({self.start_date})"
    
    def get_absolute_url(self):
        return reverse('life:event_detail', kwargs={'pk': self.pk})
    
    @property
    def is_past(self):
        return self.start_date < timezone.now().date()
    
    @property
    def is_today(self):
        return self.start_date == timezone.now().date()


# =============================================================================
# Home Inventory
# =============================================================================

class InventoryItem(UserOwnedModel):
    """
    Household items documented for insurance and peace of mind.
    """
    
    CONDITION_CHOICES = [
        ('new', 'New'),
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Categorization
    category = models.CharField(
        max_length=100,
        help_text="e.g., Electronics, Furniture, Appliances, Jewelry"
    )
    location = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g., Living Room, Garage, Master Bedroom"
    )
    
    # Value & Purchase
    purchase_date = models.DateField(null=True, blank=True)
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    estimated_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Current estimated value"
    )
    
    condition = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        default='good'
    )
    
    # Details
    brand = models.CharField(max_length=100, blank=True)
    model_number = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    
    # Warranty
    warranty_expiration = models.DateField(null=True, blank=True)
    warranty_info = models.TextField(blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['category', 'name']
        verbose_name = "Inventory Item"
        verbose_name_plural = "Inventory Items"
    
    def __str__(self):
        return f"{self.name} ({self.category})"
    
    def get_absolute_url(self):
        return reverse('life:inventory_detail', kwargs={'pk': self.pk})


class InventoryPhoto(models.Model):
    """Photos for inventory items."""
    
    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name='photos'
    )
    image = models.ImageField(upload_to='life/inventory/')
    caption = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-is_primary', '-uploaded_at']
    
    def __str__(self):
        return f"Photo for {self.item.name}"


# =============================================================================
# Home Maintenance
# =============================================================================

class MaintenanceLog(UserOwnedModel):
    """
    History of home repairs, upgrades, and service visits.
    
    Homes have memory. This preserves it.
    """
    
    LOG_TYPE_CHOICES = [
        ('repair', 'Repair'),
        ('maintenance', 'Maintenance'),
        ('upgrade', 'Upgrade'),
        ('service', 'Service Visit'),
        ('replacement', 'Replacement'),
        ('inspection', 'Inspection'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    log_type = models.CharField(
        max_length=20,
        choices=LOG_TYPE_CHOICES,
        default='maintenance'
    )
    
    # What was worked on
    area = models.CharField(
        max_length=100,
        help_text="e.g., HVAC, Plumbing, Roof, Kitchen"
    )
    
    # When
    date = models.DateField()
    
    # Cost
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Service provider
    provider = models.CharField(
        max_length=200,
        blank=True,
        help_text="Who did the work?"
    )
    provider_contact = models.CharField(max_length=200, blank=True)
    
    # Related items
    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.SET_NULL,
        related_name='maintenance_logs',
        null=True,
        blank=True
    )
    
    # Notes and follow-up
    notes = models.TextField(blank=True)
    follow_up_date = models.DateField(
        null=True,
        blank=True,
        help_text="When should this be done again?"
    )
    
    class Meta:
        ordering = ['-date']
        verbose_name = "Maintenance Log"
        verbose_name_plural = "Maintenance Logs"
    
    def __str__(self):
        return f"{self.title} ({self.date})"
    
    def get_absolute_url(self):
        return reverse('life:maintenance_detail', kwargs={'pk': self.pk})


# =============================================================================
# Pets
# =============================================================================

class Pet(UserOwnedModel):
    """
    Pet profiles - treating pets as family members.
    """
    
    SPECIES_CHOICES = [
        ('dog', 'Dog'),
        ('cat', 'Cat'),
        ('bird', 'Bird'),
        ('fish', 'Fish'),
        ('rabbit', 'Rabbit'),
        ('hamster', 'Hamster'),
        ('reptile', 'Reptile'),
        ('other', 'Other'),
    ]
    
    name = models.CharField(max_length=100)
    species = models.CharField(
        max_length=20,
        choices=SPECIES_CHOICES,
        default='dog'
    )
    breed = models.CharField(max_length=100, blank=True)
    
    # Details
    birth_date = models.DateField(null=True, blank=True)
    adoption_date = models.DateField(null=True, blank=True)
    color = models.CharField(max_length=100, blank=True)
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Weight in pounds"
    )
    
    # Medical
    microchip_id = models.CharField(max_length=100, blank=True)
    veterinarian = models.CharField(max_length=200, blank=True)
    vet_phone = models.CharField(max_length=20, blank=True)
    
    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Uncheck if pet has passed away"
    )
    passed_date = models.DateField(null=True, blank=True)
    
    # Photo
    photo = models.ImageField(
        upload_to='life/pets/',
        blank=True,
        null=True
    )
    
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-is_active', 'name']
        verbose_name = "Pet"
        verbose_name_plural = "Pets"
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('life:pet_detail', kwargs={'pk': self.pk})
    
    @property
    def age(self):
        if self.birth_date:
            today = timezone.now().date()
            years = today.year - self.birth_date.year
            if today.month < self.birth_date.month or (
                today.month == self.birth_date.month and today.day < self.birth_date.day
            ):
                years -= 1
            return years
        return None


class PetRecord(models.Model):
    """
    Vet visits, medications, and care records for pets.
    """
    
    RECORD_TYPE_CHOICES = [
        ('vet_visit', 'Vet Visit'),
        ('vaccination', 'Vaccination'),
        ('medication', 'Medication'),
        ('grooming', 'Grooming'),
        ('weight', 'Weight Check'),
        ('other', 'Other'),
    ]
    
    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        related_name='records'
    )
    
    record_type = models.CharField(
        max_length=20,
        choices=RECORD_TYPE_CHOICES,
        default='vet_visit'
    )
    
    date = models.DateField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Cost
    cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Follow-up
    next_due_date = models.DateField(
        null=True,
        blank=True,
        help_text="When is this needed again?"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date']
    
    def __str__(self):
        return f"{self.pet.name}: {self.title} ({self.date})"


# =============================================================================
# Recipes
# =============================================================================

class Recipe(UserOwnedModel):
    """
    Favorite recipes and family traditions.
    
    About preserving family culture, not just storing instructions.
    """
    
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(
        blank=True,
        help_text="Brief description or story behind this recipe"
    )
    
    # Recipe details
    ingredients = models.TextField(help_text="One ingredient per line")
    instructions = models.TextField()
    
    # Metadata
    prep_time_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Preparation time in minutes"
    )
    cook_time_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Cooking time in minutes"
    )
    servings = models.PositiveIntegerField(null=True, blank=True)
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        blank=True
    )
    
    # Organization
    category = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g., Breakfast, Dinner, Dessert, Holiday"
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text="Tags like 'vegetarian', 'quick', 'family-favorite'"
    )
    
    # Source
    source = models.CharField(
        max_length=200,
        blank=True,
        help_text="Where did this recipe come from?"
    )
    source_url = models.URLField(blank=True)
    
    # Image
    image = models.ImageField(
        upload_to='life/recipes/',
        blank=True,
        null=True
    )
    
    # Personal notes
    notes = models.TextField(
        blank=True,
        help_text="Your variations, tips, or memories"
    )
    
    # Favorites
    is_favorite = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-is_favorite', 'title']
        verbose_name = "Recipe"
        verbose_name_plural = "Recipes"
    
    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('life:recipe_detail', kwargs={'pk': self.pk})
    
    @property
    def total_time_minutes(self):
        prep = self.prep_time_minutes or 0
        cook = self.cook_time_minutes or 0
        return prep + cook if (prep or cook) else None


# =============================================================================
# Documents
# =============================================================================

class Document(UserOwnedModel):
    """
    Important document storage.
    
    For storing and organizing important family/household documents
    like insurance policies, warranties, contracts, manuals, etc.
    """
    
    CATEGORY_CHOICES = [
        ('insurance', 'Insurance'),
        ('legal', 'Legal Documents'),
        ('financial', 'Financial'),
        ('medical', 'Medical Records'),
        ('home', 'Home & Property'),
        ('vehicle', 'Vehicle'),
        ('education', 'Education'),
        ('identity', 'Identity Documents'),
        ('warranty', 'Warranties & Manuals'),
        ('tax', 'Tax Documents'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    category = models.CharField(
        max_length=30,
        choices=CATEGORY_CHOICES,
        default='other'
    )
    
    # File upload
    file = models.FileField(
        upload_to='life/documents/%Y/%m/',
        help_text="Upload document (PDF, image, or other file)"
    )
    file_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Auto-detected file type"
    )
    file_size = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="File size in bytes"
    )
    
    # Dates
    document_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date on the document (if applicable)"
    )
    expiration_date = models.DateField(
        null=True,
        blank=True,
        help_text="When does this document expire?"
    )
    
    # Organization
    tags = models.JSONField(
        default=list,
        blank=True
    )
    
    # Related items
    related_inventory_item = models.ForeignKey(
        'InventoryItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
        help_text="Link to inventory item (e.g., warranty for appliance)"
    )
    related_pet = models.ForeignKey(
        'Pet',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documents',
        help_text="Link to pet (e.g., vaccination records)"
    )
    
    # Notes
    notes = models.TextField(blank=True)
    
    # Archive
    is_archived = models.BooleanField(
        default=False,
        help_text="Archived documents are hidden from default view"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Document"
        verbose_name_plural = "Documents"
    
    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('life:document_detail', kwargs={'pk': self.pk})
    
    def save(self, *args, **kwargs):
        # Auto-detect file type and size
        if self.file:
            self.file_size = self.file.size
            name = self.file.name.lower()
            if name.endswith('.pdf'):
                self.file_type = 'pdf'
            elif name.endswith(('.jpg', '.jpeg')):
                self.file_type = 'image/jpeg'
            elif name.endswith('.png'):
                self.file_type = 'image/png'
            elif name.endswith(('.doc', '.docx')):
                self.file_type = 'word'
            elif name.endswith(('.xls', '.xlsx')):
                self.file_type = 'excel'
            else:
                self.file_type = 'other'
        super().save(*args, **kwargs)
    
    @property
    def is_expiring_soon(self):
        """Check if document expires within 30 days."""
        if self.expiration_date:
            from datetime import timedelta
            return self.expiration_date <= timezone.now().date() + timedelta(days=30)
        return False
    
    @property
    def is_expired(self):
        """Check if document is expired."""
        if self.expiration_date:
            return self.expiration_date < timezone.now().date()
        return False
    
    @property
    def file_size_display(self):
        """Human-readable file size."""
        if not self.file_size:
            return ""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"


# =============================================================================
# Google Calendar Integration
# =============================================================================

class GoogleCalendarCredential(models.Model):
    """
    Store Google Calendar OAuth credentials in the database.
    
    This ensures tokens persist across sessions and can be refreshed properly.
    """
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_calendar_credential'
    )
    
    # OAuth tokens
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True)
    token_uri = models.CharField(max_length=500, default='https://oauth2.googleapis.com/token')
    client_id = models.CharField(max_length=500)
    client_secret = models.CharField(max_length=500)
    
    # Token expiration
    token_expiry = models.DateTimeField(null=True, blank=True)
    
    # Scopes granted
    scopes = models.TextField(
        blank=True,
        help_text="JSON list of OAuth scopes"
    )
    
    # Sync settings
    selected_calendar_id = models.CharField(
        max_length=500, 
        default='primary',
        help_text="Google Calendar ID to sync with"
    )
    selected_calendar_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Display name of selected calendar"
    )
    
    SYNC_DIRECTION_CHOICES = [
        ('import', 'Import Only (Google → App)'),
        ('export', 'Export Only (App → Google)'),
        ('both', 'Two-Way Sync'),
    ]
    sync_direction = models.CharField(
        max_length=20,
        choices=SYNC_DIRECTION_CHOICES,
        default='import'
    )
    
    days_past = models.PositiveIntegerField(
        default=0,
        help_text="Days in the past to sync"
    )
    days_future = models.PositiveIntegerField(
        default=30,
        help_text="Days in the future to sync"
    )
    
    # Which event types to sync
    sync_event_types = models.TextField(
        default='["personal", "family", "work", "health", "social", "travel"]',
        help_text="JSON list of event types to sync"
    )
    
    auto_sync_enabled = models.BooleanField(
        default=False,
        help_text="Automatically sync on page load"
    )
    
    # Tracking
    last_sync = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=50, blank=True)
    last_sync_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Google Calendar Credential"
        verbose_name_plural = "Google Calendar Credentials"
    
    def __str__(self):
        return f"Google Calendar for {self.user}"
    
    @property
    def is_token_expired(self):
        """Check if the access token has expired."""
        if not self.token_expiry:
            return True
        return timezone.now() >= self.token_expiry
    
    @property
    def is_connected(self):
        """Check if we have valid credentials."""
        return bool(self.access_token)
    
    def get_credentials_dict(self):
        """Return credentials in the format expected by Google API."""
        return {
            'token': self.access_token,
            'refresh_token': self.refresh_token,
            'token_uri': self.token_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scopes': self.get_scopes_list(),
        }
    
    def update_from_credentials(self, credentials_dict):
        """Update model from a credentials dictionary."""
        self.access_token = credentials_dict.get('token', '')
        self.refresh_token = credentials_dict.get('refresh_token', self.refresh_token)
        self.token_uri = credentials_dict.get('token_uri', self.token_uri)
        self.client_id = credentials_dict.get('client_id', self.client_id)
        self.client_secret = credentials_dict.get('client_secret', self.client_secret)
        
        # Handle expiry
        expiry = credentials_dict.get('expiry')
        if expiry:
            if isinstance(expiry, str):
                from datetime import datetime
                self.token_expiry = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            else:
                self.token_expiry = expiry
        
        if credentials_dict.get('scopes'):
            self.set_scopes_list(credentials_dict['scopes'])
        
        self.save()
    
    def get_scopes_list(self):
        """Get scopes as a Python list."""
        if not self.scopes:
            return []
        try:
            return json.loads(self.scopes)
        except json.JSONDecodeError:
            return []
    
    def set_scopes_list(self, scopes_list):
        """Set scopes from a Python list."""
        self.scopes = json.dumps(scopes_list)
    
    def get_sync_event_types(self):
        """Get sync event types as a Python list."""
        try:
            return json.loads(self.sync_event_types)
        except json.JSONDecodeError:
            return ['personal', 'family', 'work', 'health', 'social', 'travel']
    
    def set_sync_event_types(self, types_list):
        """Set sync event types from a Python list."""
        self.sync_event_types = json.dumps(types_list)
    
    def record_sync(self, success=True, message=''):
        """Record the result of a sync operation."""
        self.last_sync = timezone.now()
        self.last_sync_status = 'success' if success else 'error'
        self.last_sync_message = message
        self.save(update_fields=['last_sync', 'last_sync_status', 'last_sync_message'])