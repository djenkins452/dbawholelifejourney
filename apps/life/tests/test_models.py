"""
Life Module Model Tests

Tests for Life module models: Project, Task, LifeEvent, etc.

Location: apps/life/tests/test_models.py
"""

from datetime import date, time, timedelta
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.life.models import (
    Project, Task, LifeEvent, InventoryItem, 
    MaintenanceLog, Pet, Recipe, Document
)

User = get_user_model()


class ProjectModelTest(TestCase):
    """Tests for the Project model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_project(self):
        """Project can be created with required fields."""
        project = Project.objects.create(
            user=self.user,
            title='Home Renovation',
            description='Update the kitchen'
        )
        self.assertEqual(project.title, 'Home Renovation')
        self.assertEqual(project.user, self.user)
        self.assertEqual(project.status, 'active')  # default
    
    def test_project_str(self):
        """Project string representation is title."""
        project = Project.objects.create(
            user=self.user,
            title='Test Project'
        )
        self.assertEqual(str(project), 'Test Project')
    
    def test_project_is_overdue(self):
        """is_overdue returns True when past target date."""
        project = Project.objects.create(
            user=self.user,
            title='Overdue Project',
            status='active',
            target_date=date.today() - timedelta(days=1)
        )
        self.assertTrue(project.is_overdue)
    
    def test_project_not_overdue_when_completed(self):
        """Completed projects are not overdue."""
        project = Project.objects.create(
            user=self.user,
            title='Done Project',
            status='completed',
            target_date=date.today() - timedelta(days=1)
        )
        self.assertFalse(project.is_overdue)
    
    def test_project_progress_with_no_tasks(self):
        """Progress is 0 when no tasks."""
        project = Project.objects.create(
            user=self.user,
            title='Empty Project'
        )
        self.assertEqual(project.progress_percentage, 0)
    
    def test_project_progress_with_tasks(self):
        """Progress calculated correctly from tasks."""
        project = Project.objects.create(
            user=self.user,
            title='Project with Tasks'
        )
        # Create 4 tasks, 2 completed
        for i in range(4):
            Task.objects.create(
                user=self.user,
                title=f'Task {i}',
                project=project,
                is_completed=(i < 2)
            )
        self.assertEqual(project.progress_percentage, 50)


class TaskModelTest(TestCase):
    """Tests for the Task model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_task(self):
        """Task can be created with required fields."""
        task = Task.objects.create(
            user=self.user,
            title='Buy groceries'
        )
        self.assertEqual(task.title, 'Buy groceries')
        self.assertFalse(task.is_completed)
    
    def test_task_str(self):
        """Task string representation is title."""
        task = Task.objects.create(
            user=self.user,
            title='Test Task'
        )
        self.assertEqual(str(task), 'Test Task')
    
    def test_mark_complete(self):
        """mark_complete() sets completion status and timestamp."""
        task = Task.objects.create(
            user=self.user,
            title='Complete me'
        )
        task.mark_complete()
        
        self.assertTrue(task.is_completed)
        self.assertIsNotNone(task.completed_at)
    
    def test_mark_incomplete(self):
        """mark_incomplete() clears completion status."""
        task = Task.objects.create(
            user=self.user,
            title='Toggle me',
            is_completed=True,
            completed_at=timezone.now()
        )
        task.mark_incomplete()
        
        self.assertFalse(task.is_completed)
        self.assertIsNone(task.completed_at)
    
    def test_task_is_overdue(self):
        """is_overdue returns True when past due date."""
        task = Task.objects.create(
            user=self.user,
            title='Overdue task',
            due_date=date.today() - timedelta(days=1)
        )
        self.assertTrue(task.is_overdue)
    
    def test_completed_task_not_overdue(self):
        """Completed tasks are not overdue."""
        task = Task.objects.create(
            user=self.user,
            title='Done task',
            due_date=date.today() - timedelta(days=1),
            is_completed=True
        )
        self.assertFalse(task.is_overdue)


class LifeEventModelTest(TestCase):
    """Tests for the LifeEvent model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_event(self):
        """Event can be created with required fields."""
        event = LifeEvent.objects.create(
            user=self.user,
            title='Doctor Appointment',
            start_date=date.today()
        )
        self.assertEqual(event.title, 'Doctor Appointment')
        self.assertEqual(event.event_type, 'personal')  # default
    
    def test_event_str(self):
        """Event string representation includes title and date."""
        event = LifeEvent.objects.create(
            user=self.user,
            title='Meeting',
            start_date=date(2025, 1, 15)
        )
        self.assertIn('Meeting', str(event))
        self.assertIn('2025-01-15', str(event))
    
    def test_event_is_today(self):
        """is_today returns True for today's events."""
        from django.utils import timezone
        # Use timezone.now().date() to match the model's is_today logic
        event = LifeEvent.objects.create(
            user=self.user,
            title='Today Event',
            start_date=timezone.now().date()
        )
        self.assertTrue(event.is_today)
    
    def test_event_is_past(self):
        """is_past returns True for past events."""
        event = LifeEvent.objects.create(
            user=self.user,
            title='Past Event',
            start_date=date.today() - timedelta(days=1)
        )
        self.assertTrue(event.is_past)
    
    def test_all_day_event(self):
        """All day events have no specific time."""
        event = LifeEvent.objects.create(
            user=self.user,
            title='All Day Event',
            start_date=date.today(),
            is_all_day=True
        )
        self.assertTrue(event.is_all_day)
        self.assertIsNone(event.start_time)
    
    def test_event_with_time(self):
        """Events can have specific start and end times."""
        event = LifeEvent.objects.create(
            user=self.user,
            title='Timed Event',
            start_date=date.today(),
            start_time=time(14, 30),
            end_time=time(15, 30)
        )
        self.assertEqual(event.start_time, time(14, 30))
        self.assertEqual(event.end_time, time(15, 30))


class RecipeModelTest(TestCase):
    """Tests for the Recipe model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_recipe(self):
        """Recipe can be created with required fields."""
        recipe = Recipe.objects.create(
            user=self.user,
            title='Chocolate Cake',
            ingredients='flour\nsugar\ncocoa',
            instructions='Mix and bake'
        )
        self.assertEqual(recipe.title, 'Chocolate Cake')
    
    def test_recipe_total_time(self):
        """total_time_minutes calculates correctly."""
        recipe = Recipe.objects.create(
            user=self.user,
            title='Quick Recipe',
            ingredients='stuff',
            instructions='do things',
            prep_time_minutes=10,
            cook_time_minutes=20
        )
        self.assertEqual(recipe.total_time_minutes, 30)
    
    def test_recipe_total_time_with_missing_values(self):
        """total_time_minutes handles missing values."""
        recipe = Recipe.objects.create(
            user=self.user,
            title='No Times',
            ingredients='stuff',
            instructions='do things'
        )
        self.assertIsNone(recipe.total_time_minutes)


class PetModelTest(TestCase):
    """Tests for the Pet model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_pet(self):
        """Pet can be created with required fields."""
        pet = Pet.objects.create(
            user=self.user,
            name='Max',
            species='dog'
        )
        self.assertEqual(pet.name, 'Max')
        self.assertTrue(pet.is_active)
    
    def test_pet_age_calculation(self):
        """Pet age is calculated from birth date."""
        # Use a date that's definitely 3 full years ago
        from dateutil.relativedelta import relativedelta
        three_years_ago = date.today() - relativedelta(years=3)
        
        pet = Pet.objects.create(
            user=self.user,
            name='Buddy',
            species='dog',
            birth_date=three_years_ago
        )
        self.assertEqual(pet.age, 3)
    
    def test_pet_age_none_without_birth_date(self):
        """Pet age is None when no birth date."""
        pet = Pet.objects.create(
            user=self.user,
            name='Unknown Age',
            species='cat'
        )
        self.assertIsNone(pet.age)