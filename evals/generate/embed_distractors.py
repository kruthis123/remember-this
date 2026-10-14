import asyncio
import json
from pathlib import Path

from remember_this.retrieval.embeddings import embed_text

SOURCE = Path("evals/data/generated/distractors.json")
DEST = Path("evals/data/generated/distractors_embedded.json")

BATCH_SIZE = 50


async def main() -> None:
    distractors = json.loads(SOURCE.read_text(encoding="utf-8"))
    texts = [d["text"] for d in distractors]

    embeddings: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        embeddings.extend(await embed_text(text_to_embed=batch))
        print(f"embedded {min(start + BATCH_SIZE, len(texts))}/{len(texts)}")

    for distractor, embedding in zip(distractors, embeddings):
        distractor["embedding"] = embedding

    DEST.write_text(json.dumps(distractors, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(distractors)} embedded distractors to {DEST}")


if __name__ == "__main__":
    asyncio.run(main())
