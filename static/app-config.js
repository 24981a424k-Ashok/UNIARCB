/**
 * app-config.js — Frontend API Configuration
 * 
 * Set API_BASE to the backend server URL.
 * When running both backend and frontend separately:
 *   - Backend runs on:  http://127.0.0.1:8000
 *   - Frontend runs on: http://127.0.0.1:3000
 * 
 * In production, set API_BASE to your backend's public URL.
 */

(function() {
    // Auto-detect: If the page is being served from the backend (port 8000),
    // use relative paths. If served from a separate frontend server, use absolute URL.
    const currentPort = window.location.port;
    
    // Ports where the frontend static server runs (not the backend)
    const FRONTEND_ONLY_PORTS = ['3000', '5000', '5500', '4000'];
    
    if (FRONTEND_ONLY_PORTS.includes(currentPort)) {
        // Frontend is on a separate server — point to backend explicitly
        window.API_BASE = 'http://127.0.0.1:8000';
    } else {
        // Running through the backend (same origin) — use relative paths
        window.API_BASE = '';
    }

    // Helper: Build a full API URL from a relative path
    window.apiUrl = function(path) {
        return window.API_BASE + path;
    };

    console.log('[UNI ARC] API Base:', window.API_BASE || '(same origin)');
})();
