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
from apps.core.utils import get_user_today

import json


def get_document_storage():
    """
    Return the appropriate storage backend for document files.

    Uses RawMediaCloudinaryStorage for Cloudinary (handles PDFs and raw files properly)
    or falls back to default FileSystemStorage for local development.
    """
    from django.conf import settings

    # Check if Cloudinary is configured
    cloudinary_settings = getattr(settings, 'CLOUDINARY_STORAGE', None)
    if cloudinary_settings and cloudinary_settings.get('CLOUD_NAME'):
        try:
            from cloudinary_storage.storage import RawMediaCloudinaryStorage
            return RawMediaCloudinaryStorage()
        except ImportError:
            pass

    # Fall back to default storage
    from django.core.files.storage import default_storage
    return default_storage


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
            user_today = get_user_today(self.user) if self.user_id else timezone.now().date()
            return self.target_date < user_today
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

    # Partial progress (Phase 1 — CoS Foundational Restructure)
    progress_percentage = models.PositiveSmallIntegerField(
        default=0,
        help_text="0-100 progress percentage. >0 counts as 'worked on' for conflict detection.",
    )
    progress_state = models.JSONField(
        default=dict,
        blank=True,
        help_text="Flexible progress state (e.g. steps completed, notes on progress)",
    )

    # Recurrence
    is_recurring = models.BooleanField(default=False)
    recurrence_pattern = models.CharField(
        max_length=50,
        blank=True,
        help_text="e.g., 'daily', 'weekly', 'monthly', 'yearly'"
    )
    # For recurring tasks: the date range during which the task repeats
    start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Start date for recurring tasks"
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="End date for recurring tasks (optional)"
    )

    # Email source tracking (for Gmail integration)
    email_source_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Gmail message ID if created from email"
    )
    email_source_subject = models.CharField(
        max_length=500,
        blank=True,
        help_text="Original email subject"
    )
    email_source_sender = models.CharField(
        max_length=255,
        blank=True,
        help_text="Original email sender"
    )
    email_source_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Original email date"
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
            user_today = get_user_today(self.user) if self.user_id else timezone.now().date()
            return self.due_date < user_today
        return False

    def calculate_priority(self, user_today=None):
        """
        Calculate priority based on due date using user's timezone.

        Args:
            user_today: Optional date to use as "today". If not provided,
                       uses the user's timezone from preferences.

        Returns:
            str: 'now' if due today or overdue,
                 'soon' if due within 7 days,
                 'someday' if no due date or due > 7 days away
        """
        if not self.due_date:
            return 'someday'

        # Use provided today, or calculate from user's timezone
        if user_today is None:
            user_today = get_user_today(self.user) if self.user_id else timezone.now().date()

        days_until_due = (self.due_date - user_today).days

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
        """
        Override save to:
        1. Auto-set due_date for recurring tasks from start_date
        2. Auto-calculate priority based on due date
        """
        # For new recurring tasks, set due_date from start_date if not already set
        if self.is_recurring and self.start_date and not self.due_date:
            self.due_date = self.start_date

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
        user_today = get_user_today(self.user) if self.user_id else timezone.now().date()
        return self.start_date < user_today

    @property
    def is_today(self):
        user_today = get_user_today(self.user) if self.user_id else timezone.now().date()
        return self.start_date == user_today


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
            user_today = get_user_today(self.user) if self.user_id else timezone.now().date()
            years = user_today.year - self.birth_date.year
            if user_today.month < self.birth_date.month or (
                user_today.month == self.birth_date.month and user_today.day < self.birth_date.day
            ):
                years -= 1
            return years
        return None

    def create_or_update_birthday_event(self):
        """
        Create or update a SignificantEvent for this pet's birthday.

        - Living pets get a 'birthday' event
        - Passed pets get a 'memorial' event (remembering them)
        - If pet has no birth_date, any existing event is deleted

        Returns:
            SignificantEvent or None
        """
        if not self.birth_date:
            # Remove any existing birthday event for this pet
            SignificantEvent.objects.filter(
                user=self.user,
                title__icontains=f"{self.name}'s Birthday",
                event_type__in=['birthday', 'memorial'],
            ).delete()
            return None

        # Determine event type based on pet status
        if self.is_active:
            event_type = 'birthday'
            title = f"{self.name}'s Birthday"
            description = f"🎂 Celebrate {self.name}'s birthday!"
        else:
            event_type = 'memorial'
            title = f"Remembering {self.name}"
            if self.passed_date:
                description = f"🌈 In loving memory of {self.name}, who passed on {self.passed_date.strftime('%B %d, %Y')}."
            else:
                description = f"🌈 In loving memory of {self.name}."

        # Try to find existing event for this pet
        # Match by title pattern (case-insensitive contains name)
        existing = SignificantEvent.objects.filter(
            user=self.user,
            event_date__month=self.birth_date.month,
            event_date__day=self.birth_date.day,
        ).filter(
            models.Q(title__icontains=self.name) |
            models.Q(person_name__iexact=self.name)
        ).first()

        if existing:
            # Update existing event
            existing.title = title
            existing.description = description
            existing.event_type = event_type
            existing.person_name = self.name
            existing.original_year = self.birth_date.year
            existing.save()
            return existing
        else:
            # Create new event
            event = SignificantEvent.objects.create(
                user=self.user,
                title=title,
                description=description,
                event_type=event_type,
                event_date=self.birth_date,
                original_year=self.birth_date.year,
                person_name=self.name,
                reminder_days=[7, 1, 0],  # Remind 1 week, 1 day, and day-of
            )
            return event


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
    
    # File upload - uses RawMediaCloudinaryStorage for PDFs and raw files
    file = models.FileField(
        upload_to='life/documents/%Y/%m/',
        storage=get_document_storage,
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
            user_today = get_user_today(self.user) if self.user_id else timezone.now().date()
            return self.expiration_date <= user_today + timedelta(days=30)
        return False

    @property
    def is_expired(self):
        """Check if document is expired."""
        if self.expiration_date:
            user_today = get_user_today(self.user) if self.user_id else timezone.now().date()
            return self.expiration_date < user_today
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

    Security Note (CISO Review 2026-01-12):
        OAuth tokens are encrypted at rest using Fernet AES-256 encryption.
        Use the property accessors (access_token_decrypted, etc.) to get
        plaintext values. Raw database fields contain encrypted data.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_calendar_credential'
    )

    # OAuth tokens (encrypted at rest)
    # Use the _decrypted property accessors for plaintext values
    access_token = models.TextField(help_text="Encrypted access token")
    refresh_token = models.TextField(blank=True, help_text="Encrypted refresh token")
    token_uri = models.CharField(max_length=500, default='https://oauth2.googleapis.com/token')
    client_id = models.CharField(max_length=500)
    client_secret = models.CharField(max_length=500, help_text="Encrypted client secret")
    
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

    # =========================================================================
    # Encrypted Token Accessors (CISO Review 2026-01-12)
    # =========================================================================

    @property
    def access_token_decrypted(self):
        """Get the decrypted access token."""
        from apps.core.encryption import decrypt_oauth_token_safe
        value, success = decrypt_oauth_token_safe(self.access_token)
        if not success:
            self._decryption_failed = True
        return value

    @property
    def refresh_token_decrypted(self):
        """Get the decrypted refresh token."""
        from apps.core.encryption import decrypt_oauth_token_safe
        value, success = decrypt_oauth_token_safe(self.refresh_token)
        if not success:
            self._decryption_failed = True
        return value

    @property
    def client_secret_decrypted(self):
        """Get the decrypted client secret."""
        from apps.core.encryption import decrypt_oauth_token_safe
        value, success = decrypt_oauth_token_safe(self.client_secret)
        if not success:
            self._decryption_failed = True
        return value

    def has_decryption_error(self):
        """
        Check if any token decryption has failed.

        This should be called after accessing decrypted properties to determine
        if the credentials need to be re-authenticated.

        Returns:
            bool: True if decryption failed, False otherwise
        """
        # Reset flag and test all tokens
        self._decryption_failed = False
        from apps.core.encryption import decrypt_oauth_token_safe

        for field in [self.access_token, self.refresh_token, self.client_secret]:
            if field:
                _, success = decrypt_oauth_token_safe(field)
                if not success:
                    return True
        return False

    def set_access_token(self, plaintext):
        """Set and encrypt the access token."""
        from apps.core.encryption import encrypt_oauth_token
        self.access_token = encrypt_oauth_token(plaintext)

    def set_refresh_token(self, plaintext):
        """Set and encrypt the refresh token."""
        from apps.core.encryption import encrypt_oauth_token
        self.refresh_token = encrypt_oauth_token(plaintext) if plaintext else ''

    def set_client_secret(self, plaintext):
        """Set and encrypt the client secret."""
        from apps.core.encryption import encrypt_oauth_token
        self.client_secret = encrypt_oauth_token(plaintext)

    def get_credentials_dict(self):
        """Return credentials in the format expected by Google API."""
        return {
            'token': self.access_token_decrypted,
            'refresh_token': self.refresh_token_decrypted,
            'token_uri': self.token_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret_decrypted,
            'scopes': self.get_scopes_list(),
        }

    def update_from_credentials(self, credentials_dict):
        """Update model from a credentials dictionary (encrypts tokens)."""
        if 'token' in credentials_dict:
            self.set_access_token(credentials_dict.get('token', ''))
        if 'refresh_token' in credentials_dict:
            self.set_refresh_token(credentials_dict.get('refresh_token', ''))
        self.token_uri = credentials_dict.get('token_uri', self.token_uri)
        self.client_id = credentials_dict.get('client_id', self.client_id)
        if 'client_secret' in credentials_dict:
            self.set_client_secret(credentials_dict.get('client_secret', ''))

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


# =============================================================================
# Significant Events (Birthdays, Anniversaries, etc.)
# =============================================================================

class SignificantEvent(UserOwnedModel):
    """
    Significant recurring events like birthdays, anniversaries, and milestones.

    These events automatically recur annually and can trigger SMS reminders
    at configurable intervals before the event date.
    """

    EVENT_TYPE_CHOICES = [
        ('birthday', 'Birthday'),
        ('anniversary', 'Anniversary'),
        ('memorial', 'Memorial / In Memory'),
        ('milestone', 'Milestone'),
        ('holiday', 'Personal Holiday'),
        ('other', 'Other'),
    ]

    # Core fields
    title = models.CharField(
        max_length=200,
        help_text="e.g., Mom's Birthday, Wedding Anniversary"
    )
    description = models.TextField(
        blank=True,
        help_text="Optional notes about this event"
    )

    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPE_CHOICES,
        default='birthday'
    )

    # The event date (month/day matter most, year used for age/years calculation)
    event_date = models.DateField(
        help_text="The date of the event (year used for calculating years/age)"
    )

    # Optional: Track the original year for "years since" calculation
    # If not set, uses event_date.year
    original_year = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Year the event started (for calculating anniversaries, ages)"
    )

    # Person/entity this relates to
    person_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="e.g., Mom, John & Jane, Grandpa"
    )

    # Optional link to AI Relationships Person record (backward-compatible)
    person = models.ForeignKey(
        'ai_relationships.Person',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='significant_events',
        help_text="Optional link to tracked Person record",
    )

    # SMS Reminder Settings
    sms_reminder_enabled = models.BooleanField(
        default=False,
        help_text="Send SMS reminders for this event"
    )

    # Reminder days before event (stored as JSON array)
    # e.g., [14, 7, 3, 1, 0] for reminders at 14 days, 7 days, 3 days, 1 day, and day-of
    reminder_days = models.JSONField(
        default=list,
        blank=True,
        help_text="Days before event to send reminders (e.g., [7, 3, 1, 0])"
    )

    # Custom message to include in SMS
    custom_message = models.TextField(
        blank=True,
        help_text="Custom message to include in reminders (e.g., Gift ideas: Books, flowers)"
    )

    class Meta:
        ordering = ['event_date']
        verbose_name = "Significant Event"
        verbose_name_plural = "Significant Events"

    def __str__(self):
        return f"{self.title} ({self.event_date.strftime('%b %d')})"

    def get_absolute_url(self):
        return reverse('life:significant_event_detail', kwargs={'pk': self.pk})

    def get_next_occurrence(self, from_date=None):
        """
        Calculate the next occurrence of this event.

        Args:
            from_date: Date to calculate from (defaults to user's today)

        Returns:
            date: The next occurrence date
        """
        if from_date is None:
            from_date = get_user_today(self.user) if self.user_id else timezone.now().date()

        # Get month and day from the event
        event_month = self.event_date.month
        event_day = self.event_date.day

        # Handle Feb 29 for non-leap years
        def get_valid_date(year, month, day):
            import calendar
            max_day = calendar.monthrange(year, month)[1]
            return timezone.datetime(year, month, min(day, max_day)).date()

        # Try this year first
        this_year_date = get_valid_date(from_date.year, event_month, event_day)

        if this_year_date >= from_date:
            return this_year_date
        else:
            # Event has passed this year, return next year's date
            return get_valid_date(from_date.year + 1, event_month, event_day)

    def get_years_count(self, from_date=None):
        """
        Calculate how many years since the original event.

        Returns:
            int or None: Years count, or None if no original year set
        """
        # Use original_year if set, otherwise use the event_date year
        start_year = self.original_year or self.event_date.year

        if from_date is None:
            from_date = get_user_today(self.user) if self.user_id else timezone.now().date()

        next_occurrence = self.get_next_occurrence(from_date)
        years = next_occurrence.year - start_year

        return years if years > 0 else None

    def days_until_next(self, from_date=None):
        """
        Calculate days until the next occurrence.

        Returns:
            int: Days until next occurrence (0 = today)
        """
        if from_date is None:
            from_date = get_user_today(self.user) if self.user_id else timezone.now().date()

        next_occurrence = self.get_next_occurrence(from_date)
        return (next_occurrence - from_date).days

    @property
    def is_today(self):
        """Check if this event is today."""
        return self.days_until_next() == 0

    @property
    def is_this_week(self):
        """Check if this event is within the next 7 days."""
        return self.days_until_next() <= 7

    @property
    def is_this_month(self):
        """Check if this event is within the next 30 days."""
        return self.days_until_next() <= 30

    def get_display_date(self):
        """
        Get a human-friendly display of the event date.

        Returns:
            str: e.g., "Tomorrow", "Jan 15", "In 3 days"
        """
        days = self.days_until_next()
        next_date = self.get_next_occurrence()

        if days == 0:
            return "Today"
        elif days == 1:
            return "Tomorrow"
        elif days <= 7:
            return f"In {days} days"
        else:
            return next_date.strftime('%b %d')

    def get_years_display(self):
        """
        Get a human-friendly display of years count.

        Returns:
            str or None: e.g., "10th", "25th", or None
        """
        years = self.get_years_count()
        if years is None:
            return None

        # Handle ordinal suffix
        if 11 <= years % 100 <= 13:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(years % 10, 'th')

        return f"{years}{suffix}"

    def get_reminder_days_list(self):
        """Get reminder days as a sorted list."""
        if not self.reminder_days:
            return []
        return sorted(self.reminder_days, reverse=True)


# =============================================================================
# Gmail Integration
# =============================================================================

class GmailCredential(models.Model):
    """
    Store Gmail OAuth credentials for inbox scanning.

    Follows OAuth 2.0 pattern matching GoogleCalendarCredential.

    Security Note (CISO Review):
        OAuth tokens are encrypted at rest using Fernet AES-256 encryption.
        Use property accessors (access_token_decrypted, etc.) for plaintext.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gmail_credential'
    )

    # OAuth tokens (encrypted at rest)
    access_token = models.TextField(help_text="Encrypted access token")
    refresh_token = models.TextField(blank=True, help_text="Encrypted refresh token")
    token_uri = models.CharField(
        max_length=500,
        default='https://oauth2.googleapis.com/token'
    )
    client_id = models.CharField(max_length=500)
    client_secret = models.CharField(max_length=500, help_text="Encrypted")
    token_expiry = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(blank=True, help_text="JSON list of OAuth scopes")

    # Sync settings
    scan_enabled = models.BooleanField(
        default=True,
        help_text="Enable automatic inbox scanning"
    )
    max_emails_per_scan = models.PositiveIntegerField(
        default=20,
        help_text="Maximum emails to process per scan"
    )
    days_to_look_back = models.PositiveIntegerField(
        default=3,
        help_text="Only scan emails from the last N days"
    )

    # Tracking
    last_scan = models.DateTimeField(null=True, blank=True)
    last_scan_status = models.CharField(max_length=50, blank=True)
    last_scan_message = models.TextField(blank=True)
    last_scan_tasks_created = models.PositiveIntegerField(default=0)
    last_scan_errors = models.TextField(blank=True, help_text="JSON list of errors")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Gmail Credential"
        verbose_name_plural = "Gmail Credentials"

    def __str__(self):
        return f"Gmail for {self.user}"

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

    # =========================================================================
    # Encrypted Token Accessors
    # =========================================================================

    @property
    def access_token_decrypted(self):
        """Get the decrypted access token."""
        from apps.core.encryption import decrypt_oauth_token_safe
        value, success = decrypt_oauth_token_safe(self.access_token)
        if not success:
            self._decryption_failed = True
        return value

    @property
    def refresh_token_decrypted(self):
        """Get the decrypted refresh token."""
        from apps.core.encryption import decrypt_oauth_token_safe
        value, success = decrypt_oauth_token_safe(self.refresh_token)
        if not success:
            self._decryption_failed = True
        return value

    @property
    def client_secret_decrypted(self):
        """Get the decrypted client secret."""
        from apps.core.encryption import decrypt_oauth_token_safe
        value, success = decrypt_oauth_token_safe(self.client_secret)
        if not success:
            self._decryption_failed = True
        return value

    def has_decryption_error(self):
        """Check if any token decryption has failed."""
        self._decryption_failed = False
        from apps.core.encryption import decrypt_oauth_token_safe

        for field in [self.access_token, self.refresh_token, self.client_secret]:
            if field:
                _, success = decrypt_oauth_token_safe(field)
                if not success:
                    return True
        return False

    def set_access_token(self, plaintext):
        """Set and encrypt the access token."""
        from apps.core.encryption import encrypt_oauth_token
        self.access_token = encrypt_oauth_token(plaintext)

    def set_refresh_token(self, plaintext):
        """Set and encrypt the refresh token."""
        from apps.core.encryption import encrypt_oauth_token
        self.refresh_token = encrypt_oauth_token(plaintext) if plaintext else ''

    def set_client_secret(self, plaintext):
        """Set and encrypt the client secret."""
        from apps.core.encryption import encrypt_oauth_token
        self.client_secret = encrypt_oauth_token(plaintext)

    def get_credentials_dict(self):
        """Return credentials in the format expected by Google API."""
        return {
            'token': self.access_token_decrypted,
            'refresh_token': self.refresh_token_decrypted,
            'token_uri': self.token_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret_decrypted,
            'scopes': self.get_scopes_list(),
        }

    def update_from_credentials(self, credentials_dict):
        """Update model from a credentials dictionary (encrypts tokens)."""
        if 'token' in credentials_dict:
            self.set_access_token(credentials_dict.get('token', ''))
        if 'refresh_token' in credentials_dict:
            self.set_refresh_token(credentials_dict.get('refresh_token', ''))
        self.token_uri = credentials_dict.get('token_uri', self.token_uri)
        self.client_id = credentials_dict.get('client_id', self.client_id)
        if 'client_secret' in credentials_dict:
            self.set_client_secret(credentials_dict.get('client_secret', ''))

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

    def record_scan(self, success=True, message='', tasks_created=0, errors=None):
        """Record the result of a scan operation."""
        self.last_scan = timezone.now()
        self.last_scan_status = 'success' if success else 'error'
        self.last_scan_message = message
        self.last_scan_tasks_created = tasks_created
        self.last_scan_errors = json.dumps(errors) if errors else ''
        self.save(update_fields=[
            'last_scan', 'last_scan_status', 'last_scan_message',
            'last_scan_tasks_created', 'last_scan_errors'
        ])


class ProcessedEmail(models.Model):
    """
    Track which emails have been processed to prevent duplicates.

    Each processed email is recorded with its Gmail message ID so we
    don't re-process the same email multiple times.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='processed_emails'
    )
    gmail_message_id = models.CharField(max_length=255, db_index=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    # Result tracking
    action_items_found = models.PositiveIntegerField(default=0)
    tasks_created = models.PositiveIntegerField(default=0)
    skipped_reason = models.CharField(
        max_length=100,
        blank=True,
        help_text="e.g., 'no_action_items', 'ai_error'"
    )

    class Meta:
        unique_together = ['user', 'gmail_message_id']
        ordering = ['-processed_at']
        verbose_name = "Processed Email"
        verbose_name_plural = "Processed Emails"

    def __str__(self):
        return f"Email {self.gmail_message_id} for {self.user}"


# =============================================================================
# Shopping List & Items
# =============================================================================

SHOPPING_CATEGORY_CHOICES = [
    ("produce", "Produce"),
    ("protein", "Protein"),
    ("dairy", "Dairy"),
    ("grains", "Grains"),
    ("frozen", "Frozen"),
    ("pantry", "Pantry"),
    ("beverages", "Beverages"),
    ("supplements", "Supplements"),
    ("household", "Household"),
    ("other", "Other"),
]


class ShoppingList(UserOwnedModel):
    """
    A shopping list for organizing grocery and meal prep purchases.

    Integrates with the transformation protocol for nutrition planning.
    """

    name = models.CharField(
        max_length=200,
        help_text="List name (e.g., 'Week 3 Meal Prep', 'Protein Sources')",
    )
    is_completed = models.BooleanField(
        default=False,
        help_text="Whether all items have been purchased",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the list was completed",
    )
    notes = models.TextField(blank=True, help_text="Shopping list notes")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "shopping list"
        verbose_name_plural = "shopping lists"

    def __str__(self):
        return self.name

    @property
    def item_count(self):
        return self.items.count()

    @property
    def purchased_count(self):
        return self.items.filter(is_purchased=True).count()

    @property
    def progress_percent(self):
        total = self.item_count
        if total == 0:
            return 0
        return round(self.purchased_count / total * 100)


class ShoppingItem(UserOwnedModel):
    """
    An individual item on a shopping list.
    """

    shopping_list = models.ForeignKey(
        ShoppingList,
        on_delete=models.CASCADE,
        related_name="items",
    )
    name = models.CharField(
        max_length=200,
        help_text="Item name",
    )
    quantity = models.CharField(
        max_length=50,
        blank=True,
        help_text="Quantity (e.g., '2 lbs', '1 dozen', '3')",
    )
    category = models.CharField(
        max_length=20,
        choices=SHOPPING_CATEGORY_CHOICES,
        default="other",
    )
    is_purchased = models.BooleanField(
        default=False,
    )
    purchased_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["is_purchased", "category", "name"]
        verbose_name = "shopping item"
        verbose_name_plural = "shopping items"

    def __str__(self):
        return f"{self.name} ({self.quantity})" if self.quantity else self.name