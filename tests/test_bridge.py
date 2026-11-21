"""Check Native Messaging registration, socket ownership and request cleanup."""
import asyncio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from local import HEADER, HOST, MAX_FRAME, ROOT, extension_id, frame, receive, socket_path
from server import Browser


class RegistrationTest(unittest.TestCase):
    def test_launcher_and_chrome_allowlist(self):
        with tempfile.TemporaryDirectory(prefix="sovra chrome ") as temp:
            product = Path(temp) / "browser"
            env = {**os.environ, "SOVRA_CHROME_RUNTIME_DIR": str(Path(temp) / "run")}
            output = subprocess.check_output([
                sys.executable, ROOT / "bridge/install.py", "--browser-config-dir", product
            ], env=env)
            settings = json.loads(output)["mcpServers"]["Sovra Chrome"]
            self.assertEqual(settings, {"command": sys.executable, "args": [str(ROOT / "bridge/server.py")]})
            manifest = json.loads((product / "NativeMessagingHosts" / f"{HOST}.json").read_text())
            origin = f"chrome-extension://{extension_id()}/"
            self.assertEqual(manifest["allowed_origins"], [origin])
            foreign = subprocess.run([manifest["path"], "chrome-extension://wrong/"], capture_output=True, env=env)
            self.assertNotEqual(foreign.returncode, 0)
            self.assertEqual(foreign.stdout, b"")
            no_server = subprocess.run([manifest["path"], origin], capture_output=True, env=env)
            size, = HEADER.unpack(no_server.stdout[:4])
            self.assertEqual(size, len(no_server.stdout) - 4)
            self.assertIn("Harness Connections", json.loads(no_server.stdout[4:])["error"])

    def test_runtime_directory_rejects_public_and_symlink_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "private"
            with patch.dict(os.environ, SOVRA_CHROME_RUNTIME_DIR=str(target)):
                self.assertEqual(socket_path().parent.stat().st_mode & 0o777, 0o700)
                target.chmod(0o755)
                with self.assertRaises(PermissionError):
                    socket_path()
                target.chmod(0o700)
            link = Path(temp) / "link"
            link.symlink_to(target, target_is_directory=True)
            with patch.dict(os.environ, SOVRA_CHROME_RUNTIME_DIR=str(link)):
                with self.assertRaises(PermissionError):
                    socket_path()


class ProtocolTest(unittest.IsolatedAsyncioTestCase):
    async def test_oversized_frame_rejected_before_payload_read(self):
        reader = asyncio.StreamReader()
        reader.feed_data(HEADER.pack(MAX_FRAME + 1))
        with self.assertRaises(ValueError):
            await receive(reader)

    async def test_pending_call_ends_with_its_peer(self):
        browser = Browser()
        left, right = socket.socketpair()
        reader, writer = await asyncio.open_connection(sock=left)
        client, peer = await asyncio.open_connection(sock=right)
        attached = asyncio.create_task(browser.attach(reader, writer))
        self.assertEqual(await receive(client), {"ready": True})
        pending = asyncio.create_task(browser.call("scroll", direction="up"))
        request = await receive(client)
        self.assertEqual(request["action"], "scroll")
        with self.assertRaisesRegex(ValueError, "already in progress"):
            await browser.call("snapshot")
        peer.write(frame({"id": "wrong-id", "result": {}}))
        await peer.drain()
        with self.assertRaisesRegex(ValueError, "Sharing ended"):
            await pending
        await attached
        with self.assertRaisesRegex(ValueError, "Share this page"):
            await browser.call("snapshot")
        peer.close()
        await peer.wait_closed()
