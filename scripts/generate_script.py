
import os
from pathlib import Path
from google import genai

# Read API key securely from GitHub Secrets
api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is missing in GitHub Secrets!")

# Read first topic
topics_file = Path("content/topics.txt")
topics = [
    line.strip()
    for line in topics_file.read_text(encoding="utf-8").splitlines()
    if line.strip()
]

if not topics:
    raise ValueError("No topics found in topics.txt!")

topic = topics[0]

# Connect to Gemini
client = genai.Client(api_key=api_key)

prompt = f"""
You are the lead documentary scriptwriter for THE MONEY LEDGER,
a premium American financial documentary YouTube channel.

Write an ORIGINAL, engaging English documentary script about:

{topic}

TARGET AUDIENCE:
American viewers aged 18-45.

STYLE:
- Premium Netflix-style financial documentary narration.
- Mysterious, cinematic and intellectually engaging.
- Clear American English.
- Strong opening hook in the first 20 seconds.
- Explain complex financial concepts simply.
- Use storytelling, examples and smooth transitions.
- No copied scripts or competitor content.

STRUCTURE:
1. Powerful opening hook.
2. Historical background.
3. How the financial system or business works.
4. Key companies, institutions and people involved.
5. Hidden risks and lesser-known facts.
6. Real-world examples.
7. Strong conclusion that makes viewers think.

LENGTH:
Aim for approximately 1,800 words.

FACTUAL RULES:
- Do not invent statistics, quotes, dates or events.
- Clearly flag claims that need fact-checking.
- Include a short list of suggested sources to verify.
- Separate established facts from opinions.

OUTPUT:
Give the title first, then the complete narration script.
Finish with a section called FACT-CHECK NOTES.
"""

print("Connecting to Gemini AI...")


response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents=prompt
)

script = response.text


if not script or not script.strip():
    raise ValueError("Gemini returned an empty script!")

output_file = Path("output/script.txt")
output_file.parent.mkdir(parents=True, exist_ok=True)
output_file.write_text(script, encoding="utf-8")

print("SUCCESS: AI documentary script generated!")
print("Output:", output_file)
