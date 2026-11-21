// Chrome copies this function into the top document's isolated extension world.
export function pageCommand(token, command) {
  const key = Symbol.for("ai.sovra.chrome.page");
  const fail = (error) => ({error});
  if (command.action === "share") {
    if (!["http:", "https:"].includes(location.protocol)) return fail("Open an HTTP or HTTPS page.");
    globalThis[key] = {token, href: location.href, refs: new Map()};
    return {origin: location.origin};
  }
  const state = globalThis[key];
  if (!state || state.token !== token || state.href !== location.href) {
    return fail("The page changed. Share it again.");
  }
  if (command.action === "stop") {
    delete globalThis[key];
    return {};
  }
  const normalize = (text) => (text || "").trim().replace(/\s+/g, " ").slice(0, 160);
  function visible(element) {
    if (element.closest('[hidden],[inert],[aria-hidden="true"]')) return false;
    return element.checkVisibility
      ? element.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})
      : getComputedStyle(element).visibility === "visible" && element.getClientRects().length > 0;
  }
  function inView(rect) {
    return rect.width > 0 && rect.height > 0 && rect.right > 0 && rect.left < innerWidth &&
      rect.bottom > 0 && rect.top < innerHeight;
  }
  function labelText(element) {
    if (!element) return "";
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let text = "";
    for (let count = 0; count < 256 && text.length < 160; count++) {
      const node = walker.nextNode();
      if (!node) break;
      const parent = node.parentElement;
      if (parent && !parent.closest("script,style,textarea,input,select,[contenteditable]") && visible(parent)) {
        text += node.textContent.trim().slice(0, 160) + " ";
      }
    }
    return normalize(text);
  }
  function describe(element) {
    if (!element.isConnected || element.matches(':disabled,[aria-disabled="true"]') || !visible(element)) return null;
    const rect = element.getBoundingClientRect();
    if (!inView(rect)) return null;
    const x = (Math.max(0, rect.left) + Math.min(innerWidth, rect.right)) / 2;
    const y = (Math.max(0, rect.top) + Math.min(innerHeight, rect.bottom)) / 2;
    if (!element.contains(document.elementFromPoint(x, y))) return null;
    let kind;
    let destination;
    if (element instanceof HTMLAnchorElement && element.hasAttribute("href")) {
      if (!["http:", "https:"].includes(element.protocol) ||
          element.username || element.password || element.href.length > 2048) return null;
      kind = "link";
      destination = element.href;
    } else if (element instanceof HTMLButtonElement) {
      kind = "button";
    } else if (element instanceof HTMLTextAreaElement ||
               (element instanceof HTMLInputElement && ["text", "search"].includes(element.type))) {
      if (element.readOnly || /(?:password|one-time-code|cc-|transaction-)/i.test(element.autocomplete)) return null;
      kind = "field";
    } else {
      return null;
    }
    const label = normalize(element.getAttribute("aria-label") || labelText(element.labels?.[0]) ||
      (kind === "field" ? element.placeholder || element.name : labelText(element)) || element.title);
    if (!label) return null;
    return {kind, label, destination};
  }
  function viewportText() {
    const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    let text = "";
    for (let count = 0; count < 12000 && text.length < 3000; count++) {
      const node = walker.nextNode();
      if (!node) break;
      const parent = node.parentElement;
      if (!parent || !node.textContent.trim() ||
          parent.closest("script,style,noscript,template,textarea,input,select,[contenteditable]") || !visible(parent)) continue;
      range.selectNodeContents(node);
      if (inView(range.getBoundingClientRect())) text += node.textContent.trim().slice(0, 3000) + " ";
    }
    return text.trim().slice(0, 3000);
  }
  if (command.action === "snapshot") {
    state.refs.clear();
    const controls = [];
    for (const element of document.querySelectorAll("a[href],button,input,textarea")) {
      const info = describe(element);
      if (!info) continue;
      const ref = crypto.randomUUID ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint32Array(4))).join("-");
      state.refs.set(ref, {element, info});
      controls.push({ref, kind: info.kind, label: info.label});
      if (controls.length === 36) break;
    }
    return {title: document.title.slice(0, 160), origin: location.origin, text: viewportText(), controls};
  }
  if (command.action === "scroll") {
    if (!["up", "down"].includes(command.direction)) return fail("Unknown scroll direction.");
    state.refs.clear();
    const before = scrollY;
    window.scrollBy({top: (command.direction === "down" ? 1 : -1) * innerHeight * 0.85, behavior: "instant"});
    return {moved: scrollY !== before};
  }
  const saved = state.refs.get(command.ref);
  if (!saved || JSON.stringify(describe(saved.element)) !== JSON.stringify(saved.info)) {
    return fail("That control changed. Take a new snapshot.");
  }
  const {element, info} = saved;
  if (command.action === "fill") {
    if (info.kind !== "field" || typeof command.text !== "string" || command.text.length > 4000) return fail("Invalid text field request.");
  } else if (command.action !== "click" || !["button", "link"].includes(info.kind)) {
    return fail("Invalid click request.");
  }
  if (command.phase === "preview") return info;
  if (command.phase !== "apply") return fail("Review the action first.");
  state.refs.clear();
  if (command.action === "click") {
    element.click();
  } else {
    element.value = command.text;
    element.dispatchEvent(new Event("input", {bubbles: true}));
    element.dispatchEvent(new Event("change", {bubbles: true}));
  }
  return {applied: true};
}
