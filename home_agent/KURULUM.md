# Ev Relay — Şarkıları kendi internetinle çal

Bot **Render'da** kalır (Highrise bağlantısı, icecast, `/stream1` orada).
Sadece **şarkı isteklerinin sesi** evindeki cihazdan çekilir. Böylece
YouTube/SoundCloud'un veri merkezi IP engeline takılmaz.

```
Highrise  <->  Render botu  <--(MP3 byte'ları)--  ev cihazı  <--  SoundCloud/YouTube
                    |
                    +--> icecast --> https://highrise-ai-bot.onrender.com/stream1
```

Bağlantı **ev cihazından Render'a doğru** kurulur. Bu yüzden:

- port yönlendirme YOK
- domain / DuckDNS YOK
- Cloudflare Tunnel YOK
- statik IP / CGNAT sorunu YOK (mobil veri bile olur)
- sadece **internet + açık kalan bir cihaz** gerekir

Ev cihazı bağlıyken Render servisi de uyanık kalır (WebSocket trafiği
uykuya geçmesini engeller) — UptimeRobot'a ek gerek yok ama zararı da yok.

---

## Bilgisayar (Windows) ile kurulum — önerilen

### 1) Python kur
https://www.python.org/downloads/ → indir → kurarken **"Add python.exe to PATH"** işaretle.

Kontrol:
```bat
python --version
```

### 2) ffmpeg kur
```bat
winget install Gyan.FFmpeg
```
Kurulumdan sonra terminali kapat/aç, kontrol:
```bat
ffmpeg -version
```
Komut bulunamazsa ffmpeg'i indirip `C:\ffmpeg\bin` klasörüne çıkar ve
`baslat.bat` içindeki şu satırın başındaki `rem`i kaldır:
```bat
rem set "PATH=C:\ffmpeg\bin;%PATH%"
```

### 3) websockets paketi
```bat
pip install websockets
```

### 4) Relay dosyalarını indir
GitHub'dan `home_agent` klasörünü indir (repo: `facescore1-lgtm/highrise-ai-bot`,
branch: `render`). İçinde:
- `relay_agent.py`
- `baslat.bat`

İkisi aynı klasörde olsun.

### 5) Başlat
`baslat.bat` dosyasına çift tıkla. Şunu görürsen tamamdır:
```
[..] relay cihazi basliyor: ...
[..] Render'a baglandi
```

### 6) Kontrol
Tarayıcıda:
```
https://highrise-ai-bot.onrender.com/control/relay
```
Cevap `{"connected": true ...}` olmalı.

Sonra odada:
```
-p Semicenk - Pişman Değilim
```
Şarkı çalmaya başlar.

---

## Bilgisayarın uyumaması için

Windows'ta: **Ayarlar → Sistem → Güç → Ekran ve uyku**
- "Uykuya geçir": **Hiçbir zaman** (şarjdaysa / prize takılıyken)
- Ekran kapanabilir, sorun değil.

`baslat.bat` penceresini kapatmayın (küçültebilirsiniz). Bilgisayar yeniden
başlarsa `baslat.bat`ı tekrar çalıştırın. İsterseniz:
- `Win+R` → `shell:startup` → `baslat.bat`ın kısayolunu koyun (otomatik başlar).

---

## Telefon (Termux) ile kurulum

Telefon da olur ama ekran kapalıyken çalışması için ayar gerekir.

```bash
pkg update -y
pkg install -y python ffmpeg
pip install websockets
termux-wake-lock
python relay_agent.py --url wss://highrise-ai-bot.onrender.com/relay --token TOKEN
```

`TOKEN` değeri `baslat.bat` içindeki `RELAY_TOKEN` ile aynı.

Ek olarak:
- Termux için **pil optimizasyonu kapalı / kısıtlayıcı yok** olmalı.
- Xiaomi/Redmi/Poco: **Otomatik başlatma** açık.
- Wi-Fi'de kalmalı (sürekli upload var, mobil veri kotayı yer).
- Şarjda tutun.

İsterseniz tek satırlık başlatma scripti:
```bash
echo 'termux-wake-lock; python ~/relay_agent.py --url wss://highrise-ai-bot.onrender.com/relay --token TOKEN' > ~/relay.sh
chmod +x ~/relay.sh
```

---

## Nasıl çalışıyor?

1. Odada `-p ...` yazılır.
2. Render'daki bot SoundCloud'da arar, ses akışının URL'sini bulur.
3. URL'yi WebSocket ile ev cihazına yollar.
4. Ev cihazı ffmpeg ile sesi indirir, MP3'e çevirir, Render'a geri yollar.
5. Render bunu icecast'e basar → `/stream1`.

Ev cihazı bağlı değilse bot eski davranışa döner (Render üzerinden dener).

## Sık sorunlar

| Belirti | Çözüm |
|---|---|
| `/control/relay` → `connected: false` | `baslat.bat` açık mı? İnternet var mı? Pencereyi kapatmayın. |
| `ffmpeg bulunamadi` | ffmpeg PATH'te değil; 2. adımı uygulayın. |
| `token gecersiz` | `baslat.bat` içindeki `RELAY_TOKEN` Render'daki `RELAY_TOKEN` ile aynı olmalı. |
| Şarkı 20 sn sonra radyoya dönüyor | Ev cihazı ses gönderemedi; o cihazın internetini/ffmpeg'i kontrol edin. |
| Bilgisayar uyuyunca müzik duruyor | Güç ayarından uykuyu kapatın. |
