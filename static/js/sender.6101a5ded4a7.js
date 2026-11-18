/**
 * Sender.net forms (newsletter and contact pages only).
 *
 * Sender's official snippet is an inline <script>, which the CSP forbids: it
 * is reproduced here as an external module. Sender's script then renders
 * every `.sender-form-field[data-sender-form-id]` of the page.
 *
 * Progressive enhancement: each `.form-embed` shows its fallback text by
 * default (no JS). `data-state` drives the CSS (_forms.scss):
 * - `loading`: skeleton while Sender's script loads;
 * - `ready`: Sender has rendered the form;
 * - `error`: the script failed or was blocked (ad blockers often block
 *   e-mail marketing scripts), the fallback text is shown again.
 */

const SCRIPT_URL = "https://cdn.sender.net/accounts_resources/universal.js";
const TIMEOUT_MS = 10000;

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

/** Resolves `embed` to `ready` as soon as Sender renders something in it. */
function watch(embed) {
  const field = embed.querySelector(".sender-form-field");
  if (!field) return;
  embed.dataset.state = "loading";

  const rendered = () => field.childElementCount > 0;
  if (rendered()) {
    embed.dataset.state = "ready";
    return;
  }
  const observer = new MutationObserver(() => {
    if (!rendered()) return;
    observer.disconnect();
    clearTimeout(timer);
    embed.dataset.state = "ready";
  });
  const timer = setTimeout(() => {
    observer.disconnect();
    embed.dataset.state = rendered() ? "ready" : "error";
  }, TIMEOUT_MS);
  observer.observe(field, { childList: true });
}

function fail(embeds) {
  for (const embed of embeds) {
    if (embed.dataset.state !== "ready") embed.dataset.state = "error";
  }
}

const embeds = [...document.querySelectorAll(".form-embed[data-sender-account]")];
if (embeds.length) {
  embeds.forEach(watch);
  loadSender(embeds[0].dataset.senderAccount, () => fail(embeds));
}
