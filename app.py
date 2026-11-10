from flask import Flask, request, jsonify, send_from_directory
import threading, time

app = Flask(__name__, static_folder="static")
lock = threading.Lock()
rooms = {}   # id -> {"name": str, "messages": [...]}
next_id = 1

@app.get("/")
def index():
    return send_from_directory("static", "index.html")

@app.get("/api/health")
def health():
    return {"status": "ok"}

# 기능 1: 채팅방 목록 / 생성
@app.get("/api/rooms")
def list_rooms():
    with lock:
        return jsonify([{"id": i, "name": r["name"], "count": len(r["messages"])}
                        for i, r in rooms.items()])

@app.post("/api/rooms")
def create_room():
    global next_id
    name = (request.get_json(silent=True) or {}).get("name", "").strip()
    if not name:
        return {"error": "방 이름을 입력하세요"}, 400
    if len(name) > 30:
        return {"error": "방 이름은 30자 이하로 입력하세요"}, 400
    with lock:
        if any(r["name"] == name for r in rooms.values()):
            return {"error": "이미 있는 방 이름입니다"}, 409
        rid = next_id
        next_id += 1
        rooms[rid] = {"name": name, "messages": []}
    return {"id": rid, "name": name}, 201

# 기능 3: 메시지 조회 / 전송
@app.get("/api/rooms/<int:rid>/messages")
def get_messages(rid):
    after = request.args.get("after", 0, type=int)
    with lock:
        if rid not in rooms:
            return {"error": "없는 방입니다"}, 404
        return jsonify(rooms[rid]["messages"][after:])

@app.post("/api/rooms/<int:rid>/messages")
def post_message(rid):
    data = request.get_json(silent=True) or {}
    nick = data.get("nickname", "").strip()
    text = data.get("text", "").strip()
    if not nick:
        return {"error": "닉네임이 필요합니다"}, 400
    if not text:
        return {"error": "메시지를 입력하세요"}, 400
    with lock:
        if rid not in rooms:
            return {"error": "없는 방입니다"}, 404
        rooms[rid]["messages"].append(
            {"nickname": nick, "text": text[:500], "time": time.strftime("%H:%M:%S")})
    return {"ok": True}, 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)