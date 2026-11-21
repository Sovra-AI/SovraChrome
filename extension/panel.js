import {pageCommand} from "./page.js";

const ui = Object.fromEntries([...document.querySelectorAll("[id]")].map(node => [node.id, node]));
let sharing;

async function runOnPage(session, command) {
  const target = {tabId: session.tabId};
  if (session.documentId) target.documentIds = [session.documentId];
  const [injection] = await chrome.scripting.executeScript({
    target, world: "ISOLATED", func: pageCommand, args: [session.token, command]
  });
  if (!injection?.result || injection.result.error) {
    throw new Error(injection?.result?.error || "The shared document is unavailable.");
  }
  return injection;
}

function end(session, message) {
  if (!session || sharing !== session) return;
  sharing = undefined;
  clearTimeout(session.connectTimer);
  session.pending?.finish(false);
  session.port?.disconnect();
  if (session.documentId) runOnPage(session, {action: "stop"}).catch(() => {});
  ui.review.hidden = true;
  ui.share.hidden = false;
  ui.stop.hidden = true;
  ui.origin.textContent = "";
  ui.status.textContent = message;
}

function review(session, request, control) {
  const filling = request.action === "fill";
  ui.summary.textContent = filling ? `Replace the text in “${control.label}” with the following?`
    : `Click the ${control.kind} “${control.label}”?`;
  ui.detail.textContent = filling ? request.text : control.destination || "";
  ui.review.hidden = false;
  ui.deny.focus();
  return new Promise(resolve => {
    const timer = setTimeout(() => finish(false), 45000);
    function finish(accepted) {
      clearTimeout(timer);
      session.pending = undefined;
      ui.review.hidden = true;
      ui.detail.textContent = "";
      ui.summary.textContent = "";
      resolve(accepted);
    }
    session.pending = {finish};
  });
}

async function onRequest(session, request) {
  if (sharing !== session) return;
  if (request.error && !request.id) {
    end(session, request.error);
    return;
  }
  if (request.ready === true && !session.ready) {
    session.ready = true;
    clearTimeout(session.connectTimer);
    ui.status.textContent = "Sharing with Sovra";
    return;
  }
  if (!session.ready || session.busy || typeof request.id !== "string" ||
      !["snapshot", "scroll", "click", "fill"].includes(request.action)) {
    end(session, "The bridge sent an unexpected message. Share again.");
    return;
  }
  session.busy = true;
  let reply;
  try {
    if (["click", "fill"].includes(request.action)) {
      const preview = await runOnPage(session, {...request, phase: "preview"});
      if (sharing !== session) return;
      if (!await review(session, request, preview.result)) throw new Error("The action was declined or its review expired.");
    }
    if (sharing !== session) return;
    const {result} = await runOnPage(session, {...request, phase: "apply"});
    reply = {id: request.id, result};
  } catch (error) {
    reply = {id: request.id, error: error.message};
  } finally {
    session.busy = false;
  }
  if (sharing === session) session.port.postMessage(reply);
}

async function share() {
  if (sharing) return;
  const session = {token: crypto.randomUUID()};
  sharing = session;
  ui.share.hidden = true;
  ui.stop.hidden = false;
  ui.status.textContent = "Connecting…";
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    if (sharing !== session) return;
    if (!tab || !/^https?:\/\//.test(tab.url || "")) {
      throw new Error("Open a web page and click the Sovra toolbar icon on that tab.");
    }
    session.tabId = tab.id;
    session.windowId = tab.windowId;
    const injection = await runOnPage(session, {action: "share"});
    if (sharing !== session) return;
    session.documentId = injection.documentId;
    ui.origin.textContent = injection.result.origin;
    session.port = chrome.runtime.connectNative("ai.sovra.chrome");
    session.port.onDisconnect.addListener(() => {
      const error = chrome.runtime.lastError;
      end(session, error ? "Could not reach the native host. Check the installation and Harness connection." : "Sharing ended.");
    });
    session.port.onMessage.addListener(request => onRequest(session, request));
    session.connectTimer = setTimeout(() => end(session, "Connection timed out. Start the bridge in Harness."), 5000);
  } catch (error) {
    end(session, error.message);
  }
}

ui.share.addEventListener("click", share);
ui.stop.addEventListener("click", () => end(sharing, "Sharing stopped."));
ui.allow.addEventListener("click", () => sharing?.pending?.finish(true));
ui.deny.addEventListener("click", () => sharing?.pending?.finish(false));
chrome.tabs.onActivated.addListener(({tabId, windowId}) => {
  if (sharing?.windowId === windowId && sharing.tabId !== tabId) end(sharing, "Tab changed. Sharing stopped.");
});
chrome.tabs.onRemoved.addListener(tabId => {
  if (sharing?.tabId === tabId) end(sharing, "Tab closed. Sharing stopped.");
});
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (sharing?.tabId === tabId && (change.status === "loading" || change.url)) {
    end(sharing, "Page changed. Share the new page to continue.");
  }
});
window.addEventListener("pagehide", () => end(sharing, "Sharing stopped."));
