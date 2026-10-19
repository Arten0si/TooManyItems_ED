/* TooManyItems – logika okna. Dane z lokalnego serwera tmi_gui.py (tylko 127.0.0.1, klucz w adresie). */
"use strict";

const TOKEN = new URLSearchParams(location.hash.slice(1)).get("t") || "";
const $ = (id) => document.getElementById(id);

const RARITY = [
  ["Legendary", "var(--r-legendary)"],
  ["Epic", "var(--r-epic)"],
  ["Rare", "var(--r-rare)"],
  ["Uncommon", "var(--r-uncommon)"],
  ["Common", "var(--r-common)"],
];
const R_COLOR = Object.fromEntries(RARITY);
const R_ORDER = Object.fromEntries(RARITY.map(([k], i) => [k, i]));

// Napisy okna w wybranym języku (gui/i18n.js); brak -> angielski
let L = I18N.Pl_Pl;
const EN = I18N.En_Us;
const T = (k) => L[k] ?? EN[k];
const TM = (group, k) => (L[group] && L[group][k]) || (EN[group] && EN[group][k]) || k;
const fill = (tpl, a) => String(tpl).replace(/\{(\w+)\}/g, (_, k) => (a[k] !== undefined ? a[k] : ""));
const TS = (k, a) => fill((L.st && L.st[k]) || EN.st[k] || k, a || {});
const EYE = { black: "#1d1d1d", blue: "#3f74d8", blue_bright: "#8fc4f2", brown_dark: "#4a2d18", brown_bright: "#9a6a3b",
  red_dark: "#7a1c1c", red: "#d43b3b", grey: "#8c9399", green: "#3f9a4b", orange: "#e08a2e", pink: "#e98bc4",
  purple: "#8a4fcf", turquoise: "#33c2b8", white: "#e8e8e8", yellow: "#e6c83a" };
const ICONS = {
  helmet: "M3 15c2-5 5-7 9-7s7 2 9 7 M3 15h18 M12 8V4 M12 4l-1 2h2z",
  chest: "M7 4l5 2 5-2 3 4-3 2v10H7V10L4 8z M12 6v14",
  gloves: "M8 21v-6L5 11V6h2v4 M9 10V4h2v6 M11 10V3h2v7 M13 10V4h2v7l3-2 1 2-4 5v5",
  legs: "M7 3h10l1 18h-4l-2-11-2 11H6z",
  boots: "M7 3h6v9l6 3v5H5v-5l2-1z M5 17h14",
  ring: "M12 21a6 6 0 1 0 0-12 6 6 0 0 0 0 12z M9 6l3-3 3 3-3 3z",
  sword: "M20 4l-9.5 9.5 M14 4h6v6 M5 15l4 4 M3 21l3-3",
  bow: "M6 3c9 2 13 8 15 15 M6 3l15 15 M3 12l9-9 M12 21l9-9",
  staff: "M5 20L15 10 M15 4a5 5 0 1 1 0 10 5 5 0 0 1 0-10z M15 2v2 M20 9h2",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z M12 7v10",
  flask: "M9 3h6 M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3 M7.5 15h9",
  food: "M3 13h18a9 6 0 0 1-18 0z M7 10c1.5-3 8.5-3 10 0",
  arrow: "M4 20L18 6 M13 6h5v5 M4 20l1-4 3 3z",
  backpack: "M6 9a6 6 0 0 1 12 0v11H6z M9 5V3h6v2 M9 13h6v4H9z",
  glider: "M2 14l10-8 10 8 M12 6v13 M8 19h8",
  stone: "M4 16l3-8 6-3 6 4 1 7-6 4H8z M9 9l3 4 4-2",
  block: "M12 3l8 4.5v9L12 21l-8-4.5v-9z M12 12l8-4.5 M12 12v9 M12 12L4 7.5",
  core: "M12 3l7 5-7 13L5 8z M5 8h14 M9.5 8L12 21 14.5 8",
  rune: "M6 3h12v18H6z M11 7v10 M11 12l4-4 M11 12l4 4",
  gel: "M12 3c4 5 6 8 6 11a6 6 0 0 1-12 0c0-3 2-6 6-11z M9 15a3 3 0 0 0 3 3",
  axe: "M6 21L15 12 M13 3c4 0 8 3 8 8l-5 1-4-4z",
  music: "M9 18V5l11-2v13 M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z M20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
  rod: "M4 20L19 5 M19 5v9 M19 14a2 2 0 1 1-4 0",
  coin: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v10 M9 9.5h4.5a1.5 1.5 0 0 1 0 3h-3a1.5 1.5 0 0 0 0 3H15",
};
const SLOT_ICON = { Armour_Head: "helmet", Armour_UpperBody: "chest", Armour_Arms: "gloves", Armour_LowerBody: "legs",
  Armour_Feet: "boots", Armour_Ring: "ring", MeleeWeapon: "sword", RangeWeapon: "bow", MidRangeWeapon: "staff",
  Shield: "shield", Spell: "rune", Arrow: "arrow", Backpack: "backpack", Glider: "glider", Tool: "axe",
  Consumable: "flask", TerrainMaterial: "stone", BuildTool: "block", FishingBait: "food" };
const CAT_ICON = { Materials: "stone", BuildTools: "block", Equipment: "shield", Weapons: "sword", Consumables: "flask",
  Ammunition: "arrow", Collectibles: "core", ColorPalette: "gel", WeaponGem: "core", Tools: "axe", AnimalFood: "food",
  Instrument: "music", FishingRod: "rod", Currency: "coin" };

const S = {
  items: [], byId: new Map(), perks: {}, texts: {}, languages: [],
  lang: "Pl_Pl", setting: null, gameLang: null,
  q: "", cat: null, sub: null, open: null, subOrder: {}, rar: null, sort: "rarity",
  sel: null, filtered: [], conn: "off", busy: false, creator: true, seq: -1,
};
// Identyfikatory tekstów gry (niezależne od języka): „Poziom przedmiotu” i „Czas we Mgle” (różowy pasek)
const LVL_LABEL = 2298204525;
const FOG_LABELS = new Set([871997548, 1542051209, 3139571057, 4187833821, 1125830499, 317193095]);
let NUM = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 2 });
let COLL = new Intl.Collator("pl");

// ---------------------------------------------------------------- API
async function api(path, body) {
  const opt = { headers: { "X-TMI-Token": TOKEN } };
  if (body !== undefined) {
    opt.method = "POST";
    opt.headers["Content-Type"] = "application/json";
    opt.body = JSON.stringify(body);
  }
  const r = await fetch(path, opt);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------- tekst
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fold = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");
const nameOf = (it) => it.names[S.lang] || it.names.En_Us || it.debug;
const text = (id) => (id == null ? "" : S.texts[String(id)] || "");
const label = (id) => { const t = text(id).replace(/<[^>]+>/g, "").trim(); return t.charAt(0).toUpperCase() + t.slice(1); };

function fmtDur(ms) {
  const a = Math.abs(ms);
  const H = T("uH"), M = T("uMin"), S_ = T("uS");
  if (a >= 3600000) { const h = Math.floor(a / 3600000), m = Math.round((a % 3600000) / 60000); return m ? `${h} ${H} ${m} ${M}` : `${h} ${H}`; }
  if (a >= 60000) { const m = Math.floor(a / 60000), s = Math.round((a % 60000) / 1000); return s ? `${m} ${M} ${s} ${S_}` : `${m} ${M}`; }
  return `${NUM.format(Math.round(a / 100) / 10)} ${S_}`;
}
function fmtVal(fmt, v, signed) {
  const sign = v < 0 ? "−" : signed && v > 0 ? "+" : "";
  const a = Math.abs(v);
  switch (fmt) {
    case "Percentage": return `${sign}${NUM.format(a)}%`;
    case "Duration": case "DurationMilliseconds": return `${sign}${fmtDur(a)}`;
    case "Float": return `${sign}${NUM.format(a / 100)} ${T("uM")}`;
    default: return `${sign}${NUM.format(a)}`;
  }
}
// Teksty gry: <b>, <i>, <img gemeffect_…>, <npc>, %k = kolejne wartości
function rich(raw, values) {
  let k = 0;
  let s = esc(raw || "").replace(/%k/g, () => (k < values.length ? `<b>${esc(values[k++])}</b>` : "…"));
  s = s.replace(/&lt;(\/?)(b|i)&gt;/g, "<$1$2>")
       .replace(/&lt;img [^&]*&gt;\s*/g, "◆ ")
       .replace(/&lt;\/?[a-z_]+[^&]*&gt;/gi, "");
  return s.trim();
}

// ---------------------------------------------------------------- ikony
function symbolFor(it) {
  return ICONS[SLOT_ICON[it.slot] || CAT_ICON[it.cat] || "core"];
}
function iconHtml(it, size) {
  const c = R_COLOR[it.rarity] || "var(--r-common)";
  if (it.icon) return `<img src="/${esc(it.icon)}" alt="" loading="lazy" draggable="false">`;
  const eye = /^Icon_(Eye|Hair)Color_(.+)$/.exec(it.debug);
  if (eye) {
    const col = EYE[eye[2].toLowerCase()] || "#888";
    return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" fill="${col}" stroke="#ddd" stroke-width=".8"/><circle cx="12" cy="12" r="3" fill="#000" opacity=".55"/></svg>`;
  }
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${symbolFor(it)}"/></svg>`;
}
function typeLine(it) {
  const t = it.sub && S.subOrder[it.cat] && it.cat !== "Equipment" ? TM("subcat", it.sub) :
    it.slot ? TM("slot", it.slot) : TM("cat", it.cat);
  return `${TM("rar", it.rarity)} · ${t}`;
}
function lvlText(it) {
  if (!it.lvl) return "";
  const [a, b] = it.lvl;
  return a === b ? String(a) : `${a}–${b}`;
}

// ---------------------------------------------------------------- filtry
function matches(it, qf) {
  if (!qf) return true;
  if (String(it.id) === S.q.trim()) return true;
  return it._fold.includes(qf);
}
function buildFold() {
  for (const it of S.items) {
    it._name = nameOf(it);
    it._fold = fold(`${it._name} ${it.names.En_Us || ""} ${it.debug}`);
  }
}
function applyFilters() {
  const qf = fold(S.q.trim());
  const base = S.items.filter((it) => matches(it, qf) && (!S.rar || it.rarity === S.rar));
  const counts = new Map();
  for (const it of base) {
    counts.set(it.cat, (counts.get(it.cat) || 0) + 1);
    if (it.sub) { const k = `${it.cat}/${it.sub}`; counts.set(k, (counts.get(k) || 0) + 1); }
  }
  S.filtered = base.filter((it) => (!S.cat || it.cat === S.cat) && (!S.sub || it.sub === S.sub));
  const byName = (a, b) => COLL.compare(a._name, b._name);
  if (S.sort === "name") S.filtered.sort(byName);
  else if (S.sort === "level") S.filtered.sort((a, b) => ((b.lvl ? b.lvl[1] : -1) - (a.lvl ? a.lvl[1] : -1)) || byName(a, b));
  else S.filtered.sort((a, b) => ((R_ORDER[a.rarity] ?? 9) - (R_ORDER[b.rarity] ?? 9)) || byName(a, b));
  renderCats(counts, base.length);
  renderGrid();
}

// ---------------------------------------------------------------- widoki
function renderCats(counts, total) {
  const all = new Map();
  for (const it of S.items) all.set(it.cat, (all.get(it.cat) || 0) + 1);
  const cats = [...all.keys()].sort((a, b) => all.get(b) - all.get(a));
  let h = `<button type="button" class="cat${S.cat ? "" : " sel"}" data-cat=""><span>${esc(T("all"))}</span><span class="n">${total}</span></button>`;
  for (const c of cats) {
    const n = counts.get(c) || 0;
    const subs = subsOf(c);
    const open = subs.length > 0 && S.open === c;
    const arrow = subs.length ? `<span class="arr" aria-hidden="true">${open ? "▾" : "▸"}</span>` : `<span class="arr"></span>`;
    h += `<button type="button" class="cat${S.cat === c && !S.sub ? " sel" : ""}${S.cat === c && S.sub ? " parent" : ""}${n ? "" : " zero"}" data-cat="${esc(c)}"` +
      `${subs.length ? ` aria-expanded="${open}"` : ""}>${arrow}<span class="nm">${esc(TM("cat", c))}</span><span class="n">${n}</span></button>`;
    if (open) {
      h += `<div class="subs">`;
      for (const s of subs) {
        const m = counts.get(`${c}/${s}`) || 0;
        h += `<button type="button" class="cat sub${S.sub === s && S.cat === c ? " sel" : ""}${m ? "" : " zero"}" data-cat="${esc(c)}" data-sub="${esc(s)}">` +
          `<span class="nm">${esc(TM("subcat", s))}</span><span class="n">${m}</span></button>`;
      }
      h += `</div>`;
    }
  }
  $("cats").innerHTML = h;
  $("catTitle").textContent = S.cat ? TM("cat", S.cat) + (S.sub ? ` › ${TM("subcat", S.sub)}` : "") : T("allItems");
}
// Podkategorie danej kategorii (kolejność z tmi_categories.ORDER), tylko te, które mają przedmioty
function subsOf(cat) {
  if (!S._subs) {
    S._subs = new Map();
    const have = new Set(S.items.filter((it) => it.sub).map((it) => `${it.cat}/${it.sub}`));
    for (const [c, list] of Object.entries(S.subOrder || {})) S._subs.set(c, list.filter((s) => have.has(`${c}/${s}`)));
  }
  const l = S._subs.get(cat) || [];
  return l.length > 1 ? l : [];
}
function renderRarity() {
  let h = `<button type="button" class="chip${S.rar ? "" : " sel"}" data-rar="">${esc(T("all"))}</button>`;
  for (const [k, c] of [...RARITY].reverse()) {
    h += `<button type="button" class="chip${S.rar === k ? " sel" : ""}" data-rar="${k}"><span class="d" style="background:${c}"></span>${esc(TM("rar", k))}</button>`;
  }
  $("rar").innerHTML = h;
}
function renderGrid() {
  const parts = [];
  for (const it of S.filtered) {
    const c = R_COLOR[it.rarity] || "var(--r-common)";
    const lv = it.lvl && it.lvl[0] === it.lvl[1] ? `<span class="lv">${it.lvl[0]}</span>` : "";
    const st = it.stack > 1 ? `<span class="stk">${it.stack}</span>` : "";
    parts.push(`<button type="button" class="tile${it.id === S.sel ? " sel" : ""}" data-id="${it.id}" role="option" aria-label="${esc(it._name)}">` +
      `<div class="ibox" style="--rc:${c}">${iconHtml(it, 44)}${lv}${st}</div>` +
      `<span class="tname">${esc(it._name)}</span></button>`);
  }
  $("grid").innerHTML = parts.join("");
  $("empty").hidden = S.filtered.length > 0;
  const n = S.filtered.length;
  $("count").textContent = T("count")(n);
}

function statRows(stats, withFog) {
  return (stats || []).map(([lid, fmt, v, signed]) => {
    const l = label(lid) || "?";
    const fog = withFog && FOG_LABELS.has(lid);
    const isLvl = lid === LVL_LABEL;
    const cls = isLvl ? "lvl" : v < 0 ? "neg" : fmt === "Percentage" ? "pct" : "";
    return `<div class="stat${fog ? " fog" : ""}"><span class="l">${esc(l)}</span><span class="v ${cls}">${esc(fmtVal(fmt, v, signed && !isLvl))}</span></div>`;
  }).join("");
}
function statValues(stats) {
  return (stats || []).map(([, fmt, v, signed]) => fmtVal(fmt, v, signed));
}
function perksHtml(it) {
  if (!it.perks || !it.perks.length) return "";
  const order = [], count = new Map();
  for (const g of it.perks) { if (!count.has(g)) order.push(g); count.set(g, (count.get(g) || 0) + 1); }
  const rows = order.map((g) => {
    const p = S.perks[g] || {};
    const name = label(p.name) || p.debug || "?";
    const vals = statValues(p.stats);
    let d = "", side = "";
    if (p.desc && text(p.desc)) d = rich(text(p.desc), vals);
    else if (p.stats && p.stats.length === 1 && fold(label(p.stats[0][0])) === fold(name)) side = vals[0];
    else if (p.stats && p.stats.length) d = p.stats.map(([lid, fmt, v, s]) => `${esc(label(lid) || "")} <b>${esc(fmtVal(fmt, v, s))}</b>`).join(" · ");
    const x = (side ? `<b class="pv">${esc(side)}</b>` : "") + (count.get(g) > 1 ? ` <span class="x">×${count.get(g)}</span>` : "");
    return `<div class="perk"><div class="perk-n"><span>${esc(name)}</span><span>${x}</span></div>${d ? `<div class="perk-d">${d}</div>` : ""}</div>`;
  });
  return `<div class="sec-h">${esc(T("perks"))}</div><div class="perks">${rows.join("")}</div>`;
}
function tagsHtml(it) {
  const t = [];
  if (it.armor) {
    const k = Object.keys(it.armor).map((a) => TM("armor", a));
    if (k.length) t.push(`<span class="tag">${esc(T("tArmor"))}: ${esc(k.join(" · "))}</span>`);
  }
  if (it.dmg) {
    const dist = it.dmg.dist || {};
    const d = Object.keys(dist).filter((k) => EN.dmg[k]).map((k) => TM("dmg", k));
    const m = Object.keys(dist).filter((k) => EN.mine[k]).map((k) => `${TM("mine", k)} ${dist[k]}`);
    if (d.length) t.push(`<span class="tag">${esc(T("tDmg"))}: ${esc(d.join(" · "))}</span>`);
    if (m.length) t.push(`<span class="tag">${esc(T("tMine"))}: ${esc(m.join(" · "))}</span>`);
  }
  if (it.cls) t.push(`<span class="tag">${esc(T("tCls"))}: ${esc(TM("cls", it.cls))}</span>`);
  if (it.comfort) t.push(`<span class="tag">${esc(T("tComfort"))} +${esc(it.comfort)}</span>`);
  if (it.pide) {
    t.push(S.creator ? `<span class="tag ok">${esc(T("pideOk"))}</span>` : `<span class="tag warn">${esc(T("pideWarn"))}</span>`);
  }
  return t.length ? `<div class="tags">${t.join("")}</div>` : "";
}
function renderCard() {
  const card = $("card");
  const it = S.byId.get(S.sel);
  if (!it) {
    card.className = "card none";
    card.innerHTML = `${esc(T("pick"))}<br><span style="font-size:14px">${esc(T("pick2"))}</span>`;
    $("add").disabled = true;
    return;
  }
  card.className = "card";
  const c = R_COLOR[it.rarity] || "var(--r-common)";
  const lv = lvlText(it);
  const diamond = lv ? `<div class="diamond"><div><small>${esc(T("lvl"))}</small><b class="${lv.length > 3 ? "range" : ""}">${esc(lv)}</b></div></div>` : "";
  const desc = it.desc && text(it.desc) ? `<p class="desc">${rich(text(it.desc), statValues(it.stats))}</p>` : "";
  const lore = it.lore && text(it.lore) ? `<p class="desc">${rich(text(it.lore), [])}</p>` : "";
  const stats = (it.stats && it.stats.length) || (it.buffs && it.buffs.length)
    ? `<div class="stats">${statRows(it.stats, true)}${statRows(it.buffs, true)}</div>` : "";
  card.style.setProperty("--rc", c);
  // Wybór rzadkości – tylko gdy gra ją losuje (rgen); TMI3 przekazuje wybraną rzadkość grze
  const rpick = it.rgen ? `<div class="rpick" role="radiogroup" aria-label="${esc(T("rarH"))}"><span class="rpick-h">${esc(T("rarH"))}</span>` +
    [...it.rgen].reverse().map((r) => `<button type="button" class="rchip${r === it.rarity ? " sel" : ""}" role="radio" aria-checked="${r === it.rarity}" data-r="${esc(r)}" style="--rc:${R_COLOR[r]}">` +
      `<span class="dot"></span>${esc(TM("rar", r))}</button>`).join("") + `</div>` : "";
  card.innerHTML =
    `<div class="c-head"><div style="display:flex;flex-direction:column;gap:4px">` +
      `<h2 class="c-name" style="color:${c}">${esc(it._name)}</h2><span class="c-type">${esc(typeLine(it))}${it.stack > 1 ? ` · ${esc(T("stack"))} ${it.stack}` : ""}</span></div>${diamond}</div>` +
    rpick +
    `<div class="c-icon" style="--rc:${c}">${iconHtml(it, 96)}</div>` +
    stats + perksHtml(it) + desc + lore + tagsHtml(it) +
    `<div class="ids">ID ${it.id} · ${esc(it.debug)}</div>`;
  const q = $("qty");
  if (+q.value > it.stack) q.value = it.stack;
  updateAdd();
}
function updateAdd() {
  const b = $("add");
  b.disabled = !S.byId.get(S.sel) || S.busy;
  b.classList.toggle("busy", S.busy);
  for (const id of ["rescue", "diag", "reconnect"]) $(id).disabled = S.busy;
}

// ---------------------------------------------------------------- podpowiedź
// Podpowiedź: po 0,7 s nad przedmiotem albo od razu prawym przyciskiem; znika, gdy kursor opuści przedmiot.
const TIP_DELAY = 700;
let tipTimer = 0, tipFor = null, hoverTile = null, quietTile = null;
function showTip(tile) {
  const it = S.byId.get(+tile.dataset.id);
  if (!it) return;
  const tip = $("tip");
  const c = R_COLOR[it.rarity] || "var(--r-common)";
  const stats = (it.stats || []).slice(0, 4);
  const desc = it.desc && text(it.desc) ? `<p class="desc">${rich(text(it.desc), statValues(it.stats))}</p>` : "";
  tip.innerHTML =
    `<div class="tip-h"><div class="ibox" style="--rc:${c}">${iconHtml(it, 36)}</div><div>` +
    `<div class="tip-n" style="color:${c}">${esc(it._name)}</div><div class="tip-t">${esc(typeLine(it))}${it.stack > 1 ? ` · ${esc(T("stack"))} ${it.stack}` : ""}${it.lvl ? ` · ${esc(T("lvlShort"))} ${lvlText(it)}` : ""}</div></div></div>` +
    (stats.length ? `<div>${statRows(stats, true)}</div>` : "") + desc +
    `<div class="tip-f"><span>ID ${it.id}</span><span>${esc(T("tipFoot"))}</span></div>`;
  tip.hidden = false;
  const r = tile.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
  let x = r.right + 10;
  if (x + w > innerWidth - 8) x = r.left - w - 10;
  let y = Math.min(Math.max(8, r.top), innerHeight - h - 8);
  tip.style.left = `${Math.max(8, x)}px`;
  tip.style.top = `${y}px`;
}
function hideTip() { clearTimeout(tipTimer); tipFor = null; $("tip").hidden = true; }
function onHover(t) {
  if (t === hoverTile) return;
  hoverTile = t;
  if (t !== quietTile) quietTile = null;           // po kliknięciu: cisza, dopóki kursor nie zjedzie
  hideTip();
  if (t && !quietTile) tipTimer = setTimeout(() => { if (hoverTile === t) { showTip(t); tipFor = t; } }, TIP_DELAY);
}

// ---------------------------------------------------------------- akcje
function select(id, scroll) {
  S.sel = id;
  for (const el of $("grid").querySelectorAll(".tile.sel")) el.classList.remove("sel");
  const el = $("grid").querySelector(`.tile[data-id="${id}"]`);
  if (el) { el.classList.add("sel"); if (scroll) el.scrollIntoView({ block: "nearest" }); }
  renderCard();
}
// Rzadkość wybrana przez użytkownika (dla przedmiotów z rgen) – zapamiętana w przeglądarce okna
function loadRarityPicks() {
  let picks = {};
  try { picks = JSON.parse(localStorage.getItem("tmi_rar") || "{}"); } catch (e) { picks = {}; }
  for (const it of S.items) {
    if (it.rgen && picks[it.id] && it.rgen.includes(picks[it.id])) it.rarity = picks[it.id];
  }
}
function setRarity(it, r) {
  if (!it.rgen || !it.rgen.includes(r) || it.rarity === r) return;
  it.rarity = r;
  try {
    const picks = JSON.parse(localStorage.getItem("tmi_rar") || "{}");
    picks[it.id] = r;
    localStorage.setItem("tmi_rar", JSON.stringify(picks));
  } catch (e) { /* bez pamięci – wybór tylko do zamknięcia okna */ }
  const g = $("grid"), top = g.scrollTop;
  if (S.rar || S.sort === "rarity") applyFilters(); else renderGrid();   // ramka, filtr i kolejność wg nowej rzadkości
  g.scrollTop = top;
  renderCard();
}
async function addSelected() {
  const it = S.byId.get(S.sel);
  if (!it || S.busy) return;
  let qty = Math.round(+$("qty").value || 1);
  qty = Math.max(1, Math.min(qty, 9999));
  $("qty").value = qty;
  await post("/api/add", it.rgen ? { id: it.id, qty, rarity: it.rarity } : { id: it.id, qty });
}
async function post(path, body) {
  try {
    const r = await api(path, body || {});
    applyState(r.state);
  } catch (e) {
    setStatus({ key: "contact", args: { d: e.message }, error: true });
  }
}
function statusText(st) {
  if (!st || !st.key) return (st && st.text) || "";
  const a = Object.assign({}, st.args || {});
  if (a.id !== undefined) { const it = S.byId.get(a.id); a.name = it ? it._name : String(a.id); }
  if (st.key === "connected") {
    a.mode = TS(a.mode === "old" ? "modeOld" : "modeGame");
    const l = S.languages.find((x) => x.key === a.lang);
    a.lang = l ? l.label : TS("langUnknown");
  }
  let txt = TS(st.key, a);
  if (st.key === "connected") {
    if (a.unsup) txt += " " + TS("unsupOld");
    else if (a.newBuild) txt += " " + TS("newBuild", a);
  }
  if (st.key === "added") {
    if (a.rar) txt += ` (${TM("rar", a.rar)})`;
    if (a.rarLost) txt += " " + TS("rarLost");
    if (a.ready) txt += " " + TS("ready");
    if (a.noroom) txt += " " + TS("noroom", { n: a.noroom });
    if (a.hint) txt += " " + TS("moveHint");
    if (a.extra) txt += ` (${a.extra})`;
  }
  if (st.key === "rescueDone" && a.left) txt += " " + TS("rescueLeft", { n: a.left });
  return txt;
}
function setStatus(st) {
  S.lastStatus = st;
  const el = $("status");
  el.textContent = statusText(st);
  el.className = "status" + (st.error ? " err" : S.busy ? " work" : "");
  // link do strony wydań przy nowej / nieobsługiwanej wersji gry
  const a = st.args || {};
  if (S.releasesUrl && /^https:\/\//.test(S.releasesUrl) && !S.releasesUrl.includes("[") &&
      (st.key === "unsupported" || (st.key === "connected" && (a.unsup || a.newBuild)))) {
    const link = document.createElement("a");
    link.href = S.releasesUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "stlink";
    link.textContent = TS("updLink");
    el.append(" ", link);
  }
}
function renderConn() {
  $("conn").className = `conn ${S.conn}`;
  $("connTxt").textContent = S.conn === "on" ? `${T("on")} · ${T(S.connMode === "old" ? "modeOld" : "modeGame")}` :
    S.conn === "connecting" ? T("connecting") : S.conn === "unsupported" ? T("unsup") : T("off");
}
function applyState(st) {
  S.busy = st.busy;
  S.conn = st.conn;
  S.connMode = st.connMode;
  const creator = st.creator || st.conn !== "on";
  const creatorChanged = creator !== S.creator;
  S.creator = creator;
  S.seq = st.seq;
  if (st.releasesUrl) S.releasesUrl = st.releasesUrl;
  if (st.appVersion && st.appVersion !== S.appVersion) { S.appVersion = st.appVersion; renderLegal(); }
  setStatus(st.status);
  if (creatorChanged) renderCard();
  renderConn();
  S.gameLang = st.gameLang;
  const want = S.setting || S.gameLang || "Pl_Pl";
  if (want !== S.lang) setLang(want);
  updateAdd();
}
// Język: napisy okna + nazwy/teksty przedmiotów
function renderLegal() {
  const el = $("legal");
  if (el) el.textContent = (S.appVersion ? `v${S.appVersion} · ` : "") + T("legal");
}
function applyI18n() {
  document.documentElement.lang = (LOCALE[S.lang] || "en").slice(0, 2);
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = T(el.dataset.i18n);
  $("q").placeholder = T("search");
  $("q").title = T("searchTip");
  $("conn").title = T("connTip");
  const auto = $("lang").querySelector('option[value=""]');
  if (auto) auto.textContent = T("auto");
  renderLegal();
}
function setLang(lang) {
  S.lang = lang;
  L = I18N[lang] || EN;
  const loc = LOCALE[lang] || "en-US";
  NUM = new Intl.NumberFormat(loc, { maximumFractionDigits: 2 });
  COLL = new Intl.Collator(loc);
  applyI18n();
  renderRarity();
  renderConn();
  return loadTexts();
}
async function loadTexts() {
  try { S.texts = await api(`/api/texts?lang=${encodeURIComponent(S.lang)}`); } catch (e) { S.texts = {}; }
  buildFold();
  applyFilters();
  renderCard();
}
async function poll() {
  try { applyState(await api("/api/state")); }
  catch (e) { setStatus({ key: "noResp", error: true }); }
  setTimeout(poll, S.busy || S.conn === "connecting" ? 300 : 900);
}

// ---------------------------------------------------------------- start
function bind() {
  let qTimer = 0;
  $("q").addEventListener("input", (e) => { clearTimeout(qTimer); qTimer = setTimeout(() => { S.q = e.target.value; applyFilters(); }, 120); });
  $("q").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && S.filtered.length) { select(S.filtered[0].id, true); $("grid").focus(); }
    if (e.key === "ArrowDown" && S.filtered.length) { e.preventDefault(); if (!S.sel) select(S.filtered[0].id, true); $("grid").focus(); }
  });
  $("cats").addEventListener("click", (e) => {
    const b = e.target.closest(".cat"); if (!b) return;
    const cat = b.dataset.cat || null, sub = b.dataset.sub || null;
    if (sub) { S.cat = cat; S.sub = sub; }
    else if (cat && S.cat === cat && !S.sub && S.open === cat) { S.open = null; }        // 2. klik zwija
    else { S.cat = cat; S.sub = null; S.open = cat && subsOf(cat).length ? cat : null; }
    try { localStorage.setItem("tmi_cat", JSON.stringify([S.cat, S.sub])); } catch (e2) { /* brak pamięci */ }
    applyFilters(); $("grid").scrollTop = 0;
  });
  $("rar").addEventListener("click", (e) => {
    const b = e.target.closest(".chip"); if (!b) return;
    S.rar = b.dataset.rar || null; renderRarity(); applyFilters(); $("grid").scrollTop = 0;
  });
  $("sort").addEventListener("change", (e) => { S.sort = e.target.value; applyFilters(); });
  const grid = $("grid");
  grid.addEventListener("click", (e) => { const t = e.target.closest(".tile"); if (t) { hideTip(); quietTile = t; select(+t.dataset.id); } });
  grid.addEventListener("dblclick", (e) => { const t = e.target.closest(".tile"); if (t) { hideTip(); quietTile = t; select(+t.dataset.id); addSelected(); } });
  grid.addEventListener("contextmenu", (e) => {        // PPM = podpowiedź od razu (drugi raz – schowaj)
    const t = e.target.closest(".tile");
    if (!t) return;
    e.preventDefault();
    if (tipFor === t && !$("tip").hidden) { hideTip(); quietTile = t; return; }
    hideTip(); hoverTile = t; quietTile = null; showTip(t); tipFor = t;
  });
  // Każdy ruch myszy: czy kursor jest jeszcze nad tym samym przedmiotem? (pewniejsze niż samo mouseleave)
  document.addEventListener("mousemove", (e) => {
    const t = e.target.closest ? e.target.closest("#grid .tile") : null;
    onHover(t);
  }, { passive: true });
  document.documentElement.addEventListener("mouseleave", () => onHover(null));
  document.addEventListener("mouseout", (e) => { if (!e.relatedTarget) onHover(null); });   // kursor poza oknem
  window.addEventListener("blur", () => onHover(null));
  grid.addEventListener("scroll", hideTip, { passive: true });
  document.addEventListener("wheel", hideTip, { passive: true });
  document.addEventListener("keydown", (e) => { if (!["Shift", "Control", "Alt"].includes(e.key)) hideTip(); });
  grid.addEventListener("keydown", (e) => {
    const i = S.filtered.findIndex((x) => x.id === S.sel);
    const cols = Math.max(1, getComputedStyle(grid).gridTemplateColumns.split(" ").length);
    const go = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: cols, ArrowUp: -cols }[e.key];
    if (go !== undefined) {
      e.preventDefault(); hideTip();
      const n = i < 0 ? 0 : Math.max(0, Math.min(S.filtered.length - 1, i + go));
      if (S.filtered[n]) select(S.filtered[n].id, true);
    } else if (e.key === "Enter") { e.preventDefault(); addSelected(); }
  });
  $("add").addEventListener("click", addSelected);
  $("card").addEventListener("click", (e) => {
    const b = e.target.closest(".rchip");
    if (b) setRarity(S.byId.get(S.sel), b.dataset.r);
  });
  $("qty").addEventListener("keydown", (e) => { if (e.key === "Enter") addSelected(); });
  $("one").addEventListener("click", () => { $("qty").value = 1; });
  $("full").addEventListener("click", () => { const it = S.byId.get(S.sel); if (it) $("qty").value = it.stack; });
  $("rescue").addEventListener("click", () => post("/api/rescue"));
  $("diag").addEventListener("click", () => post("/api/diag"));
  $("reconnect").addEventListener("click", () => post("/api/connect"));
  $("conn").addEventListener("click", () => post("/api/connect"));
  $("lang").addEventListener("change", (e) => {
    S.setting = e.target.value || null;
    api("/api/settings", { language: S.setting }).catch(() => {});
    setLang(S.setting || S.gameLang || "Pl_Pl").then(() => setStatus(S.lastStatus || {}));
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey && e.key.toLowerCase() === "f") || (e.key === "/" && document.activeElement.tagName !== "INPUT")) {
      e.preventDefault(); $("q").focus(); $("q").select();
    }
    if (e.key === "Escape" && document.activeElement === $("q")) { $("q").value = ""; S.q = ""; applyFilters(); }
  });
}

async function start() {
  bind();
  renderRarity();
  renderCard();
  try {
    const [data, st] = await Promise.all([api("/api/data"), api("/api/state")]);
    S.items = data.items;
    S.perks = data.perks;
    S.languages = data.languages;
    S.subOrder = data.subOrder || {};
    S._subs = null;
    for (const it of S.items) S.byId.set(it.id, it);
    loadRarityPicks();
    try {                                              // ostatnio wybrana kategoria / podkategoria
      const [c, sb] = JSON.parse(localStorage.getItem("tmi_cat") || "[]");
      if (c && S.items.some((it) => it.cat === c)) {
        S.cat = c; S.open = subsOf(c).length ? c : null;
        if (sb && subsOf(c).includes(sb)) S.sub = sb;
      }
    } catch (e2) { /* brak pamięci przeglądarki – zaczynamy od „Wszystkie” */ }
    S.setting = st.language || null;
    S.gameLang = st.gameLang;
    $("lang").innerHTML = `<option value=""></option>` +
      S.languages.map((l) => `<option value="${esc(l.key)}">${esc(l.label)}</option>`).join("");
    $("lang").value = S.setting || "";
    await setLang(S.setting || S.gameLang || "Pl_Pl");
    applyState(st);
    if (!S.items.length) setStatus({ key: "noDb", error: true });
  } catch (e) {
    setStatus({ key: "noData", args: { d: e.message }, error: true });
  }
  $("q").focus();
  poll();
}
start();
