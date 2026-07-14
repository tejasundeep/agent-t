document.addEventListener('DOMContentLoaded', () => {
    const socket = io();

    // DOM Elements - Theme & Connection
    const body = document.body;
    const themeToggle = document.getElementById('theme-toggle');
    const themeIcon = document.getElementById('theme-icon');
    const btnReset = document.getElementById('btn-reset');
    const connectionStatus = document.querySelector('.connection-status');

    // DOM Elements - Chat Feed (Center Panel)
    const chatFeed = document.getElementById('chat-feed');
    const chatFeedContainer = document.getElementById('chat-feed-container');
    const promptForm = document.getElementById('prompt-form');
    const promptInput = document.getElementById('prompt-input');
    const btnSubmit = document.getElementById('btn-submit');
    const statusSpinner = document.getElementById('status-spinner');
    
    // DOM Elements - Scheduler (Modal-based Dashboard)
    const btnOpenScheduler = document.getElementById('btn-open-scheduler');
    const schedulerContainer = document.getElementById('scheduler-routines-container');
    const btnAddRoutineModal = document.getElementById('btn-add-routine-modal');
    const createRoutineForm = document.getElementById('create-routine-form');
    const routineErrorAlert = document.getElementById('routine-error-alert');
    
    // DOM Elements - Scheduler Logs Modal
    const routineLogsModalName = document.getElementById('log-modal-routine-name');
    const routineLogsOutputContainer = document.getElementById('routine-logs-output-container');

    // Modals Initialization
    const routinesDashboardModal = new bootstrap.Modal(document.getElementById('routinesDashboardModal'));
    const addRoutineModal = new bootstrap.Modal(document.getElementById('addRoutineModal'));
    const routineLogsModal = new bootstrap.Modal(document.getElementById('routineLogsModal'));

    // State Variables
    let currentResponseBlock = null;
    let currentResponseText = '';

    // Initialize Tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[title]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // ---------------------------------------------
    // Theme Management
    // ---------------------------------------------
    function setTheme(theme) {
        if (theme === 'light') {
            body.classList.remove('theme-dark');
            body.classList.add('theme-light');
            themeIcon.className = 'bi bi-moon-fill text-dark fs-8';
            localStorage.setItem('theme', 'light');
        } else {
            body.classList.remove('theme-light');
            body.classList.add('theme-dark');
            themeIcon.className = 'bi bi-sun-fill text-warning fs-8';
            localStorage.setItem('theme', 'dark');
        }
    }

    const savedTheme = localStorage.getItem('theme') || 'dark';
    setTheme(savedTheme);

    themeToggle.addEventListener('click', () => {
        if (body.classList.contains('theme-dark')) {
            setTheme('light');
        } else {
            setTheme('dark');
        }
    });

    // ---------------------------------------------
    // Socket.IO Status Events
    // ---------------------------------------------
    socket.on('connect', () => {
        connectionStatus.innerHTML = '<span class="status-dot online animate-pulse" title="Socket.IO Live Connected"></span>';
    });

    socket.on('disconnect', () => {
        connectionStatus.innerHTML = '<span class="status-dot offline" title="Disconnected"></span>';
    });

    // Reset workspace trigger
    btnReset.addEventListener('click', () => {
        if (confirm('Are you sure you want to reset the workspace? This will restore orchestrator.py to defaults.')) {
            fetch('/api/reset', { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    chatFeed.innerHTML = `
                        <div class="trajectory-log text-secondary fs-8 mb-4">
                            [System Reset]: Workspace initialized cleanly. Ready for next prompt.
                        </div>
                    `;
                });
        }
    });

    // ---------------------------------------------
    // Routines Scheduler (Modal-based)
    // ---------------------------------------------
    btnOpenScheduler.addEventListener('click', () => {
        routinesDashboardModal.show();
        loadSchedulerDashboard();
    });

    function loadSchedulerDashboard() {
        fetch('/api/routines')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    renderRoutinesDashboard(data.routines);
                } else {
                    schedulerContainer.innerHTML = `<div class="text-danger fs-8 p-3">Error fetching routines database: ${data.message}</div>`;
                }
            })
            .catch(() => {
                schedulerContainer.innerHTML = `<div class="text-danger fs-8 p-3">Failed to load routines database.</div>`;
            });
    }

    function renderRoutinesDashboard(routines) {
        if (!routines || routines.length === 0) {
            schedulerContainer.innerHTML = `
                <div class="text-center text-muted py-5 fs-8">
                    <i class="bi bi-calendar-event display-6 text-muted mb-2 d-block"></i>
                    No crons or intervals configured in scheduler.
                </div>
            `;
            return;
        }

        schedulerContainer.innerHTML = '';
        routines.forEach(r => {
            const card = document.createElement('div');
            card.className = 'routine-dashboard-card animate-fade-in';
            
            const isPaused = r.status === 'paused';
            const badgeClass = isPaused ? 'paused' : 'active';
            const statusLabel = isPaused ? 'Paused' : 'Active';

            const lastRunClean = r.last_run ? r.last_run.substring(0, 19).replace('T', ' ') : 'Never';
            const nextRunClean = r.next_run ? r.next_run.substring(0, 19).replace('T', ' ') : 'N/A';

            card.innerHTML = `
                <div class="routine-card-header justify-content-between">
                    <span class="routine-card-title">${escapeHTML(r.name)}</span>
                    <span class="routine-badge-status ${badgeClass}">${statusLabel}</span>
                </div>
                
                <div class="routine-meta-item">
                    <i class="bi bi-clock"></i> <span>Schedule: <strong class="text-white">${escapeHTML(r.schedule)}</strong></span>
                </div>
                <div class="routine-meta-item">
                    <i class="bi bi-cpu"></i> <span>Type: <span class="badge bg-secondary font-mono fs-9 text-uppercase">${escapeHTML(r.type)}</span></span>
                </div>
                <div class="routine-code-block">${escapeHTML(r.action)}</div>
                
                <div class="routine-meta-item">
                    <i class="bi bi-arrow-left-right"></i> <span>Last run: ${lastRunClean}</span>
                </div>
                <div class="routine-meta-item">
                    <i class="bi bi-arrow-right"></i> <span>Next run: ${nextRunClean}</span>
                </div>
                
                <div class="routine-card-actions">
                    <button class="btn btn-routine-action" data-action="trigger" data-name="${r.name}"><i class="bi bi-play-fill text-success"></i> Trigger</button>
                    <button class="btn btn-routine-action" data-action="toggle-pause" data-name="${r.name}" data-status="${r.status}">
                        <i class="bi ${isPaused ? 'bi-check-circle text-primary' : 'bi-pause-fill text-warning'}"></i> ${isPaused ? 'Resume' : 'Pause'}
                    </button>
                    <button class="btn btn-routine-action" data-action="view-logs" data-name="${r.name}"><i class="bi bi-list-task text-info"></i> Logs</button>
                    <button class="btn btn-routine-action danger ms-auto" data-action="delete" data-name="${r.name}"><i class="bi bi-trash"></i></button>
                </div>
            `;

            // Wire action buttons
            card.querySelectorAll('.btn-routine-action').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const action = btn.getAttribute('data-action');
                    const name = btn.getAttribute('data-name');
                    
                    if (action === 'trigger') {
                        btn.disabled = true;
                        fetch(`/api/routines/${encodeURIComponent(name)}/trigger`, { method: 'POST' })
                            .then(res => res.json())
                            .then(data => {
                                alert(data.message);
                                loadSchedulerDashboard();
                            })
                            .finally(() => btn.disabled = false);
                    } 
                    else if (action === 'toggle-pause') {
                        const status = btn.getAttribute('data-status');
                        const endpoint = status === 'paused' ? 'resume' : 'pause';
                        btn.disabled = true;
                        fetch(`/api/routines/${encodeURIComponent(name)}/${endpoint}`, { method: 'POST' })
                            .then(res => res.json())
                            .then(data => {
                                loadSchedulerDashboard();
                            })
                            .finally(() => btn.disabled = false);
                    }
                    else if (action === 'view-logs') {
                        openRoutineLogsModal(name);
                    }
                    else if (action === 'delete') {
                        if (confirm(`Delete routine '${name}' and all its execution logs?`)) {
                            fetch(`/api/routines/${encodeURIComponent(name)}`, { method: 'DELETE' })
                                .then(res => res.json())
                                .then(data => {
                                    loadSchedulerDashboard();
                                });
                        }
                    }
                });
            });

            schedulerContainer.appendChild(card);
        });
    }

    // Modal Trigger for Add Routine
    btnAddRoutineModal.addEventListener('click', () => {
        createRoutineForm.reset();
        routineErrorAlert.classList.add('d-none');
        addRoutineModal.show();
    });

    // Create Routine Form Submit
    createRoutineForm.addEventListener('submit', (e) => {
        e.preventDefault();
        routineErrorAlert.classList.add('d-none');
        
        const payload = {
            name: document.getElementById('routine-name').value.trim(),
            schedule: document.getElementById('routine-schedule').value.trim(),
            type: document.getElementById('routine-type').value,
            action: document.getElementById('routine-action').value.trim(),
            timeout: parseInt(document.getElementById('routine-timeout').value)
        };

        fetch('/api/routines', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                addRoutineModal.hide();
                loadSchedulerDashboard();
            } else {
                routineErrorAlert.textContent = data.message;
                routineErrorAlert.classList.remove('d-none');
            }
        })
        .catch(err => {
            routineErrorAlert.textContent = 'Failed to submit routine request.';
            routineErrorAlert.classList.remove('d-none');
        });
    });

    // Routine Logs Viewer
    function openRoutineLogsModal(name) {
        routineLogsModalName.textContent = name;
        routineLogsOutputContainer.innerHTML = `<div class="text-center text-muted py-4"><div class="spinner-border spinner-border-sm text-secondary me-2" role="status"></div>Loading logs...</div>`;
        routineLogsModal.show();

        fetch(`/api/routines/${encodeURIComponent(name)}/logs?limit=30`)
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    renderRoutineLogsList(data.logs);
                } else {
                    routineLogsOutputContainer.innerHTML = `<div class="text-danger p-3">Error: ${data.message}</div>`;
                }
            })
            .catch(() => {
                routineLogsOutputContainer.innerHTML = `<div class="text-danger p-3">Failed to retrieve logs.</div>`;
            });
    }

    function renderRoutineLogsList(logs) {
        if (!logs || logs.length === 0) {
            routineLogsOutputContainer.innerHTML = `<div class="text-muted p-4 text-center fs-8">No historical execution logs found for this routine.</div>`;
            return;
        }

        routineLogsOutputContainer.innerHTML = '';
        logs.forEach(log => {
            const item = document.createElement('div');
            item.className = 'routine-log-row-item';

            const trigClean = log.triggered_at.substring(0, 19).replace('T', ' ');
            const finClean = log.finished_at ? log.finished_at.substring(0, 19).replace('T', ' ') : 'N/A';
            
            let statusBadgeClass = 'running';
            if (log.status === 'success') statusBadgeClass = 'success';
            else if (log.status === 'failure') statusBadgeClass = 'failure';
            else if (log.status === 'timeout') statusBadgeClass = 'timeout';

            item.innerHTML = `
                <div class="d-flex align-items-center justify-content-between mb-2 fs-8">
                    <span class="text-secondary">Triggered: <strong class="text-white">${trigClean}</strong> &bull; Finished: ${finClean}</span>
                    <span class="routine-log-badge-status ${statusBadgeClass}">${log.status}</span>
                </div>
                
                ${log.output ? `
                    <div class="fs-9 text-secondary fw-semibold mb-1">Standard Output:</div>
                    <pre class="bg-black border p-2 rounded text-secondary fs-9 font-mono mb-2" style="white-space: pre-wrap; max-height: 120px; overflow-y: auto;">${escapeHTML(log.output)}</pre>
                ` : ''}

                ${log.error ? `
                    <div class="fs-9 text-danger fw-semibold mb-1">Standard Error / Failures:</div>
                    <pre class="bg-black border border-danger p-2 rounded text-danger fs-9 font-mono" style="white-space: pre-wrap; max-height: 120px; overflow-y: auto;">${escapeHTML(log.error)}</pre>
                ` : ''}
            `;
            routineLogsOutputContainer.appendChild(item);
        });
    }

    // ---------------------------------------------
    // Chat Submission & Feed (Center Panel)
    // ---------------------------------------------
    promptForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const prompt = promptInput.value.trim();
        if (!prompt) return;

        // Render user prompt in the feed
        const userHtml = `
            <div class="user-msg-row my-3 animate-fade-in">
                <div class="user-msg-box shadow-sm">
                    ${escapeHTML(prompt)}
                </div>
            </div>
        `;
        chatFeed.insertAdjacentHTML('beforeend', userHtml);
        promptInput.value = '';

        // Disable inputs during processing
        btnSubmit.disabled = true;
        promptInput.disabled = true;
        statusSpinner.classList.remove('d-none');

        // Close any lingering thought blocks
        const oldThought = document.getElementById('active-thought');
        if (oldThought) oldThought.remove();

        socket.emit('start_agent', { prompt: prompt });
    });

    // ---------------------------------------------
    // WebSockets Diagnostics Inline Trajectory Stream
    // ---------------------------------------------
    socket.on('agent_status', (data) => {
        if (data.status === 'finished') {
            btnSubmit.disabled = false;
            promptInput.disabled = false;
            statusSpinner.classList.add('d-none');
            currentResponseBlock = null;
            
            // Remove active thought indicator
            const activeThought = document.getElementById('active-thought');
            if (activeThought) activeThought.remove();

            // Refresh systems status if modal is currently open
            const routinesModalEl = document.getElementById('routinesDashboardModal');
            if (routinesModalEl.classList.contains('show')) {
                loadSchedulerDashboard();
            }
        }
    });

    socket.on('trajectory_log', (data) => {
        const logHtml = `
            <div class="trajectory-log text-secondary fs-9 my-1 font-mono animate-fade-in" style="opacity: 0.85;">
                <span class="text-muted">&gt;</span> ${escapeHTML(data.log)}
            </div>
        `;
        chatFeed.insertAdjacentHTML('beforeend', logHtml);
        chatFeedContainer.scrollTop = chatFeedContainer.scrollHeight;
    });

    socket.on('thought_start', (data) => {
        const duration = data.duration || 1;
        const oldThought = document.getElementById('active-thought');
        if (oldThought) oldThought.remove();

        const thoughtHtml = `
            <div class="thought-log-item my-2 animate-fade-in" id="active-thought" style="font-size: 0.78rem;">
                <i class="bi bi-cpu-fill text-primary animate-pulse me-1"></i>
                <span class="text-secondary">Thinking (${duration}s)...</span>
            </div>
        `;
        chatFeed.insertAdjacentHTML('beforeend', thoughtHtml);
        chatFeedContainer.scrollTop = chatFeedContainer.scrollHeight;
    });

    socket.on('step_start', (data) => {
        const action = data.action;
        const stepId = data.id;

        // Remove active thought indicator when a tool starts
        const activeThought = document.getElementById('active-thought');
        if (activeThought) activeThought.remove();

        // Render clean, inline tool running card
        const cardHtml = `
            <div class="running-tool-card my-2 p-2 rounded border bg-card-blur d-flex align-items-center gap-2 animate-fade-in" id="step-card-${stepId}" style="font-family: 'Fira Code', monospace; font-size: 0.78rem;">
                <i class="bi bi-gear-fill text-primary animate-spin" id="step-icon-${stepId}"></i>
                <span id="step-text-${stepId}">Running tool: <strong class="text-white">${escapeHTML(action)}</strong> (${escapeHTML(data.name)})</span>
            </div>
        `;
        chatFeed.insertAdjacentHTML('beforeend', cardHtml);
        chatFeedContainer.scrollTop = chatFeedContainer.scrollHeight;
    });

    socket.on('step_log', (data) => {
        // Only show running tool inline, omit standard output logs
    });

    socket.on('step_complete', (data) => {
        const stepId = data.id;
        const cardText = document.getElementById(`step-text-${stepId}`);
        const cardIcon = document.getElementById(`step-icon-${stepId}`);
        
        if (cardText && cardIcon) {
            if (data.status === 'success') {
                cardIcon.className = 'bi bi-check-circle-fill text-success';
                cardIcon.classList.remove('animate-spin');
                cardText.innerHTML = `Ran tool: <strong class="text-white">${cardText.querySelector('strong').textContent}</strong> (Success)`;
            } else {
                cardIcon.className = 'bi bi-x-circle-fill text-danger';
                cardIcon.classList.remove('animate-spin');
                cardText.innerHTML = `Ran tool: <strong class="text-white">${cardText.querySelector('strong').textContent}</strong> (Error)`;
            }
        }
    });

    // ---------------------------------------------
    // Chat Stream Assistant Blocks
    // ---------------------------------------------
    socket.on('thought_chunk', (data) => {
        const activeThought = document.getElementById('active-thought');
        if (activeThought) activeThought.remove();

        if (!currentResponseBlock) {
            const blockId = `response-${Date.now()}`;
            const blockHtml = `
                <div class="assistant-response-row my-3 animate-fade-in">
                    <div class="assistant-response-text" id="${blockId}"></div>
                </div>
            `;
            chatFeed.insertAdjacentHTML('beforeend', blockHtml);
            currentResponseBlock = document.getElementById(blockId);
            currentResponseText = '';
        }
        currentResponseText += data.text;
        
        if (window.marked) {
            currentResponseBlock.innerHTML = marked.parse(currentResponseText);
        } else {
            currentResponseBlock.textContent = currentResponseText;
        }
        
        // Auto scroll
        chatFeedContainer.scrollTop = chatFeedContainer.scrollHeight;
    });

    function escapeHTML(str) {
        if (!str) return '';
        return str.replace(/[&<>'"]/g, 
            tag => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#39;',
                '"': '&quot;'
            }[tag] || tag)
        );
    }
});
