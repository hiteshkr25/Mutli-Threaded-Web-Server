# server/server.py
import socket, threading, time, os, uuid, random
from datetime import datetime
from http import HTTPStatus
from typing import Dict, Any, List
from server.threadpool import ThreadPool
from server.logger_config import setup_logger
import statistics

logger = setup_logger()

metrics_lock = threading.Lock()

metrics = {
    "active_clients": 0,
    "total_requests": 0,
    "average_response_time": 0.0,
    "recent_requests": [],
    "cache_enabled": True,
    "cache_hits": 0,
    "cache_misses": 0,
    "response_times": [],
    "unique_sessions": 0,
    "thread_pool_size": 10,
    "queue_size": 0,
    "latency_trend": [],
    # status code breakdown
    "status_codes": {"200": 0, "400": 0, "404": 0, "500": 0},
    # geo (simulated) distribution
    "geo": {}
}

session_data: Dict[str, Dict[str, Any]] = {}
file_cache: Dict[str, Any] = {}

MAX_RECENT = 100
MAX_LAT = 120


def detect_device(ua: str):
    ua = (ua or "").lower()
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        return "mobile"
    if "tablet" in ua or "ipad" in ua:
        return "tablet"
    return "desktop"


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def guess_country_from_ip(ip: str):
    # lightweight deterministic pseudo-geo for demo (no external API).
    # This keeps the project offline and safe.
    buckets = ["IN", "US", "GB", "DE", "FR", "AU", "BR"]
    idx = sum(ord(c) for c in ip) % len(buckets)
    return buckets[idx]


class WebServer:
    def __init__(self, host="127.0.0.1", port=8081, num_threads=10):
        self.host = host
        self.port = port
        self.running = False
        self.thread_pool = ThreadPool(num_threads)
        os.makedirs("server/static", exist_ok=True)
        with metrics_lock:
            metrics["thread_pool_size"] = num_threads

    def start(self):
        try:
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen(300)
            self.server_socket = s
            self.running = True
            logger.info(f"[WebServer] Running at http://{self.host}:{self.port}")
        except Exception as e:
            logger.error("Cannot bind:", e)
            return

        while self.running:
            try:
                client, addr = self.server_socket.accept()
                self.thread_pool.submit(self.handle_client, client, addr)
                with metrics_lock:
                    try:
                        metrics["queue_size"] = self.thread_pool.get_queue_size()
                    except Exception:
                        metrics["queue_size"] = 0
            except Exception:
                # continue accepting
                pass

        self.stop()

    def stop(self):
        self.running = False
        try:
            self.server_socket.close()
        except Exception:
            pass
        try:
            self.thread_pool.shutdown()
        except Exception:
            pass
        logger.info("[WebServer] Stopped")

    def handle_client(self, sock, addr):
        ip = addr[0]
        start = time.time()
        with metrics_lock:
            metrics["active_clients"] += 1

        try:
            req = sock.recv(8192).decode(errors="ignore")
            if not req:
                return

            lines = req.split("\r\n")
            first = lines[0] if lines else ""
            parts = first.split()
            if len(parts) < 3:
                # bad request
                resp = b"HTTP/1.1 400 Bad Request\r\nContent-Length:11\r\n\r\nBad Request"
                try: sock.sendall(resp)
                except: pass
                status_code = 400
                rt = time.time() - start
                self.record(ip, "/", rt, status_code, "unknown")
                return

            method, path, proto = parts
            if path == "/":
                path = "/index.html"

            # small random processing to make spikes visible
            if path == "/slow":
                time.sleep(random.uniform(0.6, 1.2))
            else:
                time.sleep(random.uniform(0.02, 0.18))

            headers = {}
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip()] = v.strip()

            # produce response (cache aware)
            body, status_code = self.get_file(path, headers)

            # build response, send cookie
            cookie = f"Set-Cookie: SESSION_ID={self._ensure_session_for_ip(ip)}; Path=/; HttpOnly\r\n"
            body_bytes = body.encode("utf-8", errors="ignore")
            resp_headers = (
                f"HTTP/1.1 {status_code} {'OK' if status_code==200 else ''}\r\n"
                f"Content-Type: text/html\r\n"
                f"{cookie}"
                f"Content-Length: {len(body_bytes)}\r\n\r\n"
            ).encode("utf-8")

            sock.sendall(resp_headers + body_bytes)

            rt = time.time() - start
            device = detect_device(headers.get("User-Agent", ""))
            self.record(ip, path, rt, status_code, device)

        except Exception as e:
            logger.error(f"Client error: {e}")
        finally:
            try: sock.close()
            except: pass
            with metrics_lock:
                metrics["active_clients"] = max(0, metrics["active_clients"] - 1)

    def _ensure_session_for_ip(self, ip):
        # create a simple session id per ip if not present
        if ip in session_data:
            return session_data[ip]["session_id"]
        sid = uuid.uuid4().hex[:16]
        session_data[ip] = {
            "session_id": sid,
            "first_seen": now(),
            "last_seen": now(),
            "hit_count": 0,
            "last_path": None,
            "device_type": "unknown"
        }
        with metrics_lock:
            metrics["unique_sessions"] = len(session_data)
        return sid

    def get_file(self, path, headers=None):
        if headers is None: headers = {}
        # cache check
        if metrics["cache_enabled"] and path in file_cache:
            with metrics_lock:
                metrics["cache_hits"] += 1
            return file_cache[path]["body"], 200

        with metrics_lock:
            metrics["cache_misses"] += 1

        loc = os.path.join("server", "static", path.lstrip("/"))
        if os.path.exists(loc) and os.path.isfile(loc):
            try:
                with open(loc, "r", encoding="utf8") as f:
                    body = f.read()
            except Exception:
                body = "<h1>500 - File read error</h1>"
                return body, 500
            resp = {"body": body}
            if metrics["cache_enabled"]:
                try:
                    file_cache[path] = resp
                except Exception:
                    pass
            return body, 200
        return "<h1>404 - Not Found</h1>", 404

    def record(self, ip, path, rt, status_code, device):
        country = guess_country_from_ip(ip)
        with metrics_lock:
            metrics["total_requests"] += 1
            metrics["response_times"].append(rt)
            metrics["response_times"] = metrics["response_times"][-2000:]

            try:
                metrics["average_response_time"] = sum(metrics["response_times"]) / len(metrics["response_times"])
            except Exception:
                metrics["average_response_time"] = 0.0

            metrics["latency_trend"].append(rt * 1000.0)
            metrics["latency_trend"] = metrics["latency_trend"][-MAX_LAT:]

            code_str = str(status_code)
            if code_str not in metrics["status_codes"]:
                metrics["status_codes"][code_str] = 0
            metrics["status_codes"][code_str] += 1

            metrics["recent_requests"].insert(0, {
                "ip": ip,
                "path": path,
                "response_time": round(rt, 4),
                "status_code": status_code,
                "time": now(),
                "country": country
            })
            metrics["recent_requests"] = metrics["recent_requests"][:MAX_RECENT]

            # session book-keeping (ip grouped)
            if ip not in session_data:
                session_data[ip] = {
                    "session_id": uuid.uuid4().hex[:16],
                    "first_seen": now(),
                    "last_seen": now(),
                    "hit_count": 0,
                    "last_path": None,
                    "device_type": device
                }
            s = session_data[ip]
            s["hit_count"] = s.get("hit_count", 0) + 1
            s["last_seen"] = now()
            s["last_path"] = path
            s["device_type"] = device

            # geo counters
            if country not in metrics["geo"]:
                metrics["geo"][country] = 0
            metrics["geo"][country] += 1

    def get_session_summary(self, limit=20):
        with metrics_lock:
            return [
                {
                    "session_id": s["session_id"],
                    "first_seen": s["first_seen"],
                    "last_seen": s["last_seen"],
                    "hit_count": s["hit_count"],
                    "last_path": s.get("last_path"),
                    "device_type": s.get("device_type", "unknown")
                } for s in list(session_data.values())[:limit]
            ]


def _calc_percentiles(times: List[float], pct: float):
    if not times:
        return 0.0
    try:
        return round(1000.0 * statistics.quantiles(times, n=100)[int(pct)-1], 2)
    except Exception:
        # fallback simple
        times_ms = sorted(t * 1000.0 for t in times)
        idx = max(0, int(len(times_ms) * pct/100) - 1)
        return round(times_ms[idx], 2)


def _get_metrics_copy():
    with metrics_lock:
        times = list(metrics.get("response_times", []))
        p95 = _calc_percentiles(times, 95)
        p99 = _calc_percentiles(times, 99)
        
        session_summary = [
            {
                "session_id": s["session_id"],
                "first_seen": s["first_seen"],
                "last_seen": s["last_seen"],
                "hit_count": s["hit_count"],
                "last_path": s.get("last_path"),
                "device_type": s.get("device_type", "unknown")
            } for s in list(session_data.values())[:20]
        ]
        
        return {
            "active_clients": int(metrics.get("active_clients", 0)),
            "total_requests": int(metrics.get("total_requests", 0)),
            "average_response_time": round(float(metrics.get("average_response_time", 0.0)), 4),
            "p95_ms": p95,
            "p99_ms": p99,
            "recent_requests": list(metrics.get("recent_requests", []))[:20],
            "cache_enabled": bool(metrics.get("cache_enabled", True)),
            "cache_hits": int(metrics.get("cache_hits", 0)),
            "cache_misses": int(metrics.get("cache_misses", 0)),
            "unique_sessions": int(len(session_data)),
            "thread_pool_size": int(metrics.get("thread_pool_size", 0)),
            "queue_size": int(metrics.get("queue_size", 0)),
            "latency_trend": list(metrics.get("latency_trend", []))[-MAX_LAT:],
            "status_codes": dict(metrics.get("status_codes", {})),
            "geo": dict(metrics.get("geo", {})),
            "session_summary": session_summary
        }


get_metrics = _get_metrics_copy


def toggle_cache():
    with metrics_lock:
        metrics["cache_enabled"] = not metrics.get("cache_enabled", True)
        if not metrics["cache_enabled"]:
            file_cache.clear()
        return metrics["cache_enabled"]


server_instance = WebServer()


def start_internal_server():
    # launches server in background thread
    threading.Thread(target=server_instance.start, daemon=True).start()
