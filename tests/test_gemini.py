import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from openai import OpenAI

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

client = OpenAI(api_key=GEMINI_API_KEY, base_url=GEMINI_BASE_URL)

print(f"Probando Gemini ({GEMINI_MODEL})...\n")

response = client.chat.completions.create(
    model=GEMINI_MODEL,
    max_tokens=200,
    temperature=0.0,
    messages=[
        {
            "role": "system",
            "content": "You are a crypto trading analyst. Respond ONLY with valid JSON."
        },
        {
            "role": "user",
            "content": (
                "BTC is at $84,000. RSI=68, MACD bearish cross, volume -10%. "
                "Respond with: {\"vote\": \"BUY|SELL|HOLD\", \"confidence\": 0.0, \"reasoning\": \"brief\"}"
            )
        }
    ]
)

text = response.choices[0].message.content.strip()
print(f"Status:  OK")
print(f"Model:   {response.model}")
print(f"Tokens:  {response.usage.prompt_tokens} in / {response.usage.completion_tokens} out")
print(f"Respuesta: {text}")
