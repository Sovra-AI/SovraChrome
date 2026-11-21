# Sovra for Chrome

Let Sovra Harness work with the Chrome page you choose. It can read a snapshot, scroll, click a visible link or button, and fill an ordinary text field. Clicks and text entries appear in Chrome's side panel for your approval.

## Install from source

Use desktop Chrome 116 or newer on Linux or macOS, Sovra Harness with **Connections → MCP servers**, Git and [uv](https://docs.astral.sh/uv/getting-started/installation/). The bridge uses a local Unix socket. Linux has an end-to-end browser test. Windows packaging is a future milestone.

1. Clone the project into a directory you intend to keep. Install the Python environment and register the companion for your Chrome installation.

   ```sh
   git clone https://github.com/Sovra-AI/SovraChrome.git
   cd SovraChrome
   uv sync --frozen --no-dev
   .venv/bin/python bridge/install.py
   ```

   For Chromium, add `--browser chromium` to the installer command. The installer prints a JSON settings object with the exact local paths.

2. In Sovra, open **Connections → Add MCP server → Paste settings** and paste that JSON. Choose **Run it** after reviewing the program. The connection should list four tools.

3. Visit `chrome://extensions`, turn on **Developer mode**, choose **Load unpacked**, and select the cloned **extension** folder.

4. Open an ordinary web page, click **Sovra for Chrome** in the extensions menu or toolbar, then choose **Share this page**. The panel shows the shared origin when connected.

5. Try asking Sovra, *“What can I do on this page?”* On a page with a labeled search field, try *“Enter botany in the search field.”* The panel shows the proposed value. **Allow once** applies it and **Decline** leaves the field alone.

## Browser tools

| MCP tool | Behavior |
| --- | --- |
| `page_snapshot()` | Returns the title, origin, a bounded excerpt from text blocks intersecting the viewport, and up to 36 visible, labeled controls. |
| `page_scroll(direction)` | Scrolls the page up or down by 85% of the viewport. |
| `page_click(ref)` | Requests one click on a link or button. The panel shows link destinations. |
| `page_fill(ref, text)` | Requests replacement of a text input, search input or textarea with up to 2,000 characters. |

References belong to the latest snapshot. After a scroll or accepted edit, take another snapshot. The starter supports the top document's ordinary HTML controls. Embedded frames, shadow-root controls, file inputs and password inputs are outside its current coverage. Sites that require trusted keyboard or pointer events may ignore DOM events.

## Sharing and privacy

Only one page can be shared at a time. **Stop sharing**, closing the panel, changing tabs within its window, or navigating ends the session. After an approved link opens a new document, share the destination to continue. If the connection drops during an action, inspect the page before retrying.

Snapshots go to the local Harness process. Your Harness settings determine which model receives the result and how chat history is stored. A visible page can contain sensitive information. The bridge keeps its live connection and control references in memory. It has no telemetry or browsing-history store.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| The panel asks you to click the toolbar icon | Open the extension from the toolbar on the desired HTTP(S) tab. Chrome restricts privileged pages and the Chrome Web Store. |
| Chrome cannot reach the host | Rerun the installer with the Python interpreter in the project environment and the browser product you actually use. Reload the unpacked extension after editing its manifest. |
| Chrome asks you to start the connection | Check for **Connected** and four tools in Sovra. After moving the checkout, rerun the installer and import the new program paths. |
| Another page or server is connected | Stop sharing in the other panel or pause the duplicate MCP connection. Start one connection for the OS account. |

To remove the integration, remove its connection in Sovra and its extension in Chrome. Delete `ai.sovra.chrome.json` and `ai.sovra.chrome-host` from the browser's per-user `NativeMessagingHosts` directory. [Chrome host locations](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging#native-messaging-host-location)

## Development

Edit the files in `extension/` and reload the extension at `chrome://extensions`. Restart its connection in Sovra after changing `bridge/`. The research note explains the transport choice, permission model, session lifetime and distribution tradeoffs. [Design and research](docs/research.md)

Run the integration tests from the checkout. The browser test uses a temporary profile and per-test native host registration on Linux.

```sh
uv sync --frozen
.venv/bin/python -m unittest discover -s tests
.venv/bin/playwright install chromium
xvfb-run -a .venv/bin/python tests/browser.py
```

Licensed under the [MIT License](LICENSE).
