
import os
import json
import urllib.request
import urllib.error
from pathlib import Path
from google import genai

# API keys from GitHub Secrets
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

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

# Documentary prompt
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


def generate_with_gemini():
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY missing")

    print("Trying Gemini AI...")

    client = genai.Client(api_key=GEMINI_API_KEY)

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt
    )

    if not response.text or not response.text.strip():
        raise ValueError("Gemini returned empty script")

    return response.text


def generate_with_openrouter():
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY missing")

    print("Gemini unavailable. Switching to OpenRouter FREE model...")

    url = "https://openrouter.ai/api/v1/chat/completions"

    payload = {
        "model": "openrouter/free",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 6000
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "X-Title": "The Money Ledger"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            result = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"OpenRouter API error {error.code}: {details}"
        )

    print("DEBUG: OpenRouter response:")
    print(json.dumps(result, indent=2)[:5000])

    choices = result.get("choices", [])

    if not choices:
        raise ValueError(f"OpenRouter returned no choices: {result}")

    if not choices:
        raise ValueError(f"OpenRouter returned no choices: {result}")

    content = choices[0].get("message", {}).get("content")

    if isinstance(content, list):
        content = "\n".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict)
        )

    if not content or not content.strip():
        raise ValueError("OpenRouter returned empty script")

    print("OpenRouter model used:", result.get("model", "Unknown"))

    return content


# Primary + automatic backup
print("Starting THE MONEY LEDGER script generation...")

try:
    script = generate_with_gemini()
    print("SUCCESS: Script generated using Gemini!")

except Exception as gemini_error:
    print("Gemini failed:", str(gemini_error))
    print("Activating backup provider...")

    try:
        script = generate_with_openrouter()
        print("SUCCESS: Script generated using OpenRouter!")

    except Exception as openrouter_error:
        raise RuntimeError(
            "Both AI providers failed.\n"
            f"Gemini: {gemini_error}\n"
            f"OpenRouter: {openrouter_error}"
        )

# Save output
output_file = Path("output/script.txt")
output_file.parent.mkdir(parents=True, exist_ok=True)

output_file.write_text(script, encoding="utf-8")

print("DOCUMENTARY SCRIPT READY!")
print("Output:", output_file)
