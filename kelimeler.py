# Turkce kelime listesi - Kategorilere gore (taze, daha zor)
# Her kategoriye ait sabit canli neon rengi (Highrise <#RRGGBB>).
KELIMELER = {
    "hayvanlar": [
        "yunus", "kaplumbağa", "timsah", "kertenkele", "baykuş", "vaşak",
        "karga", "saksağan", "tavus", "flamingo", "penguen", "pirana",
        "vatoz", "müren", "ahtapot", "alageyik", "ceylan", "kirpi",
        "gelincik", "sansar", "pars", "zürafa", "karakulak", "sincap",
        "yarasa", "kokarca", "kaplan", "yengeç", "midye", "ıstakoz",
        "salamander", "bukalemun", "jaguar", "panter", "kunduz",
    ],
    "yiyecekler": [
        "lahmacun", "mantar", "baklagil", "midye", "istiridye", "kerevit",
        "levrek", "çipura", "barbunya", "bakla", "soğan", "pazı",
        "hindiba", "kabak", "patlıcan", "bamya", "enginar", "karnabahar",
        "brokoli", "mercimek", "nohut", "pirinç", "bulgur", "tarhana",
        "mantı", "börek", "bazlama", "kumpir", "gözleme", "helva",
        "lokum", "kadayıf", "baklava", "peynir", "zeytin", "tahin",
    ],
    "sehirler": [
        "istanbul", "ankara", "izmir", "bursa", "antalya", "adana",
        "trabzon", "konya", "gaziantep", "mersin", "kayseri", "eskişehir",
        "samsun", "diyarbakır", "manisa", "malatya", "erzurum", "van",
        "hatay", "tekirdağ", "sakarya", "karabük", "rize", "artvin",
        "giresun", "sinop", "amasya", "tokat", "çankırı", "bartın",
        "bilecik", "bolu", "düzce", "yalova", "kütahya", "burdur",
    ],
    "meslekler": [
        "doktor", "mühendis", "öğretmen", "avukat", "hemşire", "pilot",
        "mimar", "eczacı", "gazeteci", "ressam", "aktör", "sporcu",
        "asker", "polis", "itfaiye", "berber", "kuaför", "gardiyan",
        "şoför", "garson", "kasap", "fırıncı", "terzi", "marangoz",
        "tesisatçı", "elektrikçi", "boyacı", "bahçıvan", "çiftçi",
        "balıkçı", "avcı", "saatçi", "kuyumcu", "nalbant", "demirci",
        "kalaycı", "semerci", "attar", "debbağ", "nakkaş",
    ],
    "ulkeler": [
        "türkiye", "almanya", "fransa", "ingiltere", "italya", "ispanya",
        "rusya", "kanada", "çin", "japonya", "hindistan", "avustralya",
        "mısır", "yunanistan", "portekiz", "hollanda", "belçika",
        "isviçre", "avusturya", "norveç", "isveç", "danimarka", "polonya",
        "macaristan", "romanya", "ukrayna", "kore", "brezilya", "arjantin",
        "meksika", "çekya", "slovakya", "slovenya", "hırvatistan",
        "sırbistan", "bulgaristan", "gürcistan", "ermenistan",
    ],
    "spor": [
        "futbol", "basketbol", "voleybol", "tenis", "yüzme", "koşu",
        "bisiklet", "golf", "boks", "güreş", "judo", "karate", "kızak",
        "kayak", "snowboard", "sörf", "dart", "satranç", "espor",
        "badminton", "squash", "ragbi", "beyzbol", "okçuluk", "atıcılık",
        "eskrim", "halter", "kürek", "yelkencilik", "kaykay", "paten",
        "cirit", "dalma", "sutopu", "jimnastik", "vücut",
    ],
    "teknoloji": [
        "bilgisayar", "telefon", "tablet", "laptop", "yazılım", "donanım",
        "internet", "wifi", "bluetooth", "robot", "sunucu", "veritabanı",
        "program", "uygulama", "oyun", "konsol", "ekran", "klavye",
        "fare", "hoparlör", "kulaklık", "kamera", "drone", "işlemci",
        "bellek", "sürücü", "modem", "antivirüs", "şifreleme", "protokol",
        "algoritma", "yapay", "zihinsel", "kripto", "blokzincir", "siber",
    ],
    "doga": [
        "güneş", "ay", "yıldız", "bulut", "yağmur", "kar", "rüzgar",
        "deniz", "göl", "nehir", "dağ", "orman", "çöl", "ada", "vadi",
        "mağara", "şelale", "volkan", "deprem", "sel", "toprak", "taş",
        "kaya", "kum", "buz", "duman", "ateş", "su", "sis", "çiğ",
        "tufan", "kasırga", "hortum", "karayel", "keşişleme", "poyraz",
        "lodos", "samyeli", "yıldız", "keyf",
    ],
    "sanat": [
        "resim", "heykel", "müzik", "dans", "tiyatro", "sinema", "opera",
        "bale", "seramik", "fresk", "mozaik", "minyatür", "ebru",
        "hat", "kaligrafi", "fotoğraf", "edebiyat", "şiir", "roman",
        "drama", "komedi", "dokuma", "cam", "porselen", "nakkaş",
        "ritim", "melodi", "armoni", "senfoni", "koro", "solo",
        "virtüöz", "heykeltıraş", "yontu", "perde", "sahne",
    ],
    "bilim": [
        "fizik", "kimya", "biyoloji", "matematik", "astronomi", "jeoloji",
        "botanik", "zooloji", "genetik", "nöroloji", "kardiyoloji",
        "dahiliye", "cerrahi", "mikroskop", "teleskop", "deney",
        "teori", "hipotez", "kanıt", "veri", "istatistik", "mitoz",
        "mayoz", "atom", "molekül", "nükleus", "proton", "nötron",
        "foton", "kuantum", "relativite", "evrim", "genom", "hücre",
    ],
}

CATEGORIES = list(KELIMELER.keys())

# Kategori -> sabit canli neon rengi (Highrise <#RRGGBB>)
CATEGORY_COLORS = {
    "hayvanlar": "<#00FF7F>",   # bahar yesili
    "yiyecekler": "<#FF8C00>",  # turuncu
    "sehirler": "<#00BFFF>",    # gok mavisi
    "meslekler": "<#FF00FF>",   # magenta
    "ulkeler": "<#FFFF00>",     # sari
    "spor": "<#00FF00>",        # yesil
    "teknoloji": "<#00FFFF>",   # camgobegi
    "doga": "<#32CD32>",        # lime
    "sanat": "<#FF4500>",       # alev kizili
    "bilim": "<#FF1493>",       # deep pink
}


def get_random_category():
    import random
    return random.choice(CATEGORIES)


def get_category_color(category=None):
    return CATEGORY_COLORS.get(category, "<#FFFFFF>")


def get_random_word(category=None):
    import random
    if category and category in KELIMELER and KELIMELER[category]:
        return random.choice(KELIMELER[category])
    pool = [w for ws in KELIMELER.values() for w in ws]
    return random.choice(pool) if pool else "kale"


# ---- Geriye donuk uyumluluk (room_bot bunlari kullanmiyor) ----
ORTA_KELIMELER = [
    "makasla", "üşengeç", "kızamık", "zamazingo", "karabasan", "sarsıntı",
]
ZOR_KELIMELER = [
    "müteahhit", "mübadele", "münferit", "istihbarat", "istimlak", "müphem",
]


def get_random_level():
    import random
    return random.choice(["kolay", "orta", "zor"])


def get_word_by_level(level="kolay"):
    import random
    if level == "orta":
        return random.choice(ORTA_KELIMELER)
    if level == "zor":
        return random.choice(ZOR_KELIMELER)
    pool = [w for ws in KELIMELER.values() for w in ws]
    return random.choice(pool) if pool else "kale"
