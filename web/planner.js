var LOCAL_URL = 'http://localhost:7071/api/DivePlanner';
var PROD_URL  = 'https://gasblender-tcif7s.azurewebsites.net/api/DivePlanner';

// ── Cookie helpers ────────────────────────────────────────────────────────────

function setCookie(name, value) {
    var expires = new Date(Date.now() + 365 * 864e5).toUTCString();
    document.cookie = name + '=' + encodeURIComponent(value) + '; expires=' + expires + '; path=/; SameSite=Lax';
}

function getCookie(name) {
    var match = document.cookie.split('; ').find(function (c) { return c.startsWith(name + '='); });
    return match ? decodeURIComponent(match.split('=')[1]) : null;
}

// ── Gas physics ───────────────────────────────────────────────────────────────

var RHO_O2 = 1.429, RHO_N2 = 1.251, RHO_HE = 0.179;   // g/L at STP

function surfaceDensity(o2, he) {
    var fO2 = o2 / 100, fHe = he / 100, fN2 = 1 - fO2 - fHe;
    return fO2 * RHO_O2 + fN2 * RHO_N2 + fHe * RHO_HE;
}

// Depth (m) at which gas density reaches limit g/L (5.2 = BSAC recommended)
function densityLimitDepth(o2, he, limitGl) {
    limitGl = limitGl || 5.2;
    var rho0 = surfaceDensity(o2, he);
    if (rho0 <= 0) return 999;
    var d = Math.floor((limitGl / rho0 - 1) * 10);
    return Math.max(0, d);
}

// Suggest O2 and He for a target depth and setpoint:
//   O2 → min(setpoint/ambient, 21%) — keeps diluent non-hyperoxic relative to setpoint
//   He → min fraction so gas density at depth ≤ densityLimitGl
function bestMix(depth, setpoint, densityLimitGl) {
    var amb = depth / 10 + 1;
    // Cap at setpoint/ambient so diluent O2 never exceeds CCR setpoint fraction
    var fO2 = Math.min(0.21, setpoint / amb);
    var densLimSurf = densityLimitGl / amb;
    // Solve: ρN2 + fO2*(ρO2-ρN2) + fHe*(ρHe-ρN2) = densLimSurf
    var fHe = (densLimSurf - RHO_N2 - fO2 * (RHO_O2 - RHO_N2)) / (RHO_HE - RHO_N2);
    fHe = Math.max(0, Math.min(1 - fO2, fHe));
    // Round He to nearest 5%, O2 to nearest 1%
    var heRounded = Math.ceil(fHe * 20) * 5;
    var o2Rounded = Math.round(fO2 * 100);
    if (o2Rounded + heRounded > 100) heRounded = 100 - o2Rounded;
    return { o2: o2Rounded, he: heRounded };
}

function selectedDensityLimit() {
    return document.getElementById('dl_upper').checked ? 6.3 : 5.2;
}

// ── Gas naming ────────────────────────────────────────────────────────────────

function gasName(o2, he) {
    if (o2 === 100) return 'O₂';
    if (he === 0) {
        if (o2 === 21) return 'Air';
        return 'Nx' + o2;
    }
    return 'Tx' + o2 + '/' + he;
}

// ── Gas library state ─────────────────────────────────────────────────────────

var gasLibrary = [];
var nextGasId  = 1;
var editingGasId = null;

var DEFAULT_GASES = [
    { o2: 21, he: 0,  setpoint: 1.3 },
    { o2: 10, he: 70, setpoint: 1.3 },
    { o2: 12, he: 60, setpoint: 1.3 },
    { o2: 15, he: 55, setpoint: 1.3 },
    { o2: 18, he: 45, setpoint: 1.3 },
];

function saveGasLibrary() {
    var data = {
        gases: gasLibrary.map(function (g) {
            return { id: g.id, o2: g.o2, he: g.he, setpoint: g.setpoint, active: !!g.active };
        }),
        nextId: nextGasId,
    };
    setCookie('planner_gases', JSON.stringify(data));
}

function loadGasLibrary() {
    var raw = getCookie('planner_gases');
    if (raw) {
        try {
            var data = JSON.parse(raw);
            gasLibrary = data.gases || [];
            nextGasId  = data.nextId || (gasLibrary.length + 1);
            if (!gasLibrary.some(function (g) { return g.active; }) && gasLibrary.length > 0) {
                gasLibrary[0].active = true;
            }
            return;
        } catch (e) { /* fall through to defaults */ }
    }
    nextGasId = 1;
    gasLibrary = DEFAULT_GASES.map(function (g, i) {
        return { id: nextGasId++, o2: g.o2, he: g.he, setpoint: g.setpoint, active: i === 1 };
    });
    saveGasLibrary();
}

function activeGas() {
    return gasLibrary.find(function (g) { return g.active; }) || null;
}

// ── Gas library rendering ─────────────────────────────────────────────────────

function renderGasLibrary() {
    var container = document.getElementById('gas_library');
    container.innerHTML = '';
    gasLibrary.forEach(function (gas) {
        container.appendChild(buildGasCard(gas));
    });
}

function buildGasCard(gas) {
    var o2 = gas.o2, he = gas.he;
    var n2 = Math.max(0, 100 - o2 - he);
    var name = gasName(o2, he);
    var limRec   = densityLimitDepth(o2, he, 5.2);
    var limUpper = densityLimitDepth(o2, he, 6.3);

    var card = document.createElement('div');
    card.className = 'gas-card' + (gas.active ? ' gas-card-active' : '');

    card.innerHTML =
        '<div class="gas-card-top">' +
            '<span class="gas-card-name">' + name + '</span>' +
            '<span>' +
                '<button class="btn-gas-action" onclick="editGas(' + gas.id + ')" title="Edit"><i class="bi bi-pencil"></i></button>' +
                '<button class="btn-gas-action" onclick="confirmDeleteGas(' + gas.id + ')" title="Delete"><i class="bi bi-trash"></i></button>' +
            '</span>' +
        '</div>' +
        '<div class="gas-card-meta">O₂ ' + o2 + '% · He ' + he + '% · N₂ ' + n2 + '% · SP ' + gas.setpoint + ' bar</div>' +
        '<div class="gas-bar" style="margin-top:0.15rem;">' +
            '<div class="gas-bar-o2" style="width:' + o2 + '%"></div>' +
            '<div class="gas-bar-he" style="width:' + he + '%"></div>' +
            '<div class="gas-bar-n2" style="width:' + n2 + '%"></div>' +
        '</div>' +
        '<div class="gas-card-footer">' +
            '<span class="gas-depth-badge"><i class="bi bi-arrow-down-circle"></i> rec ~' + limRec + ' m · upper ~' + limUpper + ' m</span>' +
            '<button class="btn-gas-toggle' + (gas.active ? ' active' : '') + '" onclick="selectGas(' + gas.id + ')">' +
                '<i class="bi bi-' + (gas.active ? 'check-circle-fill' : 'circle') + '"></i>' +
                (gas.active ? ' Selected' : ' Select') +
            '</button>' +
        '</div>';

    return card;
}

function selectGas(id) {
    gasLibrary.forEach(function (g) { g.active = (g.id === id); });
    saveGasLibrary();
    renderGasLibrary();
}

// ── Modal: add / edit gas ─────────────────────────────────────────────────────

var _gasModalInstance = null;

function openAddGas() {
    editingGasId = null;
    document.getElementById('gasModalLabel').textContent = 'Add Diluent Gas';
    document.getElementById('modal_o2').value = 21;
    document.getElementById('modal_he').value = 0;
    document.getElementById('modal_sp').value = 1.3;
    document.getElementById('modal_bestmix_note').textContent = '';
    updateModalPreview();
    _gasModalInstance = bootstrap.Modal.getOrCreateInstance(document.getElementById('gasModal'));
    _gasModalInstance.show();
}

function editGas(id) {
    var gas = gasLibrary.find(function (g) { return g.id === id; });
    if (!gas) return;
    editingGasId = id;
    document.getElementById('gasModalLabel').textContent = 'Edit Diluent Gas';
    document.getElementById('modal_o2').value = gas.o2;
    document.getElementById('modal_he').value = gas.he;
    document.getElementById('modal_sp').value = gas.setpoint;
    document.getElementById('modal_bestmix_note').textContent = '';
    updateModalPreview();
    _gasModalInstance = bootstrap.Modal.getOrCreateInstance(document.getElementById('gasModal'));
    _gasModalInstance.show();
}

function saveGas() {
    var o2 = Math.round(Math.max(0, Math.min(100, parseFloat(document.getElementById('modal_o2').value) || 0)));
    var he = Math.round(Math.max(0, Math.min(100, parseFloat(document.getElementById('modal_he').value) || 0)));
    var sp = parseFloat(document.getElementById('modal_sp').value) || 1.3;

    if (o2 + he > 100) {
        document.getElementById('modal_o2').classList.add('is-invalid');
        document.getElementById('modal_he').classList.add('is-invalid');
        return;
    }
    document.getElementById('modal_o2').classList.remove('is-invalid');
    document.getElementById('modal_he').classList.remove('is-invalid');

    if (editingGasId !== null) {
        var gas = gasLibrary.find(function (g) { return g.id === editingGasId; });
        if (gas) { gas.o2 = o2; gas.he = he; gas.setpoint = sp; }
    } else {
        gasLibrary.push({ id: nextGasId++, o2: o2, he: he, setpoint: sp, active: false });
    }

    saveGasLibrary();
    renderGasLibrary();
    if (_gasModalInstance) _gasModalInstance.hide();
}

function confirmDeleteGas(id) {
    if (gasLibrary.length <= 1) return;
    var gas = gasLibrary.find(function (g) { return g.id === id; });
    if (!gas) return;
    if (!confirm('Remove ' + gasName(gas.o2, gas.he) + '?')) return;
    var wasActive = gas.active;
    gasLibrary = gasLibrary.filter(function (g) { return g.id !== id; });
    if (wasActive && gasLibrary.length > 0) gasLibrary[0].active = true;
    saveGasLibrary();
    renderGasLibrary();
}

function applyBestMix() {
    var depth    = parseFloat(document.getElementById('depth_m').value) || 60;
    var setpoint = parseFloat(document.getElementById('modal_sp').value) || 1.3;
    var densLim  = selectedDensityLimit();
    var mix      = bestMix(depth, setpoint, densLim);
    document.getElementById('modal_o2').value = mix.o2;
    document.getElementById('modal_he').value = mix.he;
    var limitLabel = densLim === 6.3 ? '6.3 g/L (upper)' : '5.2 g/L (recommended)';
    document.getElementById('modal_bestmix_note').textContent =
        depth + ' m · SP ' + setpoint + ' · O₂ ≤ SP/amb · density ≤' + limitLabel;
    updateModalPreview();
}

function updateModalPreview() {
    var o2 = Math.max(0, Math.min(100, parseInt(document.getElementById('modal_o2').value) || 0));
    var he = Math.max(0, Math.min(100 - o2, parseInt(document.getElementById('modal_he').value) || 0));
    var n2 = Math.max(0, 100 - o2 - he);

    document.getElementById('modal_o2bar').style.width = o2 + '%';
    document.getElementById('modal_hebar').style.width  = he + '%';
    document.getElementById('modal_n2bar').style.width  = n2 + '%';
    document.getElementById('modal_name').textContent   = gasName(o2, he);

    var sp = parseFloat(document.getElementById('modal_sp').value) || 1.3;
    document.getElementById('modal_sp_val').textContent = sp.toFixed(1);

    var limRec   = densityLimitDepth(o2, he, 5.2);
    var limUpper = densityLimitDepth(o2, he, 6.3);
    document.getElementById('modal_limit').textContent = 'rec ~' + limRec + ' m · upper ~' + limUpper + ' m';
}

// ── Settings helpers ──────────────────────────────────────────────────────────

function applyGF(low, high) {
    document.getElementById('gf_low').value  = low;
    document.getElementById('gf_high').value = high;
    setCookie('gf_low',  low);
    setCookie('gf_high', high);
}

function initPopovers() {
    document.querySelectorAll('[data-bs-toggle="popover"]').forEach(function (el) {
        var existing = bootstrap.Popover.getInstance(el);
        if (existing) existing.dispose();
        new bootstrap.Popover(el);
    });
}

// ── Calculate ─────────────────────────────────────────────────────────────────

function calculate() {
    var errorEl   = document.getElementById('error');
    var resultEl  = document.getElementById('result');
    var loadingEl = document.getElementById('loading');

    errorEl.classList.add('d-none');
    errorEl.textContent = '';
    resultEl.innerHTML  = '';

    var gas = activeGas();
    if (!gas) {
        errorEl.textContent = 'Select a diluent gas before calculating.';
        errorEl.classList.remove('d-none');
        return;
    }

    var gfLow  = parseFloat(document.getElementById('gf_low').value);
    var gfHigh = parseFloat(document.getElementById('gf_high').value);
    if (gfLow > gfHigh) {
        errorEl.textContent = 'GF Low must not exceed GF High.';
        errorEl.classList.remove('d-none');
        return;
    }

    loadingEl.classList.remove('d-none');

    var payload = JSON.stringify({
        diluent_o2:      gas.o2,
        diluent_he:      gas.he,
        setpoint:        gas.setpoint,
        depth_m:         parseFloat(document.getElementById('depth_m').value),
        bottom_time_min: parseFloat(document.getElementById('bottom_time').value),
        gf_low:          gfLow,
        gf_high:         gfHigh,
    });

    var h   = window.location.hostname;
    var url = (h === 'localhost' || h === '127.0.0.1' || h === '') ? LOCAL_URL : PROD_URL;

    fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload })
        .then(function (res) {
            if (!res.ok) return res.text().then(function (t) { throw new Error(t || res.statusText); });
            return res.json();
        })
        .then(function (data) {
            loadingEl.classList.add('d-none');
            resultEl.appendChild(buildResult(data));
        })
        .catch(function (err) {
            loadingEl.classList.add('d-none');
            errorEl.textContent = err.message;
            errorEl.classList.remove('d-none');
        });
}

// ── Result rendering ──────────────────────────────────────────────────────────

function buildResult(data) {
    var frag = document.createDocumentFragment();

    var da = data.density_analysis;
    if (da.exceeded_limit) {
        frag.appendChild(buildAlert(
            'danger',
            'Gas density exceeds the BSAC upper limit (' + da.density_gl + ' g/L — limit 6.3 g/L). This diluent is not safe to breathe at this depth.'
        ));
    } else if (da.exceeded_recommended) {
        frag.appendChild(buildAlert(
            'warning',
            'Gas density exceeds the BSAC recommended limit (' + da.density_gl + ' g/L — recommended ≤5.2 g/L). Increased work of breathing and CO₂ retention risk.'
        ));
    }

    var scheduleDiv = document.createElement('div');
    scheduleDiv.className = 'mb-4';

    var heading = document.createElement('div');
    heading.className = 'mb-1';
    var headingSpan = document.createElement('span');
    headingSpan.className = 'result-heading';
    headingSpan.textContent = 'Decompression Schedule';
    heading.appendChild(headingSpan);
    scheduleDiv.appendChild(heading);

    var gas = activeGas();
    var depthM    = parseFloat(document.getElementById('depth_m').value) || 0;
    var btMin     = parseFloat(document.getElementById('bottom_time').value) || 0;
    var sp        = gas ? gas.setpoint : 1.3;
    var gO2       = gas ? gas.o2 : 21;
    var gHe       = gas ? gas.he : 0;
    var gName     = gas ? gasName(gO2, gHe) : '—';
    var descTime  = Math.round(depthM / 20.0 * 10) / 10;
    var btRuntime = Math.round((depthM / 20.0 + btMin) * 10) / 10;

    function densStr(d) {
        return (surfaceDensity(gO2, gHe) * (d / 10.0 + 1.0)).toFixed(2) + ' g/L';
    }
    function densColor(d) {
        var v = surfaceDensity(gO2, gHe) * (d / 10.0 + 1.0);
        return v > 6.3 ? '#dc3545' : v > 5.2 ? '#e07000' : '';
    }

    var card = document.createElement('div');
    card.className = 'card';
    var cardBody = document.createElement('div');
    cardBody.className = 'card-body p-0';

    var tableWrap = document.createElement('div');
    tableWrap.className = 'table-responsive';
    var table = document.createElement('table');
    table.className = 'table table-sm mb-0 deco-table';

    var thead = document.createElement('thead');
    thead.innerHTML =
        '<tr>' +
        '<th class="ps-2" style="width:2rem"></th>' +
        '<th>Depth</th><th>Time</th><th>Runtime</th>' +
        '<th>ppO₂</th><th>Density</th><th>Gas</th>' +
        '</tr>';
    table.appendChild(thead);

    var tbody = document.createElement('tbody');

    // Descent row
    var dcDesc = densColor(depthM);
    var trDesc = document.createElement('tr');
    trDesc.innerHTML =
        '<td class="ps-2"><i class="bi bi-arrow-down-circle" style="color:#0077b6"></i></td>' +
        '<td>0 → ' + depthM + ' m</td>' +
        '<td>' + descTime + ' min</td>' +
        '<td>' + descTime + ' min</td>' +
        '<td>' + sp.toFixed(2) + '</td>' +
        '<td' + (dcDesc ? ' style="color:' + dcDesc + '"' : '') + '>' + densStr(depthM) + '</td>' +
        '<td>' + gName + '</td>';
    tbody.appendChild(trDesc);

    // Bottom row
    var trBtm = document.createElement('tr');
    trBtm.innerHTML =
        '<td class="ps-2"><i class="bi bi-circle-fill" style="color:#03045e;font-size:0.55em;vertical-align:middle"></i></td>' +
        '<td>' + depthM + ' m</td>' +
        '<td>' + btMin + ' min</td>' +
        '<td>' + btRuntime + ' min</td>' +
        '<td>' + sp.toFixed(2) + '</td>' +
        '<td' + (dcDesc ? ' style="color:' + dcDesc + '"' : '') + '>' + densStr(depthM) + '</td>' +
        '<td>' + gName + '</td>';
    tbody.appendChild(trBtm);

    if (data.stops.length === 0) {
        var ascTime = Math.round(depthM / 9.0 * 10) / 10;
        var ascRuntime = Math.round((depthM / 20.0 + btMin + depthM / 9.0) * 10) / 10;
        var trAsc = document.createElement('tr');
        trAsc.innerHTML =
            '<td class="ps-2"><i class="bi bi-arrow-up-circle" style="color:#198754"></i></td>' +
            '<td>' + depthM + ' → 0 m</td>' +
            '<td>' + ascTime + ' min</td>' +
            '<td>' + ascRuntime + ' min</td>' +
            '<td>' + sp.toFixed(2) + '</td>' +
            '<td>—</td>' +
            '<td>' + gName + '</td>';
        tbody.appendChild(trAsc);
    } else {
        data.stops.forEach(function (stop) {
            var dc = densColor(stop.depth_m);
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td class="ps-2"><i class="bi bi-arrow-up-circle" style="color:#e07000"></i></td>' +
                '<td>' + stop.depth_m + ' m</td>' +
                '<td>' + stop.time_min + ' min</td>' +
                '<td>' + stop.runtime_min + ' min</td>' +
                '<td>' + sp.toFixed(2) + '</td>' +
                '<td' + (dc ? ' style="color:' + dc + '"' : '') + '>' + densStr(stop.depth_m) + '</td>' +
                '<td>' + gName + '</td>';
            tbody.appendChild(tr);
        });
    }

    table.appendChild(tbody);
    tableWrap.appendChild(table);
    cardBody.appendChild(tableWrap);
    card.appendChild(cardBody);
    scheduleDiv.appendChild(card);

    if (data.tts_min !== undefined) {
        scheduleDiv.appendChild(buildMetricsCard(data));
    }

    var hasChart = data.profile_points && data.profile_points.length > 2;

    if (hasChart) {
        var row = document.createElement('div');
        row.className = 'row g-3 align-items-start';

        var scheduleCol = document.createElement('div');
        scheduleCol.className = 'col-12 col-lg-5';
        scheduleDiv.className = '';  // remove mb-4, grid handles spacing
        scheduleCol.appendChild(scheduleDiv);
        row.appendChild(scheduleCol);

        var chartCol = document.createElement('div');
        chartCol.className = 'col-12 col-lg-7';
        chartCol.appendChild(buildChart(data));
        row.appendChild(chartCol);

        frag.appendChild(row);
    } else {
        frag.appendChild(scheduleDiv);
    }

    return frag;
}

// ── Dive profile chart ────────────────────────────────────────────────────────

var _profileChart = null;
var _tissueChart  = null;

var TISSUE_LABELS = ["5'","8'","12'","18'","27'","38'","54'","77'","109'","146'","187'","239'","305'","390'","498'","635'"];

function buildChart(data) {
    var wrap = document.createElement('div');
    wrap.className = 'chart-wrap';

    var header = document.createElement('div');
    header.className = 'chart-header';
    var title = document.createElement('span');
    title.className = 'result-heading';
    title.textContent = 'Dive Profile';
    var fsBtn = document.createElement('button');
    fsBtn.className = 'chart-fs-btn';
    fsBtn.title = 'Full screen';
    fsBtn.innerHTML = '<i class="bi bi-fullscreen"></i>';
    fsBtn.onclick = function () { toggleChartFullscreen(wrap, fsBtn); };
    header.appendChild(title);
    header.appendChild(fsBtn);
    wrap.appendChild(header);

    var profileBox = document.createElement('div');
    profileBox.className = 'profile-canvas';
    profileBox.style.height = '260px';
    profileBox.style.position = 'relative';
    var profileCanvas = document.createElement('canvas');
    profileBox.appendChild(profileCanvas);
    wrap.appendChild(profileBox);

    // Tissue panel (visible by default)
    var tissueToggle = document.createElement('button');
    tissueToggle.className = 'btn btn-sm btn-outline-secondary w-100 tissue-toggle';
    tissueToggle.textContent = 'Hide Tissue Saturation';
    var tissuePanel = document.createElement('div');
    tissuePanel.style.display = 'block';
    var tissueBox = document.createElement('div');
    tissueBox.style.height = '200px';
    tissueBox.style.position = 'relative';
    var tissueCanvas = document.createElement('canvas');
    tissueBox.appendChild(tissueCanvas);
    tissuePanel.appendChild(tissueBox);
    tissueToggle.onclick = function () {
        var open = tissuePanel.style.display !== 'none';
        tissuePanel.style.display = open ? 'none' : 'block';
        tissueToggle.textContent = open ? 'Show Tissue Saturation' : 'Hide Tissue Saturation';
        if (!open) renderTissueChart(tissueCanvas, data);
        if (open && _tissueChart) { _tissueChart.destroy(); _tissueChart = null; }
    };
    wrap.appendChild(tissueToggle);
    wrap.appendChild(tissuePanel);

    // Render profile chart on next tick (canvas needs to be in DOM for sizing)
    setTimeout(function () {
        renderProfileChart(profileCanvas, data);
        renderTissueChart(tissueCanvas, data);

        function hoverAtX(offsetX) {
            if (!_profileChart || !_tissueChart) return;
            var xVal = _profileChart.scales.x.getValueForPixel(offsetX);
            var pts = data.profile_points;
            if (!pts || !pts.length) return;
            var nearest = pts.reduce(function (prev, curr) {
                return Math.abs(curr.t - xVal) < Math.abs(prev.t - xVal) ? curr : prev;
            });
            if (nearest && nearest.sats) _updateTissueData(nearest.sats, nearest.t);
        }

        function resetTissue() {
            if (!_tissueChart) return;
            var finalSats = data.tissue_saturations;
            if (finalSats) _updateTissueData(finalSats, null);
        }

        profileCanvas.addEventListener('mousemove', function (e) { hoverAtX(e.offsetX); });
        profileCanvas.addEventListener('mouseleave', resetTissue);

        profileCanvas.addEventListener('touchmove', function (e) {
            var touch = e.touches[0];
            var rect = profileCanvas.getBoundingClientRect();
            hoverAtX(touch.clientX - rect.left);
        }, { passive: true });
        profileCanvas.addEventListener('touchend', resetTissue);
    }, 0);

    return wrap;
}

function renderProfileChart(canvas, data) {
    if (_profileChart) { _profileChart.destroy(); _profileChart = null; }

    var pts = data.profile_points;
    var maxDepth = Math.max.apply(null, pts.map(function (p) { return p.d; }));

    _profileChart = new Chart(canvas, {
        type: 'line',
        data: {
            datasets: [
                {
                    label: 'Depth',
                    data: pts.map(function (p) { return { x: p.t, y: p.d }; }),
                    borderColor: 'rgba(0,100,160,0.85)',
                    backgroundColor: 'rgba(0,119,182,0.10)',
                    fill: true,
                    tension: 0,
                    pointRadius: 0,
                    borderWidth: 2,
                    order: 2,
                },
                {
                    label: 'Ceiling',
                    data: pts.map(function (p) { return { x: p.t, y: p.c }; }),
                    borderColor: 'rgba(220,80,40,0.8)',
                    borderDash: [6, 4],
                    backgroundColor: 'transparent',
                    fill: false,
                    tension: 0,
                    pointRadius: 0,
                    borderWidth: 1.5,
                    order: 1,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 },
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: {
                    type: 'linear',
                    title: { display: true, text: 'Time (min)', font: { size: 10 } },
                    ticks: { font: { size: 10 } },
                },
                y: {
                    reverse: true,
                    min: 0,
                    suggestedMax: Math.ceil(maxDepth * 1.08 / 5) * 5,
                    title: { display: true, text: 'Depth (m)', font: { size: 10 } },
                    ticks: { font: { size: 10 } },
                },
            },
            plugins: {
                legend: { display: true, labels: { font: { size: 10 }, boxWidth: 14, padding: 10 } },
                tooltip: {
                    callbacks: {
                        title: function (items) { return items[0].parsed.x.toFixed(1) + ' min'; },
                        label: function (item) {
                            return item.dataset.label + ': ' + item.parsed.y + ' m';
                        },
                    },
                },
            },
        },
    });
}

function renderTissueChart(canvas, data) {
    if (_tissueChart) { _tissueChart.destroy(); _tissueChart = null; }

    var gfHighPct = parseFloat(document.getElementById('gf_high').value) || 80;
    var sats = data.tissue_saturations.map(function (r) { return Math.round(r * 100); });

    var colors = sats.map(function (s) {
        if (s > 100)        return 'rgba(220,53,69,0.75)';
        if (s > gfHighPct)  return 'rgba(255,140,0,0.75)';
        return 'rgba(32,150,130,0.75)';
    });

    _tissueChart = new Chart(canvas, {
        data: {
            labels: TISSUE_LABELS,
            datasets: [
                {
                    type: 'bar',
                    label: 'Saturation',
                    data: sats,
                    backgroundColor: colors,
                    borderRadius: 3,
                    order: 2,
                },
                {
                    type: 'line',
                    label: 'GF High (' + gfHighPct + '%)',
                    data: Array(16).fill(gfHighPct),
                    borderColor: 'rgba(255,140,0,0.9)',
                    borderDash: [5, 4],
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: false,
                    order: 1,
                },
                {
                    type: 'line',
                    label: 'M-value (100%)',
                    data: Array(16).fill(100),
                    borderColor: 'rgba(220,53,69,0.85)',
                    borderDash: [3, 3],
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: false,
                    order: 0,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 },
            scales: {
                x: { title: { display: true, text: 'Compartment half-time', font: { size: 10 } }, ticks: { font: { size: 10 } } },
                y: {
                    min: 0,
                    max: Math.max(110, Math.max.apply(null, sats) + 5),
                    title: { display: true, text: '% of GF-adjusted M-value', font: { size: 10 } },
                    ticks: { font: { size: 10 } },
                },
            },
            plugins: {
                legend: { display: true, labels: { font: { size: 10 }, boxWidth: 14, padding: 8 } },
                title: { display: true, text: 'Tissue loading at surfacing', font: { size: 10 }, color: '#555', padding: { bottom: 2 } },
            },
        },
    });
}

function _updateTissueData(sats, timeMin) {
    if (!_tissueChart) return;
    var gfHighPct = parseFloat(document.getElementById('gf_high').value) || 80;
    var satsPct = sats.map(function(r) { return Math.round(r * 100); });
    _tissueChart.data.datasets[0].data = satsPct;
    _tissueChart.data.datasets[0].backgroundColor = satsPct.map(function(s) {
        if (s > 100)       return 'rgba(220,53,69,0.75)';
        if (s > gfHighPct) return 'rgba(255,140,0,0.75)';
        return 'rgba(32,150,130,0.75)';
    });
    var label = timeMin !== null ? 'at ' + parseFloat(timeMin).toFixed(1) + ' min' : 'at surfacing';
    _tissueChart.options.plugins.title.text = 'Tissue loading ' + label;
    _tissueChart.update('none');
}
function toggleChartFullscreen(wrap, btn) {
    if (!document.fullscreenElement) {
        wrap.requestFullscreen();
        btn.innerHTML = '<i class="bi bi-fullscreen-exit"></i>';
    } else {
        document.exitFullscreen();
        btn.innerHTML = '<i class="bi bi-fullscreen"></i>';
    }
}

document.addEventListener('fullscreenchange', function () {
    if (!document.fullscreenElement) {
        var btn = document.querySelector('.chart-fs-btn');
        if (btn) btn.innerHTML = '<i class="bi bi-fullscreen"></i>';
    }
    if (_profileChart) _profileChart.resize();
    if (_tissueChart)  _tissueChart.resize();
});

function buildMetricsCard(data) {
    var cnsColor = data.cns_pct > 80 ? '#dc3545' : data.cns_pct > 40 ? '#e07000' : 'var(--ocean)';
    var otuColor = data.otu > 250 ? '#dc3545' : data.otu > 150 ? '#e07000' : 'var(--navy)';

    var card = document.createElement('div');
    card.className = 'card mt-3';
    var body = document.createElement('div');
    body.className = 'card-body py-2 px-3';
    body.innerHTML =
        '<div class="d-flex justify-content-around text-center">' +
            '<div>' +
                '<div class="field-label mb-1">Runtime</div>' +
                '<div style="font-size:1.05rem;font-weight:800;color:var(--ocean);">' + data.total_time_min + ' min</div>' +
            '</div>' +
            '<div>' +
                '<div class="field-label mb-1">TTS</div>' +
                '<div style="font-size:1.05rem;font-weight:800;color:var(--ocean);">' + data.tts_min + ' min</div>' +
            '</div>' +
            '<div>' +
                '<div class="field-label mb-1">CNS</div>' +
                '<div style="font-size:1.05rem;font-weight:800;color:' + cnsColor + ';">' + data.cns_pct + '%</div>' +
            '</div>' +
            '<div>' +
                '<div class="field-label mb-1">OTU</div>' +
                '<div style="font-size:1.05rem;font-weight:800;color:' + otuColor + ';">' + data.otu + '</div>' +
            '</div>' +
        '</div>';
    card.appendChild(body);
    return card;
}

function buildAlert(type, html) {
    var div = document.createElement('div');
    div.className = 'alert alert-' + type + ' rounded-3 density-warning mb-3';
    div.innerHTML = html;
    return div;
}

// ── Saved plans ───────────────────────────────────────────────────────────────

var savedPlans = [];
var nextPlanId = 1;
var _pendingSavePlan = null;

var EXAMPLE_PLANS = [
    {
        name: 'Shallow Reef',
        gas: { o2: 21, he: 0, setpoint: 1.3 },
        depth_m: 20,
        bottom_time_min: 45,
        gf_low: 85,
        gf_high: 95,
    },
    {
        name: 'Wreck Dive',
        gas: { o2: 21, he: 35, setpoint: 1.3 },
        depth_m: 40,
        bottom_time_min: 25,
        gf_low: 65,
        gf_high: 85,
    },
    {
        name: 'Deep Trimix',
        gas: { o2: 10, he: 70, setpoint: 1.3 },
        depth_m: 60,
        bottom_time_min: 20,
        gf_low: 50,
        gf_high: 80,
    },
];

function loadSavedPlans() {
    try {
        var raw = localStorage.getItem('planner_saved_plans');
        if (raw) {
            var data = JSON.parse(raw);
            savedPlans = data.plans || [];
            nextPlanId = data.nextId || (savedPlans.length + 1);
            return;
        }
    } catch (e) { /* fall through to examples */ }
    nextPlanId = 1;
    savedPlans = EXAMPLE_PLANS.map(function (p) {
        return Object.assign({}, p, { id: nextPlanId++, created_at: new Date().toISOString() });
    });
    persistSavedPlans();
}

function persistSavedPlans() {
    localStorage.setItem('planner_saved_plans', JSON.stringify({
        plans: savedPlans,
        nextId: nextPlanId,
    }));
}

function saveCurrentPlan() {
    var gas = activeGas();
    if (!gas) {
        alert('Select a diluent gas first.');
        return;
    }
    var depth = parseFloat(document.getElementById('depth_m').value) || 0;
    var bt    = parseFloat(document.getElementById('bottom_time').value) || 0;
    var gfL   = parseFloat(document.getElementById('gf_low').value) || 60;
    var gfH   = parseFloat(document.getElementById('gf_high').value) || 80;
    _pendingSavePlan = {
        gas: { o2: gas.o2, he: gas.he, setpoint: gas.setpoint },
        depth_m: depth,
        bottom_time_min: bt,
        gf_low: gfL,
        gf_high: gfH,
    };
    document.getElementById('savePlanName').value =
        gasName(gas.o2, gas.he) + ' · ' + depth + 'm / ' + bt + 'min';
    bootstrap.Modal.getOrCreateInstance(document.getElementById('savePlanModal')).show();
}

function confirmSavePlan() {
    if (!_pendingSavePlan) return;
    var name = (document.getElementById('savePlanName').value || '').trim() || 'Unnamed plan';
    savedPlans.push(Object.assign({}, _pendingSavePlan, {
        id: nextPlanId++,
        name: name,
        created_at: new Date().toISOString(),
    }));
    _pendingSavePlan = null;
    persistSavedPlans();
    renderSavedPlans();
    bootstrap.Modal.getInstance(document.getElementById('savePlanModal')).hide();
    bootstrap.Offcanvas.getOrCreateInstance(document.getElementById('savedPlansOffcanvas')).show();
}

function loadPlan(id) {
    var plan = savedPlans.find(function (p) { return p.id === id; });
    if (!plan) return;

    document.getElementById('depth_m').value       = plan.depth_m;
    document.getElementById('bottom_time').value   = plan.bottom_time_min;
    document.getElementById('gf_low').value        = plan.gf_low;
    document.getElementById('gf_high').value       = plan.gf_high;
    setCookie('gf_low',  plan.gf_low);
    setCookie('gf_high', plan.gf_high);

    var g = plan.gas;
    var match = gasLibrary.find(function (x) {
        return x.o2 === g.o2 && x.he === g.he && x.setpoint === g.setpoint;
    });
    if (match) {
        selectGas(match.id);
    } else {
        gasLibrary.push({ id: nextGasId++, o2: g.o2, he: g.he, setpoint: g.setpoint, active: false });
        saveGasLibrary();
        selectGas(gasLibrary[gasLibrary.length - 1].id);
    }

    bootstrap.Offcanvas.getInstance(document.getElementById('savedPlansOffcanvas')).hide();
    calculate();
}

function deleteSavedPlan(id) {
    var plan = savedPlans.find(function (p) { return p.id === id; });
    if (!plan) return;
    if (!confirm('Remove "' + plan.name + '"?')) return;
    savedPlans = savedPlans.filter(function (p) { return p.id !== id; });
    persistSavedPlans();
    renderSavedPlans();
}

function renderSavedPlans() {
    var container = document.getElementById('savedPlansList');
    if (!container) return;
    container.innerHTML = '';
    if (savedPlans.length === 0) {
        container.innerHTML = '<p class="text-muted" style="font-size:0.82rem;">No saved plans yet. Set up a dive and click “Save current plan”.</p>';
        return;
    }
    savedPlans.slice().reverse().forEach(function (plan) {
        var div = document.createElement('div');
        div.className = 'plan-card';
        div.innerHTML =
            '<div class="plan-card-name">' + plan.name + '</div>' +
            '<div class="plan-card-meta">' +
                gasName(plan.gas.o2, plan.gas.he) + ' · SP ' + plan.gas.setpoint +
                ' · ' + plan.depth_m + ' m · ' + plan.bottom_time_min + ' min' +
                ' · GF ' + plan.gf_low + '/' + plan.gf_high +
            '</div>' +
            '<div class="plan-card-actions">' +
                '<button class="btn btn-sm btn-apply flex-grow-1" onclick="loadPlan(' + plan.id + ')">Load</button>' +
                '<button class="btn btn-sm btn-outline-secondary" onclick="deleteSavedPlan(' + plan.id + ')" title="Delete"><i class="bi bi-trash"></i></button>' +
            '</div>';
        container.appendChild(div);
    });
}
// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function () {
    loadSavedPlans();
    renderSavedPlans();
    loadGasLibrary();
    renderGasLibrary();

    var savedLow  = getCookie('gf_low');
    var savedHigh = getCookie('gf_high');
    if (savedLow)  document.getElementById('gf_low').value  = savedLow;
    if (savedHigh) document.getElementById('gf_high').value = savedHigh;

    ['gf_low', 'gf_high'].forEach(function (id) {
        document.getElementById(id).addEventListener('change', function () {
            setCookie(id, this.value);
        });
    });

    initPopovers();
    calculate();
});
