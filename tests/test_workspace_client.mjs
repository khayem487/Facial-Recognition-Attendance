import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createWorkspaceClient, captureSize, similarityLabel, cameraError} from '../static/workspace-client.mjs';

const reply = (body, ok = true) => ({ok, json: async () => body});
test('concurrent writes share one session bootstrap and carry CSRF without exposing a cookie', async () => {
  const calls = [];
  const client = createWorkspaceClient(async (path, options) => {
    calls.push({path, options});
    return reply(path === '/api/session' ? {csrf_token: 'TEST-DERIVED-CSRF', isolation: 'browser'} : {success: true});
  });
  await Promise.all([client.request('/api/register_user', {method: 'POST', body: {name: 'TEST'}}),
    client.request('/api/users/TEST', {method: 'DELETE'})]);
  assert.equal(calls.filter(call => call.path === '/api/session').length, 1);
  for (const call of calls) {
    assert.equal(call.options.credentials, 'same-origin'); assert.equal(call.options.cache, 'no-store');
    assert.equal(call.options.headers?.Cookie, undefined);
    if (call.path !== '/api/session') assert.equal(call.options.headers['X-CSRF-Token'], 'TEST-DERIVED-CSRF');
  }
  assert.equal(JSON.parse(calls.find(call => call.path === '/api/register_user').options.body).name, 'TEST');
});
test('invalid or failed sessions block writes and a later bootstrap can recover', async () => {
  let attempt = 0, writes = 0;
  const client = createWorkspaceClient(async path => {
    if (path !== '/api/session') {writes++; return reply({success: true});}
    attempt++;
    if (attempt === 1) return reply({csrf_token: 'TEST', isolation: 'shared'});
    if (attempt === 2) throw new Error('TEST offline');
    return reply({csrf_token: 'TEST', isolation: 'browser'});
  });
  await assert.rejects(client.request('/api/users/TEST', {method: 'DELETE'}));
  await assert.rejects(client.request('/api/users/TEST', {method: 'DELETE'}));
  assert.equal(writes, 0);
  await client.request('/api/users/TEST', {method: 'DELETE'}); assert.equal(writes, 1);
});
test('write failures never trigger an automatic duplicate write and unreadable server responses fail clearly', async () => {
  let writes = 0;
  const client = createWorkspaceClient(async path => {
    if (path === '/api/session') return reply({csrf_token: 'TEST', isolation: 'browser'});
    writes++; return reply({error: 'TEST validation rejected'}, false);
  });
  await assert.rejects(client.request('/api/register_user', {method: 'POST', body: {name: 'TEST'}}), /validation rejected/);
  assert.equal(writes, 1);
  const broken = createWorkspaceClient(async () => ({ok: false, json: async () => {throw new SyntaxError();}}));
  await assert.rejects(broken.session(), /ne répond pas normalement/);
});
test('camera frames stay within 1280x720 without enlarging or distorting dimensions', () => {
  assert.deepEqual(captureSize(3840, 2160), {width: 1280, height: 720});
  assert.deepEqual(captureSize(2160, 3840), {width: 405, height: 720});
  assert.deepEqual(captureSize(320, 240), {width: 320, height: 240});
  for (const [w, h] of [[0, 720], [1280, 0], [NaN, 1], [Infinity, 720], [-1, 720]])
    assert.throws(() => captureSize(w, h), /pas encore prête/);
});
test('session bootstrap times out and back-navigation refresh replaces its derived token', async () => {
  const hung = createWorkspaceClient((path, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('TEST aborted')), {once: true});
  }), {sessionTimeoutMs: 5});
  await assert.rejects(hung.session(), /trop de temps/);
  let version = 0, writtenToken;
  const client = createWorkspaceClient(async (path, options) => {
    if (path === '/api/session') return reply({csrf_token: 'TEST-' + ++version, isolation: 'browser'});
    writtenToken = options.headers['X-CSRF-Token']; return reply({success: true});
  });
  await client.session(); await client.refreshSession();
  await client.request('/api/users/TEST', {method: 'DELETE'});
  assert.equal(writtenToken, 'TEST-2');
});
test('similarity never invents a percentage for an absent, string or invalid score', () => {
  assert.equal(similarityLabel(.853), '85 / 100'); assert.equal(similarityLabel(0), '0 / 100');
  for (const value of [undefined, null, NaN, Infinity, -1, 1.1, '.85']) assert.equal(similarityLabel(value), '—');
});
test('permission denied, missing and busy cameras have actionable separate messages', () => {
  assert.match(cameraError({name: 'NotAllowedError'}), /refusé/);
  assert.match(cameraError({name: 'NotFoundError'}), /Aucune caméra/);
  assert.match(cameraError({name: 'NotReadableError'}), /déjà utilisée/);
});
