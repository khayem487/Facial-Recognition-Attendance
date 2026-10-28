import {createWorkspaceClient, cameraError, captureSize, similarityLabel} from './workspace-client.mjs';
const api = createWorkspaceClient();
const $ = id => document.getElementById(id);
const text = (element, value) => {if (element && element.textContent !== value) element.textContent = value;};
const element = (tag, value, className = '') => {const node = document.createElement(tag); node.textContent = value; node.className = className; return node;};
function feedback(target, message, kind = 'muted') {
  if (!target) return;
  target.className = 'feedback ' + kind; text(target, message);
}
function emptyList(target, message) {
  target?.replaceChildren(element('li', message, 'empty'));
}
async function request(path, options = {}) {
  const controller = new AbortController(), callerSignal = options.signal;
  const abort = () => controller.abort();
  if (callerSignal?.aborted) abort();
  callerSignal?.addEventListener('abort', abort, {once: true});
  const timer = setTimeout(abort, 30000);
  try {return await api.request(path, {...options, signal: controller.signal});}
  catch (error) {
    if (controller.signal.aborted && !callerSignal?.aborted)
      throw new Error('Le serveur met trop de temps à répondre. Réessayez dans un instant.');
    throw error;
  } finally {clearTimeout(timer); callerSignal?.removeEventListener('abort', abort);}
}
function makeCamera(video, placeholder, onEnded) {
  let stream = null, generation = 0;
  function stop() {
    generation++;
    if (stream) stream.getTracks().forEach(track => {track.onended = null; track.stop();});
    stream = null; video.srcObject = null;
    if (placeholder) placeholder.hidden = false;
  }
  async function start() {
    stop(); const ticket = generation;
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('La caméra nécessite un navigateur compatible et une connexion HTTPS.');
    const opened = await navigator.mediaDevices.getUserMedia({video: {width: {ideal: 1280}, height: {ideal: 720}, facingMode: 'user'}, audio: false});
    if (ticket !== generation) {opened.getTracks().forEach(track => track.stop()); return false;}
    stream = opened; video.srcObject = stream; video.muted = true;
    try {await video.play();}
    catch (error) {stop(); throw error;}
    if (ticket !== generation) return false;
    if (placeholder) placeholder.hidden = true;
    stream.getVideoTracks().forEach(track => {track.onended = onEnded;});
    return true;
  }
  return {start, stop, ready: () => !!stream && video.readyState >= 2};
}
function captureFrame(video) {
  const size = captureSize(video.videoWidth, video.videoHeight);
  const canvas = document.createElement('canvas'); canvas.width = size.width; canvas.height = size.height;
  canvas.getContext('2d').drawImage(video, 0, 0, size.width, size.height);
  return canvas.toDataURL('image/jpeg', .88);
}
function renderRecent(target, rows) {
  if (!rows.length) {emptyList(target, 'Aucun pointage dans votre espace pour le moment.'); return;}
  target.replaceChildren(...rows.slice(0, 15).map(row => {
    const item = element('li', ''), detail = element('div', '');
    const stamp = row.RecordedAt ? new Date(row.RecordedAt) : null;
    const when = stamp && Number.isFinite(stamp.getTime()) ? stamp.toLocaleString('fr-FR') : row.Time || 'Date indisponible';
    detail.append(element('strong', row.Name || 'Profil'), element('div', when, 'user-detail'));
    item.append(detail, element('span', row.Mode === 'recognition' ? 'Encodage facial' : 'OpenCV', 'pill'));
    return item;
  }));
}
function initAttendancePage() {
  const video = $('attendance-video'), start = $('start-attendance'), stop = $('stop-attendance');
  if (!video || !start || !stop) return;
  const output = $('attendance-feedback'), statusBox = $('attendance-status');
  let timer = null, generation = 0, pending = null, active = false, recentSequence = 0;
  const camera = makeCamera(video, $('attendance-placeholder'), () => finish('La caméra a été déconnectée.'));
  async function refreshRecent() {
    const ticket = ++recentSequence;
    const button = $('refresh-attendance'); button.disabled = true;
    try {const data = await request('/api/attendance/recent'); if (ticket === recentSequence) renderRecent($('recent-attendance-list'), data.rows || []);}
    catch (error) {if (ticket === recentSequence) feedback(output, error.message, 'error');}
    finally {if (ticket === recentSequence) button.disabled = false;}
  }
  function finish(message = 'Caméra arrêtée. Aucune nouvelle image n’est envoyée.') {
    generation++; active = false; clearTimeout(timer); pending?.abort(); pending = null;
    camera.stop(); start.disabled = false; stop.disabled = true;
    statusBox.classList.add('hidden'); text($('camera-state'), 'Éteinte'); feedback(output, message);
  }
  async function processFrame(ticket) {
    if (!active || ticket !== generation) return;
    if (!camera.ready()) {timer = setTimeout(() => processFrame(ticket), 1200); return;}
    const controller = new AbortController(); pending = controller;
    try {
      const result = await request('/process_frame', {method: 'POST', body: {frame: captureFrame(video)}, signal: controller.signal});
      if (!active || ticket !== generation) return;
      if (result.success) {
        statusBox.classList.remove('hidden');
        text($('employee-name'), result.name || 'Profil'); text($('employee-mode'), result.mode === 'recognition' ? 'Encodage facial' : 'OpenCV');
        text($('employee-confidence'), similarityLabel(result.confidence));
        feedback(output, result.marked ? 'Pointage ajouté à votre historique.' : 'Référence similaire. Un pointage récent existe déjà.', 'success');
        if (result.marked) await refreshRecent();
      } else {
        statusBox.classList.add('hidden');
        feedback(output, result.prediction === 'NO_FACE' ? 'Aucun visage détecté. Centrez-vous face à la lumière.' : 'Aucune référence rapprochée. Vous pouvez ajouter un profil depuis Profils.');
      }
    } catch (error) {
      if (!active || ticket !== generation || controller.signal.aborted) return;
      statusBox.classList.add('hidden'); feedback(output, error.message, 'error');
    } finally {
      if (pending === controller) pending = null;
      if (active && ticket === generation) timer = setTimeout(() => processFrame(ticket), 1500);
    }
  }
  start.addEventListener('click', async () => {
    start.disabled = true; stop.disabled = false; const ticket = ++generation;
    feedback(output, 'Ouverture de la caméra…'); text($('camera-state'), 'Démarrage');
    try {
      if (!await camera.start() || ticket !== generation) return;
      active = true; text($('camera-state'), 'Active'); feedback(output, 'Analyse en cours. Le premier contrôle peut prendre quelques secondes.');
      await processFrame(ticket);
    } catch (error) {if (ticket === generation) {finish(); feedback(output, cameraError(error), 'error');}}
  });
  stop.addEventListener('click', () => finish());
  $('refresh-attendance').addEventListener('click', refreshRecent);
  window.addEventListener('pagehide', () => {recentSequence++; finish();});
  window.addEventListener('pageshow', event => {if (event.persisted) api.refreshSession().then(refreshRecent).catch(error => feedback(output, error.message, 'error'));});
  refreshRecent();
}
function initCreateUserPage() {
  const video = $('register-video'), start = $('start-camera-btn'), stop = $('stop-camera-btn'), capture = $('capture-user-btn'), form = $('create-user-form');
  if (!video || !form) return;
  let generation = 0, saveGeneration = 0, usersSequence = 0, saving = false, saveRequest = null, deleteTarget = null, deleting = false;
  const output = $('register-result'), dialog = $('delete-dialog');
  const camera = makeCamera(video, $('register-placeholder'), () => stopCamera('La caméra a été déconnectée.'));
  function stopCamera(message = 'Caméra arrêtée. Vous pouvez la réactiver pour une nouvelle référence.') {
    generation++; camera.stop(); start.disabled = false; stop.disabled = true; capture.disabled = true;
    if (!saving) feedback(output, message);
  }
  async function refreshUsers() {
    const ticket = ++usersSequence;
    const button = $('refresh-users'); button.disabled = true;
    try {
      const data = await request('/api/users'), users = data.users || [], holder = $('users-list');
      if (ticket !== usersSequence) return;
      if (!users.length) {emptyList(holder, 'Aucun profil enregistré. Ajoutez votre première référence ci-dessus.'); return;}
      holder.replaceChildren(...users.map(user => {
        const item = element('li', ''), detail = element('div', ''), remove = element('button', 'Supprimer', 'btn secondary compact');
        detail.append(element('strong', user.name || 'Profil'));
        detail.append(element('div', [user.user_id, user.designation].filter(Boolean).join(' · ') || 'Profil de démonstration', 'user-detail'));
        remove.type = 'button'; remove.setAttribute('aria-label', 'Supprimer le profil ' + (user.name || ''));
        remove.addEventListener('click', () => {
          deleteTarget = user; text($('delete-profile-name'), user.name || 'Profil');
          $('delete-dialog-error').classList.add('hidden'); dialog.showModal();
        });
        item.append(detail, remove); return item;
      }));
    } catch (error) {if (ticket === usersSequence) feedback($('delete-result'), error.message, 'error');}
    finally {if (ticket === usersSequence) button.disabled = false;}
  }
  start.addEventListener('click', async () => {
    start.disabled = true; stop.disabled = false; const ticket = ++generation; feedback(output, 'Ouverture de la caméra…');
    try {
      if (!await camera.start() || ticket !== generation) return;
      capture.disabled = false; feedback(output, 'Visage centré, puis Capturer et enregistrer. La photo n’est pas encore sauvegardée.');
    } catch (error) {if (ticket === generation) {stopCamera(); feedback(output, cameraError(error), 'error');}}
  });
  stop.addEventListener('click', () => stopCamera());
  form.addEventListener('submit', event => event.preventDefault());
  capture.addEventListener('click', async () => {
    if (saving || !form.reportValidity()) return;
    if (!camera.ready()) {feedback(output, 'La caméra n’est pas encore prête.', 'error'); return;}
    let frame;
    try {frame = captureFrame(video);} catch (error) {feedback(output, error.message, 'error'); return;}
    const body = {name: form.elements.namedItem('name').value, id: form.elements.namedItem('id').value,
      designation: form.elements.namedItem('designation').value, frame};
    saving = true; capture.disabled = true; form.setAttribute('aria-busy', 'true');
    const controller = new AbortController(); saveRequest = controller; const ticket = saveGeneration;
    feedback(output, 'Enregistrement de la référence…');
    try {
      const result = await request('/api/register_user', {method: 'POST', body, signal: controller.signal});
      if (!result.success) throw new Error(result.error || 'Le profil n’a pas pu être enregistré.');
      if (ticket !== saveGeneration) return;
      feedback(output, 'Profil ' + result.user.name + ' enregistré dans votre espace.', 'success');
      form.reset(); await refreshUsers();
    } catch (error) {if (!controller.signal.aborted && ticket === saveGeneration) feedback(output, error.message, 'error');}
    finally {saving = false; saveRequest = null; capture.disabled = !camera.ready(); form.removeAttribute('aria-busy');}
  });
  $('confirm-delete').addEventListener('click', async () => {
    if (!deleteTarget || deleting) return;
    deleting = true; $('confirm-delete').disabled = true; $('cancel-delete').disabled = true;
    try {
      await request('/api/users/' + encodeURIComponent(deleteTarget.key), {method: 'DELETE'});
      dialog.close(); feedback($('delete-result'), 'Profil, référence et pointages associés supprimés.', 'success');
      await refreshUsers();
    } catch (error) {feedback($('delete-dialog-error'), error.message, 'error');}
    finally {deleting = false; $('confirm-delete').disabled = false; $('cancel-delete').disabled = false;}
  });
  dialog.addEventListener('cancel', event => {if (deleting) event.preventDefault();});
  dialog.addEventListener('close', () => {deleteTarget = null;});
  $('refresh-users').addEventListener('click', refreshUsers);
  window.addEventListener('pagehide', () => {usersSequence++; saveGeneration++; saveRequest?.abort(); stopCamera();});
  window.addEventListener('pageshow', event => {if (event.persisted) api.refreshSession().then(refreshUsers).catch(error => feedback(output, error.message, 'error'));});
  refreshUsers();
}
async function initHomePage() {
  if (!$('health-summary')) return;
  try {
    const [health, ownUsers] = await Promise.all([request('/health'), request('/api/users')]);
    text($('home-user-count'), String((ownUsers.users || []).length));
    text($('health-summary'), health.full_recognition_available ? 'Encodage facial' : 'OpenCV');
    text($('storage-summary'), health.storage === 'private-vercel-blob' ? 'Stockage privé' : 'Sur cet appareil');
  } catch (error) {text($('health-summary'), 'Indisponible'); text($('storage-summary'), 'À vérifier'); feedback($('workspace-status'), error.message, 'error');}
}
async function init() {
  try {
    await api.session(); text($('workspace-status'), 'Votre espace est prêt · visible dans ce navigateur uniquement');
    initCreateUserPage(); initAttendancePage(); await initHomePage();
  } catch (error) {text($('workspace-status'), error.message); $('workspace-status')?.classList.add('error');}
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, {once: true}); else init();
