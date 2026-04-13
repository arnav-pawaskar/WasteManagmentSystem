// Smart Waste Management System - Web UI Controller

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

// Canvas contexts
const binsCanvas = document.getElementById('bins-canvas');
const routesCanvas = document.getElementById('routes-canvas');
const networkCanvas = document.getElementById('network-canvas');
const binsCtx = binsCanvas.getContext('2d');
const routesCtx = routesCanvas.getContext('2d');
const networkCtx = networkCanvas.getContext('2d');

// Data storage
let binsData = [];
let routesData = [];
let networkData = { nodes: [], edges: [] };
let eventsData = [];

// Event Listeners
startBtn.addEventListener('click', startSystem);
stopBtn.addEventListener('click', stopSystem);
triggerElectionBtn.addEventListener('click', triggerElection);

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
            addEvent('SYSTEM', 'System started with configuration');
        }
    } catch (error) {
        console.error('Error starting system:', error);
        addEvent('SYSTEM', 'Error starting system: ' + error.message);
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
        const response = await fetch(`${API_BASE}/api/election/trigger`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initiator_zone: null })
        });
        const result = await response.json();
        addEvent('ELECTION', 'Leader election triggered');
    } catch (error) {
        console.error('Error triggering election:', error);
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
        // Fetch all data in parallel
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
        console.error('Error updating data:', error);
    }
}

function updateStatusDisplay(status) {
    if (status.bin_statistics) {
        totalBinsEl.textContent = status.bin_statistics.total_bins || 0;
        overflowingBinsEl.textContent = status.bin_statistics.overflowing_bins || 0;
    }
    
    if (status.fog_nodes && status.fog_nodes.system_totals) {
        routesCompletedEl.textContent = status.fog_nodes.system_totals.total_routes_completed || 0;
    }
    
    if (status.election_status && status.election_status.current_leader) {
        const leaderId = status.election_status.current_leader;
        currentLeaderEl.textContent = 'Zone ' + leaderId;
        currentLeaderEl.className = 'status-value leader-active';
    } else {
        currentLeaderEl.textContent = 'None';
        currentLeaderEl.className = 'status-value leader-none';
    }
}

function drawBinsMap() {
    const ctx = binsCtx;
    const width = binsCanvas.width;
    const height = binsCanvas.height;
    
    // Clear canvas
    ctx.fillStyle = '#0a0f1a';
    ctx.fillRect(0, 0, width, height);
    
    if (!binsData.length) return;
    
    // Calculate zone positions
    const zones = [...new Set(binsData.map(b => b.zone_id))].sort((a, b) => a - b);
    const zoneWidth = width / zones.length;
    
    // Draw zone separators
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 2;
    for (let i = 1; i < zones.length; i++) {
        const x = i * zoneWidth;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
    }
    
    // Draw bins
    zones.forEach((zoneId, zoneIndex) => {
        const zoneBins = binsData.filter(b => b.zone_id === zoneId);
        const startX = zoneIndex * zoneWidth;
        
        zoneBins.forEach((bin, idx) => {
            const col = idx % 5;
            const row = Math.floor(idx / 5);
            const x = startX + 20 + col * 50;
            const y = 30 + row * 50;
            
            // Bin color based on fill level
            const fill = bin.fill_level;
            let color;
            if (fill < 80) color = '#22c55e';
            else if (fill < 85) color = '#f59e0b';
            else if (fill < 95) color = '#f97316';
            else color = '#ef4444';
            
            // Draw bin circle
            ctx.beginPath();
            ctx.arc(x + 15, y + 15, 12, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();
            ctx.strokeStyle = '#334155';
            ctx.lineWidth = 2;
            ctx.stroke();
            
            // Draw fill percentage
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 10px Arial';
            ctx.textAlign = 'center';
            ctx.fillText(Math.round(fill) + '%', x + 15, y + 19);
        });
        
        // Zone label
        ctx.fillStyle = '#3b82f6';
        ctx.font = 'bold 14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Zone ' + zoneId, startX + zoneWidth / 2, 20);
    });
}

function drawRoutes() {
    const ctx = routesCtx;
    const width = routesCanvas.width;
    const height = routesCanvas.height;
    
    // Clear canvas
    ctx.fillStyle = '#0a0f1a';
    ctx.fillRect(0, 0, width, height);
    
    if (!routesData.length) {
        ctx.fillStyle = '#64748b';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('No active routes', width / 2, height / 2);
        return;
    }
    
    // Calculate zone positions
    const zones = [...new Set(routesData.map(r => r.zone_id))].sort((a, b) => a - b);
    const zoneWidth = width / Math.max(zones.length, 1);
    
    routesData.forEach(route => {
        const zoneIndex = zones.indexOf(route.zone_id);
        const startX = zoneIndex * zoneWidth;
        const centerX = startX + zoneWidth / 2;
        const truckColor = ['#3b82f6', '#8b5cf6', '#f59e0b'][route.zone_id % 3];
        
        // Draw truck
        ctx.fillStyle = truckColor;
        ctx.fillRect(centerX - 20, 30, 40, 30);
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.strokeRect(centerX - 20, 30, 40, 30);
        
        // Truck label
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 12px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Truck ' + route.truck_id, centerX, 50);
        
        // Draw route bins
        if (route.bins.length) {
            ctx.beginPath();
            ctx.moveTo(centerX, 60);
            
            route.bins.forEach((bin, idx) => {
                const binY = 100 + idx * 35;
                const binX = centerX + (idx % 2 === 0 ? -30 : 30);
                
                ctx.lineTo(binX, binY);
                
                // Draw bin point
                ctx.fillStyle = '#ef4444';
                ctx.beginPath();
                ctx.arc(binX, binY, 8, 0, Math.PI * 2);
                ctx.fill();
                ctx.stroke();
                
                // Bin label
                ctx.fillStyle = '#fff';
                ctx.font = '10px Arial';
                ctx.fillText(bin.bin_id.split('_').slice(1).join('_'), binX + 12, binY + 3);
            });
            
            ctx.strokeStyle = truckColor;
            ctx.lineWidth = 2;
            ctx.stroke();
        }
        
        // Route info
        ctx.fillStyle = '#94a3b8';
        ctx.font = '11px Arial';
        ctx.fillText(route.bin_count + ' bins, ' + route.total_distance.toFixed(1) + ' units', centerX, height - 30);
    });
}

function drawNetwork() {
    const ctx = networkCtx;
    const width = networkCanvas.width;
    const height = networkCanvas.height;
    
    // Clear canvas
    ctx.fillStyle = '#0a0f1a';
    ctx.fillRect(0, 0, width, height);
    
    if (!networkData.nodes.length) return;
    
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) / 3;
    const nodePositions = {};
    
    // Calculate node positions in a circle
    networkData.nodes.forEach((node, index) => {
        const angle = (index / networkData.nodes.length) * Math.PI * 2 - Math.PI / 2;
        nodePositions[node.id] = {
            x: centerX + Math.cos(angle) * radius,
            y: centerY + Math.sin(angle) * radius
        };
    });
    
    // Draw edges (peer connections)
    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    
    networkData.edges.forEach(edge => {
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
    networkData.nodes.forEach(node => {
        const pos = nodePositions[node.id];
        if (!pos) return;
        
        // Node circle
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 35, 0, Math.PI * 2);
        ctx.fillStyle = node.is_leader ? '#fbbf24' : '#3b82f6';
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 3;
        ctx.stroke();
        
        // Inner circle for state
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 25, 0, Math.PI * 2);
        ctx.fillStyle = '#1e293b';
        ctx.fill();
        
        // Node label
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 16px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Z' + node.id, pos.x, pos.y + 5);
        
        // Leader indicator (L) instead of crown
        if (node.is_leader) {
            ctx.fillStyle = '#fbbf24';
            ctx.font = 'bold 14px Arial';
            ctx.fillText('L', pos.x, pos.y - 45);
        }
        
        // Status below
        ctx.fillStyle = '#94a3b8';
        ctx.font = '10px Arial';
        ctx.fillText(node.state, pos.x, pos.y + 50);
    });
    
    // Legend
    ctx.font = '12px Arial';
    ctx.fillStyle = '#fbbf24';
    ctx.fillText('* Leader', 20, height - 40);
    ctx.fillStyle = '#3b82f6';
    ctx.fillText('* Follower', 20, height - 20);
}

function updateEventLog() {
    eventLogEl.innerHTML = '';
    
    eventsData.forEach(event => {
        const eventEl = document.createElement('div');
        eventEl.className = 'event-item';
        
        const time = new Date(event.timestamp).toLocaleTimeString();
        const typeClass = 'event-type-' + event.type;
        
        eventEl.innerHTML = '<span class="event-timestamp">' + time + '</span>' +
            '<span class="event-type ' + typeClass + '">' + event.type + '</span>' +
            '<span class="event-message">' + event.message + '</span>';
        
        eventLogEl.appendChild(eventEl);
    });
    
    // Auto-scroll to bottom
    eventLogEl.scrollTop = eventLogEl.scrollHeight;
}

function addEvent(type, message) {
    const event = {
        timestamp: new Date().toISOString(),
        type: type,
        message: message
    };
    eventsData.push(event);
    if (eventsData.length > 50) eventsData.shift();
    updateEventLog();
}

function updateModuleStats(status) {
    // Route stats
    if (status.fog_nodes && status.fog_nodes.system_totals) {
        const totals = status.fog_nodes.system_totals;
        const activeRoutes = Object.values(status.fog_nodes.nodes || {}).reduce(
            (sum, node) => sum + (node.zone_status?.active_routes || 0), 0
        );
        document.getElementById('route-stats').innerHTML = 
            '<span>Active: ' + activeRoutes + '</span>' +
            '<span>Completed: ' + (totals.total_routes_completed || 0) + '</span>';
        document.getElementById('comm-stats').innerHTML = 
            '<span>Peers: ' + (Object.keys(status.fog_nodes.nodes || {}).length - 1) + '</span>' +
            '<span>Spillovers: ' + (totals.total_spillovers || 0) + '</span>';
    }
    
    // Election stats
    if (status.election_status) {
        const election = status.election_status;
        const leaderNode = Object.values(election.nodes || {}).find(n => n.state === 'LEADER');
        document.getElementById('election-stats').innerHTML = 
            '<span>State: ' + (election.current_leader ? 'LEADER_ELECTED' : 'ELECTING') + '</span>' +
            '<span>Term: ' + (leaderNode?.term || 0) + '</span>';
    }
}

// Handle window resize
window.addEventListener('resize', () => {
    drawBinsMap();
    drawRoutes();
    drawNetwork();
});

// Initial state
updateUIState();
addEvent('SYSTEM', 'Web UI loaded. Click Start System to begin.');
