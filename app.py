from flask import Flask, request, jsonify, send_from_directory
import threading, time

app = Flask(__name__, static_folder="static")
lock = threading.Lock()   # 동시에 눌러도 번호와 정원이 어긋나지 않게 하는 잠금
events = {}               # id -> {"name": 이름, "capacity": 정원, "tickets": [번호표 목록]}
next_id = 1

@app.get("/")
def index():
    return send_from_directory("static", "index.html")

@app.get("/api/health")
def health():
    return {"status": "ok"}

# 기능 1: 이벤트 목록 / 만들기
@app.get("/api/events")
def list_events():
    with lock:
        return jsonify([{"id": i, "name": e["name"], "capacity": e["capacity"],
                         "count": len(e["tickets"])} for i, e in events.items()])

@app.post("/api/events")
def create_event():
    global next_id
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return {"error": "이벤트 이름을 입력하세요"}, 400
    if len(name) > 30:
        return {"error": "이벤트 이름은 30자 이하로 입력하세요"}, 400
    try:
        capacity = int(data.get("capacity"))
    except (TypeError, ValueError):
        return {"error": "정원을 숫자로 입력하세요"}, 400
    if not 1 <= capacity <= 1000:
        return {"error": "정원은 1명 이상 1000명 이하로 입력하세요"}, 400
    with lock:
        if any(e["name"] == name for e in events.values()):
            return {"error": "이미 있는 이벤트입니다"}, 409
        eid = next_id
        next_id += 1
        events[eid] = {"name": name, "capacity": capacity, "tickets": []}
    return {"id": eid, "name": name, "capacity": capacity}, 201

# 기능 3: 대기 명단 조회
@app.get("/api/events/<int:eid>/tickets")
def get_tickets(eid):
    after = request.args.get("after", 0, type=int)
    with lock:
        if eid not in events:
            return {"error": "없는 이벤트입니다"}, 404
        return jsonify(events[eid]["tickets"][after:])

# 기능 2: 번호표 뽑기 (도착 순서대로 번호 부여, 정원이 차면 마감)
@app.post("/api/events/<int:eid>/tickets")
def draw_ticket(eid):
    nick = str((request.get_json(silent=True) or {}).get("nickname", "")).strip()
    if not nick:
        return {"error": "닉네임을 입력하세요"}, 400
    if len(nick) > 20:
        return {"error": "닉네임은 20자 이하로 입력하세요"}, 400
    with lock:
        if eid not in events:
            return {"error": "없는 이벤트입니다"}, 404
        tickets = events[eid]["tickets"]
        if any(t["nickname"] == nick for t in tickets):
            return {"error": "이미 번호표를 받았습니다"}, 409
        if len(tickets) >= events[eid]["capacity"]:
            return {"error": "선착순이 마감되었습니다"}, 409
        number = len(tickets) + 1
        tickets.append({"number": number, "nickname": nick,
                        "time": time.strftime("%H:%M:%S")})
    return {"number": number}, 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)