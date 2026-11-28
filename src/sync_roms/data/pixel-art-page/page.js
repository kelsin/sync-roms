"use strict";
(function () {
  const data = JSON.parse(document.getElementById("page-data").textContent || "{}");
  const sections = data.sections || [];
  const BIG = { boxes: 2 }; // tile scale per section; sprites 3x
  const GRID = "rgba(128, 128, 128, .55)";

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function dims(w, h) { return w + "×" + h; }

  if (data.home) {
    const home = document.getElementById("home");
    home.href = data.home;
    home.hidden = false;
  }
  if (data.palette) {
    document.getElementById("palette").textContent = "Palette icons are shown in the " + data.palette + " palette.";
  }

  // Sections and tiles
  const jump = document.getElementById("jump");
  const main = document.getElementById("sections");
  const grids = [];
  const byId = new Map();
  let selected = null;
  for (const section of sections) {
    const link = el("a");
    link.href = "#" + section.id;
    link.append(el("span", "", section.title), el("span", "count", String(section.items.length)));
    jump.append(link);

    const box = el("section");
    box.id = section.id;
    const h2 = el("h2", "", section.title);
    h2.append(el("span", "count", section.items.length + (section.items.length === 1 ? " picture" : " pictures")));
    const grid = el("div", "grid " + section.id);
    const tiles = [];
    for (const item of section.items) {
      const tile = el("a", "tile");
      // The anchor is the section and the picture's file stem, which page data keeps unique per section.
      tile.id = section.id + "-" + item.img.split("/").pop().replace(/\.png$/, "");
      tile.href = "#" + tile.id;
      const art = el("div", "art");
      const img = el("img");
      img.src = item.img;
      img.alt = item.label;
      img.width = item.w;
      img.height = item.h;
      img.decoding = "async";
      img.loading = "lazy";
      art.append(img);
      tile.append(art, el("div", "label", item.label), el("div", "size", dims(item.w, item.h)));
      if (item.note) tile.append(el("div", "note", item.note));
      tile.addEventListener("click", (e) => {
        if (e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; // let new-tab clicks through
        e.preventDefault();
        if (selected && selected.tile === tile) { history.pushState(null, "", location.pathname + location.search); select(null); }
        else { history.pushState(null, "", tile.href); select(byId.get(tile.id), "nearest"); }
      });
      grid.append(tile);
      const entry = { item, tile, art, img, grid };
      tiles.push(entry);
      byId.set(tile.id, entry);
    }
    box.append(h2, grid);
    main.append(box);
    grids.push({ scale: BIG[section.id] || 3, tiles });
  }
  const guideLink = el("a");
  guideLink.href = "#artist-guide";
  guideLink.append(el("span", "", "For pixel artists"));
  jump.append(guideLink);

  // The artists' brief: a swatch per sprite colour.
  const swatches = document.getElementById("guide-swatches");
  for (const [name, hex] of Object.entries(data.colors || {})) {
    const chip = el("span", "g-chip");
    const box = el("i");
    box.style.background = hex;
    chip.append(box, document.createTextNode(name + " " + hex));
    swatches.append(chip);
  }

  // Each picture at an integer scale: the section's, or the largest that fits its tile. A picture wider than a tile
  // gets a full row; one wider than that stays at 1x and scrolls inside its tile.
  function layout() {
    for (const { scale, tiles } of grids) {
      if (!tiles.length) continue;
      for (const t of tiles) t.tile.classList.remove("wide");
      const narrow = tiles[0].art.clientWidth;
      let wide = null;
      for (const t of tiles) {
        const fits = t.item.w <= narrow;
        t.tile.classList.toggle("wide", !fits);
        if (!fits && !wide) wide = t;
      }
      const full = wide ? wide.art.clientWidth : narrow;
      for (const t of tiles) {
        const room = t.tile.classList.contains("wide") ? full : narrow;
        const s = Math.max(1, Math.min(scale, Math.floor(room / t.item.w)));
        t.img.style.width = t.item.w * s + "px";
        t.img.style.height = t.item.h * s + "px";
      }
    }
  }
  layout();
  let queued = false;
  let lastWidth = window.innerWidth;
  window.addEventListener("resize", () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      layout();
      // Only a width change moves the rows: a phone's address bar hiding changes just the height.
      if (selected && window.innerWidth !== lastWidth) show(selected);
      lastWidth = window.innerWidth;
    });
  });

  // The detail: one panel, moved into the selected tile's grid right after the last tile of its row.
  const detail = el("div", "detail");
  detail.hidden = true;
  detail.setAttribute("role", "region");
  detail.setAttribute("aria-label", "Selected picture");
  const closeButton = el("button", "detail-close", "×");
  closeButton.type = "button";
  closeButton.setAttribute("aria-label", "Close");
  closeButton.addEventListener("click", () => {
    const tile = selected && selected.tile;
    history.pushState(null, "", location.pathname + location.search);
    select(null);
    if (tile) tile.focus({ preventScroll: true });
  });
  const detailArt = el("div", "detail-art");
  const detailInfo = el("div", "detail-info");
  detail.append(closeButton, detailArt, detailInfo);
  let generation = 0;

  function info(entry) {
    const { item, tile } = entry;
    const title = el("div", "title");
    const link = el("a", "", item.label);
    link.href = "#" + tile.id;
    title.append(link);
    detailInfo.replaceChildren(title);
    let meta = dims(item.w, item.h) + " pixels";
    if (item.cell) meta += " · 1 pixel = " + item.cell + " screen pixels";
    detailInfo.append(el("div", "meta", meta));
    if (item.note) detailInfo.append(el("div", "meta", item.note));
    if (item.files && item.files.length) {
      const list = el("ul");
      for (const file of item.files) {
        const li = el("li", "", file.path + "  ");
        if (file.theme) li.append(el("span", "dim", "(in the " + file.theme + " theme)  "));
        li.append(el("span", "dim", file.size ? dims(file.size[0], file.size[1]) : "size unknown"));
        list.append(li);
      }
      detailInfo.append(list);
    }
  }

  function draw(canvas, img, w, h, s) {
    canvas.width = w * s;
    canvas.height = h * s;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, 0, 0, w * s, h * s);
    ctx.fillStyle = GRID;
    for (let x = 1; x < w; x++) ctx.fillRect(x * s, 0, 1, h * s);
    for (let y = 1; y < h; y++) ctx.fillRect(0, y * s, w * s, 1);
  }

  function load(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = src;
    });
  }

  // Put the panel after the selected tile's row and point its caret at the tile.
  function place(entry) {
    const { tile, grid } = entry;
    detail.remove();
    let last = tile;
    for (let next = tile.nextElementSibling; next && next.offsetTop === tile.offsetTop; next = next.nextElementSibling) last = next;
    last.after(detail);
    const g = grid.getBoundingClientRect(), r = tile.getBoundingClientRect();
    detail.style.setProperty("--caret", Math.round(r.left + r.width / 2 - g.left) + "px");
  }

  function show(entry) {
    const gen = ++generation;
    const { item } = entry;
    place(entry);
    const srcs = item.dim ? [item.img, item.dim] : [item.img];
    return Promise.all(srcs.map(load)).then((imgs) => {
      if (gen !== generation) return;
      info(entry);
      detailArt.replaceChildren();
      detail.hidden = false;
      const { w, h } = item;
      // Room for the art: the panel's width less its padding, and about 60% of the viewport's height.
      const roomW = detailArt.clientWidth;
      const roomH = Math.max(160, Math.round(document.documentElement.clientHeight * 0.6));
      let s, stacked = false;
      if (imgs.length === 1) {
        s = Math.floor(Math.min(roomW / w, roomH / h));
      } else {
        const caption = 20, gap = 12;
        const side = Math.floor(Math.min((roomW - gap) / (2 * w), (roomH - caption) / h));
        const stack = Math.floor(Math.min(roomW / w, (roomH - gap - 2 * caption) / (2 * h)));
        stacked = stack > side;
        s = Math.max(side, stack);
      }
      s = Math.max(4, s); // at least 4x, with the grid: past the panel's width, the art scrolls
      detailArt.classList.toggle("stacked", stacked);
      imgs.forEach((img, i) => {
        const canvas = el("canvas");
        draw(canvas, img, w, h, s);
        if (imgs.length === 1) { detailArt.append(canvas); return; }
        const fig = el("figure");
        fig.append(canvas, el("figcaption", "", i === 0 ? "selected" : "unselected"));
        detailArt.append(fig);
      });
    }, () => {});
  }

  // scroll: "start" brings the tile to the top (a link opened), "nearest" only what it takes to show the panel.
  function select(entry, scroll) {
    if (selected) selected.tile.classList.remove("selected");
    selected = entry;
    if (!entry) {
      generation++;
      detail.hidden = true;
      detail.remove();
      detailArt.replaceChildren();
      return;
    }
    entry.tile.classList.add("selected");
    show(entry).then(() => {
      if (selected !== entry || !scroll) return;
      if (scroll === "start") entry.tile.scrollIntoView({ block: "start" });
      else {
        const r = entry.tile.getBoundingClientRect(), d = detail.getBoundingClientRect();
        const vh = document.documentElement.clientHeight;
        // Show the panel's bottom without pushing its tile off the top.
        const by = Math.min(d.bottom - vh + 12, r.top - 12);
        if (by > 0) window.scrollBy({ top: by, behavior: "smooth" });
      }
    });
  }

  function fromHash(scroll) {
    const entry = byId.get(decodeURIComponent(location.hash.slice(1)));
    if (entry) { if (entry !== selected) select(entry, scroll); }
    else if (!location.hash && selected) select(null); // a section link keeps the selection
  }
  // Back and forward through pushState entries fire hashchange too, so this one listener covers them.
  window.addEventListener("hashchange", () => fromHash("nearest"));
  fromHash("start");

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && selected) closeButton.click();
  });
})();
