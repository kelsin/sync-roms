"use strict";
(function () {
  const data = JSON.parse(document.getElementById("page-data").textContent || "{}");
  const sections = data.sections || [];
  const BIG = { frames: 2, boxes: 2 }; // tile scale per section; sprites 3x
  const GAP = 16; // the view keeps this far from the viewport's edges
  const GRID = "rgba(128, 128, 128, .55)";
  const hoverable = window.matchMedia("(hover: hover)");

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
    document.getElementById("palette").textContent = "Frames are shown in the " + data.palette + " palette.";
  }

  // Sections and tiles
  const jump = document.getElementById("jump");
  const main = document.getElementById("sections");
  const grids = [];
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
      const tile = el("button", "tile");
      tile.type = "button";
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
      tile.addEventListener("pointerenter", () => { if (hoverable.matches && !pinned) open(item, tile, false); });
      tile.addEventListener("pointerleave", () => { if (!pinned && current === tile) close(); });
      tile.addEventListener("click", () => {
        if (pinned && current === tile) close();
        else open(item, tile, true);
      });
      grid.append(tile);
      tiles.push({ item, tile, art, img });
    }
    box.append(h2, grid);
    main.append(box);
    grids.push({ scale: BIG[section.id] || 3, tiles });
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
  window.addEventListener("resize", () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; layout(); if (current) close(); });
  });

  // Large view
  const view = document.getElementById("view");
  const viewArt = document.getElementById("view-art");
  const viewInfo = document.getElementById("view-info");
  let current = null, pinned = false, generation = 0;

  function info(item) {
    viewInfo.replaceChildren(el("div", "title", item.label));
    let meta = dims(item.w, item.h) + " pixels";
    if (item.cell) meta += " · 1 pixel = " + item.cell + " screen pixels";
    viewInfo.append(el("div", "meta", meta));
    if (item.note) viewInfo.append(el("div", "meta", item.note));
    if (item.files && item.files.length) {
      const list = el("ul");
      for (const file of item.files) {
        const li = el("li", "", file.path + "  ");
        li.append(el("span", "dim", file.size ? dims(file.size[0], file.size[1]) : "size unknown"));
        list.append(li);
      }
      viewInfo.append(list);
    }
  }

  function draw(canvas, img, w, h, s) {
    canvas.width = w * s;
    canvas.height = h * s;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(img, 0, 0, w * s, h * s);
    if (s < 3) return; // a grid at 1x or 2x would hide the picture
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

  function open(item, tile, pin) {
    const gen = ++generation;
    if (current) current.classList.remove("open");
    current = tile;
    pinned = pin;
    tile.classList.add("open");
    view.classList.toggle("hover", !pin);
    info(item);
    const srcs = item.dim ? [item.img, item.dim] : [item.img];
    Promise.all(srcs.map(load)).then((imgs) => {
      if (gen !== generation) return;
      const { w, h } = item;
      viewArt.replaceChildren();
      view.hidden = false;
      // Room for the art: the viewport less the gutter, the panel's padding and border, and the info under it.
      const pad = 26;
      const roomW = window.innerWidth - 2 * GAP - pad;
      const roomH = window.innerHeight - 2 * GAP - pad - viewInfo.offsetHeight - 10;
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
      s = Math.max(1, s);
      viewArt.classList.toggle("stacked", stacked);
      imgs.forEach((img, i) => {
        const canvas = el("canvas");
        draw(canvas, img, w, h, s);
        if (imgs.length === 1) { viewArt.append(canvas); return; }
        const fig = el("figure");
        fig.append(canvas, el("figcaption", "", i === 0 ? "selected" : "unselected"));
        viewArt.append(fig);
      });
      place(tile);
    }, () => {});
  }

  // Beside the tile when there's room (so hovering doesn't cover it), else over it; always inside the viewport.
  function place(tile) {
    const vw = window.innerWidth, vh = window.innerHeight;
    const pw = view.offsetWidth, ph = view.offsetHeight;
    const r = tile.getBoundingClientRect();
    let x, y;
    if (pinned && !hoverable.matches) {
      x = (vw - pw) / 2;
      y = (vh - ph) / 2;
    } else {
      if (r.right + 12 + pw <= vw - GAP) x = r.right + 12;
      else if (r.left - 12 - pw >= GAP) x = r.left - 12 - pw;
      else x = (vw - pw) / 2;
      y = r.top + r.height / 2 - ph / 2;
    }
    view.style.left = Math.round(Math.max(GAP, Math.min(x, vw - GAP - pw))) + "px";
    view.style.top = Math.round(Math.max(GAP, Math.min(y, vh - GAP - ph))) + "px";
  }

  function close() {
    generation++;
    if (current) current.classList.remove("open");
    current = null;
    pinned = false;
    view.hidden = true;
    viewArt.replaceChildren();
  }

  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && current) close(); });
  document.addEventListener("click", (e) => {
    if (current && !view.contains(e.target) && !e.target.closest(".tile")) close();
  });
  window.addEventListener("scroll", () => { if (current && !pinned) close(); }, { passive: true });
})();
