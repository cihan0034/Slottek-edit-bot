import os
from io import BytesIO

import requests
from flask import Flask, request
from PIL import Image, ImageOps, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
TELEGRAM_FILE = f"https://api.telegram.org/file/bot{BOT_TOKEN}"

LOGO_PATH = "logo.png"

# Ayarlar
TARGET_LONG_EDGE = 7680          # 8K uzun kenar
LOGO_WIDTH_RATIO = 0.43          # logo genişliği = görselin %43'ü
BOTTOM_MARGIN_RATIO = 0.045      # alttan boşluk
JPEG_QUALITY = 96                # çıktı kalitesi


def send_message(chat_id, text, reply_to_message_id=None):
    data = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_to_message_id:
        data["reply_to_message_id"] = reply_to_message_id

    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        data=data,
        timeout=60
    )


def send_document(chat_id, file_bytes, filename="slottek_8k.jpg", caption="Hazır ✅", reply_to_message_id=None):
    data = {
        "chat_id": chat_id,
        "caption": caption,
    }
    if reply_to_message_id:
        data["reply_to_message_id"] = reply_to_message_id

    files = {
        "document": (filename, file_bytes, "image/jpeg")
    }

    requests.post(
        f"{TELEGRAM_API}/sendDocument",
        data=data,
        files=files,
        timeout=120
    )


def get_file_path(file_id):
    r = requests.get(
        f"{TELEGRAM_API}/getFile",
        params={"file_id": file_id},
        timeout=60
    )
    result = r.json()
    if not result.get("ok"):
        raise Exception(f"getFile hatası: {result}")
    return result["result"]["file_path"]


def download_telegram_file(file_path):
    r = requests.get(f"{TELEGRAM_FILE}/{file_path}", timeout=120)
    r.raise_for_status()
    return r.content


def load_logo():
    logo = Image.open(LOGO_PATH).convert("RGBA")

    # Şeffaf boşlukları kırp
    alpha = logo.getchannel("A")
    bbox = alpha.getbbox()
    if bbox:
        logo = logo.crop(bbox)

    return logo


def upscale_to_8k(img):
    width, height = img.size
    long_edge = max(width, height)

    if long_edge >= TARGET_LONG_EDGE:
        return img

    scale = TARGET_LONG_EDGE / long_edge
    new_width = int(width * scale)
    new_height = int(height * scale)

    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)


def add_logo_and_make_8k(photo_bytes):
    # Ana görseli aç
    photo = Image.open(BytesIO(photo_bytes))
    photo = ImageOps.exif_transpose(photo).convert("RGBA")

    # 8K uzun kenara upscale
    photo = upscale_to_8k(photo)

    # Logo yükle
    logo = load_logo()

    # Fotoğrafa göre logo boyutu
    target_width = int(photo.width * LOGO_WIDTH_RATIO)
    scale = target_width / logo.width
    target_height = int(logo.height * scale)

    logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)

    # Tam orta alt
    x = (photo.width - logo.width) // 2
    bottom_margin = int(photo.height * BOTTOM_MARGIN_RATIO)
    y = photo.height - logo.height - bottom_margin

    # Ekleyelim
    photo.alpha_composite(logo, (x, y))

    # JPEG olarak çıktı ver
    output = BytesIO()
    rgb_photo = photo.convert("RGB")
    rgb_photo.save(
        output,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
        subsampling=0
    )
    output.seek(0)
    return output


def process_photo_message(message):
    chat_id = message["chat"]["id"]
    message_id = message["message_id"]

    try:
        send_message(chat_id, "Görsel hazırlanıyor, lütfen bekleyin... ⏳", reply_to_message_id=message_id)

        # Eğer normal fotoğraf geldiyse
        if "photo" in message:
            file_id = message["photo"][-1]["file_id"]

        # Eğer belge olarak resim geldiyse
        elif "document" in message and str(message["document"].get("mime_type", "")).startswith("image/"):
            file_id = message["document"]["file_id"]

        else:
            send_message(chat_id, "Lütfen bir fotoğraf ya da resim dosyası gönder.", reply_to_message_id=message_id)
            return

        file_path = get_file_path(file_id)
        photo_bytes = download_telegram_file(file_path)
        final_file = add_logo_and_make_8k(photo_bytes)

        send_document(
            chat_id,
            final_file,
            filename="slottek_8k.jpg",
            caption="Hazır ✅",
            reply_to_message_id=message_id
        )

    except Exception as e:
        send_message(chat_id, f"Hata oluştu: {str(e)}", reply_to_message_id=message_id)


def handle_update(update):
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text == "/start":
        send_message(
            chat_id,
            "SLOTTEK edit bot aktif ✅\n\n"
            "Bana bir fotoğraf gönder.\n"
            "Logo görselin alt orta kısmına eklenir ve sana yüksek kalite geri gönderilir.\n\n"
            "En iyi kalite için resmi mümkünse belge olarak da gönderebilirsin."
        )
        return

    if "photo" in message:
        process_photo_message(message)
        return

    if "document" in message and str(message["document"].get("mime_type", "")).startswith("image/"):
        process_photo_message(message)
        return

    if text:
        send_message(chat_id, "Bana bir fotoğraf gönder, üzerine SLOT TEK ekleyeyim.")


@app.route("/", methods=["GET", "POST"])
def root():
    if request.method == "GET":
        return "SLOTTEK Edit Bot Aktif ✅", 200

    update = request.get_json(silent=True) or {}
    handle_update(update)
    return {"ok": True}, 200


@app.route("/webhook", methods=["POST", "GET"])
def webhook():
    if request.method == "GET":
        return "Webhook aktif ✅", 200

    update = request.get_json(silent=True) or {}
    handle_update(update)
    return {"ok": True}, 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
