# Highrise AI Bot

Gemini gibi cevap veren Highrise chatbotu.

## Kurulum

### 1. Bagimliliklari yukle
```bash
cd highrise-ai-bot
npm install
```

### 2. Config dosyasini duzenle
`config.js` dosyasinda su degerleri guncelle:

```javascript
token: 'HIGHRISE_BOT_TOKEN',        // Bot token
room: 'ROOM_ID',                    // Oda ID
geminiApiKey: 'GEMINI_API_KEY',     // Gemini API key
```

### 3. Gemini API Key al
1. https://aistudio.google.com/apikey adresine git
2. "Get API key" butonuna tikla
3. Yeni bir API key olustur
4. Kopyalayip config.js'e yapistir

### 4. Botu baslat
```bash
npm start
```

## Komutlar

| Komut | Aciklama |
|-------|----------|
| `soru yaz` | Dogrudan soru sor |
| `-ai <soru>` | AI'ya soru sor |
| `-temizle` | Sohbet gecmisini temizle |
| `-gecmis` | Sohbet gecmisini goster |
| `-bot` | Botu yanina cagir |
| `-help` | Komutlari goster |

## Ozellikler

- Her kullanici icin ayri sohbet gecmisi
- Turkce ve Ingilice cevaplar
- Kisa ve net cevaplar
- Otomatik soru anlama
- Sohbet gecmisi hafizasi

## Notlar

- Bot calisirken konsolda loglari gorursunuz
- AI quota asilirsa hata mesaji gosterir
- Bellek tasarrufu icin ayrilan kullanicilarin gecmisi temizlenir