(function () {
  "use strict";
  var data = JSON.parse(document.getElementById("page-data").textContent);
  var tagDefs = data.tags || {};
  var systems = data.systems || {};
  var list = data.collections || [];
  var hasPaths = list.some(function (c) { return (c.games || []).some(function (g) { return (g.paths || []).length; }); });
  var pressed = new Set();
  var cards = [];
  var current = null;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function plural(n, word) { return n + " " + word + (n === 1 ? "" : "s"); }
  function byName(a, b) { return a.name.localeCompare(b.name); }
  function formatSize(n) {
    var units = ["B", "KB", "MB", "GB", "TB"], i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (i === 0 ? String(n) : n.toFixed(n < 10 ? 2 : n < 100 ? 1 : 0)) + " " + units[i];
  }
  function sizeTotal(game) { return game.size ? game.size.rom + game.size.art : -1; }

  var pop = el("div", "size-pop");
  pop.hidden = true;
  document.body.appendChild(pop);
  function showPop(target, size) {
    pop.textContent = "";
    [["ROM", size.rom], ["Art data", size.art], ["Total", size.rom + size.art]].forEach(function (r) {
      var cls = r[0] === "Total" ? "sum" : "";
      pop.appendChild(el("span", cls, r[0]));
      pop.appendChild(el("span", cls, formatSize(r[1])));
    });
    pop.hidden = false;
    var box = target.getBoundingClientRect(), width = pop.offsetWidth, height = pop.offsetHeight;
    var left = Math.max(8, Math.min(box.right - width, window.innerWidth - width - 8));
    var top = box.bottom + 6 + height > window.innerHeight ? box.top - height - 6 : box.bottom + 6;
    pop.style.left = left + "px";
    pop.style.top = Math.max(8, top) + "px";
  }
  function hidePop() { pop.hidden = true; tip.hidden = true; }
  // The tag tooltip lives on the body, so no row or header border can clip it.
  var tip = el("div", "tip");
  tip.hidden = true;
  document.body.appendChild(tip);
  function tagOf(event) { return event.target.closest ? event.target.closest(".tag[data-tip]") : null; }
  function showTip(event) {
    var tag = tagOf(event);
    if (!tag) return;
    tip.textContent = tag.getAttribute("data-tip");
    tip.hidden = false;
    var box = tag.getBoundingClientRect(), width = tip.offsetWidth, height = tip.offsetHeight;
    var left = Math.max(8, Math.min(box.left + box.width / 2 - width / 2, window.innerWidth - width - 8));
    var top = box.top - height - 6 < 8 ? box.bottom + 6 : box.top - height - 6;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  function hideTip(event) { if (tagOf(event)) tip.hidden = true; }
  document.addEventListener("mouseover", showTip);
  document.addEventListener("mouseout", hideTip);
  document.addEventListener("focusin", showTip);
  document.addEventListener("focusout", hideTip);
  window.addEventListener("scroll", hidePop, {passive: true});
  document.addEventListener("click", function (event) {
    if (!event.target.classList || !event.target.classList.contains("size-val")) hidePop();
  });

  var select = document.getElementById("system");
  var all = el("option", "", "All systems");
  all.value = "";
  select.appendChild(all);
  Object.keys(systems).map(function (id) { return {id: id, name: systems[id]}; }).sort(byName)
    .forEach(function (s) {
      var option = el("option", "", s.name);
      option.value = s.id;
      select.appendChild(option);
    });

  var chips = document.getElementById("chips");
  var tagInput = document.getElementById("tag-input");
  var tagList = Object.keys(tagDefs).map(function (id) {
    return {id: id, name: tagDefs[id].name, emoji: tagDefs[id].emoji};
  }).sort(byName);
  var options = document.getElementById("tag-options");
  tagList.forEach(function (t) {
    var option = el("option");
    option.value = t.emoji + " " + t.name;
    options.appendChild(option);
  });
  function renderChips() {
    chips.textContent = "";
    tagList.filter(function (t) { return pressed.has(t.id); }).forEach(function (t) {
      var chip = el("button", "chip", t.emoji + " " + t.name + " \u00d7");
      chip.type = "button";
      chip.title = "Remove " + t.name;
      chip.setAttribute("aria-label", "Remove tag " + t.name);
      chip.addEventListener("click", function () {
        pressed.delete(t.id);
        renderChips();
        update();
      });
      chips.appendChild(chip);
    });
  }
  function addTag(typed, prefix) {
    var text = typed.trim().toLowerCase();
    if (!text) return false;
    var free = tagList.filter(function (t) { return !pressed.has(t.id); });
    var hits = free.filter(function (t) {
      return t.name.toLowerCase() === text || (t.emoji + " " + t.name).toLowerCase() === text;
    });
    if (!hits.length && prefix) {
      hits = free.filter(function (t) { return t.name.toLowerCase().indexOf(text) !== -1; });
      if (hits.length !== 1) hits = [];
    }
    if (hits.length !== 1) return false;
    pressed.add(hits[0].id);
    tagInput.value = "";
    renderChips();
    update();
    return true;
  }
  tagInput.addEventListener("input", function () { addTag(tagInput.value, false); });
  tagInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") { event.preventDefault(); addTag(tagInput.value, true); }
  });

  function fallbackCopy(text) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      return document.execCommand("copy") === true;
    } catch (e) {
      return false;
    } finally {
      document.body.removeChild(area);
    }
  }
  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(function () { return true; },
        function () { return fallbackCopy(text); });
    }
    return Promise.resolve(fallbackCopy(text));
  }
  function copyButton(button, text, label) {
    var timer;
    button.addEventListener("click", function () {
      copy(text()).then(function (ok) {
        button.textContent = ok ? "Copied" : "Copy failed";
        button.classList.toggle("done", ok);
        clearTimeout(timer);
        timer = setTimeout(function () {
          button.textContent = label;
          button.classList.remove("done");
        }, 1500);
      });
    });
  }

  var sortKey = "year", sortDir = 1;
  var bar = document.querySelector(".bar");

  function gameRow(game) {
    var row = el("tr", "game");
    var name = el("td", "");
    name.appendChild(el("div", "title", game.flag ? game.title + " " + game.flag : game.title));
    name.appendChild(el("div", "sys-inline", systems[game.system] || game.system));
    row.appendChild(name);
    row.appendChild(el("td", "col-system", systems[game.system] || game.system));
    row.appendChild(el("td", "col-year", game.year || "\u2014"));
    var sizeCell = el("td", "col-size");
    if (game.size) {
      var val = el("span", "size-val", formatSize(sizeTotal(game)));
      val.tabIndex = 0;
      val.setAttribute("aria-label", "Size " + formatSize(sizeTotal(game)) + ": ROM " + formatSize(game.size.rom) +
        ", art data " + formatSize(game.size.art));
      val.addEventListener("mouseenter", function () { showPop(val, game.size); });
      val.addEventListener("mouseleave", hidePop);
      val.addEventListener("focus", function () { showPop(val, game.size); });
      val.addEventListener("blur", hidePop);
      val.addEventListener("click", function () { showPop(val, game.size); });
      sizeCell.appendChild(val);
    } else {
      sizeCell.appendChild(el("span", "size-none", "\u2014"));
    }
    row.appendChild(sizeCell);
    var tagCell = el("td", "col-tags cell-tags");
    (game.tags || []).filter(function (id) { return tagDefs[id]; }).sort(function (a, b) {
      return tagDefs[a].name.localeCompare(tagDefs[b].name);
    }).forEach(function (id) {
      var def = tagDefs[id];
      var span = el("span", "", def.emoji);
      span.className = "tag";
      span.setAttribute("data-tip", def.name);
      span.setAttribute("aria-label", def.name);
      span.tabIndex = 0;
      tagCell.appendChild(span);
    });
    row.appendChild(tagCell);
    if (hasPaths) {
      var paths = (game.paths || []).join("\n");
      var button = el("button", "copy", "Copy");
      button.type = "button";
      button.title = paths;
      copyButton(button, function () { return paths; }, "Copy");
      var last = el("td", "col-copy");
      last.appendChild(button);
      row.appendChild(last);
    }
    return row;
  }

  function tagsOf(c) {
    var seen = {};
    (c.games || []).forEach(function (g) {
      (g.tags || []).forEach(function (id) { if (tagDefs[id]) seen[id] = true; });
    });
    return Object.keys(seen).map(function (id) { return {id: id, name: tagDefs[id].name, emoji: tagDefs[id].emoji}; })
      .sort(byName);
  }

  if (typeof data.home === "string") {
    var home = el("a", "home", "\u2190 All users");
    home.href = data.home;
    var header = document.querySelector("header");
    header.insertBefore(home, header.firstChild);
  }

  var grid = document.getElementById("grid");
  list.forEach(function (c) {
    var row = el("article", "row");
    var art = c.art || {};
    var head = el("div", "rhead");
    var text = el("div", "rtext");
    var title = el("div", "rtitle");
    title.appendChild(el("h2", "name", c.name));
    text.appendChild(title);
    if (c.description) text.appendChild(el("p", "desc", c.description));
    var pills = el("div", "pills");
    var meta = el("span", "pill meta");
    pills.appendChild(meta);
    function stat(value, label) {
      var pill = el("span", "pill");
      pill.appendChild(el("b", "", value));
      pill.appendChild(document.createTextNode(label));
      return pill;
    }
    if (c.size && (c.games || []).some(function (g) { return g.size; })) {
      [["Total", c.size.rom + c.size.art], ["ROMs", c.size.rom], ["Scraped Data", c.size.art]].forEach(function (p) {
        pills.appendChild(stat(formatSize(p[1]), p[0]));
      });
    }
    text.appendChild(pills);
    var tagLine = el("div", "pills tags");
    tagsOf(c).forEach(function (t) {
      var span = el("span", "tag", t.emoji);
      span.setAttribute("data-tip", t.name);
      span.setAttribute("aria-label", t.name);
      span.tabIndex = 0;
      tagLine.appendChild(span);
    });
    if (tagLine.childNodes.length) text.appendChild(tagLine);
    head.appendChild(text);
    var pics = el("div", "pics");
    [["box", "box"], ["band", "band"], ["totk", "ToTK"]].forEach(function (kind) {
      if (!art[kind[0]]) return;
      var img = document.createElement("img");
      img.loading = "lazy";
      img.src = art[kind[0]];
      img.alt = c.name + " " + kind[1];
      pics.appendChild(img);
    });
    if (pics.childNodes.length) head.appendChild(pics);
    row.appendChild(head);
    var games = (c.games || []).map(function (g, i) { return {game: g, index: i, tr: null}; });
    var entry = {collection: c, row: row, head: head, meta: meta, body: null, games: games, matching: games,
                 filtering: false, ths: null, tbody: null};
    if (games.length) {
      head.setAttribute("role", "button");
      head.tabIndex = 0;
      head.setAttribute("aria-expanded", "false");
      head.addEventListener("click", function () { toggle(entry); });
      head.addEventListener("keydown", function (event) {
        if (event.target === head && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          toggle(entry);
        }
      });
    }
    grid.appendChild(row);
    cards.push(entry);
  });

  function buildBody(entry) {
    var wrap = el("div", "tablewrap");
    var table = el("table", "games");
    var tr = el("tr");
    entry.ths = {};
    [["name", "Name", ""], ["system", "System", "col-system"], ["year", "Year", "col-year"], ["size", "Size", "col-size"], [null, "Tags", "col-tags"]]
      .concat(hasPaths ? [[null, "", "col-copy"]] : [])
      .forEach(function (col) {
        var th = el("th", col[2]);
        th.scope = "col";
        if (col[0]) {
          var button = el("button", "sort");
          button.type = "button";
          button.addEventListener("click", function () {
            if (sortKey === col[0]) sortDir = -sortDir;
            else { sortKey = col[0]; sortDir = col[0] === "size" ? -1 : 1; }
            cards.forEach(function (other) { if (other.body) renderTable(other); });
          });
          th.appendChild(button);
          entry.ths[col[0]] = {th: th, button: button, label: col[1]};
        } else {
          th.textContent = col[1];
        }
        tr.appendChild(th);
      });
    var thead = el("thead");
    thead.appendChild(tr);
    table.appendChild(thead);
    entry.tbody = el("tbody");
    table.appendChild(entry.tbody);
    wrap.appendChild(table);
    entry.body = wrap;
    entry.row.appendChild(wrap);
  }

  function renderTable(entry) {
    if (!entry.body) buildBody(entry);
    Object.keys(entry.ths).forEach(function (key) {
      var h = entry.ths[key];
      var on = key === sortKey;
      h.button.textContent = h.label + (on ? (sortDir > 0 ? " ▲" : " ▼") : "");
      h.button.classList.toggle("on", on);
      h.th.setAttribute("aria-sort", on ? (sortDir > 0 ? "ascending" : "descending") : "none");
    });
    var rows = entry.matching.slice();
    function tie(a, b) {  // name (the page's title order), then system
      if (a.game.title === b.game.title) {
        return (systems[a.game.system] || a.game.system).localeCompare(systems[b.game.system] || b.game.system) || a.index - b.index;
      }
      return a.index - b.index;
    }
    rows.sort(function (a, b) {
      var order = 0;
      if (sortKey === "size") {  // no known size sorts last in either direction
        var sa = sizeTotal(a.game), sb = sizeTotal(b.game);
        if ((sa < 0) !== (sb < 0)) return sa < 0 ? 1 : -1;
        return (sa - sb) * sortDir || tie(a, b);
      }
      if (sortKey === "year") {  // no known year sorts last in either direction
        var ya = a.game.year || "", yb = b.game.year || "";
        if (!ya !== !yb) return ya ? -1 : 1;
        return ya.localeCompare(yb) * sortDir || tie(a, b);
      }
      if (sortKey === "system") {
        order = (systems[a.game.system] || a.game.system).localeCompare(systems[b.game.system] || b.game.system);
      }
      return (order || tie(a, b)) * sortDir;
    });
    entry.tbody.textContent = "";
    rows.forEach(function (r) {
      if (!r.tr) r.tr = gameRow(r.game);
      entry.tbody.appendChild(r.tr);
    });
    if (!rows.length) {
      var none = el("tr", "nomatch");
      var cell = el("td", "", "No games match the filters");
      cell.colSpan = 6;
      none.appendChild(cell);
      entry.tbody.appendChild(none);
    }
  }

  var search = document.getElementById("search");
  var count = document.getElementById("count");
  var empty = document.getElementById("empty");

  function params(collection) {
    var out = new URLSearchParams();
    var query = search.value.trim();
    if (query) out.set("q", query);
    if (select.value) out.set("system", select.value);
    if (pressed.size) out.set("tags", Array.from(pressed).sort().join(","));
    if (collection) out.set("c", collection);
    return out;
  }
  function pageUrl() {
    if (location.origin === "null") return location.href.split("#")[0];
    return location.origin + location.pathname;
  }
  function writeHash() {
    var hash = params(current).toString();
    try {
      if (hash) history.replaceState(null, "", "#" + hash);
      else history.replaceState(null, "", location.pathname + location.search);
    } catch (e) {
      // Some browsers refuse replaceState on file:// pages; the page still works without the hash.
    }
  }
  function barHeight() { return Math.round(bar.getBoundingClientRect().height); }
  function measureBar() {
    document.documentElement.style.setProperty("--bar-h", barHeight() + "px");
  }
  function scrollToRow(entry) {
    var top = entry.row.getBoundingClientRect().top + window.scrollY;
    window.scrollTo(0, top - barHeight() - 12);
  }
  function openEntry() {
    return cards.filter(function (entry) { return entry.collection.id === current; })[0];
  }
  var toast = el("div", "toast");
  toast.hidden = true;
  document.body.appendChild(toast);
  var toastTimer;
  function copyLink(entry) {
    copy(pageUrl() + "#" + params(entry.collection.id).toString()).then(function (ok) {
      toast.textContent = ok ? "Link copied" : "Couldn't copy the link";
      toast.hidden = false;
      clearTimeout(toastTimer);
      toastTimer = setTimeout(function () { toast.hidden = true; }, 1500);
    });
  }
  function toggle(entry) {
    var before = entry.row.getBoundingClientRect().top;
    var closing = current === entry.collection.id;
    current = closing ? null : entry.collection.id;
    update();
    var after = entry.row.getBoundingClientRect().top;
    if (!closing && after !== before) window.scrollBy(0, after - before); // keep the row where it was
    if (entry.row.getBoundingClientRect().top < barHeight()) scrollToRow(entry);
    if (!closing) copyLink(entry);
  }
  function applyHash() {
    var hash = new URLSearchParams(location.hash.slice(1));
    search.value = hash.get("q") || "";
    var system = hash.get("system") || "";
    select.value = Object.prototype.hasOwnProperty.call(systems, system) ? system : "";
    pressed.clear();
    (hash.get("tags") || "").split(",").forEach(function (id) {
      if (id && Object.prototype.hasOwnProperty.call(tagDefs, id)) pressed.add(id);
    });
    renderChips();
    var wanted = hash.get("c");
    var target = cards.filter(function (entry) { return entry.collection.id === wanted && entry.games.length; })[0];
    current = target ? wanted : null;
    update();
    if (target) scrollToRow(target);
  }

  function update() {
    var query = search.value.trim().toLowerCase();
    var system = select.value;
    var filtering = Boolean(query || system || pressed.size);
    var shownCollections = 0, shownGames = 0;
    cards.forEach(function (entry) {
      var nameHit = query && entry.collection.name.toLowerCase().indexOf(query) !== -1;
      entry.matching = entry.games.filter(function (r) {
        var g = r.game;
        return (!query || nameHit || String(g.title).toLowerCase().indexOf(query) !== -1) &&
          (!system || g.system === system) &&
          Array.from(pressed).every(function (t) { return (g.tags || []).indexOf(t) !== -1; });
      });
      var passing = entry.matching.length;
      var picked = entry.collection.id === current;
      var visible = picked || !filtering || passing > 0;
      entry.row.hidden = !visible;
      entry.row.classList.toggle("open", picked);
      entry.head.setAttribute("aria-expanded", picked ? "true" : "false");
      if (picked) renderTable(entry);
      if (entry.body) entry.body.hidden = !picked;
      var total = entry.games.length;
      entry.meta.textContent = "";
      entry.meta.appendChild(el("b", "", String(passing)));
      entry.meta.appendChild(document.createTextNode(
        (filtering && passing !== total ? "of " + total + " " : "") + (total === 1 ? "game" : "games")));
      if (visible) { shownCollections++; shownGames += passing; }
    });
    count.textContent = plural(shownCollections, "collection") + " · " + plural(shownGames, "game");
    if (!list.length) {
      empty.textContent = "No collections yet.";
      empty.hidden = false;
    } else if (!shownCollections) {
      empty.textContent = "No games match.";
      empty.hidden = false;
    } else {
      empty.hidden = true;
    }
    writeHash();
  }

  search.addEventListener("input", update);
  select.addEventListener("change", update);
  document.getElementById("clear").addEventListener("click", function () {
    search.value = "";
    select.value = "";
    pressed.clear();
    tagInput.value = "";
    renderChips();
    update();
  });
  window.addEventListener("hashchange", applyHash);
  window.addEventListener("resize", function () { measureBar(); });
  if (window.ResizeObserver) new ResizeObserver(measureBar).observe(bar);
  // The bar covers the open row's top border while its header is stuck, so the stuck header draws its own.
  function markStuck() {
    var open = openEntry();
    cards.forEach(function (entry) {
      var stuck = entry === open && entry.row.getBoundingClientRect().top < barHeight() - 1;
      entry.row.classList.toggle("stuck", stuck);
    });
  }
  window.addEventListener("scroll", markStuck, { passive: true });
  window.addEventListener("resize", markStuck);
  measureBar();
  applyHash();
})();
