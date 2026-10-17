"""Demo video of the citizens' app (frontend/app.html), phone size.

    python -m http.server -d frontend 8000 &
    python tools/record_app_video.py frontend/assets/video/app.mp4

Needs Playwright with Chromium and ffmpeg; CHROMIUM may point to a browser binary, FZ_URL to another server.
The deck also wants a WebM copy: ffmpeg -i X.mp4 -c:v libvpx-vp9 -crf 31 -b:v 0 -an X.webm
"""
import asyncio, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.async_api import async_playwright
from demo_recorder import Recorder, TAP_JS

OUT, WORK = sys.argv[1], os.path.join(tempfile.gettempdir(), "fz_frames")
BASE = os.environ.get("FZ_URL", "http://localhost:8000")
W, H, DPR = 430, 932, 1.5

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None,
                                    args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        ctx = await b.new_context(viewport={"width": W, "height": H}, device_scale_factor=DPR, locale="it-IT", timezone_id="Europe/Rome")
        await ctx.add_init_script(TAP_JS)
        page = await ctx.new_page()
        errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
        hold = lambda s: page.wait_for_timeout(int(s * 1000))
        await page.goto(BASE + "/app.html"); await hold(1.5)
        rec = Recorder(page, WORK, int(W * DPR), int(H * DPR)); await rec.start()
        await hold(2.6)
        await page.click("text=Iniziamo"); await hold(1.3)
        await page.type("#wzIn", "Giulia", delay=140); await hold(.6)
        await page.click("[data-act=wiz-next]"); await hold(1.4)
        await page.click("[data-act=wiz-opt][data-v=donna]"); await hold(1.6)
        await page.click("[data-act=wiz-opt][data-v='16_34']"); await hold(1.6)
        await page.click("[data-act=wiz-opt][data-v=conosce_zona]"); await hold(.7)
        await page.click("[data-act=wiz-next]"); await hold(1.4)
        await page.click("[data-act=wiz-opt][data-v=medio]"); await hold(1.6)
        await page.click("[data-act=wiz-skip]"); await hold(1.3)
        for _ in range(5):
            await page.click("[data-act=tut-next]"); await hold(1.1)
        await page.click("[data-act=end-finish]")
        rec.pause(); await page.wait_for_function("window.FZ && window.FZ.state", timeout=60000); await hold(.4); rec.resume()
        await hold(2.2)
        await page.click(".bnav >> text=Mappa")
        rec.pause(); await page.wait_for_function("FZ.map && FZ.map.loaded()", timeout=90000); await hold(2.5); rec.resume()
        await hold(1.5)
        await page.click("[data-act=demo-route]"); await hold(5.5)
        await page.click("[data-act=start]"); await hold(3)
        await page.evaluate("FZ.setSimSpeed(9)"); await hold(6)
        await page.locator("[data-act=sos]:visible").first.click(); await hold(4)
        await page.keyboard.press("Escape"); await hold(1.2)
        rec.pause(); await page.evaluate("FZ.setSimSpeed(300)")
        await page.wait_for_function("FZ.current === 's-arrive'", timeout=90000); await hold(.6); rec.resume()
        await hold(2.4)
        await page.click("#s-arrive [data-go=s-report]"); await hold(1.6)
        await page.click("[data-act=report-pick]"); await hold(1.4)
        box = await page.evaluate("(() => { const r = document.getElementById('app').getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height * 0.45]; })()")
        await page.mouse.click(box[0], box[1]); await hold(1.2)
        await page.click("[data-act=rep-type][data-v=luce_scarsa]"); await hold(1.2)
        await page.click("[data-act=report-send]"); await hold(2.6)
        await page.click(".bnav >> text=Supporto"); await hold(3.4)
        await rec.stop()
        n, dur = rec.assemble(OUT)
        print("frames", n, "seconds", round(dur, 1), "fps", round(n / dur, 1), "errors", errs)
        await b.close()

asyncio.run(main())
