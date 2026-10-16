/* Quartieri Vivi: shared browser core.
 *
 * Scoring (mirrors model/scoring.py), time bands from the real sunset (mirrors
 * model/timebands.py), a spatial index for snapping points to the pedestrian
 * network, and least-cost routes (mirrors model/routing.py).
 * Used by frontend/src/enti.html and frontend/src/lumi.html; tests/test_frontend_js.py
 * runs it in Node and compares it with the Python model.
 */
const QV = (() => {
  "use strict";
  const RAD = Math.PI / 180;

  // ------------------------------------------------------------------ data
  async function unpack(b64, Type) {
    const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const stream = new Blob([bin]).stream().pipeThrough(new DecompressionStream("gzip"));
    return new Type(await new Response(stream).arrayBuffer());
  }

  async function load(DATA) {
    const M = DATA.model, N = DATA.n, K = M.keys;
    const idx = Object.fromEntries(K.map((k, i) => [k, i]));
    const S = {}, H = {};
    for (const [k, v] of Object.entries(DATA.static)) S[k] = await unpack(v, k === "via" || k === "lunghezza" ? Uint16Array : Uint8Array);
    for (const [k, v] of Object.entries(DATA.hourly)) H[k] = await unpack(v, Uint8Array);
    const counts = await unpack(DATA.geometry.counts, Uint16Array);
    const deltas = await unpack(DATA.geometry.coords, Int32Array);
    // segment i has vertices start[i] .. start[i+1]-1; xy holds lon, lat pairs
    const start = new Uint32Array(N + 1);
    for (let i = 0; i < N; i++) start[i + 1] = start[i] + counts[i];
    const xy = new Float64Array(start[N] * 2), bbox = new Float64Array(N * 4);
    let p = 0;
    for (let i = 0; i < N; i++) {
      let x = 0, y = 0, minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
      for (let j = start[i]; j < start[i + 1]; j++) {
        x += deltas[p++]; y += deltas[p++];
        const lon = x / 1e5, lat = y / 1e5;
        xy[2 * j] = lon; xy[2 * j + 1] = lat;
        if (lon < minx) minx = lon; if (lon > maxx) maxx = lon;
        if (lat < miny) miny = lat; if (lat > maxy) maxy = lat;
      }
      bbox[4 * i] = minx; bbox[4 * i + 1] = miny; bbox[4 * i + 2] = maxx; bbox[4 * i + 3] = maxy;
    }
    const ctx = { DATA, M, N, K, idx, S, H, start, xy, bbox };
    if (DATA.graph) {
      ctx.u = await unpack(DATA.graph.u, Uint16Array);
      ctx.v = await unpack(DATA.graph.v, Uint16Array);
      ctx.nodeCount = DATA.graph.nodes;
    }
    return ctx;
  }

  function line(ctx, i) {
    const out = [];
    for (let j = ctx.start[i]; j < ctx.start[i + 1]; j++) out.push([ctx.xy[2 * j], ctx.xy[2 * j + 1]]);
    return out;
  }

  // --------------------------------------------------------------- scoring
  function profileLambda(M, profs) {
    return M.lambda_base * profs.reduce((a, p) => a * M.profiles[p].lambda_factor, 1);
  }

  /** S, reliability and class of every segment.
   *  o = {band, day: "feriale"|"weekend", hour: 0-23, rain: bool, profiles: [..]} */
  function scores(ctx, o) {
    const { M, N, K, idx, S, H } = ctx;
    const B = M.bands[o.band], profs = o.profiles || [];
    const w = B.weights.slice(); let darkFactor = 1;
    for (const p of profs) {
      for (const [k, m] of Object.entries(M.profiles[p].multipliers)) w[idx[k]] *= m;
      darkFactor *= M.profiles[p].dark_factor;
    }
    const excluded = new Set(M.excluded.map(k => idx[k]));
    const off = ((o.day === "weekend" ? 24 : 0) + o.hour) * N;
    const D = M.penalties.dark, intensity = D.band_intensity[o.band] || 0;
    const rel = M.reliability, base = B.weights, scale = M.scale, NA = M.na;
    const red = M.classes.red_below, green = M.classes.green_above;
    const Sv = new Float32Array(N), R = new Float32Array(N), Pd = new Float32Array(N), cls = new Uint8Array(N);
    const x = new Float64Array(K.length), f = new Float64Array(K.length);
    const get = (arr, j) => arr[j] === NA ? NaN : arr[j] / scale;
    for (let i = 0; i < N; i++) {
      const sb = S.bits[i], hb = H.bits[off + i];
      x.fill(NaN);
      x[idx.luce] = get(S.luce, i);
      x[idx.persone] = get(H.persone, off + i) * (o.rain ? M.rain.persone : 1);
      x[idx.fronti_attivi] = get(H.fronti_attivi, off + i);
      x[idx.visuale] = get(S.visuale, i) * (o.rain ? M.rain.visuale : 1);
      x[idx.vie_di_fuga] = get(S.vie_di_fuga, i);
      x[idx.uso_suolo] = get(B.dark ? S.suolo_notte : S.suolo_giorno, i);
      x[idx.percorso] = get(S.percorso, i);
      x[idx.punti_aiuto] = get(H.punti_aiuto, off + i);
      x[idx.trasporto] = get(H.trasporto, off + i);
      let num = 0, den = 0;
      for (let j = 0; j < K.length; j++) {
        if (excluded.has(j) || Number.isNaN(x[j])) continue;
        num += w[j] * Math.min(1, Math.max(0, x[j])); den += w[j];
      }
      const light = Number.isNaN(x[idx.luce]) ? 0.5 : x[idx.luce];
      const pd = Math.min(D.max, intensity * (D.base + D.poor_light * (1 - light)) * darkFactor);
      const pen = ((sb & 8) ? 1 - M.penalties.blocking : 1) * ((hb & 4) ? 1 - M.penalties.park_dark : 1) * (1 - pd);
      const s = Math.min(100, Math.max(0, den > 0 ? 100 * num / den * pen : 0));
      Sv[i] = s; Pd[i] = pd;
      cls[i] = s < red ? 2 : s > green ? 0 : 1;
      // reliability: base weights x origin factor (measured 1, proxy 0.5, excluded 0)
      f.fill(rel.measured);
      f[idx.luce] = (sb & 1) ? rel.proxy : rel.measured;
      f[idx.persone] = rel.proxy; f[idx.visuale] = rel.proxy;
      f[idx.fronti_attivi] = (hb & 1) ? rel.proxy : rel.measured;
      f[idx.punti_aiuto] = (hb & 2) ? rel.proxy : rel.measured;
      f[idx.trasporto] = (hb & 8) ? rel.proxy : rel.measured;
      f[idx.percorso] = (sb & 2) ? rel.proxy : rel.measured;
      f[idx.uso_suolo] = (sb & 4) ? rel.excluded : rel.measured;
      for (const j of excluded) f[j] = rel.excluded;
      let r = 0; for (let j = 0; j < K.length; j++) r += base[j] * f[j];
      R[i] = r / 100;
    }
    return { band: o.band, day: o.day, hour: o.hour, rain: !!o.rain, profs, w, off, darkFactor,
             S: Sv, R, Pd, cls, lam: profileLambda(M, profs) };
  }

  /** Parameter values of one segment and the points each one costs, with the weights of `st`. */
  function explain(ctx, st, i) {
    const { M, K, idx, S, H } = ctx, off = st.off, scale = M.scale, NA = M.na;
    const x = new Array(K.length).fill(NaN);
    const get = (arr, j) => arr[j] === NA ? NaN : arr[j] / scale;
    const B = M.bands[st.band];
    x[idx.luce] = get(S.luce, i); x[idx.persone] = get(H.persone, off + i) * (st.rain ? M.rain.persone : 1);
    x[idx.fronti_attivi] = get(H.fronti_attivi, off + i); x[idx.visuale] = get(S.visuale, i) * (st.rain ? M.rain.visuale : 1);
    x[idx.vie_di_fuga] = get(S.vie_di_fuga, i); x[idx.uso_suolo] = get(B.dark ? S.suolo_notte : S.suolo_giorno, i);
    x[idx.percorso] = get(S.percorso, i); x[idx.punti_aiuto] = get(H.punti_aiuto, off + i); x[idx.trasporto] = get(H.trasporto, off + i);
    let den = 0; for (let j = 0; j < K.length; j++) if (!Number.isNaN(x[j])) den += st.w[j];
    const loss = x.map((v, j) => Number.isNaN(v) ? NaN : 100 * st.w[j] / den * (1 - Math.min(1, Math.max(0, v))));
    return { x, loss };
  }

  // ------------------------------------------------------------ time bands
  const TZ = "Europe/Rome";
  const fmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23", weekday: "short" });
  const WD = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };

  /** Wall-clock time in Vicenza: {y, m, d, h, mi, wd (0 = Monday)}. */
  function local(date) {
    const o = {};
    for (const p of fmt.formatToParts(date)) o[p.type] = p.value;
    return { y: +o.year, m: +o.month, d: +o.day, h: +o.hour % 24, mi: +o.minute, wd: WD[o.weekday] };
  }
  function utcOffsetMin(date) {
    const l = local(date);
    return Math.round((Date.UTC(l.y, l.m - 1, l.d, l.h, l.mi) - date.getTime()) / 60000);
  }

  /** Sunrise or sunset in minutes after 00:00 UTC (NOAA almanac algorithm, zenith 90.833). */
  function sunUtcMinutes(y, m, d, lat, lon, rising) {
    const N1 = Math.floor(275 * m / 9), N2 = Math.floor((m + 9) / 12), N3 = 1 + Math.floor((y - 4 * Math.floor(y / 4) + 2) / 3);
    const n = N1 - N2 * N3 + d - 30, lngHour = lon / 15;
    const t = n + ((rising ? 6 : 18) - lngHour) / 24;
    const Ma = 0.9856 * t - 3.289;
    let L = Ma + 1.916 * Math.sin(Ma * RAD) + 0.020 * Math.sin(2 * Ma * RAD) + 282.634;
    L = (L % 360 + 360) % 360;
    let RA = Math.atan(0.91764 * Math.tan(L * RAD)) / RAD;
    RA = (RA % 360 + 360) % 360;
    RA = (RA + Math.floor(L / 90) * 90 - Math.floor(RA / 90) * 90) / 15;
    const sinDec = 0.39782 * Math.sin(L * RAD), cosDec = Math.cos(Math.asin(sinDec));
    const cosH = (Math.cos(90.833 * RAD) - sinDec * Math.sin(lat * RAD)) / (cosDec * Math.cos(lat * RAD));
    const Hh = (rising ? 360 - Math.acos(cosH) / RAD : Math.acos(cosH) / RAD) / 15;
    const T = Hh + RA - 0.06571 * t - 6.622;
    return ((T - lngHour) % 24 + 24) % 24 * 60;
  }

  function easter(y) {
    const a = y % 19, b = Math.floor(y / 100), c = y % 100, d = Math.floor(b / 4), e = b % 4;
    const f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30;
    const i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451);
    const month = Math.floor((h + l - 7 * m + 114) / 31), day = ((h + l - 7 * m + 114) % 31) + 1;
    return [month, day];
  }
  const hhmm = s => { const [h, m] = s.split(":"); return +h * 60 + +m; };
  const pad = n => String(n).padStart(2, "0");
  const clock = minutes => { const t = ((Math.round(minutes) % 1440) + 1440) % 1440; return pad(Math.floor(t / 60)) + ":" + pad(t % 60); };

  /** Band, day type and sun times of a moment in Vicenza (same rules as model/timebands.py). */
  function moment(M, date) {
    const T = M.time, b = T.boundaries, l = local(date);
    const noon = new Date(Date.UTC(l.y, l.m - 1, l.d, 11, 0));
    const off = utcOffsetMin(noon);
    const sunrise = sunUtcMinutes(l.y, l.m, l.d, T.center.lat, T.center.lon, true) + off;
    const sunset = sunUtcMinutes(l.y, l.m, l.d, T.center.lat, T.center.lon, false) + off;
    const now = l.h * 60 + l.mi, deep = hhmm(b.deep_night_end);
    let band;
    if (now < deep) band = "notte_fonda";
    else if (now < sunrise) band = "mattina_buia";
    else if (now < sunset - b.twilight_start_before_sunset_min) band = "giorno";
    else if (now < sunset + b.twilight_end_after_sunset_min) band = "prima_ora_buio";
    else if (now < hhmm(b.evening_end)) band = "sera";
    else band = "notte_fonda";
    // hours before 05:00 belong to the previous evening
    const back = band === "notte_fonda" && now < deep ? 1 : 0;
    const dd = new Date(Date.UTC(l.y, l.m - 1, l.d - back));
    const wd = (dd.getUTCDay() + 6) % 7, mmdd = pad(dd.getUTCMonth() + 1) + "-" + pad(dd.getUTCDate());
    const [em, ed] = easter(dd.getUTCFullYear());
    const easterMonday = new Date(Date.UTC(dd.getUTCFullYear(), em - 1, ed + 1));
    const holiday = T.calendar.holidays_mmdd.includes(mmdd) || (T.calendar.easter_monday_is_holiday && +easterMonday === +dd);
    let day = "feriale";
    if (T.calendar.weekend_days.includes(wd) || holiday) day = "weekend";
    else if (T.calendar.weekend_evening_days.includes(wd) && T.calendar.weekend_evening_bands.includes(band)) day = "weekend";
    return { band, day, hour: l.h, minutes: now, sunrise, sunset, local: l, dark: M.bands[band].dark };
  }

  // -------------------------------------------------------- spatial index
  const CELL = 0.004;
  function spatialIndex(ctx) {
    const grid = new Map(), { bbox, N } = ctx;
    for (let i = 0; i < N; i++) {
      for (let gx = Math.floor(bbox[4 * i] / CELL); gx <= Math.floor(bbox[4 * i + 2] / CELL); gx++)
        for (let gy = Math.floor(bbox[4 * i + 1] / CELL); gy <= Math.floor(bbox[4 * i + 3] / CELL); gy++) {
          const key = gx + ":" + gy;
          if (!grid.has(key)) grid.set(key, []);
          grid.get(key).push(i);
        }
    }
    return grid;
  }
  const metres = lat => [111320 * Math.cos(lat * RAD), 110540];
  function distM(a, b) { const [kx, ky] = metres((a[1] + b[1]) / 2); return Math.hypot((b[0] - a[0]) * kx, (b[1] - a[1]) * ky); }
  function segLength(ctx, i) {
    let L = 0;
    for (let j = ctx.start[i] + 1; j < ctx.start[i + 1]; j++)
      L += distM([ctx.xy[2 * j - 2], ctx.xy[2 * j - 1]], [ctx.xy[2 * j], ctx.xy[2 * j + 1]]);
    return L;
  }

  /** Closest point of the network to (lon, lat): {i, t (0 = start of the segment, 1 = end), d (m), lon, lat}. */
  function nearest(ctx, grid, lon, lat, maxM) {
    const [kx, ky] = metres(lat);
    const reach = Math.max(1, Math.ceil(maxM / (CELL * ky)));
    const gx0 = Math.floor(lon / CELL), gy0 = Math.floor(lat / CELL);
    let best = null; const seen = new Set();
    for (let gx = gx0 - reach; gx <= gx0 + reach; gx++) for (let gy = gy0 - reach; gy <= gy0 + reach; gy++) {
      for (const i of grid.get(gx + ":" + gy) || []) {
        if (seen.has(i)) continue; seen.add(i);
        let along = 0;
        const s0 = ctx.start[i], s1 = ctx.start[i + 1];
        const total = segLength(ctx, i) || 1;
        for (let j = s0 + 1; j < s1; j++) {
          const ax = (ctx.xy[2 * j - 2] - lon) * kx, ay = (ctx.xy[2 * j - 1] - lat) * ky;
          const bx = (ctx.xy[2 * j] - lon) * kx, by = (ctx.xy[2 * j + 1] - lat) * ky;
          const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy, len = Math.sqrt(l2);
          const tt = l2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / l2)) : 0;
          const d = Math.hypot(ax + tt * dx, ay + tt * dy);
          if (d <= maxM && (!best || d < best.d)) {
            best = { i, d, t: Math.min(1, (along + tt * len) / total),
                     lon: lon + (ax + tt * dx) / kx, lat: lat + (ay + tt * dy) / ky };
          }
          along += len;
        }
      }
    }
    return best;
  }

  // --------------------------------------------------------------- routing
  function graph(ctx) {
    const n = ctx.nodeCount, deg = new Uint32Array(n + 1);
    for (let i = 0; i < ctx.N; i++) { deg[ctx.u[i] + 1]++; if (ctx.u[i] !== ctx.v[i]) deg[ctx.v[i] + 1]++; }
    for (let k = 0; k < n; k++) deg[k + 1] += deg[k];
    const fill = deg.slice(0, n), nb = new Uint32Array(deg[n]), seg = new Uint32Array(deg[n]);
    for (let i = 0; i < ctx.N; i++) {
      const a = ctx.u[i], b = ctx.v[i];
      nb[fill[a]] = b; seg[fill[a]++] = i;
      if (a !== b) { nb[fill[b]] = a; seg[fill[b]++] = i; }
    }
    const len = new Float64Array(ctx.N);
    for (let i = 0; i < ctx.N; i++) len[i] = ctx.S.lunghezza[i] || segLength(ctx, i);
    return { n, off: deg, nb, seg, len };
  }

  class Heap {
    constructor() { this.k = []; this.v = []; }
    push(key, val) {
      const k = this.k, v = this.v; let i = k.length; k.push(key); v.push(val);
      while (i > 0) { const p = (i - 1) >> 1; if (k[p] <= key) break; k[i] = k[p]; v[i] = v[p]; i = p; }
      k[i] = key; v[i] = val;
    }
    pop() {
      const k = this.k, v = this.v, top = v[0], key = k.pop(), val = v.pop(), n = k.length;
      if (n) {
        let i = 0;
        for (;;) {
          let c = 2 * i + 1; if (c >= n) break;
          if (c + 1 < n && k[c + 1] < k[c]) c++;
          if (k[c] >= key) break;
          k[i] = k[c]; v[i] = v[c]; i = c;
        }
        k[i] = key; v[i] = val;
      }
      return top;
    }
    get size() { return this.k.length; }
  }

  /** Least-cost route between two snapped points (see nearest) for a lambda.
   *  Returns {parts: [{i, f0, f1}], length, cost, redM, yellowM, greenM, mean} or null. */
  function route(ctx, g, st, from, to, lam) {
    const n = g.n, SRC = n, DST = n + 1;
    const cost = i => g.len[i] * (1 + lam * Math.pow((100 - st.S[i]) / 100, 2));
    const dist = new Float64Array(n + 2).fill(Infinity), prevN = new Int32Array(n + 2).fill(-1), prevS = new Int32Array(n + 2).fill(-1);
    const heap = new Heap();
    const relax = (node, d, from_, seg) => {
      if (d < dist[node]) { dist[node] = d; prevN[node] = from_; prevS[node] = seg; heap.push(d, node); }
    };
    const c0 = cost(from.i), c1 = cost(to.i);
    relax(ctx.u[from.i], from.t * c0, SRC, from.i);
    relax(ctx.v[from.i], (1 - from.t) * c0, SRC, from.i);
    if (from.i === to.i) relax(DST, Math.abs(to.t - from.t) * c0, SRC, from.i);
    const done = new Uint8Array(n + 2);
    while (heap.size) {
      const node = heap.pop();
      if (done[node]) continue;
      done[node] = 1;
      if (node === DST) break;
      for (let k = g.off[node]; k < g.off[node + 1]; k++) relax(g.nb[k], dist[node] + cost(g.seg[k]), node, g.seg[k]);
      if (node === ctx.u[to.i]) relax(DST, dist[node] + to.t * c1, node, to.i);
      if (node === ctx.v[to.i]) relax(DST, dist[node] + (1 - to.t) * c1, node, to.i);
    }
    if (!Number.isFinite(dist[DST])) return null;
    // walk back: each step is a (part of a) segment between two positions along it
    const parts = [];
    let node = DST;
    while (node !== SRC) {
      const p = prevN[node], i = prevS[node];
      const fEnd = node === DST ? to.t : (node === ctx.u[i] ? 0 : 1);
      const fStart = p === SRC ? from.t : (p === ctx.u[i] ? 0 : 1);
      // a self-loop walked in full goes 0 -> 1
      const full = p !== SRC && node !== DST && ctx.u[i] === ctx.v[i];
      parts.push({ i, f0: full ? 0 : fStart, f1: full ? 1 : fEnd });
      node = p;
    }
    parts.reverse();
    const r = { parts, cost: dist[DST], length: 0, redM: 0, yellowM: 0, greenM: 0, mean: 0 };
    for (const q of parts) {
      const L = g.len[q.i] * Math.abs(q.f1 - q.f0);
      r.length += L; r.mean += L * st.S[q.i];
      if (st.cls[q.i] === 2) r.redM += L; else if (st.cls[q.i] === 1) r.yellowM += L; else r.greenM += L;
    }
    r.mean = r.length > 0 ? r.mean / r.length : st.S[from.i];
    return r;
  }

  /** Vertices of segment i between fractions f0 and f1 (f0 > f1 walks it backwards). */
  function subLine(ctx, i, f0, f1) {
    const pts = line(ctx, i), cum = [0];
    for (let j = 1; j < pts.length; j++) cum.push(cum[j - 1] + distM(pts[j - 1], pts[j]));
    const total = cum[cum.length - 1] || 1;
    const at = f => {
      const d = f * total;
      for (let j = 1; j < pts.length; j++) if (d <= cum[j] || j === pts.length - 1) {
        const s = cum[j] - cum[j - 1] ? (d - cum[j - 1]) / (cum[j] - cum[j - 1]) : 0;
        return [pts[j - 1][0] + (pts[j][0] - pts[j - 1][0]) * s, pts[j - 1][1] + (pts[j][1] - pts[j - 1][1]) * s];
      }
      return pts[0];
    };
    const lo = Math.min(f0, f1), hi = Math.max(f0, f1), out = [at(lo)];
    for (let j = 1; j < pts.length - 1; j++) if (cum[j] / total > lo && cum[j] / total < hi) out.push(pts[j]);
    out.push(at(hi));
    return f0 <= f1 ? out : out.reverse();
  }

  function bearing(a, b) {
    const y = Math.sin((b[0] - a[0]) * RAD) * Math.cos(b[1] * RAD);
    const x = Math.cos(a[1] * RAD) * Math.sin(b[1] * RAD) - Math.sin(a[1] * RAD) * Math.cos(b[1] * RAD) * Math.cos((b[0] - a[0]) * RAD);
    return (Math.atan2(y, x) / RAD + 360) % 360;
  }

  /** Polyline of the route plus turn-by-turn steps where the street name changes. */
  function itinerary(ctx, r) {
    const names = ctx.DATA.names.via, unnamed = ctx.DATA.model.unnamed_label;
    const coords = [], legs = [];
    let along = 0;
    for (const q of r.parts) {
      const pts = subLine(ctx, q.i, q.f0, q.f1);
      const name = names[ctx.S.via[q.i]];
      let L = 0; for (let j = 1; j < pts.length; j++) L += distM(pts[j - 1], pts[j]);
      const startIdx = coords.length ? coords.length - 1 : 0;
      for (let j = coords.length ? 1 : 0; j < pts.length; j++) coords.push(pts[j]);
      const last = legs[legs.length - 1];
      if (last && last.name === name) { last.length += L; last.end = coords.length - 1; }
      else legs.push({ name, length: L, start: startIdx, end: coords.length - 1, at: along });
      along += L;
    }
    // short unnamed connectors (crossings, little paths) and very short legs are folded into the next street
    const merged = [];
    for (const leg of legs) {
      let prev = merged[merged.length - 1];
      if (prev && merged.length > 1 && (prev.length < 12 || (prev.name === unnamed && prev.length < 25))) {
        merged.pop();
        leg.at = prev.at; leg.start = prev.start; leg.length += prev.length;
        prev = merged[merged.length - 1];
      }
      if (prev && leg.name === prev.name) { prev.length += leg.length; prev.end = leg.end; }
      else merged.push(leg);
    }
    const pointAt = (from, metresAlong, dir) => {
      let acc = 0, k = from;
      while (acc < metresAlong && k + dir >= 0 && k + dir < coords.length) { acc += distM(coords[k], coords[k + dir]); k += dir; }
      return coords[k];
    };
    const steps = merged.map((leg, n) => {
      if (n === 0) return { type: "start", name: leg.name, at: 0, length: leg.length, pos: coords[0] };
      const c = coords[leg.start];
      const inB = bearing(pointAt(leg.start, 15, -1), c), outB = bearing(c, pointAt(leg.start, 15, 1));
      const turn = ((outB - inB + 540) % 360) - 180;
      const a = Math.abs(turn);
      const dir = a < 25 ? "straight" : a > 155 ? "uturn" : (a < 50 ? "slight_" : "") + (turn < 0 ? "left" : "right");
      return { type: "turn", dir, name: leg.name, at: leg.at, length: leg.length, pos: c };
    });
    // going straight on into a street with another name is not announced as a manoeuvre
    const turns = steps.filter((st, n) => n === 0 || st.dir !== "straight");
    turns.push({ type: "arrive", name: "", at: along, length: 0, pos: coords[coords.length - 1] });
    return { coords, steps: turns, length: along };
  }

  return { unpack, load, line, scores, explain, profileLambda, local, moment, clock, sunUtcMinutes,
           spatialIndex, nearest, distM, segLength, graph, route, subLine, itinerary, bearing };
})();
if (typeof module !== "undefined") module.exports = QV;
