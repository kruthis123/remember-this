import asyncio
import json
import re
from pathlib import Path

from pydantic import BaseModel

from remember_this.llm.client import create_agent

DEST = Path("evals/data/generated/distractors.json")

NOTES_PER_TOPIC = 25
MIN_KEPT_PER_TOPIC = 15
MAX_ATTEMPTS_PER_TOPIC = 3
CONCURRENCY = 4

TOPICS = [
    "hobbies and weekend projects",
    "books, podcasts and shows",
    "cooking at home and recipes",
    "gardening and houseplants",
    "fitness routines and sports",
    "work tasks and colleagues",
    "school, courses and studying",
    "household chores and repairs",
    "shopping and purchases",
    "friends and social plans",
    "neighbourhood and local places",
    "music, concerts and instruments",
    "games and puzzles",
    "health habits and sleep",
    "volunteering and community events",
    "technology, gadgets and apps",
    "art, crafts and photography",
    "weather and seasonal activities",
    "bills, subscriptions and admin",
    "kids' activities and school events",
]

# Subjects the labelled eval cases ask about. A distractor mentioning any of these
# could accidentally answer a case question (or turn an abstention case into an
# answerable one), so they are both avoided in the prompt and filtered afterwards.
BLOCKED_TERMS = [
    "wifi", "password", "student id", "locker", "rent", "flight", "airline", "airport",
    "Rosetta", "mac and cheese", "apartment", "burrito", "Guzman", "exam", "Midas",
    "car", "dentist", "dental", "cleaning", "Priya", "Pranav", "Priyanka", "Olive Tree",
    "farmers market", "Hendricks", "peach", "peaches", "sourdough", "Q3", "Marcus",
    "Dana", "conference room", "offsite", "gym", "storage unit", "Siobhán", "manager",
    "bookshop", "bookstore", "Bookmarq", "rental", "Corolla", "plate", "passport",
    "Venmo", "plumber", "Dmitri", "sink", "leak", "pipe", "pipes", "lily", "lilies",
    "bouquet", "flowers", "mum", "mom", "mother", "Okafor", "vet", "Biscuit", "beagle",
    "dog", "pup", "puppy", "parked", "parking", "garage", "key", "keys", "locked out",
    "flowerpot", "Nando's", "Olive Garden", "Ippudo", "chicken", "KFC", "Popeyes",
    "Decathlon", "REI", "sporting goods", "running shoes", "Trader Joe's", "Best Buy",
    "Japan", "Japanese", "Kyoto", "Tokyo", "Osaka", "Lyon", "Melbourne", "cousin",
    "Qantas", "Jetstar", "Lufthansa", "Southwest", "Australia", "Australian", "in-laws",
    "Duolingo", "Strava", "Headspace", "owl", "Spanish", "cabin", "dermatologist",
    "skin", "eye doctor", "appointment", "pad thai", "Thai Orchid", "Bangkok Kitchen",
    "pad see ew", "hospital", "mall", "Maya", "Alvarez", "Alvarado", "Leo", "Albright",
    "piano", "savings", "checking account", "credit card", "bank account", "Dad",
    "father", "wallet", "watch", "Christmas", "frequent flyer", "blood type",
    "license plate", "hamster", "cat", "Luna", "Sorrel", "tasting menu", "Jess",
    "dim sum", "Golden Dragon", "Hilton", "hotel", "Parkers", "blender", "Target",
    "haircut", "hair cut", "Studio 9", "Monet", "museum", "exhibition", "Stripe",
    "job offer", "grandma", "grandmother", "birthday", "exhibit",
]

_blocked_pattern = re.compile(
    r"\b(" + "|".join(re.escape(term) for term in BLOCKED_TERMS) + r")\b",
    re.IGNORECASE,
)

# Notes that ask the bot to do something rather than state a fact. The generator
# produces these despite the prompt, and they would be routed as requests, not memories.
_instruction_pattern = re.compile(
    r"\b(remind me|please|don't let me forget|can you|could you|make sure)\b",
    re.IGNORECASE,
)

SYSTEM_PROMPT = f"""
You write short personal notes that a person might text to a memory-keeping chat bot so it can
remember things for them later.

Rules:
1. Every note is a statement of something the person wants remembered. Never write a question,
   and never address or instruct the bot.
2. Write in the first person, as a real person would type on their phone. Vary the style: some
   notes terse, some chatty, some lowercase with no punctuation, some with two related details.
3. Invent specific, concrete details (names of people and places, days, amounts, small
   opinions). Keep each note under 30 words.
4. Every note must be different from the others.
5. Never mention any of these subjects: {", ".join(BLOCKED_TERMS)}.
"""


class DistractorBatch(BaseModel):
    notes: list[str]


generator_agent = create_agent(
    model_key="generator_model",
    output_type=DistractorBatch,
    system_prompt=SYSTEM_PROMPT,
    # High temperature on purpose: filler only needs to be varied, not precise.
    temperature=0.9,
)


def keep(note: str) -> bool:
    text = note.strip()
    if not text or len(text) > 200:
        return False
    if "?" in text:
        return False
    if _instruction_pattern.search(text):
        return False
    return _blocked_pattern.search(text) is None


async def generate_topic(topic: str, semaphore: asyncio.Semaphore) -> list[dict]:
    kept: list[dict] = []
    async with semaphore:
        # Heavy filtering can leave a topic nearly empty, so keep asking until it
        # has enough notes or the attempts run out.
        for attempt in range(MAX_ATTEMPTS_PER_TOPIC):
            if len(kept) >= MIN_KEPT_PER_TOPIC:
                break
            try:
                result = await generator_agent.run(
                    f"Write {NOTES_PER_TOPIC} notes about: {topic}"
                )
            except Exception as error:
                print(f"  {topic}: attempt {attempt + 1} failed ({type(error).__name__})")
                continue
            kept.extend(
                {"topic": topic, "text": note.strip()}
                for note in result.output.notes
                if keep(note)
            )
    return kept


async def main() -> None:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    batches = await asyncio.gather(*(generate_topic(t, semaphore) for t in TOPICS))

    seen: set[str] = set()
    distractors = []
    for batch in batches:
        for item in batch:
            key = item["text"].lower()
            if key in seen:
                continue
            seen.add(key)
            distractors.append(item)

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps(distractors, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"requested: {len(TOPICS) * NOTES_PER_TOPIC}")
    print(f"kept after filtering and dedupe: {len(distractors)}")
    for topic, batch in zip(TOPICS, batches):
        print(f"  {len(batch):3d}  {topic}")


if __name__ == "__main__":
    asyncio.run(main())
