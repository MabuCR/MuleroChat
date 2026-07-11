"""
MuleroChat - FastAPI server.
Handles auth, REST endpoints, WebSocket real-time, photo uploads.
"""
import json
import secrets
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import (Cookie, FastAPI, File, Form, Request,
                     UploadFile, WebSocket, WebSocketDisconnect)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database as db
from ws_manager import manager

# ── App setup ─────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="MuleroChat")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

db.init_db()

# In-memory session store: token -> user_id
sessions: dict[str, int] = {}

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_MB = 10


# ── Session helpers ───────────────────────────────────────────────────────────

def new_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    sessions[token] = user_id
    return token


def get_current_user(session: str | None):
    if not session:
        return None
    uid = sessions.get(session)
    if not uid:
        return None
    return db.get_user_by_id(uid)


def redirect_login(msg: str = ""):
    url = f"/?error={msg}" if msg else "/"
    return RedirectResponse(url, status_code=302)


# ── Health check + PWA offline page ─────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "app": "mulerochat"}


@app.get("/offline", response_class=HTMLResponse)
async def offline_page(request: Request):
    return templates.TemplateResponse(request, "offline.html", {})


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request, error: str = "", session: str | None = Cookie(default=None)):
    user = get_current_user(session)
    if user:
        return RedirectResponse("/admin" if user["is_admin"] else "/chat", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login")
async def login(name: str = Form(...), pin: str = Form(...)):
    name = name.strip()
    pin = pin.strip()
    if not name or not pin:
        return redirect_login("Nombre y PIN son requeridos")
    if len(pin) < 4:
        return redirect_login("El PIN debe tener al menos 4 dígitos")

    user = db.get_user_by_name(name)
    if user is None:
        # Auto-register new driver
        if len(name) < 2:
            return redirect_login("Nombre muy corto")
        user = db.create_driver(name, pin)
    elif not db.verify_pin(user, pin):
        return redirect_login("PIN incorrecto")

    token = new_token(user["id"])
    dest = "/admin" if user["is_admin"] else "/chat"
    resp = RedirectResponse(dest, status_code=302)
    resp.set_cookie("session", token, httponly=True, max_age=7 * 86400)
    return resp


@app.get("/logout")
async def logout(session: str | None = Cookie(default=None)):
    if session:
        sessions.pop(session, None)
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie("session")
    return resp


# ── Driver chat page ──────────────────────────────────────────────────────────

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, session: str | None = Cookie(default=None)):
    user = get_current_user(session)
    if not user:
        return redirect_login()
    if user["is_admin"]:
        return RedirectResponse("/admin", status_code=302)
    msgs = db.get_messages(user["id"])
    return templates.TemplateResponse(request, "driver.html", {
        "user": dict(user),
        "messages": [dict(m) for m in msgs],
    })


# ── Admin panel ───────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, session: str | None = Cookie(default=None)):
    user = get_current_user(session)
    if not user:
        return redirect_login()
    if not user["is_admin"]:
        return RedirectResponse("/chat", status_code=302)

    drivers = db.get_all_drivers()
    online_ids = manager.online_driver_ids()
    driver_list = []
    for d in drivers:
        last = db.get_last_message(d["id"])
        driver_list.append({
            "id": d["id"],
            "name": d["name"],
            "online": d["id"] in online_ids,
            "unread": db.get_unread_count(d["id"]),
            "last_content": last["content"] if last else None,
            "last_photo": last["photo_url"] if last else None,
            "last_time": last["created_at"][11:16] if last else "",
        })

    return templates.TemplateResponse(request, "admin.html", {
        "user": dict(user),
        "drivers": driver_list,
        "online_json": json.dumps(list(online_ids)),
    })


# ── REST API ──────────────────────────────────────────────────────────────────

@app.get("/api/chat/{driver_id}")
async def api_get_chat(driver_id: int, session: str | None = Cookie(default=None)):
    user = get_current_user(session)
    if not user or not user["is_admin"]:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    db.mark_read(driver_id)
    msgs = db.get_messages(driver_id)
    online = manager.is_driver_online(driver_id)
    return {"messages": [dict(m) for m in msgs], "online": online}


@app.post("/api/mark-read/{driver_id}")
async def api_mark_read(driver_id: int, session: str | None = Cookie(default=None)):
    user = get_current_user(session)
    if not user or not user["is_admin"]:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    db.mark_read(driver_id)
    return {"ok": True}


@app.post("/api/upload")
async def upload_photo(file: UploadFile = File(...),
                       session: str | None = Cookie(default=None)):
    user = get_current_user(session)
    if not user:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return JSONResponse({"error": "Tipo de archivo no permitido"}, status_code=400)

    data = await file.read()
    if len(data) > MAX_MB * 1024 * 1024:
        return JSONResponse({"error": f"Máximo {MAX_MB}MB"}, status_code=400)

    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(data)
    return {"url": f"/static/uploads/{filename}"}


# ── WebSocket: Driver ─────────────────────────────────────────────────────────

@app.websocket("/ws/driver/{driver_id}")
async def ws_driver(websocket: WebSocket, driver_id: int):
    user = db.get_user_by_id(driver_id)
    if not user or user["is_admin"]:
        await websocket.close(code=4001)
        return

    await manager.connect_driver(driver_id, websocket)
    await manager.notify_driver_status(driver_id, user["name"], True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            content = data.get("content", "").strip() or None
            photo_url = data.get("photo_url") or None
            if not content and not photo_url:
                continue
            msg_id = db.save_message(driver_id, "driver", content, photo_url)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await manager.relay_driver_message(driver_id, user["name"],
                                               msg_id, content, photo_url, ts)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_driver(driver_id)
        await manager.notify_driver_status(driver_id, user["name"], False)


# ── WebSocket: Admin ──────────────────────────────────────────────────────────

@app.websocket("/ws/admin")
async def ws_admin(websocket: WebSocket):
    await manager.connect_admin(websocket)
    # Send current online snapshot
    await websocket.send_text(json.dumps({
        "type": "online_snapshot",
        "online_ids": list(manager.online_driver_ids()),
    }))
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            driver_id = data.get("driver_id")
            content = (data.get("content") or "").strip() or None
            photo_url = data.get("photo_url") or None
            if not driver_id or (not content and not photo_url):
                continue
            driver = db.get_user_by_id(driver_id)
            if not driver:
                continue
            msg_id = db.save_message(driver_id, "admin", content, photo_url)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await manager.relay_admin_message(driver_id, msg_id, content, photo_url, ts)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect_admin(websocket)
