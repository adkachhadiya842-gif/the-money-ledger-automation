
from pathlib import Path

topics_file = Path("content/topics.txt")
output_file = Path("output/script.txt")

topics = [
    line.strip()
    for line in topics_file.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

if not topics:
    raise ValueError("No topics found!")

topic = topics[0]

script = f"""
THE MONEY LEDGER
FINANCIAL DOCUMENTARY

TITLE: {topic}

OPENING:
Start with an interesting financial mystery.

BACKGROUND:
Explain the history of this topic.

HOW IT WORKS:
Explain the financial system in simple language.

HIDDEN SIDE:
Explain the risks and lesser-known facts.

CONCLUSION:
End with an interesting question.

IMPORTANT:
Verify facts before publishing.
"""

output_file.parent.mkdir(parents=True, exist_ok=True)
output_file.write_text(script.strip(), encoding="utf-8")

print("Documentary script draft created!")
