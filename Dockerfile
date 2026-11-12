FROM python:3.12-slim
WORKDIR /app

# 의존성 목록을 먼저 복사해서 설치 → 코드만 바뀌면 이 단계는 캐시를 재사용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 운영용 서버 gunicorn
# -w 1: 데이터가 메모리에 있으므로 프로세스는 1개 (2개면 서로 데이터가 달라짐)
# --threads 100: 롱 폴링으로 대기하는 접속을 동시에 처리
CMD ["gunicorn", "-w", "1", "--threads", "100", "--timeout", "60", "-b", "0.0.0.0:5000", "app:app"]