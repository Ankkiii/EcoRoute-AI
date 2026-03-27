// API Configuration
const API_BASE_URL = window.location.origin;

// Google Maps Variables
let map;
let directionsService;
let markers = [];
let mapsLoaded = false;
let activePolylines = [];

// Chart instance
let emissionChart = null;

// Route colors by emission rank
const ROUTE_COLORS = ['#10b981', '#f59e0b', '#ef4444'];

// -----------------------------
// GOOGLE MAPS
// -----------------------------
function initMap() {
    try {
        const mapContainer = document.getElementById('map');
        if (!mapContainer) return;

        map = new google.maps.Map(mapContainer, {
            zoom: 5,
            center: { lat: 20.5937, lng: 78.9629 },
            mapTypeControl: true,
            streetViewControl: false,
            fullscreenControl: true
        });

        directionsService = new google.maps.DirectionsService();
        mapsLoaded = true;
        console.log('Google Maps initialized');
    } catch (error) {
        console.error('Error initializing Google Maps:', error);
    }
}
window.initMap = initMap;

function clearPolylines() {
    activePolylines.forEach(p => p.setMap(null));
    activePolylines = [];
}

function displayRouteOnMap(source, destination, routeResults) {
    if (!mapsLoaded || !directionsService) return;
    clearPolylines();

    // Show map section and trigger resize so Google Maps renders correctly
    const mapSection = document.getElementById('mapSection');
    if (mapSection) {
        mapSection.style.display = 'block';
        google.maps.event.trigger(map, 'resize');
    }

    directionsService.route({
        origin: source,
        destination: destination,
        travelMode: google.maps.TravelMode.DRIVING,
        provideRouteAlternatives: true
    }, (result, status) => {
        if (status !== 'OK') return;

        const bounds = new google.maps.LatLngBounds();
        const sorted = [...(routeResults || [])].sort((a, b) => a.predicted_co2_kg - b.predicted_co2_kg);
        const rankMap = {};
        sorted.forEach((r, i) => { rankMap[r.route_number] = i; });

        result.routes.forEach((route, idx) => {
            const routeNumber = idx + 1;
            const rank = rankMap[routeNumber] ?? idx;
            const color = ROUTE_COLORS[Math.min(rank, ROUTE_COLORS.length - 1)];
            const isRecommended = rank === 0;

            const path = [];
            route.legs[0].steps.forEach(step => step.path.forEach(pt => path.push(pt)));

            const polyline = new google.maps.Polyline({
                path, map,
                strokeColor: color,
                strokeWeight: isRecommended ? 6 : 4,
                strokeOpacity: isRecommended ? 0.9 : 0.55,
                zIndex: isRecommended ? 10 : 5
            });
            polyline._routeNumber = routeNumber;
            activePolylines.push(polyline);
            path.forEach(pt => bounds.extend(pt));

            // Click on polyline → highlight it and scroll to its route card
            polyline.addListener('click', () => {
                highlightPolyline(routeNumber);
                // Highlight corresponding route card
                document.querySelectorAll('[data-route]').forEach(c => {
                    const match = parseInt(c.dataset.route, 10) === routeNumber;
                    c.classList.toggle('route-card-active', match);
                    if (match) c.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                });
            });
        });

        map.fitBounds(bounds);
    });
}

function highlightPolyline(routeNumber) {
    activePolylines.forEach(p => {
        const isSelected = p._routeNumber === routeNumber;
        p.setOptions({
            strokeWeight: isSelected ? 7 : 3,
            strokeOpacity: isSelected ? 1.0 : 0.3,
            zIndex: isSelected ? 20 : 1
        });
    });
}

// -----------------------------
// MAIN INIT
// -----------------------------
document.addEventListener('DOMContentLoaded', () => {
    console.log('EcoRoute AI initialized');

    // DOM refs
    const routeForm = document.getElementById('routeForm');
    const errorSection = document.getElementById('errorSection');
    const errorText = document.getElementById('errorText');
    const resultsSection = document.getElementById('resultsSection');
    const recommendedRouteEl = document.getElementById('recommendedRoute');
    const alternativeRoutesEl = document.getElementById('alternativeRoutes');
    const alternativeRoutesContainer = document.getElementById('alternativeRoutesContainer');
    const savingsSummary = document.getElementById('savingsSummary');
    const submitButton = routeForm.querySelector('button[type="submit"]');
    const btnText = submitButton.querySelector('.btn-text');
    const spinner = submitButton.querySelector('.spinner');

    // ---- Helpers ----
    function showError(message) {
        errorText.textContent = message;
        errorSection.style.display = 'block';
        errorSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    function hideError() {
        errorSection.style.display = 'none';
        errorText.textContent = '';
    }
    function hideResults() {
        resultsSection.style.display = 'none';
        const cs = document.getElementById('compareSection');
        if (cs) cs.style.display = 'none';
        ['compareGrades', 'compareAllRoutes', 'compareAlternatives'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.remove();
        });
        const ms = document.getElementById('mapSection');
        if (ms) ms.style.display = 'none';
        const cc = document.getElementById('chartContainer');
        if (cc) { cc.style.display = 'none'; cc.style.height = ''; }
        const gb = document.getElementById('emissionGradeBanner');
        if (gb) gb.style.display = 'none';
        const ga = document.getElementById('greenAlternatives');
        if (ga) ga.style.display = 'none';
        if (emissionChart) { emissionChart.destroy(); emissionChart = null; }
        clearPolylines();
    }
    function showLoading() {
        submitButton.disabled = true;
        btnText.textContent = 'Finding Routes...';
        spinner.style.display = 'inline-block';
    }
    function hideLoading() {
        submitButton.disabled = false;
        btnText.textContent = 'Find Eco-Routes';
        spinner.style.display = 'none';
    }

    // ---- Form Submit ----
    routeForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const formData = {
            vehicle_no: document.getElementById('vehicle_no').value.trim(),
            source: document.getElementById('source').value.trim(),
            destination: document.getElementById('destination').value.trim()
        };

        const fuelPriceInput = document.getElementById('fuel_price').value.trim();
        if (fuelPriceInput) {
            const parsed = parseFloat(fuelPriceInput);
            if (!isNaN(parsed) && parsed > 0) formData.fuel_price_per_litre = parsed;
        }

        if (!validateForm(formData, showError)) return;

        hideError();
        hideResults();
        showLoading();

        const compareMode = document.getElementById('compareVehicleGroup').style.display !== 'none';
        const vehicle2 = document.getElementById('vehicle_no_2').value.trim();

        try {
            if (compareMode && vehicle2) {
                const [data1, data2] = await Promise.all([
                    fetchEcoRoute(formData),
                    fetchEcoRoute({ ...formData, vehicle_no: vehicle2 })
                ]);
                displayComparison(data1, data2, resultsSection);
                // Show map for compare mode too — same route, both vehicles
                displayRouteOnMap(formData.source, formData.destination, data1.all_routes);
            } else {
                const data = await fetchEcoRoute(formData);
                displayResults(data, recommendedRouteEl, alternativeRoutesEl,
                    alternativeRoutesContainer, savingsSummary, resultsSection, showError);
                displayRouteOnMap(formData.source, formData.destination, data.all_routes);
            }
        } catch (error) {
            showError(error.message);
        } finally {
            hideLoading();
        }
    });

    // ---- Init features ----
    initAutocomplete();
    loadPopularVehicles();
    initCompareToggle();
});

// -----------------------------
// API
// -----------------------------
async function fetchEcoRoute(payload) {
    const response = await fetch(`${API_BASE_URL}/eco-route`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'An error occurred while fetching routes');
    return data;
}

// -----------------------------
// VALIDATION
// -----------------------------
function validateForm(formData, showError) {
    if (!formData.vehicle_no) { showError('Please enter a vehicle number'); return false; }
    if (formData.vehicle_no.length > 50) { showError('Vehicle number is too long (max 50 characters)'); return false; }
    if (!formData.source) { showError('Please enter a source location'); return false; }
    if (formData.source.length > 500) { showError('Source location is too long'); return false; }
    if (!formData.destination) { showError('Please enter a destination location'); return false; }
    if (formData.destination.length > 500) { showError('Destination location is too long'); return false; }
    return true;
}

// -----------------------------
// DISPLAY RESULTS
// -----------------------------
function displayResults(data, recommendedRouteEl, alternativeRoutesEl,
    alternativeRoutesContainer, savingsSummary, resultsSection, showError) {

    recommendedRouteEl.innerHTML = createRouteCard(data.recommended_route, true, data.co2_equivalents);
    recommendedRouteEl.dataset.route = data.recommended_route.route_number;
    recommendedRouteEl.style.cursor = 'pointer';

    // Show emission grade banner above recommended route
    const gradeContainer = document.getElementById('emissionGradeBanner');
    if (gradeContainer && data.emission_grade) {
        gradeContainer.innerHTML = buildGradeBanner(data.vehicle_no, data.emission_grade, data.co2_per_km);
        gradeContainer.style.display = 'block';
    }

    if (data.emission_savings_kg > 0) {
        savingsSummary.innerHTML = `
            <h4>🎉 Emission Savings</h4>
            <div class="savings-value">${data.emission_savings_kg.toFixed(2)} kg CO₂</div>
            <div class="savings-description">
                By choosing the recommended route, you'll save ${data.emission_savings_percent.toFixed(1)}%
                emissions compared to the highest-emission alternative
            </div>`;
        savingsSummary.style.display = 'block';
    } else {
        savingsSummary.style.display = 'none';
    }

    const alternatives = data.all_routes.filter(
        r => r.route_number !== data.recommended_route.route_number
    );

    if (alternatives.length > 0) {
        alternativeRoutesEl.innerHTML = alternatives
            .map(r => `<div class="route-card" data-route="${r.route_number}">${createRouteCard(r, false)}</div>`)
            .join('');
        alternativeRoutesContainer.style.display = 'block';
    } else {
        alternativeRoutesContainer.style.display = 'none';
    }

    resultsSection.style.display = 'block';

    // Wire up route card click → polyline highlight
    document.querySelectorAll('[data-route]').forEach(card => {
        card.style.cursor = 'pointer';
        card.addEventListener('click', () => {
            const rn = parseInt(card.dataset.route, 10);
            highlightPolyline(rn);
            document.querySelectorAll('[data-route]').forEach(c =>
                c.classList.toggle('route-card-active', parseInt(c.dataset.route, 10) === rn)
            );
        });
    });

    // Render chart AFTER section is visible so Chart.js gets correct dimensions
    renderEmissionChart(data.all_routes, data.recommended_route.route_number);

    // Fetch and display greener alternatives
    loadGreenAlternatives(data.vehicle_no);

    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// -----------------------------
// ROUTE CARD HTML
// -----------------------------
function createRouteCard(route, isRecommended, co2Equivalents) {
    const trafficClass = route.traffic_level.toLowerCase();
    const badgeHtml = isRecommended ? '<span class="route-badge best">Best Choice</span>' : '';

    const equivalentsHtml = isRecommended && co2Equivalents ? `
        <div class="co2-equivalents">
            <span class="equiv-item">🌳 ${co2Equivalents.trees_to_offset} trees/yr to offset</span>
            <span class="equiv-item">🔋 ${co2Equivalents.phone_charges.toLocaleString()} phone charges</span>
            <span class="equiv-item">🚗 ${co2Equivalents.km_in_avg_car} km in avg car</span>
        </div>` : '';

    const fuelCostHtml = route.fuel_cost_estimate != null ? `
        <div class="detail-item">
            <span class="detail-label">Fuel Cost</span>
            <span class="detail-value fuel-cost">₹${route.fuel_cost_estimate.toFixed(2)}</span>
        </div>` : '';

    const carbonCostHtml = route.carbon_cost_inr != null ? `
        <div class="detail-item">
            <span class="detail-label">Environmental Cost</span>
            <span class="detail-value carbon-cost">🌍 ₹${route.carbon_cost_inr.toFixed(2)}</span>
        </div>` : '';

    const ecoScoreHtml = route.eco_score != null ? buildEcoScoreBar(route.eco_score) : '';

    return `
        <div class="route-header">
            <span class="route-number">Route ${route.route_number}</span>
            ${badgeHtml}
        </div>
        ${route.summary ? `<div class="route-summary">${route.summary}</div>` : ''}
        <div class="route-details">
            <div class="detail-item">
                <span class="detail-label">Distance</span>
                <span class="detail-value">${route.distance_km.toFixed(1)} km</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Duration</span>
                <span class="detail-value">${formatDuration(route.duration_minutes)}</span>
            </div>
            <div class="detail-item">
                <span class="detail-label">Traffic Level</span>
                <span class="detail-value">
                    <span class="traffic-indicator ${trafficClass}">${route.traffic_level}</span>
                </span>
            </div>
            <div class="detail-item">
                <span class="detail-label">CO₂ Emission</span>
                <span class="detail-value emission">${route.predicted_co2_kg.toFixed(2)} kg</span>
            </div>
            ${fuelCostHtml}
            ${carbonCostHtml}
        </div>
        ${ecoScoreHtml}
        ${equivalentsHtml}
    `;
}

function formatDuration(minutes) {
    const hours = Math.floor(minutes / 60);
    const mins = Math.round(minutes % 60);
    return hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
}

// -----------------------------
// EMISSION CHART
// -----------------------------
function renderEmissionChart(routes, recommendedRouteNumber) {
    const container = document.getElementById('chartContainer');
    const canvas = document.getElementById('emissionChart');
    if (!container || !canvas) return;

    if (emissionChart) { emissionChart.destroy(); emissionChart = null; }

    container.style.display = 'block';

    // Give browser one frame to paint the container before measuring
    requestAnimationFrame(() => {
        const w = container.clientWidth - 40; // subtract padding
        const h = Math.max(130, routes.length * 52 + 40);
        canvas.width = w > 0 ? w : 600;
        canvas.height = h;
        container.style.height = (h + 60) + 'px'; // +60 for title + padding

        const labels = routes.map(r => r.summary || `Route ${r.route_number}`);
        const values = routes.map(r => r.predicted_co2_kg);
        const colors = routes.map(r => r.route_number === recommendedRouteNumber ? '#10b981' : '#f59e0b');

        emissionChart = new Chart(canvas, {
            type: 'bar',
            data: {
                labels,
                datasets: [{
                    label: 'CO₂ Emission (kg)',
                    data: values,
                    backgroundColor: colors,
                    borderColor: colors,
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: false,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.x.toFixed(2)} kg CO₂` } }
                },
                scales: {
                    x: {
                        title: { display: true, text: 'CO₂ (kg)', color: '#94a3b8' },
                        ticks: { color: '#94a3b8' },
                        grid: { color: 'rgba(148,163,184,0.1)' }
                    },
                    y: { ticks: { color: '#94a3b8' }, grid: { display: false } }
                }
            }
        });
    });
}

// -----------------------------
// COMPARE MODE
// -----------------------------
function initCompareToggle() {
    const btn = document.getElementById('compareToggle');
    const group = document.getElementById('compareVehicleGroup');
    const icon = document.getElementById('compareToggleIcon');
    if (!btn) return;
    btn.addEventListener('click', () => {
        const isOpen = group.style.display !== 'none';
        group.style.display = isOpen ? 'none' : 'block';
        icon.textContent = isOpen ? '＋' : '－';
        btn.classList.toggle('active', !isOpen);
        if (isOpen) document.getElementById('vehicle_no_2').value = '';
    });
}

function displayComparison(data1, data2, resultsSection) {
    const section = document.getElementById('compareSection');
    const grid = document.getElementById('compareGrid');
    resultsSection.style.display = 'none';

    const rec1 = data1.recommended_route;
    const rec2 = data2.recommended_route;
    const winner = rec1.predicted_co2_kg <= rec2.predicted_co2_kg ? 1 : 2;

    // Grade banners for both vehicles
    const grade1Html = data1.emission_grade
        ? buildGradeBanner(data1.vehicle_no, data1.emission_grade, data1.co2_per_km) : '';
    const grade2Html = data2.emission_grade
        ? buildGradeBanner(data2.vehicle_no, data2.emission_grade, data2.co2_per_km) : '';

    // Side-by-side comparison cards (with eco-score + carbon cost)
    grid.innerHTML = `
        ${buildCompareCard(data1.vehicle_no, rec1, winner === 1)}
        ${buildCompareCard(data2.vehicle_no, rec2, winner === 2)}
    `;

    // Remove old extras if exist
    ['compareGrades', 'compareAllRoutes', 'compareAlternatives'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.remove();
    });

    // Grade banners
    const gradesDiv = document.createElement('div');
    gradesDiv.id = 'compareGrades';
    gradesDiv.innerHTML = `<div class="compare-grades-wrap">${grade1Html}${grade2Html}</div>`;
    section.insertBefore(gradesDiv, grid);

    // All routes table for vehicle 1
    const routesDiv = document.createElement('div');
    routesDiv.id = 'compareAllRoutes';
    routesDiv.innerHTML = buildAllRoutesTable(data1.vehicle_no, data1.all_routes, data1.recommended_route.route_number);
    section.appendChild(routesDiv);

    // Greener alternatives for vehicle 1
    const altDiv = document.createElement('div');
    altDiv.id = 'compareAlternatives';
    altDiv.className = 'green-alternatives';
    altDiv.style.display = 'none';
    section.appendChild(altDiv);

    section.style.display = 'block';

    // Chart + map + greener alternatives
    renderEmissionChart(data1.all_routes, data1.recommended_route.route_number);

    // Load greener alternatives into compareAlternatives div
    loadGreenAlternativesInto(data1.vehicle_no, altDiv);

    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function buildAllRoutesTable(vehicleNo, routes, recommendedRouteNumber) {
    const rows = routes.map(r => {
        const isRec = r.route_number === recommendedRouteNumber;
        const fuelCell = r.fuel_cost_estimate != null
            ? `₹${r.fuel_cost_estimate.toFixed(2)}`
            : '—';
        return `
            <tr class="${isRec ? 'rec-row' : ''}">
                <td>${isRec ? '🏆 ' : ''}${r.summary || `Route ${r.route_number}`}</td>
                <td>${r.distance_km.toFixed(1)} km</td>
                <td>${formatDuration(r.duration_minutes)}</td>
                <td>${r.traffic_level}</td>
                <td>${r.predicted_co2_kg.toFixed(2)} kg</td>
                <td>${fuelCell}</td>
            </tr>`;
    }).join('');

    return `
        <div class="all-routes-table-wrap">
            <h3>All Routes — ${vehicleNo}</h3>
            <table class="all-routes-table">
                <thead>
                    <tr>
                        <th>Route</th>
                        <th>Distance</th>
                        <th>Duration</th>
                        <th>Traffic</th>
                        <th>CO₂</th>
                        <th>Fuel Cost</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
}

function buildCompareCard(vehicleNo, route, isWinner) {
    const ecoScoreHtml = route.eco_score != null ? buildEcoScoreBar(route.eco_score) : '';
    const carbonHtml = route.carbon_cost_inr != null
        ? `<div class="compare-stat"><span class="compare-label">Environmental Cost</span><span class="compare-value" style="color:#a78bfa">🌍 ₹${route.carbon_cost_inr.toFixed(2)}</span></div>`
        : '';
    return `
        <div class="compare-card ${isWinner ? 'compare-winner' : ''}">
            <div class="compare-card-header">
                <span class="compare-vehicle-name">${vehicleNo}</span>
                ${isWinner ? '<span class="compare-winner-badge">🏆 Lower Emissions</span>' : ''}
            </div>
            <div class="compare-stat">
                <span class="compare-label">Best Route</span>
                <span class="compare-value">${route.summary || `Route ${route.route_number}`}</span>
            </div>
            <div class="compare-stat">
                <span class="compare-label">Distance</span>
                <span class="compare-value">${route.distance_km.toFixed(1)} km</span>
            </div>
            <div class="compare-stat">
                <span class="compare-label">CO₂ Emission</span>
                <span class="compare-value compare-emission ${isWinner ? 'winner-emission' : ''}">${route.predicted_co2_kg.toFixed(2)} kg</span>
            </div>
            <div class="compare-stat">
                <span class="compare-label">Traffic</span>
                <span class="compare-value">${route.traffic_level}</span>
            </div>
            ${carbonHtml}
            ${ecoScoreHtml}
        </div>
    `;
}

// -----------------------------
// NOVELTY FEATURE HELPERS
// -----------------------------

const GRADE_CONFIG = {
    A: { color: '#10b981', label: 'Excellent' },
    B: { color: '#84cc16', label: 'Good' },
    C: { color: '#f59e0b', label: 'Fair' },
    D: { color: '#ef4444', label: 'Poor' }
};

function buildGradeBanner(vehicleNo, grade, co2PerKm) {
    const cfg = GRADE_CONFIG[grade] || GRADE_CONFIG['D'];
    return `
        <div class="grade-banner" style="border-color:${cfg.color}">
            <span class="grade-badge" style="background:${cfg.color}">${grade}</span>
            <span class="grade-text">
                <strong>${vehicleNo}</strong> — Emission Grade: <strong>${grade} (${cfg.label})</strong>
                &nbsp;·&nbsp; ${co2PerKm.toFixed(0)} g CO₂/km
            </span>
        </div>`;
}

function buildEcoScoreBar(score) {
    const color = score >= 80 ? '#10b981' : score >= 60 ? '#84cc16' : score >= 40 ? '#f59e0b' : '#ef4444';
    const label = score >= 80 ? 'Excellent' : score >= 60 ? 'Good' : score >= 40 ? 'Fair' : 'Poor';
    return `
        <div class="eco-score-wrap">
            <span class="eco-score-label">Eco-Score</span>
            <div class="eco-score-bar-bg">
                <div class="eco-score-bar-fill" style="width:${score}%;background:${color}"></div>
            </div>
            <span class="eco-score-value" style="color:${color}">${score} <small>${label}</small></span>
        </div>`;
}

async function loadGreenAlternatives(vehicleNo) {
    const container = document.getElementById('greenAlternatives');
    if (!container) return;
    await loadGreenAlternativesInto(vehicleNo, container);
}

async function loadGreenAlternativesInto(vehicleNo, container) {
    if (!container) return;
    try {
        const res = await fetch(`${API_BASE_URL}/vehicles/greener-alternatives?vehicle_no=${encodeURIComponent(vehicleNo)}`);
        const data = await res.json();
        if (!data.alternatives || !data.alternatives.length) {
            container.style.display = 'none';
            return;
        }
        const rows = data.alternatives.map(a => {
            const cfg = GRADE_CONFIG[a.emission_grade] || GRADE_CONFIG['D'];
            return `
                <div class="alt-vehicle-card">
                    <span class="grade-badge-sm" style="background:${cfg.color}">${a.emission_grade}</span>
                    <span class="alt-vehicle-name">${a.vehicle_no}</span>
                    <span class="alt-vehicle-co2">${a.co2_per_km.toFixed(0)} g/km</span>
                    <span class="alt-vehicle-savings">↓ ${a.savings_percent}% less CO₂</span>
                </div>`;
        }).join('');
        container.innerHTML = `
            <h3>🌿 Greener Alternatives for Your Vehicle Class</h3>
            <p class="alt-subtitle">These vehicles emit less CO₂ than <strong>${vehicleNo}</strong> on the same route:</p>
            <div class="alt-vehicles-list">${rows}</div>`;
        container.style.display = 'block';
    } catch (_) {
        container.style.display = 'none';
    }
}

// -----------------------------
// AUTOCOMPLETE
// -----------------------------
function initAutocomplete() {
    setupAutocompleteInput('vehicle_no', 'vehicleSuggestions');
    setupAutocompleteInput('vehicle_no_2', 'vehicleSuggestions2');
}

function setupAutocompleteInput(inputId, dropdownId) {
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(dropdownId);
    if (!input || !dropdown) return;
    let debounceTimer = null;

    input.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        const q = input.value.trim();
        if (q.length < 2) { closeDropdown(dropdown); return; }
        debounceTimer = setTimeout(() => fetchSuggestions(q, dropdown, input), 300);
    });

    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) closeDropdown(dropdown);
    });

    input.addEventListener('keydown', (e) => {
        const items = dropdown.querySelectorAll('li');
        const active = dropdown.querySelector('li.active');
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (!active) { items[0]?.classList.add('active'); }
            else { const next = active.nextElementSibling; active.classList.remove('active'); (next || items[0]).classList.add('active'); }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (active) { const prev = active.previousElementSibling; active.classList.remove('active'); (prev || items[items.length - 1]).classList.add('active'); }
        } else if (e.key === 'Enter' && active) {
            e.preventDefault(); input.value = active.textContent; closeDropdown(dropdown);
        } else if (e.key === 'Escape') {
            closeDropdown(dropdown);
        }
    });
}

async function fetchSuggestions(q, dropdown, input) {
    try {
        const res = await fetch(`${API_BASE_URL}/vehicles/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        renderDropdown(data.results || [], dropdown, input);
    } catch (_) {
        closeDropdown(dropdown);
    }
}

function renderDropdown(results, dropdown, input) {
    if (!results.length) { closeDropdown(dropdown); return; }
    dropdown.innerHTML = results.map(v => `<li>${v}</li>`).join('');
    dropdown.style.display = 'block';
    dropdown.querySelectorAll('li').forEach(li => {
        li.addEventListener('mousedown', (e) => {
            e.preventDefault();
            input.value = li.textContent;
            closeDropdown(dropdown);
        });
    });
}

function closeDropdown(dropdown) {
    dropdown.style.display = 'none';
    dropdown.innerHTML = '';
}

// -----------------------------
// POPULAR VEHICLES CHIPS
// -----------------------------
async function loadPopularVehicles() {
    try {
        const res = await fetch(`${API_BASE_URL}/vehicles/popular`);
        const data = await res.json();
        renderChips(data.vehicles || []);
    } catch (_) { /* silently fail */ }
}

function renderChips(vehicles) {
    const container = document.getElementById('popularVehicles');
    if (!container || !vehicles.length) return;
    container.innerHTML = vehicles.map(v =>
        `<button type="button" class="vehicle-chip">${v}</button>`
    ).join('');
    container.querySelectorAll('.vehicle-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            document.getElementById('vehicle_no').value = chip.textContent;
            closeDropdown(document.getElementById('vehicleSuggestions'));
        });
    });
}
