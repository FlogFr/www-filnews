/**
 * Sender.net forms (newsletter and contact pages only).
 *
 * Sender's official snippet is an inline <script>, which the CSP forbids: it
 * is reproduced here as an external module. Sender's script then renders
 * every `.sender-form-field[data-sender-form-id]` of the page, in a
 * same-origin about:blank iframe sized after the form.
 *
 * Design: once the iframe exists, the site's stylesheet for it
 * (`data-frame-css`, css/sender-frame.css) is injected into it, its theme
 * follows the page's (`data-theme`), and its height follows the restyled
 * form. Should Sender ever switch to a cross-origin iframe, the form keeps
 * Sender's own design.
 *
 * Progressive enhancement: each `.form-embed` shows its fallback text by
 * default (no JS). `data-state` drives the CSS (_forms.scss):
 * - `loading`: skeleton while Sender's script loads and the form is styled;
 * - `ready`: the form is shown;
 * - `error`: the script failed or was blocked (ad blockers often block
 *   e-mail marketing scripts), the fallback text is shown again.
 */

const SCRIPT_URL = "https://cdn.sender.net/accounts_resources/universal.js";
const TIMEOUT_MS = 10000;
// Show the form even if the site's stylesheet is slow (Sender's design then).
const STYLE_TIMEOUT_MS = 3000;

const root = document.documentElement;
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

/** Same rule as js/theme.js: stored choice, else the OS preference. */
function currentTheme() {
  return root.dataset.theme || (darkQuery.matches ? "dark" : "light");
}

/** Sender's loader: queues calls until universal.js is loaded. */
function loadSender(account, onError) {
  window.Sender = "sender";
  window.sender =
    window.sender ||
    function () {
      (window.sender.q = window.sender.q || []).push(arguments);
    };
  window.sender.l = Date.now();
  window.sender.on = function (event, callback) {
    window.sender.listeners = window.sender.listeners || {};
    (window.sender.listeners[event] = window.sender.listeners[event] || []).push(callback);
  };

  const script = document.createElement("script");
  script.async = true;
  script.src = SCRIPT_URL;
  script.addEventListener("error", onError);
  document.head.append(script);

  window.sender(account);
}

/** The iframe's document, or null if it is not readable (cross-origin). */
function frameDocument(iframe) {
  try {
    return iframe.contentDocument;
  } catch {
    return null;
  }
}

/** Styles Sender's iframe like the site; calls `done` once applied (or not). */
function styleFrame(iframe, doc, cssUrl, done) {
  const form = doc.querySelector("form");

  // Theme: mirrored now and whenever the page's theme changes.
  const syncTheme = () => {
    doc.documentElement.dataset.theme = currentTheme();
  };
  syncTheme();
  new MutationObserver(syncTheme).observe(root, { attributeFilter: ["data-theme"] });
  darkQuery.addEventListener("change", syncTheme);

  // Height: Sender sizes the iframe after its own design; follow the form.
  const fit = () => {
    iframe.style.height = `${Math.ceil(form.getBoundingClientRect().height)}px`;
  };
  const FrameResizeObserver = iframe.contentWindow.ResizeObserver || window.ResizeObserver;
  new FrameResizeObserver(fit).observe(form);

  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    fit();
    done();
  };
  const link = doc.createElement("link");
  link.rel = "stylesheet";
  link.href = cssUrl;
  link.addEventListener("load", finish);
  link.addEventListener("error", finish);
  setTimeout(finish, STYLE_TIMEOUT_MS);
  doc.head.append(link);
}

/** Follows one form: loading → (styled) ready, or error. */
function watch(embed) {
  const field = embed.querySelector(".sender-form-field");
  if (!field) return;
  embed.dataset.state = "loading";

  let done = false;
  let retry = 0;
  const ready = () => {
    embed.dataset.state = "ready";
  };
  // True once Sender has rendered the form (then styled, or shown as is).
  const check = () => {
    clearTimeout(retry);
    if (done || !field.childElementCount) return done;
    const iframe = field.querySelector("iframe");
    const doc = iframe && frameDocument(iframe);
    if (doc && !doc.querySelector("form")) {
      retry = setTimeout(check, 100); // Sender is still filling it in.
      return false;
    }
    done = true;
    observer.disconnect();
    clearTimeout(timer);
    if (doc && embed.dataset.frameCss) {
      styleFrame(iframe, doc, embed.dataset.frameCss, ready);
    } else {
      ready(); // No iframe, or a cross-origin one: Sender's design.
    }
    return true;
  };

  const observer = new MutationObserver(check);
  const timer = setTimeout(() => {
    if (check()) return;
    done = true;
    observer.disconnect();
    clearTimeout(retry);
    embed.dataset.state = "error";
  }, TIMEOUT_MS);
  if (!check()) observer.observe(field, { childList: true, subtree: true });
}

function fail(embeds) {
  for (const embed of embeds) {
    if (embed.dataset.state === "loading") embed.dataset.state = "error";
  }
}

const embeds = [...document.querySelectorAll(".form-embed[data-sender-account]")];
if (embeds.length) {
  embeds.forEach(watch);
  loadSender(embeds[0].dataset.senderAccount, () => fail(embeds));
}
