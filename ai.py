import requests

API_BASE = "https://generativelanguage.googleapis.com/v1beta"

SYSTEM = (
    "Sen {owner} adlı kişinin Highrise oyunundaki sohbet asistanısın. "
    "Sana özel mesajla (DM/whisper) soru soran kişilere cevap veriyorsun.\n"
    "Görevin: karşıdaki kişiye samimi, kısa ve doğal Türkçe cevaplar vermek.\n"
    "Kurallar:\n"
    "- Soru sorulduğunda net ve kısa cevap ver.\n"
    "- Sohbet havasındaysa muhabbeti sürdür, tek kelimelik cevap verme.\n"
    "- Yanlış bilgi uydurma; bilmiyorsan 'bunu tam bilmiyorum' de.\n"
    "- Kısa tut: genelde 1-3 cümle, bir Highrise mesajı gibi.\n"
    "- Emoji kullanma.\n"
    "- Biri bot olup olmadığını sorarsa dürüstçe 'evet, otomatik bir sohbet "
    "asistanıyım ama burada sana yardım etmek için konuşuyorum' diyebilirsin."
)


class GeminiAI:
    def __init__(self, api_key, model="gemini-3.5-flash"):
        self.api_key = api_key
        self.model = model
        self._fallback = "Kısa bir an yanıtlayamadım, bir daha yazarsan dönerim!"

    def respond(self, owner, sender, message, history):
        try:
            system = SYSTEM.replace("{owner}", owner)
            history_text = "\n".join(
                f"{'Sen' if role == 'owner' else 'Karşı taraf'}: {text}"
                for role, text in history[-10:]
            )
            prompt = (
                f"{system}\n\n"
                f"Sohbet geçmişi:\n{history_text or '(yeni sohbet)'}\n\n"
                f"Karşı taraf ({sender}) şunları yazdı: {message}\n"
                f"Cevap:"
            )
            url = f"{API_BASE}/models/{self.model}:generateContent"
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            r = requests.post(url, params={"key": self.api_key}, json=payload, timeout=60)
            if r.status_code != 200:
                print(f"[AI] HTTP {r.status_code}: {r.text[:200]}")
                return self._fallback
            data = r.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return text or self._fallback
        except Exception as e:
            print(f"[AI] Hata: {e}")
            return self._fallback
