import base64
import json
import os
import posixpath
import re
import urllib.parse
import urllib.request
import urllib.error
import uuid
import threading
import h3_comfy
import h3_prompt_agent
import rig_export
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
RES = r"I:\彩虹AI\design\视频素材_design\Walulu萌宠\多角色【deepseek】"
FILL = r"C:\Users\root\WorkBuddy\Walulu游戏素材\spine_fill"
CHARACTER_SOURCE = r"I:\彩虹AI\design\AI玩具_design\美术资源\棉花娃娃\基础角色-测试"
UPLOADS = os.path.join(ROOT, "studio_v3", "uploads")
CHARACTERS = os.path.join(UPLOADS, "characters")
H3_SLOTS = threading.BoundedSemaphore(2)


def character_manifest_path(character_id):
    if not re.fullmatch(r"char_[a-f0-9]{12}", character_id or ""):
        raise ValueError("无效角色 ID")
    return os.path.join(CHARACTERS, character_id, "manifest.json")


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        path = posixpath.normpath(urllib.parse.unquote(path))
        parts = [p for p in path.split("/") if p and p not in (".", "..")]
        if parts and parts[0] == "res":
            base, parts = RES, parts[1:]
        elif parts and parts[0] == "fill":
            base, parts = FILL, parts[1:]
        elif parts and parts[0] == "character-source":
            base, parts = CHARACTER_SOURCE, parts[1:]
        elif len(parts) >= 3 and parts[0] == "character-assets":
            character_id, filename = parts[1], parts[2]
            try:
                manifest_path = character_manifest_path(character_id)
                with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                    manifest = json.load(manifest_file)
                if filename not in manifest.get("views", {}).values():
                    return os.path.join(ROOT, "__not_found__")
                base, parts = os.path.dirname(manifest_path), [filename]
            except (ValueError, OSError, json.JSONDecodeError):
                return os.path.join(ROOT, "__not_found__")
        elif parts and parts[0] == "res2":
            base, parts = os.path.join(ROOT, "asset_v2"), parts[1:]
        else:
            base = ROOT
        full = base
        for p in parts:
            full = os.path.join(full, p)
        return full

    def send_head(self):
        self.__dict__.pop("_range_remaining", None)
        path = self.translate_path(self.path)
        if not os.path.isfile(path) or os.path.splitext(path)[1].lower() not in {".mp4", ".webm"}:
            return super().send_head()
        try:
            file = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None
        size = os.fstat(file.fileno()).st_size
        byte_range = self.headers.get("Range")
        modified = self.date_time_string(os.fstat(file.fileno()).st_mtime)
        if self.headers.get("If-Range") not in (None, modified):
            byte_range = None
        if not byte_range:
            self.send_response(200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Content-Length", str(size))
            self.send_header("Last-Modified", self.date_time_string(os.fstat(file.fileno()).st_mtime))
            self.end_headers()
            return file
        match = re.fullmatch(r"bytes=([0-9]{0,18})-([0-9]{0,18})", byte_range.strip())
        if not match or not any(match.groups()) or "," in byte_range:
            file.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        first, last = match.groups()
        if first:
            start = int(first)
            end = int(last) if last else size - 1
        else:
            suffix = int(last)
            if suffix <= 0:
                start, end = size, size - 1
            else:
                start, end = max(0, size - suffix), size - 1
        if start >= size or end < start:
            file.close()
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        end = min(end, size - 1)
        file.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Last-Modified", self.date_time_string(os.fstat(file.fileno()).st_mtime))
        self.end_headers()
        self._range_remaining = end - start + 1
        return file

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_range_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        del self._range_remaining
        while remaining:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        if not getattr(self, "_h3_request", False):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        path = urllib.parse.urlsplit(self.path).path
        self._h3_request = path.startswith(("/api/h3/", "/api/comfy/")) or path in {"/api/video/tasks", "/api/video/tasks/status"}
        if self._h3_request or path == "/api/video/ark-output":
            try:
                h3_comfy.check_origin(self)
            except h3_comfy.H3Error as exc:
                self._json_response(exc.status, {"ok": False, "error": str(exc)})
                return
        self.send_response(204)
        self.end_headers()

    def _json_response(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _h3_call(self, callback):
        if not H3_SLOTS.acquire(blocking=False):
            self._json_response(429, {"ok": False, "error": "H3 请求并发已满，请稍后重试"})
            return
        try:
            callback()
        except h3_comfy.H3Error as exc:
            self._json_response(exc.status, {"ok": False, "error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            self._json_response(502, {"ok": False, "error": "H3 服务响应异常，未能确认操作结果；请检查本地服务日志"})
        finally:
            H3_SLOTS.release()

    def _seedance_video(self, query):
        # Resolve only an existing Ark task; never accept a client-supplied URL.
        h3_comfy.check_origin(self)
        params = urllib.parse.parse_qs(query, keep_blank_values=True)
        if set(params) != {"task_id"} or len(params["task_id"]) != 1:
            raise h3_comfy.H3Error("视频代理需要唯一 task_id")
        task_id = params["task_id"][0]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", task_id):
            raise h3_comfy.H3Error("无效视频任务 ID")
        key = os.environ.get("ARK_API_KEY")
        if not key:
            raise h3_comfy.H3Error("未设置 ARK_API_KEY，无法读取历史视频", 503)
        task = h3_comfy.request_json(
            "https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/" + task_id,
            headers={"Authorization": "Bearer " + key}, timeout=30, service="历史视频查询")
        url = task.get("content", {}).get("video_url")
        if task.get("status") != "succeeded" or not isinstance(url, str):
            raise h3_comfy.H3Error("该任务尚未返回可播放视频，请刷新结果", 409)
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or parsed.username or parsed.password or
                parsed.port not in (None, 443) or
                parsed.hostname != "ark-acg-cn-beijing.tos-cn-beijing.volces.com"):
            raise h3_comfy.H3Error("视频来源不在已确认的方舟输出域名中", 502)
        headers = {}
        byte_range = self.headers.get("Range")
        if byte_range:
            match = re.fullmatch(r"bytes=(\d{0,18})-(\d{0,18})", byte_range)
            if not match or not any(match.groups()):
                raise h3_comfy.H3Error("只支持单段 bytes Range", 416)
            start, end = match.groups()
            if (start and end and int(start) > int(end)) or (not start and int(end) == 0):
                raise h3_comfy.H3Error("无效视频 Range", 416)
            headers["Range"] = byte_range
        try:
            response = h3_comfy._open(urllib.request.Request(url, headers=headers), timeout=60)
        except urllib.error.HTTPError as exc:
            if exc.code == 416:
                self.send_response(416)
                if exc.headers.get("Content-Range"):
                    self.send_header("Content-Range", exc.headers["Content-Range"])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            raise h3_comfy.H3Error(f"历史视频读取失败 HTTP {exc.code}；可刷新结果后重试", 502) from None
        except (OSError, TimeoutError):
            raise h3_comfy.H3Error("历史视频读取连接失败或超时", 502) from None
        with response:
            if response.status not in (200, 206):
                raise h3_comfy.H3Error("历史视频响应状态无效", 502)
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if content_type not in {"video/mp4", "video/webm", "application/octet-stream", "binary/octet-stream"}:
                raise h3_comfy.H3Error("历史视频返回的不是支持的媒体文件", 502)
            self.send_response(response.status)
            self.send_header("Content-Type", "video/webm" if content_type == "video/webm" else "video/mp4")
            self.send_header("X-Content-Type-Options", "nosniff")
            for name in ("Content-Length", "Content-Range", "Accept-Ranges", "ETag", "Last-Modified"):
                if response.headers.get(name):
                    self.send_header(name, response.headers[name])
            self.end_headers()
            try:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except (OSError, TimeoutError):
                self.close_connection = True

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        self._h3_request = parsed.path.startswith(("/api/h3/", "/api/comfy/"))
        if parsed.path == "/api/video/ark-output":
            self._h3_request = True
            try:
                self._seedance_video(parsed.query)
            except h3_comfy.H3Error as exc:
                self._json_response(exc.status, {"ok": False, "error": str(exc)})
            return
        if parsed.path == "/api/h3/health":
            self._h3_call(lambda: self._json_response(200, h3_comfy.health()))
            return
        if parsed.path == "/api/comfy/video":
            self._h3_call(lambda: h3_comfy.proxy_video(self, parsed.query))
            return
        if parsed.path == "/api/health":
            self._json_response(200, {"ok": True, "api_key_configured": bool(os.environ.get("ARK_API_KEY"))})
            return
        if parsed.path == "/api/characters":
            characters = []
            if os.path.isdir(CHARACTERS):
                for entry in os.scandir(CHARACTERS):
                    if not entry.is_dir():
                        continue
                    try:
                        with open(os.path.join(entry.path, "manifest.json"), "r", encoding="utf-8") as manifest_file:
                            characters.append(json.load(manifest_file))
                    except (OSError, json.JSONDecodeError):
                        continue
            self._json_response(200, {"ok": True, "characters": characters})
            return
        super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/rig/export":
            self._h3_request = True
            try:
                h3_comfy.check_origin(self)
                payload = h3_comfy.read_payload(self, 12_000_000)
                self._json_response(200, rig_export.export_project(payload.get('project')))
            except h3_comfy.H3Error as exc:
                self.close_connection = True
                self._json_response(exc.status, {"ok": False, "error": str(exc)})
            except rig_export.ExportError as exc:
                self._json_response(422, {"ok": False, "error": str(exc)})
            return
        if path == "/api/video/delete":
            self._h3_request = True
            try:
                h3_comfy.check_origin(self)
                payload = h3_comfy.read_payload(self, 64_000)
                task_id = payload.get("task_id")
                if not isinstance(task_id, str) or not re.fullmatch(r"(?:comfy_)?[A-Za-z0-9_-]{1,256}", task_id):
                    raise h3_comfy.H3Error("无效任务 ID")
                self._json_response(501, {"ok": False, "deleted": False,
                    "error": "当前服务没有可验证的远端输出文件删除能力；视频与历史均未删除。请先在 Comfy 主机配置受限的文件删除服务，或为云端任务提供明确承诺删除媒体文件的接口。"})
            except h3_comfy.H3Error as exc:
                self._json_response(exc.status, {"ok": False, "deleted": False, "error": str(exc)})
            return
        self._h3_request = path.startswith(("/api/h3/", "/api/comfy/"))
        video_payload = None
        if path in {"/api/h3/translate", "/api/h3/optimize", "/api/video/tasks", "/api/video/tasks/status"}:
            try:
                # 先校验来源及有界 JSON，再根据模型/任务前缀分流，不能先依赖 ARK key。
                h3_comfy.check_origin(self)
                video_payload = h3_comfy.read_payload(self, 64_000 if path != "/api/video/tasks" else h3_comfy.MAX_BODY)
            except h3_comfy.H3Error as exc:
                self._h3_request = True
                self.close_connection = True
                self._json_response(exc.status, {"ok": False, "error": str(exc)})
                return
            if path == "/api/h3/optimize":
                self._h3_call(lambda: self._json_response(200, {"ok": True, **h3_prompt_agent.optimize(video_payload)}))
                return
            if path == "/api/h3/translate":
                self._h3_call(lambda: self._json_response(200, {"ok": True, **h3_comfy.translate(video_payload)}))
                return
            if path == "/api/video/tasks" and video_payload.get("model") == h3_comfy.MODEL:
                self._h3_request = True
                self._h3_call(lambda: self._json_response(200, {"ok": True, "result": h3_comfy.submit(video_payload)}))
                return
            if path == "/api/video/tasks/status" and isinstance(video_payload.get("task_id"), str) and video_payload["task_id"].startswith("comfy_"):
                self._h3_request = True
                self._h3_call(lambda: self._json_response(200, {"ok": True, "result": h3_comfy.task_status(video_payload["task_id"])}))
                return
        if self.path == "/api/characters":
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 64_000_000:
                self._json_response(413 if length > 64_000_000 else 400, {"ok": False, "error": "角色数据为空或超过 64 MB。"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
                name = str(payload.get("name", "")).strip()
                views = payload.get("views")
                valid_views = {"front", "back", "right_front_3q", "right_back_3q", "left_front_3q", "left_back_3q"}
                if not name or len(name) > 80 or not isinstance(views, dict) or not views:
                    raise ValueError("请填写角色名称并至少上传一个方向 PNG。")
                if set(views) - valid_views:
                    raise ValueError("方向字段不在六方向清单中。")
                character_id = "char_" + uuid.uuid4().hex[:12]
                target_dir = os.path.dirname(character_manifest_path(character_id))
                os.makedirs(target_dir, exist_ok=False)
                saved_views = {}
                for view_id, data_url in views.items():
                    header, separator, encoded = str(data_url).partition(",")
                    if header != "data:image/png;base64" or not separator:
                        raise ValueError(f"{view_id} 只接受 PNG。")
                    raw = base64.b64decode(encoded, validate=True)
                    if not raw or len(raw) > 10 * 1024 * 1024:
                        raise ValueError(f"{view_id} PNG 为空或超过 10 MB。")
                    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise ValueError(f"{view_id} 文件不是有效 PNG。")
                    filename = view_id + ".png"
                    with open(os.path.join(target_dir, filename), "wb") as image_file:
                        image_file.write(raw)
                    saved_views[view_id] = filename
                manifest = {"id": character_id, "name": name, "createdAt": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"), "views": saved_views}
                with open(character_manifest_path(character_id), "w", encoding="utf-8") as manifest_file:
                    json.dump(manifest, manifest_file, ensure_ascii=False, indent=2)
                self._json_response(200, {"ok": True, "character": manifest})
            except Exception as exc:
                self._json_response(400, {"ok": False, "error": str(exc)})
            return
        if self.path == "/api/reference/upload":
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 14_000_000:
                self._json_response(413 if length > 14_000_000 else 400, {"ok": False, "error": "上传图片为空或超过 10 MB。"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
                data_url = payload.get("data_url", "")
                header, separator, encoded = data_url.partition(",")
                media_type = header.removeprefix("data:").removesuffix(";base64")
                extensions = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
                if not separator or not header.endswith(";base64") or media_type not in extensions:
                    raise ValueError("参考图只支持 PNG、JPEG 或 WebP。")
                raw = base64.b64decode(encoded, validate=True)
                if not raw or len(raw) > 10 * 1024 * 1024:
                    raise ValueError("图片为空或超过 10 MB。")
                os.makedirs(UPLOADS, exist_ok=True)
                filename = f"reference_{uuid.uuid4().hex}{extensions[media_type]}"
                with open(os.path.join(UPLOADS, filename), "wb") as image_file:
                    image_file.write(raw)
                self._json_response(200, {"ok": True, "name": filename, "message": "文件保存在本机，不会上传到公开图床。"})
            except Exception as exc:
                self._json_response(400, {"ok": False, "error": str(exc)})
            return
        if self.path == "/api/video/tasks":
            key = os.environ.get("ARK_API_KEY")
            if not key:
                self._json_response(503, {"ok": False, "error": "未设置环境变量 ARK_API_KEY；请不要将 Key 写入网页。"})
                return
            try:
                payload = video_payload
                model = payload.get("model")
                allowed = {"doubao-seedance-2-5-260628", "doubao-seedance-2-0-260128", "doubao-seedance-2-0-mini-260615", "doubao-seedance-2-0-fast-260128"}
                if model not in allowed:
                    raise ValueError("不支持的模型 ID")
                prompt = payload.get("prompt", "").strip()
                if not prompt or len(prompt) > 12000:
                    raise ValueError("提示词不能为空且不能超过 12000 字符")
                mode = payload.get("mode", "first_frame")
                if mode not in {"text", "first_frame", "first_last"}:
                    raise ValueError("不支持的生成模式")
                direction = payload.get("direction", "").strip()
                if direction and len(direction) > 500:
                    raise ValueError("动作目标不能超过 500 字符")
                if direction and not prompt.startswith("动作目标："):
                    prompt = f"动作目标：{direction}\n{prompt}"
                content = [{"type": "text", "text": prompt}]
                image_url = payload.get("image_url", "").strip()
                image_data = payload.get("image_data", "")
                last_frame_data = payload.get("last_frame_data", "")
                if mode == "text" and (image_url or image_data or last_frame_data):
                    raise ValueError("文生视频模式不能附带首帧或尾帧图片")
                if mode == "first_last" and (not image_data or not last_frame_data):
                    raise ValueError("首尾帧模式需要同时提供首帧和尾帧图片")
                if image_url and (image_data or last_frame_data):
                    raise ValueError("公网 URL 与本地首尾帧只能选择一种")
                if image_url and mode == "first_last":
                    raise ValueError("首尾帧模式请上传本地图片；公网 URL 暂只作为单张首帧使用")
                if image_url:
                    parsed = urllib.parse.urlparse(image_url)
                    if parsed.scheme != "https" or not parsed.netloc:
                        raise ValueError("参考图 URL 必须是有效的 HTTPS 公网地址")
                    content.append({"type": "image_url", "image_url": {"url": image_url}, "role": "first_frame"})
                elif image_data:
                    if not image_data.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")):
                        raise ValueError("本地参考图只支持 PNG、JPEG 或 WebP")
                    if len(image_data) > 14_000_000:
                        raise ValueError("参考图编码过大，请选择小于 10 MB 的图片")
                    content.append({"type": "image_url", "image_url": {"url": image_data}, "role": "first_frame"})
                if last_frame_data:
                    if not last_frame_data.startswith(("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")):
                        raise ValueError("尾帧只支持 PNG、JPEG 或 WebP")
                    if len(last_frame_data) > 14_000_000:
                        raise ValueError("尾帧图片编码过大，请选择小于 10 MB 的图片")
                    content.append({"type": "image_url", "image_url": {"url": last_frame_data}, "role": "last_frame"})
                resolution = payload.get("resolution", "720p")
                allowed_resolution = {"doubao-seedance-2-5-260628": {"480p", "720p", "1080p"}, "doubao-seedance-2-0-260128": {"480p", "720p", "1080p", "4k"}, "doubao-seedance-2-0-mini-260615": {"480p", "720p"}, "doubao-seedance-2-0-fast-260128": {"480p", "720p"}}
                if resolution not in allowed_resolution[model]:
                    raise ValueError(f"{model} 不支持 {resolution} 分辨率")
                ratio = payload.get("ratio", "adaptive")
                if ratio not in {"adaptive", "16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "9:21"}:
                    raise ValueError("不支持的画幅比例")
                request_body = {"model": model, "content": content, "generate_audio": False, "ratio": ratio, "resolution": resolution, "duration": int(payload.get("duration", 5)), "watermark": True}
                max_duration = 30 if model == "doubao-seedance-2-5-260628" else 15
                if request_body["duration"] < 2 or request_body["duration"] > max_duration:
                    raise ValueError(f"所选模型时长需在 2–{max_duration} 秒范围内")
                if int(payload.get("count", 1)) != 1:
                    raise ValueError("当前火山方舟视频生成接口每次创建一个任务，生成数量固定为 1")
                req = urllib.request.Request("https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks", data=json.dumps(request_body).encode("utf-8"), headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=90) as response:
                    result = json.loads(response.read())
                self._json_response(200, {"ok": True, "result": result})
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")
                self._json_response(exc.code, {"ok": False, "error": detail[:4000]})
            except Exception as exc:
                self._json_response(400, {"ok": False, "error": str(exc)})
            return
        if self.path == "/api/video/tasks/status":
            key = os.environ.get("ARK_API_KEY")
            if not key:
                self._json_response(503, {"ok": False, "error": "未设置环境变量 ARK_API_KEY。"})
                return
            try:
                payload = video_payload
                task_id = payload.get("task_id", "")
                if not task_id or len(task_id) > 256 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in task_id):
                    raise ValueError("无效任务 ID")
                req = urllib.request.Request(f"https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/{task_id}", headers={"Authorization": f"Bearer {key}"}, method="GET")
                with urllib.request.urlopen(req, timeout=60) as response:
                    result = json.loads(response.read())
                self._json_response(200, {"ok": True, "result": result})
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")
                self._json_response(exc.code, {"ok": False, "error": detail[:4000]})
            except Exception as exc:
                self._json_response(400, {"ok": False, "error": str(exc)})
            return
        if self.path == "/save-atlas":
            length = int(self.headers.get("Content-Length", "0"))
            if length > 20_000_000:
                self.send_error(413)
                return
            try:
                payload = json.loads(self.rfile.read(length))
                text = payload["text"]
                if not isinstance(text, str) or "size:" not in text:
                    raise ValueError("not an atlas")
                target = os.path.join(ROOT, "asset_v2", "character.atlas")
                with open(target, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
                body = json.dumps({"ok": True, "bytes": len(text)}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:
                body = json.dumps({"ok": False, "error": str(exc)}).encode()
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        if self.path != "/snap":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > 30_000_000:
            self.send_error(413)
            return
        try:
            payload = json.loads(self.rfile.read(length))
            name = payload["name"]
            data = payload["data"]
            if name != "snap.png" and not (name.startswith("snap_") and name.endswith(".png")):
                raise ValueError("bad name")
            if not data.startswith("data:image/png;base64,"):
                raise ValueError("png data url required")
            raw = base64.b64decode(data.split(",", 1)[1], validate=True)
            with open(os.path.join(ROOT, name), "wb") as f:
                f.write(raw)
            body = json.dumps({"ok": True, "bytes": len(raw)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

if __name__ == "__main__":
    import argparse
    import ipaddress
    parser = argparse.ArgumentParser(description="Cotton V3 unified workbench")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Loopback or an explicit private IPv4 address")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()
    address = ipaddress.ip_address(args.host)
    if not (address.is_loopback or
            (address.version == 4 and address.is_private and not address.is_unspecified)):
        parser.error("Bind only to loopback or an explicit private IPv4 address")
    server = ThreadingHTTPServer((str(address), args.port), Handler)
    server.h3_allowed_hosts = frozenset({str(address)})
    print(f"V3 unified workbench: http://{address}:{args.port}/studio_v3/", flush=True)
    server.serve_forever()
