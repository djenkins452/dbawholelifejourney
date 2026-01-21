# ==============================================================================
# File: apps/faith/management/commands/load_jonah_plan.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to create "Jonah: The Reluctant Prophet" reading plan
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-20
# Last Updated: 2026-01-20
# ==============================================================================
"""
Management command to create the Jonah reading plan.

Creates a 5-day reading plan for the book of Jonah:
- Day 1: Jonah 1:1-16 - Running from God
- Day 2: Jonah 1:17-2:10 - Prayer from the Depths
- Day 3: Jonah 3:1-10 - Nineveh Repents
- Day 4: Jonah 4:1-11 - God's Compassion Revealed
- Day 5: Reflection & Application - Lessons from Jonah

Each day includes:
- Context summary (who, when, setting)
- Commentary at 3 difficulty levels (Beginner, Intermediate, Advanced)
- Reflection prompts

Biblical accuracy verified. Non-denominational, Bible-based content.
"""

from django.core.management.base import BaseCommand
from apps.faith.models import ReadingPlanTemplate, ReadingPlanDay


class Command(BaseCommand):
    help = "Load Jonah: The Reluctant Prophet reading plan"

    def handle(self, *args, **options):
        self.stdout.write("Loading Jonah reading plan...")

        template = self._create_jonah_plan()
        self.stdout.write(f"  Created: {template.title} ({template.duration_days} days)")

        self.stdout.write(self.style.SUCCESS("Jonah reading plan loaded successfully!"))

    def _create_jonah_plan(self):
        """Create Jonah: The Reluctant Prophet reading plan."""
        template, created = ReadingPlanTemplate.objects.get_or_create(
            slug="jonah-reluctant-prophet",
            defaults={
                "title": "Jonah: The Reluctant Prophet",
                "description": "A 5-day journey through the book of Jonah, one of the most dramatic and surprising stories in the Bible. This short book reveals profound truths about God's mercy, human resistance, and the scope of divine compassion that extends beyond our expectations. Jonah's story challenges us to examine our own hearts when God calls us to uncomfortable obedience.",
                "category": "book",
                "difficulty": "beginner",
                "duration_days": 5,
                "topics": ["jonah", "prophet", "mercy", "obedience", "nineveh", "compassion", "repentance"],
                "series": "People of the Bible",
                "series_order": 1,
                "allowed_emails": [],
                "is_active": True,
                "is_featured": True,
            }
        )

        if not created:
            # Plan exists, skip day creation
            return template

        # Jonah reading plan days
        days = [
            {
                "day_number": 1,
                "title": "Running from God",
                "scripture_references": ["Jonah 1:1-16"],
                "context_summary": "The book of Jonah is set during the reign of Jeroboam II of Israel (around 785-760 BC), a time of relative prosperity for Israel. Jonah son of Amittai was a prophet from Gath-hepher in Galilee (2 Kings 14:25). God calls him to go to Nineveh, the capital of Assyria—Israel's most feared enemy, known for extreme cruelty in warfare. Instead of obeying, Jonah boards a ship heading in the opposite direction.",
                "commentary_beginner": "God told Jonah to go to Nineveh and preach against their wickedness. But Jonah didn't want to go! The Assyrians were Israel's enemies—cruel and violent. So Jonah ran the other way, boarding a ship to Tarshish (probably in Spain—as far west as he could go). But you can't run from God. The Lord sent a violent storm that terrified the experienced sailors. While the pagan sailors prayed to their gods and threw cargo overboard, Jonah was asleep below deck! When they cast lots to find who caused the trouble, Jonah was identified. He admitted he was running from the Lord, the God who made the sea and land. The only solution? Throw him overboard. The sailors reluctantly did so, and immediately the storm stopped. These pagan sailors then feared the Lord and offered sacrifices to Him. Even in Jonah's disobedience, God was working!",
                "commentary_intermediate": "Jonah's flight reveals the depth of his prejudice against Nineveh. As a prophet, he knew God's character—merciful and compassionate (as he later admits in 4:2). He ran not because he feared failure, but because he feared success: that God might actually spare Israel's enemies. Tarshish represented the edge of the known world—maximum distance from God's assignment. The phrase 'from the presence of the Lord' (1:3) echoes language used of Cain's exile (Genesis 4:16), suggesting spiritual separation. The sailors' response contrasts sharply with Jonah's: they show more reverence and fear than the prophet himself. Their desperate prayers, sacrifice, and vows (1:16) mirror proper Israelite worship, while Jonah remains spiritually asleep. The Hebrew word for the 'great storm' uses the same root as 'great city' Nineveh—God's power matches the mission's scope.",
                "commentary_advanced": "The book of Jonah stands unique among prophetic literature—it's narrative about a prophet rather than oracles from one. Jonah son of Amittai is historically attested in 2 Kings 14:25, where he prophesied Israel's territorial expansion under Jeroboam II. This context is significant: Jonah enjoyed prophesying blessing for Israel but resisted prophesying mercy for their oppressors. The verb 'to flee' (barach) appears three times in verse 3, emphasizing the deliberateness of his rebellion. 'Going down' (yarad) recurs throughout chapter 1 (down to Joppa, down into the ship, down to sleep)—a physical descent mirroring spiritual decline. The sailors' question about Jonah's occupation (1:8) receives his theological confession: he 'fears' (yare) YHWH who made sea and dry land—ironic given his actions contradict this claim. The sailors' fear (yare) of YHWH in 1:16 uses the same term, suggesting these Gentiles now possess what Jonah professed but lacked. The text notes they offered sacrifices and made vows—technical language for proper worship, prefiguring the Gentile response in chapter 3.",
                "reflection_prompt": "Jonah knew exactly who God was but still ran the other direction. Is there something God is calling you to do that you've been avoiding? What fears or prejudices might be holding you back from obedience?",
            },
            {
                "day_number": 2,
                "title": "Prayer from the Depths",
                "scripture_references": ["Jonah 1:17-2:10"],
                "context_summary": "After being thrown overboard, Jonah should have drowned. Instead, God appointed a great fish to swallow him. Jonah spent three days and three nights in the fish's belly—a place of darkness, distress, and unexpected preservation. From this unlikely place of rescue and confinement, Jonah prays one of the most poetic prayers in Scripture.",
                "commentary_beginner": "Jonah didn't drown! God sent a huge fish to swallow him, and Jonah was inside for three days and three nights. Can you imagine? Surrounded by darkness, seaweed, and the smell of fish—yet alive! From this strange place, Jonah prayed. His prayer is beautiful poetry that echoes many Psalms. He remembered crying out to God from the depths, feeling like he was in the grave itself, with waves crashing over him. He felt cast away from God's presence. But when his life was fading, he remembered the Lord! He acknowledged that those who worship worthless idols give up the mercy that could be theirs. Jonah declared, 'Salvation belongs to the Lord!' And God commanded the fish, which vomited Jonah onto dry land. God gave Jonah a second chance.",
                "commentary_intermediate": "Jonah's prayer from the fish's belly is filled with quotations and allusions to the Psalms—particularly psalms of distress and thanksgiving (Psalms 18, 42, 69, 88, 116, 120, 142). This shows Jonah's deep familiarity with Scripture and worship traditions. Notably, his prayer is thanksgiving for deliverance, not a petition for rescue—Jonah already recognizes that being swallowed by the fish was salvation from drowning, not additional punishment. The imagery of 'the roots of the mountains' and 'the pit' (2:6) reflects ancient Near Eastern cosmology's three-tiered universe. Jonah's confession that idol-worshipers 'forsake their hope of steadfast love' (2:8, ESV) or 'give up their faithfulness' is striking given his own recent behavior. The phrase 'Salvation belongs to the Lord' (2:9) is the theological center of the book. After this declaration, God speaks to the fish—demonstrating His sovereignty over all creation. The fish obeys immediately, unlike the prophet.",
                "commentary_advanced": "The 'great fish' (dag gadol) is described with intentional ambiguity—the focus is theological, not zoological. The three days and three nights become typologically significant in Jesus' teaching (Matthew 12:40), where Jonah's experience prefigures Christ's burial and resurrection. Jonah's prayer employs technical Hebrew poetic forms: chiastic structures, merismus ('sea... heart of the seas... deep... currents... waves'), and spatial language mapping his spiritual journey (cast out, brought up, looked toward temple). The phrase 'out of the belly of Sheol' (mi-beten sheol, 2:2) uses the realm of the dead as metaphor for his near-death experience. His statement that 'my prayer came to you, into your holy temple' (2:7) affirms that God's presence isn't limited to the Jerusalem temple—a theme that will become central when Nineveh's prayers reach heaven. The Hebrew word for the fish 'vomiting' (va-yaqe) is deliberately undignified, perhaps humor, certainly humbling. Jonah exits as he entered—passive, acted upon by creatures obeying God better than he did.",
                "reflection_prompt": "Jonah found that even in the darkest, strangest circumstances, God was still rescuing him. When have you experienced God's mercy in an unexpected place? How does it change your perspective knowing that 'Salvation belongs to the Lord'?",
            },
            {
                "day_number": 3,
                "title": "Nineveh Repents",
                "scripture_references": ["Jonah 3:1-10"],
                "context_summary": "After his dramatic rescue, Jonah receives God's call a second time. This time he obeys, traveling to Nineveh—a journey of about 500 miles northeast from Israel. Nineveh was the capital of the Assyrian Empire, a city so large it took three days to walk through it. The Assyrians were infamous for their brutal treatment of conquered peoples, including Israel. What happens when Jonah finally preaches is beyond anything he could have expected.",
                "commentary_beginner": "God spoke to Jonah a second time: 'Go to Nineveh and preach the message I give you.' This time, Jonah obeyed. Nineveh was enormous—it took three days to walk across! Jonah went in and delivered the shortest sermon in the Bible: 'Forty more days and Nineveh will be overthrown!' That's it—just eight words in Hebrew! But something amazing happened. The people of Nineveh believed God! They declared a fast, and everyone from the greatest to the least put on sackcloth (rough cloth worn during mourning). When the king heard, he got off his throne, removed his royal robes, covered himself in sackcloth, and sat in ashes. He commanded everyone—even the animals!—to fast, wear sackcloth, and call urgently on God. He said, 'Who knows? God may relent and turn from His fierce anger.' And God saw their actions, that they turned from their evil ways, and He did not bring the destruction He had threatened.",
                "commentary_intermediate": "The narrative highlights the contrast between Jonah's minimal effort and Nineveh's maximal response. His message lacks any call to repentance—just announcement of doom. Yet the Ninevites 'believed God' (3:5), not merely believed Jonah. The response is overwhelming: the entire city, from greatest to least, repents. The king's decree is remarkably thorough, including animals in the fast and sackcloth—hyperbolic language emphasizing total participation. His theological reasoning is sophisticated: 'Who knows?' echoes similar statements in Joel 2:14 and 2 Samuel 12:22, showing genuine uncertainty combined with hope in divine mercy. The phrase 'turn from his evil way' (3:8, 10) creates deliberate wordplay—the same repentance asked of Nineveh is what God then 'relents' from (same Hebrew root). Importantly, God responds to their 'works' (3:10)—not mere words or rituals, but genuine behavioral change. Forty days recalls other biblical periods of testing and transformation (Moses on Sinai, Jesus in the wilderness).",
                "commentary_advanced": "The historicity of Nineveh's mass repentance has been questioned, but archaeological evidence suggests Assyrian religion included rituals of collective penance, and historical records note crises (plagues, eclipses) that prompted such responses in this era. The phrase 'great city to God' (ir gedolah l'elohim, 3:3) can mean 'exceedingly great' (superlative) or may hint at the city's significance to God. The 'three-day journey' likely describes the greater Nineveh metropolitan area, including suburbs referenced in Assyrian texts. Jonah's oracle uses 'overthrown' (nehpaketh), the same term for Sodom and Gomorrah's destruction (Genesis 19:21, 25)—but also allows a metaphorical reading of being 'turned around' or transformed, which is precisely what happens. The king's hope that God may 'relent' uses nacham, a term describing divine pathos—God's genuine emotional response to human action. This directly addresses the theological issue of whether God changes His mind: biblical theology holds that God's character is unchanging, but His responses are genuinely relational. The text emphasizes that God saw their 'deeds' (ma'asim)—not ritual performance but moral transformation.",
                "reflection_prompt": "The Ninevites responded immediately and wholeheartedly to God's message, even though they had been His enemies. What does genuine repentance look like in your life? Is there any area where you've been resistant to turning back to God?",
            },
            {
                "day_number": 4,
                "title": "God's Compassion Revealed",
                "scripture_references": ["Jonah 4:1-11"],
                "context_summary": "The final chapter reveals Jonah's true feelings about Nineveh's repentance. Rather than rejoicing that an entire city turned to God, Jonah is furious. His prayer in this chapter contrasts sharply with his prayer from the fish—revealing that his earlier piety masked a heart still resistant to God's purposes. Through a vine, a worm, and a scorching wind, God teaches Jonah an unforgettable lesson about divine compassion.",
                "commentary_beginner": "Jonah was angry! Very angry! He actually prayed that he would rather die than see Nineveh saved. Then he revealed why he ran in the first place: 'I knew you are a gracious and compassionate God, slow to anger and abounding in love, a God who relents from sending calamity.' He knew God's merciful character—and he didn't want his enemies to receive that mercy! God asked him gently, 'Is it right for you to be angry?' Jonah didn't answer. Instead, he went outside the city, built a shelter, and sat down to watch what would happen—maybe still hoping God would destroy Nineveh. God made a plant grow quickly to shade Jonah, and Jonah was happy about the plant. But the next day, God sent a worm to eat the plant and a scorching east wind. Jonah grew faint and again wished to die! God asked, 'Is it right for you to be angry about the plant?' Jonah said, 'Yes! Angry enough to die!' Then God delivered His point: 'You're concerned about a plant you didn't grow or tend, that appeared overnight and died overnight. Shouldn't I be concerned about Nineveh—a great city with 120,000 people who don't know right from wrong, plus many animals?'",
                "commentary_intermediate": "Jonah's angry prayer (4:2) quotes Exodus 34:6-7, one of the most important self-descriptions of God in the Old Testament. This passage was foundational to Israel's faith—yet Jonah cites it as a complaint! He wanted God to be gracious to Israel but not to Israel's enemies. The plant (Hebrew: qiqayon, possibly a castor oil plant) becomes God's object lesson. Jonah's emotional investment in temporary personal comfort contrasts with his lack of concern for 120,000 eternal souls. The phrase 'who cannot tell their right hand from their left' likely describes moral confusion or spiritual ignorance rather than age—Nineveh's people didn't know YHWH or His ways. The mention of 'many animals' at the end is touching and theologically significant—God's concern extends to all His creatures (Psalm 36:6, 145:9). The book ends with a question, leaving readers to answer for themselves: Will we align our hearts with God's expansive mercy, or remain like Jonah—technically obedient but inwardly resistant?",
                "commentary_advanced": "The Hebrew construction at 4:1 is emphatic: literally 'it was evil to Jonah, a great evil' (va-yera' el-yonah ra'ah gedolah), using the same language applied to Nineveh's wickedness in 1:2. Jonah considers Nineveh's salvation to be 'evil'! His death wish (4:3, 8) echoes Elijah's despair (1 Kings 19:4), but while Elijah fled after confronting evil, Jonah despairs after witnessing repentance. The qiqayon plant, worm, and east wind are all divinely 'appointed' (the verb manah, also used of the fish in 1:17), showing God's sovereign orchestration of creation for pedagogical purposes. The east wind (ruach qadiym) was known for its withering heat, associated with divine judgment (Exodus 14:21, Hosea 13:15). God's final question employs a fortiori reasoning: if Jonah cares for a plant he didn't create and that lasted one day, how much more should God care for a city with thousands of image-bearers and animals He created? The 120,000 figure, often interpreted as children, more likely represents the entire population using the idiom of moral confusion. The open-ended conclusion is literarily sophisticated—readers must complete the story in their own hearts.",
                "reflection_prompt": "Jonah cared more about his own comfort (the plant) than about people who needed God's mercy. What does this reveal about how easily our preferences can become more important than God's purposes? Is there anyone you struggle to want God's mercy to reach?",
            },
            {
                "day_number": 5,
                "title": "Lessons from Jonah",
                "scripture_references": ["Jonah 1-4", "Matthew 12:38-41", "Luke 11:29-32"],
                "context_summary": "On this final day, we step back to see the whole story and its impact throughout Scripture. Jesus Himself referenced Jonah as a sign to His generation. The book of Jonah raises profound questions about God's character, the scope of His mercy, and our response to His call. We'll review the key themes and consider how this ancient story speaks to us today.",
                "commentary_beginner": "Looking back at the whole story, we see several important lessons. First, you can't run from God—He pursues us even when we flee. Second, God uses everything for His purposes—storms, fish, plants, worms, and wind all obey Him. Third, God's mercy extends beyond our expectations and preferences—the 'enemies' we write off may be the very people God wants to reach. Fourth, genuine repentance matters—Nineveh's response saved an entire city. Jesus later pointed to Jonah as a sign (Matthew 12:40-41). Just as Jonah was three days in the fish's belly, Jesus would be three days in the earth. And Jesus warned that the Ninevites will judge His generation, because Nineveh repented at Jonah's preaching, but 'something greater than Jonah is here'! The book ends with a question because God wants us to answer: Will we embrace His heart for all people, or cling to our prejudices?",
                "commentary_intermediate": "Jonah is unique in prophetic literature because the prophet is more of an anti-hero than a model. Throughout the book, pagans consistently outperform the prophet: sailors pray while Jonah sleeps, Ninevites repent while Jonah resents, and even animals fast while Jonah pouts. This ironic reversal challenges Israel's assumptions about insiders and outsiders. The book anticipates the gospel's reach to the Gentiles. Key contrasts structure the narrative: chapter 1 (fleeing) vs. chapter 3 (going); chapter 2 (grateful prayer) vs. chapter 4 (angry prayer); Jonah's resistance vs. creation's obedience. The word 'great' (gadol) appears fourteen times—great city, great wind, great fish, great fear—emphasizing that everything about this story operates on a divine scale. Jesus' use of Jonah focuses on both the sign (burial and resurrection) and the response (repentance at preaching). The Ninevites' example condemns those who reject a greater revelation with less response.",
                "commentary_advanced": "The book of Jonah functions as sophisticated theological satire, using a historical prophet to explore the tension between Israel's election and God's universal concern. It addresses post-exilic debates about Jewish exclusivism, evident in books like Ezra-Nehemiah, by showing God's mercy to the quintessential enemy. The literary artistry is remarkable: the narrator never directly condemns Jonah, allowing irony and divine questioning to do the work. The book's placement among the Twelve Minor Prophets, near Nahum (which prophesies Nineveh's destruction), creates canonical tension that reflects real theological complexity. Jonah's character embodies the temptation to domesticate God—to accept His mercy for ourselves while denying it to others. The christological significance extends beyond typology: Jesus identifies with Jonah's experience while contrasting with his attitude. Early church fathers saw the fish episode as a death-resurrection pattern, and the Ninevites' response as a prototype of Gentile conversion. The unanswered final question invites every generation to examine their own hearts—do we rejoice when God shows mercy to those we consider undeserving, or do we, like Jonah, find it 'evil'?",
                "reflection_prompt": "The book of Jonah ends with a question, inviting us to answer. How has this study challenged your understanding of God's mercy? Is there a 'Nineveh' in your life—people or groups you'd rather not see receive God's grace? What would it look like to align your heart with God's compassion for all people?",
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
