import base64
import os
import sys
from typing import Optional

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# Supply configuration through process environment before starting the API.

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import auth
import db
import telegram_client
from openai_client import ask_kater
from telegram_auth import verify_init_data

OWNER_TELEGRAM_ID = int(os.environ["OWNER_TELEGRAM_ID"])
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

# Веб-клиент — это всегда Создатель (единственный, у кого есть пароль),
# и использует тот же chat_id, что и личка владельца в Telegram-боте —
# задел на объединение памяти после cutover (см. AGENTS.md / kater-pwa-hosting.md).
CHAT_ID = OWNER_TELEGRAM_ID

WEBAPP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "webapp"
)

app = FastAPI()


def require_session(request: Request):
    token = request.cookies.get(auth.COOKIE_NAME)

    if not auth.verify_session_token(token):
        raise HTTPException(status_code=401, detail="Не авторизован")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    password = data.get("password", "")

    if not auth.check_password(password):
        raise HTTPException(status_code=403, detail="Неверный пароль")

    token = auth.create_session_token()

    response = JSONResponse({"ok": True})
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=auth.SESSION_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax"
    )

    return response


@app.post("/api/telegram-auth")
async def telegram_auth(request: Request):
    data = await request.json()
    init_data_raw = data.get("initData", "")

    user = verify_init_data(init_data_raw, TELEGRAM_TOKEN)

    if not user or user.get("id") != OWNER_TELEGRAM_ID:
        raise HTTPException(status_code=403, detail="Не похоже на Создателя")

    token = auth.create_session_token()

    response = JSONResponse({"ok": True})
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=auth.SESSION_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax"
    )

    return response


@app.post("/api/logout")
def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE_NAME)
    return response


@app.get("/api/history")
def get_history(request: Request):
    require_session(request)
    return {"messages": db.load_history(CHAT_ID)}


@app.post("/api/clear")
def clear(request: Request):
    require_session(request)
    db.clear_history(CHAT_ID)
    return {"ok": True}


@app.post("/api/chat")
async def chat(
    request: Request,
    text: str = Form(""),
    image: Optional[UploadFile] = File(None)
):
    require_session(request)

    if not text and not image:
        raise HTTPException(status_code=400, detail="Пустое сообщение")

    image_data_url = None

    if image is not None:
        content = await image.read()
        mime_type = image.content_type or "image/jpeg"
        encoded = base64.b64encode(content).decode("ascii")
        image_data_url = f"data:{mime_type};base64,{encoded}"

    tagged_text = (
        f"[Отправитель: Создатель]\n{text or '[фото без подписи]'}"
    )

    history = db.load_history(CHAT_ID)

    try:
        answer = ask_kater(history, tagged_text, image_data_url=image_data_url)
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI опять занимается хуйнёй: {e}"
        )

    db.save_message(CHAT_ID, "user", tagged_text, image_data_url=image_data_url)
    db.save_message(CHAT_ID, "assistant", answer)

    # Эхо в Telegram: бот не может притвориться, что сообщение написал сам
    # владелец, поэтому пересылает его от своего имени с пометкой источника,
    # а затем свой обычный ответ. Лучшая попытка — сбой Telegram не должен
    # ломать ответ веб-клиенту, см. telegram_client.py.
    pwa_label = f"📱 (с PWA): {text}" if text else "📱 (с PWA)"

    if image is not None:
        telegram_client.send_photo(OWNER_TELEGRAM_ID, content, caption=pwa_label)
    else:
        telegram_client.send_text(OWNER_TELEGRAM_ID, pwa_label)

    telegram_client.send_text(OWNER_TELEGRAM_ID, answer)

    return {"answer": answer}


app.mount("/", StaticFiles(directory=WEBAPP_DIR, html=True), name="webapp")
