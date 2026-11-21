"""Local IPC shared by the MCP server and Chrome's native host."""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

ROOT = Path(__file__).resolve().parent.parent
HOST = "ai.sovra.chrome"
HEADER = struct.Struct("=I")
MAX_FRAME = 64 * 1024


def extension_id():
    manifest = json.loads((ROOT / "extension/manifest.json").read_text())
    digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
    return "".join(chr(ord("a") + int(n, 16)) for n in digest)


def socket_path():
    # A short path also fits macOS sockaddr_un. Tests can isolate whole runs.
    path = Path(os.environ.get("SOVRA_CHROME_RUNTIME_DIR", f"/tmp/sovra-chrome-{os.getuid()}"))
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError("The browser bridge needs a private, user-owned runtime directory.")
    return path / "bridge.sock"


def frame(message):
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()
    if not 0 < len(payload) <= MAX_FRAME:
        raise ValueError("Message exceeds the bridge size limit.")
    return HEADER.pack(len(payload)) + payload


async def receive(reader):
    size, = HEADER.unpack(await reader.readexactly(HEADER.size))
    if not 0 < size <= MAX_FRAME:
        raise ValueError("Invalid message size.")
    data = json.loads(await reader.readexactly(size))
    if not isinstance(data, dict):
        raise ValueError("Expected an object.")
    return data
