// The opaque workspace cookie is HttpOnly. Only a derived CSRF value reaches JS.
export function createWorkspaceClient(fetchImpl = globalThis.fetch, {sessionTimeoutMs = 30000} = {}) {
  let sessionPromise;
  async function json(path, options = {}) {
    const response = await fetchImpl(path, {credentials: 'same-origin', cache: 'no-store', ...options});
    let data;
    try { data = await response.json(); }
    catch { throw new Error('Le serveur ne répond pas normalement. Réessayez dans un instant.'); }
    if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : 'La demande a échoué.');
    return data;
  }
  function session() {
    if (!sessionPromise) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), sessionTimeoutMs);
      sessionPromise = json('/api/session', {signal: controller.signal}).then(data => {
        if (!data.csrf_token || data.isolation !== 'browser') throw new Error('Votre espace n’a pas pu être ouvert. Rechargez la page.');
        return data;
      }).catch(error => {
        sessionPromise = undefined;
        if (controller.signal.aborted) throw new Error('Votre espace met trop de temps à répondre. Rechargez la page.');
        throw error;
      }).finally(() => clearTimeout(timer));
    }
    return sessionPromise;
  }
  async function request(path, {method = 'GET', body, signal} = {}) {
    if (!/^\/api\//.test(path) && path !== '/process_frame' && path !== '/health') throw new Error('Chemin non autorisé.');
    const headers = {'Accept': 'application/json'};
    if (!['GET', 'HEAD'].includes(method)) {
      const current = await session();
      headers['X-CSRF-Token'] = current.csrf_token;
      headers['Content-Type'] = 'application/json';
    }
    return json(path, {method, headers, ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal});
  }
  function refreshSession() {sessionPromise = undefined; return session();}
  return {session, refreshSession, request};
}

export function cameraError(error) {
  if (error?.name === 'NotAllowedError') return 'L’accès à la caméra est refusé. Autorisez-la dans votre navigateur, puis réessayez.';
  if (error?.name === 'NotFoundError') return 'Aucune caméra n’a été trouvée sur cet appareil.';
  if (error?.name === 'NotReadableError') return 'La caméra est déjà utilisée ou indisponible. Fermez les autres applications qui l’utilisent.';
  if (error?.name === 'AbortError') return 'La demande a été interrompue.';
  return error?.message || 'La caméra n’a pas pu démarrer.';
}

export function similarityLabel(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
    ? Math.round(value * 100) + ' / 100' : '—';
}

export function captureSize(width, height) {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0)
    throw new Error('La caméra n’est pas encore prête. Patientez un instant.');
  const ratio = Math.min(1, 1280 / width, 720 / height);
  return {width: Math.max(1, Math.floor(width * ratio)), height: Math.max(1, Math.floor(height * ratio))};
}
