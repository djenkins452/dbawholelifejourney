# ==============================================================================
# File: apps/faith/management/commands/load_ruth_plan.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to create "Ruth & Naomi: Loyalty and Redemption" reading plan
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-20
# Last Updated: 2026-01-20
# ==============================================================================
"""
Management command to create the Ruth reading plan.

Creates a 4-day reading plan for the book of Ruth:
- Day 1: Ruth 1 - Tragedy and Loyalty
- Day 2: Ruth 2 - Gleaning and Grace
- Day 3: Ruth 3 - The Threshing Floor
- Day 4: Ruth 4 - Redemption and Legacy

Each day includes:
- Context summary (who, when, setting)
- Commentary at 3 difficulty levels (Beginner, Intermediate, Advanced)
- Reflection prompts

Biblical accuracy verified. Non-denominational, Bible-based content.
"""

from django.core.management.base import BaseCommand
from apps.faith.models import ReadingPlanTemplate, ReadingPlanDay


class Command(BaseCommand):
    help = "Load Ruth & Naomi: Loyalty and Redemption reading plan"

    def handle(self, *args, **options):
        self.stdout.write("Loading Ruth reading plan...")

        template = self._create_ruth_plan()
        self.stdout.write(f"  Created: {template.title} ({template.duration_days} days)")

        self.stdout.write(self.style.SUCCESS("Ruth reading plan loaded successfully!"))

    def _create_ruth_plan(self):
        """Create Ruth & Naomi: Loyalty and Redemption reading plan."""
        template, created = ReadingPlanTemplate.objects.get_or_create(
            slug="ruth-naomi-loyalty-redemption",
            defaults={
                "title": "Ruth & Naomi: Loyalty and Redemption",
                "description": "A 4-day journey through the book of Ruth, one of the most beautiful love stories in the Bible. Set during the dark period of the Judges, this short book shines as a beacon of faithfulness, kindness, and redemption. Through the loyal devotion of Ruth the Moabitess and the generous heart of Boaz, we see God's providence weaving together a story that leads directly to King David and ultimately to Jesus Christ.",
                "category": "book",
                "difficulty": "beginner",
                "duration_days": 4,
                "topics": ["ruth", "naomi", "boaz", "loyalty", "redemption", "kinsman-redeemer", "faithfulness", "providence"],
                "series": "People of the Bible",
                "series_order": 2,
                "allowed_emails": [],
                "is_active": True,
                "is_featured": True,
            }
        )

        if not created:
            # Plan exists, skip day creation
            return template

        # Ruth reading plan days
        days = [
            {
                "day_number": 1,
                "title": "Tragedy and Loyalty",
                "scripture_references": ["Ruth 1:1-22"],
                "context_summary": "The book of Ruth is set 'in the days when the judges ruled' (approximately 1100-1000 BC), a period characterized by spiritual and moral decline in Israel ('everyone did what was right in his own eyes,' Judges 21:25). A famine drives an Israelite family from Bethlehem to Moab—a nation with a troubled history with Israel. After tragedy strikes, we witness one of the most beautiful declarations of loyalty in all of Scripture.",
                "commentary_beginner": "A man named Elimelech took his wife Naomi and their two sons from Bethlehem to the foreign land of Moab because of a famine. While there, Elimelech died. The two sons married Moabite women—Orpah and Ruth—but after about ten years, both sons also died. Naomi was left with nothing: no husband, no sons, and no grandchildren. In that culture, a widow without sons was extremely vulnerable. When Naomi heard the famine had ended in Israel, she decided to return home. She urged her daughters-in-law to go back to their own families and find new husbands. Orpah tearfully agreed, but Ruth refused to leave. Her words are unforgettable: 'Where you go I will go, and where you stay I will stay. Your people will be my people and your God my God' (1:16). Ruth chose to leave everything familiar—her homeland, her family, her gods—to stay with her bitter, grieving mother-in-law. They arrived in Bethlehem at the beginning of barley harvest.",
                "commentary_intermediate": "The opening verse sets the book against the dark backdrop of the Judges period, creating contrast: amidst national unfaithfulness, personal faithfulness shines. Elimelech's name means 'My God is King,' yet he left the Promised Land (and God's provision) for pagan Moab. Moab had a troubled history with Israel—born from Lot's incestuous relationship with his daughter (Genesis 19:37), Moab had seduced Israel into idolatry (Numbers 25), and Moabites were excluded from the assembly 'to the tenth generation' (Deuteronomy 23:3). Yet from this unlikely background comes Ruth. Naomi's name means 'pleasant,' but she renames herself 'Mara' (bitter), saying the Almighty has dealt bitterly with her. Her theology is notable: despite her grief, she still acknowledges God's sovereignty. Ruth's declaration (1:16-17) uses covenantal language—she is essentially converting to Israel's faith. The phrase 'your God my God' is a profound confession. Her loyalty (Hebrew: chesed—covenant faithfulness, loving-kindness) becomes the book's central theme.",
                "commentary_advanced": "The book of Ruth functions as a literary gem within the canon, offering subtle critique of the Judges era while pointing forward to David's kingship. The Moab setting is theologically charged: the Moabites originated from Lot (Genesis 19:37), opposed Israel's wilderness journey (Numbers 22-25), and were excluded from the congregation (Deuteronomy 23:3-6). Yet Ruth's inclusion challenges ethnic exclusivism while maintaining covenantal theology—entry to Israel is through faith commitment, not merely birth. Naomi's speeches employ the divine name YHWH even in expressing complaint (1:13, 20-21), reflecting the tension between faith and suffering. Ruth's oath (1:16-17) employs the self-maledictory formula 'May the LORD deal with me, be it ever so severely' (1:17), indicating the seriousness of her commitment. The Hebrew word chesed (1:8) appears multiple times in Ruth, carrying rich connotations of covenant loyalty, steadfast love, and faithful kindness that exceeds obligation. The barley harvest timing (1:22) sets up the narrative for chapters 2-3, where harvest imagery carries theological weight. The Bethlehem setting ('house of bread') is ironic given the famine, and anticipates the greater Redeemer who would be born there.",
                "reflection_prompt": "Ruth left everything familiar to follow Naomi and Naomi's God. Her commitment wasn't based on what she would receive, but on love and loyalty. What does Ruth's example teach you about genuine commitment? Is there a relationship in your life that calls for this kind of sacrificial loyalty?",
            },
            {
                "day_number": 2,
                "title": "Gleaning and Grace",
                "scripture_references": ["Ruth 2:1-23"],
                "context_summary": "With no husband or sons to provide for them, Ruth and Naomi face an uncertain future. Israelite law made provision for the poor and foreigners through 'gleaning'—the practice of leaving the edges of fields and dropped grain for those in need (Leviticus 19:9-10, 23:22). Ruth takes initiative to provide for herself and Naomi, and 'happens' to end up in the field of a man who will change everything.",
                "commentary_beginner": "Ruth volunteered to go gather leftover grain in the fields—a humble but legal way for poor people to find food. She 'happened' to end up in a field belonging to Boaz, a wealthy relative of Naomi's deceased husband. Boaz noticed Ruth and asked about her. When he learned she was the Moabite woman who had shown such kindness to Naomi, he was deeply moved. He told Ruth to stay in his fields where she would be safe, drink from his workers' water, and eat with his harvesters. He instructed his workers to leave extra grain for her to find and never to bother her. When Ruth asked why he was being so kind to a foreigner, Boaz gave a beautiful answer: he had heard about everything Ruth had done for Naomi, and he prayed that the God of Israel, under whose wings Ruth had come for refuge, would richly reward her. Ruth returned home with an enormous amount of grain—about 30 pounds! Naomi was amazed and asked where she had worked. When she heard it was Boaz's field, she exclaimed, 'The LORD bless him! He is one of our kinsman-redeemers!' Hope was stirring.",
                "commentary_intermediate": "The chapter opens with a genealogical note: Boaz was 'a man of standing' (ish gibbor chayil) from Elimelech's clan. This information prepares readers for the kinsman-redeemer theme. Ruth's initiative ('Let me go to the fields') shows her character—she doesn't wait for help but acts within available means. The text says she 'happened' (miqreh) to find Boaz's field, but readers recognize divine providence arranging events. Boaz's name may mean 'in him is strength,' fitting his role as protector and provider. His treatment of Ruth exceeds legal requirement: he offers protection, provision, water, food, and commands his workers to intentionally leave extra grain. The 'wings' imagery (2:12) creates a beautiful verbal connection to Ruth's later request that Boaz spread his 'wing' (same Hebrew word: kanap) over her (3:9). Naomi's revelation about the 'kinsman-redeemer' (go'el) introduces the crucial legal concept: a close relative who could restore family property and perpetuate a deceased man's name. Ruth's gleaning yielded an ephah of barley (about 30 pounds)—extraordinarily generous.",
                "commentary_advanced": "The literary artistry of Ruth 2 reveals theological depth. The 'chance' (miqreh) meeting with Boaz employs literary irony—the reader perceives divine orchestration where characters see coincidence. Boaz is introduced as gibbor chayil ('mighty man of wealth/valor'), the same phrase later applied to Ruth (3:11, 'woman of noble character'), suggesting their suitability. Boaz's blessing (2:12) invokes the divine name and employs the metaphor of YHWH's protective 'wings' (kanap), alluding to Deuteronomy 32:11 where God protects Israel like an eagle. This imagery creates intentional foreshadowing for Ruth's threshing floor request. The gleaning laws (Leviticus 19:9-10, 23:22; Deuteronomy 24:19-22) explicitly mention 'the foreigner' (ger), which Ruth embodies. Boaz's treatment exceeds these requirements, demonstrating the chesed (loyal love) the book celebrates. The go'el (kinsman-redeemer) institution is rooted in Israelite family law (Leviticus 25:25-55) and becomes central to understanding Christ as our Redeemer. The ephah of barley (2:17) far exceeds normal gleaning; some calculate this as 10-15 times a typical day's gleaning, indicating Boaz's exceptional generosity. The chapter ends with Ruth 'staying close' to Boaz's workers through both harvests (barley and wheat, approximately seven weeks)—a narrative pause allowing relationship development.",
                "reflection_prompt": "Boaz went far beyond legal obligation in caring for Ruth. His generosity reflected God's generous character. In what ways has God shown you 'more than enough' grace? How might you extend that same kind of abundant kindness to someone in your life?",
            },
            {
                "day_number": 3,
                "title": "The Threshing Floor",
                "scripture_references": ["Ruth 3:1-18"],
                "context_summary": "After the harvest ends, Naomi devises a bold plan. What happens on the threshing floor at night seems strange to modern readers, but every action carries cultural significance. Ruth's approach to Boaz is not about romance alone—it's a request for legal protection and redemption according to Israelite custom. The scene is charged with tension: Will Boaz accept this vulnerable woman's proposal?",
                "commentary_beginner": "Naomi told Ruth it was time to find her a husband—'a home where you will be well provided for.' She had a plan involving Boaz. After he finished working at the threshing floor, eating and drinking, and lay down by the grain pile, Ruth was to uncover his feet and lie down. Ruth agreed to do everything Naomi said. That night, Ruth did exactly as instructed. When Boaz woke up startled in the middle of the night, he found a woman at his feet! 'Who are you?' he asked. Ruth answered, 'I am your servant Ruth. Spread the corner of your garment over me, since you are a kinsman-redeemer.' She was asking him to marry her and fulfill the family responsibility to carry on her dead husband's name. Boaz was deeply moved. He called her 'my daughter' and blessed her, saying this kindness was even greater than her earlier loyalty to Naomi—she chose him rather than running after younger men. He promised to do what she asked, noting that everyone knew she was 'a woman of noble character.' But there was a complication: another relative had first right to redeem. Boaz would settle things in the morning. Ruth stayed until early dawn, then left before anyone could see her. Boaz gave her six measures of barley so she wouldn't go home empty-handed.",
                "commentary_intermediate": "The threshing floor scene is often misunderstood. Ancient threshing floors were public places where grain was separated from chaff; workers sometimes slept there to protect the harvest. Naomi's instructions have legitimate purpose within cultural norms, though the nighttime approach adds tension. Ruth's request to 'spread your wing over me' uses the same Hebrew word (kanap) Boaz used when blessing Ruth (2:12), now applied to the marriage relationship—she asks him to be God's agent of protection. This is essentially a marriage proposal, framed within the kinsman-redeemer (go'el) tradition. The term 'noble character' (eshet chayil) applied to Ruth (3:11) is the same phrase used in Proverbs 31:10 for the 'wife of noble character'—high praise indeed. The closer redeemer introduces legal complication: proper procedure must be followed. Boaz's integrity is shown both in his self-control that night and his commitment to handle things properly. The six measures of barley are both practical provision and symbolic of abundance—Naomi interprets it as a sign that Boaz will not rest until the matter is settled. The Hebrew wordplay between 'empty' (reiqam, 3:17) and Naomi's earlier complaint of returning 'empty' (1:21) suggests restoration is coming.",
                "commentary_advanced": "The threshing floor narrative is constructed with remarkable literary care. The setting carries symbolic weight: threshing floors were liminal spaces associated with both harvest blessing and potential moral danger (cf. Hosea 9:1). Naomi's instructions employ seven imperatives (wash, anoint, dress, go down, wait, uncover, lie down), emphasizing Ruth's complete obedience. The uncovering of 'feet' (margelot) has been debated—some see it as euphemism, but the narrative context emphasizes propriety rather than impropriety; Boaz praises Ruth's virtue, which would be inconsistent with inappropriate behavior. Ruth's request invokes the go'el institution in marriage context. The 'wing/garment corner' (kanap) request explicitly connects to Boaz's earlier blessing (2:12): Ruth asks Boaz to enact what he prayed. The closer redeemer (3:12) creates legal-narrative tension requiring resolution. Boaz's reference to Ruth as 'eshet chayil' (3:11, 'woman of noble character/valor') matches his own introduction as 'ish gibbor chayil' (2:1), confirming their matching character. The six measures of barley are sometimes interpreted symbolically: six days of labor before Sabbath rest, or six letters in the Hebrew names to be born (Obed, Jesse, David), though such interpretations are speculative. The chapter demonstrates that chesed (covenant loyalty) operates within, not outside, proper social and legal structures.",
                "reflection_prompt": "Ruth took a risk by approaching Boaz, placing herself in a vulnerable position. Boaz responded with integrity, kindness, and action. How do trust and vulnerability play out in your relationships? When have you seen God honor a step of faith?",
            },
            {
                "day_number": 4,
                "title": "Redemption and Legacy",
                "scripture_references": ["Ruth 4:1-22"],
                "context_summary": "The final chapter moves to the city gate, where legal matters were settled in ancient Israel. The question of Ruth's redemption hangs in the balance. The unnamed closer relative must decide whether to fulfill his family duty. What happens next resolves not only Ruth and Naomi's story but establishes a lineage that will change the world.",
                "commentary_beginner": "Boaz went to the town gate and found the closer relative. He gathered ten elders as witnesses and presented the situation: Naomi was selling the family property, and the kinsman-redeemer had first right to buy it. The man agreed to redeem the land. But then Boaz added a crucial detail: with the land came responsibility to marry Ruth and raise up children to carry on the deceased husband's name. The man immediately backed out—'I cannot redeem it because I might endanger my own estate.' In those days, to confirm a transaction, one party removed his sandal and gave it to the other. The man gave his sandal to Boaz, and the elders witnessed that Boaz had acquired everything belonging to Elimelech and his sons, including Ruth as his wife. The people blessed Boaz with fertility like Rachel and Leah, and blessing like Perez (ancestor of the Bethlehem clan). Boaz married Ruth, and the LORD enabled her to conceive. She gave birth to a son! The women celebrated with Naomi: 'Praise be to the LORD, who this day has not left you without a kinsman-redeemer... He will renew your life and sustain you in your old age. For your daughter-in-law, who loves you and is better to you than seven sons, has given him birth.' Naomi took the child and cared for him. The women named him Obed, meaning 'servant.' And then comes the stunning conclusion: Obed became the father of Jesse, and Jesse the father of David—Israel's greatest king!",
                "commentary_intermediate": "The city gate was the place for legal transactions and dispute resolution. Ten elders provided official witness (this number later became the quorum for synagogue worship, the minyan). The closer relative is never named—he is simply 'So-and-so' (peloni almoni) in Hebrew, perhaps intentionally left anonymous because he failed to fulfill his duty. His willingness to buy property but unwillingness to marry Ruth reveals selfish calculation: children born to Ruth would inherit that property, diminishing his own family's holdings. The sandal ceremony (cf. Deuteronomy 25:9-10) publicly transferred redemption rights. The community's blessing invokes Rachel and Leah (matriarchs of the twelve tribes) and Tamar and Perez (ancestors of the Bethlehem clan through whom the line continued). The birth announcement emphasizes the LORD's agency—Ruth had been married for ten years without children (1:4); this child is God's gift. The women's praise to Naomi highlights Ruth's extraordinary worth: 'better than seven sons'—seven being the number of completeness. Obed ('servant') becomes the grandfather of David, placing this humble story in the direct lineage of Israel's monarchy and ultimately of Jesus Christ (Matthew 1:5).",
                "commentary_advanced": "The gate setting (sha'ar) represents judicial and civic authority; elders (zeqenim) served as witnesses and arbiters. The closer redeemer's anonymity (peloni almoni, a Hebrew equivalent to 'Mr. So-and-So') stands in pointed contrast to Boaz's named honor—the book preserves the legacy of those who act with chesed while letting self-interested parties fade from memory. His refusal exposes the limits of mere legal obligation without genuine love. The Levirate marriage custom (Deuteronomy 25:5-10) intersects with go'el redemption in complex ways; the text assumes readers understand these institutions. The women's blessing invokes Perez (4:12), born of Tamar and Judah (Genesis 38)—another story of unconventional means preserving the family line, with a foreign or marginalized woman as agent. The seven sons comparison (4:15) explicitly values Ruth above the ideal Israelite family. The genealogy (4:18-22) begins with Perez, connecting to the blessing, and concludes with David—the narrative purpose throughout. Matthew's genealogy (1:5) includes Ruth among only four women mentioned before Mary, highlighting God's inclusion of Gentiles in the messianic line. Theologically, Boaz as go'el prefigures Christ: the willing redeemer who pays the full price to bring His bride into His family. The book thus transforms from a pastoral idyll into salvation history, showing how God works through ordinary faithfulness to accomplish extraordinary redemption.",
                "reflection_prompt": "From tragedy to redemption, from foreign widow to ancestor of kings—Ruth's story shows God weaving together ordinary faithfulness into an extraordinary plan. How does knowing that God can use your everyday acts of loyalty and kindness encourage you? What 'small' obediences might be part of a larger story you can't yet see?",
            },
        ]

        for day_data in days:
            ReadingPlanDay.objects.get_or_create(
                plan=template,
                day_number=day_data["day_number"],
                defaults={
                    "title": day_data["title"],
                    "scripture_references": day_data["scripture_references"],
                    "context_summary": day_data["context_summary"],
                    "commentary_beginner": day_data["commentary_beginner"],
                    "commentary_intermediate": day_data["commentary_intermediate"],
                    "commentary_advanced": day_data["commentary_advanced"],
                    "reflection_prompt": day_data["reflection_prompt"],
                }
            )

        return template
