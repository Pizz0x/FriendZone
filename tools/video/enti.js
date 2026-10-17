// Demo video of the map for the Comune (frontend/enti.html), as in the talk: the hour goes from 11 to 22
// and the streets change colour, then the districts with the lowest score, then one street up close.
// Writes video/demo_enti.mp4 (with captions) and video/demo_enti_senza_didascalie.mp4.
"use strict";
const fs = require("fs");
const path = require("path");
const L = require("./lib");

// the red stretch of Campo Marzo that the shortest route of the app demo goes through
const TARGET = [45.543775, 11.538515];
const ZOOM_TO = { center: [45.5446, 11.5412], zoom: 16.3 };

async function record(browser, file) {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, locale: "it-IT", timezoneId: "Europe/Rome", colorScheme: "light" });
  // keep a handle on the Leaflet map, which the page creates inside a closure
  await ctx.addInitScript(() => {
    let lib;
    Object.defineProperty(window, "L", { configurable: true, get: () => lib, set(v) { lib = v; if (v && v.Map && !v.__hooked) { v.__hooked = true; v.Map.addInitHook(function () { window.__map = this; }); } } });
  });
  await ctx.addInitScript(L.OVERLAY);
  await ctx.clock.install({ time: Date.parse("2026-10-17T12:00:00+02:00") });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.error("page:", e.message));
  await page.goto("file://" + path.join(L.ROOT, "frontend/enti.html"));
  await page.waitForSelector("#loading", { state: "detached", timeout: 120000 });
  const setHour = h => page.evaluate(h => { const el = document.getElementById("hour"); el.value = h; el.dispatchEvent(new Event("input")); }, h);
  await setHour(11);
  const read = () => page.evaluate(() => ({ red: document.getElementById("stRed").textContent, mean: document.getElementById("stMean").textContent,
    worst: [...document.querySelectorAll("#worstQ li span:first-child")].map(e => e.textContent) }));
  const at11 = await read();
  const geo = await page.evaluate(() => {
    const r = document.getElementById("hour").getBoundingClientRect(), z = __map.getZoom(), c = __map.getCenter();
    __map.options.zoomSnap = 0;  // fractional zoom for a smooth zoom-in
    return { slider: { x: r.x, y: r.y + r.height / 2, w: r.width }, zoom: z, center: [c.lat, c.lng], n: DATA.n };
  });
  const thumb = v => ({ x: geo.slider.x + 8 + (v / 23) * (geo.slider.w - 16), y: geo.slider.y });

  const rec = await L.Recorder.start(page, file, Date.parse("2026-10-17T12:00:30+02:00"));
  let cur = { x: 1010, y: 860 };
  const glide = (to, sec) => {
    const from = cur; cur = to;
    rec.effect(sec, (p, ov) => { const k = L.ease(p); ov.cursor = { x: L.lerp(from.x, to.x, k), y: L.lerp(from.y, to.y, k) }; });
  };
  const move = async (to, sec) => { glide(to, sec); await rec.wait(sec); };
  const click = async () => {
    const at = cur;
    rec.effect(0.55, (p, ov) => { ov.cursor = { x: at.x, y: at.y, down: p < 0.3 }; ov.ring = p < 1 ? { x: at.x, y: at.y, s: L.lerp(0.4, 1.6, p), a: L.lerp(0.9, 0, p) } : undefined; });
    await rec.wait(0.12);
  };
  rec.ov.cursor = cur;

  rec.mark("rete");
  await rec.wait(1.6);
  await move(thumb(11), 0.9);
  rec.ov.cursor = Object.assign({ down: true }, cur);
  await rec.wait(0.2);

  // drag the hour from 11 to 22: the pointer moves smoothly, the slider goes by whole hours
  rec.mark("ore");
  const frames = Math.round(4.8 * L.FPS);
  let hour = 11;
  for (let i = 1; i <= frames; i++) {
    const v = L.lerp(11, 22, L.ease(i / frames)), h = Math.round(v);
    cur = thumb(v); rec.ov.cursor = Object.assign({ down: true }, cur);
    if (h !== hour) { hour = h; await setHour(h); }
    await rec.frame();
  }
  rec.ov.cursor = Object.assign({}, cur);
  const at22 = await read();
  await rec.wait(1.4);

  // the districts with the lowest mean score
  rec.mark("quartieri");
  const box = await page.evaluate(() => {
    const a = document.getElementById("worstQ").previousElementSibling.getBoundingClientRect(), b = document.getElementById("worstQ").getBoundingClientRect();
    return { x: b.x - 10, y: a.y - 10, w: b.width + 20, h: b.bottom - a.y + 20 };
  });
  rec.effect(0.4, (p, ov) => { ov.box = Object.assign({ a: p }, box); });
  await move({ x: box.x + box.w - 70, y: box.y + box.h - 40 }, 0.8);
  await rec.wait(3.0);
  rec.effect(0.35, (p, ov) => { ov.box = p < 1 ? Object.assign({ a: 1 - p }, box) : undefined; });

  // zoom on the station and Campo Marzo, as if about a fixed point
  rec.mark("zoom");
  const z0 = geo.zoom, z1 = ZOOM_TO.zoom, c0 = geo.center, c1 = ZOOM_TO.center;
  const zf = Math.round(2.6 * L.FPS);
  glide({ x: 1180, y: 640 }, 1.2);  // the pointer drifts to the map meanwhile
  for (let i = 1; i <= zf; i++) {
    const z = L.lerp(z0, z1, L.ease(i / zf)), f = (1 - Math.pow(2, z0 - z)) / (1 - Math.pow(2, z0 - z1));
    await page.evaluate(([lat, lng, z]) => { __map.setView([lat, lng], z, { animate: false }); }, [L.lerp(c0[0], c1[0], f), L.lerp(c0[1], c1[1], f), z]);
    await rec.frame();
  }
  await rec.wait(0.8);

  // one street: score and what lowers it
  rec.mark("tratto");
  const pt = await page.evaluate(ll => { const p = __map.latLngToContainerPoint(ll), r = __map.getContainer().getBoundingClientRect(); return { x: r.x + p.x, y: r.y + p.y }; }, TARGET);
  await move(pt, 1.0);
  await click();
  await page.evaluate(ll => { __map.fire("click", { latlng: window.L.latLng(ll) }); }, TARGET);
  await rec.wait(0.7);
  const seg = await page.evaluate(() => {
    const c = document.getElementById("segCard"), panel = c.closest(".panel"), r = c.getBoundingClientRect();
    return { via: c.querySelector("h3").textContent, s: c.querySelector(".score b").textContent, pill: c.querySelector(".pill").textContent,
      scroll: Math.max(0, Math.min(panel.scrollHeight - panel.clientHeight, panel.scrollTop + r.top - 90)) };
  });
  const sf = Math.round(1.2 * L.FPS);
  for (let i = 1; i <= sf; i++) {
    await page.evaluate(y => { document.querySelector(".panel").scrollTop = y; }, seg.scroll * L.ease(i / sf));
    await rec.frame();
  }
  await rec.wait(4.6);
  const out = await rec.finish();
  await ctx.close();
  return Object.assign(out, { n: geo.n, at11, at22, seg });
}

function captions(info) {
  const fmt = n => n.toLocaleString("it-IT");
  if (!/priorità/.test(info.seg.pill)) throw new Error("the Campo Marzo stretch is no longer red: " + JSON.stringify(info.seg));
  const w = info.at22.worst;
  return {
    rete: ["Tutta la rete pedonale di Vicenza", `${fmt(info.n)} tratti con la sicurezza percepita stimata. Giorno feriale, ore 11.`],
    ore: ["Dalle 11 alle 22", `Le strade cambiano colore ora per ora: i km in rosso passano da ${info.at11.red} a ${info.at22.red}.`],
    quartieri: ["Priorità di intervento per quartiere", `Alle 22 il punteggio medio più basso è a ${w[0]}, ${w[1]} e ${w[2]}.`],
    zoom: ["Ogni strada, a ogni ora", "Zoom sulla stazione e sul Campo Marzo."],
    tratto: ["Il tratto che l'app fa evitare", `Nel Campo Marzo, alle 22: S ${info.seg.s} su 100, ${info.seg.pill}. Sotto, i parametri che lo abbassano.`]
  };
}

function card([t, d], i, n) {
  const bars = Array.from({ length: n }, (_, k) => `<i class="${k <= i ? "on" : ""}"></i>`).join("");
  return `<!doctype html><html><head><meta charset="utf-8"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;800&family=Atkinson+Hyperlegible:wght@400;700&display=swap"><style>
  html, body { margin: 0; background: transparent; }
  .card { position: absolute; right: 24px; top: 24px; width: 470px; box-sizing: border-box; background: #ffffff; border-radius: 18px; padding: 20px 24px 20px;
          box-shadow: 0 14px 40px rgba(36, 29, 58, .20), 0 0 0 1px rgba(36, 29, 58, .07); font-family: "Atkinson Hyperlegible", sans-serif; }
  .k { font: 800 14px Archivo, sans-serif; letter-spacing: .14em; text-transform: uppercase; color: #6a3ea1; }
  .t { font: 800 29px/1.15 Archivo, sans-serif; color: #1f1a2e; margin-top: 8px; }
  .d { font-size: 19px; line-height: 1.4; color: #4b4560; margin-top: 8px; }
  .bars { display: flex; gap: 6px; margin-top: 14px; } .bars i { flex: 1; height: 4px; border-radius: 2px; background: #e6e1ef; } .bars i.on { background: #6a3ea1; }
  </style></head><body><div class="card"><div class="k">Mappa per il Comune · ${i + 1}/${n}</div><div class="t">${L.esc(t)}</div><div class="d">${L.esc(d)}</div><div class="bars">${bars}</div></div></body></html>`;
}

async function compose(browser, raw, info) {
  const caps = captions(info), keys = info.marks.map(m => m.label), D = info.duration, X = 0.35;
  const args = ["-i", raw], fl = [];
  let prev = "0:v";
  for (let i = 0; i < keys.length; i++) {
    const f = path.join(L.BUILD, `enti_card_${i}.png`);
    await L.renderPng(browser, card(caps[keys[i]], i, keys.length), f);
    args.push("-loop", "1", "-framerate", String(L.FPS), "-t", String(D), "-i", f);
    const tin = i === 0 ? 0.4 : Math.max(0, info.marks[i].t - 0.1);
    const out = i + 1 < keys.length ? `,fade=t=out:st=${(info.marks[i + 1].t + 0.2).toFixed(2)}:d=${X}:alpha=1` : "";
    fl.push(`[${i + 1}:v]format=rgba,fade=t=in:st=${tin.toFixed(2)}:d=${X}:alpha=1${out}[k${i}]`, `[${prev}][k${i}]overlay[c${i}]`);
    prev = `c${i}`;
  }
  const ends = `fade=t=in:st=0:d=0.4,fade=t=out:st=${(D - 0.6).toFixed(2)}:d=0.6`;
  fl.push(`[${prev}]${ends},format=yuv420p[out]`);
  await L.ffmpeg([...args, "-filter_complex", fl.join(";"), "-map", "[out]", "-t", String(D), "-r", String(L.FPS), ...L.DELIVERY, path.join(L.OUT, "demo_enti.mp4")]);
  await L.ffmpeg(["-i", raw, "-vf", ends, ...L.DELIVERY, path.join(L.OUT, "demo_enti_senza_didascalie.mp4")]);
}

(async () => {
  fs.mkdirSync(L.BUILD, { recursive: true });
  const browser = await L.launch();
  const raw = path.join(L.BUILD, "enti_raw.mp4");
  const t = Date.now();
  const info = await record(browser, raw);
  fs.writeFileSync(path.join(L.BUILD, "enti_marks.json"), JSON.stringify(info, null, 1));
  console.log(`recorded ${info.duration} s in ${Math.round((Date.now() - t) / 1000)} s`, JSON.stringify(info.marks), JSON.stringify({ at11: info.at11, at22: info.at22, seg: info.seg }));
  await compose(browser, raw, info);
  await browser.close();
  console.log("written video/demo_enti.mp4 and video/demo_enti_senza_didascalie.mp4");
})().catch(e => { console.error(e); process.exit(1); });
