import os
import json
import re
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from openai import OpenAI

# Загрузка переменных окружения из .env в корне проекта
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dams-secret-key-change-in-production")

# Загрузка системных промптов из файлов
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def load_prompt(filename):
    """Загружает промпт из файла"""
    filepath = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"⚠️ Промпт {filename} не найден!")
        return ""


SYSTEM_PROMPT = load_prompt("system.txt")
START_PROMPT = load_prompt("start.txt")
SETTING_PROMPT = load_prompt("setting.txt")


def clean_json_response(content):
    """Извлекает JSON из ответа, убирая мусор и чиня обрезанный JSON"""
    print(f"📥 Сырой ответ от модели: {content[:200]}...")

    content = content.strip()

    # Убираем HTML-подобные теги
    content = re.sub(r'<[^>]+>', '', content)

    # 1. Если JSON полный — возвращаем
    if content.endswith("}"):
        try:
            json.loads(content)
            return content
        except:
            pass

    # 2. Ищем валидный JSON от { до }
    start = content.find('{')
    if start != -1:
        for end in range(content.rfind('}'), start, -1):
            candidate = content[start:end + 1]
            try:
                json.loads(candidate)
                return candidate
            except:
                continue

    # 3. Если JSON обрезан — пытаемся починить
    if start != -1:
        fixed = content[start:]
        
        # Находим последнее корректное место (перед обрезанным текстом)
        # Удаляем оборванный хвост после последней закрывающей скобки/кавычки
        last_good = max(
            fixed.rfind('}'),
            fixed.rfind(']'),
            fixed.rfind('"') if fixed.count('"') % 2 == 0 else fixed.rfind('"', 0, fixed.rfind('"'))
        )
        if last_good > 0 and last_good < len(fixed) - 5:
            # Если есть большой хвост после последней хорошей позиции — обрезаем
            potential = fixed[:last_good + 1]
            # Проверяем не обрываем ли мы строку
            if potential.count('"') % 2 == 0:
                fixed = potential
        
        # Закрываем открытую кавычку
        if fixed.count('"') % 2 != 0:
            fixed += '"'
        
        # Закрываем незакрытые объекты/массивы
        open_braces = fixed.count('{') - fixed.count('}')
        open_brackets = fixed.count('[') - fixed.count(']')
        fixed += '}' * open_braces + ']' * open_brackets
        
        try:
            json.loads(fixed)
            print(f"🔧 Починили обрезанный JSON")
            return fixed
        except:
            # Если не вышло, пробуем минимальный fallback JSON
            print(f"⚠️ Стандартная починка не сработала, используем fallback")
            return '{"description": "Ошибка обработки ответа. Попробуйте другое действие.", "suggestions": ["Попробовать снова", "Начать заново"], "inventory": [], "effects": [], "image_prompt": "error terminal"}'

    print(f"❌ Не удалось извлечь JSON. Контент: {content[:300]}")
    raise ValueError("Не удалось извлечь JSON из ответа")


# Инициализация клиента OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if OPENROUTER_API_KEY:
    client = OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )
    print("✅ OpenRouter подключён!")
else:
    client = None
    print("⚠️ OPENROUTER_API_KEY не найден! Нейросеть не будет работать.")

# Модель по умолчанию (бесплатная или дешёвая)
# Варианты: "qwen/qwen3-coder:free", "google/gemma-3-12b-it:free", "meta-llama/llama-3.2-3b-instruct:free"
DEFAULT_MODEL = os.getenv("AI_MODEL", "qwen/qwen3-coder:free")

# Временное хранилище состояния игры (в памяти)
game_state = {"history": [], "inventory": [], "effects": [], "location": "start"}


@app.route("/")
def index():
    """Главная страница игры"""
    return render_template("index.html")


@app.route("/api/action", methods=["POST"])
def handle_action():
    """Обработка действия игрока"""
    import time

    start_time = time.time()

    data = request.json
    action = data.get("action", "")

    if not client:
        return jsonify(
            {
                "description": "⚠️ API не настроен. Добавь ключ в .env файл.",
                "suggestions": ["Настроить API", "Попробовать снова", "Начать заново"],
                "inventory": [],
                "effects": [],
                "image_prompt": "error terminal screen",
            }
        )

    # Формируем историю диалога для контекста
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Добавляем последние 2 хода (экономим токены и время)
    for turn in game_state["history"][-2:]:
        messages.append({"role": "user", "content": turn["action"]})
        messages.append({"role": "assistant", "content": turn["response"]})

    messages.append({"role": "user", "content": action})

    try:
        # Запрос к AI через OpenRouter
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1000,  # Достаточно для полного JSON
            response_format={"type": "json_object"},
        )

        # Проверяем, есть ли контент в ответе
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Пустой ответ от AI модели")

        # Извлекаем и чистим JSON
        content = clean_json_response(content)
        qwen_response = json.loads(content)

        # Проверяем обязательные поля
        if "description" not in qwen_response:
            raise ValueError("Отсутствует поле 'description' в ответе AI")

        # Обновляем историю
        game_state["history"].append(
            {"action": action, "response": qwen_response["description"]}
        )

        # Обновляем состояние
        game_state["inventory"] = qwen_response.get("inventory", [])
        game_state["effects"] = qwen_response.get("effects", [])

        # Логгируем время ответа
        elapsed = time.time() - start_time
        print(f"⏱ Ответ за {elapsed:.2f} сек | Модель: {DEFAULT_MODEL}")

        return jsonify(qwen_response)

    except json.JSONDecodeError as e:
        # Логгируем сырой ответ для отладки
        print(f"JSON decode error. Raw content: {content}")
        return jsonify(
            {
                "description": f"Ошибка формата ответа от DaMS. Попробуй другую формулировку.",
                "suggestions": ["Попробовать снова", "Начать заново", "Помощь"],
                "inventory": game_state["inventory"],
                "effects": game_state["effects"],
                "image_prompt": "error terminal glitch",
            }
        )
    except Exception as e:
        return jsonify(
            {
                "description": f"Ошибка DaMS: {str(e)}",
                "suggestions": ["Попробовать снова", "Начать заново", "Помощь"],
                "inventory": game_state["inventory"],
                "effects": game_state["effects"],
                "image_prompt": "error terminal glitch",
            }
        )


@app.route("/api/start", methods=["POST"])
def start_game():
    """Начало новой игры - выбор сеттинга"""
    import time

    start_time = time.time()

    game_state["history"] = []
    game_state["inventory"] = []
    game_state["effects"] = []
    game_state["location"] = "start"

    if not client:
        response = {
            "description": "DaMS загружен. API не настроен — добавь ключ в .env",
            "suggestions": ["Настроить API", "Начать заново"],
            "inventory": [],
            "effects": [],
            "image_prompt": "retro terminal loading screen",
        }
    else:
        try:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": START_PROMPT},
            ]

            response_qwen = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )

            # Проверяем на ошибки API
            if hasattr(response_qwen, 'error') and response_qwen.error:
                raise ValueError(f"Ошибка API: {response_qwen.error.get('message', 'Unknown')}")

            if not response_qwen.choices:
                raise ValueError("Пустой ответ от API (choices is None)")

            content = response_qwen.choices[0].message.content
            print(f"📝 Content: '{content[:100]}...'")

            if not content:
                raise ValueError("Пустой ответ от AI")

            content = clean_json_response(content)
            response = json.loads(content)

            if "description" not in response:
                raise ValueError("Отсутствует поле 'description'")

            game_state["history"].append(
                {"action": "start", "response": response["description"]}
            )

            elapsed = time.time() - start_time
            print(f"⏱ Ответ за {elapsed:.2f} сек | Модель: {DEFAULT_MODEL}")

        except json.JSONDecodeError as e:
            print(f"JSON decode error in start_game. Raw content: {content}")
            response = {
                "description": "Ошибка формата ответа от DaMS. Попробуй начать заново.",
                "suggestions": ["Попробовать снова", "Начать заново"],
                "inventory": [],
                "effects": [],
                "image_prompt": "error terminal",
            }
        except Exception as e:
            response = {
                "description": f"Ошибка запуска DaMS: {str(e)}",
                "suggestions": ["Попробовать снова", "Начать заново"],
                "inventory": [],
                "effects": [],
                "image_prompt": "error terminal",
            }

    return jsonify(response)


@app.route("/api/image", methods=["GET"])
def generate_image():
    """Генерирует уникальное изображение через Pollinations (без кэша)"""
    import requests as req
    from urllib.parse import quote
    import re

    prompt = request.args.get("prompt", "scene")

    try:
        # Разбиваем слитные слова и чистим
        spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', prompt)
        spaced = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', spaced)
        parts = []
        for word in spaced.split():
            if word.isupper() and len(word) > 6:
                parts.extend([word[i:i+4] for i in range(0, len(word), 4)])
            else:
                parts.append(word)
        clean = " ".join(parts)
        clean = re.sub(r'[^a-zA-Z\s]', '', clean)
        words = clean.split()[:6]
        full_prompt = " ".join(words).lower()
        print(f"🎨 '{prompt}' → '{full_prompt}'")

        safe_prompt = quote(full_prompt)
        # Уникальный seed = каждый раз новая картинка
        url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=600&height=350&nologo=true&model=flux&seed={abs(hash(full_prompt + str(prompt)))}"

        # 3 попытки
        for attempt in range(3):
            try:
                response = req.get(url, timeout=60)
                if response.status_code == 200:
                    print(f"✅ Картинка готова (попытка {attempt + 1})")
                    return response.content, 200, {
                        "Content-Type": "image/jpeg",
                        "Cache-Control": "no-store"
                    }
                else:
                    print(f"⚠️ Pollinations вернул {response.status_code} (попытка {attempt + 1})")
            except req.exceptions.Timeout:
                print(f"⏳ Таймаут (попытка {attempt + 1}/3)")
                continue
        
        print(f"❌ Pollinations не ответил за 3 попытки")
        return b"", 200, {"Content-Type": "image/jpeg"}
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return "Ошибка", 500


@app.route("/api/setting", methods=["POST"])
def choose_setting():
    """Выбор сеттинга для игры"""
    import time

    start_time = time.time()

    data = request.json
    setting = data.get("setting", "1")

    # Словарь сеттингов
    settings_map = {
        "1": "фэнтези (замок, драконы, магия)",
        "2": "научная фантастика (космос, технологии, инопланетяне)",
        "3": "постапокалипсис (разрушенный город, выживание)",
    }

    setting_name = settings_map.get(setting, settings_map["1"])

    if not client:
        return jsonify(
            {
                "description": f"Вы выбрали: {setting_name}. API не настроен.",
                "suggestions": ["Идти вперёд", "Осмотреться", "Назад"],
                "inventory": [],
                "effects": [],
                "image_prompt": "fantasy castle or sci-fi space",
            }
        )

    try:
        # Формируем промпт для выбранного сеттинга
        setting_prompt = SETTING_PROMPT.replace("{setting}", setting_name)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": setting_prompt},
        ]

        response_qwen = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        content = response_qwen.choices[0].message.content
        if not content:
            raise ValueError("Пустой ответ от AI")

        content = clean_json_response(content)
        response = json.loads(content)

        if "description" not in response:
            raise ValueError("Отсутствует поле 'description'")

        # Сохраняем выбор сеттинга в историю
        game_state["location"] = setting
        game_state["history"].append(
            {
                "action": f"Выбор сеттинга: {setting_name}",
                "response": response["description"],
            }
        )

        elapsed = time.time() - start_time
        print(f"⏱ Сеттинг за {elapsed:.2f} сек | {setting_name}")

        return jsonify(response)

    except Exception as e:
        return jsonify(
            {
                "description": f"Ошибка: {str(e)}",
                "suggestions": ["Попробовать снова", "Начать заново"],
                "inventory": [],
                "effects": [],
                "image_prompt": "error terminal",
            }
        )


if __name__ == "__main__":
    # Запуск сервера
    print("🚀 DaMS запускается на http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000)
