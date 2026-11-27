/* Wake Render on demand before sending game/profile writes.
 * No background polling or keep-alive; no automatic replay of mutations.
 */
(function () {
  'use strict';
  const MAX_WAIT = 110000;
  const FRESH_FOR = 20000;
  let readyAt = null;
  let waiting = null;
  let banner = null;

  function showStatus(message) {
    if (!banner) {
      banner = document.createElement('div');
      banner.setAttribute('role', 'status');
      banner.setAttribute('aria-live', 'polite');
      banner.style.cssText = 'position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:10000;max-width:calc(100vw - 24px);width:max-content;padding:10px 14px;box-sizing:border-box;background:#10283c;color:#ffe2a0;border:1px solid #edc574;border-radius:9px;box-shadow:0 3px 15px #0008;font:600 13px/1.45 system-ui,sans-serif;text-align:center;pointer-events:none;';
      document.body.appendChild(banner);
    }
    banner.textContent = message;
  }

  function clearStatus() {
    if (banner) banner.remove();
    banner = null;
  }

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

  async function probe(remaining) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), Math.min(16000, remaining));
    try {
      const response = await fetch('/api/service_ready', {
        method: 'GET', cache: 'no-store', credentials: 'same-origin',
        headers: {'Accept': 'application/json'}, redirect: 'error',
        signal: controller.signal
      });
      if (!response.ok || !(response.headers.get('content-type') || '').includes('application/json')) return false;
      const data = await response.json();
      return data.status === 'ready' && data.database === 'connected';
    } catch (_) {
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  function waitForBackend() {
    if (readyAt !== null && Date.now() - readyAt < FRESH_FOR) return Promise.resolve();
    if (waiting) return waiting;
    const started = Date.now();
    const notice = setTimeout(() => showStatus('Connecting to the game server…'), 600);
    waiting = (async () => {
      let delay = 2000;
      while (Date.now() - started < MAX_WAIT) {
        if (await probe(MAX_WAIT - (Date.now() - started))) {
          readyAt = Date.now();
          return;
        }
        const elapsed = Math.round((Date.now() - started) / 1000);
        showStatus('Game server is waking up. This can take about a minute. (' + elapsed + 's)');
        const remaining = MAX_WAIT - (Date.now() - started);
        if (remaining <= 0) break;
        await sleep(Math.min(delay, remaining));
        delay = Math.min(delay + 1000, 5000);
      }
      throw new Error('The game server did not become ready. Please retry. No new request was sent.');
    })().finally(() => {
      clearTimeout(notice);
      clearStatus();
      waiting = null;
    });
    return waiting;
  }

  function isGatewayFailure(response) {
    return [502, 503, 504].includes(response.status) ||
      (response.ok && !(response.headers.get('content-type') || '').toLowerCase().includes('json'));
  }

  window.bcApiFetch = async function (url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    await waitForBackend();
    let response;
    try {
      response = await fetch(url, options);
    } catch (error) {
      readyAt = null;
      if (method !== 'GET') throw error;
      await waitForBackend();
      return fetch(url, options);
    }
    if (isGatewayFailure(response)) {
      readyAt = null;
      if (method === 'GET') {
        await waitForBackend();
        return fetch(url, options);
      }
    }
    return response;
  };
})();
