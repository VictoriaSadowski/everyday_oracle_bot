import os
import json
import random
import asyncio
from pathlib import Path
from hashlib import sha1
from typing import Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types.input_file import BufferedInputFile

# =========================
# НАСТРОЙКИ
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # ← из окружения Render
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден в переменных окружения (Render → Environment).")

BASE_DIR = Path(__file__).parent.resolve()

QUOTES_DIR = BASE_DIR / "quotes"
IMAGES_DIR = BASE_DIR / "images"
STATE_FILE = BASE_DIR / "state.json"

# создадим папки, если они вдруг не залиты
for p in (QUOTES_DIR, IMAGES_DIR):
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"⚠️ Не удалось создать {p}: {e}")

RECENT_N = 20  # глубина анти-повтора
IMG_EXTS = {".jpg", ".jpeg", ".png"}

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()

# =========================
# АНТИ-ПОВТОР (состояние)
# =========================
def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️ Ошибка чтения state.json: {e}")
    return {}

def _save_state(st: dict):
    try:
        STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Ошибка записи state.json: {e}")

def _hash_text(s: str) -> str:
    return sha1(s.encode("utf-8")).hexdigest()[:16]

def _user_bucket(st: dict, user_id: int, cat_key: str) -> list:
    u = st.setdefault(str(user_id), {})
    return u.setdefault(cat_key, [])

def _remember(st: dict, user_id: int, cat_key: str, key: str):
    u = st.setdefault(str(user_id), {})
    bucket = u.setdefault(cat_key, [])
    bucket.append(key)
    if len(bucket) > RECENT_N:
        del bucket[: len(bucket) - RECENT_N]

def pick_non_repeating(user_id: int, cat_key: str, items: list[str]) -> str:
    items = items or ["(нет данных)"]
    st = _load_state()
    seen = set(_user_bucket(st, user_id, cat_key))
    candidates = [x for x in items if _hash_text(x) not in seen]
    if not candidates:
        st.setdefault(str(user_id), {})[cat_key] = []
        _save_state(st)
        candidates = items[:]
    choice = random.choice(candidates)
    _remember(st, user_id, cat_key, _hash_text(choice))
    _save_state(st)
    return choice

def pick_image_non_repeating(user_id: int, cat_key: str, folder: Path) -> Optional[BufferedInputFile]:
    try:
        imgs = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTS]
    except Exception as e:
        print(f"⚠️ Не удалось прочитать папку {folder}: {e}")
        imgs = []
    if not imgs:
        return None
    st = _load_state()
    last_key = f"{cat_key}__last_image"
    last = st.get(str(user_id), {}).get(last_key)
    choices = [p for p in imgs if p.name != last] or imgs
    img = random.choice(choices)
    u = st.setdefault(str(user_id), {})
    u[last_key] = img.name
    _save_state(st)
    try:
        return BufferedInputFile(img.read_bytes(), filename=img.name)
    except Exception as e:
        print(f"⚠️ Не удалось прочитать файл изображения {img}: {e}")
        return None

# =========================
# ЗАГРУЗКА ЦИТАТ
# =========================
def load_quotes(file_path: Path) -> list[str]:
    try:
        if not file_path.exists():
            print(f"⚠️ Файл {file_path} не найден.")
            return ["(нет цитат)"]
        lines = [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return lines or ["(файл пуст)"]
    except Exception as e:
        print(f"⚠️ Ошибка чтения {file_path}: {e}")
        return ["(ошибка чтения файла)"]

# =========================
# КЛАВИАТУРА
# =========================
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎬 Movies"), KeyboardButton(text="🎵 Songs")],
        [KeyboardButton(text="✨ Affirmations"), KeyboardButton(text="🎲 Random")]
    ],
    resize_keyboard=True
)

# =========================
# /start
# =========================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "Привет! 💫 Я твой ежедневный оракул.\nВыбери категорию:",
        reply_markup=keyboard
    )

# =========================
# MOVIES
# =========================
@dp.message(F.text == "🎬 Movies")
async def movies_category(message: types.Message):
    sub_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Supernatural"), KeyboardButton(text="Friends")],
            [KeyboardButton(text="Rebelde Way")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выбери подкатегорию 🎥", reply_markup=sub_kb)

@dp.message(F.text.in_({"Supernatural", "Friends", "Rebelde Way"}))
async def movie_sub(message: types.Message):
    tag = message.text.lower().replace(" ", "_")
    quotes_file = QUOTES_DIR / "movies.txt"
    all_lines = load_quotes(quotes_file)
    lines = [l.split("]", 1)[1].strip() for l in all_lines if l.startswith(f"[{tag}]")]
    quote = pick_non_repeating(message.from_user.id, f"movies:{tag}", lines)
    folder = IMAGES_DIR_
