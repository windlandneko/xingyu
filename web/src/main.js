import "@shoelace-style/shoelace/dist/themes/light.css";
import "@shoelace-style/shoelace/dist/themes/dark.css";
import "@shoelace-style/shoelace/dist/components/button/button.js";
import "@shoelace-style/shoelace/dist/components/drawer/drawer.js";
import "@shoelace-style/shoelace/dist/components/range/range.js";
import "@shoelace-style/shoelace/dist/components/switch/switch.js";
import '@shoelace-style/shoelace/dist/components/dropdown/dropdown.js'
import '@shoelace-style/shoelace/dist/components/menu/menu.js'
import '@shoelace-style/shoelace/dist/components/menu-item/menu-item.js'
import '@shoelace-style/shoelace/dist/components/divider/divider.js'
import { createIcons, ArrowUp, Copy, Download, CircleQuestionMark, List, Search, X } from "lucide";
import { joinWords, toPieces } from "./convert.js";
import { fontTokens } from "./font-tokens.js";
import { PRESETS } from "./presets.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => s.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);
const hex = (n) => n.toString(16).toUpperCase();
const chr = (h) => String.fromCodePoint(parseInt(h, 16));
const store = {
  get(k, d) {
    try {
      return JSON.parse(localStorage.getItem("xingyu." + k)) ?? d;
    } catch {
      return d;
    }
  },
  set(k, v) {
    try {
      localStorage.setItem("xingyu." + k, JSON.stringify(v));
    } catch {}
  },
};
let toastTimer;
function toast(msg) {
  $("toast").textContent = msg;
  $("toast").classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").classList.remove("on"), 1600);
}
const copy = (text, what) =>
  navigator.clipboard.writeText(text).then(
    () => toast(`已复制${what}`),
    () => toast("复制失败"),
  );
createIcons({
  icons: { ArrowUp, Copy, Download, CircleQuestionMark, List, Search, X },
  attrs: { "aria-hidden": "true" },
});
const dark = matchMedia("(prefers-color-scheme: dark)");
const theme = () => document.documentElement.classList.toggle("sl-theme-dark", dark.matches);
dark.addEventListener("change", theme);
theme();
// phones and narrow windows: the entry card opens as a bottom sheet instead of a column
const narrow = matchMedia("(max-width: 860px)");
// a tap looks a character up (there is no right click); a mouse click still inserts it
let touch = false;
addEventListener("pointerdown", (ev) => (touch = ev.pointerType !== "mouse"), true);

for (const trigger of document.querySelectorAll(".help-trigger")) {
  const panel = $(trigger.getAttribute("popovertarget"));
  let pinned = false;
  const show = () => {
    panel.showPopover();
    const rect = trigger.getBoundingClientRect();
    panel.style.left =
      Math.max(16, Math.min(rect.left, innerWidth - panel.offsetWidth - 16)) + "px";
    panel.style.top =
      Math.max(16, Math.min(rect.bottom + 8, innerHeight - panel.offsetHeight - 16)) + "px";
  };
  const hide = () =>
    setTimeout(() => {
      if (!pinned && !trigger.matches(":hover") && !panel.matches(":hover")) panel.hidePopover();
    }, 100);
  trigger.addEventListener("pointerenter", (ev) => {
    if (ev.pointerType === "mouse") show();
  });
  trigger.addEventListener("pointerleave", hide);
  panel.addEventListener("pointerleave", hide);
  trigger.addEventListener("click", (ev) => {
    ev.preventDefault();
    pinned = !pinned;
    if (pinned) show();
    else panel.hidePopover();
  });
  panel.addEventListener("toggle", () => {
    const open = panel.matches(":popover-open");
    trigger.setAttribute("aria-expanded", String(open));
    if (!open) pinned = false;
  });
}

// ---------- data: the font and its table ----------

const [res, fontRes] = await Promise.all([
  fetch(import.meta.env.BASE_URL + "xingyu.json"),
  fetch(import.meta.env.BASE_URL + "Xingyu-VF.woff2"),
]);
const [data, buffer] = await Promise.all([res.json(), fontRes.arrayBuffer()]);
const face = new FontFace("Xingyu", buffer, { weight: "100 900", display: "block" });
document.fonts.add(face);
await face.load();
const entries = data.entries.map((e) => ({ ...e, char: chr(e.cp) }));
const byCp = new Map(entries.map((e) => [e.cp, e]));
const byToken = new Map(
  [...(await fontTokens(buffer))].map(([token, cp]) => [token, byCp.get(cp)]).filter(([, e]) => e),
);
const ed = { ...data, entries, byCp, byToken };

$("brand").textContent = chr("F7603");
const lookup = (token) => ed.byToken.get(token)?.char;
for (const el of document.querySelectorAll("[data-word]")) el.textContent = lookup(el.dataset.word);

// ---------- save slots ----------

const fullUnlock = $('full-unlock')
const saves = new Map(store.get('saves', []).filter(save => /^slot-[1-7]$/.test(save.id)).map(save => [save.id, save]))
let activeSlot = store.get('save-slot', 'slot-1') || 'slot-1'
const available = e => e && (!e.fan || fullUnlock.checked)
const unlocked = e => available(e) && (fullUnlock.checked || e.note !== undefined)
const annotation = e => e?.note || (fullUnlock.checked ? e?.name ?? '' : '')
const mark = (cp, fallback) => unlocked(ed.byCp.get(cp)) ? chr(cp) : fallback

async function readSave(file) {
  let text = (await file.text()).trim()
  if (!text.startsWith('{')) {
    const encode = text => new TextEncoder().encode(text)
    const key = await crypto.subtle.importKey(
      'raw', encode('terrible_artwork'), 'AES-CBC', false, ['decrypt'],
    )
    const bytes = Uint8Array.from(atob(text), ch => ch.charCodeAt(0))
    const plain = await crypto.subtle.decrypt(
      { name: 'AES-CBC', iv: encode("wedidn'tplaytest") }, key, bytes,
    )
    text = new TextDecoder().decode(plain)
  }
  const { dict } = JSON.parse(text)
  if (!dict || typeof dict !== 'object' || !Object.values(dict).every(note => typeof note === 'string')) {
    throw new Error('存档中没有字典记录')
  }
  return dict
}

const slotLabel = id => {
  const number = toPieces(id.slice(5), { ss01: true, ss02: false, lookup })
    .map(piece => piece.pua).join('')
  return `存档 <span class="xy">${number}</span>`
}

$('save-menu').insertAdjacentHTML('afterbegin', Array.from({ length: 7 }, (_, i) => {
  const id = `slot-${i + 1}`
  return `<sl-menu-item value="${id}" type="checkbox">${slotLabel(id)}</sl-menu-item>`
}).join(''))
const slotItems = $('save-menu').querySelectorAll('[type="checkbox"]')

function selectSlot(id = activeSlot) {
  activeSlot = id
  $('save-dropdown').hidden = !saves.size
  store.set('save-slot', id)
  $('save-label').innerHTML = slotLabel(id)
  for (const item of slotItems) item.checked = item.value === id
  $('save-delete').disabled = !saves.has(id)
}

$('save-import').addEventListener('click', () => $('save-files').click())

function refreshSave() {
  const notes = new Map(Object.entries(saves.get(activeSlot)?.notes ?? {}))
  for (const e of entries) {
    const note = notes.get(e.name) ?? notes.get(`:${e.name}`) ??
      (e.struct === 'exp' ? notes.get(e.name[0]) : undefined)
    e.note = note?.trim().replace(/^\?$/, '')
  }
  $('stat').textContent = `v${ed.version} · ${entries.filter(unlocked).length} / ${entries.filter(available).length} 字已解锁`
  Object.assign(hist, { list: [], i: -1, auto: false })
  showDetail(null)
  renderNav()
  renderChart()
}

fullUnlock.addEventListener('sl-change', refreshSave)
$('save-menu').addEventListener('sl-select', ev => {
  const id = ev.detail.item.value
  if (id === 'delete') {
    saves.delete(activeSlot)
    store.set('saves', [...saves.values()])
  }
  selectSlot(id === 'delete' ? activeSlot : id)
  refreshSave()
})
$('save-files').addEventListener('change', async () => {
  const input = $('save-files')
  if (!input.files.length) return
  $('save-import').disabled = true
  const failed = []
  let selectedSlot
  for (const file of input.files) {
    try {
      const notes = await readSave(file)
      const number = /^alienmessage([1-7])\.sav/i.exec(file.name)?.[1]
      const id = `slot-${number ?? 1}`
      saves.set(id, { id, notes })
      selectedSlot ??= id
    } catch {
      failed.push(file.name)
    }
  }
  if (selectedSlot) {
    store.set('saves', [...saves.values()])
    selectSlot(selectedSlot)
    fullUnlock.checked = false
    refreshSave()
  }
  toast(failed.length ? `无法读取：${failed.join('、')}` : '已导入存档')
  input.value = ''
  $('save-import').disabled = false
})
selectSlot()

// ---------- typing pad ----------

const pad = $("pad-input");
$("presets").innerHTML = Object.keys(PRESETS)
  .map((k) => `<button type="button" class="chip">${k}</button>`)
  .join("");
$("presets").addEventListener("click", (ev) => {
  const button = ev.target.closest("button");
  if (button) {
    pad.value = PRESETS[button.textContent];
    pad.scrollTop = 0;
    updatePad();
  }
});
pad.value = "";

const feats = () => ({ ss01: $("f-ss01").checked, ss02: $("f-ss02").checked });
function updatePad() {
  const { ss01, ss02 } = feats();
  $("o-wght").textContent = pad.style.fontWeight = $("f-wght").value;
  document.documentElement.style.setProperty("--glyph-weight", pad.style.fontWeight);
  $("o-size").textContent = $("f-size").value;
  pad.style.fontSize = $("f-size").value + "px";
  pad.style.fontFeatureSettings =
    [ss01 && '"ss01"', ss02 && '"ss02"'].filter(Boolean).join(", ") || "normal";
  $("pad-src").textContent = pad.value;
}
pad.addEventListener("input", updatePad);
for (const el of [$("f-ss01"), $("f-ss02"), $("f-wght"), $("f-size")])
  el.addEventListener("sl-input", updatePad);
// word characters for ss02's joining: everything but numerals and the two words ss01 writes
const isWord = (ch) => {
  const e = ed.byCp.get(hex(ch.codePointAt(0)));
  return (
    !!e && e.struct !== "exp" && e !== ed.byToken.get("negative") && e !== ed.byToken.get("exp7")
  );
};
$("copy-pua").addEventListener("click", () => {
  const text = toPieces(pad.value, { ...feats(), lookup })
    .map((p) => p.text ?? p.pua ?? "")
    .join("");
  copy(feats().ss02 ? joinWords(text, isWord) : text, " PUA 文本");
});
updatePad();

// ---------- code chart ----------

const STRUCT = {
  s: "单体",
  exp: "数字",
  lr: "左右",
  ud: "上下",
  oi: "内外",
  our: "右上包围",
  oul: "左上包围",
  odr: "右下包围",
  odl: "左下包围",
  ol: "左包围",
  or: "右包围",
  d: "双写",
  t: "三写",
  q: "四写",
  vd: "竖双写",
  flr: "左右翻转",
  fud: "上下翻转",
  fb: "旋转",
};
const KIND = {
  numeral: ["数字"],
  token: ["其他", "不是字的字"],
  overflow: ["溢出区", "留给以后新增的字"],
};

const groupLabel = b => {
  const head = ed.byCp.get(b.head)
  return unlocked(head) ? annotation(head) : '未解锁'
}

// a code point as a glyph button
const ref = (cp, interactive = true) => {
  const e = ed.byCp.get(cp)
  if (!available(e)) return '<span class="part empty"></span>'
  if (!unlocked(e)) return '<span class="part empty locked" role="img" aria-label="未解锁"></span>'
  const tag = interactive ? 'button' : 'span'
  return `<${tag} class="part xy"${interactive ? ` type="button" data-cp="${cp}" title="U+${cp}"` : ''}><span>${e.char}</span><small class="part-note">${esc(annotation(e))}</small></${tag}>`
}

function cell(e) {
  if (!available(e)) return '<span class="cell empty"></span>';
  if (!unlocked(e)) return '<span class="cell empty locked" role="img" aria-label="未解锁"></span>';
  const title = esc(annotation(e));
  return (
    `<button type="button" class="cell${e === selected ? " sel" : ""}" data-cp="${e.cp}" title="${title}">` +
    `<span class="xy">${e.char}</span><small><span class="cell-note">${title}</span><span class="cell-code">${e.cp.slice(1, -1)}<b>${e.cp.slice(-1)}</b></span></small></button>`
  );
}

const groupCount = b => {
  const words = ed.entries.filter(e => available(e) && e.cp >= b.start && e.cp <= b.end)
  const total = words.length
  const collected = words.filter(unlocked).length
  const complete = !fullUnlock.checked && total > 0 && collected === total
  return `<i${complete ? ' class="complete"' : ''}>${fullUnlock.checked ? total : `${collected}/${total}`}</i>`
}

// one card of cells per block; the row numbers hang in the margin on the same grid rows
function renderBlock(b) {
  const lo = parseInt(b.start, 16),
    hi = parseInt(b.end, 16);
  const labels = [],
    cells = [];
  for (let r = lo; r <= hi; r += 16) {
    labels.push(`<span class="rlabel"><span><b>${hex(r).slice(1, -1)}</b>x</span></span>`);
    for (let c = 0; c < 16; c++) cells.push(cell(ed.byCp.get(hex(r + c))));
  }
  const [title, note] = KIND[b.kind] ?? [`${ref(b.head)} ${esc(groupLabel(b))}`];
  return (
    `<section class="block" id="b-${b.start}"><div class="bhead"><b>${title}</b><span>${b.start}–${b.end}${groupCount(b)}</span>` +
    `${note ? `<small>${note}</small>` : ""}</div>` +
    `<div class="bgrid" style="--rows:${labels.length};--rows2:${labels.length * 2}">${labels.join("")}` +
    `<div class="bcells">${cells.join("")}</div></div></section>`
  );
}

// Search only visible characters, code points and player annotations.
function search(q) {
  const hits = new Map();
  const add = (e) => unlocked(e) && hits.set(e.cp, e);
  const pasted = (ch) => ed.byCp.get(hex(ch.codePointAt(0)));
  for (const ch of q) add(pasted(ch));
  const terms = q.toLowerCase().split(/\s+/);
  const match = (e, t) =>
    (/^(u\+)?[0-9a-f]{3,5}$/.test(t) && e.cp.toLowerCase().endsWith(t.replace("u+", ""))) ||
    annotation(e).toLowerCase().includes(t);
  for (const e of ed.entries) if (terms.every((t) => match(e, t))) add(e);
  return [...hits.values()];
}

function renderChart() {
  const q = $("q").value.trim();
  const hits = q && search(q);
  $("q-clear").disabled = !q;
  $("q-count").textContent = q ? `${hits.length} 个结果` : "";
  $("chart-body").innerHTML = !q
    ? ed.blocks.map(renderBlock).join("")
    : hits.length
      ? `<div class="hits">${hits.map(cell).join("")}</div>`
      : '<p class="none">没有找到。</p>';
  if (hits?.length && !hits.includes(selected)) go(hits[0], true);
  queueStuck();
}

let selected = null;
// The game's dictionary sentences, followed by a blank line and the definition.
const word = (x) =>
  x[0] === "~" ? `<span class="raw">${esc(x.slice(1).replace("div", "/"))}</span>` : ref(x);
const line = (xs, title = "") => `<p${title && ` title="${title}"`}>${xs.map(word).join("")}</p>`;
function showDetail(e) {
  selected = e;
  document.querySelector(".cell.sel")?.classList.remove("sel");
  if (!unlocked(e)) {
    selected = null;
    $("detail").innerHTML = '<p class="hint">左键插入，右键查阅。</p>';
    return;
  }
  const cell = document.querySelector(`.cell[data-cp="${e.cp}"]`);
  cell?.classList.add("sel");
  const row = (k, v) => (v ? `<dt>${k}</dt><dd>${v}</dd>` : "");
  const cp = (token) => ed.byToken.get(token)?.cp ?? "?";
  const be = [e.cp, cp("be")];
  const roots = e.roots?.length
    ? [
        e.cp,
        cp("de"),
        cp("radicial"),
        cp("be"),
        ...e.roots.flatMap((root, i) => (i ? [cp("and"), root] : [root])),
      ]
    : [...be, cp("single"), cp("radicial")];
  const dict = e.wt?.length
    ? [
        line([...be, ...e.wt], "词性"),
        line(roots, "词根"),
        e.def?.length && "<p></p>",
        ...(e.def ?? []).map((l) => line(l)),
      ].filter(Boolean)
    : [line([e.cp, cp("benot"), cp("word")], "不是字")];
  const nav = (id, cp, title, ok) =>
    `<button type="button" class="tool xy" id="${id}" data-cp="${cp}" title="${title}" aria-label="${title}"${ok ? "" : " disabled"}>${mark(cp, id === "d-back" ? "←" : "→")}</button>`;
  $("detail").innerHTML =
    `<div class="dhead"><div class="dlabels"><span class="dcode">U+${e.cp}</span>${e.fan ? '<span class="dcode fan">自造字</span>' : ''}</div>` +
    `<div class="dnav"><button type="button" class="tool xy" id="d-copy" data-cp="F73BE" title="复制" aria-label="复制 U+${e.cp}">${mark("F73BE", "⧉")}</button>` +
    `${nav("d-back", "F729A", "上一个", hist.i > 0)}${nav("d-fwd", "F7299", "下一个", hist.i < hist.list.length - 1)}</div>` +
    `</div><div class="dtop"><button type="button" class="big xy" data-cp="${e.cp}" title="插入" aria-label="插入 U+${e.cp}">${e.char}</button>` +
    `<div class="dmeta"><b class="word-name">${esc(annotation(e))}</b>` +
    `<dl>${row("结构", STRUCT[e.struct])}${row("部件", !e.roots && e.parts?.map(cp => ref(cp)).join(""))}${row("类别", e.cats?.map(cp => ref(cp)).join(""))}</dl>` +
    `</div></div>` +
    (dict.length ? `<div class="dict">${dict.join("")}</div>` : "") +
    `<div class="dacts"><sl-button variant="primary" id="d-insert"><i data-lucide="arrow-up" slot="prefix"></i>插入打字区</sl-button>` +
    `<sl-button id="d-copy2"><i data-lucide="copy" slot="prefix"></i>复制</sl-button></div>`;
  createIcons({ icons: { ArrowUp, Copy }, attrs: { "aria-hidden": "true" }, root: $("detail") });
  $("d-insert").onclick = () => insert(e);
  $("d-copy2").onclick = () => copy(e.char, ` U+${e.cp}`);
  $("d-copy").onclick = () => copy(e.char, ` U+${e.cp}`);
  $("d-back").onclick = () => showDetail(hist.list[--hist.i]);
  $("d-fwd").onclick = () => showDetail(hist.list[++hist.i]);
}

// history for the card's back / forward; a search's automatic pick replaces itself instead of piling up
const hist = { list: [], i: -1, auto: false };
function go(e, auto = false) {
  if (!unlocked(e)) return;
  if (e === hist.list[hist.i]) return showDetail(e);
  hist.list = hist.list.slice(0, hist.i + (hist.auto ? 0 : 1)).concat(e);
  hist.i = hist.list.length - 1;
  hist.auto = auto;
  showDetail(e);
  if (!auto && narrow.matches) $("sheet").show();
}

function insert(e) {
  if (!unlocked(e)) return;
  pad.setRangeText(e.char, pad.selectionStart, pad.selectionEnd, "end");
  updatePad();
  toast("已加入打字区");
}
document.addEventListener("click", (ev) => {
  const target = ev.target.closest("[data-cp]");
  if (!target || target.closest(".dnav")) return;
  const e = ed.byCp.get(target.dataset.cp);
  if (!e) return;
  if (touch && !target.matches(".big")) go(e);
  else if (!target.matches("#brand")) insert(e);
});
document.addEventListener("contextmenu", (ev) => {
  const e = ed.byCp.get(ev.target.closest("[data-cp]")?.dataset.cp);
  if (!e) return;
  ev.preventDefault();
  go(e);
});
$("q").value = new URLSearchParams(location.search).get("q") ?? "";
let qTimer;
$("q").addEventListener("input", () => {
  clearTimeout(qTimer);
  qTimer = setTimeout(renderChart, 120);
});
$("q-clear").addEventListener("click", () => {
  $("q").value = "";
  renderChart();
  $("q").focus();
});
// the card lives in the chart's side column, or in the bottom sheet on narrow screens
function placeDetail() {
  if (narrow.matches) $("sheet").append($("detail"));
  else {
    $("sheet").hide();
    $("chart").append($("detail"));
  }
}
narrow.addEventListener("change", placeDetail);
placeDetail();

// ---------- group list ----------

function renderNav() {
  $("nav-list").innerHTML = ed.blocks
    .map((b) => {
      const title = KIND[b.kind]?.[0] ?? groupLabel(b);
      const cp = b.head ?? (b.kind === "numeral" ? "F7029" : b.start);
      return `<a href="#b-${b.start}" data-start="${b.start}">${ref(cp, false)}<b>${esc(title)}</b>${groupCount(b)}</a>`;
    })
    .join("");
}
$("nav-open").addEventListener("click", () => {
  // mark the group at the top of the chart
  const top = parseFloat(getComputedStyle(document.documentElement).scrollPaddingTop) || 0;
  const here = [...document.querySelectorAll(".block")].findLast(
    (b) => b.getBoundingClientRect().top <= top + 1,
  );
  for (const a of $("nav-list").children)
    a.toggleAttribute("aria-current", here?.id === "b-" + a.dataset.start);
  $("nav").placement = narrow.matches ? "bottom" : "end";
  $("nav").show();
});
$("nav").addEventListener("sl-after-show", () =>
  $("nav-list").querySelector("[aria-current]")?.scrollIntoView({ block: "center" }),
);
$("nav-list").addEventListener("click", async (ev) => {
  const a = ev.target.closest("a");
  if (!a) return;
  ev.preventDefault();
  await $("nav").hide();
  if ($("q").value) {
    $("q").value = "";
    renderChart();
  }
  $("b-" + a.dataset.start).scrollIntoView();
});

// a button back to the pad once it has scrolled away
new IntersectionObserver(([en]) => $("to-pad").classList.toggle("on", !en.isIntersecting)).observe(
  $("pad"),
);
$("to-pad").addEventListener("click", () => {
  $("pad").scrollIntoView({ behavior: "smooth" });
  pad.focus({ preventScroll: true });
});

// the sticky bars' heights, for scrolling to a group
new ResizeObserver(() => {
  const root = document.documentElement.style;
  const top = document.querySelector(".top");
  root.setProperty("--top-h", (getComputedStyle(top).position === "sticky" ? top.offsetHeight : 0) + "px");
  root.setProperty("--bar-h", document.querySelector(".chart-bar").offsetHeight + "px");
}).observe(document.body);

// which sticky bars are stuck: the lowest one fades its glass out past its edge
let stuckFrame = 0;
function markStuck() {
  stuckFrame = 0;
  const bar = document.querySelector(".chart-bar");
  const line = bar.getBoundingClientRect();
  const top = parseFloat(getComputedStyle(bar).top);
  const edge = top + bar.offsetHeight + 0.5;
  let any = false;
  for (const h of document.querySelectorAll(".bhead")) {
    const r = h.getBoundingClientRect();
    const stuck = r.top <= edge && r.bottom >= top;
    h.classList.toggle("stuck", stuck);
    any ||= stuck;
  }
  bar.classList.toggle("fade", line.top <= top + 0.5 && scrollY > 0 && !any);
}
const queueStuck = () => (stuckFrame ||= requestAnimationFrame(markStuck));
addEventListener("scroll", queueStuck, { passive: true });
addEventListener("resize", queueStuck);

refreshSave();
