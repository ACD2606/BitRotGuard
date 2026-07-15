/* ================================================================
   BitRot Guard — Visualizations Module
   ================================================================
   Canvas-based bit grid, Chart.js integrity chart, SVG gauges,
   corruption heatmap, and celebration particles.
   ================================================================ */

// ----------------------------------------------------------------
// BIT GRID — Canvas rendering of individual bits
// ----------------------------------------------------------------
const BitGrid = (() => {
    const CELL = 6;       // px per bit cell
    const GAP = 1;        // px gap between cells
    const BYTE_GAP = 2;   // extra gap between bytes
    const COLS = 64;      // bits per row (8 bytes)

    let originalBits = [];
    let unprotectedBits = [];
    let diffMask = [];    // indices of differing bits
    let windowStart = 0;

    function render(canvasId, bits, highlight = [], highlightColor = '#ff5555') {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        // Calculate dimensions
        const bytesPerRow = COLS / 8;
        const totalBits = bits.length;
        const rows = Math.ceil(totalBits / COLS);

        const cellTotal = CELL + GAP;
        const byteExtra = BYTE_GAP - GAP;
        const rowWidth = COLS * cellTotal + (bytesPerRow - 1) * byteExtra;
        const rowHeight = rows * cellTotal;

        canvas.width = rowWidth + 4;
        canvas.height = rowHeight + 4;

        // Background
        ctx.fillStyle = '#080916';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        const highlightSet = new Set(highlight);

        for (let i = 0; i < totalBits; i++) {
            const row = Math.floor(i / COLS);
            const col = i % COLS;
            const byteCol = Math.floor(col / 8);

            const x = 2 + col * cellTotal + byteCol * byteExtra;
            const y = 2 + row * cellTotal;

            if (highlightSet.has(i)) {
                ctx.fillStyle = highlightColor;
            } else if (bits[i] === 1) {
                ctx.fillStyle = '#4a5280';
            } else {
                ctx.fillStyle = '#14162e';
            }

            ctx.fillRect(x, y, CELL, CELL);
        }
    }

    function renderOriginal(bits, window_start = 0) {
        originalBits = bits;
        windowStart = window_start;
        render('bitGridOriginal', bits);
    }

    function renderUnprotected(bits, window_start = 0) {
        unprotectedBits = bits;
        windowStart = window_start;
        // Find differences with original
        diffMask = [];
        for (let i = 0; i < Math.min(originalBits.length, bits.length); i++) {
            if (originalBits[i] !== bits[i]) {
                diffMask.push(i);
            }
        }
        render('bitGridUnprotected', bits, diffMask, '#ff5555');

        const flipInfo = document.getElementById('bitGridFlips');
        if (flipInfo) {
            flipInfo.textContent = diffMask.length > 0
                ? `${diffMask.length} bit(s) differ from original in this view`
                : '';
        }
    }

    function getBitIndexFromClick(canvasId, event) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return -1;
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / rect.width;
        const scaleY = canvas.height / rect.height;
        const mx = (event.clientX - rect.left) * scaleX - 2;
        const my = (event.clientY - rect.top) * scaleY - 2;

        const bytesPerRow = COLS / 8;
        const cellTotal = CELL + GAP;
        const byteExtra = BYTE_GAP - GAP;

        const row = Math.floor(my / cellTotal);
        // Reverse the x position to bit index
        let bestCol = -1;
        for (let col = 0; col < COLS; col++) {
            const byteCol = Math.floor(col / 8);
            const x = col * cellTotal + byteCol * byteExtra;
            if (mx >= x && mx < x + CELL) {
                bestCol = col;
                break;
            }
        }

        if (bestCol < 0 || row < 0) return -1;
        const bitIndex = row * COLS + bestCol;
        if (bitIndex >= unprotectedBits.length) return -1;
        return bitIndex;
    }

    function getWindowStart() {
        return windowStart;
    }

    return { renderOriginal, renderUnprotected, getBitIndexFromClick, getWindowStart };
})();


// ----------------------------------------------------------------
// INTEGRITY CHART — Chart.js line chart
// ----------------------------------------------------------------
const IntegrityChart = (() => {
    let chart = null;

    function init() {
        const ctx = document.getElementById('integrityChart');
        if (!ctx) return;

        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['Start'],
                datasets: [
                    {
                        label: 'Protected',
                        data: [100],
                        borderColor: '#50fa7b',
                        backgroundColor: 'rgba(80, 250, 123, 0.08)',
                        borderWidth: 2.5,
                        pointRadius: 5,
                        pointBackgroundColor: '#50fa7b',
                        pointBorderColor: '#50fa7b',
                        fill: true,
                        tension: 0.3,
                    },
                    {
                        label: 'Unprotected',
                        data: [100],
                        borderColor: '#ff5555',
                        backgroundColor: 'rgba(255, 85, 85, 0.08)',
                        borderWidth: 2.5,
                        pointRadius: 5,
                        pointBackgroundColor: '#ff5555',
                        pointBorderColor: '#ff5555',
                        fill: true,
                        tension: 0.3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 800, easing: 'easeInOutQuart' },
                plugins: {
                    legend: {
                        labels: {
                            color: '#8892b0',
                            font: { family: "'Inter', sans-serif", size: 11, weight: '600' },
                            padding: 16,
                            usePointStyle: true,
                            pointStyleWidth: 8,
                        },
                    },
                    tooltip: {
                        backgroundColor: '#10122a',
                        titleColor: '#eef0ff',
                        bodyColor: '#8892b0',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        cornerRadius: 8,
                        padding: 10,
                        callbacks: {
                            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)}%`
                        }
                    },
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                        ticks: { color: '#4a5280', font: { size: 11 } },
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.04)', drawBorder: false },
                        ticks: {
                            color: '#4a5280',
                            font: { size: 11 },
                            callback: (v) => v + '%',
                        },
                        suggestedMin: 95,
                        suggestedMax: 101,
                    },
                },
            },
        });
    }

    function update(timeline) {
        if (!chart) init();
        if (!chart) return;

        const labels = timeline.map(t => t.step);
        const protectedData = timeline.map(t => t.protected);
        const unprotectedData = timeline.map(t => t.unprotected);

        chart.data.labels = labels;
        chart.data.datasets[0].data = protectedData;
        chart.data.datasets[1].data = unprotectedData;

        // Auto-scale Y axis
        const allVals = [...protectedData, ...unprotectedData];
        const minVal = Math.min(...allVals);
        const maxVal = Math.max(...allVals);
        const span = maxVal - minVal;
        const pad = Math.max(span * 0.3, 0.5);
        chart.options.scales.y.suggestedMin = Math.max(-2, minVal - pad);
        chart.options.scales.y.suggestedMax = Math.min(103, maxVal + pad);

        chart.update();
    }

    function reset() {
        if (chart) {
            chart.data.labels = ['Start'];
            chart.data.datasets[0].data = [100];
            chart.data.datasets[1].data = [100];
            chart.options.scales.y.suggestedMin = 95;
            chart.options.scales.y.suggestedMax = 101;
            chart.update();
        }
    }

    return { init, update, reset };
})();


// ----------------------------------------------------------------
// GAUGES — SVG circular progress
// ----------------------------------------------------------------
const Gauges = (() => {
    const CIRCUMFERENCE = 2 * Math.PI * 52; // r=52

    function setGauge(circleId, labelId, pct, color) {
        const circle = document.getElementById(circleId);
        const label = document.getElementById(labelId);
        if (!circle || !label) return;

        const offset = CIRCUMFERENCE * (1 - pct / 100);
        circle.style.strokeDasharray = CIRCUMFERENCE;
        circle.style.strokeDashoffset = offset;

        // Color based on percentage
        let c = color;
        if (pct >= 99.9) c = 'var(--green)';
        else if (pct >= 95) c = 'var(--orange)';
        else c = 'var(--red)';

        circle.style.stroke = c;
        label.textContent = pct.toFixed(1) + '%';
        label.style.color = c;
    }

    function update(unprotPct, healedPct) {
        setGauge('gaugeUnprot', 'gaugeUnprotVal', unprotPct, 'var(--red)');
        setGauge('gaugeHealed', 'gaugeHealedVal', healedPct, 'var(--green)');
    }

    function reset() {
        setGauge('gaugeUnprot', 'gaugeUnprotVal', 100, 'var(--green)');
        setGauge('gaugeHealed', 'gaugeHealedVal', 100, 'var(--green)');
    }

    return { update, reset };
})();


// ----------------------------------------------------------------
// HEATMAP — Corruption distribution visualization
// ----------------------------------------------------------------
const Heatmap = (() => {
    function render(segments, totalBytes) {
        const bar = document.getElementById('heatmapBar');
        const endLabel = document.getElementById('heatmapEnd');
        if (!bar) return;

        bar.innerHTML = '';
        if (!segments || segments.length === 0) {
            bar.innerHTML = '<div style="flex:1;background:var(--bg-inset);border-radius:4px;height:36px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:11px">No corruption data yet</div>';
            return;
        }

        const maxVal = Math.max(...segments, 1);

        segments.forEach((count, i) => {
            const seg = document.createElement('div');
            seg.className = 'heatmap-segment';
            const intensity = count / maxVal;

            if (count === 0) {
                seg.style.background = '#0f1029';
            } else {
                const r = Math.round(40 + 215 * intensity);
                const g = Math.round(80 * (1 - intensity));
                const b = Math.round(40 * (1 - intensity));
                seg.style.background = `rgb(${r}, ${g}, ${b})`;
            }

            seg.title = `Segment ${i}: ${count} flip(s)`;
            bar.appendChild(seg);
        });

        if (endLabel) {
            endLabel.textContent = `Byte ${totalBytes.toLocaleString()}`;
        }
    }

    function reset() {
        const bar = document.getElementById('heatmapBar');
        if (bar) {
            bar.innerHTML = '<div style="flex:1;background:var(--bg-inset);border-radius:4px;height:36px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:11px">No corruption data yet</div>';
        }
    }

    return { render, reset };
})();


// ----------------------------------------------------------------
// PARTICLES — Heal celebration effect
// ----------------------------------------------------------------
const Particles = (() => {
    let animId = null;

    function celebrate() {
        const canvas = document.getElementById('particleCanvas');
        if (!canvas) return;

        canvas.classList.remove('hidden');
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        const ctx = canvas.getContext('2d');

        const particles = [];
        const colors = ['#50fa7b', '#bd93f9', '#66d9ef', '#ffb86c', '#ff79c6'];
        const numParticles = 120;

        for (let i = 0; i < numParticles; i++) {
            particles.push({
                x: Math.random() * canvas.width,
                y: canvas.height + Math.random() * 100,
                vx: (Math.random() - 0.5) * 6,
                vy: -(Math.random() * 12 + 6),
                size: Math.random() * 6 + 2,
                color: colors[Math.floor(Math.random() * colors.length)],
                alpha: 1,
                rotation: Math.random() * 360,
                rotSpeed: (Math.random() - 0.5) * 10,
                gravity: 0.15 + Math.random() * 0.1,
                life: 1,
                decay: 0.005 + Math.random() * 0.01,
            });
        }

        function frame() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            let alive = false;

            particles.forEach(p => {
                if (p.life <= 0) return;
                alive = true;

                p.x += p.vx;
                p.vy += p.gravity;
                p.y += p.vy;
                p.rotation += p.rotSpeed;
                p.life -= p.decay;
                p.alpha = p.life;

                ctx.save();
                ctx.translate(p.x, p.y);
                ctx.rotate(p.rotation * Math.PI / 180);
                ctx.globalAlpha = p.alpha;
                ctx.fillStyle = p.color;

                // Draw different shapes
                if (p.size > 5) {
                    // Star
                    ctx.beginPath();
                    for (let s = 0; s < 5; s++) {
                        const angle = (s * 72 - 90) * Math.PI / 180;
                        const r = p.size;
                        const ri = r * 0.4;
                        ctx.lineTo(Math.cos(angle) * r, Math.sin(angle) * r);
                        const angle2 = ((s * 72 + 36) - 90) * Math.PI / 180;
                        ctx.lineTo(Math.cos(angle2) * ri, Math.sin(angle2) * ri);
                    }
                    ctx.closePath();
                    ctx.fill();
                } else {
                    // Circle
                    ctx.beginPath();
                    ctx.arc(0, 0, p.size, 0, Math.PI * 2);
                    ctx.fill();
                }
                ctx.restore();
            });

            if (alive) {
                animId = requestAnimationFrame(frame);
            } else {
                canvas.classList.add('hidden');
            }
        }

        if (animId) cancelAnimationFrame(animId);
        frame();

        // Auto-cleanup after 3 seconds
        setTimeout(() => {
            if (animId) cancelAnimationFrame(animId);
            canvas.classList.add('hidden');
        }, 3500);
    }

    return { celebrate };
})();
