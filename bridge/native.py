"""Relay Chrome's length-prefixed stream onto the user's private Unix socket."""
import os
import selectors
import socket
import sys

from local import extension_id, frame, socket_path


def main():
    if sys.argv[1:2] != [f"chrome-extension://{extension_id()}/"]:
        return 1
    with socket.socket(socket.AF_UNIX) as peer, selectors.DefaultSelector() as events:
        try:
            peer.connect(str(socket_path()))
        except OSError:
            sys.stdout.buffer.write(frame({"error": "Start Sovra Chrome in Harness Connections, then share again."}))
            sys.stdout.buffer.flush()
            return 1
        events.register(sys.stdin, selectors.EVENT_READ)
        events.register(peer, selectors.EVENT_READ)
        while True:
            for key, _ in events.select():
                data = os.read(key.fd, 65536)
                if not data:
                    return 0
                if key.fileobj is peer:
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                else:
                    peer.sendall(data)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BrokenPipeError, ConnectionResetError):
        sys.exit(0)
