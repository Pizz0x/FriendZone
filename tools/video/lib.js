// Frame-by-frame recorder for the demo videos (tools/video/app.js, tools/video/enti.js).
// The page runs on a fake clock (Playwright) and CSS animations are paused and moved by hand,
// so every frame is complete and the video is smooth however slow the software renderer is.
"use strict";
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

const FPS = 30;
const DT = 1000 / FPS;
const ROOT = path.resolve(__dirname, "../..");
const OUT = path.join(ROOT, "video");
const BUILD = path.join(OUT, ".build");

function launch() {
  return chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--hide-scrollbars", "--mute-audio"] });
}

// Drawn on top of the page, moved from Node at every frame: a touch ripple, a mouse pointer, a highlight box.
const OVERLAY = `(() => {
  let root = null; const els = {};
  const mk = (k, css, html) => { const e = document.createElement("div"); e.style.cssText = "position:fixed;left:0;top:0;display:none;pointer-events:none;" + css; if (html) e.innerHTML = html; root.appendChild(e); return els[k] = e; };
  const ARROW = '<svg width="30" height="30" viewBox="0 0 30 30"><path d="M5 3l0 21 5.5-5.2 3.6 8.3 3.6-1.6-3.6-8.1 7.7-.2z" fill="#111" stroke="#fff" stroke-width="2" stroke-linejoin="round"/></svg>';
  window.__ov = { update(s) {
    if (!root) {
      root = document.createElement("div"); root.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:2147483647;";
      document.documentElement.appendChild(root);
      mk("box", "border:3px solid #6a3ea1;border-radius:12px;box-shadow:0 0 0 7px rgba(106,62,161,.18);");
      mk("ring", "width:44px;height:44px;border-radius:50%;border:3px solid #6a3ea1;");
      mk("tap", "width:50px;height:50px;border-radius:50%;background:rgba(255,255,255,.30);border:2.5px solid rgba(255,255,255,.92);box-shadow:0 2px 12px rgba(0,0,0,.35);");
      mk("cursor", "width:30px;height:30px;filter:drop-shadow(0 2px 3px rgba(0,0,0,.35));transform-origin:5px 3px;", ARROW);
    }
    const b = s.box, r = s.ring, t = s.tap, c = s.cursor;
    Object.assign(els.box.style, b ? { display: "block", left: b.x + "px", top: b.y + "px", width: b.w + "px", height: b.h + "px", opacity: b.a } : { display: "none" });
    Object.assign(els.ring.style, r ? { display: "block", transform: "translate(" + (r.x - 22) + "px," + (r.y - 22) + "px) scale(" + r.s + ")", opacity: r.a } : { display: "none" });
    Object.assign(els.tap.style, t ? { display: "block", transform: "translate(" + (t.x - 25) + "px," + (t.y - 25) + "px) scale(" + t.s + ")", opacity: t.a } : { display: "none" });
    Object.assign(els.cursor.style, c ? { display: "block", transform: "translate(" + (c.x - 5) + "px," + (c.y - 3) + "px) scale(" + (c.down ? 0.86 : 1) + ")" } : { display: "none" });
  } };
})();`;

const ease = p => p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
const lerp = (a, b, p) => a + (b - a) * p;

class Recorder {
  /** Pauses the page clock at `pauseAt` and pipes every frame (JPEG) into ffmpeg. */
  static async start(page, file, pauseAt) {
    const r = new Recorder();
    r.page = page; r.file = file; r.n = 0; r.ov = {}; r.effects = []; r.anims = new Map(); r.marks = [];
    await page.evaluate(() => document.fonts.ready);
    // a plain capture comes out at 1x: the clip asks for every device pixel
    const vp = page.viewportSize();
    r.clip = { x: 0, y: 0, width: vp.width, height: vp.height, scale: await page.evaluate(() => devicePixelRatio) };
    await page.clock.pauseAt(pauseAt);
    r.cdp = await page.context().newCDPSession(page);
    await r.cdp.send("Animation.enable");
    await r.cdp.send("Animation.setPlaybackRate", { playbackRate: 0 });
    r.cdp.on("Animation.animationStarted", e => {
      const s = e.animation.source || {};
      r.anims.set(e.animation.id, { start: r.ms, end: (s.delay || 0) + (s.duration || 0) + (s.endDelay || 0) });
    });
    fs.mkdirSync(path.dirname(file), { recursive: true });
    r.ff = spawn("ffmpeg", ["-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "mjpeg", "-i", "-",
      "-c:v", "libx264", "-preset", "medium", "-crf", "12", "-pix_fmt", "yuv420p", file], { stdio: ["pipe", "inherit", "inherit"] });
    r.done = new Promise((ok, ko) => r.ff.on("close", code => code ? ko(new Error("ffmpeg " + code)) : ok()));
    return r;
  }
  get ms() { return this.n * DT; }
  get t() { return this.n / FPS; }
  mark(label) { this.marks.push({ t: +this.t.toFixed(3), label }); }
  /** Runs `fn(p, ov)` for `sec` seconds from now, p going from 0 to 1. */
  effect(sec, fn) { this.effects.push({ t0: this.ms, dur: sec * 1000, fn }); }
  async frame() {
    await this.page.clock.runFor(DT);
    this.n++;
    for (const [id, a] of this.anims) {
      const ct = this.ms - a.start;
      await this.cdp.send("Animation.seekAnimations", { animations: [id], currentTime: Math.min(ct, a.end) }).catch(() => this.anims.delete(id));
      if (ct > a.end + 200) this.anims.delete(id);
    }
    this.effects = this.effects.filter(e => { const p = Math.min(1, (this.ms - e.t0) / e.dur); e.fn(p, this.ov); return p < 1; });
    await this.page.evaluate(s => window.__ov.update(s), this.ov);
    const { data } = await this.cdp.send("Page.captureScreenshot", { format: "jpeg", quality: 95, clip: this.clip });
    if (!this.ff.stdin.write(Buffer.from(data, "base64"))) await new Promise(ok => this.ff.stdin.once("drain", ok));
  }
  async wait(sec) { const end = this.n + Math.round(sec * FPS); while (this.n < end) await this.frame(); }
  async finish() {
    this.ff.stdin.end(); await this.done;
    return { duration: +this.t.toFixed(3), marks: this.marks };
  }
}

/** Screenshots a self-contained HTML page (captions, backgrounds) to PNG, transparent where the page is. */
async function renderPng(browser, html, file, { width = 1920, height = 1080 } = {}) {
  const page = await browser.newPage({ viewport: { width, height } });
  await page.setContent(html, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: file, omitBackground: true });
  await page.close();
}

function ffmpeg(args) {
  return new Promise((ok, ko) => {
    const p = spawn("ffmpeg", ["-loglevel", "error", "-y", ...args], { stdio: ["ignore", "inherit", "inherit"] });
    p.on("close", code => code ? ko(new Error("ffmpeg " + code)) : ok());
  });
}
// H.264 that plays in PowerPoint, Keynote and Google Slides
const DELIVERY = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an"];

const FONTS = '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=Montserrat:wght@700;800&display=swap">';
const WORDMARK = '<span class="wm"><span style="color:#f1edfa">FRIEND</span><span style="color:#4cc27d">ly</span><span style="color:#f0b155">ZO</span><span style="color:#f0675a">NE</span></span>';
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

module.exports = { FPS, ROOT, OUT, BUILD, launch, OVERLAY, Recorder, ease, lerp, renderPng, ffmpeg, DELIVERY, FONTS, WORDMARK, esc };
