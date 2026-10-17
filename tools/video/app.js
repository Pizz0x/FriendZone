// Demo video of the app for people on foot (frontend/app.html), as in the talk:
// 22:00, Stazione -> Corso Fogazzaro, recommended vs shortest route, navigator, SOS.
// Writes video/demo_app.mp4 (16:9 with captions) and video/demo_app_verticale.mp4 (phone screen only).
"use strict";
const fs = require("fs");
const path = require("path");
const L = require("./lib");

// Saturday 17 October 2026, 22:00 in Vicenza: the numbers in the talk (16 and 15 min, 239 m) are for this evening
const START = Date.parse("2026-10-17T21:59:30+02:00");
const PAUSE = Date.parse("2026-10-17T22:00:00+02:00");
const PHONE = { w: 390, h: 844, dsf: 2 };
// where the phone screen goes in the 1920x1080 frame
const SCREEN = { x: 338, y: 60, w: 444, h: 960, r: 54 };
const BODY = { x: SCREEN.x - 16, y: SCREEN.y - 16, w: SCREEN.w + 32, h: SCREEN.h + 32, r: 70 };

async function record(browser, file) {
  const ctx = await browser.newContext({ viewport: { width: PHONE.w, height: PHONE.h }, deviceScaleFactor: PHONE.dsf, isMobile: true, hasTouch: true, locale: "it-IT", timezoneId: "Europe/Rome" });
  await ctx.addInitScript(() => {
    // the initial questions are already done (step 1 of the demo): a woman, no other answers
    localStorage.setItem("lumi.done", "true");
    localStorage.setItem("lumi.guide", '"f"');
    localStorage.setItem("lumi.profile", JSON.stringify({ nome: "Giulia", genere: "donna", eta: "nd", situazioni: [], deviazione: "medio", forma: "f" }));
  });
  await ctx.addInitScript(L.OVERLAY);
  await ctx.clock.install({ time: START });
  const page = await ctx.newPage();
  page.on("pageerror", e => console.error("page:", e.message));
  await page.goto("file://" + path.join(L.ROOT, "frontend/app.html"));
  await page.waitForFunction(() => window.FZ && FZ.ctx && FZ.map && FZ.map.loaded(), null, { timeout: 120000 });
  // no GPS here, so the navigator runs in simulation: hide the toast that says so (the "Simulazione" label stays)
  await page.addStyleTag({ content: "#toast { visibility: hidden !important; }" });

  const rec = await L.Recorder.start(page, file, PAUSE);
  async function tap(sel) {
    const c = await page.evaluate(s => { const r = document.querySelector(s).getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; }, sel);
    const press = 0.28;
    rec.effect(0.65, (p, ov) => {
      if (p >= 1) { delete ov.tap; return; }
      ov.tap = p < press ? { x: c.x, y: c.y, s: L.lerp(1.25, 0.85, p / press), a: L.lerp(0, 0.95, p / press) }
        : { x: c.x, y: c.y, s: L.lerp(0.85, 1.7, (p - press) / (1 - press)), a: L.lerp(0.95, 0, (p - press) / (1 - press)) };
    });
    await rec.wait(0.18);
    await page.evaluate(s => document.querySelector(s).click(), sel);
  }

  rec.mark("ore22");
  await rec.wait(1.8);
  await tap('#bnav [data-go="s-plan"]');
  await rec.wait(1.5);
  rec.mark("confronto");
  await tap('[data-act="demo-route"]');
  await rec.wait(4.4);
  const nums = await page.evaluate(() => {
    const o = [...document.querySelectorAll("#pSheet .ropt")].map(e => ({ min: e.querySelector(".t").textContent, d: e.querySelector(".d").textContent }));
    return { when: document.getElementById("whenTxt").textContent, a: o[0], b: o[1], why: document.querySelector("#pSheet .why").textContent };
  });
  rec.mark("rosso");
  await tap('#pSheet .ropt[data-v="1"]');
  await rec.wait(2.8);
  await tap('#pSheet .ropt[data-v="0"]');
  await rec.wait(1.4);
  rec.mark("navigatore");
  await tap('[data-act="start"]');
  await rec.wait(6.5);
  rec.mark("sos");
  await tap('#s-nav [data-act="sos"]');
  await rec.wait(4.2);
  const out = await rec.finish();
  await ctx.close();
  return Object.assign(out, { nums });
}

function captions(nums) {
  const red = (nums.b.d.match(/(\d+) m con criticità/) || [])[1], extra = (nums.why.match(/allunga di ([\d,]+ k?m)/) || [])[1];
  if (!/22:00/.test(nums.when) || !red || !extra) throw new Error("the demo route changed: " + JSON.stringify(nums));
  return {
    ore22: ["Sono le 22:00", "Dalla stazione a Corso Fogazzaro, a piedi"],
    confronto: ["Due percorsi a confronto", `Consigliato: ${nums.a.min}, <b class="g">nessun tratto rosso</b><br>Più breve: ${nums.b.min}`],
    rosso: ["Il più breve passa sul rosso", `<b class="r">${red} m con criticità percepite</b>: il consigliato li evita con ${extra} in più`],
    navigatore: ["Navigatore svolta per svolta", "Indicazioni anche a voce, con il colore del tratto in cui sei"],
    sos: ["SOS sempre in vista", "112 e 1522 subito, senza codice"]
  };
}

function background(steps, active) {
  const items = steps.map(([t, d], i) => `<div class="step ${i < active ? "done" : i === active ? "on" : ""}"><div class="num">${i < active ? "✓" : i + 1}</div><div><div class="t">${L.esc(t)}</div><div class="d">${d}</div></div></div>`).join("");
  return `<!doctype html><html><head><meta charset="utf-8">${L.FONTS}<style>
  html, body { margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: #100d18; font-family: Manrope, sans-serif; color: #f1edfa; }
  .glow { position: absolute; border-radius: 50%; transform: translate(-50%, -50%); }
  .phone { position: absolute; left: ${BODY.x}px; top: ${BODY.y}px; width: ${BODY.w}px; height: ${BODY.h}px; border-radius: ${BODY.r}px; background: #07060b;
           box-shadow: 0 0 0 2px #2f2a42, 0 0 0 10px #181522, 0 0 0 12px #2a2539, 0 50px 100px rgba(0, 0, 0, .65); }
  .panel { position: absolute; left: 930px; top: 0; width: 870px; height: 1080px; display: flex; flex-direction: column; justify-content: center; }
  .kicker { font-weight: 800; letter-spacing: .16em; text-transform: uppercase; color: #b9a3f5; font-size: 19px; margin-top: 14px; }
  .wm { font-family: Montserrat, sans-serif; font-weight: 800; font-size: 60px; letter-spacing: -.01em; line-height: 1; }
  .steps { margin-top: 52px; display: flex; flex-direction: column; gap: 26px; }
  .step { display: grid; grid-template-columns: 52px 1fr; gap: 22px; align-items: start; opacity: .34; }
  .step.done { opacity: .55; } .step.on { opacity: 1; }
  .num { width: 48px; height: 48px; border-radius: 50%; border: 2px solid #4a3f78; color: #b9a3f5; font: 800 21px Montserrat, sans-serif; display: grid; place-items: center; margin-top: -4px; }
  .on .num { background: #9b7cf0; border-color: #9b7cf0; color: #15121f; box-shadow: 0 0 0 8px rgba(155, 124, 240, .18); }
  .t { font: 800 33px/1.15 Montserrat, sans-serif; }
  .d { font-size: 23px; line-height: 1.38; color: #cbc4de; margin-top: 7px; font-weight: 600; }
  .g { color: #5fd38f; font-weight: 800; } .r { color: #ff7a6b; font-weight: 800; }
  .foot { position: absolute; left: 930px; bottom: 44px; width: 860px; font-size: 16px; line-height: 1.45; color: #7d7596; font-weight: 500; }
  </style></head><body>
  <div class="glow" style="left:${BODY.x + BODY.w / 2}px;top:540px;width:1250px;height:1250px;background:radial-gradient(circle, rgba(106,63,208,.42), rgba(106,63,208,0) 60%);"></div>
  <div class="glow" style="left:1500px;top:180px;width:900px;height:900px;background:radial-gradient(circle, rgba(76,194,125,.10), rgba(76,194,125,0) 60%);"></div>
  <div class="phone"></div>
  <div class="panel">${L.WORDMARK}<div class="kicker">L'app per chi cammina · demo</div><div class="steps">${items}</div></div>
  <div class="foot">Il punteggio stima la sicurezza percepita a partire da dati pubblici: non misura la sicurezza reale di un luogo. Senza GPS il navigatore mostra il percorso in simulazione.</div>
  </body></html>`;
}

// alpha mask with the rounded corners of the screen
const mask = () => `<!doctype html><html><body style="margin:0;background:#000;"><div style="width:${SCREEN.w}px;height:${SCREEN.h}px;border-radius:${SCREEN.r}px;background:#fff;"></div></body></html>`;

async function compose(browser, raw, info) {
  const steps = captions(info.nums), keys = info.marks.map(m => m.label);
  const pngs = [];
  for (let i = 0; i < keys.length; i++) {
    const f = path.join(L.BUILD, `app_bg_${i}.png`);
    await L.renderPng(browser, background(keys.map(k => steps[k]), i), f);
    pngs.push(f);
  }
  const msk = path.join(L.BUILD, "app_mask.png");
  await L.renderPng(browser, mask(), msk, { width: SCREEN.w, height: SCREEN.h });
  const D = info.duration, X = 0.35;
  const args = ["-i", raw];
  for (const f of [msk, ...pngs]) args.push("-loop", "1", "-framerate", String(L.FPS), "-t", String(D), "-i", f);
  const fl = [`[0:v]scale=${SCREEN.w}:${SCREEN.h}:flags=lanczos,setsar=1,format=rgba[ph]`, "[1:v]format=gray[mk]", "[ph][mk]alphamerge[scr]", "[2:v]format=rgba[c0]"];
  for (let i = 1; i < pngs.length; i++) {
    const t = Math.max(0, info.marks[i].t - 0.1);
    fl.push(`[${i + 2}:v]format=rgba,fade=t=in:st=${t}:d=${X}:alpha=1[b${i}]`, `[c${i - 1}][b${i}]overlay[c${i}]`);
  }
  fl.push(`[c${pngs.length - 1}][scr]overlay=${SCREEN.x}:${SCREEN.y},fade=t=in:st=0:d=0.4,fade=t=out:st=${(D - 0.6).toFixed(2)}:d=0.6,format=yuv420p[out]`);
  await L.ffmpeg([...args, "-filter_complex", fl.join(";"), "-map", "[out]", "-t", String(D), "-r", String(L.FPS), ...L.DELIVERY, path.join(L.OUT, "demo_app.mp4")]);
  // the phone screen alone, for a slide with its own phone frame
  await L.ffmpeg(["-i", raw, "-vf", "fade=t=in:st=0:d=0.3,fade=t=out:st=" + (D - 0.5).toFixed(2) + ":d=0.5", ...L.DELIVERY, path.join(L.OUT, "demo_app_verticale.mp4")]);
}

(async () => {
  fs.mkdirSync(L.BUILD, { recursive: true });
  const browser = await L.launch();
  const raw = path.join(L.BUILD, "app_raw.mp4");
  const t = Date.now();
  const info = await record(browser, raw);
  fs.writeFileSync(path.join(L.BUILD, "app_marks.json"), JSON.stringify(info, null, 1));
  console.log(`recorded ${info.duration} s in ${Math.round((Date.now() - t) / 1000)} s`, JSON.stringify(info.marks), JSON.stringify(info.nums));
  await compose(browser, raw, info);
  await browser.close();
  console.log("written video/demo_app.mp4 and video/demo_app_verticale.mp4");
})().catch(e => { console.error(e); process.exit(1); });
