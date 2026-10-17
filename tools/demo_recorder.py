"""Record a Playwright page as a sharp H.264 video: CDP screencast frames, pausable, assembled with ffmpeg.

Used by tools/record_app_video.py and tools/record_enti_video.py for the demo clips in the pitch deck.
"""
import asyncio, base64, os, shutil, subprocess, time

TAP_JS = """
addEventListener('pointerdown', e => {
  const d = document.createElement('div');
  d.style.cssText = `position:fixed;left:${e.clientX - 24}px;top:${e.clientY - 24}px;width:48px;height:48px;border-radius:50%;` +
    `background:rgba(255,255,255,.38);border:3px solid rgba(255,255,255,.95);box-shadow:0 0 0 2px rgba(36,29,58,.25);` +
    `pointer-events:none;z-index:2147483647;transition:transform .5s ease,opacity .5s ease;transform:scale(.55);opacity:1`;
  document.documentElement.appendChild(d);
  requestAnimationFrame(() => requestAnimationFrame(() => { d.style.transform = 'scale(1.5)'; d.style.opacity = '0'; }));
  setTimeout(() => d.remove(), 700);
}, true);
"""
CURSOR_JS = """
addEventListener('DOMContentLoaded', () => {
  const c = document.createElement('div');
  c.innerHTML = '<svg width="26" height="30" viewBox="0 0 26 30"><path d="M2 2 L2 24 L8 18 L12.5 28 L16.5 26 L12 16.5 L20 16.5 Z" fill="#fff" stroke="#241d3a" stroke-width="2" stroke-linejoin="round"/></svg>';
  c.style.cssText = 'position:fixed;left:-50px;top:-50px;pointer-events:none;z-index:2147483647;filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))';
  document.documentElement.appendChild(c);
  addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
});
"""

class Recorder:
    def __init__(self, page, workdir, width, height):
        self.page, self.dir, self.w, self.h = page, workdir, width, height
        shutil.rmtree(workdir, ignore_errors=True); os.makedirs(workdir)
        self.frames, self.on, self.seg, self.ends, self.n = [], False, 0, {}, 0

    async def start(self):
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._frame)
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 94, "maxWidth": self.w, "maxHeight": self.h, "everyNthFrame": 1})
        self.on = True

    def _frame(self, p):
        asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": p["sessionId"]}))
        if not self.on:
            return
        path = os.path.join(self.dir, f"f{self.n:06d}.jpg"); self.n += 1
        with open(path, "wb") as f:
            f.write(base64.b64decode(p["data"]))
        self.frames.append((self.seg, time.time(), path))

    def pause(self):
        if self.on:
            self.ends[self.seg] = time.time(); self.on = False

    def resume(self):
        if not self.on:
            self.seg += 1; self.on = True

    async def stop(self):
        self.pause()
        await self.cdp.send("Page.stopScreencast")

    def assemble(self, out, fps=30, crf=21):
        lines, total = [], 0.0
        for i, (seg, t, path) in enumerate(self.frames):
            nxt = self.frames[i + 1] if i + 1 < len(self.frames) else None
            end = nxt[1] if nxt and nxt[0] == seg else self.ends.get(seg, t + 1 / fps)
            d = max(1 / fps, end - t); total += d
            lines += [f"file '{path}'", f"duration {d:.4f}"]
        lines.append(f"file '{self.frames[-1][2]}'")
        lst = os.path.join(self.dir, "list.txt")
        open(lst, "w").write("\n".join(lines) + "\n")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                        "-vf", f"fps={fps},scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
                        "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-movflags", "+faststart", "-an", out], check=True)
        return len(self.frames), total
