// Fog Waste Console — dashboard controller (vanilla JS, no dependencies)

// config.js sets window.WMS_CONFIG. Local (FastAPI) mode reads /api/*; cloud mode
// (Firebase Hosting) reads the snapshot the fog layer publishes to Supabase.
const CONFIG = window.WMS_CONFIG || { mode: 'local' };
const HOSTED = CONFIG.mode === 'cloud';
const API_BASE = '';
const POLL_MS = HOSTED ? (CONFIG.pollMs || 3000) : 2000;
let updateInterval = null;
let isRunning = false;

// ---------------------------------------------------------------------------
// DOM
// ---------------------------------------------------------------------------

const $ = (id) => document.getElementById(id);

const startBtn = $('start-btn');
const stopBtn = $('stop-btn');
const triggerElectionBtn = $('trigger-election-btn');
const statusPill = $('system-status');
const lastUpdatedEl = $('last-updated');
const eventLogEl = $('event-log');

const binsCanvas = $('bins-canvas');
const routesCanvas = $('routes-canvas');
const networkCanvas = $('network-canvas');
const binsCtx = binsCanvas.getContext('2d');
const routesCtx = routesCanvas.getContext('2d');
const networkCtx = networkCanvas.getContext('2d');

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let binsData = [];
let routesData = [];
let networkData = { nodes: [], edges: [] };
let serverEvents = [];
let localEvents = [];          // UI-only messages, kept separately so polling doesn't erase them
let seenEventKeys = new Set();
let lastStatus = null;

// Hit-test targets for tooltips, rebuilt on every draw
let binHits = [];
let routeHits = [];

const ROUTE_COLORS = ['#2563eb', '#7c3aed', '#db2777', '#0891b2', '#4f46e5', '#65a30d', '#c026d3', '#0d9488'];

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

let palette = null;

function readPalette() {
    const css = getComputedStyle(document.documentElement);
    const v = (name) => css.getPropertyValue(name).trim();
    palette = {
        surface: v('--surface'), surface2: v('--surface-2'), plot: v('--plot'),
        border: v('--border'), borderStrong: v('--border-strong'),
        text: v('--text'), muted: v('--muted'), faint: v('--faint'),
        accent: v('--accent'), info: v('--info'), leader: v('--leader'),
        low: v('--tier-low'), medium: v('--tier-medium'), high: v('--tier-high'), critical: v('--tier-critical'),
        font: v('--font'),
    };
}

function isDarkTheme() {
    const explicit = document.documentElement.dataset.theme;
    if (explicit) return explicit === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function toggleTheme() {
    const next = isDarkTheme() ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('wms-theme', next); } catch (e) { /* storage blocked */ }
    redrawAll();
}

window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redrawAll);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Priority tiers from the paper (modules/route_optimizer/priority.py)
function tierOf(fill) {
    if (fill >= 90) return { key: 'critical', label: 'Critical' };
    if (fill >= 80) return { key: 'high', label: 'High' };
    if (fill >= 60) return { key: 'medium', label: 'Medium' };
    return { key: 'low', label: 'Low' };
}

function tierColor(fill) {
    return palette[tierOf(fill).key];
}

function withAlpha(color, alpha) {
    // Works for #rrggbb; falls back to the colour itself
    if (/^#[0-9a-f]{6}$/i.test(color)) {
        const n = parseInt(color.slice(1), 16);
        return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
    }
    return color;
}

function font(size, weight = 500) {
    return `${weight} ${size}px ${palette.font}`;
}

function formatTime(date) {
    return date.toLocaleTimeString([], { hour12: false });
}

function setupCanvas(canvas, ctx) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width));
    const h = Math.max(1, Math.floor(rect.height));
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.scale(dpr, dpr);
}

function clear(ctx, canvas) {
    const w = canvas.parentElement.clientWidth;
    const h = canvas.parentElement.clientHeight;
    ctx.clearRect(0, 0, w, h);
    return { w, h };
}

function emptyMessage(ctx, w, h, text) {
    ctx.fillStyle = palette.faint;
    ctx.font = font(13);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, w / 2, h / 2);
}

// Text with a background-coloured outline, so lines behind it don't cut through
function haloText(ctx, text, x, y, fontSpec, color) {
    ctx.font = fontSpec;
    ctx.lineJoin = 'round';
    ctx.lineWidth = 4;
    ctx.strokeStyle = palette.plot;
    ctx.strokeText(text, x, y);
    ctx.fillStyle = color;
    ctx.fillText(text, x, y);
}

function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, r);
}

function initCanvases() {
    setupCanvas(binsCanvas, binsCtx);
    setupCanvas(routesCanvas, routesCtx);
    setupCanvas(networkCanvas, networkCtx);
}

function redrawAll() {
    readPalette();
    drawBinsMap();
    drawRoutes();
    drawNetwork();
}

// ---------------------------------------------------------------------------
// Admin key (control endpoints require X-API-Key)
// ---------------------------------------------------------------------------

const ADMIN_KEY_STORAGE = 'wms-admin-key';

function getAdminKey() {
    let key = null;
    try { key = localStorage.getItem(ADMIN_KEY_STORAGE); } catch (e) { /* storage blocked */ }
    if (!key) {
        key = prompt('Admin API key (required to control the simulation):');
        if (key) {
            try { localStorage.setItem(ADMIN_KEY_STORAGE, key); } catch (e) { /* storage blocked */ }
        }
    }
    return key;
}

function clearAdminKey() {
    try { localStorage.removeItem(ADMIN_KEY_STORAGE); } catch (e) { /* storage blocked */ }
}

// fetch() for control endpoints. Returns the response, or null if no key was given.
async function adminFetch(url, options = {}) {
    const key = getAdminKey();
    if (!key) {
        addEvent('SYSTEM', 'Action cancelled: admin key required');
        return null;
    }
    const headers = Object.assign({ 'Content-Type': 'application/json', 'X-API-Key': key }, options.headers || {});
    const response = await fetch(url, Object.assign({}, options, { headers }));
    if (response.status === 401) {
        clearAdminKey();
        addEvent('SYSTEM', 'Error: invalid admin key');
    } else if (response.status === 503) {
        addEvent('SYSTEM', 'Error: controls are disabled on this server');
    }
    return response;
}

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

startBtn.addEventListener('click', startSystem);
stopBtn.addEventListener('click', stopSystem);
triggerElectionBtn.addEventListener('click', triggerElection);
$('theme-toggle').addEventListener('click', toggleTheme);

// Re-measure canvases whenever their container changes size (window resize,
// layout settling after load, breakpoint changes), at most once per frame.
let resizeFrame = null;
const resizeObserver = new ResizeObserver(() => {
    if (resizeFrame) return;
    resizeFrame = requestAnimationFrame(() => {
        resizeFrame = null;
        initCanvases();
        redrawAll();
    });
});
[binsCanvas, routesCanvas, networkCanvas].forEach(c => resizeObserver.observe(c.parentElement));

async function startSystem() {
    const config = {
        zones: parseInt($('zones').value, 10),
        bins_per_zone: parseInt($('bins').value, 10),
        trucks_per_zone: parseInt($('trucks').value, 10),
        update_interval: 3
    };

    startBtn.disabled = true;
    try {
        const response = await adminFetch(`${API_BASE}/api/system/config`, {
            method: 'POST',
            body: JSON.stringify(config)
        });
        if (response && response.ok) {
            isRunning = true;
            addEvent('SYSTEM', `Started: ${config.zones} zones × ${config.bins_per_zone} bins`);
            startUpdates();
        } else if (response && response.status === 422) {
            addEvent('SYSTEM', 'Error: configuration out of range');
        }
    } catch (error) {
        console.error('Error starting system:', error);
        addEvent('SYSTEM', 'Error: ' + error.message);
    }
    updateUIState();
}

async function stopSystem() {
    try {
        const response = await adminFetch(`${API_BASE}/api/system/stop`, { method: 'POST' });
        if (response && response.ok) {
            isRunning = false;
            stopUpdates();
            addEvent('SYSTEM', 'System stopped');
        }
    } catch (error) {
        console.error('Error stopping system:', error);
    }
    updateUIState();
}

async function triggerElection() {
    triggerElectionBtn.disabled = true;
    const label = triggerElectionBtn.textContent;
    triggerElectionBtn.textContent = 'Electing…';
    try {
        const response = await adminFetch(`${API_BASE}/api/election/trigger`, {
            method: 'POST',
            body: JSON.stringify({ initiator_zone: null })
        });
        if (response && response.ok) {
            addEvent('ELECTION', 'Election triggered');
            updateAllData();
        }
    } catch (error) {
        console.error('Error:', error);
    }
    triggerElectionBtn.textContent = label;
    triggerElectionBtn.disabled = !isRunning;
}

function setPill(state) {
    const labels = { live: 'Live', stopped: 'Stopped', offline: 'Offline', stale: 'Fog offline', waiting: 'Waiting' };
    statusPill.className = 'pill pill-' + state;
    statusPill.querySelector('.pill-text').textContent = labels[state];
}

function updateUIState() {
    startBtn.disabled = isRunning;
    stopBtn.disabled = !isRunning;
    triggerElectionBtn.disabled = !isRunning;
    ['zones', 'bins', 'trucks'].forEach(id => { $(id).disabled = isRunning; });
    if (!HOSTED) setPill(isRunning ? 'live' : 'stopped');   // cloud mode sets it from data age
}

function startUpdates() {
    if (updateInterval) clearInterval(updateInterval);
    updateInterval = setInterval(updateAllData, POLL_MS);
    updateAllData();
}

function stopUpdates() {
    if (updateInterval) {
        clearInterval(updateInterval);
        updateInterval = null;
    }
}

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------

function applySnapshot({ status, bins, routes, network, events }) {
    lastStatus = status;
    binsData = bins || [];
    routesData = routes || [];
    networkData = network || { nodes: [], edges: [] };
    serverEvents = events || [];

    updateStatusDisplay(status);
    redrawAll();
    updateEventLog();
    updateModuleStats(status);
}

async function updateAllData() {
    if (HOSTED) return updateFromCloud();
    if (!isRunning) return;

    try {
        const responses = await Promise.all([
            fetch(`${API_BASE}/api/system/status`),
            fetch(`${API_BASE}/api/bins`),
            fetch(`${API_BASE}/api/routes`),
            fetch(`${API_BASE}/api/network`),
            fetch(`${API_BASE}/api/events?limit=50`)
        ]);
        if (responses.some(r => !r.ok)) throw new Error('Server returned an error');
        const [status, bins, routes, network, events] = await Promise.all(responses.map(r => r.json()));

        if (!status.running) {
            // Stopped by another admin
            isRunning = false;
            stopUpdates();
            updateUIState();
        } else {
            setPill('live');
        }
        lastUpdatedEl.textContent = 'Updated ' + formatTime(new Date());
        applySnapshot({ status, bins, routes, network, events });
    } catch (error) {
        console.error('Error:', error);
        setPill('offline');
    }
}

// ---------------------------------------------------------------------------
// Cloud mode: read the latest snapshot from Supabase (read-only publishable key)
// ---------------------------------------------------------------------------

async function fetchCloudSnapshot() {
    const base = String(CONFIG.supabaseUrl || '').replace(/\/+$/, '');
    const response = await fetch(`${base}/rest/v1/snapshots?id=eq.live&select=published_at,payload`, {
        headers: { apikey: CONFIG.supabaseKey, Accept: 'application/json' },
        cache: 'no-store'
    });
    if (!response.ok) throw new Error('Supabase returned ' + response.status);
    const rows = await response.json();
    return rows[0] || null;
}

function formatAge(seconds) {
    if (seconds < 5) return 'just now';
    if (seconds < 60) return Math.round(seconds) + ' s ago';
    if (seconds < 3600) return Math.round(seconds / 60) + ' min ago';
    return 'at ' + formatTime(new Date(Date.now() - seconds * 1000));
}

async function updateFromCloud() {
    try {
        const row = await fetchCloudSnapshot();
        if (!row) {
            setPill('waiting');
            lastUpdatedEl.textContent = 'No data published yet';
            return;
        }
        const payload = row.payload || {};
        const ageS = Math.max(0, (Date.now() - new Date(row.published_at)) / 1000);
        const cloud = payload.cloud || {};
        const staleAfter = Math.max(15, 4 * (cloud.interval_s || 3));

        applySnapshot(payload);

        if (!payload.status?.running) setPill('stopped');
        else if (ageS > staleAfter) setPill('stale');
        else setPill('live');
        lastUpdatedEl.textContent = 'Fog data ' + formatAge(ageS);

        const sync = cloud.sync_ms != null ? `, last sync ${Math.round(cloud.sync_ms)} ms` : '';
        $('footnote').textContent =
            `Read-only view. The fog layer publishes to Supabase every ${cloud.interval_s || 3} s${sync}. ` +
            'Fog nodes run as threads within one simulation process.';
    } catch (error) {
        console.error('Error:', error);
        setPill('offline');
        lastUpdatedEl.textContent = 'Cannot reach Supabase';
    }
}

// ---------------------------------------------------------------------------
// KPIs
// ---------------------------------------------------------------------------

function updateStatusDisplay(status) {
    const bins = status.bin_statistics || {};
    const totals = status.fog_nodes?.system_totals || {};
    const nodes = Object.values(status.fog_nodes?.nodes || {});
    const zones = status.configuration?.zones || nodes.length;

    const total = bins.total_bins || 0;
    const over = bins.overflowing_bins || 0;
    const avg = bins.avg_fill_level || 0;
    const activeRoutes = nodes.reduce((sum, n) => sum + (n.zone_status?.active_routes || 0), 0);

    $('total-bins').textContent = total;
    $('kpi-bins-sub').textContent = `across ${zones} zone${zones === 1 ? '' : 's'}`;
    $('overflowing-bins').textContent = over;
    $('overflow-meter').style.width = (total ? (over / total) * 100 : 0) + '%';
    $('avg-fill').textContent = Math.round(avg) + '%';
    $('avg-meter').style.width = Math.min(100, avg) + '%';
    $('routes-completed').textContent = totals.total_routes_completed || 0;
    $('kpi-routes-sub').textContent = `${activeRoutes} active now`;
    $('spillovers').textContent = totals.total_spillovers || 0;

    const election = status.election_status || {};
    const leaderEl = $('current-leader');
    if (election.current_leader) {
        const leaderNode = (election.nodes || {})[election.current_leader] || {};
        leaderEl.textContent = 'Zone ' + election.current_leader;
        leaderEl.className = 'kpi-value leader-active';
        $('kpi-term').textContent = `elected · term ${leaderNode.term || 0}`;
    } else {
        leaderEl.textContent = 'None';
        leaderEl.className = 'kpi-value leader-none';
        $('kpi-term').textContent = 'no election yet';
    }
}

// ---------------------------------------------------------------------------
// Bin fill gauges
// ---------------------------------------------------------------------------

function drawBinsMap() {
    const ctx = binsCtx;
    const { w, h } = clear(ctx, binsCanvas);
    binHits = [];
    if (!binsData.length) return emptyMessage(ctx, w, h, 'Waiting for bin telemetry…');

    const leader = String(lastStatus?.election_status?.current_leader ?? '');
    const zones = [...new Set(binsData.map(b => b.zone_id))].sort((a, b) => a - b);
    const pad = 10;
    const zoneW = (w - pad * (zones.length + 1)) / zones.length;
    const zoneH = h - pad * 2;

    zones.forEach((zoneId, zi) => {
        const zx = pad + zi * (zoneW + pad);
        const zy = pad;
        const zoneBins = binsData.filter(b => b.zone_id === zoneId)
            .sort((a, b) => a.bin_id.localeCompare(b.bin_id, undefined, { numeric: true }));
        const over = zoneBins.filter(b => b.fill_level >= 80).length;
        const isLeader = String(zoneId) === leader;

        // Zone panel
        roundRect(ctx, zx, zy, zoneW, zoneH, 8);
        ctx.fillStyle = palette.surface;
        ctx.fill();
        ctx.strokeStyle = isLeader ? withAlpha(palette.leader, 0.55) : palette.border;
        ctx.lineWidth = 1;
        ctx.stroke();

        // Header
        ctx.textBaseline = 'middle';
        ctx.textAlign = 'left';
        ctx.fillStyle = palette.text;
        ctx.font = font(12.5, 600);
        const title = 'Zone ' + zoneId;
        ctx.fillText(title, zx + 10, zy + 16);
        if (isLeader && zoneW > 150) {
            const tx = zx + 10 + ctx.measureText(title).width + 6;
            ctx.fillStyle = palette.leader;
            ctx.font = font(10.5, 700);
            ctx.fillText('★ LEADER', tx, zy + 16.5);
        }
        if (zoneW > 110) {
            ctx.textAlign = 'right';
            ctx.font = font(11, 500);
            ctx.fillStyle = over ? palette.critical : palette.faint;
            ctx.fillText(`${over}/${zoneBins.length} over`, zx + zoneW - 10, zy + 16);
        }

        // Pick the column count that gives the largest gauge
        const innerX = zx + 8, innerY = zy + 32, innerW = zoneW - 16, innerH = zoneH - 38;
        const n = zoneBins.length;
        let best = { cols: 1, gw: 0 };
        for (let cols = 1; cols <= n; cols++) {
            const rows = Math.ceil(n / cols);
            const gw = Math.min((innerW / cols) * 0.55, (innerH / rows - 16) / 1.35, 26);
            if (gw > best.gw) best = { cols, gw };
        }
        const cols = best.cols;
        const rows = Math.ceil(n / cols);
        const cw = innerW / cols, ch = innerH / rows;
        const gw = Math.max(6, best.gw), gh = gw * 1.3;
        const showLabel = ch - gh >= 14 && cw >= 24;

        zoneBins.forEach((bin, i) => {
            const cx = innerX + (i % cols) * cw + cw / 2;
            const cy = innerY + Math.floor(i / cols) * ch + (ch - gh - (showLabel ? 13 : 0)) / 2;
            const gx = cx - gw / 2;
            const fill = Math.max(0, Math.min(100, bin.fill_level));
            const color = tierColor(fill);

            // Lid
            ctx.fillStyle = palette.borderStrong;
            roundRect(ctx, gx - 1.5, cy - 3.5, gw + 3, 2.5, 1.2);
            ctx.fill();

            // Body
            roundRect(ctx, gx, cy, gw, gh, 3);
            ctx.fillStyle = palette.surface2;
            ctx.fill();

            // Fill level
            const fh = (gh - 2) * fill / 100;
            if (fh > 0) {
                ctx.save();
                roundRect(ctx, gx, cy, gw, gh, 3);
                ctx.clip();
                ctx.fillStyle = color;
                ctx.fillRect(gx, cy + gh - fh - 1, gw, fh + 1);
                ctx.restore();
            }

            roundRect(ctx, gx, cy, gw, gh, 3);
            ctx.strokeStyle = fill >= 80 ? color : palette.borderStrong;
            ctx.lineWidth = 1;
            ctx.stroke();

            if (showLabel) {
                ctx.textAlign = 'center';
                ctx.textBaseline = 'top';
                ctx.font = font(10.5, fill >= 80 ? 700 : 500);
                ctx.fillStyle = fill >= 80 ? color : palette.muted;
                ctx.fillText(Math.round(fill) + '%', cx, cy + gh + 3);
            }

            binHits.push({ x: gx - 4, y: cy - 4, w: gw + 8, h: gh + (showLabel ? 16 : 8), bin });
        });
    });
}

// ---------------------------------------------------------------------------
// Route map (bins at their real coordinates)
// ---------------------------------------------------------------------------

function sortedRoutes() {
    return [...routesData].sort((a, b) =>
        a.zone_id !== b.zone_id ? a.zone_id - b.zone_id : a.truck_id.localeCompare(b.truck_id));
}

function truckLabel(route) {
    const m = /truck_\d+_(\d+)/.exec(route.truck_id);
    return `Zone ${route.zone_id} · Truck ${m ? m[1] : route.truck_id}`;
}

function renderRouteLegend() {
    const el = $('route-legend');
    el.textContent = '';
    sortedRoutes().forEach((route, ri) => {
        const chip = document.createElement('span');
        chip.className = 'chip';
        const sw = document.createElement('i');
        sw.className = 'swatch';
        sw.style.background = ROUTE_COLORS[ri % ROUTE_COLORS.length];
        chip.append(sw, `${truckLabel(route)} · ${route.bin_count} stops · ${route.total_distance.toFixed(1)} u`);
        el.append(chip);
    });
}

function drawRoutes() {
    const ctx = routesCtx;
    const { w, h } = clear(ctx, routesCanvas);
    routeHits = [];
    renderRouteLegend();
    if (!binsData.length) return emptyMessage(ctx, w, h, 'Waiting for bin telemetry…');

    // Bins are placed at x = (zone-1)*100 + [0, 80), y = [0, 80)
    const zoneCount = Math.max(lastStatus?.configuration?.zones || 0,
        ...binsData.map(b => Math.floor(b.x / 100) + 1));
    const worldW = zoneCount * 100;
    const worldH = 85;
    const pad = 22, top = 28;
    const scale = Math.min((w - pad * 2) / worldW, (h - top - pad) / worldH);
    const ox = (w - worldW * scale) / 2;
    const oy = top + (h - top - pad - worldH * scale) / 2;
    const px = (x) => ox + (x + 10) * scale;
    const py = (y) => oy + (y + 2.5) * scale;

    // Zone bands
    for (let z = 0; z < zoneCount; z++) {
        const x0 = ox + z * 100 * scale, x1 = ox + (z + 1) * 100 * scale;
        ctx.fillStyle = z % 2 ? palette.plot : palette.surface;
        roundRect(ctx, x0 + 2, oy, x1 - x0 - 4, worldH * scale, 6);
        ctx.fill();
        ctx.strokeStyle = palette.border;
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.fillStyle = palette.faint;
        ctx.font = font(11, 600);
        ctx.textAlign = 'left';
        ctx.textBaseline = 'bottom';
        ctx.fillText('ZONE ' + (z + 1), x0 + 6, oy - 6);
    }

    // All bins, coloured by tier
    const onRoute = new Set(routesData.flatMap(r => (r.bins || []).map(b => b.bin_id)));
    binsData.forEach(bin => {
        ctx.beginPath();
        ctx.arc(px(bin.x), py(bin.y), 3.5, 0, Math.PI * 2);
        ctx.fillStyle = withAlpha(tierColor(bin.fill_level), onRoute.has(bin.bin_id) ? 1 : 0.6);
        ctx.fill();
    });

    if (!routesData.length) {
        const msg = 'No active routes — trucks are dispatched when bins reach 80%';
        ctx.font = font(12.5);
        const tw = ctx.measureText(msg).width + 28;
        roundRect(ctx, w / 2 - tw / 2, h / 2 - 15, tw, 30, 15);
        ctx.fillStyle = palette.surface;
        ctx.fill();
        ctx.strokeStyle = palette.border;
        ctx.stroke();
        ctx.fillStyle = palette.muted;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(msg, w / 2, h / 2);
        return;
    }

    sortedRoutes().forEach((route, ri) => {
        const color = ROUTE_COLORS[ri % ROUTE_COLORS.length];
        const pts = (route.bins || []).map(b => ({ x: px(b.x), y: py(b.y), bin: b }));
        if (!pts.length) return;

        // Path in visit order
        ctx.strokeStyle = withAlpha(color, 0.85);
        ctx.lineWidth = 2.25;
        ctx.lineJoin = 'round';
        ctx.setLineDash([6, 4]);
        ctx.beginPath();
        pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
        ctx.stroke();
        ctx.setLineDash([]);

        // Direction arrows at segment midpoints
        for (let i = 1; i < pts.length; i++) {
            const a = pts[i - 1], b = pts[i];
            if (Math.hypot(b.x - a.x, b.y - a.y) < 34) continue;
            ctx.save();
            ctx.translate((a.x + b.x) / 2, (a.y + b.y) / 2);
            ctx.rotate(Math.atan2(b.y - a.y, b.x - a.x));
            ctx.beginPath();
            ctx.moveTo(4.5, 0); ctx.lineTo(-3.5, -4); ctx.lineTo(-3.5, 4); ctx.closePath();
            ctx.fillStyle = color;
            ctx.fill();
            ctx.restore();
        }

        // Numbered stops
        pts.forEach((p, i) => {
            const r = 8.5;
            ctx.beginPath();
            ctx.arc(p.x, p.y, r + 3, 0, Math.PI * 2);
            ctx.fillStyle = withAlpha(color, 0.18);
            ctx.fill();
            ctx.beginPath();
            ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();
            ctx.fillStyle = '#fff';
            ctx.font = font(9.5, 700);
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(String(i + 1), p.x, p.y + 0.5);
            routeHits.push({ x: p.x, y: p.y, r: r + 3, route, stop: i + 1, bin: p.bin });
        });
    });
}

// ---------------------------------------------------------------------------
// Fog node network
// ---------------------------------------------------------------------------

function drawNetwork() {
    const ctx = networkCtx;
    const { w, h } = clear(ctx, networkCanvas);
    if (!networkData.nodes.length) return emptyMessage(ctx, w, h, 'No fog nodes');

    const nodes = [...networkData.nodes].sort((a, b) => Number(a.id) - Number(b.id));
    const cx = w / 2, cy = h / 2 + 8;
    const nodeR = Math.max(17, Math.min(28, Math.min(w, h) / (nodes.length > 6 ? 12 : 9)));
    const ringR = nodes.length === 1 ? 0 : Math.max(40, Math.min(w / 2 - nodeR - 40, h / 2 - nodeR - 36));
    const pos = {};
    nodes.forEach((node, i) => {
        const ang = (i / nodes.length) * Math.PI * 2 - Math.PI / 2;
        pos[node.id] = { x: cx + Math.cos(ang) * ringR, y: cy + Math.sin(ang) * ringR };
    });
    const leader = nodes.find(n => n.is_leader);

    // Edges: peer links faint, leader links highlighted
    const drawn = new Set();
    networkData.edges.forEach(edge => {
        const key = [edge.from, edge.to].sort().join('-');
        if (drawn.has(key)) return;
        drawn.add(key);
        const a = pos[edge.from], b = pos[edge.to];
        if (!a || !b) return;
        const leaderEdge = leader && (edge.from === leader.id || edge.to === leader.id);
        ctx.strokeStyle = leaderEdge ? withAlpha(palette.leader, 0.6) : palette.borderStrong;
        ctx.lineWidth = leaderEdge ? 1.75 : 1;
        ctx.setLineDash(leaderEdge ? [] : [4, 4]);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
    });
    ctx.setLineDash([]);

    const binsPerZone = Math.max(1, lastStatus?.configuration?.bins_per_zone || 15);
    nodes.forEach(node => {
        const p = pos[node.id];
        const color = node.is_leader ? palette.leader : palette.info;

        if (node.is_leader) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, nodeR + 6, 0, Math.PI * 2);
            ctx.fillStyle = withAlpha(color, 0.16);
            ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, nodeR, 0, Math.PI * 2);
        ctx.fillStyle = palette.surface;
        ctx.fill();
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = color;
        ctx.stroke();

        // Load arc: share of this zone's bins that are overflowing
        const load = Math.min(1, (node.active_bins || 0) / binsPerZone);
        if (load > 0) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, nodeR - 5, -Math.PI / 2, -Math.PI / 2 + load * Math.PI * 2);
            ctx.strokeStyle = palette.critical;
            ctx.lineWidth = 3;
            ctx.stroke();
        }

        ctx.fillStyle = palette.text;
        ctx.font = font(Math.round(nodeR * 0.55), 700);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('Z' + node.id, p.x, p.y + 0.5);

        haloText(ctx, node.state || '', p.x, p.y + nodeR + 13, font(10, 600),
            node.is_leader ? palette.leader : palette.faint);
        haloText(ctx, `${node.active_bins || 0} over · ${node.routes_completed || 0} done`,
            p.x, p.y + nodeR + 26, font(10, 500), palette.muted);
    });

    // Legend
    const items = [[palette.leader, 'Leader', false], [palette.info, 'Follower', false], [palette.critical, 'Overflow load', true]];
    ctx.font = font(11);
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    let lx = 12;
    items.forEach(([color, label, arc]) => {
        ctx.beginPath();
        ctx.arc(lx + 5, 16, 4.5, arc ? -Math.PI / 2 : 0, arc ? Math.PI : Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.lineWidth = arc ? 2.5 : 2;
        ctx.stroke();
        ctx.fillStyle = palette.muted;
        ctx.fillText(label, lx + 15, 16);
        lx += 15 + ctx.measureText(label).width + 14;
    });
}

// ---------------------------------------------------------------------------
// Tooltips
// ---------------------------------------------------------------------------

function attachTooltip(canvas, tooltip, findHit, render) {
    canvas.addEventListener('mousemove', (e) => {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left, my = e.clientY - rect.top;
        const hit = findHit(mx, my);
        if (!hit) {
            tooltip.hidden = true;
            return;
        }
        tooltip.textContent = '';
        render(tooltip, hit);
        tooltip.hidden = false;
        tooltip.style.left = Math.min(Math.max(mx, 80), rect.width - 80) + 'px';
        tooltip.style.top = Math.max(my, 52) + 'px';
    });
    canvas.addEventListener('mouseleave', () => { tooltip.hidden = true; });
}

function tooltipLines(tooltip, title, lines) {
    const strong = document.createElement('strong');
    strong.textContent = title;
    tooltip.append(strong);
    lines.forEach(line => tooltip.append(document.createElement('br'), line));
}

attachTooltip(binsCanvas, $('bins-tooltip'),
    (x, y) => binHits.find(r => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h),
    (tip, hit) => {
        const fill = hit.bin.fill_level;
        tooltipLines(tip, hit.bin.bin_id, [`${fill.toFixed(1)}% · ${tierOf(fill).label} priority`]);
    });

attachTooltip(routesCanvas, $('routes-tooltip'),
    (x, y) => routeHits.find(r => Math.hypot(x - r.x, y - r.y) <= r.r),
    (tip, hit) => tooltipLines(tip, truckLabel(hit.route),
        [`Stop ${hit.stop} of ${hit.route.bin_count}: ${hit.bin.bin_id}`]));

// ---------------------------------------------------------------------------
// Event log
// ---------------------------------------------------------------------------

function eventKey(e) {
    return e.timestamp + '|' + e.type + '|' + e.message;
}

function updateEventLog() {
    const events = serverEvents.concat(localEvents)
        .map(e => ({ ...e, date: new Date(e.timestamp) }))
        .sort((a, b) => b.date - a.date)
        .slice(0, 40);

    eventLogEl.textContent = '';
    if (!events.length) {
        const li = document.createElement('li');
        li.className = 'empty';
        li.textContent = 'No events yet';
        eventLogEl.append(li);
        return;
    }

    const firstRender = seenEventKeys.size === 0;
    events.forEach(event => {
        const key = eventKey(event);
        const li = document.createElement('li');
        li.className = 'event-item';
        if (!firstRender && !seenEventKeys.has(key)) li.classList.add('is-new');
        seenEventKeys.add(key);

        const time = document.createElement('span');
        time.className = 'event-time';
        time.textContent = isNaN(event.date) ? '' : formatTime(event.date);

        const type = document.createElement('span');
        type.className = 'event-type event-type-' + event.type;
        type.textContent = event.type;

        const msg = document.createElement('span');
        msg.className = 'event-message';
        msg.textContent = event.message;

        li.append(time, type, msg);
        eventLogEl.append(li);
    });

    if (seenEventKeys.size > 500) seenEventKeys = new Set(events.map(eventKey));
}

function addEvent(type, message) {
    localEvents.push({ timestamp: new Date().toISOString(), type, message });
    if (localEvents.length > 30) localEvents.shift();
    updateEventLog();
}

// ---------------------------------------------------------------------------
// Module cards
// ---------------------------------------------------------------------------

function renderStats(id, rows) {
    const dl = $(id);
    dl.textContent = '';
    rows.forEach(([label, value, cls]) => {
        const row = document.createElement('div');
        const dt = document.createElement('dt');
        dt.textContent = label;
        const dd = document.createElement('dd');
        dd.textContent = value;
        if (cls) dd.className = cls;
        row.append(dt, dd);
        dl.append(row);
    });
}

function updateModuleStats(status) {
    const nodes = Object.values(status.fog_nodes?.nodes || {});
    const totals = status.fog_nodes?.system_totals || {};
    const sum = (fn) => nodes.reduce((acc, n) => acc + (fn(n) || 0), 0);

    renderStats('route-stats', [
        ['Active routes', sum(n => n.zone_status?.active_routes)],
        ['Completed', totals.total_routes_completed || 0],
        ['Bins serviced', totals.total_bins_serviced || 0],
    ]);

    const peers = nodes.map(n => n.communication_status?.peer_discovery?.total_peers || 0);
    renderStats('comm-stats', [
        ['Peers per node', nodes.length ? `${Math.min(...peers)} of ${Math.max(0, nodes.length - 1)}` : '—'],
        ['Messages sent', sum(n => n.communication_status?.message_router?.messages_sent).toLocaleString()],
        ['Spillovers ok / rejected',
            `${sum(n => n.communication_status?.spillover_manager?.completed_spillovers)} / ${sum(n => n.communication_status?.spillover_manager?.rejected_spillovers)}`],
    ]);

    const election = status.election_status || {};
    const leaderNode = (election.nodes || {})[election.current_leader] || {};
    renderStats('election-stats', [
        ['State', election.current_leader ? 'Leader elected' : 'Electing', election.current_leader ? 'ok' : ''],
        ['Leader', election.current_leader ? 'Zone ' + election.current_leader : '—'],
        ['Term', leaderNode.term || 0],
    ]);

    const ledger = status.fog_nodes?.ledger;
    renderStats('ledger-stats', ledger ? [
        ['Blocks', ledger.blocks],
        ['Committed events', (ledger.committed_transactions || 0).toLocaleString()],
        ['Quorum', `${ledger.quorum_size} of ${ledger.validators}`],
        ['Chain integrity', ledger.chain_valid ? 'Verified' : 'Broken', ledger.chain_valid ? 'ok' : 'bad'],
    ] : [['Status', 'Unavailable']]);
}

// ---------------------------------------------------------------------------
// Startup
// ---------------------------------------------------------------------------

// Viewer mode: the simulation is shared by every visitor, so if it is already
// running (e.g. autostarted on the server) attach to it instead of restarting it.
async function attachToRunningSystem() {
    try {
        const response = await fetch(`${API_BASE}/api/system/status`);
        if (!response.ok) return false;
        const status = await response.json();
        if (!status.running) return false;

        const config = status.configuration || {};
        if (config.zones) $('zones').value = config.zones;
        if (config.bins_per_zone) $('bins').value = config.bins_per_zone;
        if (config.trucks_per_zone) $('trucks').value = config.trucks_per_zone;

        isRunning = true;
        updateUIState();
        startUpdates();
        return true;
    } catch (error) {
        console.error('Error reading system status:', error);
        setPill('offline');
        return false;
    }
}

if (HOSTED) document.body.classList.add('is-hosted');
readPalette();
initCanvases();
updateUIState();
redrawAll();
renderStats('route-stats', [['Active routes', 0], ['Completed', 0], ['Bins serviced', 0]]);
renderStats('comm-stats', [['Peers per node', '—'], ['Messages sent', 0], ['Spillovers ok / rejected', '0 / 0']]);
renderStats('election-stats', [['State', 'Idle'], ['Leader', '—'], ['Term', 0]]);
renderStats('ledger-stats', [['Blocks', 0], ['Committed events', 0], ['Quorum', '—'], ['Chain integrity', '—']]);
if (HOSTED) {
    // Read-only: poll the cloud snapshot whether or not the fog layer is up right now
    // (the footer's /docs link only exists on the local FastAPI server)
    $('footnote').textContent = 'Read-only view of data published by the fog layer to Supabase.';
    setPill('waiting');
    isRunning = true;
    startUpdates();
    addEvent('SYSTEM', 'Cloud dashboard — read-only view of the fog layer');
} else {
    attachToRunningSystem().then(attached => {
        addEvent('SYSTEM', attached
            ? 'Dashboard attached to the running simulation'
            : 'Dashboard ready — press Start to run the simulation');
    });
}
