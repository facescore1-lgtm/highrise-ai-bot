import os
import json


def _norm(text):
    return "".join((text or "").lower().split())


def load_emotes():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emotes.json")
    emotes = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        for i, e in enumerate(raw, 1):
            emotes.append(
                {
                    "num": i,
                    "name": e["name"],
                    "id": e["code"],
                    "duration": e["duration"],
                }
            )
    except Exception:
        pass
    return emotes


EMOTES = load_emotes()

BY_NUMBER = {e["num"]: e for e in EMOTES}
BY_NAME = {_norm(e["name"]): e for e in EMOTES}
BY_ID = {e["id"].lower(): e for e in EMOTES}

# ayni animasyonu farkli id'lerle denemek icin
ALTS = {
    "sit-open": ["sit-open", "idle-sitfloor", "sit-idle-cute"],
    "emote-rainstruck-fail": ["emote-rainstruck-fail", "emote-rainstruck"],
    "emote-rainstruck-success": ["emote-rainstruck-success", "emote-rainstruck"],
    "idle_layingdown": ["idle_layingdown", "idle-laying-phone-talking", "idle-laying-phone-texting"],
    "idle_layingdown2": ["idle_layingdown2", "idle-laying-phone-texting"],
    "idle-floorsleeping2": ["idle-floorsleeping2", "idle-floorsleeping"],
    "idle-floorsleeping": ["idle-floorsleeping", "idle-floorsleeping2"],
    "emote-kissing": ["emote-kissing", "emote-kissing-bound"],
    "idle-dance-tiktok4": ["idle-dance-tiktok4", "dance-tiktok4"],
    "emote-offdutyangels-comehere": ["emote-offdutyangels-comehere", "emote-comehere"],
    "emote-offdutyangels-backoff": ["emote-offdutyangels-backoff", "emote-backoff"],
    "emote-bloomify-pose2": ["emote-bloomify-pose2"],
    "emote-bloomify-pose1": ["emote-bloomify-pose1"],
    "emote-bloomify-pose3": ["emote-bloomify-pose3"],
    "emote-pose-goth1": ["emote-pose-goth1"],
    "emote-pose-goth2": ["emote-pose-goth2"],
    "emote-pose-goth3": ["emote-pose-goth3"],
    "emote-pose-sit": ["emote-pose-sit"],
    "emote-pose-stand2": ["emote-pose-stand2"],
    "emote-sicklycute-sing-fast": ["emote-sicklycute-sing-fast", "emote-crowd"],
    "emote-sicklycute-sing-slow": ["emote-sicklycute-sing-slow", "emote-jammer"],
    "emote-littlemonsters-dance": ["emote-littlemonsters-dance", "dance-monster"],
    "emote-spiderman": ["emote-spiderman"],
    "emote-shy2": ["emote-shy2", "emote-shy"],
    "dance-running-man": ["dance-running-man", "dance-runningman"],
    "emote-idle-daydreaming": ["emote-idle-daydreaming", "emote-daydream"],
    "emote-threadexchange-floating": ["emote-threadexchange-floating", "emote-float2"],
    "emote-boxer": ["emote-boxer"],
    "emote-jewelrise-vibing": ["emote-jewelrise-vibing", "emote-vibing"],
    "emote-ragdoll": ["emote-ragdoll", "emote-yoink"],
    "emote-flirt": ["emote-flirt"],
    "emote-cartwheel": ["emote-cartwheel"],
    "dance-hiphop": ["dance-hiphop"],
    "fishing-pull-small": ["fishing-pull-small"],
    "hcc-jetpack": ["hcc-jetpack", "emote-jetpack"],
    "emote-armcannon": ["emote-armcannon"],
    "dance-mine": ["dance-mine"],
    "idle-phone-camera": ["idle-phone-camera", "idle-selfie"],
    "emote-alice-shrink": ["emote-alice-shrink"],
    "dance-tiktok3": ["dance-tiktok3"],
    "profile-breakscreen": ["profile-breakscreen"],
    "emote-electrified": ["emote-electrified"],
    "dance-twerk": ["dance-twerk"],
    "emote-surf": ["emote-surf"],
    "idle-space": ["idle-space", "dance-zerochill"],
    "sit-idle-cute": ["sit-idle-cute", "sit-open"],
    "dance-floss": ["dance-floss"],
    "emote-collab-celebrate-right": ["emote-collab-celebrate-right"],
    "dance-breakdance": ["dance-breakdance"],
    "emote-lust": ["emote-lust"],
    "dance-swagbounce": ["dance-swagbounce"],
    "dance-woah": ["dance-woah"],
    "emote-yogaSurprise": ["emote-yogaSurprise"],
    "emote-kawaiipose": ["emote-kawaiipose"],
    "sit-idle-laidBack": ["sit-idle-laidBack"],
    "sit-idle-phone-text": ["sit-idle-phone-text"],
    "dance-freshprince": ["dance-freshprince"],
    "emote-ghost-idle": ["emote-ghost-idle"],
    "emote-tune-accept": ["emote-tune-accept"],
    "idle-dance-tiktok6": ["idle-dance-tiktok6"],
    "idle-laying-phone-texting": ["idle-laying-phone-texting"],
    "emote-hopscotch": ["emote-hopscotch"],
    "idle-crouched": ["idle-crouched"],
    "dance-popularvibe": ["dance-popularvibe"],
    "emote-headball": ["emote-headball"],
    "dance-robotic": ["dance-robotic"],
    "emote-meditate-idle": ["emote-meditate-idle"],
    "emote-afk-idle": ["emote-afk-idle", "emote-afk"],
    "dance-tiktok5": ["dance-tiktok5"],
    "emote-inside-out": ["emote-inside-out", "dance-inside"],
    "emote-threadexchange-star": ["emote-threadexchange-star"],
    "emote-hyped": ["emote-hyped"],
    "emote-iceskating": ["emote-iceskating"],
    "emote-jetpack": ["emote-jetpack", "hcc-jetpack"],
    "emote-judochop": ["emote-judochop"],
    "emote-jumpb": ["emote-jumpb"],
    "emote-kicking": ["emote-kicking", "emote-kick"],
    "emote-kiss": ["emote-kiss", "emote-kissing"],
    "emote-laughing2": ["emote-laughing2", "emote-laugh"],
    "emote-laughing": ["emote-laughing"],
    "emote-levelup": ["emote-levelup"],
    "emote-looping": ["emote-looping", "emote-teleport"],
    "emote-maniac": ["emote-maniac"],
    "emote-model": ["emote-model"],
    "emote-monster_fail": ["emote-monster_fail"],
    "emote-gordonshuffle": ["emote-gordonshuffle"],
    "emote-nightfever": ["emote-nightfever"],
    "emote-ninjarun": ["emote-ninjarun"],
    "emote-panic": ["emote-panic"],
    "emote-peace": ["emote-peace"],
    "emote-peekaboo": ["emote-peekaboo"],
    "emote-pose1": ["emote-pose1"],
    "emote-pose10": ["emote-pose10"],
    "emote-pose3": ["emote-pose3"],
    "emote-pose5": ["emote-pose5"],
    "emote-pose6": ["emote-pose6"],
    "emote-pose7": ["emote-pose7"],
    "emote-pose8": ["emote-pose8"],
    "emote-proposing": ["emote-proposing"],
    "emote-punkguitar": ["emote-punkguitar"],
    "emote-puppet": ["emote-puppet"],
    "emote-rainbow": ["emote-rainbow"],
    "emote-robot": ["emote-robot"],
    "emote-rofl": ["emote-rofl"],
    "emote-roll": ["emote-roll"],
    "emote-ropepull": ["emote-ropepull"],
    "emote-superrun": ["emote-superrun"],
    "emote-sad": ["emote-sad"],
    "emote-shrink": ["emote-shrink"],
    "emote-shy": ["emote-shy", "emote-shy2"],
    "emote-slap": ["emote-slap"],
    "emote-kissing-bound": ["emote-kissing-bound", "emote-kissing"],
    "emote-snake": ["emote-snake"],
    "emote-snowangel": ["emote-snowangel"],
    "emote-snowball": ["emote-snowball"],
    "emote-splitsdrop": ["emote-splitsdrop"],
    "emote-suckthumb": ["emote-suckthumb"],
    "emote-celebrationstep": ["emote-celebrationstep"],
    "emote-sumo": ["emote-sumo"],
    "emote-superpose": ["emote-superpose"],
    "emote-superpunch": ["emote-superpunch"],
    "emote-swordfight": ["emote-swordfight"],
    "emote-tapdance": ["emote-tapdance"],
    "emote-telekinesis": ["emote-telekinesis"],
    "emote-teleporting": ["emote-teleporting"],
    "emote-theatrical": ["emote-theatrical"],
    "emote-think": ["emote-think"],
    "emote-timejump": ["emote-timejump"],
    "emote-tired": ["emote-tired"],
    "emote-wave": ["emote-wave"],
    "emote-wings": ["emote-wings"],
    "emote-zombierun": ["emote-zombierun"],
    "dance-aerobics": ["dance-aerobics"],
    "dance-anime": ["dance-anime"],
    "dance-blackpink": ["dance-blackpink"],
    "dance-creepypuppet": ["dance-creepypuppet"],
    "dance-duckwalk": ["dance-duckwalk"],
    "dance-employee": ["dance-employee"],
    "dance-handsup": ["dance-handsup"],
    "dance-icecream": ["dance-icecream"],
    "dance-jinglebell": ["dance-jinglebell"],
    "dance-kawai": ["dance-kawai"],
    "dance-macarena": ["dance-macarena"],
    "dance-metal": ["dance-metal"],
    "dance-orangejustice": ["dance-orangejustice"],
    "dance-pennywise": ["dance-pennywise"],
    "dance-pinguin": ["dance-pinguin"],
    "dance-russian": ["dance-russian"],
    "dance-sexy": ["dance-sexy"],
    "dance-shoppingcart": ["dance-shoppingcart"],
    "dance-singleladies": ["dance-singleladies"],
    "dance-smoothwalk": ["dance-smoothwalk"],
    "dance-tiktok10": ["dance-tiktok10"],
    "dance-tiktok2": ["dance-tiktok2"],
    "dance-tiktok8": ["dance-tiktok8"],
    "dance-tiktok9": ["dance-tiktok9"],
    "dance-touch": ["dance-touch"],
    "dance-voguehands": ["dance-voguehands"],
    "dance-weird": ["dance-weird"],
    "dance-wrong": ["dance-wrong"],
    "dance-zombie": ["dance-zombie"],
    "dance-hipshake": ["dance-hipshake"],
    "idle-loop-aerobics": ["idle-loop-aerobics"],
    "idle-angry": ["idle-angry"],
    "idle-loop-annoyed": ["idle-loop-annoyed"],
    "idle-loop-happy": ["idle-loop-happy"],
    "idle-dance-casual": ["idle-dance-casual"],
    "idle-dance-headbobbing": ["idle-dance-headbobbing"],
    "idle-enthusiastic": ["idle-enthusiastic"],
    "idle-fighter": ["idle-fighter"],
    "idle-floating": ["idle-floating"],
    "idle-guitar": ["idle-guitar"],
    "idle-hero": ["idle-hero"],
    "idle-nervous": ["idle-nervous"],
    "idle-lookup": ["idle-lookup"],
    "idle-posh": ["idle-posh"],
    "idle-sad": ["idle-sad"],
    "sit-relaxed": ["sit-relaxed"],
    "idle-loop-sad": ["idle-loop-sad"],
    "idle_singing": ["idle_singing"],
    "idle-loop-sitfloor": ["idle-loop-sitfloor"],
    "idle-sleep": ["idle-sleep"],
    "idle-loop-tapdance": ["idle-loop-tapdance"],
    "idle-dance-tiktok7": ["idle-dance-tiktok7"],
    "idle-loop-tired": ["idle-loop-tired"],
    "idle-toilet": ["idle-toilet"],
    "idle-uwu": ["idle-uwu"],
    "idle-wild": ["idle-wild"],
    "idle_zombie": ["idle_zombie"],
    "emoji-angry": ["emoji-angry"],
    "emoji-arrogance": ["emoji-arrogance"],
    "emoji-celebrate": ["emoji-celebrate"],
    "emoji-clapping": ["emoji-clapping"],
    "emoji-crying": ["emoji-crying"],
    "emoji-cursing": ["emoji-cursing"],
    "emoji-dizzy": ["emoji-dizzy"],
    "emoji-eyeroll": ["emoji-eyeroll"],
    "emoji-flex": ["emoji-flex"],
    "emoji-gagging": ["emoji-gagging"],
    "emoji-ghost": ["emoji-ghost"],
    "emoji-give-up": ["emoji-give-up"],
    "emoji-hadoken": ["emoji-hadoken"],
    "emoji-halo": ["emoji-halo"],
    "emoji-lying": ["emoji-lying"],
    "emoji-mind-blown": ["emoji-mind-blown"],
    "emoji-naughty": ["emoji-naughty"],
    "emoji-there": ["emoji-there"],
    "emoji-pray": ["emoji-pray"],
    "emoji-punch": ["emoji-punch"],
    "emoji-scared": ["emoji-scared"],
    "emoji-sick": ["emoji-sick"],
    "emoji-smirking": ["emoji-smirking"],
    "emoji-sneeze": ["emoji-sneeze"],
    "emoji-poop": ["emoji-poop"],
    "emoji-thumbsup": ["emoji-thumbsup"],
    "idle_tough": ["idle_tough"],
    "emote-receive-disappointed": ["emote-receive-disappointed"],
    "sit-idle-sleep": ["sit-idle-sleep"],
    "emote-coolguy": ["emote-coolguy"],
    "emote-apart": ["emote-apart"],
    "emote-astronaut": ["emote-astronaut"],
    "emote-sleigh": ["emote-sleigh"],
    "emote-attention": ["emote-attention"],
    "emote-baseball": ["emote-baseball"],
    "emote-headblowup": ["emote-headblowup"],
    "emote-boo": ["emote-boo"],
    "emote-bow": ["emote-bow"],
    "emote-bunnyhop": ["emote-bunnyhop"],
    "emote-charging": ["emote-charging"],
    "emote-cold": ["emote-cold"],
    "emote-confused": ["emote-confused"],
    "emote-creepycute": ["emote-creepycute"],
    "emote-curtsy": ["emote-curtsy"],
    "emote-cute": ["emote-cute"],
    "emote-cutey": ["emote-cutey"],
    "emote-dab": ["emote-dab"],
    "emote-death": ["emote-death"],
    "emote-death2": ["emote-death2"],
    "emote-deathdrop": ["emote-deathdrop"],
    "emote-disappear": ["emote-disappear"],
    "emote-disco": ["emote-disco"],
    "emote-pose9": ["emote-pose9"],
    "emote-elbowbump": ["emote-elbowbump"],
    "emote-embarrassed": ["emote-embarrassed"],
    "emote-energyball": ["emote-energyball"],
    "emote-exasperated": ["emote-exasperated"],
    "emote-exasperatedb": ["emote-exasperatedb"],
    "emote-fainting": ["emote-fainting"],
    "emote-fail2": ["emote-fail2"],
    "emote-fail1": ["emote-fail1"],
    "emote-fashionista": ["emote-fashionista"],
    "emote-float": ["emote-float"],
    "emote-frog": ["emote-frog"],
    "emote-frustrated": ["emote-frustrated"],
    "emote-gangnam": ["emote-gangnam"],
    "emote-gift": ["emote-gift"],
    "emote-gravity": ["emote-gravity"],
    "emote-greedy": ["emote-greedy"],
    "emote-secrethandshake": ["emote-secrethandshake"],
    "emote-handstand": ["emote-handstand"],
    "emote-happy": ["emote-happy"],
    "emote-harlemshake": ["emote-harlemshake"],
    "emote-hearteyes": ["emote-hearteyes"],
    "emote-heartfingers": ["emote-heartfingers"],
    "emote-heartshape": ["emote-heartshape"],
    "emote-hot": ["emote-hot"],
    "emote-hug": ["emote-hug"],
    "emote-hugyourself": ["emote-hugyourself"],
}


def find_emote(text):
    text = (text or "").strip()
    if not text or text.startswith("-"):
        return None
    if text.isdigit():
        return BY_NUMBER.get(int(text))
    key = _norm(text)
    emote = BY_NAME.get(key)
    if not emote:
        emote = BY_ID.get(key.lower())
    if emote is None:
        cands = [e for e in EMOTES if _norm(e["name"]).startswith(key)]
        if len(cands) == 1:
            emote = cands[0]
    if emote is None:
        return None
    alts = ALTS.get(emote["id"])
    if not alts:
        return emote
    entry = dict(emote)
    entry["alts"] = [emote["id"]] + [a for a in alts if a.lower() != emote["id"].lower()]
    return entry


def search_emotes(query):
    key = _norm(query)
    if not key:
        return []
    return [e for e in EMOTES if key in _norm(e["name"]) or key in e["id"].lower()]


def emote_count():
    return len(EMOTES)
