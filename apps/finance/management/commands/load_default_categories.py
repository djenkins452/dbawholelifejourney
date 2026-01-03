# ==============================================================================
# File: load_default_categories.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Loads default transaction categories for finance module
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# ==============================================================================

"""
Management command to load default transaction categories.

This command creates a set of default income and expense categories
that are commonly used for personal finance tracking. The categories
are created as system categories (is_system=True) and are shared
across all users.

Usage:
    python manage.py load_default_categories
"""

from django.core.management.base import BaseCommand
from apps.finance.models import TransactionCategory
from apps.users.models import User


class Command(BaseCommand):
    help = 'Load default transaction categories for all users'

    # Default income categories
    INCOME_CATEGORIES = [
        {'name': 'Salary', 'icon': '💼', 'color': '#10b981'},
        {'name': 'Freelance', 'icon': '💻', 'color': '#3b82f6'},
        {'name': 'Investments', 'icon': '📈', 'color': '#8b5cf6'},
        {'name': 'Gifts', 'icon': '🎁', 'color': '#ec4899'},
        {'name': 'Refunds', 'icon': '↩️', 'color': '#6366f1'},
        {'name': 'Other Income', 'icon': '💰', 'color': '#14b8a6'},
    ]

    # Default expense categories with subcategories
    EXPENSE_CATEGORIES = [
        {
            'name': 'Housing',
            'icon': '🏠',
            'color': '#ef4444',
            'children': [
                {'name': 'Rent/Mortgage', 'icon': '🏠'},
                {'name': 'Utilities', 'icon': '💡'},
                {'name': 'Insurance', 'icon': '📋'},
                {'name': 'Maintenance', 'icon': '🔧'},
            ]
        },
        {
            'name': 'Transportation',
            'icon': '🚗',
            'color': '#f97316',
            'children': [
                {'name': 'Gas', 'icon': '⛽'},
                {'name': 'Car Payment', 'icon': '🚗'},
                {'name': 'Car Insurance', 'icon': '📋'},
                {'name': 'Maintenance', 'icon': '🔧'},
                {'name': 'Public Transit', 'icon': '🚌'},
            ]
        },
        {
            'name': 'Food',
            'icon': '🍽️',
            'color': '#eab308',
            'children': [
                {'name': 'Groceries', 'icon': '🛒'},
                {'name': 'Restaurants', 'icon': '🍽️'},
                {'name': 'Coffee/Snacks', 'icon': '☕'},
            ]
        },
        {
            'name': 'Healthcare',
            'icon': '🏥',
            'color': '#22c55e',
            'children': [
                {'name': 'Doctor', 'icon': '👨‍⚕️'},
                {'name': 'Pharmacy', 'icon': '💊'},
                {'name': 'Insurance', 'icon': '📋'},
            ]
        },
        {
            'name': 'Personal',
            'icon': '👤',
            'color': '#3b82f6',
            'children': [
                {'name': 'Clothing', 'icon': '👕'},
                {'name': 'Personal Care', 'icon': '🧴'},
                {'name': 'Gym/Fitness', 'icon': '🏋️'},
            ]
        },
        {
            'name': 'Entertainment',
            'icon': '🎬',
            'color': '#8b5cf6',
            'children': [
                {'name': 'Streaming Services', 'icon': '📺'},
                {'name': 'Movies/Events', 'icon': '🎬'},
                {'name': 'Hobbies', 'icon': '🎨'},
                {'name': 'Subscriptions', 'icon': '📧'},
            ]
        },
        {
            'name': 'Education',
            'icon': '📚',
            'color': '#06b6d4',
            'children': [
                {'name': 'Courses', 'icon': '🎓'},
                {'name': 'Books', 'icon': '📚'},
                {'name': 'Supplies', 'icon': '✏️'},
            ]
        },
        {
            'name': 'Giving',
            'icon': '❤️',
            'color': '#ec4899',
            'children': [
                {'name': 'Tithe', 'icon': '⛪'},
                {'name': 'Charity', 'icon': '🤝'},
                {'name': 'Gifts', 'icon': '🎁'},
            ]
        },
        {
            'name': 'Debt Payments',
            'icon': '💳',
            'color': '#64748b',
            'children': [
                {'name': 'Credit Card', 'icon': '💳'},
                {'name': 'Student Loans', 'icon': '🎓'},
                {'name': 'Personal Loans', 'icon': '📝'},
            ]
        },
        {
            'name': 'Savings',
            'icon': '🐷',
            'color': '#10b981',
            'children': [
                {'name': 'Emergency Fund', 'icon': '🆘'},
                {'name': 'Retirement', 'icon': '👴'},
                {'name': 'Goals', 'icon': '🎯'},
            ]
        },
        {'name': 'Fees', 'icon': '📄', 'color': '#94a3b8'},
        {'name': 'Other Expenses', 'icon': '📦', 'color': '#6b7280'},
    ]

    def handle(self, *args, **options):
        users = User.objects.all()

        if not users.exists():
            self.stdout.write(self.style.WARNING('No users found. Categories will be created when users sign up.'))
            return

        for user in users:
            self.stdout.write(f'Loading categories for {user.email}...')
            self.load_categories_for_user(user)

        self.stdout.write(self.style.SUCCESS('Default categories loaded successfully!'))

    def load_categories_for_user(self, user):
        """Load default categories for a specific user."""
        created_count = 0

        # Create income categories
        for cat_data in self.INCOME_CATEGORIES:
            cat, created = TransactionCategory.objects.get_or_create(
                user=user,
                name=cat_data['name'],
                category_type='income',
                parent=None,
                defaults={
                    'icon': cat_data['icon'],
                    'color': cat_data['color'],
                    'is_system': True,
                }
            )
            if created:
                created_count += 1

        # Create expense categories (with potential children)
        for cat_data in self.EXPENSE_CATEGORIES:
            parent, created = TransactionCategory.objects.get_or_create(
                user=user,
                name=cat_data['name'],
                category_type='expense',
                parent=None,
                defaults={
                    'icon': cat_data['icon'],
                    'color': cat_data.get('color', '#6b7280'),
                    'is_system': True,
                }
            )
            if created:
                created_count += 1

            # Create child categories if any
            for child_data in cat_data.get('children', []):
                child, created = TransactionCategory.objects.get_or_create(
                    user=user,
                    name=child_data['name'],
                    category_type='expense',
                    parent=parent,
                    defaults={
                        'icon': child_data['icon'],
                        'color': parent.color,
                        'is_system': True,
                    }
                )
                if created:
                    created_count += 1

        self.stdout.write(f'  Created {created_count} new categories')
