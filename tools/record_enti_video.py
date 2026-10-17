"""Demo video of the map for the Comune (frontend/enti.html), desktop size.

    python -m http.server -d frontend 8000 &
    python tools/record_enti_video.py frontend/assets/video/enti.mp4

Needs Playwright with Chromium and ffmpeg; CHROMIUM may point to a browser binary, FZ_URL to another server.
The deck also wants a WebM copy: ffmpeg -i X.mp4 -c:v libvpx-vp9 -crf 31 -b:v 0 -an X.webm
"""
import asyncio, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from demo_recorder import Recorder, CURSOR_JS

OUT, WORK = sys.argv[1], os.path.join(tempfile.gettempdir(), "fz_frames")
BASE = os.environ.get("FZ_URL", "http://localhost:8000")
W, H = 1600, 900

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
        ctx = await b.new_context(viewport={"width": W, "height": H}, locale="it-IT", timezone_id="Europe/Rome")
        await ctx.add_init_script(CURSOR_JS)
        page = await ctx.new_page()
        errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
        hold = lambda s: page.wait_for_timeout(int(s * 1000))
        mouse = [W / 2, H / 2]
        async def glide(x, y, steps=28):
            await page.mouse.move(x, y, steps=steps); mouse[:] = [x, y]
        async def center_of(sel):
            bb = await page.locator(sel).first.bounding_box(); return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
        await page.goto(BASE + "/enti.html")
        await page.wait_for_function("window.QVcheck && window.QVcheck.map", timeout=90000); await hold(2)
        await page.mouse.move(W * .62, H * .55)
        rec = Recorder(page, WORK, W, H); await rec.start()
        await hold(2.5)
        # hour: evening -> day -> night
        x, y = await center_of("#hour"); await glide(x, y); await hold(.4)
        await page.focus("#hour")
        for _ in range(9):
            await page.keyboard.press("ArrowLeft"); await hold(.38)
        await hold(2.2)
        for _ in range(12):
            await page.keyboard.press("ArrowRight"); await hold(.3)
        await hold(2)
        # who walks: man, then woman again
        x, y = await center_of("label[for=sx-u]"); await glide(x, y); await page.mouse.click(x, y); await hold(2)
        x, y = await center_of("label[for=sx-d]"); await glide(x, y); await page.mouse.click(x, y); await hold(1.6)
        x, y = await center_of("label[for=a-1]"); await glide(x, y); await page.mouse.click(x, y); await hold(2)
        # fly to the centre and open a red segment
        await glide(W * .62, H * .5)
        await page.evaluate("void QVcheck.map.flyTo([45.5468, 11.5462], 15.5, { duration: 2.6 })"); await hold(3.4)
        pt = await page.evaluate("""(() => {
          const { S } = QVcheck.compute(), m = QVcheck.map, sz = m.getSize(), box = m.getContainer().getBoundingClientRect();
          let best = null, bd = 1e9;
          for (let i = 0; i < S.length; i++) {
            if (!(S[i] < 40)) continue;
            const p = QVcheck.point(i);
            if (p.x < sz.x * .25 || p.x > sz.x * .8 || p.y < sz.y * .25 || p.y > sz.y * .75) continue;
            const d = Math.hypot(p.x - sz.x * .55, p.y - sz.y * .5);
            if (d < bd) { bd = d; best = [box.left + p.x, box.top + p.y]; }
          }
          return best;
        })()""")
        await glide(pt[0], pt[1], steps=40); await hold(.3); await page.mouse.click(pt[0], pt[1]); await hold(1)
        await page.evaluate("document.getElementById('segCard').scrollIntoView({ behavior: 'smooth', block: 'center' })"); await hold(4.5)
        await page.evaluate("document.getElementById('worstQ').scrollIntoView({ behavior: 'smooth', block: 'center' })"); await hold(3)
        await rec.stop()
        n, dur = rec.assemble(OUT)
        print("frames", n, "seconds", round(dur, 1), "errors", errs, "red at", pt)
        await b.close()

asyncio.run(main())
