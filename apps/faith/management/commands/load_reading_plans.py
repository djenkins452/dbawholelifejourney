# ==============================================================================
# File: apps/faith/management/commands/load_reading_plans.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to load initial Bible reading plan templates
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================
"""
Load Initial Bible Reading Plans

This command loads a set of Bible reading plan templates for users to follow.
It is idempotent - safe to run multiple times without creating duplicates.

Usage:
    python manage.py load_reading_plans
"""

from django.core.management.base import BaseCommand

from apps.faith.models import ReadingPlanDay, ReadingPlanTemplate


class Command(BaseCommand):
    help = "Load initial Bible reading plan templates"

    def handle(self, *args, **options):
        self.stdout.write("Loading Bible reading plans...")

        plans_created = 0
        plans_existed = 0

        # Define the reading plans
        reading_plans = self.get_reading_plans()

        for plan_data in reading_plans:
            days_data = plan_data.pop("days")
            slug = plan_data["slug"]

            plan, created = ReadingPlanTemplate.objects.get_or_create(
                slug=slug,
                defaults=plan_data,
            )

            if created:
                plans_created += 1
                self.stdout.write(f"  Created: {plan.title}")

                # Create the days for this plan
                for day_data in days_data:
                    ReadingPlanDay.objects.create(plan=plan, **day_data)
            else:
                plans_existed += 1
                self.stdout.write(f"  Exists: {plan.title}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done! Created {plans_created} plans, {plans_existed} already existed."
            )
        )

    def get_reading_plans(self):
        """Return the list of reading plan templates to create."""
        return [
            # Plan 1: Forgiveness (7 days)
            {
                "title": "Finding Forgiveness",
                "slug": "finding-forgiveness",
                "description": (
                    "A 7-day journey through Scripture exploring God's forgiveness "
                    "and how we can extend forgiveness to others. Learn to release "
                    "bitterness and experience freedom through Christ."
                ),
                "category": "topical",
                "difficulty": "beginner",
                "duration_days": 7,
                "topics": ["forgiveness", "healing", "grace", "relationships"],
                "is_featured": True,
                "is_active": True,
                "days": [
                    {
                        "day_number": 1,
                        "title": "God's Forgiveness",
                        "scripture_references": ["Psalm 103:8-12", "1 John 1:9"],
                        "reflection_prompt": "How does knowing God completely forgives you change how you see yourself?",
                        "devotional_text": "God's forgiveness is complete and unconditional. He removes our sins as far as the east is from the west.",
                    },
                    {
                        "day_number": 2,
                        "title": "The Cost of Forgiveness",
                        "scripture_references": ["Isaiah 53:4-6", "1 Peter 2:24"],
                        "reflection_prompt": "Reflect on what Jesus endured to secure your forgiveness.",
                    },
                    {
                        "day_number": 3,
                        "title": "Forgiving Others",
                        "scripture_references": ["Matthew 18:21-35", "Colossians 3:13"],
                        "reflection_prompt": "Is there someone you need to forgive? What's holding you back?",
                    },
                    {
                        "day_number": 4,
                        "title": "Releasing Bitterness",
                        "scripture_references": ["Hebrews 12:14-15", "Ephesians 4:31-32"],
                        "reflection_prompt": "What bitterness might be taking root in your heart?",
                    },
                    {
                        "day_number": 5,
                        "title": "Forgiveness and Healing",
                        "scripture_references": ["Luke 6:27-36", "Romans 12:17-21"],
                        "reflection_prompt": "How can forgiving others bring healing to your own heart?",
                    },
                    {
                        "day_number": 6,
                        "title": "Seeking Forgiveness",
                        "scripture_references": ["Matthew 5:23-24", "James 5:16"],
                        "reflection_prompt": "Is there someone you need to ask for forgiveness?",
                    },
                    {
                        "day_number": 7,
                        "title": "Living Forgiven",
                        "scripture_references": ["Romans 8:1-2", "2 Corinthians 5:17"],
                        "reflection_prompt": "How will you live differently knowing you are completely forgiven?",
                    },
                ],
            },
            # Plan 2: Prayer (7 days)
            {
                "title": "Learning to Pray",
                "slug": "learning-to-pray",
                "description": (
                    "Discover the power and purpose of prayer through this 7-day "
                    "study. Learn from Jesus' example and develop a deeper "
                    "conversation with God."
                ),
                "category": "topical",
                "difficulty": "beginner",
                "duration_days": 7,
                "topics": ["prayer", "faith", "spiritual growth", "relationship with God"],
                "is_featured": True,
                "is_active": True,
                "days": [
                    {
                        "day_number": 1,
                        "title": "Why We Pray",
                        "scripture_references": ["Philippians 4:6-7", "1 Thessalonians 5:16-18"],
                        "reflection_prompt": "What role does prayer currently play in your daily life?",
                    },
                    {
                        "day_number": 2,
                        "title": "The Lord's Prayer",
                        "scripture_references": ["Matthew 6:5-15"],
                        "reflection_prompt": "What elements of the Lord's Prayer speak most to you?",
                    },
                    {
                        "day_number": 3,
                        "title": "Praying with Faith",
                        "scripture_references": ["Mark 11:22-24", "James 1:5-8"],
                        "reflection_prompt": "How can you pray with greater faith and expectation?",
                    },
                    {
                        "day_number": 4,
                        "title": "Praying in God's Will",
                        "scripture_references": ["1 John 5:14-15", "Romans 8:26-27"],
                        "reflection_prompt": "How do you discern God's will when you pray?",
                    },
                    {
                        "day_number": 5,
                        "title": "Persistent Prayer",
                        "scripture_references": ["Luke 18:1-8", "Luke 11:5-10"],
                        "reflection_prompt": "What prayers have you been tempted to give up on?",
                    },
                    {
                        "day_number": 6,
                        "title": "Praying for Others",
                        "scripture_references": ["Ephesians 6:18-20", "James 5:13-16"],
                        "reflection_prompt": "Who in your life needs your prayers right now?",
                    },
                    {
                        "day_number": 7,
                        "title": "Listening in Prayer",
                        "scripture_references": ["Psalm 46:10", "1 Kings 19:11-13"],
                        "reflection_prompt": "How can you create more space to listen to God?",
                    },
                ],
            },
            # Plan 3: Finding Peace in Stress (7 days)
            {
                "title": "Peace in Troubled Times",
                "slug": "peace-in-troubled-times",
                "description": (
                    "When life feels overwhelming, God offers peace that passes "
                    "understanding. This 7-day plan helps you find calm in the "
                    "midst of life's storms."
                ),
                "category": "topical",
                "difficulty": "beginner",
                "duration_days": 7,
                "topics": ["peace", "anxiety", "stress", "trust", "faith"],
                "is_featured": True,
                "is_active": True,
                "days": [
                    {
                        "day_number": 1,
                        "title": "The Source of Peace",
                        "scripture_references": ["John 14:27", "John 16:33"],
                        "reflection_prompt": "What situations are stealing your peace right now?",
                    },
                    {
                        "day_number": 2,
                        "title": "Trading Anxiety for Peace",
                        "scripture_references": ["Philippians 4:6-7", "1 Peter 5:6-7"],
                        "reflection_prompt": "What worries do you need to cast on the Lord?",
                    },
                    {
                        "day_number": 3,
                        "title": "Trusting God's Plan",
                        "scripture_references": ["Jeremiah 29:11", "Proverbs 3:5-6"],
                        "reflection_prompt": "In what areas of life do you struggle to trust God?",
                    },
                    {
                        "day_number": 4,
                        "title": "God is With You",
                        "scripture_references": ["Isaiah 41:10", "Psalm 23"],
                        "reflection_prompt": "How does knowing God is with you change your perspective?",
                    },
                    {
                        "day_number": 5,
                        "title": "Peace Through Focus",
                        "scripture_references": ["Isaiah 26:3", "Colossians 3:15"],
                        "reflection_prompt": "What helps you keep your mind focused on God?",
                    },
                    {
                        "day_number": 6,
                        "title": "Rest for the Weary",
                        "scripture_references": ["Matthew 11:28-30", "Psalm 62:1-2"],
                        "reflection_prompt": "Are you truly resting in God, or still carrying your burdens?",
                    },
                    {
                        "day_number": 7,
                        "title": "Peace as a Witness",
                        "scripture_references": ["Romans 12:18", "Galatians 5:22-23"],
                        "reflection_prompt": "How can your peace in difficult times point others to Christ?",
                    },
                ],
            },
            # Plan 4: Marriage (7 days)
            {
                "title": "Building a Godly Marriage",
                "slug": "building-godly-marriage",
                "description": (
                    "Strengthen your marriage through God's Word. This 7-day plan "
                    "explores biblical principles for love, communication, and "
                    "building a Christ-centered relationship."
                ),
                "category": "topical",
                "difficulty": "intermediate",
                "duration_days": 7,
                "topics": ["marriage", "love", "relationships", "family"],
                "is_featured": False,
                "is_active": True,
                "days": [
                    {
                        "day_number": 1,
                        "title": "God's Design for Marriage",
                        "scripture_references": ["Genesis 2:18-25", "Mark 10:6-9"],
                        "reflection_prompt": "How does understanding marriage as God's design shape your view of it?",
                    },
                    {
                        "day_number": 2,
                        "title": "Unconditional Love",
                        "scripture_references": ["1 Corinthians 13:4-8", "Ephesians 5:25-28"],
                        "reflection_prompt": "In what ways can you show unconditional love to your spouse?",
                    },
                    {
                        "day_number": 3,
                        "title": "Unity and Partnership",
                        "scripture_references": ["Ecclesiastes 4:9-12", "Amos 3:3"],
                        "reflection_prompt": "How can you and your spouse grow in unity?",
                    },
                    {
                        "day_number": 4,
                        "title": "Communication and Kindness",
                        "scripture_references": ["Proverbs 15:1", "Ephesians 4:29-32"],
                        "reflection_prompt": "How is the tone of communication in your marriage?",
                    },
                    {
                        "day_number": 5,
                        "title": "Serving One Another",
                        "scripture_references": ["Philippians 2:3-4", "Galatians 5:13"],
                        "reflection_prompt": "How can you serve your spouse better this week?",
                    },
                    {
                        "day_number": 6,
                        "title": "Forgiveness in Marriage",
                        "scripture_references": ["Colossians 3:12-14", "Matthew 18:21-22"],
                        "reflection_prompt": "Is there any unforgiveness you need to release in your marriage?",
                    },
                    {
                        "day_number": 7,
                        "title": "Praying Together",
                        "scripture_references": ["Matthew 18:19-20", "1 Peter 3:7"],
                        "reflection_prompt": "How can you make prayer a more central part of your marriage?",
                    },
                ],
            },
            # Plan 5: Gospel of John (21 days)
            {
                "title": "Journey Through John",
                "slug": "journey-through-john",
                "description": (
                    "Read through the Gospel of John in 21 days. Discover who Jesus "
                    "is through His words, miracles, and interactions with others."
                ),
                "category": "book",
                "difficulty": "beginner",
                "duration_days": 21,
                "topics": ["Jesus", "Gospel", "faith", "salvation"],
                "is_featured": False,
                "is_active": True,
                "days": [
                    {"day_number": 1, "title": "The Word Made Flesh", "scripture_references": ["John 1:1-18"]},
                    {"day_number": 2, "title": "The First Disciples", "scripture_references": ["John 1:19-51"]},
                    {"day_number": 3, "title": "Water into Wine", "scripture_references": ["John 2:1-25"]},
                    {"day_number": 4, "title": "You Must Be Born Again", "scripture_references": ["John 3:1-21"]},
                    {"day_number": 5, "title": "The Woman at the Well", "scripture_references": ["John 4:1-42"]},
                    {"day_number": 6, "title": "Healing and Authority", "scripture_references": ["John 5:1-47"]},
                    {"day_number": 7, "title": "Bread of Life", "scripture_references": ["John 6:1-40"]},
                    {"day_number": 8, "title": "Words of Eternal Life", "scripture_references": ["John 6:41-71"]},
                    {"day_number": 9, "title": "Living Water", "scripture_references": ["John 7:1-52"]},
                    {"day_number": 10, "title": "Light of the World", "scripture_references": ["John 8:1-30"]},
                    {"day_number": 11, "title": "The Truth Sets Free", "scripture_references": ["John 8:31-59"]},
                    {"day_number": 12, "title": "The Good Shepherd", "scripture_references": ["John 10:1-42"]},
                    {"day_number": 13, "title": "Lazarus Raised", "scripture_references": ["John 11:1-44"]},
                    {"day_number": 14, "title": "Triumphal Entry", "scripture_references": ["John 12:1-50"]},
                    {"day_number": 15, "title": "Washing Feet", "scripture_references": ["John 13:1-38"]},
                    {"day_number": 16, "title": "The Way, Truth, Life", "scripture_references": ["John 14:1-31"]},
                    {"day_number": 17, "title": "The True Vine", "scripture_references": ["John 15:1-27"]},
                    {"day_number": 18, "title": "The Helper Comes", "scripture_references": ["John 16:1-33"]},
                    {"day_number": 19, "title": "Jesus' Prayer", "scripture_references": ["John 17:1-26"]},
                    {"day_number": 20, "title": "The Cross", "scripture_references": ["John 18-19"]},
                    {"day_number": 21, "title": "He Is Risen", "scripture_references": ["John 20-21"]},
                ],
            },
            # Plan 6: Psalms of Comfort (5 days)
            {
                "title": "Psalms of Comfort",
                "slug": "psalms-of-comfort",
                "description": (
                    "Find comfort in God's Word through these beloved Psalms. "
                    "A 5-day journey through some of the most comforting passages "
                    "in Scripture."
                ),
                "category": "devotional",
                "difficulty": "beginner",
                "duration_days": 5,
                "topics": ["comfort", "peace", "hope", "trust"],
                "is_featured": False,
                "is_active": True,
                "days": [
                    {
                        "day_number": 1,
                        "title": "The Lord is My Shepherd",
                        "scripture_references": ["Psalm 23"],
                        "reflection_prompt": "Which verse in Psalm 23 brings you the most comfort today?",
                    },
                    {
                        "day_number": 2,
                        "title": "God is Our Refuge",
                        "scripture_references": ["Psalm 46"],
                        "reflection_prompt": "How have you experienced God as your refuge?",
                    },
                    {
                        "day_number": 3,
                        "title": "Thirsting for God",
                        "scripture_references": ["Psalm 42"],
                        "reflection_prompt": "How deep is your thirst for God's presence?",
                    },
                    {
                        "day_number": 4,
                        "title": "Praise in the Night",
                        "scripture_references": ["Psalm 63"],
                        "reflection_prompt": "Can you praise God even in difficult seasons?",
                    },
                    {
                        "day_number": 5,
                        "title": "Everlasting Love",
                        "scripture_references": ["Psalm 136"],
                        "reflection_prompt": "How have you seen God's steadfast love in your life?",
                    },
                ],
            },
        ]
