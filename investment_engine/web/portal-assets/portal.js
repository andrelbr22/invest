"use strict";

(() => {
  const BASE_PATH = location.pathname === "/testefdi" || location.pathname.startsWith("/testefdi/") ? "/testefdi" : "";
  const one = selector => document.querySelector(selector);
  const all = selector => [...document.querySelectorAll(selector)];
  const setText = (selector, value) => {
    const node = one(selector);
    if (node && typeof value === "string") node.textContent = value;
  };
  const coverUrl = book => book.cover_media_id
    ? `${BASE_PATH}/portal-media/${encodeURIComponent(book.cover_media_id)}`
    : `${BASE_PATH}${book.fallback_cover_path || "/portal-assets/books/formacao-investidor-fundamentos.webp"}`;

  function setBrand(content) {
    all(".brand-monogram").forEach(node => { node.textContent = content.brand.monogram; });
    all(".portal-brand").forEach(node => {
      const primary = node.querySelector("strong");
      const secondary = node.querySelector("small");
      if (primary) primary.textContent = content.brand.primary;
      if (secondary) secondary.textContent = content.brand.secondary;
    });
    const links = all(".portal-nav a");
    if (links[0]) links[0].textContent = content.navigation.books;
    if (links[1]) links[1].textContent = content.navigation.purpose;
    if (links[2]) links[2].textContent = `${content.navigation.platform} →`;
    if (links[3]) links[3].textContent = content.navigation.admin;
    setText(".skip-link", content.navigation.skip);
  }

  function setHero(content, books) {
    setText(".hero-copy .eyebrow", content.hero.eyebrow);
    setText("#hero-title", content.hero.title);
    setText(".hero-intro", content.hero.intro);
    const actions = all(".hero-actions a");
    if (actions[0]) actions[0].textContent = `${content.hero.primary_action} →`;
    if (actions[1]) actions[1].textContent = content.hero.secondary_action;
    const proof = one(".hero-proof");
    if (proof) {
      proof.replaceChildren(...content.hero.proof.map(label => {
        const span = document.createElement("span"); span.textContent = label; return span;
      }));
    }
    const note = one(".collection-note");
    if (note) {
      const title = note.querySelector("strong"), subtitle = note.querySelector("span");
      if (title) title.textContent = content.hero.collection_title;
      if (subtitle) subtitle.textContent = content.hero.collection_subtitle;
    }
    const figures = [one(".cover-left"), one(".cover-center"), one(".cover-right")];
    figures.forEach((figure, index) => {
      if (!figure) return;
      const book = books.find(item => Number(item.hero_position) === index + 1);
      figure.hidden = !book;
      const image = figure.querySelector("img");
      if (book && image) { image.src = coverUrl(book); image.alt = book.alt_text; }
    });
  }

  function setPurpose(content) {
    setText("#proposta .section-heading .eyebrow", content.purpose.eyebrow);
    setText("#proposta .section-heading h2", content.purpose.title);
    const grid = one(".purpose-grid");
    if (!grid) return;
    grid.replaceChildren(...content.purpose.items.map(item => {
      const article = document.createElement("article");
      const number = document.createElement("span"); number.textContent = item.number;
      const title = document.createElement("h3"); title.textContent = item.title;
      const body = document.createElement("p"); body.textContent = item.body;
      article.append(number, title, body); return article;
    }));
  }

  function bookCard(book) {
    const article = document.createElement("article");
    article.className = `book-card${book.collection === "primary" ? " featured" : ""}`;
    const image = document.createElement("img");
    image.src = coverUrl(book); image.alt = book.alt_text; image.loading = "lazy";
    const copy = document.createElement("div"); copy.className = "book-copy";
    const kicker = document.createElement("p"); kicker.className = "book-kicker"; kicker.textContent = book.kicker || "";
    const title = document.createElement("h3"); title.textContent = book.title;
    const summary = document.createElement("p"); summary.textContent = book.summary || "";
    const details = document.createElement("details"), detailsTitle = document.createElement("summary"), description = document.createElement("p");
    detailsTitle.textContent = window.__portalDetailsLabel || "Sobre esta obra";
    description.textContent = book.description || "";
    details.append(detailsTitle, description); copy.append(kicker, title, summary, details);
    if (book.sales_links?.length) {
      const links = document.createElement("div"); links.className = "book-sales-links";
      book.sales_links.forEach(item => {
        const anchor = document.createElement("a"); anchor.className = "book-sales-link";
        anchor.href = item.url; anchor.target = "_blank"; anchor.rel = "noopener noreferrer"; anchor.textContent = item.label;
        links.append(anchor);
      });
      copy.append(links);
    }
    article.append(image, copy); return article;
  }

  function setBooks(content, books) {
    setText("#livros .section-heading .eyebrow", content.books.eyebrow);
    setText("#books-title", content.books.title);
    const intro = one("#livros .section-heading > p"); if (intro) intro.textContent = content.books.intro;
    const titles = all("#livros .series-title");
    if (titles[0]) { titles[0].querySelector("span").textContent = content.books.primary_title; titles[0].querySelector("p").textContent = content.books.primary_subtitle; }
    if (titles[1]) { titles[1].querySelector("span").textContent = content.books.complementary_title; titles[1].querySelector("p").textContent = content.books.complementary_subtitle; }
    window.__portalDetailsLabel = content.books.details_label;
    const primary = one(".book-grid.trilogy"), complementary = one(".book-grid.complementary");
    if (primary) primary.replaceChildren(...books.filter(book => book.collection === "primary").map(bookCard));
    if (complementary) complementary.replaceChildren(...books.filter(book => book.collection === "complementary").map(bookCard));
  }

  function setPlatformAndFooter(content) {
    setText(".platform-callout .eyebrow", content.platform.eyebrow);
    setText(".platform-callout h2", content.platform.title);
    setText(".platform-callout div > p:last-child", content.platform.body);
    const platformButton = one(".platform-callout > a"); if (platformButton) platformButton.textContent = `${content.platform.button} →`;
    setText(".portal-footer > p", content.footer.disclaimer);
    const footerLink = one(".portal-footer > a:last-child"); if (footerLink) footerLink.textContent = content.footer.platform;
  }

  async function revealAdminLink() {
    try {
      const response = await fetch(`${BASE_PATH}/session/me`, {credentials: "same-origin", headers: {Accept: "application/json"}});
      if (!response.ok) return;
      const session = await response.json(), link = one("#portal-admin-link");
      if (link && session.authenticated && (session.access?.is_owner || session.access?.can_manage_portal)) link.hidden = false;
    } catch (_) {}
  }

  async function hydrate() {
    try {
      const response = await fetch(`${BASE_PATH}/public/portal`, {credentials: "same-origin", headers: {Accept: "application/json"}});
      if (!response.ok) return;
      const payload = await response.json(), content = payload.page, books = payload.books || [];
      if (!content) return;
      document.title = content.meta.title;
      const description = one('meta[name="description"]'); if (description) description.content = content.meta.description;
      setBrand(content); setHero(content, books); setPurpose(content); setBooks(content, books); setPlatformAndFooter(content);
      document.documentElement.dataset.portalRevision = String(payload.revision || "");
    } catch (_) {
      // The complete static page remains visible when the database or network is unavailable.
    }
  }

  document.addEventListener("DOMContentLoaded", () => { hydrate(); revealAdminLink(); });
})();
