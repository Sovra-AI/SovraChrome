"""Exercise the actual toolbar action, side panel, native host and stdio MCP connection in Linux Chrome for Testing."""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
TOOLS = {"page_snapshot", "page_click", "page_fill", "page_scroll"}
FIXTURE = """
<!doctype html><title>Library search</title>
<label>Search titles <input type="search" value="private-draft"></label>
<label>Notes <textarea>private-note</textarea></label>
<a href="/next">Open reading list</a><a href="http://[">Malformed address</a>
<input aria-label="Password" type="password" value="secret-value">
<button onclick="this.dataset.done='yes'">Apply filter</button>
<p>Reading room</p><p hidden>hidden-sentinel</p><div style="height:160vh"></div><p>Lower shelf</p>
"""


@asynccontextmanager
async def mcp_tools(settings, env):
    process = settings["mcpServers"]["Sovra Chrome"]
    server = StdioServerParameters(**process, env=env)
    async with stdio_client(server) as streams, ClientSession(*streams) as session:
        await session.initialize()
        assert {tool.name for tool in (await session.list_tools()).tools} == TOOLS

        async def call(tool, **args):
            result = await session.call_tool(tool, args)
            return {"error": result.content[0].text} if result.isError else json.loads(result.content[0].text)

        yield call


class Panel:
    """Drive the side panel target that Chrome owns outside Playwright's tab list."""

    def __init__(self, cdp, session):
        self.cdp = cdp
        self.session = session
        self.calls = {}
        self.sequence = 0
        cdp.on("Target.receivedMessageFromTarget", self.received)

    def received(self, event):
        if event["sessionId"] == self.session:
            reply = json.loads(event["message"])
            if reply.get("id") in self.calls:
                self.calls.pop(reply["id"]).set_result(reply)

    async def evaluate(self, expression):
        self.sequence += 1
        seq = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.calls[seq] = future
        await self.cdp.send("Target.sendMessageToTarget", {"sessionId": self.session, "message": json.dumps({
            "id": seq, "method": "Runtime.evaluate", "params": {"expression": expression, "returnByValue": True}
        })})
        reply = await asyncio.wait_for(future, 5)
        assert "error" not in reply and "exceptionDetails" not in reply["result"], reply
        return reply["result"]["result"].get("value")

    async def click(self, element):
        await self.evaluate(f"document.getElementById('{element}').click()")

    async def wait(self, expression):
        async with asyncio.timeout(8):
            while not await self.evaluate(expression):
                await asyncio.sleep(0.05)


async def open_panel(ctx, page):
    worker = ctx.service_workers[0] if ctx.service_workers else await ctx.wait_for_event("serviceworker")
    cdp = await ctx.browser.new_browser_cdp_session()
    tabs = await cdp.send("Target.getTargets", {"filter": [{"type": "tab"}]})
    tab = next(item for item in tabs["targetInfos"] if item["url"] == page.url)
    extension_id = worker.url.split("/")[2]
    await cdp.send("Extensions.triggerAction", {"id": extension_id, "targetId": tab["targetId"]})
    panel_url = f"chrome-extension://{extension_id}/panel.html"
    async with asyncio.timeout(8):
        while True:
            targets = (await cdp.send("Target.getTargets"))["targetInfos"]
            panel = next((item for item in targets if item["url"] == panel_url), None)
            if panel:
                break
            await asyncio.sleep(0.05)
    session = await cdp.send("Target.attachToTarget", {"targetId": panel["targetId"]})
    driver = Panel(cdp, session["sessionId"])
    await driver.wait("document.readyState === 'complete'")
    return driver


async def exercise(ctx, call):
    page = ctx.pages[0]
    await page.route("https://library.test/**", lambda route: route.fulfill(content_type="text/html", body=FIXTURE))
    await page.goto("https://library.test/")
    assert "Share" in (await call("page_snapshot"))["error"]
    panel = await open_panel(ctx, page)
    await panel.click("share")
    try:
        await panel.wait("document.getElementById('status').textContent === 'Sharing with Sovra'")
    except TimeoutError:
        raise AssertionError(await panel.evaluate("document.getElementById('status').textContent")) from None
    state = await call("page_snapshot")
    assert state["title"] == "Library search" and "Reading room" in state["text"], state
    for private in ["secret-value", "private-draft", "private-note", "hidden-sentinel", "Password"]:
        assert private not in json.dumps(state)
    assert all(control["label"] != "Malformed address" for control in state["controls"])
    refs = {control["label"]: control["ref"] for control in state["controls"]}
    button = page.get_by_role("button", name="Apply filter")
    field = page.get_by_role("searchbox")

    async def reviewed(tool, choice, **args):
        task = asyncio.create_task(call(tool, **args))
        await panel.wait("!document.getElementById('review').hidden")
        if tool == "page_fill":
            assert await panel.evaluate("document.getElementById('detail').textContent") == args["text"]
        await panel.click(choice)
        return await task

    assert "error" in await reviewed("page_click", "deny", ref=refs["Apply filter"])
    assert await button.get_attribute("data-done") is None
    assert (await reviewed("page_fill", "allow", ref=refs["Search titles"], text="Botany"))["applied"]
    assert await field.input_value() == "Botany"
    assert "error" in await call("page_click", ref=refs["Apply filter"])  # prior snapshot
    state = await call("page_snapshot")
    ref = next(item["ref"] for item in state["controls"] if item["kind"] == "button")
    assert (await reviewed("page_click", "allow", ref=ref))["applied"]
    assert await button.get_attribute("data-done") == "yes"
    assert (await call("page_scroll", direction="down"))["moved"]
    assert await page.evaluate("scrollY") > 0
    await panel.click("stop")
    await panel.wait("!document.getElementById('share').hidden")
    assert "error" in await call("page_snapshot")
    await panel.click("share")
    await panel.wait("document.getElementById('status').textContent === 'Sharing with Sovra'")
    await call("page_scroll", direction="up")
    state = await call("page_snapshot")
    link = next(item for item in state["controls"] if item["kind"] == "link")
    task = asyncio.create_task(call("page_click", ref=link["ref"]))
    await panel.wait("!document.getElementById('review').hidden")
    assert await panel.evaluate("document.getElementById('detail').textContent") == "https://library.test/next"
    await page.get_by_role("link", name="Open reading list").evaluate("(link) => link.href = '/changed'")
    await panel.click("allow")
    assert "error" in await task
    assert page.url == "https://library.test/"
    state = await call("page_snapshot")
    ref = next(item["ref"] for item in state["controls"] if item["kind"] == "link")
    await reviewed("page_click", "allow", ref=ref)
    await page.wait_for_url("https://library.test/changed")
    await panel.wait("!document.getElementById('share').hidden")
    assert "error" in await call("page_snapshot")
    await panel.click("share")
    await panel.wait("document.getElementById('status').textContent === 'Sharing with Sovra'")
    state = await call("page_snapshot")
    ref = next(item["ref"] for item in state["controls"] if item["kind"] == "button")
    pending = asyncio.create_task(call("page_click", ref=ref))
    await panel.wait("!document.getElementById('review').hidden")
    other = await ctx.new_page()
    await other.bring_to_front()
    await panel.wait("!document.getElementById('share').hidden")
    assert "error" in await pending
    assert await button.get_attribute("data-done") is None
    await other.close()
    await panel.click("share")
    await panel.wait("document.getElementById('status').textContent === 'Sharing with Sovra'")
    await ctx.service_workers[0].evaluate("chrome.windows.getLastFocused().then(w => chrome.sidePanel.close({windowId:w.id}))")
    async with asyncio.timeout(5):
        while "error" not in await call("page_snapshot"):
            await asyncio.sleep(0.05)


async def run(directory, client=mcp_tools):
    config = directory / "config"
    profile = config / "google-chrome-for-testing"
    env = {**os.environ, "XDG_CONFIG_HOME": str(config), "SOVRA_CHROME_RUNTIME_DIR": str(directory / "run")}
    settings = json.loads(subprocess.check_output(
        [sys.executable, ROOT / "bridge/install.py", "--browser-config-dir", profile], env=env))
    async with client(settings, env) as call, async_playwright() as playwright:
        extension = ROOT / "extension"
        ctx = await playwright.chromium.launch_persistent_context(
            profile, channel="chromium", headless=False, env=env,
            args=["--enable-unsafe-extension-debugging", f"--disable-extensions-except={extension}", f"--load-extension={extension}"])
        try:
            await exercise(ctx, call)
        finally:
            await ctx.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as temp:
        asyncio.run(run(Path(temp)))
    print("Passed: discovery, sharing, snapshot, review, click, fill, scroll, stop and navigation.")
