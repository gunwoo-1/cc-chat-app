from flask import Flask, request, jsonify, send_from_directory
import threading, time

app = Flask(__name__, static_folder="static")

lock = threading.Lock()                # 동시에 눌러도 번호·정원이 어긋나지 않게 하는 잠금
changed = threading.Condition(lock)    # 데이터가 바뀌면 기다리던 요청을 깨우는 신호
events = {}        # id -> 이벤트 정보
names = set()      # 이벤트 이름 중복 검사용 (set이라 O(1))
next_id = 1
version = 0        # 데이터가 바뀔 때마다 1씩 증가 → 화면은 바뀐 경우에만 다시 그림
WAIT = 25          # 롱 폴링 최대 대기 시간(초)

def touch():
    """데이터가 바뀌었음을 알리고, 기다리던 요청을 모두 깨운다 (lock을 잡은 상태에서 호출)"""
    global version
    version += 1
    changed.notify_all()

def summary(eid, e):
    return {"id": eid, "name": e["name"], "capacity": e["capacity"],
            "count": len(e["tickets"]), "created": e["created"],
            "open_at": e["open_at"], "close_at": e["close_at"],
            "closed_sec": e["closed_sec"]}

def read_minutes(data, key, max_value):
    """분 단위 입력을 정수로 읽는다. 잘못된 값이면 None"""
    try:
        value = int(data.get(key, 0))
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= max_value else None

@app.get("/")
def index():
    return send_from_directory("static", "index.html")

@app.get("/api/health")
def health():
    return {"status": "ok"}

# 기능 1: 이벤트 목록 (롱 폴링: 화면이 가진 버전과 같으면 바뀔 때까지 대기)
@app.get("/api/events")
def list_events():
    since = request.args.get("version", -1, type=int)
    with changed:
        changed.wait_for(lambda: version != since, timeout=WAIT)
        return jsonify({"now": time.time(), "version": version,
                        "events": [summary(i, e) for i, e in events.items()]})

@app.get("/api/events/<int:eid>")
def get_event(eid):
    with lock:
        e = events.get(eid)
        if e is None:
            return {"error": "없는 이벤트입니다"}, 404
        return jsonify({**summary(eid, e), "now": time.time()})

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
    open_in = read_minutes(data, "open_in", 60)
    if open_in is None:
        return {"error": "오픈 예약은 0~60분 사이로 정하세요"}, 400
    close_in = read_minutes(data, "close_in", 180)
    if close_in is None:
        return {"error": "마감 시각은 오픈 후 0~180분 사이로 정하세요"}, 400

    now = time.time()
    open_at = now + open_in * 60
    close_at = open_at + close_in * 60 if close_in > 0 else None   # 0이면 마감 시각 없음
    with lock:
        if name in names:
            return {"error": "이미 있는 이벤트입니다"}, 409
        eid = next_id
        next_id += 1
        names.add(name)
        events[eid] = {"name": name, "capacity": capacity,
                       "tickets": [], "nicknames": set(), "created": now,
                       "open_at": open_at, "close_at": close_at, "closed_sec": None}
        touch()
    return {"id": eid, "name": name, "capacity": capacity}, 201

# 기능 3: 대기 명단 (롱 폴링: 화면이 가진 개수보다 늘어날 때까지 대기)
@app.get("/api/events/<int:eid>/tickets")
def get_tickets(eid):
    after = request.args.get("after", 0, type=int)
    with changed:
        changed.wait_for(lambda: eid not in events or len(events[eid]["tickets"]) > after,
                         timeout=WAIT)
        e = events.get(eid)
        if e is None:
            return {"error": "없는 이벤트입니다"}, 404
        return jsonify({"now": time.time(), "closed_sec": e["closed_sec"],
                        "tickets": e["tickets"][after:]})

# 기능 2: 번호표 뽑기 (오픈 시각 → 마감 시각 → 중복 → 정원 순서로 검사 후 번호 발급)
@app.post("/api/events/<int:eid>/tickets")
def draw_ticket(eid):
    nick = str((request.get_json(silent=True) or {}).get("nickname", "")).strip()
    if not nick:
        return {"error": "닉네임을 입력하세요"}, 400
    if len(nick) > 20:
        return {"error": "닉네임은 20자 이하로 입력하세요"}, 400

    with lock:
        now = time.time()
        e = events.get(eid)
        if e is None:
            return {"error": "없는 이벤트입니다"}, 404
        if now < e["open_at"]:
            return {"error": f"아직 오픈 전입니다 ({int(e['open_at'] - now) + 1}초 남음)"}, 403
        if e["close_at"] is not None and now >= e["close_at"]:
            return {"error": "모집 시간이 끝났습니다"}, 409
        if nick in e["nicknames"]:
            return {"error": "이미 번호표를 받았습니다"}, 409
        if len(e["tickets"]) >= e["capacity"]:
            return {"error": "선착순이 마감되었습니다"}, 409

        number = len(e["tickets"]) + 1
        ms = int(now * 1000) % 1000
        e["tickets"].append({"number": number, "nickname": nick,
                             "time": f"{time.strftime('%H:%M:%S')}.{ms:03d}"})
        e["nicknames"].add(nick)
        if number == e["capacity"]:
            e["closed_sec"] = round(now - e["open_at"], 2)
        touch()   # 기다리던 모든 화면에 즉시 알림
    return {"number": number}, 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)