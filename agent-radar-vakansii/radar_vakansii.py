# -*- coding: utf-8 -*-
"""Радар вакансий: собирает свежие вакансии из Инстаграма через Apify.

Запуск:    APIFY_TOKEN=... python3 radar_vakansii.py
Проверка:  python3 radar_vakansii.py --test   (без ключа и без трат, данные из tests/)
Результат: радар-вакансий-ГГГГ-ММ-ДД.md и .csv рядом со скриптом.
"""

import csv
import difflib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

if sys.version_info < (3, 10):
    sys.exit(f"Нужен Python 3.10 или новее, а у тебя {sys.version.split()[0]}. "
             "Поставь свежий с https://www.python.org/downloads/")

ACTOR = "apify~instagram-scraper"           # профили
HASHTAG_ACTOR = "apify~instagram-scraper"   # хештеги; запасной вариант — "apify~instagram-hashtag-scraper"
API = "https://api.apify.com/v2"
TIMEOUT = 900                               # секунд на один запуск Apify
HERE = os.path.dirname(os.path.abspath(__file__))

COLUMNS = ["дата", "роль", "должность", "компания", "зарплата_min", "зарплата_max", "валюта",
           "формат", "город", "контакт", "ссылка", "источник", "оценка", "пометки", "текст"]
CURRENCY = {"RUB": "₽", "USD": "$", "EUR": "€"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip().replace(" ", "").replace("_", "")
    if not raw:
        return default
    if not raw.isdigit():
        sys.exit(f"{name}={raw} — это не число. Например: export {name}={default}")
    return int(raw)


TOKEN = os.environ.get("APIFY_TOKEN", "").strip()
DAYS = env_int("RADAR_DAYS", 14)            # за сколько дней смотрим
LIMIT = env_int("RADAR_LIMIT", 30)          # постов с одного источника
MIN_SALARY = env_int("MIN_SALARY", 60000)   # ₽ в месяц
OCR = os.environ.get("RADAR_OCR") == "1"    # читать текст с картинок (нужен pytesseract)


class ApifyError(Exception):
    pass


# ---------- Источники и фильтры ----------

def read_sources(filename: str, kind: str) -> list[str] | None:
    """Аккаунты или хештеги, по одному в строке. # — комментарий. None — файла нет."""
    path = os.path.join(HERE, filename)
    if not os.path.exists(path):
        return None
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.split(" #")[0].strip()
        # В хештегах «#вакансия» — это хештег, а «# текст» — комментарий
        if not line or (line.startswith("#") and (kind == "account" or not line[1:2].isalnum())):
            continue
        m = re.search(r"instagram\.com/(?:explore/tags/)?([^/?#\s]+)", line)
        name = urllib.parse.unquote(m.group(1) if m else line).lstrip("@#").strip().lower()
        if name and name not in out:
            out.append(name)
    return out


def load_filters() -> dict:
    path = os.path.join(HERE, "фильтры.json")
    if not os.path.exists(path):
        sys.exit("Нет файла фильтры.json — он должен лежать рядом со скриптом.")
    try:
        cfg = json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"В фильтры.json ошибка: строка {e.lineno}, символ {e.colno}. "
                 "Чаще всего это лишняя или пропущенная запятая либо кавычка.")
    try:
        return prepare(cfg)
    except (KeyError, TypeError, AttributeError) as e:
        sys.exit(f"В фильтры.json не хватает раздела или он записан не так: {e}. "
                 "Сверь с исходным файлом.")


def norm(text: str) -> str:
    return text.lower().replace("ё", "е")


SEP = r"[\s\-–—«»\"'“”]*"


def pattern(phrase: str) -> str:
    """«научн журналист» → слова как начала слов, между ними пробел, дефис или ничего."""
    parts = []
    for word in re.split(r"[\s\-–—]+", norm(phrase).strip()):
        if word == "*":
            parts.append(r".{0,40}?")
        elif word:
            parts.append(re.escape(word) + r"\w*")
    return r"(?<!\w)" + SEP.join(parts)


def any_of(phrases) -> re.Pattern:
    """Одна регулярка на список фраз. Пустой список не находит ничего."""
    if isinstance(phrases, str):
        phrases = [phrases]
    if not phrases:
        return re.compile(r"(?!x)x")
    return re.compile("|".join(f"(?:{pattern(p)})" for p in phrases))


def prepare(cfg: dict) -> dict:
    roles = []
    for name, r in cfg["роли"].items():
        combos = [[any_of(part) for part in combo] for combo in r.get("сочетания", [])]
        roles.append((name, any_of(r.get("слова", [])), combos))
    scam = cfg["мошенничество"]
    return {
        "роли": roles,
        "стоп": any_of(cfg["стоп_слова"]),
        "вакансия": any_of(cfg["признаки_вакансии"]),
        "удалённо": any_of(cfg["формат"]["удалённо"]),
        "гибрид": any_of(cfg["формат"]["гибрид"]),
        "офис": any_of(cfg["формат"]["офис"]),
        "мой_город": cfg["мой_город"],
        "города": [(name, any_of(words)) for name, words in cfg["города"].items()],
        "курсы": cfg["курсы_валют"],
        "подозрительно": any_of(scam["фразы"]),
        "без_опыта": any_of(scam["без_опыта"]),
        "много_без_опыта": scam["много_денег_без_опыта"],
        "оценка": cfg["оценка"],
        "похожесть": float(cfg["дубликаты_похожесть"]),
    }


# ---------- Apify ----------

def apify(method: str, path: str, payload: dict | None = None, timeout: int = 120):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise ApifyError(explain_http(e)) from None
    except urllib.error.URLError as e:
        raise ApifyError(f"не могу достучаться до Apify ({e.reason}). Проверь интернет.") from None
    except TimeoutError:
        raise ApifyError("Apify слишком долго не отвечает. Попробуй позже.") from None
    if not body.strip():
        raise ApifyError("Apify вернул пустой ответ.")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ApifyError("Apify вернул что-то непонятное вместо данных.") from None


def explain_http(e: urllib.error.HTTPError) -> str:
    try:
        msg = json.loads(e.read().decode("utf-8"))["error"]["message"]
    except Exception:
        msg = e.reason
    return {
        401: "Apify не принял ключ (401). Проверь APIFY_TOKEN — скопируй его заново "
             "в Apify: Settings → Integrations → API token.",
        402: "На счёте Apify не хватает денег (402). Пополни баланс или дождись нового месяца.",
        403: f"Apify не пускает (403): {msg}",
        404: "Apify не нашёл актор или запуск (404). Проверь ACTOR и HASHTAG_ACTOR в начале скрипта.",
        429: "Слишком много запросов к Apify (429). Подожди пару минут и запусти снова.",
    }.get(e.code, f"Apify вернул ошибку {e.code}: {msg}")


def run_actor(actor: str, payload: dict) -> list[dict]:
    """Запускает актор и ждёт результат до TIMEOUT секунд."""
    run = apify("POST", f"/acts/{actor}/runs?timeout={TIMEOUT}&waitForFinish=60", payload)["data"]
    deadline = time.monotonic() + TIMEOUT + 60
    while run["status"] in ("READY", "RUNNING", "TIMING-OUT", "ABORTING"):
        if time.monotonic() > deadline:
            try:
                apify("POST", f"/actor-runs/{run['id']}/abort")
            except ApifyError:
                pass
            raise ApifyError(f"Apify не уложился в {TIMEOUT // 60} минут, запуск остановлен. "
                             "Убавь RADAR_LIMIT или число источников.")
        print("  …Apify ещё собирает, жду")
        run = apify("GET", f"/actor-runs/{run['id']}?waitForFinish=60")["data"]
    if run["status"] not in ("SUCCEEDED", "TIMED-OUT"):
        raise ApifyError(f"запуск закончился со статусом {run['status']}. "
                         "Подробности — в консоли Apify, раздел Runs.")
    if run["status"] == "TIMED-OUT":
        print(f"  ⚠ Apify не успел за {TIMEOUT // 60} минут — беру то, что он успел собрать.")
    items = apify("GET", f"/datasets/{run['defaultDatasetId']}/items?clean=true&format=json",
                  timeout=300)
    return items if isinstance(items, list) else []


def profile_input(names: list[str], since: datetime) -> dict:
    return {"directUrls": [f"https://www.instagram.com/{n}/" for n in names],
            "resultsType": "posts",            # фото, карусели и видео, а не только ролики
            "resultsLimit": LIMIT,
            "onlyPostsNewerThan": since.strftime("%Y-%m-%d")}


def hashtag_input(tags: list[str], since: datetime) -> dict:
    if HASHTAG_ACTOR.endswith("instagram-hashtag-scraper"):
        return {"hashtags": tags, "resultsType": "posts", "resultsLimit": LIMIT}
    return {"directUrls": [f"https://www.instagram.com/explore/tags/{t}/" for t in tags],
            "resultsType": "posts",
            "resultsLimit": LIMIT,
            "onlyPostsNewerThan": since.strftime("%Y-%m-%d")}


def collect(accounts: list[str], tags: list[str], since: datetime) -> tuple[list[dict], list[str]]:
    """Профили и хештеги — двумя отдельными запусками: ошибка в одном не ломает другой."""
    items, problems = [], []
    batches = (("аккаунты", "profile", accounts, ACTOR, profile_input, "@"),
               ("хештеги", "hashtag", tags, HASHTAG_ACTOR, hashtag_input, "#"))
    for title, kind, names, actor, make, mark in batches:
        if not names:
            continue
        print(f"Смотрю {title}: {', '.join(mark + n for n in names)}")
        try:
            got = run_actor(actor, make(names, since))
        except ApifyError as e:
            problems.append(f"Не собрались {title}: {e}")
            print(f"⚠ Не собрались {title}: {e}")
            continue
        if not got:
            problems.append(f"По {title[:-1]}ам Apify ничего не вернул.")
            print(f"⚠ По {title[:-1]}ам Apify ничего не вернул.")
        for p in got:
            if p.get("error"):
                where = p.get("inputUrl") or p.get("url") or "?"
                problems.append(f"Apify не открыл {where}: {p.get('errorDescription') or p['error']}")
                continue
            p["_kind"], p["_tags"] = kind, tags
            items.append(p)
    return items, problems


def load_sample() -> list[dict]:
    path = os.path.join(HERE, "tests", "sample_apify.json")
    if not os.path.exists(path):
        sys.exit("Нет файла tests/sample_apify.json — без него проверка не работает.")
    try:
        items = json.load(open(path, encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"В tests/sample_apify.json ошибка: строка {e.lineno}, символ {e.colno}.")
    return [p for p in items if not p.get("error")]


# ---------- Разбор поста ----------

def post_time(p: dict) -> datetime | None:
    ts = p.get("timestamp") or p.get("takenAt") or ""
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, timezone.utc)
        when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, OSError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def source_of(p: dict) -> str:
    url = urllib.parse.unquote(p.get("inputUrl") or "")
    m = re.search(r"/explore/tags/([^/?#]+)", url)
    if m:
        return "#" + m.group(1).lower()
    m = re.search(r"instagram\.com/([^/?#]+)/?$", url)
    if m:
        return "@" + m.group(1).lower()
    if p.get("_kind") == "hashtag":
        for tag in p.get("hashtags") or []:
            if tag.lower() in p.get("_tags", []):
                return "#" + tag.lower()
        return "хештег"
    return "@" + p["ownerUsername"] if p.get("ownerUsername") else "?"


def author_of(p: dict) -> str:
    if p.get("ownerUsername"):
        return "@" + p["ownerUsername"]
    return p.get("ownerFullName") or "автор не указан"


def is_picture(p: dict) -> bool:
    if p.get("type"):
        return p["type"] in ("Image", "Sidecar")
    return not p.get("videoUrl")


def picture_text(p: dict) -> str:
    """Подписи к картинкам: Instagram сам кладёт в alt распознанный на них текст."""
    alts = [p.get("alt")] + [c.get("alt") for c in p.get("childPosts") or []]
    return "\n".join(a for a in alts if a)


_ocr_warned = False


def ocr_text(p: dict) -> str:
    """Текст с картинок через Tesseract. Выключено по умолчанию, включается RADAR_OCR=1.
    Нужны pip install pytesseract pillow и сам Tesseract с русским языком."""
    global _ocr_warned
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        if not _ocr_warned:
            print("⚠ RADAR_OCR=1, но нет pytesseract и pillow — читаю без распознавания картинок.")
            _ocr_warned = True
        return ""
    urls = [p.get("displayUrl")] + [c.get("displayUrl") for c in p.get("childPosts") or []]
    out = []
    for url in [u for u in urls if u][:4]:
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                out.append(pytesseract.image_to_string(Image.open(io.BytesIO(r.read())),
                                                       lang="rus+eng"))
        except Exception:
            continue
    return "\n".join(out)


def strip_noise(text: str) -> str:
    """Текст без хештегов, упоминаний и ссылок — чтобы понять, есть ли в подписи что-то по делу."""
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+|www\.\S+|[@#][\w.]+", " ", text)).strip()


def head_length(text: str, lines: int = 2) -> int:
    """Длина первых строк поста — роль, найденная в них, считается ролью из заголовка."""
    for i, m in enumerate(re.finditer(r"[^\n]*\S[^\n]*", text), 1):
        if i == lines:
            return m.end()
    return len(text)


def find_role(text: str, head: int, f: dict) -> tuple[str, int, bool] | None:
    """Роль, которая встретилась раньше всех: (название, позиция, в заголовке ли)."""
    best = None
    for name, words, combos in f["роли"]:
        m = words.search(text)
        if m and (best is None or m.start() < best[1]):
            best = (name, m.start(), m.start() < head)
        for combo in combos:
            hits = [part.search(text) for part in combo]
            if all(hits):
                pos = max(h.start() for h in hits)
                if best is None or pos < best[1]:
                    best = (name, pos, False)
    return best


# Зарплата: «от 80 000», «80–120к», «до 150 тыс.», «$1500», «7000 ₽ за статью»
SALARY_WORDS = re.compile(r"зарплат|з/п|з\.п|(?<!\w)зп(?!\w)|оклад|доход|оплат|вознагражд"
                          r"|гонорар|ставк|salary|компенсац")
AMOUNT = re.compile(
    r"(?P<cb>[$€₽])?\s?"
    r"(?P<n>\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+(?:[.,]\d+)?)"
    r"(?:(?P<k>[кk])(?![а-яa-z])|\s?(?P<m>тыс(?:яч\w*)?\.?|т\.\s?р\.?|тр(?![а-яa-z])|млн\.?))?"
    r"\s?(?P<ca>₽|руб\w*\.?|р\.|rub(?![a-z])|\$|usd(?![a-z])|долл\w*|€|eur(?![a-z])|евро)?")
PHONE = re.compile(r"(?:\+7|(?<!\d)8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")
NOT_MONEY = re.compile(r"\s*(?:%|лет|год|г\.|раз|мин|дн|знак|символ|слов|чел|подписчик|участник"
                       r"|просмотр|шт|/\d|:\d)")
NOT_MONEY_BARE = re.compile(r"\s*(?:час|ч\.|ч\b|стат|текст|материал|пост)")
RANGE_SEP = re.compile(r"\s*(?:[-–—]|до|to)\s*")
PER_MONTH = re.compile(r"\s*(?:/|в|за)\s*(?:мес|month)")
PER_PIECE = re.compile(r"за\s+(?:\d+\s*)?(?:стать|материал|текст|пост|публикац|знак|проект|выпуск"
                       r"|эпизод|лонгрид)|/\s*(?:стать|текст)")
PER_HOUR = re.compile(r"/\s*ч(?:ас)?(?!\w)|в\s+час|за\s+час|почасов")
PER_DAY = re.compile(r"\s*(?:/|в|за)\s*(?:день|смену)")
PER_YEAR = re.compile(r"\s*(?:/|в|за)\s*(?:год|year)|годов")


def amount_of(m: re.Match, low: str) -> dict:
    n = re.sub(r"[ \u00a0\u202f]", "", m.group("n"))
    if re.fullmatch(r"\d{1,3}[.,]\d{3}", n):        # 120.000 — разделитель тысяч, а не дробь
        n = n.replace(".", "").replace(",", "")
    mult = (m.group("k") or m.group("m") or "").lower()
    factor = 1_000_000 if mult.startswith("млн") else 1000 if mult else 1
    c = (m.group("cb") or m.group("ca") or "").lower()
    cur = None
    if c == "$" or c.startswith(("usd", "долл")):
        cur = "USD"
    elif c == "€" or c.startswith(("eur", "евро")):
        cur = "EUR"
    elif c:
        cur = "RUB"
    return {"v": float(n.replace(",", ".")) * factor, "factor": factor, "cur": cur,
            "bare": factor == 1 and cur is None, "start": m.start(), "n_start": m.start("n"),
            "end": m.end()}


def parse_salary(text: str, rates: dict) -> dict | None:
    """Первая зарплата в тексте: min, max, валюта, период, исходная строка."""
    for line in text.splitlines():
        low = PHONE.sub(lambda m: " " * len(m.group()), norm(line))
        keyword = bool(SALARY_WORDS.search(low))
        found = []
        for m in AMOUNT.finditer(low):
            i = m.start("n")
            if i > 0 and (low[i - 1].isalnum() or low[i - 1] in "+/:#№"):
                continue
            a = amount_of(m, low)
            if NOT_MONEY.match(low, a["end"]) or (a["bare"] and NOT_MONEY_BARE.match(low, a["end"])):
                continue
            found.append(a)
        j = 0
        while j < len(found):
            a = found[j]
            b = found[j + 1] if j + 1 < len(found) else None
            if b and RANGE_SEP.fullmatch(low[a["end"]:b["start"]]):
                if a["factor"] == 1 and b["factor"] > 1 and a["v"] < 1000:   # «80–120к»
                    a["v"] *= b["factor"]
                lo, hi, last = a["v"], b["v"], b
                bare = a["bare"] and b["bare"]
                cur = a["cur"] or b["cur"]
                j += 2
            else:
                before = low[:a["n_start"]][-12:]
                lo = hi = a["v"]
                if re.search(r"(?:^|\W)(?:от|from)\s*[$€₽]?\s*$", before):
                    hi = None
                elif re.search(r"(?:^|\W)(?:до|up to)\s*[$€₽]?\s*$", before):
                    lo = None
                last, bare, cur = a, a["bare"], a["cur"]
                j += 1
            top = max(v for v in (lo, hi) if v is not None)
            guess = False
            if bare and not (keyword and top >= 1000):
                if keyword and lo and hi and lo != hi and 10 <= top < 1000:   # «з/п 80-100»
                    lo, hi, guess = lo * 1000, hi * 1000, True
                else:
                    continue
            tail = low[last["end"]:last["end"] + 25]
            if PER_MONTH.match(tail):
                period = "месяц"
            elif PER_YEAR.match(tail):
                period = "год"
            elif PER_PIECE.search(tail) or PER_PIECE.search(low):
                period = "материал"
            elif PER_HOUR.search(tail) or PER_HOUR.search(low):
                period = "час"
            elif PER_DAY.match(tail):
                period = "день"
            else:
                period = "месяц"
            cur = cur or "RUB"
            rub = (hi or lo) * rates.get(cur, 1) / (12 if period == "год" else 1)   # ₽ в месяц
            return {"min": lo, "max": hi, "currency": cur, "period": period, "guess": guess,
                    "raw": line.strip()[:120], "rub": rub,
                    "monthly": period in ("месяц", "год")}
    return None


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def money(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", " ")


def salary_text(s: dict | None) -> str:
    if not s:
        return "не указана"
    sym = CURRENCY.get(s["currency"], s["currency"])
    if s["min"] and s["max"] and s["min"] != s["max"]:
        t = f"{money(s['min'])}–{money(s['max'])} {sym}"
    elif s["min"] and s["max"]:
        t = f"{money(s['min'])} {sym}"
    elif s["min"]:
        t = f"от {money(s['min'])} {sym}"
    else:
        t = f"до {money(s['max'])} {sym}"
    return t + {"год": " в год", "час": " в час", "день": " в день",
                "материал": " за материал"}.get(s["period"], "")


def detect_format(t: str, f: dict) -> tuple[str, bool]:
    remote = bool(f["удалённо"].search(t)) and not re.search(
        r"(?:не|без)\s+удал|удал\w*\s+(?:не|невозможн)", t)
    found = []
    if remote:
        found.append("удалённо")
    if f["гибрид"].search(t):
        found.append("гибрид")
    elif f["офис"].search(t):
        found.append("офис")
    return " или ".join(found), remote


def detect_city(t: str, f: dict) -> str:
    hits = [(m.start(), name) for name, rx in f["города"] if (m := rx.search(t))]
    if any(name == f["мой_город"] for _, name in hits):
        return f["мой_город"]
    return min(hits)[1] if hits else ""


EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL = re.compile(r"(?:https?://|www\.)[^\s<>«»\"')]+|(?<![\w@./])(?:t\.me|forms\.gle|docs\.google\.com"
                 r"|forms\.yandex\.ru|hh\.ru|tally\.so|clck\.ru|vk\.com|vk\.cc|taplink\.cc)/[^\s<>«»\"')]+",
                 re.I)
FORMS = ("forms.gle", "docs.google.com/forms", "forms.yandex", "yandex.ru/forms", "tally.so",
         "typeform", "airtable.com", "forms.office")
TELEGRAM = re.compile(r"(?<!\w)(?:телеграм\w*|telegram|тг|tg)\W{0,12}@([a-z0-9_]{3,32})", re.I)
MENTION = re.compile(r"(?<![\w.@])@([a-z0-9_.]{2,30})", re.I)
DIRECT = re.compile(r"директ|direct|в\s+личк|в\s+лс(?!\w)|личн\w*\s+сообщ|(?<!\w)dm(?!\w)")


def find_contacts(text: str, p: dict) -> tuple[list[str], bool]:
    """Контакты для отклика, самые удобные первыми. Второе — есть ли что-то кроме директа."""
    author = (p.get("ownerUsername") or "").lower()
    links = [u.rstrip(".,;:!?)»") for u in URL.findall(text)]
    tg = [u.lower() for u in TELEGRAM.findall(text)]
    found = [u for u in links if any(x in u.lower() for x in FORMS)]
    found += EMAIL.findall(text)
    found += [u for u in links if "t.me/" in u.lower()]
    found += [f"телеграм @{u}" for u in tg]
    found += [u for u in links if "instagram.com" not in u.lower()]
    found += ["@" + u.rstrip(".") for u in MENTION.findall(text)
              if u.rstrip(".").lower() not in tg and u.rstrip(".").lower() != author]
    found = list(dict.fromkeys(found))
    if found:
        return found, True
    if author or DIRECT.search(norm(text)):
        return [f"директ @{author}" if author else "директ"], False
    return [], False


def clean_line(line: str) -> str:
    """Строка без эмодзи и значков по краям."""
    line = re.sub(r"^[^\w@#$€₽«\"(]+", "", line.strip())
    return re.sub(r"[^\w)»\"!?.]+$", "", line).strip()


TITLE_LABEL = re.compile(r"(?<!\w)(?:ваканси[яи]|позиция|должность|position|role)(?:\s*:|\s+[—–-])\s*(.+)",
                         re.I)
TITLE_VERB = re.compile(r"(?:(?P<acc>ищем|ищет|ищут|в\s+поиске)|требуе?тся|открыт[аы]?\s+ваканси[яи]"
                        r"|нужен|нужна|hiring|приглашаем)\s*:?\s*(?P<title>.+)", re.I)
TITLE_STOP = re.compile(r"[.,!?;:]|\s[—–-]\s|\s(?:в|во|для|к\s+нам|на\s+проект|с\s+опытом)\s", re.I)


def nominative(word: str) -> str:
    """«научного редактора» → «научный редактор»: после «ищем» должность стоит в винительном."""
    parts = []
    for part in word.split("-"):
        low = part.lower()
        if len(low) >= 4 and re.fullmatch(r"[а-яё]+", low):
            if low.endswith("ого"):
                part = part[:-3] + "ый"
            elif low.endswith("его"):
                part = part[:-3] + "ий"
            elif low[-1] == "а" and low[-2] not in "аеёиоуыэюя":
                part = part[:-1]
            elif low[-1] == "я" and low[-2] not in "аеёиоуыэюя":
                part = part[:-1] + "ь"
        parts.append(part)
    return "-".join(parts)


def cut_title(text: str, accusative: bool = False) -> str:
    text = TITLE_STOP.split(text, 1)[0].strip()
    if accusative:
        words = text.split()
        text = " ".join([nominative(w) for w in words[:4]] + words[4:])
    return (text[:1].upper() + text[1:])[:80] if text else ""


def find_title(caption: str, f: dict) -> str:
    lines = [clean_line(l) for l in caption.splitlines() if clean_line(l)][:6]
    for line in lines:
        m = TITLE_LABEL.search(line)
        if m:
            return cut_title(m.group(1))
    for line in lines:
        if find_role(norm(line), 0, f):
            m = TITLE_VERB.search(line)
            return cut_title(m.group("title"), bool(m.group("acc"))) if m else cut_title(line)
    return ""


NAME = r"[A-ZА-ЯЁ0-9][\w&.\-]*(?:\s+[A-ZА-ЯЁ0-9][\w&.\-]*){0,3}"
COMPANY_LABEL = re.compile(r"(?i:компания|работодатель|company|организация)(?:\s*:|\s+[—–-])\s*"
                           r"([^\n,.;—–]+)")
COMPANY_AFTER = re.compile(
    r"(?i:\bв\s+(?:команд\w*|компани\w*|редакци\w*|студи\w*|агентств\w*|стартап\w*|издани\w*|медиа"
    r"|проект\w*|журнал\w*|лаборатори\w*)\s+(?:(?:медиа|издани\w*|журнал\w*|проект\w*|студи\w*"
    r"|агентств\w*|компани\w*)\s+)?)" r"([«\"“][^»\"”]{2,40}[»\"”]|" + NAME + ")")
COMPANY_SUBJECT = re.compile(r"^(" + NAME + r")\s+(?i:ищет|ищут|в\s+поиске|открывает|набирает|расширяет)",
                             re.M)
QUOTED = re.compile(r"«([^»]{2,40})»")
WE = re.compile(r"мы\s+ищем|нашу?\s+команд|к\s+нам\s+в|в\s+наш\w*\s+(?:команд|компани|редакци)")


def find_company(caption: str, p: dict) -> tuple[str, bool]:
    """Компания из текста. Второе — взята ли она из имени автора поста."""
    for rx in (COMPANY_LABEL, COMPANY_AFTER, COMPANY_SUBJECT, QUOTED):
        m = rx.search(caption)
        if m:
            name = m.group(1).strip(" «»\"“”")
            if len(name) >= 2:
                return name[:60], False
    if WE.search(norm(caption)) and (p.get("ownerFullName") or p.get("ownerUsername")):
        return p.get("ownerFullName") or "@" + p["ownerUsername"], True
    return "", False


# ---------- Оценка ----------

def analyse(p: dict, f: dict, now: datetime, since: datetime) -> tuple[str, dict]:
    """Причина отсева (или «ок», или «картинка») и разобранная вакансия."""
    when = post_time(p)
    if when and when < since:
        return "старые", {}
    caption = (p.get("caption") or "").strip()
    extra = picture_text(p)
    if OCR and is_picture(p) and not find_role(norm(caption + "\n" + extra), 0, f):
        extra += "\n" + ocr_text(p)
    full = caption + ("\n" + extra.strip() if extra.strip() else "")
    t = norm(full)
    base = {"key": p.get("shortCode") or p.get("url") or p.get("id"),
            "url": p.get("url") or "", "when": when or now, "author": author_of(p),
            "source": ", ".join(p.get("_sources") or [source_of(p)]), "text": caption}

    if f["стоп"].search(t):
        return "стоп-слова", {}
    role = find_role(t, head_length(norm(caption)), f)
    if not role:
        if is_picture(p) and f["вакансия"].search(t) and len(strip_noise(caption)) < 300:
            return "картинка", base
        return "не та роль", {}
    if not f["вакансия"].search(t):
        return "не вакансия", {}

    fmt, remote = detect_format(t, f)
    city = detect_city(t, f)
    in_city = city == f["мой_город"]
    if not remote and city and not in_city:
        return "формат или город", {}
    salary = parse_salary(full, f["курсы"])
    if salary and salary["monthly"] and salary["rub"] < MIN_SALARY:
        return "зарплата", {}

    company, from_author = find_company(caption, p)
    contacts, has_contact = find_contacts(full, p)
    w = f["оценка"]
    name, pos, in_head = role
    score = w["роль_в_заголовке"] if in_head else w["роль_в_тексте"]
    notes, warn, weak = [], [], []
    monthly_ok = salary and salary["monthly"] and salary["rub"] >= MIN_SALARY
    if monthly_ok:
        score += w["зарплата_не_ниже_порога"]
    if remote or in_city:
        score += w["удалёнка_или_мой_город"]
    if has_contact:
        score += w["есть_контакт"]
    if (now - (when or now)).total_seconds() <= w["свежая_дней"] * 86400:
        score += w["свежая"]

    suspicious = list(dict.fromkeys(m.group(0).strip() for m in f["подозрительно"].finditer(t)))
    if suspicious:
        score += w["подозрительные_фразы"]
        warn.append("подозрительное — " + ", ".join(f"«{s}»" for s in suspicious[:3]))
    if f["без_опыта"].search(t) and salary and salary["rub"] >= f["много_без_опыта"]:
        score += w["без_опыта_много_денег"]
        warn.append(f"без опыта и {salary_text(salary)}")
    if not company:
        score += w["нет_компании"]
        weak.append("компания не указана")
    if not has_contact:
        score += w["только_директ"]
        weak.append("контакты только через директ" if contacts else "контактов нет")
    if warn or len(weak) >= 2:
        notes.append("⚠ проверить: " + "; ".join(warn + weak))
    else:
        notes += weak

    if not salary:
        notes.append("зарплата не указана")
    elif not salary["monthly"]:
        notes.append("оплата не помесячная — с порогом не сравнивал")
    if salary and salary["guess"]:
        notes.append("зарплата без «тыс.» — решил, что в тысячах")
    if not fmt:
        notes.append("формат не указан")
    elif not remote and not city:
        notes.append(f"{fmt}, город не указан — уточни")
    if from_author:
        notes.append("компания — по имени автора поста")
    if pos >= len(caption):
        notes.append("роль нашлась только в тексте на картинке — проверь")
    if not when:
        notes.append("дата поста неизвестна")

    return "ок", base | {
        "role": name, "title": find_title(caption, f), "company": company, "salary": salary,
        "format": fmt, "city": city, "contacts": contacts, "notes": notes,
        "score": max(0, min(10, round(score))), "also": [], "also_keys": []}


def dup_text(text: str) -> str:
    t = re.sub(r"https?://\S+|www\.\S+|[@#][\w.]+", " ", norm(text))
    return re.sub(r"\W+", " ", t).strip()


def similar(a: str, b: str, threshold: float) -> bool:
    if len(a) < 60 or len(b) < 60:
        return a == b and a != ""
    if 2 * min(len(a), len(b)) / (len(a) + len(b)) < threshold:
        return False
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sm.quick_ratio() >= threshold and sm.ratio() >= threshold


def drop_duplicates(recs: list[dict], threshold: float) -> tuple[list[dict], int]:
    """Одна вакансия у нескольких авторов — оставляю самый ранний пост."""
    kept, dropped = [], 0
    for r in sorted(recs, key=lambda r: r["when"]):
        r["_dup"] = dup_text(r["text"])
        twin = next((k for k in kept if similar(k["_dup"], r["_dup"], threshold)), None)
        if twin:
            twin["also"].append(r["author"] if r["source"] == r["author"]
                                else f"{r['author']} ({r['source']})")
            twin["also_keys"].append(r["key"])
            dropped += 1
        else:
            kept.append(r)
    for r in kept:
        if r["also"]:
            r["notes"].append("также у " + ", ".join(r["also"]))
    return kept, dropped


# ---------- Вывод ----------

def load_seen(path: str) -> dict:
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_seen(path: str, seen: dict, today: str) -> None:
    border = (datetime.fromisoformat(today) - timedelta(days=120)).strftime("%Y-%m-%d")
    seen = {k: v for k, v in seen.items() if v >= border}
    with open(path, "w", encoding="utf-8") as out:
        json.dump(seen, out, ensure_ascii=False, indent=1, sort_keys=True)


def excerpt(text: str, limit: int = 500) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return "\n".join("> " + line if line.strip() else ">" for line in text.splitlines())


def card(r: dict) -> str:
    if r["source"] == r["author"]:
        where = r["source"]
    elif r["author"].startswith("@"):
        where = f"{r['source']}, пост {r['author']}"
    else:
        where = f"{r['source']}, {r['author']}"
    lines = [f"### {r['role']} · {r['company'] or 'компания не указана'} · {r['score']}/10", ""]
    if r["title"]:
        lines.append(f"**Должность:** {r['title']}  ")
    lines += [
        f"**Дата:** {r['when'].astimezone():%d.%m} · **Зарплата:** {salary_text(r['salary'])} · "
        f"**Формат:** {r['format'] or 'не указан'} · **Город:** {r['city'] or '—'}  ",
        f"**Контакт:** {', '.join(r['contacts'][:3]) or 'не указан'}  ",
        f"**Ссылка:** {r['url']}  ",
        f"**Источник:** {where}", "",
        excerpt(r["text"]) if r["text"] else "> (подписи нет)", ""]
    if r["notes"]:
        lines.append(f"**Пометки:** {'; '.join(r['notes'])}")
        lines.append("")
    return "\n".join(lines) + "\n---\n\n"


def write_md(path: str, day: str, now: datetime, viewed: int, recs: list[dict], new: list[dict],
             old: list[dict], pics: list[dict], counts: dict, roles: list[str], problems: list[str]):
    since = now - timedelta(days=DAYS)
    by_role = " · ".join(f"{name} — {sum(r['role'] == name for r in recs)}" for name in roles)
    labels = {"старые": "старые", "стоп-слова": "стоп-слова", "не та роль": "не та роль",
              "не вакансия": "не вакансия", "формат или город": "формат или город",
              "зарплата": f"зарплата ниже {money(MIN_SALARY)} ₽", "дубликаты": "дубликаты"}
    dropped = " · ".join(f"{labels[k]} — {counts[k]}" for k in labels if counts.get(k))
    with open(path, "w", encoding="utf-8") as out:
        out.write(f"# Радар вакансий — {day}\n\n"
                  f"За последние {DAYS} дней ({since.astimezone():%d.%m}–{now.astimezone():%d.%m}), "
                  "отсортировано по оценке соответствия (0–10), внутри — по дате.\n\n"
                  f"Просмотрено постов: {viewed} · прошли фильтры: {len(recs)} · "
                  f"новых с прошлого запуска: {len(new)}  \n"
                  f"По ролям: {by_role}  \n"
                  f"Отсеяно: {dropped or 'ничего'}  \n"
                  f"Текст на картинке, проверить вручную: {len(pics)}\n\n")
        for problem in problems:
            out.write(f"> ⚠ {problem}\n")
        if problems:
            out.write("\n")
        for title, part in (("Новое с прошлого запуска", new), ("Уже было", old)):
            out.write(f"## {title} ({len(part)})\n\n")
            out.write("".join(card(r) for r in part) or "Пока ничего.\n\n")
        if pics:
            out.write(f"## Текст на картинке — проверить вручную ({len(pics)})\n\n"
                      "Подпись не похожа на вакансию под твои роли, но пост — картинка или карусель, "
                      "и вакансия, скорее всего, на ней. Открой и посмотри сам.\n\n")
            for r in pics:
                short = strip_noise(r["text"])[:200] or "подписи нет"
                who = r["author"] if r["author"] == r["source"] else f"{r['source']}, {r['author']}"
                out.write(f"- {r['when'].astimezone():%d.%m} · {who} · {r['url']} — «{short}»\n")
            out.write("\n")


def write_csv(path: str, recs: list[dict]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as out:
        w = csv.DictWriter(out, fieldnames=COLUMNS)
        w.writeheader()
        for r in recs:
            s = r["salary"] or {}
            w.writerow({
                "дата": r["when"].astimezone().strftime("%Y-%m-%d"), "роль": r["role"],
                "должность": r["title"], "компания": r["company"],
                "зарплата_min": int(s["min"]) if s.get("min") else "",
                "зарплата_max": int(s["max"]) if s.get("max") else "",
                "валюта": s.get("currency", ""), "формат": r["format"], "город": r["city"],
                "контакт": ", ".join(r["contacts"][:3]), "ссылка": r["url"],
                "источник": r["source"], "оценка": r["score"], "пометки": "; ".join(r["notes"]),
                "текст": r["text"]})


# ---------- Главное ----------

def main():
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        return
    test = "--test" in sys.argv
    f = load_filters()
    if test:
        items, problems = load_sample(), []
        times = [t for t in map(post_time, items) if t]
        now = (max(times) if times else datetime.now(timezone.utc)) + timedelta(hours=1)
        out_dir = os.path.join(HERE, "tests")
        print("Режим проверки: беру посты из tests/sample_apify.json, Apify не трогаю. "
              f"«Сегодня» = {now.astimezone():%d.%m.%Y} — по самому свежему посту.")
    else:
        if not TOKEN:
            sys.exit("Нет ключа. Сделай: export APIFY_TOKEN=твой_ключ")
        accounts = read_sources("аккаунты.txt", "account")
        tags = read_sources("хештеги.txt", "tag")
        if accounts is None and tags is None:
            sys.exit("Нет файлов аккаунты.txt и хештеги.txt — положи их рядом со скриптом "
                     "и впиши источники, по одному в строке.")
        if not accounts and not tags:
            sys.exit("В аккаунты.txt и хештеги.txt нет ни одного источника — впиши хотя бы "
                     "один аккаунт (без @) или хештег (без #), по одному в строке.")
        now = datetime.now(timezone.utc)
        items, problems = collect(accounts or [], tags or [], now - timedelta(days=DAYS))
        out_dir = HERE
        if not items:
            sys.exit("Ничего не собрал.\n" + ("\n".join(f"  {p}" for p in problems) if problems else
                     "Apify ответил, но постов нет: проверь, что аккаунты открытые, "
                     "а названия без опечаток."))

    # Один и тот же пост мог прийти и с аккаунта, и с хештега
    posts = {}
    for p in items:
        key = p.get("shortCode") or p.get("url") or p.get("id") or id(p)
        src = source_of(p)
        if key in posts:
            if src not in posts[key]["_sources"]:
                posts[key]["_sources"].append(src)
        else:
            posts[key] = p | {"_sources": [src]}

    since = now - timedelta(days=DAYS)
    counts, recs, pics = {}, [], []
    for p in posts.values():
        reason, rec = analyse(p, f, now, since)
        counts[reason] = counts.get(reason, 0) + 1
        if reason == "ок":
            recs.append(rec)
        elif reason == "картинка":
            pics.append(rec)
    recs, counts["дубликаты"] = drop_duplicates(recs, f["похожесть"])
    recs.sort(key=lambda r: (r["score"], r["when"]), reverse=True)

    day = now.astimezone().strftime("%Y-%m-%d")
    seen_path = os.path.join(out_dir, ".seen.json")
    seen = load_seen(seen_path)
    new = [r for r in recs if r["key"] not in seen]
    old = [r for r in recs if r["key"] in seen]
    pics = sorted((r for r in pics if r["key"] not in seen), key=lambda r: r["when"], reverse=True)[:20]

    base = os.path.join(out_dir, f"радар-вакансий-{day}")
    write_md(base + ".md", day, now, len(posts), recs, new, old, pics, counts,
             [name for name, _, _ in f["роли"]], problems)
    write_csv(base + ".csv", recs)
    for r in recs + pics:
        for key in [r["key"]] + r.get("also_keys", []):
            seen.setdefault(key, day)
    save_seen(seen_path, seen, day)

    print(f"Готово: {base}.md — {plural(len(recs), 'вакансия', 'вакансии', 'вакансий')}, "
          f"новых: {len(new)}, проверить картинки: {len(pics)}")
    print(f"Таблица: {base}.csv")


if __name__ == "__main__":
    main()
