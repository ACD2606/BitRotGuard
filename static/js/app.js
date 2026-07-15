/* ================================================================
   BitRot Guard — Main Application Logic
   ================================================================
   State management, API calls, UI orchestration, event handlers,
   toast notifications, and workflow sequencing.
   ================================================================ */

(() => {
    'use strict';

    // ----------------------------------------------------------------
    // STATE
    // ----------------------------------------------------------------
    const state = {
        chosen: false,
        protected: false,
        corrupted: false,
        healed: false,
        healedOk: null,
        fileKind: null,
        fileName: null,
        fileSize: 0,
        encodedSize: 0,
        totalFlips: 0,
        errorsCorrected: 0,
        originalHash: null,
        integrityTimeline: [],
    };

    // ----------------------------------------------------------------
    // DOM REFS
    // ----------------------------------------------------------------
    const $ = (id) => document.getElementById(id);

    const els = {
        uploadZone: $('uploadZone'),
        fileInput: $('fileInput'),
        browseLink: $('browseLink'),
        fileInfoBar: $('fileInfoBar'),
        fileIcon: $('fileIcon'),
        fileName: $('fileName'),
        fileMeta: $('fileMeta'),
        btnChangeFile: $('btnChangeFile'),

        btnProtect: $('btnProtect'),
        btnCorrupt: $('btnCorrupt'),
        btnHeal: $('btnHeal'),
        btnReset: $('btnReset'),
        btnExport: $('btnExport'),

        flipSlider: $('flipSlider'),
        flipCount: $('flipCount'),

        chipChosen: $('chipChosen'),
        chipProtected: $('chipProtected'),
        chipCorrupted: $('chipCorrupted'),
        chipHealed: $('chipHealed'),

        actionSection: $('actionSection'),
        statsSection: $('statsSection'),
        panelsSection: $('panelsSection'),
        bitGridSection: $('bitGridSection'),
        dashboardSection: $('dashboardSection'),
        eccSection: $('eccSection'),

        logContainer: $('logContainer'),

        // ECC comparison
        btnCompareEcc: $('btnCompareEcc'),
        eccResults: $('eccResults'),
        eccStatus: $('eccStatus'),
    };

    // ----------------------------------------------------------------
    // TOAST NOTIFICATIONS
    // ----------------------------------------------------------------
    function toast(message, type = 'info', duration = 4000) {
        const container = $('toastContainer');
        const icons = { info: 'ℹ️', success: '✅', warning: '⚠️', error: '❌' };
        const div = document.createElement('div');
        div.className = `toast ${type}`;
        div.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ️'}</span><span>${message}</span>`;
        container.appendChild(div);

        setTimeout(() => {
            div.classList.add('toast-exit');
            setTimeout(() => div.remove(), 300);
        }, duration);
    }

    // ----------------------------------------------------------------
    // LOGGING
    // ----------------------------------------------------------------
    function log(message, type = 'info') {
        const container = els.logContainer;
        const time = new Date().toLocaleTimeString('en-US', { hour12: false });
        const entry = document.createElement('div');
        entry.className = 'log-entry';
        entry.innerHTML = `<span class="log-time">${time}</span><span class="log-msg ${type}">${message}</span>`;
        container.appendChild(entry);
        container.scrollTop = container.scrollHeight;
    }

    function logBitFlip(flip, tag = 'bad') {
        const container = els.logContainer;
        const oldBits = flip.old_byte;
        const newBits = flip.new_byte;

        // Find the differing bit
        let diffPos = -1;
        for (let i = 0; i < 8; i++) {
            if (oldBits[i] !== newBits[i]) { diffPos = i; break; }
        }

        const entry = document.createElement('div');
        entry.className = 'log-entry';

        let bitHtml = `<span class="log-time"></span><span class="log-msg muted">    byte ${flip.byte_index}: ${oldBits} → `;
        if (diffPos >= 0) {
            bitHtml += newBits.substring(0, diffPos);
            bitHtml += `<span class="log-bit-flip-${tag === 'bad' ? 'bad' : 'good'}">${newBits[diffPos]}</span>`;
            bitHtml += newBits.substring(diffPos + 1);
        } else {
            bitHtml += newBits;
        }
        bitHtml += '</span>';
        entry.innerHTML = bitHtml;
        container.appendChild(entry);
        container.scrollTop = container.scrollHeight;
    }

    // ----------------------------------------------------------------
    // STEPPER
    // ----------------------------------------------------------------
    function updateStepper() {
        const steps = [
            { el: $('step1'), conn: $('conn1'), done: state.chosen },
            { el: $('step2'), conn: $('conn2'), done: state.protected },
            { el: $('step3'), conn: $('conn3'), done: state.corrupted },
            { el: $('step4'), conn: null, done: state.healed },
        ];

        let reachedCurrent = false;
        steps.forEach((s, i) => {
            s.el.classList.remove('active', 'completed');
            if (s.conn) s.conn.classList.remove('active');

            if (s.done) {
                s.el.classList.add('completed');
                s.el.querySelector('.step-number').textContent = '✓';
                if (s.conn) s.conn.classList.add('active');
            } else if (!reachedCurrent) {
                s.el.classList.add('active');
                s.el.querySelector('.step-number').textContent = i + 1;
                reachedCurrent = true;
            } else {
                s.el.querySelector('.step-number').textContent = i + 1;
            }
        });
    }

    // ----------------------------------------------------------------
    // STATUS CHIPS
    // ----------------------------------------------------------------
    function updateChips() {
        const toggle = (el, active, text) => {
            el.classList.toggle('active', active);
            el.textContent = (active ? '✓ ' : '○ ') + text;
        };
        toggle(els.chipChosen, state.chosen, 'File chosen');
        toggle(els.chipProtected, state.protected, 'Protected');
        toggle(els.chipCorrupted, state.corrupted, 'Bit-rot simulated');

        if (state.healed) {
            const ok = state.healedOk;
            els.chipHealed.className = `chip active ${ok ? 'chip-green' : 'chip-red'}`;
            els.chipHealed.textContent = ok ? '✓ Healed — perfect' : '⚠ Healed — mismatch';
        } else {
            els.chipHealed.className = 'chip chip-green';
            els.chipHealed.textContent = '○ Healed';
        }
    }

    // ----------------------------------------------------------------
    // STATS
    // ----------------------------------------------------------------
    function updateStats() {
        $('statOrigSize').textContent = formatBytes(state.fileSize);
        $('statOrigSub').textContent = state.fileKind || '';

        if (state.encodedSize) {
            $('statEncSize').textContent = formatBytes(state.encodedSize);
            const overhead = ((state.encodedSize / state.fileSize - 1) * 100).toFixed(1);
            $('statEncSub').textContent = `+${overhead}% overhead`;
        } else {
            $('statEncSize').textContent = '—';
            $('statEncSub').textContent = '';
        }

        $('statFlips').textContent = state.totalFlips;
        $('statFlipsSub').textContent = state.totalFlips > 0 ? 'bits flipped' : '';

        if (state.errorsCorrected > 0 || state.healed) {
            $('statCorrected').textContent = state.errorsCorrected;
            $('statCorrectedSub').textContent = 'by Hamming(7,4)';
        } else {
            $('statCorrected').textContent = '—';
            $('statCorrectedSub').textContent = '';
        }

        if (state.healed) {
            const hashEl = $('statHash');
            hashEl.textContent = state.healedOk ? 'PASS ✓' : 'FAIL ✕';
            hashEl.className = `stat-value ${state.healedOk ? 'green' : 'red'}`;
            $('statHashSub').textContent = state.healedOk
                ? 'Byte-for-byte identical'
                : 'Some blocks had 2+ errors';
        } else {
            $('statHash').textContent = '—';
            $('statHash').className = 'stat-value';
            $('statHashSub').textContent = '';
        }
    }

    // ----------------------------------------------------------------
    // BUTTON STATES
    // ----------------------------------------------------------------
    function updateButtons() {
        els.btnProtect.disabled = !state.chosen || state.protected;
        els.btnCorrupt.disabled = !state.chosen || state.healed;
        els.btnHeal.disabled = !state.protected || !state.corrupted;
        els.btnExport.disabled = !state.chosen;
        els.btnCompareEcc.disabled = !state.chosen;
    }

    // ----------------------------------------------------------------
    // SECTION VISIBILITY
    // ----------------------------------------------------------------
    function showSections() {
        els.actionSection.classList.toggle('hidden', !state.chosen);
        els.statsSection.classList.toggle('hidden', !state.chosen);
        els.panelsSection.classList.toggle('hidden', !state.chosen);
        els.eccSection.classList.toggle('hidden', !state.chosen);

        // Show bit grid and dashboard immediately after upload to allow early corruption
        els.bitGridSection.classList.toggle('hidden', !state.chosen);
        els.dashboardSection.classList.toggle('hidden', !state.chosen);
    }

    // ----------------------------------------------------------------
    // FULL UI UPDATE
    // ----------------------------------------------------------------
    function updateUI() {
        updateStepper();
        updateChips();
        updateStats();
        updateButtons();
        showSections();
    }

    // ----------------------------------------------------------------
    // FILE UPLOAD
    // ----------------------------------------------------------------
    async function uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            log(`Uploading: ${file.name} (${formatBytes(file.size)})`, 'info');

            const res = await fetch('/api/upload', { method: 'POST', body: formData });
            const data = await res.json();

            if (data.error) {
                toast(data.error, 'error');
                log('Upload failed: ' + data.error, 'error');
                return;
            }

            state.chosen = true;
            state.fileName = data.filename;
            state.fileSize = data.size;
            state.fileKind = data.kind;
            state.originalHash = data.hash;
            state.integrityTimeline = [{ step: 'Start', protected: 100, unprotected: 100 }];

            // Update UI
            els.fileInfoBar.classList.remove('hidden');
            els.uploadZone.style.display = 'none';
            els.fileName.textContent = data.filename;
            els.fileMeta.textContent = `${formatBytes(data.size)} • ${data.kind} • SHA-256: ${data.hash.substring(0, 16)}…`;

            const kindIcons = { text: '📝', image: '🖼️', binary: '💾' };
            els.fileIcon.textContent = kindIcons[data.kind] || '📄';

            updateUI();
            renderPreview('original');
            renderPreview('unprotected'); // Allow previewing immediately before protection
            
            toast(`File loaded: ${data.filename}`, 'success');
            log(`Selected: ${data.filename} (${data.kind}, ${formatBytes(data.size)})`, 'success');

        } catch (e) {
            toast('Upload failed: ' + e.message, 'error');
            log('Upload error: ' + e.message, 'error');
        }
    }

    // ----------------------------------------------------------------
    // PROTECT
    // ----------------------------------------------------------------
    async function doProtect() {
        els.btnProtect.disabled = true;
        log('Protecting file with Hamming(7,4) encoding...', 'info');

        try {
            const res = await fetch('/api/protect', { method: 'POST' });
            const data = await res.json();

            if (data.error) {
                toast(data.error, 'error');
                log('Protection failed: ' + data.error, 'error');
                els.btnProtect.disabled = false;
                return;
            }

            state.protected = true;
            state.encodedSize = data.encoded_size;
            
            const lastUnprot = state.integrityTimeline.length > 0 ? 
                state.integrityTimeline[state.integrityTimeline.length - 1].unprotected : 100;
                
            state.integrityTimeline.push({
                step: 'Protected', 
                protected: 100, 
                unprotected: lastUnprot 
            });

            updateUI();
            renderPreview('unprotected');
            loadBitGrids();
            IntegrityChart.update(state.integrityTimeline);
            Gauges.update(100, 100);

            toast(`Protected! ${formatBytes(data.original_size)} → ${formatBytes(data.encoded_size)} (+${data.overhead_pct}%)`, 'success');
            log(`Protected: ${formatBytes(data.original_size)} → ${formatBytes(data.encoded_size)} (+${data.overhead_pct}% overhead)`, 'success');

        } catch (e) {
            toast('Protection failed: ' + e.message, 'error');
            log('Protection error: ' + e.message, 'error');
            els.btnProtect.disabled = false;
        }
    }

    // ----------------------------------------------------------------
    // CORRUPT
    // ----------------------------------------------------------------
    async function doCorrupt() {
        const numFlips = parseInt(els.flipSlider.value);
        els.btnCorrupt.disabled = true;

        log(`💥 Simulating bit rot (${numFlips} random bit flips)...`, 'warning');

        try {
            const res = await fetch('/api/corrupt', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ num_flips: numFlips }),
            });
            const data = await res.json();

            if (data.error) {
                toast(data.error, 'error');
                els.btnCorrupt.disabled = false;
                return;
            }

            state.corrupted = true;
            state.totalFlips = data.total_flips;

            // Update integrity timeline
            state.integrityTimeline.push({
                step: `Corrupt #${data.corruption_round}`,
                protected: 100,
                unprotected: data.unprotected_integrity,
            });

            updateUI();
            renderPreview('unprotected');
            loadBitGrids();
            IntegrityChart.update(state.integrityTimeline);
            Gauges.update(data.unprotected_integrity, 100);
            loadHeatmap();

            // Log flip details
            log(`💥 ${data.num_flips} bits flipped! (total: ${data.total_flips}). Unprotected integrity: ${data.unprotected_integrity.toFixed(2)}%`, 'warning');
            data.flip_details.slice(0, 10).forEach(flip => logBitFlip(flip, 'bad'));
            if (data.flip_details.length > 10) {
                log(`    ... and ${data.flip_details.length - 10} more`, 'muted');
            }

            toast(`${data.num_flips} bits corrupted! Total: ${data.total_flips}`, 'warning');

            els.btnCorrupt.disabled = false;

        } catch (e) {
            toast('Corruption failed: ' + e.message, 'error');
            els.btnCorrupt.disabled = false;
        }
    }

    // ----------------------------------------------------------------
    // HEAL
    // ----------------------------------------------------------------
    async function doHeal() {
        els.btnHeal.disabled = true;
        log('✨ Healing protected copy with Hamming(7,4) decoding...', 'info');

        try {
            const res = await fetch('/api/heal', { method: 'POST' });
            const data = await res.json();

            if (data.error) {
                toast(data.error, 'error');
                els.btnHeal.disabled = false;
                return;
            }

            state.healed = true;
            state.healedOk = data.hash_ok;
            state.errorsCorrected = data.errors_corrected;

            state.integrityTimeline.push({
                step: 'Healed',
                protected: data.healed_integrity,
                unprotected: data.unprotected_integrity,
            });

            updateUI();
            renderPreview('healed');
            IntegrityChart.update(state.integrityTimeline);
            Gauges.update(data.unprotected_integrity, data.healed_integrity);

            // Log results
            log('🔍 Revealing corruption details:', 'info');
            log(`    Unprotected: ${data.unprot_flip_log.length} bit(s) corrupted:`, 'muted');
            data.unprot_flip_log.slice(0, 8).forEach(f => logBitFlip(f, 'bad'));

            log(`    Protected: ${data.prot_flip_log.length} bit(s) in ECC data:`, 'muted');
            data.prot_flip_log.slice(0, 8).forEach(f => logBitFlip(f, 'good'));

            if (data.hash_ok) {
                log(`✅ Healed! ${data.errors_corrected} error(s) corrected. SHA-256 matches perfectly!`, 'success');
                toast('Perfect recovery! File is byte-for-byte identical.', 'success', 5000);
                Particles.celebrate();
            } else {
                log(`⚠ Healed with ${data.errors_corrected} corrections, but SHA-256 mismatch — some blocks had 2+ errors.`, 'error');
                toast('Partial recovery — some blocks exceeded correction capability.', 'warning', 5000);
            }

        } catch (e) {
            toast('Healing failed: ' + e.message, 'error');
            els.btnHeal.disabled = false;
        }
    }

    // ----------------------------------------------------------------
    // RESET
    // ----------------------------------------------------------------
    async function doReset() {
        try {
            await fetch('/api/reset', { method: 'POST' });
        } catch (e) { /* ignore */ }

        // Reset state
        Object.assign(state, {
            chosen: false, protected: false, corrupted: false, healed: false,
            healedOk: null, fileKind: null, fileName: null, fileSize: 0,
            encodedSize: 0, totalFlips: 0, errorsCorrected: 0,
            originalHash: null, integrityTimeline: [],
        });

        // Reset UI
        els.fileInfoBar.classList.add('hidden');
        els.uploadZone.style.display = '';
        $('eccResults').classList.add('hidden');
        $('eccStatus').textContent = '';

        // Reset panels
        ['panelOriginal', 'panelUnprotected', 'panelHealed'].forEach(id => {
            const el = $(id);
            el.innerHTML = '<div class="panel-placeholder"><div class="icon">📄</div><div>—</div></div>';
        });

        $('unprotLabel').textContent = '';
        $('healedLabel').textContent = '';

        // Reset log
        els.logContainer.innerHTML = '';
        log('Session reset. Choose a file to begin.', 'info');

        // Reset visualizations
        IntegrityChart.reset();
        Gauges.reset();
        Heatmap.reset();

        updateUI();
        toast('Session reset', 'info');
    }

    // ----------------------------------------------------------------
    // FILE PREVIEW RENDERING
    // ----------------------------------------------------------------
    async function renderPreview(type) {
        const panelMap = {
            original: 'panelOriginal',
            unprotected: 'panelUnprotected',
            healed: 'panelHealed',
        };
        const panel = $(panelMap[type]);
        if (!panel) return;

        try {
            if (state.fileKind === 'text') {
                const res = await fetch(`/api/file/${type}`);
                const data = await res.json();

                if (data.error) {
                    panel.innerHTML = `<div class="panel-placeholder"><div class="icon">⚠️</div><div>${data.error}</div></div>`;
                    return;
                }

                let content = data.content || '';

                // For unprotected/healed, do diff highlighting against original
                if (type !== 'original') {
                    const origRes = await fetch('/api/file/original');
                    const origData = await origRes.json();
                    const origContent = origData.content || '';

                    const highlighted = highlightTextDiff(origContent, content, type === 'healed');
                    panel.innerHTML = `<div class="panel-text">${highlighted}</div>`;
                } else {
                    panel.innerHTML = `<div class="panel-text">${escapeHtml(content)}</div>`;
                }

            } else if (state.fileKind === 'image') {
                const timestamp = Date.now();
                panel.innerHTML = '<div class="panel-placeholder">Loading...</div>';
                
                try {
                    const res = await fetch(`/api/file-image/${type}?t=${timestamp}`);
                    if (!res.ok) throw new Error('Fetch failed');
                    const blob = await res.blob();
                    const objectUrl = URL.createObjectURL(blob);
                    
                    await new Promise((resolve, reject) => {
                        const img = new Image();
                        img.onload = () => {
                            img.className = 'panel-image';
                            img.alt = type;
                            panel.innerHTML = '';
                            panel.appendChild(img);
                            resolve();
                        };
                        img.onerror = () => {
                            reject(new Error('Decode failed'));
                        };
                        img.src = objectUrl;
                    });
                } catch (e) {
                    panel.innerHTML = '<div class="panel-image-error">❌ Image corrupted beyond display!</div>';
                }

            } else {
                const res = await fetch(`/api/file/${type}`);
                const data = await res.json();
                panel.innerHTML = `<div class="panel-text" style="font-size:11px">Binary file: ${formatBytes(data.size || 0)}\n\nHex:\n${data.hex_preview || '—'}</div>`;
            }
        } catch (e) {
            panel.innerHTML = `<div class="panel-placeholder"><div class="icon">⚠️</div><div>Preview failed</div></div>`;
        }
    }

    // ----------------------------------------------------------------
    // TEXT DIFF HIGHLIGHTING
    // ----------------------------------------------------------------
    function highlightTextDiff(original, modified, isHealed) {
        const cls = isHealed ? 'diff-fixed' : 'diff-bad';
        let result = '';
        const maxLen = Math.max(original.length, modified.length);

        let i = 0;
        while (i < modified.length) {
            if (i < original.length && original[i] === modified[i]) {
                result += escapeHtml(modified[i]);
                i++;
            } else {
                // Find the extent of the diff
                let j = i;
                while (j < modified.length && (j >= original.length || original[j] !== modified[j])) {
                    j++;
                }
                const diffText = modified.substring(i, j);
                result += `<span class="${cls}">${escapeHtml(diffText)}</span>`;
                i = j;
            }
        }
        return result;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ----------------------------------------------------------------
    // BIT GRID
    // ----------------------------------------------------------------
    async function loadBitGrids() {
        try {
            const [origRes, unprotRes] = await Promise.all([
                fetch('/api/bit-grid/original'),
                fetch('/api/bit-grid/unprotected'),
            ]);
            const origData = await origRes.json();
            const unprotData = await unprotRes.json();

            if (!origData.error) BitGrid.renderOriginal(origData.bits, origData.window_start || 0);
            if (!unprotData.error) BitGrid.renderUnprotected(unprotData.bits, unprotData.window_start || 0);

            const startByte = unprotData.window_start || 0;
            const endByte = startByte + (unprotData.num_bytes || 0);
            $('bitGridInfo').textContent =
                `Showing bytes ${startByte.toLocaleString()} to ${endByte.toLocaleString()} (${origData.bits.length.toLocaleString()} bits) of ${origData.total_file_bytes.toLocaleString()} total bytes`;
        } catch (e) {
            console.error('Bit grid load failed:', e);
        }
    }

    // Manual bit flip on canvas click
    function handleBitGridClick(event) {
        if (!state.chosen || state.healed) return;
        const bitIndex = BitGrid.getBitIndexFromClick('bitGridUnprotected', event);
        if (bitIndex < 0) return;

        const windowStartByte = BitGrid.getWindowStart();
        const byteIndex = windowStartByte + Math.floor(bitIndex / 8);
        const bitInByte = bitIndex % 8;

        fetch('/api/manual-flip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ byte_index: byteIndex, bit_index: bitInByte }),
        })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                toast(data.error, 'error');
                return;
            }
            state.corrupted = true;
            state.totalFlips = data.total_flips;
            updateUI();
            loadBitGrids();
            renderPreview('unprotected');
            log(`🖱️ Manually flipped bit at byte ${byteIndex}, bit ${bitInByte}: ${data.old_byte} → ${data.new_byte}`, 'warning');
            toast(`Bit flipped at byte ${byteIndex}`, 'warning', 2000);
        })
        .catch(e => toast('Manual flip failed', 'error'));
    }

    // ----------------------------------------------------------------
    // HEATMAP
    // ----------------------------------------------------------------
    async function loadHeatmap() {
        try {
            const res = await fetch('/api/heatmap');
            const data = await res.json();
            Heatmap.render(data.segments, data.total_bytes);
        } catch (e) {
            console.error('Heatmap load failed:', e);
        }
    }

    // ----------------------------------------------------------------
    // ECC COMPARISON
    // ----------------------------------------------------------------
    async function doCompareEcc() {
        const numFlips = parseInt(els.flipSlider.value);
        els.btnCompareEcc.disabled = true;
        els.eccStatus.textContent = 'Running comparison...';

        try {
            const res = await fetch('/api/compare-ecc', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ num_flips: numFlips }),
            });
            const data = await res.json();

            if (data.error) {
                toast(data.error, 'error');
                els.eccStatus.textContent = '';
                els.btnCompareEcc.disabled = false;
                return;
            }

            renderEccResults(data.results, data.num_flips, data.sample_size);
            els.eccStatus.textContent = `${data.num_flips} flips on ${formatBytes(data.sample_size)} sample`;
            els.btnCompareEcc.disabled = false;

        } catch (e) {
            toast('Comparison failed', 'error');
            els.eccStatus.textContent = '';
            els.btnCompareEcc.disabled = false;
        }
    }

    function renderEccResults(results, numFlips, sampleSize) {
        const container = $('eccResults');
        container.innerHTML = '';
        container.classList.remove('hidden');

        results.forEach(r => {
            const card = document.createElement('div');
            const cardClass = r.hash_ok ? 'success' : (r.errors_detected > 0 ? 'partial' : 'fail');
            card.className = `ecc-result-card ${cardClass}`;

            const badgeClass = r.hash_ok ? 'pass' : (r.errors_detected > 0 && !r.hash_ok ? 'detect' : 'fail');
            const badgeText = r.hash_ok ? '✓ Recovered' : (r.errors_detected > 0 ? '⚠ Detected Only' : '✕ Corrupted');

            card.innerHTML = `
                <div class="ecc-name">${r.name}</div>
                <span class="ecc-badge ${badgeClass}">${badgeText}</span>
                <div class="ecc-stats">
                    <div><strong>Overhead:</strong> ${r.overhead_pct}%</div>
                    <div><strong>Errors detected:</strong> ${r.errors_detected}</div>
                    <div><strong>Errors corrected:</strong> ${r.errors_corrected}</div>
                    <div><strong>SHA-256 match:</strong> ${r.hash_ok ? '✓ Yes' : '✕ No'}</div>
                </div>
            `;
            container.appendChild(card);
        });
    }

    // ----------------------------------------------------------------
    // EXPORT
    // ----------------------------------------------------------------
    function doExport() {
        window.open('/api/export-report', '_blank');
        toast('Report download started', 'info');
        log('📄 PDF report exported', 'success');
    }

    // ----------------------------------------------------------------
    // HELPERS
    // ----------------------------------------------------------------
    function formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    // ----------------------------------------------------------------
    // DRAG & DROP
    // ----------------------------------------------------------------
    function initDragDrop() {
        const zone = els.uploadZone;

        ['dragenter', 'dragover'].forEach(evt => {
            zone.addEventListener(evt, (e) => {
                e.preventDefault();
                e.stopPropagation();
                zone.classList.add('drag-over');
            });
        });

        ['dragleave', 'drop'].forEach(evt => {
            zone.addEventListener(evt, (e) => {
                e.preventDefault();
                e.stopPropagation();
                zone.classList.remove('drag-over');
            });
        });

        zone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                uploadFile(files[0]);
            }
        });

        zone.addEventListener('click', () => els.fileInput.click());
        els.browseLink.addEventListener('click', (e) => {
            e.stopPropagation();
            els.fileInput.click();
        });

        els.fileInput.addEventListener('change', () => {
            if (els.fileInput.files.length > 0) {
                uploadFile(els.fileInput.files[0]);
            }
        });
    }

    // ----------------------------------------------------------------
    // EVENT BINDING
    // ----------------------------------------------------------------
    function bindEvents() {
        els.btnProtect.addEventListener('click', doProtect);
        els.btnCorrupt.addEventListener('click', doCorrupt);
        els.btnHeal.addEventListener('click', doHeal);
        els.btnReset.addEventListener('click', doReset);
        els.btnExport.addEventListener('click', doExport);
        els.btnCompareEcc.addEventListener('click', doCompareEcc);

        els.btnChangeFile.addEventListener('click', () => {
            doReset().then(() => {
                els.fileInput.click();
            });
        });

        // Corruption slider
        els.flipSlider.addEventListener('input', () => {
            els.flipCount.textContent = els.flipSlider.value;
        });

        // Bit grid click
        $('bitGridUnprotected').addEventListener('click', handleBitGridClick);
    }

    // ----------------------------------------------------------------
    // INIT
    // ----------------------------------------------------------------
    function init() {
        initDragDrop();
        bindEvents();
        IntegrityChart.init();
        Gauges.reset();
        Heatmap.reset();
        updateUI();
        log('Welcome to BitRot Guard. Drag a file or click to begin.', 'info');
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
