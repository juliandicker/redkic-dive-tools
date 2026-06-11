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

function gasNameCompact(o2, he) {
    if (o2 === 100) return 'O₂';
    if (he === 0) { return o2 === 21 ? 'Air' : o2 + '%'; }
    return o2 + '/' + he;
}

// ── Gas library state ─────────────────────────────────────────────────────────

var gasLibrary = [];
var nextGasId  = 1;
var editingGasId = null;
var _gasModalMode = 'diluent';  // 'diluent' | 'bailout'

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

function renderLibrary(isBailout) {
    var lib = isBailout ? bailoutLibrary : gasLibrary;
    var container = document.getElementById(isBailout ? 'bailout_library' : 'gas_library');
    container.innerHTML = '';
    lib.slice().sort(function (a, b) {
        return a.o2 !== b.o2 ? a.o2 - b.o2 : a.he - b.he;
    }).forEach(function (gas) {
        container.appendChild(buildGasCard(gas, isBailout));
    });
}

function buildGasCard(gas, isBailout) {
    var o2 = gas.o2, he = gas.he;
    var n2 = Math.max(0, 100 - o2 - he);
    var name = gasName(o2, he);
    var limRec   = densityLimitDepth(o2, he, 5.2);
    var limUpper = densityLimitDepth(o2, he, 6.3);
    var infoLine, deleteFn;
    if (isBailout) {
        infoLine = gas.mod_m <= limRec
            ? 'MOD ' + gas.mod_m + ' m'
            : limRec + ' m – ' + limUpper + ' m';
        deleteFn = 'confirmDeleteBailoutGas';
    } else {
        infoLine = limRec + ' m – ' + limUpper + ' m · SP ' + gas.setpoint + ' bar';
        deleteFn = 'confirmDeleteGas';
    }

    var card = document.createElement('div');
    card.className = 'gas-card' + (gas.active ? ' gas-card-active' : '');
    card.style.cursor = 'pointer';
    card.onclick = function() { isBailout ? toggleBailoutGas(gas.id) : selectGas(gas.id); };

    card.innerHTML =
        '<div class="gas-card-top">' +
            '<span class="gas-card-name">' + name + '</span>' +
            '<span class="gas-card-info">' + infoLine + '</span>' +
            '<span>' +
                '<i class="bi bi-' + (gas.active ? 'check-circle-fill' : 'circle') + ' btn-gas-action"' + (gas.active ? ' style="color:var(--aqua)"' : '') + '></i>' +
                '<button class="btn-gas-action" onclick="event.stopPropagation();openGasModal(' + isBailout + ',' + gas.id + ')" title="Edit"><i class="bi bi-pencil"></i></button>' +
                '<button class="btn-gas-action" onclick="event.stopPropagation();' + deleteFn + '(' + gas.id + ')" title="Delete"><i class="bi bi-trash"></i></button>' +
            '</span>' +
        '</div>' +
        '<div class="gas-bar">' +
            '<div class="gas-bar-o2" style="width:' + o2 + '%"></div>' +
            '<div class="gas-bar-he" style="width:' + he + '%"></div>' +
            '<div class="gas-bar-n2" style="width:' + n2 + '%"></div>' +
        '</div>';

    return card;
}

function selectGas(id) {
    gasLibrary.forEach(function (g) { g.active = (g.id === id); });
    saveGasLibrary();
    renderLibrary(false);
}

// ── Modal: add / edit gas ─────────────────────────────────────────────────────

var _gasModalInstance = null;

function setGasModalMode(mode) {
    _gasModalMode = mode;
    var isDiluent = mode === 'diluent';
    document.getElementById('modal_diluent_fields').classList.toggle('d-none', !isDiluent);
    document.getElementById('modal_bailout_fields').classList.toggle('d-none', isDiluent);
}

function openGasModal(isBailout, id) {
    var lib = isBailout ? bailoutLibrary : gasLibrary;
    var gas = (id != null) ? lib.find(function (g) { return g.id === id; }) : null;
    if (id != null && !gas) return;
    editingGasId     = (!isBailout && id != null) ? id : null;
    editingBailoutId = (isBailout  && id != null) ? id : null;
    setGasModalMode(isBailout ? 'bailout' : 'diluent');
    document.getElementById('gasModalLabel').textContent =
        (id != null ? 'Edit' : 'Add') + (isBailout ? ' Bailout' : ' Diluent') + ' Gas';
    document.getElementById('modal_o2').value = gas ? gas.o2 : 21;
    document.getElementById('modal_he').value = gas ? gas.he : 0;
    if (isBailout) {
        document.getElementById('modal_mod').value     = gas ? gas.mod_m : bailoutAutoMod(21);
        document.getElementById('modal_cyl_l').value   = gas ? (gas.cyl_l   || 7)   : 7;
        document.getElementById('modal_cyl_bar').value = gas ? (gas.cyl_bar || 200) : 200;
        document.getElementById('modal_bailout_bestmix_note').textContent = '';
    } else {
        document.getElementById('modal_sp').value = gas ? gas.setpoint : 1.4;
        document.getElementById('modal_bestmix_note').textContent = '';
    }
    var diveDepth = parseFloat(document.getElementById('depth_m').value) || 30;
    document.getElementById('modal_bm_depth').value = Math.min(150, Math.max(5, Math.ceil(diveDepth / 5) * 5));
    updateModalPreview();
    _gasModalInstance = bootstrap.Modal.getOrCreateInstance(document.getElementById('gasModal'));
    _gasModalInstance.show();
}

function saveGas() {
    if (_gasModalMode === 'bailout') {
        _saveBailoutGas();
        return;
    }
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
    renderLibrary(false);
    if (_gasModalInstance) _gasModalInstance.hide();
}

function _saveBailoutGas() {
    var o2  = Math.round(Math.max(0, Math.min(100, parseFloat(document.getElementById('modal_o2').value) || 0)));
    var he  = Math.round(Math.max(0, Math.min(100, parseFloat(document.getElementById('modal_he').value) || 0)));
    var mod = Math.max(3, parseFloat(document.getElementById('modal_mod').value) || 6);
    var cylL   = parseFloat(document.getElementById('modal_cyl_l').value) || 7;
    var cylBar = parseFloat(document.getElementById('modal_cyl_bar').value) || 200;

    if (o2 <= 0 || o2 + he > 100) {
        document.getElementById('modal_o2').classList.add('is-invalid');
        document.getElementById('modal_he').classList.add('is-invalid');
        return;
    }
    document.getElementById('modal_o2').classList.remove('is-invalid');
    document.getElementById('modal_he').classList.remove('is-invalid');

    if (editingBailoutId !== null) {
        var gas = bailoutLibrary.find(function (g) { return g.id === editingBailoutId; });
        if (gas) { gas.o2 = o2; gas.he = he; gas.mod_m = mod; gas.cyl_l = cylL; gas.cyl_bar = cylBar; }
    } else {
        bailoutLibrary.push({ id: nextBailoutId++, o2: o2, he: he, mod_m: mod, cyl_l: cylL, cyl_bar: cylBar, active: true });
    }

    saveBailoutLibrary();
    renderLibrary(true);
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
    renderLibrary(false);
}

function applyBestMix() {
    var depth    = parseFloat(document.getElementById('modal_bm_depth').value) || 30;
    var setpoint = parseFloat(document.getElementById('modal_sp').value) || 1.3;
    var densLim  = selectedDensityLimit();
    var mix      = bestMix(depth, setpoint, densLim);
    document.getElementById('modal_o2').value = mix.o2;
    document.getElementById('modal_he').value = mix.he;
    var limitLabel = densLim === 6.3 ? '6.3 g/L (upper)' : '5.2 g/L (recommended)';
    document.getElementById('modal_bestmix_note').textContent =
        depth + ' m · SP ' + setpoint + ' · O₂ ≤ SP/amb · density ≤ ' + limitLabel;
    updateModalPreview();
}

function applyBailoutBestMix() {
    var depth   = parseFloat(document.getElementById('modal_bm_depth').value) || 30;
    var ppO2    = parseFloat(document.getElementById('modal_bm_ppo2').value) || 1.4;
    var densLim = document.getElementById('dl_upper_bailout').checked ? 6.3 : 5.2;
    var amb     = depth / 10 + 1;
    // Floor (not round) so we never land on the exact ppO₂ boundary; then walk
    // down one step at a time until bailoutAutoMod(o2) >= depth, ensuring the
    // stored MOD is valid for the planned depth.
    var o2Rounded = Math.floor((ppO2 / amb) * 100);
    while (o2Rounded > 0 && bailoutAutoMod(o2Rounded) < depth) { o2Rounded--; }
    // Compute He for density target using the MOD-safe O₂
    var fO2 = o2Rounded / 100;
    var densLimSurf = densLim / amb;
    var fHe = (densLimSurf - RHO_N2 - fO2 * (RHO_O2 - RHO_N2)) / (RHO_HE - RHO_N2);
    fHe = Math.max(0, Math.min(1 - fO2, fHe));
    var heRounded = Math.ceil(fHe * 20) * 5;
    if (o2Rounded + heRounded > 100) heRounded = 100 - o2Rounded;
    document.getElementById('modal_o2').value  = o2Rounded;
    document.getElementById('modal_he').value  = heRounded;
    document.getElementById('modal_mod').value = bailoutAutoMod(o2Rounded);
    var limitLabel = densLim === 6.3 ? '6.3 g/L (upper)' : '5.2 g/L (recommended)';
    document.getElementById('modal_bailout_bestmix_note').textContent =
        depth + ' m · ppO₂ ' + ppO2.toFixed(1) + ' · density ≤ ' + limitLabel;
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

    document.getElementById('modal_bm_depth_val').textContent = document.getElementById('modal_bm_depth').value;

    if (_gasModalMode === 'bailout') {
        document.getElementById('modal_mod_auto').textContent = bailoutAutoMod(o2) + ' m';
        document.getElementById('modal_bm_ppo2_val').textContent = parseFloat(document.getElementById('modal_bm_ppo2').value).toFixed(1);
    }
}

// ── Bailout gas library ───────────────────────────────────────────────────────

var bailoutLibrary = [];
var nextBailoutId  = 1;
var editingBailoutId = null;

var DEFAULT_BAILOUT_GASES = [
    { o2: 100, he: 0,  mod_m: 6,  cyl_l: 11,  cyl_bar: 210 },
    { o2: 80,  he: 0,  mod_m: 9,  cyl_l: 11,  cyl_bar: 210 },
    { o2: 60,  he: 0,  mod_m: 12, cyl_l: 11,  cyl_bar: 210 },
    { o2: 50,  he: 0,  mod_m: 15, cyl_l: 11,  cyl_bar: 210 },
    { o2: 21,  he: 0,  mod_m: 54, cyl_l: 11,  cyl_bar: 210 },
    { o2: 21,  he: 25, mod_m: 54, cyl_l: 11,  cyl_bar: 210 },
    { o2: 20,  he: 55, mod_m: 57, cyl_l: 11,  cyl_bar: 210 },
    { o2: 16,  he: 70, mod_m: 75, cyl_l: 11,  cyl_bar: 210 },
    { o2: 13,  he: 75, mod_m: 96, cyl_l: 11, cyl_bar: 210 },
];

function bailoutAutoMod(o2) {
    if (o2 <= 0) return 150;
    var fo2 = o2 / 100;
    var depthAt14 = (1.4 / fo2 - 1.013) * 10;
    if (depthAt14 <= 10) {
        // Shallow deco gas — 1.6 bar ppO2 limit applies above 10 m
        var depthAt16 = (1.6 / fo2 - 1.013) * 10;
        return Math.max(3, Math.round(depthAt16 / 3) * 3);
    }
    return Math.max(3, Math.floor(depthAt14 / 3) * 3);
}

function saveBailoutLibrary() {
    var data = {
        gases: bailoutLibrary.map(function (g) {
            return { id: g.id, o2: g.o2, he: g.he, mod_m: g.mod_m, cyl_l: g.cyl_l, cyl_bar: g.cyl_bar, active: !!g.active };
        }),
        nextId: nextBailoutId,
    };
    setCookie('planner_bailout_gases', JSON.stringify(data));
}

function loadBailoutLibrary() {
    var raw = getCookie('planner_bailout_gases');
    if (raw) {
        try {
            var data = JSON.parse(raw);
            bailoutLibrary = data.gases || [];
            nextBailoutId  = data.nextId || (bailoutLibrary.length + 1);
            return;
        } catch (e) { /* fall through to defaults */ }
    }
    nextBailoutId = 1;
    bailoutLibrary = DEFAULT_BAILOUT_GASES.map(function (g) {
        return { id: nextBailoutId++, o2: g.o2, he: g.he, mod_m: g.mod_m, cyl_l: g.cyl_l, cyl_bar: g.cyl_bar, active: false };
    });
    saveBailoutLibrary();
}

function activeBailoutGases() {
    return bailoutLibrary.filter(function (g) { return g.active; });
}



function toggleBailoutGas(id) {
    var gas = bailoutLibrary.find(function (g) { return g.id === id; });
    if (gas) gas.active = !gas.active;
    saveBailoutLibrary();
    renderLibrary(true);
}

function confirmDeleteBailoutGas(id) {
    var gas = bailoutLibrary.find(function (g) { return g.id === id; });
    if (!gas) return;
    if (!confirm('Remove ' + gasName(gas.o2, gas.he) + '?')) return;
    bailoutLibrary = bailoutLibrary.filter(function (g) { return g.id !== id; });
    saveBailoutLibrary();
    renderLibrary(true);
}

// ── Settings helpers ──────────────────────────────────────────────────────────

function applyGF(low, high, isBailout) {
    var prefix = isBailout ? 'bailout_gf' : 'gf';
    document.getElementById(prefix + '_low').value  = low;
    document.getElementById(prefix + '_high').value = high;
    setCookie(prefix + '_low',  low);
    setCookie(prefix + '_high', high);
}

function applyBailoutGFFromCCR() {
    var low  = document.getElementById('gf_low').value;
    var high = document.getElementById('gf_high').value;
    applyGF(low, high, true);
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

    var descRate       = parseFloat(document.getElementById('desc_rate').value) || 20;
    var ascRateDeep    = parseFloat(document.getElementById('asc_rate_deep').value) || 9;
    var ascRateShallow = parseFloat(document.getElementById('asc_rate_shallow').value) || 3;
    var lastStopM      = parseInt(document.getElementById('last_stop_m').value) || 3;
    var cnsWarnPct     = parseFloat(document.getElementById('cns_warn_pct').value) || 80;

    var activeBailout  = activeBailoutGases();
    var bailoutGfLow   = parseFloat(document.getElementById('bailout_gf_low').value) || 50;
    var bailoutGfHigh  = parseFloat(document.getElementById('bailout_gf_high').value) || 80;

    var payload = JSON.stringify({
        diluent_o2:           gas.o2,
        diluent_he:           gas.he,
        setpoint:             gas.setpoint,
        depth_m:              parseFloat(document.getElementById('depth_m').value),
        bottom_time_min:      parseFloat(document.getElementById('bottom_time').value),
        gf_low:               gfLow,
        gf_high:              gfHigh,
        desc_rate_mpm:        descRate,
        asc_rate_deep_mpm:    ascRateDeep,
        asc_rate_shallow_mpm: ascRateShallow,
        last_stop_m:          lastStopM,
        cns_warn_pct:         cnsWarnPct,
        bailout_gases:        activeBailout.map(function (g) { return { o2: g.o2, he: g.he, mod_m: g.mod_m, cyl_l: g.cyl_l || null, cyl_bar: g.cyl_bar || null }; }),
        bailout_gf_low:       bailoutGfLow,
        bailout_gf_high:      bailoutGfHigh,
        sac_bottom_lpm:       parseFloat(document.getElementById('sac_bottom').value) || 20,
        sac_deco_lpm:         parseFloat(document.getElementById('sac_deco').value) || 15,
        reserve_bar:          parseFloat(document.getElementById('reserve_bar').value) || 50,
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

// ── Schedule table helpers ────────────────────────────────────────────────────

function buildScheduleTable() {
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
        '<th>Depth</th><th>T</th><th>RT</th>' +
        '<th>ppO₂</th><th>g/L</th><th>Gas</th>' +
        '</tr>';
    table.appendChild(thead);
    var tbody = document.createElement('tbody');
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    cardBody.appendChild(tableWrap);
    card.appendChild(cardBody);
    return { card: card, tbody: tbody };
}

function densTd(o2, he, depthM) {
    var v = surfaceDensity(o2, he) * (depthM / 10.0 + 1.0);
    var color = v > 6.3 ? '#dc3545' : v > 5.2 ? '#e07000' : '';
    return '<td' + (color ? ' style="color:' + color + '"' : '') + '>' + v.toFixed(2) + '</td>';
}

// ── Result rendering ──────────────────────────────────────────────────────────

function buildResult(data) {
    var frag = document.createDocumentFragment();

    if (data.warnings) {
        data.warnings.forEach(function (w) {
            frag.appendChild(buildAlert(w.level, w.message));
        });
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
    var depthM       = parseFloat(document.getElementById('depth_m').value) || 0;
    var btMin        = data.bottom_time_actual != null ? data.bottom_time_actual : (parseFloat(document.getElementById('bottom_time').value) || 0);
    var sp           = gas ? gas.setpoint : 1.3;
    var gO2          = gas ? gas.o2 : 21;
    var gHe          = gas ? gas.he : 0;
    var gName        = gas ? gasName(gO2, gHe) : '—';
    var gShort       = gas ? gasNameCompact(gO2, gHe) : '—';
    var descRate     = parseFloat(document.getElementById('desc_rate').value) || 20;
    var descTime     = Math.round(depthM / descRate);
    var flatBtMin    = Math.round(btMin - descTime);   // flat time at depth

    var t = buildScheduleTable();
    var tbody = t.tbody;

    // Descent row
    var trDesc = document.createElement('tr');
    trDesc.innerHTML =
        '<td class="ps-2"><i class="bi bi-arrow-down-circle" style="color:#0077b6"></i></td>' +
        '<td>0→' + depthM + 'm</td>' +
        '<td>' + descTime + '</td>' +
        '<td>' + descTime + '</td>' +
        '<td>' + sp.toFixed(2) + '</td>' +
        densTd(gO2, gHe, depthM) +
        '<td>' + gShort + '</td>';
    tbody.appendChild(trDesc);

    // Bottom row
    var trBtm = document.createElement('tr');
    trBtm.innerHTML =
        '<td class="ps-2"><i class="bi bi-circle-fill" style="color:#03045e;font-size:0.55em;vertical-align:middle"></i></td>' +
        '<td>' + depthM + 'm</td>' +
        '<td>' + flatBtMin + '</td>' +
        '<td>' + Math.round(btMin) + '</td>' +
        '<td>' + sp.toFixed(2) + '</td>' +
        densTd(gO2, gHe, depthM) +
        '<td>' + gShort + '</td>';
    tbody.appendChild(trBtm);

    if (data.stops.length === 0) {
        var ascTime = Math.round(data.total_time_min - btMin);
        var ascRuntime = Math.round(data.total_time_min);
        var trAsc = document.createElement('tr');
        trAsc.innerHTML =
            '<td class="ps-2"><i class="bi bi-arrow-up-circle" style="color:#198754"></i></td>' +
            '<td>' + depthM + '→0m</td>' +
            '<td>' + ascTime + '</td>' +
            '<td>' + ascRuntime + '</td>' +
            '<td>' + sp.toFixed(2) + '</td>' +
            '<td>—</td>' +
            '<td>' + gShort + '</td>';
        tbody.appendChild(trAsc);
    } else {
        data.stops.forEach(function (stop) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td class="ps-2"><i class="bi bi-arrow-up-circle" style="color:#e07000"></i></td>' +
                '<td>' + stop.depth_m + 'm</td>' +
                '<td>' + stop.time_min + '</td>' +
                '<td>' + Math.round(stop.runtime_min) + '</td>' +
                '<td>' + sp.toFixed(2) + '</td>' +
                densTd(gO2, gHe, stop.depth_m) +
                '<td>' + gShort + '</td>';
            tbody.appendChild(tr);
        });
    }

    scheduleDiv.appendChild(t.card);

    if (data.tts_min !== undefined) {
        scheduleDiv.appendChild(buildMetricsCard(data));
    }

    var hasChart = data.profile_points && data.profile_points.length > 2;
    var hasBailoutChart = data.bailout && data.bailout.profile_points && data.bailout.profile_points.length > 2;

    var sharedXMax = 0;
    if (hasChart && hasBailoutChart) {
        var ccrXMax = Math.max.apply(null, data.profile_points.map(function (p) { return p.t; }));
        var bailoutXMax = Math.max.apply(null, data.bailout.profile_points.map(function (p) { return p.t; })) + btMin;
        sharedXMax = Math.max(ccrXMax, bailoutXMax);
    }

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
        chartCol.appendChild(_buildChartWrap('Dive Profile', data, _charts.ccr, sharedXMax));
        row.appendChild(chartCol);

        frag.appendChild(row);
    } else {
        frag.appendChild(scheduleDiv);
    }

    if (data.bailout) {
        frag.appendChild(buildBailoutScheduleCard(data, sharedXMax, data.bottom_time_actual || btMin));
    }

    return frag;
}

// ── Bailout schedule rendering ────────────────────────────────────────────────

function bailoutGasAtDepth(depth) {
    var active = activeBailoutGases();
    if (active.length === 0) return null;
    var sorted = active.slice().sort(function (a, b) { return a.mod_m - b.mod_m; });
    for (var i = 0; i < sorted.length; i++) {
        if (depth <= sorted[i].mod_m) return sorted[i];
    }
    return sorted[sorted.length - 1];
}

function buildBailoutScheduleCard(data, xMax, btActual) {
    var bailout   = data.bailout;
    var depthM    = parseFloat(document.getElementById('depth_m').value) || 0;
    var btMin     = btActual != null ? btActual : (parseFloat(document.getElementById('bottom_time').value) || 0);
    var descRate  = parseFloat(document.getElementById('desc_rate').value) || 20;
    var gas       = activeGas();
    var sp        = gas ? gas.setpoint : 1.3;
    var gShort    = gas ? gasNameCompact(gas.o2, gas.he) : '—';
    var descTime  = Math.round(depthM / descRate);
    var flatBtMin = Math.round(btMin - descTime);

    var section = document.createElement('div');
    section.className = 'mb-4 mt-4';

    var heading = document.createElement('div');
    heading.className = 'mb-1 d-flex align-items-center gap-2';
    heading.innerHTML =
        '<span class="result-heading">Bailout Decompression Schedule</span>' +
        '<button class="info-btn" tabindex="0"' +
        ' data-bs-toggle="popover" data-bs-trigger="focus" data-bs-placement="auto"' +
        ' data-bs-title="About this plan"' +
        ' data-bs-content="Worst-case scenario: bail out at end of bottom time. Tissue loading from the CCR phase is carried into the OC ascent.">ⓘ</button>';
    setTimeout(initPopovers, 0);

    var t = buildScheduleTable();
    var tbody = t.tbody;

    // CCR descent row
    var trDesc = document.createElement('tr');
    trDesc.style.background = 'rgba(0,119,182,0.04)';
    trDesc.innerHTML =
        '<td class="ps-2"><i class="bi bi-arrow-down-circle" style="color:#0077b6"></i></td>' +
        '<td>0→' + depthM + 'm</td>' +
        '<td>' + descTime + '</td>' +
        '<td>' + descTime + '</td>' +
        '<td>' + sp.toFixed(2) + '</td>' +
        densTd(gas ? gas.o2 : 21, gas ? gas.he : 0, depthM) +
        '<td>' + gShort + '</td>';
    tbody.appendChild(trDesc);

    // CCR bottom row
    var trBtm = document.createElement('tr');
    trBtm.style.background = 'rgba(0,119,182,0.04)';
    trBtm.innerHTML =
        '<td class="ps-2"><i class="bi bi-circle-fill" style="color:#03045e;font-size:0.55em;vertical-align:middle"></i></td>' +
        '<td>' + depthM + 'm</td>' +
        '<td>' + flatBtMin + '</td>' +
        '<td>' + Math.round(btMin) + '</td>' +
        '<td>' + sp.toFixed(2) + '</td>' +
        densTd(gas ? gas.o2 : 21, gas ? gas.he : 0, depthM) +
        '<td>' + gShort + '</td>';
    tbody.appendChild(trBtm);

    // OC bailout switch row
    var firstOcGas = bailoutGasAtDepth(depthM);
    var firstOcName = firstOcGas ? gasNameCompact(firstOcGas.o2, firstOcGas.he) : '—';
    var firstOcPpO2 = firstOcGas ? (firstOcGas.o2 / 100 * (depthM / 10 + 1.013)).toFixed(2) : '—';
    var trSwitch = document.createElement('tr');
    trSwitch.style.background = 'rgba(220,53,69,0.07)';
    trSwitch.innerHTML =
        '<td class="ps-2"><i class="bi bi-lightning-charge-fill" style="color:#dc3545"></i></td>' +
        '<td>' + depthM + 'm</td>' +
        '<td>—</td>' +
        '<td>' + Math.round(btMin) + '</td>' +
        '<td>' + firstOcPpO2 + '</td>' +
        (firstOcGas ? densTd(firstOcGas.o2, firstOcGas.he, depthM) : '<td>—</td>') +
        '<td>' + firstOcName + '</td>';
    tbody.appendChild(trSwitch);

    if (bailout.stops.length === 0) {
        var ascTime = Math.round(bailout.total_time_min);
        var trAsc = document.createElement('tr');
        trAsc.innerHTML =
            '<td class="ps-2"><i class="bi bi-arrow-up-circle" style="color:#198754"></i></td>' +
            '<td>' + depthM + '→0m</td>' +
            '<td>' + ascTime + '</td>' +
            '<td>' + Math.round(btMin + bailout.total_time_min) + '</td>' +
            '<td>—</td><td>—</td><td>—</td>';
        tbody.appendChild(trAsc);
    } else {
        bailout.stops.forEach(function (stop) {
            var g = bailoutGasAtDepth(stop.depth_m);
            var gName = g ? gasNameCompact(g.o2, g.he) : '—';
            var ppO2  = g ? (g.o2 / 100 * (stop.depth_m / 10 + 1.013)).toFixed(2) : '—';
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td class="ps-2"><i class="bi bi-arrow-up-circle" style="color:#e07000"></i></td>' +
                '<td>' + stop.depth_m + 'm</td>' +
                '<td>' + stop.time_min + '</td>' +
                '<td>' + Math.round(btMin + stop.runtime_min) + '</td>' +
                '<td>' + ppO2 + '</td>' +
                (g ? densTd(g.o2, g.he, stop.depth_m) : '<td>—</td>') +
                '<td>' + gName + '</td>';
            tbody.appendChild(tr);
        });
    }

    section.appendChild(t.card);

    var cnsColor = bailout.cns_pct > 80 ? '#dc3545' : bailout.cns_pct > 40 ? '#e07000' : 'var(--ocean)';
    var otuColor = bailout.otu > 250 ? '#dc3545' : bailout.otu > 150 ? '#e07000' : 'var(--navy)';
    var metCard = document.createElement('div');
    metCard.className = 'card mt-3';
    var metBody = document.createElement('div');
    metBody.className = 'card-body py-2 px-3';
    var totalRuntime = Math.round(btMin + bailout.total_time_min);
    metBody.innerHTML =
        '<div class="d-flex justify-content-around text-center">' +
            '<div><div class="field-label mb-1">Runtime</div>' +
                '<div style="font-size:1.05rem;font-weight:800;color:var(--ocean);">' + totalRuntime + ' min</div></div>' +
            '<div><div class="field-label mb-1">TTS (OC)</div>' +
                '<div style="font-size:1.05rem;font-weight:800;color:var(--ocean);">' + bailout.tts_min + ' min</div></div>' +
            '<div><div class="field-label mb-1">CNS</div>' +
                '<div style="font-size:1.05rem;font-weight:800;color:' + cnsColor + ';">' + bailout.cns_pct + '%</div></div>' +
            '<div><div class="field-label mb-1">OTU</div>' +
                '<div style="font-size:1.05rem;font-weight:800;color:' + otuColor + ';">' + bailout.otu + '</div></div>' +
        '</div>';

    if (bailout.gas_supply && bailout.gas_supply.length > 0) {
        var supplyHtml = '<hr class="my-2"><div class="field-label mb-1">Gas Supply</div>';
        bailout.gas_supply.forEach(function (gs) {
            var name = gs.he > 0 ? 'Tx' + gs.o2 + '/' + gs.he : (gs.o2 === 21 ? 'Air' : gs.o2 === 100 ? 'O₂' : 'Nx' + gs.o2);
            var pctColor = '';
            if (gs.available_L != null) {
                pctColor = gs.pct > 90 ? '#dc3545' : gs.pct > 70 ? '#e07000' : '';
            }
            supplyHtml +=
                '<div class="d-flex align-items-center gap-2 mb-1" style="font-size:0.8rem;">' +
                    '<span style="font-weight:700;min-width:4.5rem;">' + name + '</span>';
            if (gs.available_L != null) {
                var barW = Math.min(100, gs.pct);
                supplyHtml +=
                    '<div style="flex:1;background:#e9ecef;border-radius:4px;height:8px;overflow:hidden;">' +
                        '<div style="width:' + barW + '%;height:100%;background:' + (pctColor || 'var(--aqua)') + ';border-radius:4px;"></div>' +
                    '</div>' +
                    '<span style="min-width:5.5rem;text-align:right;color:' + (pctColor || 'var(--navy)') + ';font-weight:600;">' +
                        gs.consumed_L + ' / ' + gs.available_L + ' L' +
                    '</span>' +
                    '<span style="min-width:2.5rem;text-align:right;color:' + (pctColor || 'var(--muted)') + ';font-weight:700;">' +
                        gs.pct + '%' +
                    '</span>';
            } else {
                supplyHtml +=
                    '<span style="color:var(--muted);">' + gs.consumed_L + ' L used</span>';
            }
            supplyHtml += '</div>';
        });
        metBody.innerHTML += supplyHtml;
    }

    metCard.appendChild(metBody);

    var hasBailoutChart = bailout.profile_points && bailout.profile_points.length > 2;
    if (hasBailoutChart) {
        // Combine CCR bottom phase (t ≤ btMin) with OC ascent (offset by btMin)
        var ccrBottomPts = (data.profile_points || []).filter(function (p) { return p.t <= btMin + 0.05; });
        var ocPts = bailout.profile_points.map(function (p) {
            return { t: p.t + btMin, d: p.d, c: p.c, sats: p.sats };
        });
        var bailoutChartData = {
            profile_points: ccrBottomPts.concat(ocPts),
            tissue_saturations: bailout.tissue_saturations,
        };

        var row = document.createElement('div');
        row.className = 'row g-3 align-items-start';

        var tableCol = document.createElement('div');
        tableCol.className = 'col-12 col-lg-5';
        tableCol.appendChild(heading);
        tableCol.appendChild(t.card);
        tableCol.appendChild(metCard);
        row.appendChild(tableCol);

        var chartCol = document.createElement('div');
        chartCol.className = 'col-12 col-lg-7';
        chartCol.appendChild(_buildChartWrap('Bailout Profile', bailoutChartData, _charts.bailout, xMax));
        row.appendChild(chartCol);

        section.appendChild(row);
    } else {
        section.appendChild(heading);
        section.appendChild(t.card);
        section.appendChild(metCard);
    }

    return section;
}

// ── Dive profile chart ────────────────────────────────────────────────────────

var _charts = {
    ccr:     { profile: null, tissue: null, gfField: 'gf_high',         surfaceLabel: 'at surfacing' },
    bailout: { profile: null, tissue: null, gfField: 'bailout_gf_high', surfaceLabel: 'at OC surfacing' },
};

var TISSUE_LABELS = ["5'","8'","12'","18'","27'","38'","54'","77'","109'","146'","187'","239'","305'","390'","498'","635'"];

function _profileChartConfig(data, xMax) {
    var pts = data.profile_points;
    var maxDepth = Math.max.apply(null, pts.map(function (p) { return p.d; }));
    return {
        type: 'line',
        data: {
            datasets: [
                {
                    label: 'Depth',
                    data: pts.map(function (p) { return { x: p.t, y: p.d }; }),
                    borderColor: 'rgba(0,100,160,0.85)',
                    backgroundColor: 'rgba(0,119,182,0.10)',
                    fill: true, tension: 0, pointRadius: 0, borderWidth: 2, order: 2,
                },
                {
                    label: 'Ceiling',
                    data: pts.map(function (p) { return { x: p.t, y: p.c }; }),
                    borderColor: 'rgba(220,80,40,0.8)',
                    borderDash: [6, 4],
                    backgroundColor: 'transparent',
                    fill: false, tension: 0, pointRadius: 0, borderWidth: 1.5, order: 1,
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
                    suggestedMax: xMax || undefined,
                    title: { display: true, text: 'Time (min)', font: { size: 10 } },
                    ticks: { font: { size: 10 } },
                },
                y: {
                    reverse: true, min: 0,
                    suggestedMax: Math.ceil(maxDepth * 1.08 / 5) * 5,
                    title: { display: true, text: 'Depth (m)', font: { size: 10 } },
                    ticks: { font: { size: 10 } },
                },
            },
            plugins: {
                legend: { display: true, labels: { font: { size: 10 }, boxWidth: 14, padding: 10 } },
                tooltip: {
                    callbacks: {
                        title: function (items) { return Math.round(items[0].parsed.x) + ' min'; },
                        label: function (item) { return item.dataset.label + ': ' + item.parsed.y + ' m'; },
                    },
                },
            },
        },
    };
}

function _tissueChartConfig(sats, gfHighPct, titleText) {
    var colors = sats.map(function (s) {
        if (s > 100)       return 'rgba(220,53,69,0.75)';
        if (s > gfHighPct) return 'rgba(255,140,0,0.75)';
        return 'rgba(32,150,130,0.75)';
    });
    return {
        data: {
            labels: TISSUE_LABELS,
            datasets: [
                {
                    type: 'bar', label: 'Saturation', data: sats,
                    backgroundColor: colors, borderRadius: 3, order: 2,
                },
                {
                    type: 'line', label: 'GF High (' + gfHighPct + '%)',
                    data: Array(16).fill(gfHighPct),
                    borderColor: 'rgba(255,140,0,0.9)', borderDash: [5, 4],
                    borderWidth: 1.5, pointRadius: 0, fill: false, order: 1,
                },
                {
                    type: 'line', label: 'M-value (100%)',
                    data: Array(16).fill(100),
                    borderColor: 'rgba(220,53,69,0.85)', borderDash: [3, 3],
                    borderWidth: 1.5, pointRadius: 0, fill: false, order: 0,
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
                title: { display: true, text: titleText, font: { size: 10 }, color: '#555', padding: { bottom: 2 } },
            },
        },
    };
}

function _updateTissueChart(ctx, sats, timeMin) {
    if (!ctx.tissue) return;
    var gfHighPct = parseFloat(document.getElementById(ctx.gfField).value) || 80;
    var satsPct = sats.map(function (r) { return Math.round(r * 100); });
    ctx.tissue.data.datasets[0].data = satsPct;
    ctx.tissue.data.datasets[0].backgroundColor = satsPct.map(function (s) {
        if (s > 100)       return 'rgba(220,53,69,0.75)';
        if (s > gfHighPct) return 'rgba(255,140,0,0.75)';
        return 'rgba(32,150,130,0.75)';
    });
    ctx.tissue.options.plugins.title.text = 'Tissue loading ' +
        (timeMin !== null ? 'at ' + parseFloat(timeMin).toFixed(1) + ' min' : ctx.surfaceLabel);
    ctx.tissue.update('none');
}

function _buildChartWrap(title, data, ctx, xMax) {
    var wrap = document.createElement('div');
    wrap.className = 'chart-wrap';

    var header = document.createElement('div');
    header.className = 'chart-header';
    var titleEl = document.createElement('span');
    titleEl.className = 'result-heading';
    titleEl.textContent = title;
    var fsBtn = document.createElement('button');
    fsBtn.className = 'chart-fs-btn';
    fsBtn.title = 'Full screen';
    fsBtn.innerHTML = '<i class="bi bi-fullscreen"></i>';
    fsBtn.onclick = function () { toggleChartFullscreen(wrap, fsBtn); };
    header.appendChild(titleEl);
    header.appendChild(fsBtn);
    wrap.appendChild(header);

    var profileBox = document.createElement('div');
    profileBox.className = 'profile-canvas';
    profileBox.style.height = '260px';
    profileBox.style.position = 'relative';
    var profileCanvas = document.createElement('canvas');
    profileBox.appendChild(profileCanvas);
    wrap.appendChild(profileBox);

    var tissueBox = document.createElement('div');
    tissueBox.style.height = '200px';
    tissueBox.style.position = 'relative';
    var tissueCanvas = document.createElement('canvas');
    tissueBox.appendChild(tissueCanvas);
    wrap.appendChild(tissueBox);

    setTimeout(function () {
        if (ctx.profile) { ctx.profile.destroy(); ctx.profile = null; }
        ctx.profile = new Chart(profileCanvas, _profileChartConfig(data, xMax));

        if (ctx.tissue) { ctx.tissue.destroy(); ctx.tissue = null; }
        var gfHighPct = parseFloat(document.getElementById(ctx.gfField).value) || 80;
        var sats = data.tissue_saturations.map(function (r) { return Math.round(r * 100); });
        ctx.tissue = new Chart(tissueCanvas, _tissueChartConfig(sats, gfHighPct, 'Tissue loading ' + ctx.surfaceLabel));

        function hoverAtX(offsetX) {
            if (!ctx.profile || !ctx.tissue) return;
            var xVal = ctx.profile.scales.x.getValueForPixel(offsetX);
            var pts = data.profile_points;
            if (!pts || !pts.length) return;
            var nearest = pts.reduce(function (prev, curr) {
                return Math.abs(curr.t - xVal) < Math.abs(prev.t - xVal) ? curr : prev;
            });
            if (nearest && nearest.sats) _updateTissueChart(ctx, nearest.sats, nearest.t);
        }
        function resetTissue() { _updateTissueChart(ctx, data.tissue_saturations, null); }

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
    Object.keys(_charts).forEach(function (key) {
        var c = _charts[key];
        if (c.profile) c.profile.resize();
        if (c.tissue)  c.tissue.resize();
    });
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

function buildAlert(type, message) {
    var div = document.createElement('div');
    div.className = 'alert alert-' + type + ' rounded-3 density-warning mb-3';
    div.textContent = message;
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
    renderLibrary(false);
    loadBailoutLibrary();
    renderLibrary(true);

    var savedLow  = getCookie('gf_low');
    var savedHigh = getCookie('gf_high');
    if (savedLow)  document.getElementById('gf_low').value  = savedLow;
    if (savedHigh) document.getElementById('gf_high').value = savedHigh;

    var savedBailoutGfLow  = getCookie('bailout_gf_low');
    var savedBailoutGfHigh = getCookie('bailout_gf_high');
    if (savedBailoutGfLow)  document.getElementById('bailout_gf_low').value  = savedBailoutGfLow;
    if (savedBailoutGfHigh) document.getElementById('bailout_gf_high').value = savedBailoutGfHigh;

    var savedDescRate       = getCookie('desc_rate');
    var savedAscRateDeep    = getCookie('asc_rate_deep');
    var savedAscRateShallow = getCookie('asc_rate_shallow');
    var savedLastStopM      = getCookie('last_stop_m');
    if (savedDescRate)       document.getElementById('desc_rate').value        = savedDescRate;
    if (savedAscRateDeep)    document.getElementById('asc_rate_deep').value    = savedAscRateDeep;
    if (savedAscRateShallow) document.getElementById('asc_rate_shallow').value = savedAscRateShallow;
    if (savedLastStopM)      document.getElementById('last_stop_m').value      = savedLastStopM;
    var savedCnsWarnPct = getCookie('cns_warn_pct');
    if (savedCnsWarnPct) document.getElementById('cns_warn_pct').value = savedCnsWarnPct;
    var savedSacBottom  = getCookie('sac_bottom');
    var savedSacDeco    = getCookie('sac_deco');
    var savedReserveBar = getCookie('reserve_bar');
    if (savedSacBottom)  document.getElementById('sac_bottom').value  = savedSacBottom;
    if (savedSacDeco)    document.getElementById('sac_deco').value    = savedSacDeco;
    if (savedReserveBar) document.getElementById('reserve_bar').value = savedReserveBar;

    ['gf_low', 'gf_high', 'bailout_gf_low', 'bailout_gf_high', 'desc_rate', 'asc_rate_deep', 'asc_rate_shallow', 'last_stop_m', 'cns_warn_pct', 'sac_bottom', 'sac_deco', 'reserve_bar'].forEach(function (id) {
        document.getElementById(id).addEventListener('change', function () {
            setCookie(id, this.value);
        });
    });

    initPopovers();
    calculate();
});
