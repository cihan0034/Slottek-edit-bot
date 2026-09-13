import os
from io import BytesIO

import requests
from flask import Flask, request
from PIL import Image, ImageOps

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TELEGRAM_FILE = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

LOGO_PATH = "logo.png"


def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": text
        },
        timeout=30
    )


def add_logo(photo_bytes):
    # Gelen fotoğrafı aç
    photo = Image.open(BytesIO(photo_bytes))
    photo = ImageOps.exif_transpose(photo).convert("RGBA")

    # SLOTTEK PNG
    logo = Image.open(LOGO_PATH).convert("RGBA")

    # Logo genişliği fotoğrafın yaklaşık %25'i
    target_width = int(photo.width * 0.25)

    ratio = target_width / logo.width
    target_height = int(logo.height * ratio)

    logo = logo.resize(
        (target_width, target_height),
        Image.Resampling.LANCZOS
    )

    # Kenarlardan boşluk
    margin = int(photo.width * 0.03)

    # Sağ alt köşe
    x = photo.width - logo.width - margin
    y = photo.height - logo.height - margin

    photo.alpha_composite(logo, (x, y))

    # Telegram'a JPG olarak gönder
    output = BytesIO()

    photo.convert("RGB").save(
        output,
        format="JPEG",
        quality=95,
        optimize=True
    )

    output.seek(0)

    return output


def process_photo(message):
    chat_id = message["chat"]["id"]

    photos = message.get("photo")

    if not photos:
        return

    # Telegram'ın gönderdiği en yüksek kaliteli fotoğraf
    file_id = photos[-1]["file_id"]

    info = requests.get(
        f"{TELEGRAM_API}/getFile",
        params={"file_id": file_id},
        timeout=30
    ).json()

    if not info.get("ok"):
        send_message(chat_id, "Fotoğraf alınamadı.")
        return

    file_path = info["result"]["file_path"]

    image_response = requests.get(
        f"{TELEGRAM_FILE}/{file_path}",
        timeout=60
    )

    edited = add_logo(image_response.content)

    requests.post(
        f"{TELEGRAM_API}/sendPhoto",
        data={
            "chat_id": chat_id,
            "caption": "✅ SLOTTEK görseli hazır."
        },
        files={
            "photo": ("slottek.jpg", edited, "image/jpeg")
        },
        timeout=60
    )


@app.route("/", methods=["GET"])
def home():
    return "SLOTTEK Edit Bot Aktif ✅", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True)

    if not data:
        return "OK", 200

    message = data.get("message")

    if not message:
        return "OK", 200

    chat_id = message["chat"]["id"]

    text = message.get("text")

    if text == "/start":
        send_message(
            chat_id,
            "👋 SLOTTEK Edit Bot\n\n"
            "Bana bir fotoğraf gönder.\n"
            "SLOTTEK PNG logosunu otomatik olarak fotoğrafın üzerine ekleyip sana geri göndereceğim."
        )

    elif message.get("photo"):
        try:
            process_photo(message)
        except Exception as e:
            print("HATA:", e)
            send_message(
                chat_id,
                "❌ Fotoğraf işlenirken bir hata oluştu."
            )

    else:
        send_message(
            chat_id,
            "📸 Lütfen bana bir fotoğraf gönder."
        )

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
