#!/usr/bin/env python3
"""AI桌面精灵 · 主控服务器 — WebSocket 服务，连接 Unity 前端与 AI 后端。"""

import asyncio
import json
import os
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote
from typing import Optional
import urllib.request
import urllib.error
import glob
import mimetypes

# 切到 backend 目录以正确加载 config.json
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from llm_engine import LLMEngine
from emotion_engine import EmotionEngine
from personality import Personality
from memory import MemoryStore
from automation import AutomationEngine


class PetServer:
    """WebSocket 服务器，处理 Unity 前端的所有请求。"""

    def __init__(self, config_path: str = "config.json") -> None:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        srv_cfg = cfg["server"]
        self.host: str = srv_cfg["host"]
        self.port: int = srv_cfg["port"]

        self.llm = LLMEngine(config_path)
        self.emotion = EmotionEngine(config_path)
        self.personality = Personality(config_path)
        self.memory = MemoryStore(config_path)
        self.automation = AutomationEngine(config_path)

        self._start_time: float = time.time()
        self._active: bool = True
        # 确保 music/voice 目录存在
        _preview = os.path.join(os.path.dirname(__file__), "..", "preview")
        os.makedirs(os.path.join(_preview, "music"), exist_ok=True)
        os.makedirs(os.path.join(_preview, "voice"), exist_ok=True)

    # ─── 消息处理主循环 ───

    async def handle_message(self, raw: str) -> str:
        """处理一条 JSON 消息，返回 JSON 响应字符串"""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return json.dumps({"type": "error", "message": "无效的 JSON"})

        msg_type = msg.get("type", "")

        if msg_type == "user_input":
            return await self._handle_user_input(msg)
        elif msg_type == "ping":
            return json.dumps({"type": "pong", "uptime": time.time() - self._start_time})
        elif msg_type == "get_status":
            return self._get_status()
        elif msg_type == "reset_emotion":
            self.emotion.reset_to_neutral()
            return json.dumps({"type": "status", "message": "情绪已重置"})
        elif msg_type == "music_list":
            return self._handle_music_list()
        elif msg_type == "music_download":
            return await self._handle_music_download(msg)
        elif msg_type == "voice_chat":
            return await self._handle_voice_chat(msg)
        elif msg_type == "music_songlist":
            return self._handle_music_songlist()
        elif msg_type == "music_download_batch":
            return await self._handle_music_download_batch()
        else:
            return json.dumps({"type": "error", "message": f"未知消息类型: {msg_type}"})

    # ─── 核心处理逻辑 ───

    async def _handle_user_input(self, msg: dict) -> str:
        """处理用户输入：情绪检测 → 意图解析 → LLM 回复 → 自动化执行"""
        content = msg.get("content", "")
        context = msg.get("context", {})

        # 1. 情绪检测
        self.emotion.tick()
        triggered = self.emotion.detect_from_text(content)

        # 2. 自动化意图解析
        auto_intent = self.automation.parse_intent_from_text(content)
        auto_result = None
        if auto_intent and not self.automation.require_confirmation:
            auto_result = self.automation.execute(
                auto_intent["action_type"],
                auto_intent["target"],
                auto_intent.get("params", {})
            )

        # 3. LLM 生成回复
        history = self.memory.get_recent_history()
        long_term_ctx = self.memory.get_long_term_context()
        personality_hint = self.personality.build_personality_hint()

        # 组合完整提示词
        enhanced_content = content
        if auto_intent:
            enhanced_content = f"{content}\n[系统: 用户想要执行 {auto_intent['action_type']} 操作]"
        if long_term_ctx:
            enhanced_content = f"{long_term_ctx}\n---\n{enhanced_content}"

        reply = self.llm.chat(
            user_message=enhanced_content,
            history=history,
            emotion=self.emotion.dominant_emotion,
            personality_hint=personality_hint
        )

        # 安全过滤：确保回复不超出角色设定
        reply = self._sanitize_reply(reply)

        # 4. 记录到记忆
        self.memory.add_message("user", content)
        self.memory.add_message("assistant", reply)

        # 5. 构建响应
        # 获取最近关键记忆
        recent_memories = []
        try:
            lt = self.memory.get_long_term_context()
            if lt:
                # 提取记忆摘要（每行一条）
                recent_memories = [m.strip() for m in lt.split("\n") if m.strip() and not m.strip().startswith("---")][:10]
        except Exception:
            pass

        response = {
            "type": "pet_response",
            "text": reply,
            "emotion": self.emotion.dominant_emotion,
            "emotion_values": self.emotion.emotion_values,
            "animation": self.emotion.get_animation_hint(),
            "triggered_emotion": triggered,
            "memories": recent_memories,
        }

        if auto_intent:
            response["pending_action"] = auto_intent
        if auto_result:
            response["action_result"] = auto_result

        return json.dumps(response, ensure_ascii=False)

    def _sanitize_reply(self, text: str) -> str:
        """安全过滤：截断过长回复，移除可能的注入风险"""
        # 限制回复长度
        max_len = 200
        if len(text) > max_len:
            text = text[:max_len] + "..."
        # 移除可能的代码注入标记
        text = text.replace("```", "").replace("<script>", "").replace("</script>", "")
        return text

    def _get_status(self) -> str:
        """返回宠物当前状态"""
        return json.dumps({
            "type": "status",
            "emotion": self.emotion.dominant_emotion,
            "emotion_values": self.emotion.emotion_values,
            "animation": self.emotion.get_animation_hint(),
            "uptime": time.time() - self._start_time,
            "memory_count": len(self.memory.get_recent_history()),
            "automation_enabled": self.automation.enabled
        }, ensure_ascii=False)


    # ─── 音乐管理 ───

    def _handle_music_list(self) -> str:
        """列出 music 目录下的所有音频文件"""
        music_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "preview", "music")
        os.makedirs(music_dir, exist_ok=True)
        files = []
        for f in sorted(os.listdir(music_dir)):
            if f.endswith(('.mp3', '.wav', '.ogg', '.flac', '.m4a')):
                fpath = os.path.join(music_dir, f)
                fsize = os.path.getsize(fpath)
                files.append({"name": f, "size": fsize, "path": f"music/{f}"})
        return json.dumps({"type": "music_list", "files": files}, ensure_ascii=False)

    async def _handle_music_download(self, msg: dict) -> str:
        """下载歌曲：支持直接URL或 ytsearch:N:关键词 格式"""
        url = msg.get("url", "").strip()
        if not url:
            return json.dumps({"type": "error", "message": "缺少歌曲URL"})
        music_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "preview", "music")
        os.makedirs(music_dir, exist_ok=True)

        # YouTube 搜索下载
        if url.startswith("ytsearch"):
            return await self._youtube_download(url, music_dir)

        # 直接 URL 下载
        fname = url.rsplit("/", 1)[-1].split("?")[0]
        if not fname.endswith((".mp3", ".wav", ".ogg")):
            fname += ".mp3"
        fpath = os.path.join(music_dir, fname)
        if os.path.exists(fpath):
            return json.dumps({"type": "music_downloaded", "name": fname, "path": f"music/{fname}", "cached": True})
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LingHui/2.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
                with open(fpath, "wb") as f:
                    f.write(data)
            return json.dumps({"type": "music_downloaded", "name": fname, "path": f"music/{fname}", "size": len(data)})
        except urllib.error.URLError as e:
            return json.dumps({"type": "error", "message": f"下载失败: {e.reason}"})
        except Exception as e:
            return json.dumps({"type": "error", "message": f"下载异常: {e}"})

    async def _youtube_download(self, query: str, music_dir: str) -> str:
        """使用 yt-dlp 从 YouTube 搜索并下载音频"""
        import subprocess, glob
        try:
            # yt-dlp 搜索+下载最佳音频，转 MP3
            tmpl = os.path.join(music_dir, "%(title).100s.%(ext)s")
            # 先清理旧临时文件
            for old in glob.glob(os.path.join(music_dir, "*.part")):
                try: os.remove(old)
                except: pass
            result = subprocess.run([
                "yt-dlp", "--no-playlist", "--extract-audio", "--audio-format", "mp3",
                "--audio-quality", "0", "--max-filesize", "15m",
                "--output", tmpl, query
            ], capture_output=True, text=True, timeout=120, cwd=music_dir)
            # 查找下载的文件
            mp3s = sorted(glob.glob(os.path.join(music_dir, "*.mp3")), key=os.path.getmtime, reverse=True)
            if mp3s:
                fname = os.path.basename(mp3s[0])
                fsize = os.path.getsize(mp3s[0])
                return json.dumps({"type": "music_downloaded", "name": fname, "path": f"music/{fname}", "size": fsize})
            return json.dumps({"type": "error", "message": "未找到匹配歌曲"})
        except subprocess.TimeoutExpired:
            return json.dumps({"type": "error", "message": "下载超时，请重试"})
        except FileNotFoundError:
            return json.dumps({"type": "error", "message": "yt-dlp 未安装"})
        except Exception as e:
            return json.dumps({"type": "error", "message": f"下载失败: {str(e)[:40]}"})

    async def _handle_voice_chat(self, msg: dict) -> str:
        """处理语音转文字后的对话请求，复用 user_input 逻辑"""
        msg["type"] = "user_input"
        return await self._handle_user_input(msg)

    def _handle_music_songlist(self) -> str:
        """返回预置歌单列表（供前端一键下载）"""
        songs = _load_free_songs()
        result = [{"title": s["title"], "desc": s.get("desc", ""), "mood": s.get("mood", ""), "url": s["url"]} for s in songs]
        return json.dumps({"type": "music_songlist", "songs": result}, ensure_ascii=False)

    async def _handle_music_download_batch(self) -> str:
        """批量下载预置歌单"""
        songs = _load_free_songs()
        if not songs:
            return json.dumps({"type": "error", "message": "歌单为空"})
        import importlib.util
        voice_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "linghui_voice.py")
        spec = importlib.util.spec_from_file_location("linghui_voice", voice_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        download_song = getattr(mod, "download_song", None)
        music_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "preview", "music")
        os.makedirs(music_dir, exist_ok=True)
        ok = 0
        for song in songs:
            if download_song and download_song(song, str(music_dir)):
                ok += 1
        return self._handle_music_list()

# ─── 歌单加载辅助函数 ───

def _load_free_songs() -> list:
    """加载 CC0 免费歌单"""
    try:
        import importlib.util
        voice_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "linghui_voice.py")
        spec = importlib.util.spec_from_file_location("linghui_voice", voice_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "FREE_SONGS", [])
    except Exception:
        return []


# ─── 简易 WebSocket 服务（纯 Python 标准库实现）───

class SimpleWSServer:
    """极简 WebSocket 服务器，无外部依赖。使用原始 TCP + HTTP 升级握手。"""

    def __init__(self, pet_server: PetServer) -> None:
        self.pet = pet_server

    async def start(self) -> None:
        """启动 TCP 服务器"""
        server = await asyncio.start_server(
            self._handle_client,
            self.pet.host,
            self.pet.port
        )
        addr = server.sockets[0].getsockname()
        print(f"🐾 AI桌面精灵 WebSocket 服务已启动: ws://{addr[0]}:{addr[1]}")
        print(f"   情绪引擎: 就绪 | LLM: {self.pet.llm.model} | 自动化: {'启用' if self.pet.automation.enabled else '未启用'}")
        print(f"   性格: {self.pet.personality.profile['label']}")

        # 同时启动 HTTP 静态文件服务（托管前端页面 + 文件上传）
        preview_dir = os.path.join(os.path.dirname(__file__), "..", "preview")
        os.chdir(preview_dir)
        SimpleHTTPRequestHandler.extensions_map[".glb"] = "model/gltf-binary"
        SimpleHTTPRequestHandler.extensions_map[".gltf"] = "model/gltf+json"

        # 自定义 handler：静态文件 + POST /music/upload
        pet_ref = self.pet
        class UploadHandler(SimpleHTTPRequestHandler):
            def do_POST(self):
                if self.path == "/music/upload":
                    try:
                        length = int(self.headers.get("Content-Length", 0))
                        data = self.rfile.read(length)
                        fname = unquote(self.headers.get("X-Filename", "upload.mp3"))
                        music_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "preview", "music")
                        os.makedirs(music_dir, exist_ok=True)
                        fpath = os.path.join(music_dir, os.path.basename(fname))
                        with open(fpath, "wb") as f:
                            f.write(data)
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b'{"ok":true,"name":"' + fname.encode() + b'"}')
                    except Exception as e:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(b'{"error":"' + str(e).encode() + b'"}')
                else:
                    self.send_response(404)
                    self.end_headers()

        httpd = HTTPServer(('0.0.0.0', 8080), UploadHandler)
        print(f"   🌐 前端页面: http://0.0.0.0:8080")
        http_server_task = asyncio.get_event_loop().run_in_executor(None, httpd.serve_forever)
        print("   等待连接...\n")

        async with server:
            await server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader,
                             writer: asyncio.StreamWriter) -> None:
        """处理单个 WebSocket 客户端连接"""
        addr = writer.get_extra_info('peername')
        print(f"  ✓ 新连接: {addr}")

        try:
            # 读取 HTTP 升级请求
            request = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), timeout=10)
            request_text = request.decode('utf-8', errors='replace')

            # 提取 WebSocket key
            ws_key = None
            for line in request_text.split('\r\n'):
                if line.lower().startswith('sec-websocket-key:'):
                    ws_key = line.split(':', 1)[1].strip()
                    break

            if not ws_key:
                writer.close()
                return

            # WebSocket 握手响应
            import hashlib
            import base64
            magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            accept = base64.b64encode(
                hashlib.sha1((ws_key + magic).encode()).digest()
            ).decode()

            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n"
                "\r\n"
            )
            writer.write(response.encode())
            await writer.drain()

            # 进入消息循环
            await self._message_loop(reader, writer)

        except (asyncio.TimeoutError, ConnectionError) as e:
            print(f"  ✗ 连接异常 ({addr}): {e}")
        finally:
            print(f"  ✗ 连接断开: {addr}")
            try:
                writer.close()
            except Exception:
                pass

    async def _message_loop(self, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter) -> None:
        """WebSocket 消息循环"""
        buffer = bytearray()

        while True:
            try:
                data = await asyncio.wait_for(reader.read(4096), timeout=300)
            except asyncio.TimeoutError:
                # 发送 ping
                ping_frame = self._make_frame(b'', opcode=0x9)
                writer.write(ping_frame)
                await writer.drain()
                continue

            if not data:
                break

            buffer.extend(data)

            # 尝试解析帧
            while len(buffer) >= 2:
                frame_info = self._parse_frame(buffer)
                if frame_info is None:
                    break

                fin, opcode, payload = frame_info[:3]
                buffer = buffer[frame_info[3]:]  # frame_info[3] 是帧总长度

                if opcode == 0x8:  # 关闭帧
                    close_frame = self._make_frame(b'', opcode=0x8)
                    writer.write(close_frame)
                    await writer.drain()
                    return
                elif opcode == 0x9:  # ping
                    pong = self._make_frame(payload, opcode=0xA)
                    writer.write(pong)
                    await writer.drain()
                elif opcode == 0x1:  # 文本帧
                    msg_text = payload.decode('utf-8', errors='replace')
                    response_text = await self.pet.handle_message(msg_text)
                    response_frame = self._make_frame(
                        response_text.encode('utf-8'), opcode=0x1
                    )
                    writer.write(response_frame)
                    await writer.drain()

    def _parse_frame(self, data: bytearray) -> Optional[tuple]:
        """解析 WebSocket 帧，返回 (fin, opcode, payload, total_length) 或 None"""
        if len(data) < 2:
            return None

        byte1 = data[0]
        byte2 = data[1]
        fin = (byte1 >> 7) & 1
        opcode = byte1 & 0x0F
        masked = (byte2 >> 7) & 1
        payload_len = byte2 & 0x7F

        offset = 2
        if payload_len == 126:
            if len(data) < 4:
                return None
            payload_len = int.from_bytes(data[2:4], 'big')
            offset = 4
        elif payload_len == 127:
            if len(data) < 10:
                return None
            payload_len = int.from_bytes(data[2:10], 'big')
            offset = 10

        mask_bytes = b''
        if masked:
            if len(data) < offset + 4:
                return None
            mask_bytes = data[offset:offset + 4]
            offset += 4

        total_len = offset + payload_len
        if len(data) < total_len:
            return None

        payload = bytes(data[offset:offset + payload_len])
        if masked:
            payload = bytes(b ^ mask_bytes[i % 4] for i, b in enumerate(payload))

        return (fin, opcode, payload, total_len)

    def _make_frame(self, payload: bytes, opcode: int = 0x1) -> bytes:
        """构建 WebSocket 帧"""
        frame = bytearray()
        frame.append(0x80 | opcode)  # FIN + opcode

        length = len(payload)
        if length < 126:
            frame.append(length)
        elif length < 65536:
            frame.append(126)
            frame.extend(length.to_bytes(2, 'big'))
        else:
            frame.append(127)
            frame.extend(length.to_bytes(8, 'big'))

        frame.extend(payload)
        return bytes(frame)


# ─── 入口 ───

def main() -> None:
    """启动 AI 桌面精灵服务"""
    print("╔══════════════════════════════════════════╗")
    print("║     🐾 AI 虚拟桌面精灵 · 后端服务       ║")
    print("║     Unity 3D + LLM + 手机自动化         ║")
    print("╚══════════════════════════════════════════╝")
    print()

    pet = PetServer()
    ws_server = SimpleWSServer(pet)

    try:
        asyncio.run(ws_server.start())
    except KeyboardInterrupt:
        print("\n🐾 桌面精灵已休眠，再见~")
        sys.exit(0)


if __name__ == "__main__":
    main()
