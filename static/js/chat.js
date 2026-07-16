/* ============================================================
   AGENT-K — Neural Console JavaScript
   Full UI Logic for the Neural Dark redesign
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {

  /* ──────────────────────────────────────────
     SOCKET.IO
  ────────────────────────────────────────── */
  const socket = io();

  /* ──────────────────────────────────────────
     DOM REFS
  ────────────────────────────────────────── */
  const body                    = document.body;
  const themeToggle             = document.getElementById('theme-toggle');
  const themeIcon               = document.getElementById('theme-icon');
  const btnReset                = document.getElementById('btn-reset');

  // Chat
  const chatFeed                = document.getElementById('chat-feed');
  const chatViewport            = document.getElementById('chat-viewport');
  const promptForm              = document.getElementById('prompt-form');
  const promptInput             = document.getElementById('prompt-input');
  const btnSubmit               = document.getElementById('btn-submit');
  const btnSendIcon             = document.getElementById('btn-send-icon');
  const commandSpinner          = document.getElementById('command-spinner');

  // Status
  const statusOrb               = document.getElementById('status-orb');
  const topbarOrb               = document.getElementById('topbar-orb');
  const topbarStatusText        = document.getElementById('topbar-status-text');
  const connectionIndicator     = document.getElementById('connection-indicator');

  // Mobile topbar buttons (mirrors of sidebar)
  const mobBtnScheduler         = document.getElementById('mob-btn-scheduler');
  const mobBtnReset             = document.getElementById('mob-btn-reset');
  const mobThemeToggle          = document.getElementById('mob-theme-toggle');
  const mobThemeIcon            = document.getElementById('mob-theme-icon');
  const mobStatusOrb            = document.getElementById('mob-status-orb');

  // Scheduler panel (slide-over)
  const btnOpenScheduler        = document.getElementById('btn-open-scheduler');
  const schedulerOverlay        = document.getElementById('scheduler-overlay');
  const schedulerPanel          = document.getElementById('scheduler-panel');
  const btnCloseScheduler       = document.getElementById('btn-close-scheduler');
  const schedulerPanelBody      = document.getElementById('scheduler-panel-body');
  const btnAddRoutineTrigger    = document.getElementById('btn-add-routine-trigger');

  // Create-routine modal
  const createRoutineForm       = document.getElementById('create-routine-form');
  const routineErrorAlert       = document.getElementById('routine-error-alert');

  // Edit-routine modal
  const editRoutineForm         = document.getElementById('edit-routine-form');
  const editRoutineError        = document.getElementById('edit-routine-error');
  const editRoutineNameHidden   = document.getElementById('edit-routine-name');
  const editRoutineNameLabel    = document.getElementById('edit-routine-name-label');

  // Logs modal
  const logModalRoutineName     = document.getElementById('log-modal-routine-name');
  const routineLogsContainer    = document.getElementById('routine-logs-output-container');

  // Notification center
  const btnNotifications        = document.getElementById('btn-notifications');
  const notifBellWrap           = document.getElementById('notif-bell-wrap');
  const notifBellIcon           = document.getElementById('notif-bell-icon');
  const notifBadge              = document.getElementById('notif-badge');
  const notifDropdown           = document.getElementById('notif-dropdown');
  const notifList               = document.getElementById('notif-list');
  const notifCountChip          = document.getElementById('notif-count-chip');
  const btnMarkAllRead          = document.getElementById('btn-mark-all-read');
  const btnClearNotifs          = document.getElementById('btn-clear-notifs');

  /* ──────────────────────────────────────────
     BOOTSTRAP MODALS
  ────────────────────────────────────────── */
  const addRoutineModal    = new bootstrap.Modal(document.getElementById('addRoutineModal'));
  const routineLogsModal   = new bootstrap.Modal(document.getElementById('routineLogsModal'));
  const editRoutineModal   = new bootstrap.Modal(document.getElementById('editRoutineModal'));
  const clearOptionsModal  = new bootstrap.Modal(document.getElementById('clearOptionsModal'));

  /* ──────────────────────────────────────────
     STATE
  ────────────────────────────────────────── */
  let currentResponseBlock = null;
  let currentResponseText  = '';
  let isAgentRunning       = false;
  let schedulerOpen        = false;
  let notifDropdownOpen    = false;
  let notifUnreadCount     = 0;
  let finishTimeout        = null;  // failsafe: reset UI if agent_status never arrives

  /* ──────────────────────────────────────────
     THEME MANAGEMENT
  ────────────────────────────────────────── */
  function setTheme(theme) {
    if (theme === 'light') {
      body.classList.remove('theme-dark');
      body.classList.add('theme-light');
      themeIcon.className = 'bi bi-moon-fill';
      if (mobThemeIcon) mobThemeIcon.className = 'bi bi-moon-fill';
      localStorage.setItem('theme', 'light');
    } else {
      body.classList.remove('theme-light');
      body.classList.add('theme-dark');
      themeIcon.className = 'bi bi-sun-fill';
      if (mobThemeIcon) mobThemeIcon.className = 'bi bi-sun-fill';
      localStorage.setItem('theme', 'dark');
    }
  }

  setTheme(localStorage.getItem('theme') || 'dark');

  themeToggle.addEventListener('click', () => {
    setTheme(body.classList.contains('theme-dark') ? 'light' : 'dark');
  });

  // Mobile theme toggle mirrors desktop
  if (mobThemeToggle) {
    mobThemeToggle.addEventListener('click', () => {
      setTheme(body.classList.contains('theme-dark') ? 'light' : 'dark');
    });
  }

  /* ──────────────────────────────────────────
     CONNECTION STATUS
  ────────────────────────────────────────── */
  function setConnected(connected) {
    if (connected) {
      if (statusOrb) { statusOrb.classList.add('online'); statusOrb.classList.remove('offline'); }
      if (mobStatusOrb) { mobStatusOrb.classList.add('online'); mobStatusOrb.classList.remove('offline'); }
      if (topbarOrb) {
        topbarOrb.style.background  = 'var(--emerald)';
        topbarOrb.style.boxShadow   = '0 0 8px var(--emerald-glow)';
      }
      if (connectionIndicator) connectionIndicator.setAttribute('data-tip', 'Connected');
    } else {
      if (statusOrb) { statusOrb.classList.remove('online'); statusOrb.classList.add('offline'); }
      if (mobStatusOrb) { mobStatusOrb.classList.remove('online'); mobStatusOrb.classList.add('offline'); }
      if (topbarOrb) {
        topbarOrb.style.background  = 'var(--rose)';
        topbarOrb.style.boxShadow   = '0 0 8px var(--rose-glow)';
      }
      if (connectionIndicator) connectionIndicator.setAttribute('data-tip', 'Disconnected');
    }
  }

  socket.on('connect',    () => setConnected(true));
  socket.on('disconnect', () => setConnected(false));

  // Wire mobile scheduler button
  if (mobBtnScheduler) {
    mobBtnScheduler.addEventListener('click', openScheduler);
  }

  /* ──────────────────────────────────────────
     AGENT STATUS UI
  ────────────────────────────────────────── */
  function setAgentRunning(running) {
    isAgentRunning = running;

    // Always clear the failsafe timer when state changes
    if (finishTimeout) { clearTimeout(finishTimeout); finishTimeout = null; }

    if (running) {
      if (btnSubmit) btnSubmit.disabled   = true;
      if (promptInput) promptInput.disabled = true;
      if (commandSpinner) commandSpinner.style.display = 'flex';
      if (btnSubmit) btnSubmit.classList.add('is-running');
      if (btnSendIcon) btnSendIcon.className = 'bi bi-stop-fill';
      if (topbarStatusText) topbarStatusText.textContent = 'Processing...';
      if (topbarOrb) topbarOrb.style.animation = 'orbPulse 1s ease-in-out infinite';
    } else {
      if (btnSubmit) btnSubmit.disabled   = false;
      if (promptInput) promptInput.disabled = false;
      if (commandSpinner) commandSpinner.style.display = 'none';
      if (btnSubmit) btnSubmit.classList.remove('is-running');
      if (btnSendIcon) btnSendIcon.className = 'bi bi-arrow-up';
      if (topbarStatusText) topbarStatusText.textContent = 'Ready';
      if (topbarOrb) {
        topbarOrb.style.animation = 'none';  // 'none' fully kills inline animation
        topbarOrb.style.removeProperty('animation');  // then remove so CSS class can take over
      }
      currentResponseBlock = null;
      currentResponseText  = '';
      removeNeuralThinking();
      if (promptInput) promptInput.focus();
    }
  }

  /* ──────────────────────────────────────────
     SCROLL TO BOTTOM
  ────────────────────────────────────────── */
  function scrollToBottom() {
    chatViewport.scrollTop = chatViewport.scrollHeight;
  }

  /* ──────────────────────────────────────────
     CLEAR / RESET ENVIRONMENT OPTIONS
  ────────────────────────────────────────── */
  const btnClearChatOnly      = document.getElementById('btn-clear-chat-only');
  const btnClearWorkspaceOnly = document.getElementById('btn-clear-workspace-only');
  const btnClearBoth          = document.getElementById('btn-clear-both');

  function resetChatFeedUI() {
    const hero = document.getElementById('welcome-hero');
    chatFeed.innerHTML = '';
    if (hero) chatFeed.appendChild(hero);
    currentResponseBlock = null;
    currentResponseText  = '';
  }

  // Option 1: Clear Conversation Only
  if (btnClearChatOnly) {
    btnClearChatOnly.addEventListener('click', () => {
      clearOptionsModal.hide();
      if (!confirm('Clear all conversation history? This cannot be undone.')) return;
      
      fetch('/api/history', { method: 'DELETE' })
        .then(r => r.json())
        .then(() => {
          resetChatFeedUI();
          appendTrajectoryLog('[Console Log]: Conversation history cleared successfully.');
          showToast('Conversation history cleared.', 'success');
        });
    });
  }

  // Option 2: Clear Workspace Sandbox Only
  if (btnClearWorkspaceOnly) {
    btnClearWorkspaceOnly.addEventListener('click', () => {
      clearOptionsModal.hide();
      if (!confirm('Clear all files in workspace sandbox? This will permanently delete all created files.')) return;

      fetch('/api/reset', { method: 'POST' })
        .then(r => r.json())
        .then(() => {
          appendTrajectoryLog('[Console Log]: Sandbox workspace files deleted.');
          showToast('Workspace files cleared.', 'success');
        });
    });
  }

  // Option 3: Wipe Both
  if (btnClearBoth) {
    btnClearBoth.addEventListener('click', () => {
      clearOptionsModal.hide();
      if (!confirm('Wipe everything? This will clear all chat history and delete all workspace files.')) return;

      // Run both cleanups
      Promise.all([
        fetch('/api/history', { method: 'DELETE' }),
        fetch('/api/reset', { method: 'POST' })
      ])
      .then(() => {
        resetChatFeedUI();
        appendTrajectoryLog('[Console Log]: System reset complete. History and sandbox wiped.');
        showToast('Full system wipe complete.', 'success');
      });
    });
  }



  /* ──────────────────────────────────────────
     PROMPT SUBMISSION
  ────────────────────────────────────────── */
  promptForm.addEventListener('submit', e => {
    e.preventDefault();
    const prompt = promptInput.value.trim();
    if (!prompt || isAgentRunning) return;

    // Hide welcome hero after first message
    const hero = document.getElementById('welcome-hero');
    if (hero) {
      hero.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      hero.style.opacity    = '0';
      hero.style.transform  = 'translateY(-8px)';
      setTimeout(() => hero.remove(), 400);
    }
    const initLog = document.getElementById('init-log');
    if (initLog) initLog.remove();

    // Render user message
    appendUserMessage(prompt);
    promptInput.value = '';

    // Close any lingering neural thinking
    removeNeuralThinking();

    setAgentRunning(true);
    socket.emit('start_agent', { prompt });
  });

  /* ──────────────────────────────────────────
     APPEND HELPERS
  ────────────────────────────────────────── */
  function appendUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'user-msg-row';
    row.innerHTML = `<div class="user-msg-bubble">${escapeHTML(text)}</div>`;
    chatFeed.appendChild(row);
    scrollToBottom();
  }

  function appendTrajectoryLog(text) {
    const el = document.createElement('div');
    el.className = 'traj-log fade-in';
    el.innerHTML = `
      <span class="traj-prompt">❯</span>
      <span class="traj-text">${escapeHTML(text)}</span>
    `;
    chatFeed.appendChild(el);
    scrollToBottom();
  }

  function showNeuralThinking() {
    removeNeuralThinking();
    const el = document.createElement('div');
    el.id = 'neural-thinking';
    el.className = 'neural-thinking';
    el.innerHTML = `
      <div class="neural-orb">
        <div class="neural-orb-core"></div>
        <div class="neural-orb-ring"></div>
      </div>
      <div class="neural-label">
        <span style="color:var(--text-muted)">Neural processing</span>
        <div class="neural-dots">
          <div class="neural-dot"></div>
          <div class="neural-dot"></div>
          <div class="neural-dot"></div>
        </div>
      </div>
    `;
    chatFeed.appendChild(el);
    scrollToBottom();
  }

  function removeNeuralThinking() {
    const el = document.getElementById('neural-thinking');
    if (el) el.remove();
  }

  /* ──────────────────────────────────────────
     SOCKET EVENTS
  ────────────────────────────────────────── */
  socket.on('agent_status', data => {
    if (data.status === 'finished') {
      setAgentRunning(false);
      if (schedulerOpen) loadSchedulerPanel();
    }
  });

  socket.on('trajectory_log', data => {
    removeNeuralThinking();
    appendTrajectoryLog(data.log);
  });

  socket.on('thought_start', data => {
    showNeuralThinking();
    const el = document.getElementById('neural-thinking');
    if (el) {
      const label = el.querySelector('.neural-label span');
      if (label) {
        label.textContent = data.duration > 1
          ? `Neural processing (${data.duration}s)`
          : 'Neural processing';
      }
    }
  });

  socket.on('step_start', data => {
    removeNeuralThinking();
    renderToolStepCard(data, 'running');
  });

  socket.on('step_log', () => {
    // suppress raw step logs – shown inline in the tool card header
  });
  socket.on('step_complete', data => {
    updateToolStepCard(data.id, data.status === 'success' ? 'success' : 'error');
  });

  socket.on('ask_user_prompt', data => {
    const response = prompt(data.prompt);
    socket.emit('ask_user_response', { response: response || '' });
  });

  socket.on('thought_chunk', data => {
    removeNeuralThinking();

    if (!currentResponseBlock) {
      const blockId = `resp-${Date.now()}`;
      const row = document.createElement('div');
      row.className = 'agent-response-row fade-in';
      row.innerHTML = `
        <div class="agent-avatar">AT</div>
        <div class="agent-response-body">
          <div class="agent-response-card" id="${blockId}"></div>
        </div>
      `;
      chatFeed.appendChild(row);
      currentResponseBlock = document.getElementById(blockId);
      currentResponseText  = '';
    }

    currentResponseText += data.text;

    if (window.marked) {
      currentResponseBlock.innerHTML = marked.parse(currentResponseText);
    } else {
      currentResponseBlock.textContent = currentResponseText;
    }

    scrollToBottom();

    // Failsafe: if agent_status 'finished' never arrives within 8s of the
    // last chunk, auto-reset the UI so it doesn't stay stuck.
    if (finishTimeout) clearTimeout(finishTimeout);
    finishTimeout = setTimeout(() => {
      if (isAgentRunning) {
        console.warn('[Agent-T] agent_status timeout — resetting UI');
        setAgentRunning(false);
      }
    }, 8000);
  });

  /* ──────────────────────────────────────────
     TOOL STEP CARDS
  ────────────────────────────────────────── */
  function renderToolStepCard(data, status) {
    const card = document.createElement('div');
    card.id        = `step-card-${data.id}`;
    card.className = `tool-step-card status-${status}`;

    const iconClass = status === 'running' ? 'bi-gear-fill icon-spin' : 'bi-check-circle-fill';
    const badgeLabel = status === 'running' ? 'Running' : 'Done';

    card.innerHTML = `
      <div class="tool-step-header">
        <div class="tool-step-icon" id="step-icon-${data.id}">
          <i class="bi ${iconClass}" id="step-icon-el-${data.id}"></i>
        </div>
        <div class="tool-step-name" id="step-name-${data.id}">
          <strong>${escapeHTML(data.action)}</strong>
          <span style="color:var(--text-muted)"> — ${escapeHTML(data.name || '')}</span>
        </div>
        <span class="tool-step-status-badge ${status}" id="step-badge-${data.id}">${badgeLabel}</span>
      </div>
    `;

    chatFeed.appendChild(card);
    scrollToBottom();
  }

  function updateToolStepCard(stepId, status) {
    const card  = document.getElementById(`step-card-${stepId}`);
    const icon  = document.getElementById(`step-icon-${stepId}`);
    const iconEl = document.getElementById(`step-icon-el-${stepId}`);
    const badge = document.getElementById(`step-badge-${stepId}`);

    if (!card) return;

    card.classList.remove('status-running');
    card.classList.add(`status-${status}`);

    if (icon) icon.className = `tool-step-icon`;

    if (iconEl) {
      iconEl.className = status === 'success'
        ? 'bi bi-check-circle-fill'
        : 'bi bi-x-circle-fill';
    }

    if (badge) {
      badge.className  = `tool-step-status-badge ${status}`;
      badge.textContent = status === 'success' ? 'Done' : 'Error';
    }
  }

  /* ──────────────────────────────────────────
     SCHEDULER SLIDE-OVER PANEL
  ────────────────────────────────────────── */
  function openScheduler() {
    schedulerOverlay.classList.add('is-open');
    schedulerPanel.classList.add('is-open');
    schedulerOpen = true;
    loadSchedulerPanel();
    document.body.style.overflow = 'hidden';
  }

  function closeScheduler() {
    schedulerOverlay.classList.remove('is-open');
    schedulerPanel.classList.remove('is-open');
    schedulerOpen = false;
    document.body.style.overflow = '';
  }

  btnOpenScheduler.addEventListener('click', openScheduler);
  btnCloseScheduler.addEventListener('click', closeScheduler);
  schedulerOverlay.addEventListener('click', closeScheduler);

  // Keyboard ESC to close
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && schedulerOpen) closeScheduler();
  });

  /* ──────────────────────────────────────────
     LOAD SCHEDULER DATA
  ────────────────────────────────────────── */
  function loadSchedulerPanel() {
    schedulerPanelBody.innerHTML = `
      <div class="text-center py-5" style="color:var(--text-muted);font-size:0.8rem;">
        <div class="spinner-border spinner-border-sm text-secondary me-2" role="status"></div>
        Fetching routines...
      </div>
    `;
    fetch('/api/routines')
      .then(r => r.json())
      .then(data => {
        if (data.status === 'success') {
          renderSchedulerPanel(data.routines);
        } else {
          schedulerPanelBody.innerHTML = `
            <div style="color:var(--rose);font-size:0.8rem;padding:20px;">
              Error: ${escapeHTML(data.message)}
            </div>
          `;
        }
      })
      .catch(() => {
        schedulerPanelBody.innerHTML = `
          <div style="color:var(--rose);font-size:0.8rem;padding:20px;">
            Failed to load routines.
          </div>
        `;
      });
  }

  function renderSchedulerPanel(routines) {
    if (!routines || routines.length === 0) {
      schedulerPanelBody.innerHTML = `
        <div class="scheduler-empty">
          <i class="bi bi-calendar-x"></i>
          <p>No routines scheduled yet.<br>Create your first background routine.</p>
        </div>
      `;
      return;
    }

    schedulerPanelBody.innerHTML = '';
    routines.forEach((r, i) => {
      const isPaused  = r.status === 'paused';
      const lastRun   = r.last_run ? r.last_run.slice(0, 19).replace('T', ' ') : '—';
      const nextRun   = r.next_run ? r.next_run.slice(0, 19).replace('T', ' ') : '—';

      const card = document.createElement('div');
      card.className = 'routine-card';
      card.style.animationDelay = `${i * 0.04}s`;

      card.innerHTML = `
        <div class="routine-card-top">
          <div class="routine-card-name" title="${escapeHTML(r.name)}">${escapeHTML(r.name)}</div>
          <span class="routine-status-pill ${isPaused ? 'paused' : 'active'}">${isPaused ? 'Paused' : 'Active'}</span>
        </div>

        <div class="routine-meta">
          <div class="routine-meta-row">
            <i class="bi bi-clock"></i>
            <span>Schedule: <span class="val">${escapeHTML(r.schedule)}</span></span>
          </div>
          <div class="routine-meta-row">
            <i class="bi bi-cpu"></i>
            <span>Type: <span class="val">${escapeHTML(r.type)}</span></span>
          </div>
          <div class="routine-meta-row">
            <i class="bi bi-arrow-left-right"></i>
            <span>Last: <span class="val">${lastRun}</span></span>
          </div>
          <div class="routine-meta-row">
            <i class="bi bi-arrow-right"></i>
            <span>Next: <span class="val">${nextRun}</span></span>
          </div>
        </div>

        <div class="routine-action-snippet">${escapeHTML(r.action)}</div>

        <div class="routine-actions">
          <button class="btn-routine btn-trigger" data-action="trigger" data-name="${escapeHTML(r.name)}">
            <i class="bi bi-play-fill"></i> Run
          </button>
          <button class="btn-routine btn-toggle-pause" data-action="toggle-pause" data-name="${escapeHTML(r.name)}" data-status="${r.status}">
            <i class="bi ${isPaused ? 'bi-play-circle' : 'bi-pause-fill'}"></i> ${isPaused ? 'Resume' : 'Pause'}
          </button>
          <button class="btn-routine" data-action="view-logs" data-name="${escapeHTML(r.name)}">
            <i class="bi bi-list-task"></i> Logs
          </button>
          <button class="btn-routine" data-action="edit" data-name="${escapeHTML(r.name)}" data-schedule="${escapeHTML(r.schedule)}" data-action-val="${escapeHTML(r.action)}" data-timeout="${r.timeout}">
            <i class="bi bi-pencil"></i> Edit
          </button>
          <button class="btn-routine btn-delete" data-action="delete" data-name="${escapeHTML(r.name)}">
            <i class="bi bi-trash"></i>
          </button>
        </div>
      `;

      // Wire buttons
      card.querySelectorAll('[data-action]').forEach(btn => {
        btn.addEventListener('click', () => handleRoutineAction(btn));
      });

      schedulerPanelBody.appendChild(card);
    });
  }

  function handleRoutineAction(btn) {
    const action = btn.getAttribute('data-action');
    const name   = btn.getAttribute('data-name');

    if (action === 'trigger') {
      btn.disabled = true;
      fetch(`/api/routines/${encodeURIComponent(name)}/trigger`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
          showToast(data.message, data.status === 'success' ? 'success' : 'error');
          loadSchedulerPanel();
        })
        .finally(() => btn.disabled = false);
    }
    else if (action === 'toggle-pause') {
      const status   = btn.getAttribute('data-status');
      const endpoint = status === 'paused' ? 'resume' : 'pause';
      btn.disabled   = true;
      fetch(`/api/routines/${encodeURIComponent(name)}/${endpoint}`, { method: 'POST' })
        .then(r => r.json())
        .then(() => loadSchedulerPanel())
        .finally(() => btn.disabled = false);
    }
    else if (action === 'edit') {
      const name      = btn.getAttribute('data-name');
      const schedule  = btn.getAttribute('data-schedule');
      const actionVal = btn.getAttribute('data-action-val');
      const timeout   = btn.getAttribute('data-timeout');
      openEditModal(name, schedule, actionVal, timeout);
    }
    else if (action === 'view-logs') {
      openLogsModal(name);
    }
    else if (action === 'delete') {
      if (!confirm(`Delete routine '${name}'? This cannot be undone.`)) return;
      fetch(`/api/routines/${encodeURIComponent(name)}`, { method: 'DELETE' })
        .then(r => r.json())
        .then(() => loadSchedulerPanel());
    }
  }

  /* ──────────────────────────────────────────
     ADD ROUTINE MODAL
  ────────────────────────────────────────── */
  btnAddRoutineTrigger.addEventListener('click', () => {
    createRoutineForm.reset();
    routineErrorAlert.classList.add('d-none');
    addRoutineModal.show();
  });

  createRoutineForm.addEventListener('submit', e => {
    e.preventDefault();
    routineErrorAlert.classList.add('d-none');

    const payload = {
      name:     document.getElementById('routine-name').value.trim(),
      schedule: document.getElementById('routine-schedule').value.trim(),
      type:     document.getElementById('routine-type').value,
      action:   document.getElementById('routine-action').value.trim(),
      timeout:  parseInt(document.getElementById('routine-timeout').value)
    };

    fetch('/api/routines', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(data => {
      if (data.status === 'success') {
        addRoutineModal.hide();
        loadSchedulerPanel();
        showToast(`Routine '${payload.name}' scheduled.`, 'success');
      } else {
        routineErrorAlert.textContent = data.message;
        routineErrorAlert.classList.remove('d-none');
      }
    })
    .catch(() => {
      routineErrorAlert.textContent = 'Request failed. Please try again.';
      routineErrorAlert.classList.remove('d-none');
    });
  });

  /* ──────────────────────────────────────────
     EDIT ROUTINE MODAL
  ────────────────────────────────────────── */
  function openEditModal(name, schedule, actionVal, timeout) {
    editRoutineNameHidden.value                          = name;
    editRoutineNameLabel.textContent                     = name;
    document.getElementById('edit-routine-schedule').value = schedule;
    document.getElementById('edit-routine-action').value   = actionVal;
    document.getElementById('edit-routine-timeout').value  = timeout;
    editRoutineError.classList.add('d-none');
    editRoutineModal.show();
  }

  editRoutineForm.addEventListener('submit', e => {
    e.preventDefault();
    editRoutineError.classList.add('d-none');

    const name    = editRoutineNameHidden.value;
    const payload = {
      schedule: document.getElementById('edit-routine-schedule').value.trim(),
      action:   document.getElementById('edit-routine-action').value.trim(),
      timeout:  parseInt(document.getElementById('edit-routine-timeout').value)
    };

    fetch(`/api/routines/${encodeURIComponent(name)}`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(data => {
      if (data.status === 'success') {
        editRoutineModal.hide();
        loadSchedulerPanel();
        showToast(`Routine '${name}' updated.`, 'success');
      } else {
        editRoutineError.textContent = data.message;
        editRoutineError.classList.remove('d-none');
      }
    })
    .catch(() => {
      editRoutineError.textContent = 'Request failed. Please try again.';
      editRoutineError.classList.remove('d-none');
    });
  });

  /* ──────────────────────────────────────────
     LOGS MODAL
  ────────────────────────────────────────── */
  function openLogsModal(name) {
    logModalRoutineName.textContent = name;
    routineLogsContainer.innerHTML = `
      <div class="text-center py-5" style="color:var(--text-muted);font-size:0.8rem;">
        <div class="spinner-border spinner-border-sm text-secondary me-2" role="status"></div>
        Loading logs...
      </div>
    `;
    routineLogsModal.show();

    fetch(`/api/routines/${encodeURIComponent(name)}/logs?limit=30`)
      .then(r => r.json())
      .then(data => {
        if (data.status === 'success') renderLogs(data.logs);
        else routineLogsContainer.innerHTML = `<div class="p-4" style="color:var(--rose);">Error: ${escapeHTML(data.message)}</div>`;
      })
      .catch(() => {
        routineLogsContainer.innerHTML = `<div class="p-4" style="color:var(--rose);">Failed to retrieve logs.</div>`;
      });
  }

  function renderLogs(logs) {
    if (!logs || logs.length === 0) {
      routineLogsContainer.innerHTML = `
        <div class="text-center py-5" style="color:var(--text-muted);font-size:0.8rem;">
          No execution history found.
        </div>
      `;
      return;
    }

    routineLogsContainer.innerHTML = '';
    logs.forEach(log => {
      const triggered = log.triggered_at.slice(0, 19).replace('T', ' ');
      const finished  = log.finished_at  ? log.finished_at.slice(0, 19).replace('T', ' ') : '—';

      let statusClass = 'running';
      if (log.status === 'success') statusClass = 'success';
      else if (log.status === 'failure') statusClass = 'failure';
      else if (log.status === 'timeout') statusClass = 'timeout';

      const row = document.createElement('div');
      row.className = 'log-row';
      row.innerHTML = `
        <div class="d-flex align-items-center justify-content-between mb-2" style="font-size:0.78rem;">
          <span style="color:var(--text-secondary);">
            Triggered: <strong style="color:var(--text-primary)">${triggered}</strong>
            &nbsp;·&nbsp;
            Finished: ${finished}
          </span>
          <span class="log-status-badge ${statusClass}">${log.status}</span>
        </div>
        ${log.output ? `
          <div style="font-size:0.7rem;color:var(--text-muted);font-weight:600;margin-bottom:4px;text-transform:uppercase;letter-spacing:0.06em;">Output</div>
          <pre class="log-pre">${escapeHTML(log.output)}</pre>
        ` : ''}
        ${log.error ? `
          <div style="font-size:0.7rem;color:var(--rose);font-weight:600;margin-bottom:4px;margin-top:8px;text-transform:uppercase;letter-spacing:0.06em;">Error</div>
          <pre class="log-pre error-pre">${escapeHTML(log.error)}</pre>
        ` : ''}
      `;
      routineLogsContainer.appendChild(row);
    });
  }

  /* ──────────────────────────────────────────
     TOAST NOTIFICATION
  ────────────────────────────────────────── */
  function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.style.cssText = `
      position: fixed;
      bottom: 90px;
      right: 24px;
      z-index: 9999;
      background: var(--bg-elevated);
      border: 1px solid ${type === 'success' ? 'var(--emerald-dim)' : 'var(--rose-dim)'};
      border-left: 3px solid ${type === 'success' ? 'var(--emerald)' : 'var(--rose)'};
      color: var(--text-primary);
      font-family: 'Inter', sans-serif;
      font-size: 0.8rem;
      padding: 12px 18px;
      border-radius: 10px;
      box-shadow: var(--panel-shadow);
      max-width: 320px;
      animation: toastIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
      backdrop-filter: var(--glass-blur);
    `;
    toast.textContent = message;

    const style = document.createElement('style');
    style.textContent = `
      @keyframes toastIn {
        from { opacity: 0; transform: translateY(12px) scale(0.96); }
        to   { opacity: 1; transform: translateY(0) scale(1); }
      }
      @keyframes toastOut {
        from { opacity: 1; transform: translateY(0) scale(1); }
        to   { opacity: 0; transform: translateY(8px) scale(0.96); }
      }
    `;
    document.head.appendChild(style);
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'toastOut 0.25s ease forwards';
      setTimeout(() => toast.remove(), 250);
    }, 3200);
  }

  /* ──────────────────────────────────────────
     ESCAPE HTML
  ────────────────────────────────────────── */
  function escapeHTML(str) {
    if (!str) return '';
    return String(str).replace(/[&<>'"\n]/g,
      c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c] || c)
    );
  }

  /* ──────────────────────────────────────────
     KEYBOARD SHORTCUTS
  ────────────────────────────────────────── */
  document.addEventListener('keydown', e => {
    // Focus input with '/' when not already focused
    if (e.key === '/' && document.activeElement !== promptInput && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      promptInput.focus();
    }
    // ESC to close notification dropdown
    if (e.key === 'Escape' && notifDropdownOpen) closeNotifDropdown();
  });

  /* ──────────────────────────────────────────
     NOTIFICATION CENTER
  ────────────────────────────────────────── */

  /** Converts an ISO timestamp to a relative-time string (e.g. '2m ago'). */
  function relativeTime(isoStr) {
    if (!isoStr) return '';
    const diff = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000);
    if (diff < 5)   return 'just now';
    if (diff < 60)  return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }

  /** Returns Bootstrap-icon class for a notification level. */
  function levelIcon(level) {
    const map = {
      success: 'bi-check-circle-fill',
      error:   'bi-x-circle-fill',
      warning: 'bi-exclamation-triangle-fill',
      info:    'bi-info-circle-fill'
    };
    return map[level] || map.info;
  }

  /** Updates the badge and header chip with the current unread count. */
  function updateBadge(count) {
    notifUnreadCount = Math.max(0, count);
    if (notifUnreadCount > 0) {
      notifBadge.textContent = notifUnreadCount > 99 ? '99+' : notifUnreadCount;
      notifBadge.style.display = 'block';
      notifCountChip.textContent = notifUnreadCount > 99 ? '99+' : notifUnreadCount;
      notifCountChip.style.display = 'inline-block';
      btnNotifications.classList.add('has-unread');
    } else {
      notifBadge.style.display = 'none';
      notifCountChip.style.display = 'none';
      btnNotifications.classList.remove('has-unread');
    }
  }

  /** Shakes the bell icon for 600ms. */
  function shakeBell() {
    btnNotifications.classList.remove('shake');
    // Force reflow to restart animation
    void btnNotifications.offsetWidth;
    btnNotifications.classList.add('shake');
    setTimeout(() => btnNotifications.classList.remove('shake'), 700);
  }

  /** Briefly pops the badge (scale animation). */
  function popBadge() {
    notifBadge.classList.remove('pop');
    void notifBadge.offsetWidth;
    notifBadge.classList.add('pop');
    setTimeout(() => notifBadge.classList.remove('pop'), 400);
  }

  /** Renders a single notification item DOM node. */
  function buildNotifItem(n) {
    const item = document.createElement('div');
    item.className = `notif-item ${n.is_read ? '' : 'unread'}`;
    item.dataset.id = n.id;

    item.innerHTML = `
      <div class="notif-level-icon ${escapeHTML(n.level)}">
        <i class="bi ${levelIcon(n.level)}"></i>
      </div>
      <div class="notif-item-body">
        <div class="notif-item-title">${escapeHTML(n.title)}</div>
        <div class="notif-item-msg">${escapeHTML(n.message)}</div>
        <div class="notif-item-time">${relativeTime(n.created_at)}</div>
      </div>
      ${!n.is_read ? '<div class="notif-unread-dot"></div>' : ''}
    `;
    return item;
  }

  /** Renders a full list of notifications into the dropdown. */
  function renderNotifications(notifications) {
    notifList.innerHTML = '';

    if (!notifications || notifications.length === 0) {
      notifList.innerHTML = `
        <div class="notif-empty">
          <i class="bi bi-bell-slash"></i>
          <p>No notifications yet.<br>Scheduler events will appear here.</p>
        </div>
      `;
      return;
    }

    notifications.forEach((n, i) => {
      const item = buildNotifItem(n);
      item.style.animationDelay = `${i * 0.03}s`;
      notifList.appendChild(item);
    });
  }

  /** Fetches notifications from the server and refreshes the dropdown. */
  function loadNotifications() {
    fetch('/api/notifications')
      .then(r => r.json())
      .then(data => {
        if (data.status === 'success') {
          renderNotifications(data.notifications);
          updateBadge(data.unread_count);
        }
      })
      .catch(() => {/* silently fail for background poll */});
  }

  /** Opens the notification dropdown and marks everything as read. */
  function openNotifDropdown() {
    notifDropdown.classList.add('is-open');
    notifDropdownOpen = true;
    // Refresh content on open
    loadNotifications();
    // Mark all as read after a short delay
    setTimeout(() => {
      if (notifUnreadCount > 0) {
        fetch('/api/notifications/mark-read', { method: 'POST' })
          .then(() => {
            updateBadge(0);
            // Visually clear unread state on items
            notifList.querySelectorAll('.notif-item.unread').forEach(el => {
              el.classList.remove('unread');
              const dot = el.querySelector('.notif-unread-dot');
              if (dot) dot.remove();
            });
          });
      }
    }, 400);
  }

  /** Closes the notification dropdown. */
  function closeNotifDropdown() {
    notifDropdown.classList.remove('is-open');
    notifDropdownOpen = false;
  }

  /** Toggles the notification dropdown. */
  function toggleNotifDropdown() {
    if (notifDropdownOpen) {
      closeNotifDropdown();
    } else {
      openNotifDropdown();
    }
  }

  // Bell click
  btnNotifications.addEventListener('click', e => {
    e.stopPropagation();
    toggleNotifDropdown();
  });

  // Click outside to close
  document.addEventListener('click', e => {
    if (notifDropdownOpen && !notifBellWrap.contains(e.target)) {
      closeNotifDropdown();
    }
  });

  // Mark all read button
  btnMarkAllRead.addEventListener('click', e => {
    e.stopPropagation();
    fetch('/api/notifications/mark-read', { method: 'POST' })
      .then(() => {
        updateBadge(0);
        notifList.querySelectorAll('.notif-item.unread').forEach(el => {
          el.classList.remove('unread');
          const dot = el.querySelector('.notif-unread-dot');
          if (dot) dot.remove();
        });
      });
  });

  // Clear all button
  btnClearNotifs.addEventListener('click', e => {
    e.stopPropagation();
    fetch('/api/notifications', { method: 'DELETE' })
      .then(() => {
        renderNotifications([]);
        updateBadge(0);
      });
  });

  // ── Real-time push via SocketIO ──────────────────────────────────────────
  socket.on('notification_push', notif => {
    // Increment unread count and animate bell
    updateBadge(notifUnreadCount + 1);
    shakeBell();
    popBadge();

    // Prepend to the list if dropdown is open
    if (notifDropdownOpen) {
      // Remove empty state if present
      const empty = notifList.querySelector('.notif-empty');
      if (empty) empty.remove();
      const item = buildNotifItem({ ...notif, is_read: false });
      notifList.insertBefore(item, notifList.firstChild);
    }

    // Also show a toast for immediate feedback
    const levelToast = notif.level === 'success' ? 'success' : 'error';
    showToast(`🔔 ${notif.title}`, levelToast);
  });

  // ── Conversation History ──────────────────────────────────────────────────
  function loadHistory() {
    fetch('/api/history')
      .then(r => r.json())
      .then(data => {
        if (data.status !== 'success' || !data.events || data.events.length === 0) return;

        // Hide welcome hero if we have previous messages
        const hero = document.getElementById('welcome-hero');
        if (hero) hero.remove();
        const initLog = document.getElementById('init-log');
        if (initLog) initLog.remove();

        data.events.forEach(ev => {
          if (ev.event_type === 'user_msg') {
            appendUserMessage(ev.content);
          } else if (ev.event_type === 'traj_log') {
            appendTrajectoryLog(ev.content);
          } else if (ev.event_type === 'tool_step') {
            // Re-render tool step card with its status
            const meta = ev.meta || {};
            renderToolStepCard({
              id: ev.id,
              action: meta.action || 'tool',
              name: (meta.name || '').replace(/^Running tool:\s*/, ''),
              details: meta.details || ''
            }, meta.status || 'success');
          } else if (ev.event_type === 'agent_response') {
            // Re-create assistant message body
            const blockId = `resp-hist-${ev.id}`;
            const row = document.createElement('div');
            row.className = 'agent-response-row';
            row.innerHTML = `
              <div class="agent-avatar">AT</div>
              <div class="agent-response-body">
                <div class="agent-response-card" id="${blockId}"></div>
              </div>
            `;
            chatFeed.appendChild(row);
            const block = document.getElementById(blockId);
            if (block) {
              if (window.marked) {
                block.innerHTML = marked.parse(ev.content);
              } else {
                block.textContent = ev.content;
              }
            }
          }
        });
        scrollToBottom();
      })
      .catch(() => {});
  }

  // ── Initial load on page ready ────────────────────────────────────────────
  loadNotifications();
  loadHistory();

  /* ──────────────────────────────────────────
     INIT
  ────────────────────────────────────────── */
  /* ──────────────────────────────────────────
     PIPELINES ENGINE INTEGRATION
  ────────────────────────────────────────── */
  const btnOpenPipelines        = document.getElementById('btn-open-pipelines');
  const mobBtnPipelines         = document.getElementById('mob-btn-pipelines');
  const pipelinesOverlay        = document.getElementById('pipelines-overlay');
  const pipelinesPanel          = document.getElementById('pipelines-panel');
  const btnClosePipelines       = document.getElementById('btn-close-pipelines');
  const pipelinesPanelBody      = document.getElementById('pipelines-panel-body');
  const btnCreatePipelineTrigger = document.getElementById('btn-create-pipeline-trigger');

  // Modals
  const addPipelineModal        = new bootstrap.Modal(document.getElementById('addPipelineModal'));
  const runPipelineModal        = new bootstrap.Modal(document.getElementById('runPipelineModal'));
  const pipelineLogsModal       = new bootstrap.Modal(document.getElementById('pipelineLogsModal'));

  // Form elements
  const createPipelineForm      = document.getElementById('create-pipeline-form');
  const pipelineTemplateSel     = document.getElementById('pipeline-template-selector');
  const runPipelineForm         = document.getElementById('run-pipeline-form');
  const btnCancelPipelineRun    = document.getElementById('btn-cancel-pipeline-run');

  let pipelinesOpen             = false;
  let activeLogRunId            = null;
  let activeLogTimer            = null;

  // Toggle slide-over panel
  function openPipelines() {
    pipelinesOverlay.classList.add('is-open');
    pipelinesPanel.classList.add('is-open');
    pipelinesOpen = true;
    loadPipelinesPanel();
    document.body.style.overflow = 'hidden';
  }

  function closePipelines() {
    pipelinesOverlay.classList.remove('is-open');
    pipelinesPanel.classList.remove('is-open');
    pipelinesOpen = false;
    document.body.style.overflow = '';
  }

  if (btnOpenPipelines) btnOpenPipelines.addEventListener('click', openPipelines);
  if (mobBtnPipelines) mobBtnPipelines.addEventListener('click', openPipelines);
  if (btnClosePipelines) btnClosePipelines.addEventListener('click', closePipelines);
  if (pipelinesOverlay) pipelinesOverlay.addEventListener('click', closePipelines);

  // Esc key closure
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && pipelinesOpen) closePipelines();
  });

  // Template select options
  const templates = {
    code_compiler: {
      variables: { file_name: "test_pipeline.py", run_args: "hello_engine" },
      steps: [
        {
          id: "write_code",
          name: "Write Sample Code",
          type: "tool",
          action: "write_to_file",
          args: {
            TargetFile: "{{variables.file_name}}",
            Overwrite: true,
            CodeContent: "import sys\nprint('Execution successful!')\nprint('Arguments:', sys.argv[1:])\nsys.exit(0)\n",
            Description: "Create script file"
          }
        },
        {
          id: "run_code",
          name: "Execute Code via Shell",
          type: "shell",
          action: "python {{variables.file_name}} {{variables.run_args}}",
          depends_on: ["write_code"]
        }
      ]
    },
    parallel_runner: {
      variables: { var_1: "Process A", var_2: "Process B" },
      steps: [
        {
          id: "task_a",
          name: "Launch Process A",
          type: "shell",
          action: "echo Parallel execution for {{variables.var_1}}"
        },
        {
          id: "task_b",
          name: "Launch Process B",
          type: "shell",
          action: "echo Parallel execution for {{variables.var_2}}"
        },
        {
          id: "task_c",
          name: "Merge Outputs",
          type: "python",
          action: "print('Merge complete.')\nprint('Task A output:', steps['task_a']['stdout'].strip())\nprint('Task B output:', steps['task_b']['stdout'].strip())\n",
          depends_on: ["task_a", "task_b"]
        }
      ]
    },
    agent_analyzer: {
      variables: { topic: "Cellular Respiration", report_name: "report.txt" },
      steps: [
        {
          id: "agent_prompt",
          name: "Prompt Agent for summary",
          type: "prompt",
          action: "Write a 3-bullet summary of {{variables.topic}}."
        },
        {
          id: "save_summary",
          name: "Write summary to file",
          type: "tool",
          action: "write_to_file",
          args: {
            TargetFile: "{{variables.report_name}}",
            Overwrite: true,
            CodeContent: "{{steps.agent_prompt.output}}",
            Description: "Save agent response"
          },
          depends_on: ["agent_prompt"]
        }
      ]
    }
  };

  if (pipelineTemplateSel) {
    pipelineTemplateSel.addEventListener('change', () => {
      const val = pipelineTemplateSel.value;
      if (val && templates[val]) {
        document.getElementById('pipeline-definition').value = JSON.stringify(templates[val], null, 2);
      }
    });
  }

  if (btnCreatePipelineTrigger) {
    btnCreatePipelineTrigger.addEventListener('click', () => {
      document.getElementById('pipeline-id').value = '';
      document.getElementById('pipeline-id').disabled = false;
      document.getElementById('pipeline-name').value = '';
      document.getElementById('pipeline-description').value = '';
      document.getElementById('pipeline-definition').value = '';
      document.getElementById('pipeline-template-selector').value = '';
      document.getElementById('pipeline-error-alert').classList.add('d-none');
      addPipelineModal.show();
    });
  }

  // Create/Edit pipeline form submission
  if (createPipelineForm) {
    createPipelineForm.addEventListener('submit', e => {
      e.preventDefault();
      const pipeline_id = document.getElementById('pipeline-id').value.trim();
      const name = document.getElementById('pipeline-name').value.trim();
      const description = document.getElementById('pipeline-description').value.trim();
      const definition_text = document.getElementById('pipeline-definition').value.trim();
      const error_alert = document.getElementById('pipeline-error-alert');

      let definition;
      try {
        definition = JSON.parse(definition_text);
      } catch (err) {
        error_alert.textContent = `Invalid JSON: ${err.message}`;
        error_alert.classList.remove('d-none');
        return;
      }

      fetch('/api/pipelines', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: pipeline_id, name, description, definition })
      })
      .then(r => r.json())
      .then(res => {
        if (res.status === 'success') {
          addPipelineModal.hide();
          loadPipelinesPanel();
          showToast(res.message, 'success');
        } else {
          error_alert.textContent = res.message;
          error_alert.classList.remove('d-none');
        }
      })
      .catch(err => {
        error_alert.textContent = `Server error: ${err.message}`;
        error_alert.classList.remove('d-none');
      });
    });
  }

  // Load and render configured pipelines
  function loadPipelinesPanel() {
    pipelinesPanelBody.innerHTML = `
      <div class="text-center py-5" style="color:var(--text-muted);font-size:0.8rem;">
        <div class="spinner-border spinner-border-sm text-secondary me-2" role="status"></div>
        Fetching pipelines...
      </div>
    `;
    fetch('/api/pipelines')
      .then(r => r.json())
      .then(data => {
        if (data.status === 'success') {
          renderPipelinesPanel(data.pipelines);
        } else {
          pipelinesPanelBody.innerHTML = `<div style="color:var(--rose);padding:20px;">Error: ${data.message}</div>`;
        }
      })
      .catch(() => {
        pipelinesPanelBody.innerHTML = `<div style="color:var(--rose);padding:20px;">Failed to fetch pipelines.</div>`;
      });
  }

  function renderPipelinesPanel(pipelines) {
    if (!pipelines || pipelines.length === 0) {
      pipelinesPanelBody.innerHTML = `
        <div class="scheduler-empty">
          <i class="bi bi-diagram-3"></i>
          <p>No pipelines configured yet.<br>Create a new DAG pipeline to start.</p>
        </div>
      `;
      return;
    }

    pipelinesPanelBody.innerHTML = '';
    
    // Header for runs history
    const sectionTitle = document.createElement('div');
    sectionTitle.style.cssText = 'font-weight:600;font-size:0.75rem;text-transform:uppercase;color:var(--text-muted);margin:10px 0 16px 4px;';
    sectionTitle.textContent = 'Configured Pipelines';
    pipelinesPanelBody.appendChild(sectionTitle);

    pipelines.forEach((p, i) => {
      const card = document.createElement('div');
      card.className = 'routine-card';
      card.style.animationDelay = `${i * 0.04}s`;
      
      const stepsCount = p.definition.steps ? p.definition.steps.length : 0;
      const desc = p.description || 'No description';

      card.innerHTML = `
        <div class="routine-card-top">
          <div class="routine-card-name" title="${escapeHTML(p.name)}">${escapeHTML(p.name)}</div>
          <span class="routine-status-pill active">${p.id}</span>
        </div>
        <p style="font-size:0.78rem;color:var(--text-muted);margin:6px 0 12px 0;">${escapeHTML(desc)}</p>
        <div class="routine-meta" style="margin-bottom:12px;">
          <div class="routine-meta-row">
            <i class="bi bi-diagram-3"></i>
            <span>Steps: <span class="val">${stepsCount} DAG nodes</span></span>
          </div>
        </div>
        <div class="routine-actions">
          <button class="btn-routine btn-trigger" data-action="run" data-id="${p.id}">
            <i class="bi bi-play-fill"></i> Run
          </button>
          <button class="btn-routine" data-action="edit" data-id="${p.id}">
            <i class="bi bi-pencil"></i> Edit
          </button>
          <button class="btn-routine btn-delete" data-action="delete" data-id="${p.id}">
            <i class="bi bi-trash"></i> Delete
          </button>
        </div>
      `;
      
      // Bind actions
      card.querySelector('[data-action="run"]').addEventListener('click', () => triggerRunInputs(p));
      card.querySelector('[data-action="edit"]').addEventListener('click', () => triggerEditPipeline(p));
      card.querySelector('[data-action="delete"]').addEventListener('click', () => deletePipeline(p.id));
      
      pipelinesPanelBody.appendChild(card);
    });

    // History run title
    const histTitle = document.createElement('div');
    histTitle.style.cssText = 'font-weight:600;font-size:0.75rem;text-transform:uppercase;color:var(--text-muted);margin:32px 0 16px 4px;';
    histTitle.textContent = 'Execution History';
    pipelinesPanelBody.appendChild(histTitle);

    const runsContainer = document.createElement('div');
    runsContainer.id = 'pipelines-history-runs-list';
    pipelinesPanelBody.appendChild(runsContainer);

    loadPipelinesHistory();
  }

  function triggerEditPipeline(p) {
    document.getElementById('pipeline-id').value = p.id;
    document.getElementById('pipeline-id').disabled = true;
    document.getElementById('pipeline-name').value = p.name;
    document.getElementById('pipeline-description').value = p.description || '';
    document.getElementById('pipeline-definition').value = JSON.stringify(p.definition, null, 2);
    document.getElementById('pipeline-template-selector').value = '';
    document.getElementById('pipeline-error-alert').classList.add('d-none');
    addPipelineModal.show();
  }

  function deletePipeline(id) {
    if (!confirm(`Delete pipeline '${id}'? This cannot be undone.`)) return;
    fetch(`/api/pipelines/${id}`, { method: 'DELETE' })
      .then(r => r.json())
      .then(res => {
        loadPipelinesPanel();
        showToast(res.message, 'success');
      });
  }

  // Pre-fill variable form input fields
  function triggerRunInputs(p) {
    const container = document.getElementById('pipeline-inputs-container');
    container.innerHTML = '';
    
    document.getElementById('run-pipeline-id').value = p.id;
    const def_variables = p.definition.variables || {};
    const keys = Object.keys(def_variables);
    
    if (keys.length === 0) {
      container.innerHTML = `<div class="text-secondary fs-9">This pipeline requires no input variables. Click Start below.</div>`;
    } else {
      keys.forEach(key => {
        const div = document.createElement('div');
        div.innerHTML = `
          <label class="form-label">${escapeHTML(key)}</label>
          <input type="text" class="form-control" name="var-${escapeHTML(key)}" value="${escapeHTML(String(def_variables[key]))}">
        `;
        container.appendChild(div);
      });
    }
    runPipelineModal.show();
  }

  // Run execution triggered
  if (runPipelineForm) {
    runPipelineForm.addEventListener('submit', e => {
      e.preventDefault();
      const id = document.getElementById('run-pipeline-id').value;
      const container = document.getElementById('pipeline-inputs-container');
      const inputs = {};
      
      container.querySelectorAll('input').forEach(inp => {
        const name = inp.name.replace(/^var-/, '');
        inputs[name] = inp.value;
      });

      fetch(`/api/pipelines/${id}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inputs })
      })
      .then(r => r.json())
      .then(res => {
        if (res.status === 'success') {
          runPipelineModal.hide();
          loadPipelinesPanel();
          showToast(res.message, 'success');
          // Open log streaming modal instantly for active run logs
          openPipelineLogs(res.run_id);
        } else {
          alert(`Error: ${res.message}`);
        }
      });
    });
  }

  // Load runs execution history
  function loadPipelinesHistory() {
    const list = document.getElementById('pipelines-history-runs-list');
    if (!list) return;

    list.innerHTML = `<div class="text-muted fs-9 py-2 text-center">Loading run logs...</div>`;
    fetch('/api/pipelines/runs')
      .then(r => r.json())
      .then(data => {
        if (data.status === 'success' && list) {
          if (data.runs.length === 0) {
            list.innerHTML = `<div class="text-muted fs-9 py-3 text-center">No runs recorded.</div>`;
            return;
          }
          list.innerHTML = '';
          data.runs.forEach(run => {
            const card = document.createElement('div');
            card.style.cssText = 'background:var(--bg-elevated);border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:10px;cursor:pointer;transition:all 0.15s ease;';
            card.addEventListener('mouseenter', () => card.style.borderColor = 'var(--border-hover)');
            card.addEventListener('mouseleave', () => card.style.borderColor = 'var(--border)');
            card.addEventListener('click', () => openPipelineLogs(run.id));

            const triggerTime = run.triggered_at.slice(11, 19);
            const statusClass = run.status === 'completed' ? 'text-success' : (run.status === 'failed' ? 'text-danger' : 'text-warning');
            
            card.innerHTML = `
              <div class="d-flex justify-content-between align-items-center mb-1">
                <span style="font-weight:600;font-size:0.8rem;color:var(--text-primary)">Run #${run.id} — ${escapeHTML(run.pipeline_name)}</span>
                <span style="font-size:0.75rem;font-weight:600;" class="${statusClass}">${run.status}</span>
              </div>
              <div class="d-flex justify-content-between fs-9 text-muted">
                <span>Triggered at: ${triggerTime}</span>
                <span>ID: ${run.pipeline_id}</span>
              </div>
            `;
            list.appendChild(card);
          });
        }
      });
  }

  // Open Log modal and stream details
  function openPipelineLogs(runId) {
    activeLogRunId = runId;
    document.getElementById('pipeline-log-run-id').textContent = runId;
    document.getElementById('pipeline-run-terminal-body').innerHTML = '<div class="text-muted">Initiating trace log outputs...</div>';
    document.getElementById('pipeline-run-steps-list').innerHTML = '';
    
    // Retrieve run stats
    refreshPipelineLogs();
    
    // Poll logs details while running
    if (activeLogTimer) clearInterval(activeLogTimer);
    activeLogTimer = setInterval(refreshPipelineLogs, 2500);

    pipelineLogsModal.show();
  }

  function refreshPipelineLogs() {
    if (!activeLogRunId) return;

    fetch(`/api/pipelines/runs/${activeLogRunId}/logs`)
      .then(r => r.json())
      .then(res => {
        if (res.status === 'success' && activeLogRunId === res.run.id) {
          const run = res.run;
          const logs = res.logs;

          // Update Run status badge
          const badge = document.getElementById('pipeline-run-status-badge');
          badge.textContent = run.status;
          badge.className = 'badge';
          if (run.status === 'completed') badge.classList.add('bg-success');
          else if (run.status === 'failed') badge.classList.add('bg-danger');
          else if (run.status === 'canceled') badge.classList.add('bg-secondary');
          else badge.classList.add('bg-warning', 'text-dark');

          // Toggle cancel button
          const cancelBtn = document.getElementById('btn-cancel-pipeline-run');
          if (run.status === 'running') cancelBtn.removeAttribute('disabled');
          else cancelBtn.setAttribute('disabled', 'true');

          // Render step checklist DAG list
          const list = document.getElementById('pipeline-run-steps-list');
          list.innerHTML = '';
          logs.forEach(l => {
            const row = document.createElement('div');
            row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;background:var(--bg-elevated);border:1px solid var(--border);padding:8px 12px;border-radius:8px;font-size:0.75rem;';
            
            let statusIcon = '<i class="bi bi-circle text-muted"></i>';
            if (l.status === 'running') statusIcon = '<div class="spinner-border spinner-border-sm text-warning" role="status" style="width:12px;height:12px;"></div>';
            else if (l.status === 'success') statusIcon = '<i class="bi bi-check-circle-fill text-success"></i>';
            else if (l.status === 'failed') statusIcon = '<i class="bi bi-x-circle-fill text-danger"></i>';
            else if (l.status === 'skipped') statusIcon = '<i class="bi bi-arrow-right-circle text-secondary"></i>';

            row.innerHTML = `
              <div class="d-flex align-items-center gap-2">
                ${statusIcon}
                <span style="font-weight:500;" class="text-primary">${escapeHTML(l.step_name)}</span>
              </div>
              <span class="text-muted fs-10" style="font-family:monospace;">${escapeHTML(l.step_id)}</span>
            `;
            list.appendChild(row);
          });

          // Compile all step outputs into console log view
          const term = document.getElementById('pipeline-run-terminal-body');
          term.innerHTML = '';

          // Input block
          const inpBlock = document.createElement('div');
          inpBlock.style.color = 'var(--indigo-light)';
          inpBlock.innerHTML = `[Pipeline Inputs Context]:<br>${escapeHTML(JSON.stringify(run.inputs, null, 2))}<br><br>`;
          term.appendChild(inpBlock);

          logs.forEach(l => {
            const div = document.createElement('div');
            div.style.marginBottom = '20px';
            
            const headClass = l.status === 'success' ? 'text-success' : (l.status === 'failed' ? 'text-danger' : 'text-warning');
            div.innerHTML = `
              <span class="${headClass}" style="font-weight:bold;">❯ Step: ${escapeHTML(l.step_id)} (${escapeHTML(l.step_name)}) [${l.status.toUpperCase()}]</span><br>
              <span class="text-muted" style="font-size:10px;">Started: ${l.started_at.slice(11, 19)} | Finished: ${l.finished_at ? l.finished_at.slice(11,19) : 'active'}</span><br>
            `;
            
            if (l.output) {
              const out = document.createElement('pre');
              out.style.cssText = 'background:rgba(0,0,0,0.2);padding:10px;border-radius:6px;border:1px solid var(--border);margin-top:6px;overflow-x:auto;white-space:pre-wrap;';
              out.textContent = l.output;
              div.appendChild(out);
            }
            if (l.error) {
              const err = document.createElement('pre');
              err.style.cssText = 'background:rgba(220,53,69,0.06);color:var(--rose);padding:10px;border-radius:6px;border:1px solid rgba(220,53,69,0.2);margin-top:6px;overflow-x:auto;white-space:pre-wrap;';
              err.textContent = l.error;
              div.appendChild(err);
            }
            term.appendChild(div);
          });

          // Overall pipeline run errors
          if (run.error) {
            const errBlock = document.createElement('div');
            errBlock.style.cssText = 'background:rgba(220,53,69,0.08);color:var(--rose);padding:12px;border-radius:8px;border:1px solid rgba(220,53,69,0.3);margin-top:20px;';
            errBlock.innerHTML = `<strong>Pipeline Execution Error:</strong><br>${escapeHTML(run.error)}`;
            term.appendChild(errBlock);
          }

          // If run has finished, clear active polling timer
          if (run.status !== 'running' && run.status !== 'pending') {
            if (activeLogTimer) {
              clearInterval(activeLogTimer);
              activeLogTimer = null;
            }
          }
        }
      });
  }

  // Cancel executing pipeline run
  if (btnCancelPipelineRun) {
    btnCancelPipelineRun.addEventListener('click', () => {
      if (!activeLogRunId || !confirm('Abort this pipeline execution run?')) return;
      fetch(`/api/pipelines/runs/${activeLogRunId}/cancel`, { method: 'POST' })
        .then(r => r.json())
        .then(res => {
          showToast(res.message, 'info');
          refreshPipelineLogs();
        });
    });
  }

  // Cancel timers on modal hide
  document.getElementById('pipelineLogsModal').addEventListener('hidden.bs.modal', () => {
    activeLogRunId = null;
    if (activeLogTimer) {
      clearInterval(activeLogTimer);
      activeLogTimer = null;
    }
  });

  // Socket IO streaming integration
  socket.on('pipeline_step_log', data => {
    if (activeLogRunId === data.run_id) {
      refreshPipelineLogs();
    }
  });

  socket.on('pipeline_step_status', data => {
    if (activeLogRunId === data.run_id) {
      refreshPipelineLogs();
    }
  });

  socket.on('pipeline_status', data => {
    if (activeLogRunId === data.run_id) {
      refreshPipelineLogs();
    }
    loadPipelinesHistory();
  });

  socket.on('pipeline_complete', data => {
    if (activeLogRunId === data.run_id) {
      refreshPipelineLogs();
    }
    loadPipelinesHistory();
  });

  promptInput.focus();

}); // DOMContentLoaded
