"""Franco-Arabic (Arabizi) and English support for the complaint classifier.

The kit's training texts are almost all Arabic script. A citizen who writes
"el zebala mtkawema" or "the sewage is overflowing" shares almost no words with
them, and Franco spellings vary a lot ("zbala", "zebala", "zibala").

Two steps close that gap, both rule-based and explainable:

1. `skeleton(word)`: a spelling-insensitive key for a Latin word. Digits become
   their usual letters, vowels are dropped and repeats collapse, so "zebala",
   "zbala" and "zibalaa" all become "zbl".
2. `gloss(text)`: every Latin word whose skeleton is in the lexicon below adds
   the matching Arabic word. The Arabic word is what the kit uses, so a Franco
   complaint reaches the same word and character features as an Arabic one.

The lexicon is hand-written domain vocabulary (one Arabic word per concept, many
Franco/English spellings). It was not mined from any test or probe set.
"""

import re

# Arabic word -> Franco / English spellings. Keep the Arabic side in the kit's own
# wording (see the most frequent words per category in the training data).
LEXICON = {
    # water
    "ميه": ["maya", "mayya", "mayy", "mya", "maia", "mayah", "maaya", "water", "mayet"],
    "مياه": ["meyah", "miyah", "meyyah", "mayah"],
    "ماسوره": ["masoura", "masora", "masoora", "masura", "mwasir", "mawaseer", "mwaser", "pipe", "pipes"],
    "تسريب": ["tasreeb", "tasrib", "tasreb", "leak", "leaking", "leaks", "leakage", "bt5or", "bete5or", "5ar"],
    "مغرقه": ["mghr2a", "mghar2a", "mgharaqa", "ghar2a", "ghar2an", "gharqa", "flooded", "flooding", "flood"],
    "مكسوره": ["maksoura", "maksora", "mkasara", "mkasar", "maksoor", "maksour", "broken", "burst"],
    "مقطوعه": ["ma2to3a", "maqtoo3a", "ma2too3a", "2ate3", "2at3a", "ati3a", "2at3", "et2at3et", "it2ata3it", "cut", "cutoff"],
    "مفيش": ["mafihash", "mafihoosh", "mafeesh", "mafeesh", "mafish", "mfeesh", "mafesh", "mafeech", "no"],
    "ضغط": ["daght", "dag5t", "da8t", "da3t", "pressure"],
    "ضعيف": ["da3eef", "da3if", "da3ef", "da3eefa", "da3ifa", "weak", "low"],
    "الحنفيه": ["7anafeya", "hanafeya", "7anafiya", "7anafya", "tap", "faucet"],
    "بتنزل": ["nazla", "naazla", "btenzel", "bitinzil", "t2ta2", "nu2ta"],
    "واطي": ["wate", "waty", "waye2", "wa6y"],
    # sewer
    "بلاعه": ["bala3a", "balla3a", "bala3", "manhole", "drain"],
    "طافحه": ["taf7a", "tf7et", "tef7et", "tafha", "tafa7et", "overflowing", "overflow"],
    "المجاري": ["magary", "magari", "majari", "sewage", "sewer"],
    "صرف": ["sarf", "sar5", "saarf"],
    "ريحه": ["ri7a", "re7a", "ri7et", "re7et", "smell", "stink", "smells"],
    # power
    "الكهربا": ["kahraba", "kahrba", "ka7raba", "kahrabaa", "electricity", "power"],
    "النور": ["nour", "nur", "noor"],
    "انقطاع": ["en2eta3", "in2ita3", "outage", "blackout"],
    # hvac
    "التكييف": ["tabreed", "tabrid", "cooling", "takyeef", "takeef", "takyif", "takief", "ac", "conditioner", "conditioning", "hvac"],
    "سخن": ["so5n", "su5n", "sokhn", "sukhn", "hot"],
    "الحر": ["7ar", "har", "heat"],
    # waste
    "الزباله": ["zebala", "zbala", "zibala", "zebbala", "zbalah", "garbage", "trash", "rubbish", "waste"],
    "الصندوق": ["sandoo2", "sondoo2", "sanadee2", "sanade2", "sandou2", "bin", "bins", "container"],
    "مليان": ["malyan", "malyana", "malian", "full"],
    # cleanliness
    "كنس": ["kans", "kanas", "kannas", "sweep", "sweeping", "sweeps"],
    "تراب": ["trab", "tarab", "torab", "dust", "dusty"],
    "مخلفات": ["mo5alafat", "m5lfat", "debris", "rubble"],
    "وسخ": ["wesi5", "wesekh", "wese5", "wasa5", "wsa5a", "wasa5a", "dirty", "filthy"],
    # roads
    "حفره": ["7ofar", "hofar", "7ofra", "hofra", "7ofa", "pothole", "potholes", "hole"],
    "مطب": ["matab", "mataab", "matabb", "bump", "speedbump"],
    "الرصيف": ["rasif", "raseef", "rasef", "sidewalk", "pavement"],
    "الاسفلت": ["asfalt", "asphalt"],
    "الطريق": ["tari2", "tari2", "taree2", "tare2", "road"],
    # parking
    "راكنه": ["rakna", "raknin", "rakneen", "raken", "parked", "parking"],
    "الركن": ["arkan", "rakn", "arken"],
    "الجراج": ["garage", "garag", "jaraj"],
    # traffic signals
    "الاشاره": ["ishara", "esharet", "esh3ara", "eshara", "ishaara", "esharat", "light", "signal", "signals"],
    "حمرا": ["7amra", "hamra", "red"],
    "الزحمه": ["zahma", "za7ma", "za7meh", "traffic", "congestion"],
    "التقاطع": ["ta2ato3", "taqato3", "junction", "intersection", "roundabout", "dawaran", "dawwaran"],
    # streetlights
    "عمود": ["3amood", "3amoud", "3amod", "3awamid", "pole", "lamppost"],
    "لمبه": ["lamba", "lamda", "lambet", "lamdat", "lamp", "bulb"],
    "مطفي": ["matfy", "mtafy", "tafy", "mtafya", "tafya", "off"],
    "ضلمه": ["dalma", "dlma", "dalmah", "dark", "darkness"],
    "الاناره": ["enara", "inara", "lighting", "streetlight", "streetlights"],
    # safety
    "غاز": ["gaz", "ghaz", "gas"],
    "دخان": ["do5an", "dokhan", "smoke"],
    "حريق": ["7aree2a", "7ari2a", "7aree2", "7ari2", "fire", "burning"],
    "حرامي": ["7aramy", "7arami", "haramy", "thief", "thieves"],
    "سرق": ["yesra2", "bysra2", "sor2o", "bysor2o", "break", "sara2", "sere2", "sara2o", "itsara2", "stole", "stolen", "theft", "robbed"],
    "مريب": ["mashbooh", "mashbooha", "mashboha", "mureeb", "mreeb", "ghareeb", "ghareeba", "ghorab", "suspicious", "stranger", "strangers"],
    "سكينه": ["sekeena", "sekina", "sakeena", "knife"],
    "بيهدد": ["byhadded", "bihaded", "beyhadded", "threat", "threatening", "threatens"],
    "ضاله": ["dalla", "dala", "kelab", "klab", "stray", "dogs"],
    "سلك": ["selk", "silk", "wire", "wires", "cable", "makshoof", "exposed"],
    "خطر": ["5atar", "khatar", "5atr", "danger", "dangerous"],
    # noise
    "دوشه": ["fara7", "far7", "dj", "dawsha", "dosha", "dawshah", "noise", "noisy", "loud"],
    "صوت": ["kalaksat", "klaks", "horns", "sot", "sout", "sawt", "sound"],
    "ورشه": ["warsha", "wars", "wersha", "workshop"],
    "مكبرات": ["sammaat", "sama3at", "samaat", "speakers", "music"],
    "عالي": ["3aly", "3ali", "3alya", "3alia"],
    "الكافيه": ["ka7ok", "kahwa", "2ahwa", "cafe", "coffee"],
    # parks
    "الرشاشات": ["rashashat", "sprinkler", "sprinklers", "rai", "ray", "by2assi", "watering", "waters"],
    "الحديقه": ["7adi2a", "hadi2a", "7adee2a", "park", "garden"],
    "الجنينه": ["geneena", "gnena", "gneina", "genena", "gene3na"],
    "الزرع": ["zar3", "zr3", "plants", "grass"],
    "ناشف": ["nashef", "nashf", "dry", "dried"],
    "العاب": ["al3ab", "ar2al", "playground", "swings", "swing"],
    "شجره": ["shagara", "shagar", "shgara", "tree", "trees"],
    "النجيل": ["nageel", "nagil", "lawn"],
    # app
    "صاله": ["sala", "sa2a", "2a3a", "hall", "lobby"],
    "التطبيق": ["update", "error", "tatbee2", "tatbe2", "tatbi2", "app", "application", "abblication", "ablikeshn"],
    "بيقفل": ["by2fel", "bey2fel", "bi2fil", "crash", "crashes", "crashing"],
    "دخول": ["login", "dokhool", "do5ool", "signin"],
    "رساله": ["resala", "risala", "otp", "sms", "message", "code"],
}

_DIGITS = {"2": "", "3": "3", "5": "kh", "6": "t", "7": "h", "8": "gh", "9": "k"}
_LATIN_WORD = re.compile(r"[a-z0-9]+")
_ONLY_DIGITS = re.compile(r"^[0-9]+$")


def skeleton(word: str) -> str:
    w = word.lower()
    if _ONLY_DIGITS.match(w):
        return ""
    w = "".join(_DIGITS.get(ch, ch) for ch in w)
    w = w.replace("q", "k").replace("j", "g").replace("ch", "sh").replace("ou", "u")
    w = re.sub(r"[aeiouy]", "", w)
    return re.sub(r"(.)\1+", r"\1", w)


def _build_index():
    """skeleton -> Arabic word, leaving out skeletons that point at two concepts."""
    targets = {}
    for arabic, spellings in LEXICON.items():
        for s in spellings:
            targets.setdefault(skeleton(s), set()).add(arabic)
    return {k: v.pop() for k, v in targets.items() if len(k) >= 3 and len(v) == 1}


_INDEX = _build_index()
_EXACT = {s: ar for ar, spellings in LEXICON.items() for s in spellings}


def _lookup(word: str):
    if word in _EXACT:
        return _EXACT[word]
    for prefix in ("el", "al", "fel", "bel", "wel", "w", "b", "f", "l"):
        if word.startswith(prefix) and len(word) - len(prefix) >= 3 and word[len(prefix):] in _EXACT:
            return _EXACT[word[len(prefix):]]
    return _INDEX.get(skeleton(word))


def gloss(text: str) -> str:
    """Arabic words for the Franco/English domain words found in `text` ('' if none)."""
    words = _LATIN_WORD.findall(str(text).lower())
    hits = [ar for ar in (_lookup(w) for w in words) if ar]
    return " ".join(dict.fromkeys(hits))


def latin_skeleton_text(text: str) -> str:
    """The text's Latin words as skeletons, for a spelling-insensitive feature."""
    keys = [skeleton(w) for w in _LATIN_WORD.findall(str(text).lower())]
    return " ".join(k for k in keys if k) or "nolatin"
