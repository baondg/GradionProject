#!/usr/bin/env python3
"""Manual test for RealGeminiClient via OpenRouter. Run from backend/:

    ../.venv/bin/python test_gemini_manual.py
"""

from pathlib import Path

from dotenv import load_dotenv

from app.gemini import RealGeminiClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main() -> None:
    client = RealGeminiClient.from_env()
    book_text = (
        "The Wind in the Willows - Chapter 1\n"
        "The Mole had been working very hard all the morning, spring-cleaning his little home.\n"
    )

    print("Sending book...")
    client.send_book(book_text)
    print("Book sent.")

    print("Generating style...")
    style = client.style()
    print(f"Style: {style}")

    print("Generating characters...")
    chars = client.characters()
    print(f"Characters: {chars}")

    print("Generating portraits...")
    portraits = client.portraits(chars)
    out = Path("test_output")
    (out / "portraits").mkdir(parents=True, exist_ok=True)
    for index, blob in enumerate(portraits):
        (out / "portraits" / f"{index}.png").write_bytes(blob)
        print(f"Saved portrait {index}")

    print("Generating chapters...")
    chapters = client.chapters()
    print(f"Chapters: {chapters}")

    print("Generating illustrations...")
    illustrations = client.illustrations(chapters, portraits)
    (out / "illustrations").mkdir(parents=True, exist_ok=True)
    for index, blob in enumerate(illustrations):
        (out / "illustrations" / f"{index}.png").write_bytes(blob)
        print(f"Saved illustration {index}")


if __name__ == "__main__":
    main()
