/**
 * Progressive enhancements (the site works without JS):
 *
 * - Tag hover cards: hovering or focusing a tag shows its history timeline.
 *   Every tag is a plain link to its page, which shows the full thread. The
 *   card is a pre-rendered static HTML fragment (`data-timeline`), fetched
 *   once per tag and cached. Hovering a timeline dot highlights its news in
 *   the card's list, and vice versa (`data-news`).
 * - Tag page thread: the entry nearest the middle of the screen is
 *   highlighted while scrolling.
 */

const SHOW_DELAY_MS = 250;
const HIDE_DELAY_MS = 200;
const CARD_ID = "tag-card";

const fragments = new Map();
let card = null;
let activeTag = null;
let showTimer = 0;
let hideTimer = 0;

function getCard() {
  if (!card) {
    card = document.createElement("div");
    card.id = CARD_ID;
    card.className = "tag-card";
    card.setAttribute("role", "tooltip");
    card.hidden = true;
    card.addEventListener("pointerenter", () => clearTimeout(hideTimer));
    card.addEventListener("pointerleave", () => {
      highlightNews(null);
      scheduleHide();
    });
    card.addEventListener("pointerover", (event) => highlightNews(newsIdFrom(event)));
    document.body.append(card);
  }
  return card;
}

function newsIdFrom(event) {
  const target = event.target instanceof Element ? event.target.closest("[data-news]") : null;
  return target ? target.dataset.news : null;
}

/** Highlights every element of the card about the news `id` (or none). */
function highlightNews(id) {
  for (const element of card.querySelectorAll("[data-news]")) {
    element.classList.toggle("is-highlighted", element.dataset.news === id);
  }
}

async function loadFragment(url) {
  if (!fragments.has(url)) {
    const request = fetch(url, { headers: { Accept: "text/html" } }).then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.text();
    });
    // Forget failures so a later hover can retry.
    request.catch(() => fragments.delete(url));
    fragments.set(url, request);
  }
  return fragments.get(url);
}

function position(tag, element) {
  const rect = tag.getBoundingClientRect();
  const margin = 8;
  const width = element.offsetWidth;
  const maxLeft = document.documentElement.clientWidth - width - margin;
  const left = Math.max(margin, Math.min(rect.left, maxLeft));
  element.style.left = `${left + window.scrollX}px`;
  element.style.top = `${rect.bottom + window.scrollY + margin}px`;
}

async function show(tag) {
  const element = getCard();
  let html;
  try {
    html = await loadFragment(tag.dataset.timeline);
  } catch {
    return; // The link still works; nothing else to do.
  }
  if (activeTag !== tag) return;
  const fragment = new DOMParser().parseFromString(html, "text/html");
  element.replaceChildren(...fragment.body.childNodes);
  element.hidden = false;
  position(tag, element);
  tag.setAttribute("aria-describedby", CARD_ID);
  tag.setAttribute("aria-expanded", "true");
}

function hide() {
  clearTimeout(showTimer);
  if (activeTag) {
    activeTag.removeAttribute("aria-describedby");
    activeTag.removeAttribute("aria-expanded");
  }
  activeTag = null;
  if (card) card.hidden = true;
}

function scheduleShow(tag) {
  clearTimeout(hideTimer);
  clearTimeout(showTimer);
  if (activeTag && activeTag !== tag) hide();
  activeTag = tag;
  showTimer = setTimeout(() => show(tag), SHOW_DELAY_MS);
}

function scheduleHide() {
  clearTimeout(showTimer);
  hideTimer = setTimeout(hide, HIDE_DELAY_MS);
}

function tagFrom(event) {
  return event.target instanceof Element ? event.target.closest(".tag[data-timeline]") : null;
}

function initTagCards() {
  // Only devices with a real hover get cards; touch users open the tag page.
  if (!window.matchMedia("(hover: hover)").matches) return;

  document.addEventListener("pointerover", (event) => {
    const tag = tagFrom(event);
    if (tag && tag !== activeTag) scheduleShow(tag);
  });
  document.addEventListener("pointerout", (event) => {
    const tag = tagFrom(event);
    if (tag && !tag.contains(event.relatedTarget)) scheduleHide();
  });
  document.addEventListener("focusin", (event) => {
    const tag = tagFrom(event);
    if (tag) scheduleShow(tag);
  });
  document.addEventListener("focusout", (event) => {
    if (tagFrom(event)) scheduleHide();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hide();
  });
  window.addEventListener("resize", hide);
}

function initThread() {
  const thread = document.querySelector(".thread");
  if (!thread) return;
  const items = [...thread.querySelectorAll(".thread__item")];
  let active = null;
  let frame = 0;

  function update() {
    frame = 0;
    const middle = window.innerHeight / 2;
    let nearest = null;
    let nearestDistance = Infinity;
    for (const item of items) {
      const rect = item.getBoundingClientRect();
      const distance = Math.abs(rect.top + rect.height / 2 - middle);
      if (distance < nearestDistance) {
        nearest = item;
        nearestDistance = distance;
      }
    }
    if (nearest === active) return;
    active?.classList.remove("thread__item--active");
    nearest?.classList.add("thread__item--active");
    active = nearest;
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(update);
  }

  thread.classList.add("thread--tracking");
  update();
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", schedule);
}

initTagCards();
initThread();
