// Smart Waste Management System - Web UI Controller with HiDPI Support

const API_BASE = '';
let updateInterval = null;
let isRunning = false;

// DOM Elements
const startBtn = document.getElementById('start-btn');
const stopBtn = document.getElementById('stop-btn');
const triggerElectionBtn = document.getElementById('trigger-election-btn');
const systemStatus = document.getElementById('system-status');
const totalBinsEl = document.getElementById('total-bins');
const overflowingBinsEl = document.getElementById('overflowing-bins');
const routesCompletedEl = document.getElementById('routes-completed');
const currentLeaderEl = document.getElementById('current-leader');
const eventLogEl = document.getElementById('event-log');

// Canvas elements
const binsCanvas = document.getElementById('bins-canvas');
const routesCanvas = document.getElementById('routes-canvas');
const networkCanvas = document.getElementById('network-canvas');

// Canvas contexts with willReadFrequently for better performance
const binsCtx = binsCanvas.getContext('2d', { willReadFrequently: true });
const routesCtx = routesCanvas.getContext('2d', { willReadFrequently: true });
const networkCtx = networkCanvas.getContext('2d', { willReadFrequently: true });

// Data storage
let binsData = [];
let routesData = [];
let networkData = { nodes: [], edges: [] };
let eventsData = [];

// Setup HiDPI canvas
function setupCanvas(canvas, ctx) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    const cssWidth = Math.max(1, Math.floor(rect.width));
    const cssHeight = Math.max(1, Math.floor(rect.height));

    // Reset transform before resizing so scale does not compound over time.
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    
    // Set actual size in memory (scaled to account for extra pixel density)
    canvas.width = Math.round(cssWidth * dpr);
    canvas.height = Math.round(cssHeight * dpr);
    
    // Normalize coordinate system to use css pixels
    ctx.scale(dpr, dpr);
    
    // Set display size (css pixels)
    canvas.style.width = cssWidth + 'px';
    canvas.style.height = cssHeight + 'px';
}

// Initialize canvases
function initCanvases() {
    setupCanvas(binsCanvas, binsCtx);
    setupCanvas(routesCanvas, routesCtx);
    setupCanvas(networkCanvas, networkCtx);
}

// Event Listeners
startBtn.addEventListener('click', startSystem);
stopBtn.addEventListener('click', stopSystem);
triggerElectionBtn.addEventListener('click', triggerElection);
window.addEventListener('resize', () => {
    initCanvases();
    drawBinsMap();
    drawRoutes();
    drawNetwork();
});

async function startSystem() {
    const zones = parseInt(document.getElementById('zones').value);
    const bins = parseInt(document.getElementById('bins').value);
    const trucks = parseInt(document.getElementById('trucks').value);
    
    const config = {
        zones: zones,
        bins_per_zone: bins,
        trucks_per_zone: trucks,
        update_interval: 3
    };
    
    try {
        const response = await fetch(`${API_BASE}/api/system/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        if (response.ok) {
            isRunning = true;
            updateUIState();
            startUpdates();
            addEvent('SYSTEM', 'System started');
        }
    } catch (error) {
        console.error('Error starting system:', error);
        addEvent('SYSTEM', 'Error: ' + error.message);
    }
}

async function stopSystem() {
    try {
        const response = await fetch(`${API_BASE}/api/system/stop`, { method: 'POST' });
        if (response.ok) {
            isRunning = false;
            updateUIState();
            stopUpdates();
            addEvent('SYSTEM', 'System stopped');
        }
    } catch (error) {
        console.error('Error stopping system:', error);
    }
}

async function triggerElection() {
    try {
        await fetch(`${API_BASE}/api/election/trigger`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initiator_zone: null })
        });
        addEvent('ELECTION', 'Election triggered');
    } catch (error) {
        console.error('Error:', error);
    }
}

function updateUIState() {
    if (isRunning) {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        systemStatus.textContent = 'Running';
        systemStatus.className = 'status-value status-running';
        document.getElementById('zones').disabled = true;
        document.getElementById('bins').disabled = true;
        document.getElementById('trucks').disabled = true;
    } else {
        startBtn.disabled = false;
        stopBtn.disabled = true;
        systemStatus.textContent = 'Stopped';
        systemStatus.className = 'status-value status-stopped';
        document.getElementById('zones').disabled = false;
        document.getElementById('bins').disabled = false;
        document.getElementById('trucks').disabled = false;
    }
}

function startUpdates() {
    if (updateInterval) clearInterval(updateInterval);
    updateInterval = setInterval(updateAllData, 1000);
    updateAllData();
}

function stopUpdates() {
    if (updateInterval) {
        clearInterval(updateInterval);
        updateInterval = null;
    }
}

async function updateAllData() {
    if (!isRunning) return;
    
    try {
        const [statusRes, binsRes, routesRes, networkRes, eventsRes] = await Promise.all([
            fetch(`${API_BASE}/api/system/status`),
            fetch(`${API_BASE}/api/bins`),
            fetch(`${API_BASE}/api/routes`),
            fetch(`${API_BASE}/api/network`),
            fetch(`${API_BASE}/api/events?limit=50`)
        ]);
        
        const status = await statusRes.json();
        binsData = await binsRes.json();
        routesData = await routesRes.json();
        networkData = await networkRes.json();
        eventsData = await eventsRes.json();
        
        updateStatusDisplay(status);
        drawBinsMap();
        drawRoutes();
        drawNetwork();
        updateEventLog();
        updateModuleStats(status);
    } catch (error) {
        console.error('Error:', error);
    }
}

function updateStatusDisplay(status) {
    if (status.bin_statistics) {
        totalBinsEl.textContent = status.bin_statistics.total_bins || 0;
        overflowingBinsEl.textContent = status.bin_statistics.overflowing_bins || 0;
    }
    
    if (status.fog_nodes?.system_totals) {
        routesCompletedEl.textContent = status.fog_nodes.system_totals.total_routes_completed || 0;
    }
    
    if (status.election_status?.current_leader) {
        currentLeaderEl.textContent = 'Zone ' + status.election_status.current_leader;
        currentLeaderEl.className = 'status-value leader-active';
    } else {
        currentLeaderEl.textContent = 'None';
        currentLeaderEl.className = 'status-value leader-none';
    }
}

function drawBinsMap() {
    const ctx = binsCtx;
    const width = binsCanvas.parentElement.clientWidth;
    const height = binsCanvas.parentElement.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    
    // Clear
    ctx.fillStyle = '#0a0f1a';
    ctx.fillRect(0, 0, width, height);
    
    if (!binsData.length) return;
    
    const zones = [...new Set(binsData.map(b => b.zone_id))].sort((a, b) => a - b);
    const zoneWidth = width / zones.length;
    const maxBinsPerZone = Math.max(...zones.map(z => binsData.filter(b => b.zone_id === z).length));
    const cols = 5;
    const binSpacing = Math.min(55, (zoneWidth - 40) / cols);
    const rowSpacing = Math.min(55, (height - 60) / Math.ceil(maxBinsPerZone / cols));
    
    // Zone separators
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 2;
    for (let i = 1; i < zones.length; i++) {
        const x = i * zoneWidth;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
    }
    
    zones.forEach((zoneId, zoneIndex) => {
        const zoneBins = binsData.filter(b => b.zone_id === zoneId);
        const startX = zoneIndex * zoneWidth;
        
        zoneBins.forEach((bin, idx) => {
            const col = idx % cols;
            const row = Math.floor(idx / cols);
            const x = startX + 20 + col * binSpacing + binSpacing / 2;
            const y = 50 + row * rowSpacing + rowSpacing / 2;
            
            const fill = bin.fill_level;
            let color, glowColor;
            if (fill < 80) { color = '#22c55e'; glowColor = 'rgba(34, 197, 94, 0.3)'; }
            else if (fill < 85) { color = '#f59e0b'; glowColor = 'rgba(245, 158, 11, 0.3)'; }
            else if (fill < 95) { color = '#f97316'; glowColor = 'rgba(249, 115, 22, 0.3)'; }
            else { color = '#ef4444'; glowColor = 'rgba(239, 68, 68, 0.3)'; }
            
            // Glow effect
            ctx.beginPath();
            ctx.arc(x, y, 18, 0, Math.PI * 2);
            ctx.fillStyle = glowColor;
            ctx.fill();
            
            // Bin circle
            ctx.beginPath();
            ctx.arc(x, y, 14, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.stroke();
            
            // Percentage
            ctx.fillStyle = '#fff';
            ctx.font = `bold ${Math.max(10, 12 * dpr / 2)}px Arial`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(Math.round(fill) + '%', x, y + 1);
        });
        
        // Zone label
        ctx.fillStyle = '#3b82f6';
        ctx.font = `bold ${Math.max(14, 16 * dpr / 2)}px Arial`;
        ctx.textAlign = 'center';
        ctx.fillText('Zone ' + zoneId, startX + zoneWidth / 2, 25);
    });
}

function drawRoutes() {
    const ctx = routesCtx;
    const width = routesCanvas.parentElement.clientWidth;
    const height = routesCanvas.parentElement.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    
    ctx.fillStyle = '#0a0f1a';
    ctx.fillRect(0, 0, width, height);
    
    if (!routesData.length) {
        ctx.fillStyle = '#64748b';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('No active routes', width / 2, height / 2);
        return;
    }

    const orderedRoutes = [...routesData].sort((a, b) => {
        if (a.zone_id !== b.zone_id) return a.zone_id - b.zone_id;
        return a.truck_id.localeCompare(b.truck_id);
    });

    const laneCount = orderedRoutes.length;
    const laneGap = 14;
    const horizontalPadding = 16;
    const availableWidth = width - horizontalPadding * 2 - laneGap * (laneCount - 1);
    const laneWidth = availableWidth / Math.max(laneCount, 1);
    const colors = ['#7c3aed', '#f59e0b', '#22c55e', '#38bdf8', '#ef4444', '#14b8a6'];

    orderedRoutes.forEach((route, index) => {
        const laneX = horizontalPadding + index * (laneWidth + laneGap);
        const laneY = 18;
        const laneH = height - 36;
        const laneColor = colors[index % colors.length];

        // Lane card
        ctx.fillStyle = 'rgba(15, 23, 42, 0.7)';
        ctx.strokeStyle = 'rgba(71, 85, 105, 0.65)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.roundRect(laneX, laneY, laneWidth, laneH, 12);
        ctx.fill();
        ctx.stroke();

        // Header chip
        const chipW = Math.min(120, laneWidth - 18);
        const chipX = laneX + (laneWidth - chipW) / 2;
        ctx.fillStyle = laneColor;
        ctx.beginPath();
        ctx.roundRect(chipX, laneY + 12, chipW, 28, 8);
        ctx.fill();
        ctx.strokeStyle = '#e2e8f0';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.fillStyle = '#ffffff';
        ctx.font = `bold ${Math.max(10, 11 * dpr / 2)}px Arial`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const truckLabel = route.truck_id.replace('truck_', 'T');
        ctx.fillText(`Z${route.zone_id} ${truckLabel}`, laneX + laneWidth / 2, laneY + 26);

        // Truck marker
        const truckX = laneX + laneWidth / 2;
        const truckY = laneY + 64;
        ctx.fillStyle = laneColor;
        ctx.beginPath();
        ctx.roundRect(truckX - 18, truckY - 12, 36, 24, 7);
        ctx.fill();
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        const bins = route.bins || [];
        const routeTop = truckY + 22;
        const routeBottom = laneY + laneH - 44;
        const pathHeight = Math.max(60, routeBottom - routeTop);
        const binSpacing = bins.length ? pathHeight / Math.max(bins.length, 1) : 0;
        const offset = Math.min(laneWidth * 0.24, 42);

        const points = bins.map((bin, idx) => {
            const side = idx % 2 === 0 ? -1 : 1;
            return {
                x: truckX + side * offset,
                y: routeTop + binSpacing * (idx + 0.5),
                bin
            };
        });

        // Path segments in visit order
        let prev = { x: truckX, y: truckY + 12 };
        ctx.strokeStyle = laneColor;
        ctx.lineWidth = 2.5;
        ctx.setLineDash([7, 5]);
        points.forEach((point) => {
            const controlX = (prev.x + point.x) / 2;
            const controlY = prev.y + (point.y - prev.y) * 0.15;
            ctx.beginPath();
            ctx.moveTo(prev.x, prev.y);
            ctx.quadraticCurveTo(controlX, controlY, point.x, point.y);
            ctx.stroke();
            prev = point;
        });
        ctx.setLineDash([]);

        // Bin markers
        points.forEach((point, idx) => {
            ctx.beginPath();
            ctx.arc(point.x, point.y, 13, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(239, 68, 68, 0.26)';
            ctx.fill();

            ctx.beginPath();
            ctx.arc(point.x, point.y, 10.5, 0, Math.PI * 2);
            ctx.fillStyle = '#ef4444';
            ctx.fill();
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.8;
            ctx.stroke();

            ctx.fillStyle = '#ffffff';
            ctx.font = `bold ${Math.max(9, 10 * dpr / 2)}px Arial`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(String(idx + 1), point.x, point.y + 0.5);
        });

        // Route summary
        ctx.fillStyle = '#94a3b8';
        ctx.font = `${Math.max(10, 11 * dpr / 2)}px Arial`;
        ctx.textAlign = 'center';
        ctx.fillText(
            `${route.bin_count} bins | ${route.total_distance.toFixed(1)} km`,
            laneX + laneWidth / 2,
            laneY + laneH - 18
        );
    });
}

function drawNetwork() {
    const ctx = networkCtx;
    const width = networkCanvas.parentElement.clientWidth;
    const height = networkCanvas.parentElement.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    
    ctx.fillStyle = '#0a0f1a';
    ctx.fillRect(0, 0, width, height);
    
    if (!networkData.nodes.length) return;

    const topPadding = 58;
    const bottomPadding = 54;
    const sidePadding = 58;
    const layoutHeight = Math.max(80, height - topPadding - bottomPadding);
    const centerX = width / 2;
    const centerY = topPadding + layoutHeight / 2;
    const radius = Math.max(
        50,
        Math.min((width - sidePadding * 2) / 2, layoutHeight / 2) - 38
    );
    const nodePositions = {};

    const nodes = [...networkData.nodes].sort((a, b) => Number(a.id) - Number(b.id));

    // Calculate node positions in a padded circle to avoid clipping.
    nodes.forEach((node, index) => {
        const angle = (index / nodes.length) * Math.PI * 2 - Math.PI / 2;
        nodePositions[node.id] = {
            x: centerX + Math.cos(angle) * radius,
            y: centerY + Math.sin(angle) * radius
        };
    });
    
    // Draw unique connection lines.
    ctx.strokeStyle = 'rgba(100, 116, 139, 0.55)';
    ctx.lineWidth = 2.2;
    ctx.setLineDash([8, 4]);

    const drawnEdges = new Set();
    networkData.edges.forEach(edge => {
        const minNode = Math.min(edge.from, edge.to);
        const maxNode = Math.max(edge.from, edge.to);
        const edgeKey = `${minNode}-${maxNode}`;
        if (drawnEdges.has(edgeKey)) return;
        drawnEdges.add(edgeKey);

        const from = nodePositions[edge.from];
        const to = nodePositions[edge.to];
        if (from && to) {
            ctx.beginPath();
            ctx.moveTo(from.x, from.y);
            ctx.lineTo(to.x, to.y);
            ctx.stroke();
        }
    });
    
    ctx.setLineDash([]);
    
    // Draw nodes
    const nodeRadius = Math.max(26, Math.min(42, radius / 2.8));
    
    nodes.forEach(node => {
        const pos = nodePositions[node.id];
        if (!pos) return;
        
        // Outer glow for leader
        if (node.is_leader) {
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, nodeRadius + 8, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(251, 191, 36, 0.3)';
            ctx.fill();
        }
        
        // Node circle
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, nodeRadius, 0, Math.PI * 2);
        const gradient = ctx.createRadialGradient(
            pos.x - nodeRadius/3, pos.y - nodeRadius/3, 0,
            pos.x, pos.y, nodeRadius
        );
        if (node.is_leader) {
            gradient.addColorStop(0, '#fcd34d');
            gradient.addColorStop(1, '#f59e0b');
        } else {
            gradient.addColorStop(0, '#60a5fa');
            gradient.addColorStop(1, '#3b82f6');
        }
        ctx.fillStyle = gradient;
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 3;
        ctx.stroke();
        
        // Inner circle
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, nodeRadius * 0.6, 0, Math.PI * 2);
        ctx.fillStyle = '#1e293b';
        ctx.fill();
        
        // Zone label
        ctx.fillStyle = '#fff';
        ctx.font = `bold ${Math.max(14, 18 * dpr / 2)}px Arial`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('Z' + node.id, pos.x, pos.y);
        
        // Leader badge
        if (node.is_leader) {
            ctx.fillStyle = '#fbbf24';
            ctx.font = `bold ${Math.max(10, 12 * dpr / 2)}px Arial`;
            ctx.fillText('LEADER', pos.x, pos.y - nodeRadius - 15);
        }
        
        // State label
        ctx.fillStyle = '#94a3b8';
        ctx.font = `${Math.max(9, 11 * dpr / 2)}px Arial`;
        ctx.fillText(node.state, pos.x, pos.y + nodeRadius + 16);
    });
    
    // Legend
    const legendY = height - 18;
    ctx.font = `${Math.max(11, 12 * dpr / 2)}px Arial`;
    
    ctx.fillStyle = '#fbbf24';
    ctx.beginPath();
    ctx.arc(25, legendY - 4, 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillText('Leader', 40, legendY);
    
    ctx.fillStyle = '#3b82f6';
    ctx.beginPath();
    ctx.arc(100, legendY - 4, 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillText('Follower', 115, legendY);
}

function updateEventLog() {
    eventLogEl.innerHTML = '';
    
    eventsData.slice(-20).forEach(event => {
        const eventEl = document.createElement('div');
        eventEl.className = 'event-item';
        
        const time = new Date(event.timestamp).toLocaleTimeString([], { hour12: false });
        const typeClass = 'event-type-' + event.type;
        
        eventEl.innerHTML = '<span class="event-timestamp">' + time + '</span>' +
            '<span class="event-type ' + typeClass + '">' + event.type + '</span>' +
            '<span class="event-message">' + event.message + '</span>';
        
        eventLogEl.appendChild(eventEl);
    });
    
    eventLogEl.scrollTop = eventLogEl.scrollHeight;
}

function addEvent(type, message) {
    eventsData.push({
        timestamp: new Date().toISOString(),
        type: type,
        message: message
    });
    if (eventsData.length > 100) eventsData.shift();
    updateEventLog();
}

function updateModuleStats(status) {
    if (status.fog_nodes?.system_totals) {
        const totals = status.fog_nodes.system_totals;
        const activeRoutes = Object.values(status.fog_nodes.nodes || {}).reduce(
            (sum, node) => sum + (node.zone_status?.active_routes || 0), 0
        );
        document.getElementById('route-stats').innerHTML = 
            '<span>Active: ' + activeRoutes + '</span>' +
            '<span>Completed: ' + (totals.total_routes_completed || 0) + '</span>';
        document.getElementById('comm-stats').innerHTML = 
            '<span>Peers: ' + Math.max(0, Object.keys(status.fog_nodes.nodes || {}).length - 1) + '</span>' +
            '<span>Spillovers: ' + (totals.total_spillovers || 0) + '</span>';
    }
    
    if (status.election_status) {
        const election = status.election_status;
        const leaderNode = Object.values(election.nodes || {}).find(n => n.state === 'LEADER');
        document.getElementById('election-stats').innerHTML = 
            '<span>State: ' + (election.current_leader ? 'LEADER_ELECTED' : 'ELECTING') + '</span>' +
            '<span>Term: ' + (leaderNode?.term || 0) + '</span>';
    }
}

// Initialize
initCanvases();
updateUIState();
addEvent('SYSTEM', 'Web UI ready. Click Start System to begin.');
