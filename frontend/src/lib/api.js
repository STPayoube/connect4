const API_BASE = import.meta.env.VITE_API_BASE || '/api';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request(path, options = {}) {
  const { headers: extraHeaders, ...restOptions } = options;
  const res = await fetch(`${API_BASE}${path}`, {
    ...restOptions,
    headers: {
      'Content-Type': 'application/json',
      ...(extraHeaders || {}),
    },
  });

  if (res.status === 204) {
    return null;
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) {
    const detail =
      typeof data?.detail === 'string'
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((d) => d.msg).join(', ')
          : `Erreur serveur (${res.status})`;
    throw new ApiError(detail, res.status);
  }

  return data;
}

function buildWsUrl(wsPath) {
  if (typeof window === 'undefined') return '';
  if (API_BASE.startsWith('http://') || API_BASE.startsWith('https://')) {
    return `${API_BASE.replace(/^http/, 'ws')}${wsPath}`;
  }
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}${API_BASE}${wsPath}`;
}

export function getGameWsUrl(sessionId) {
  return buildWsUrl(`/ws/games/${encodeURIComponent(sessionId)}`);
}

export function getRoomWsUrl(code) {
  return buildWsUrl(`/ws/rooms/${encodeURIComponent(code)}`);
}

export function getAdminWsUrl(token) {
  return buildWsUrl(`/ws/admin?token=${encodeURIComponent(token)}`);
}

// --- Standard Games ---

export function createGame(config, signal) {
  return request('/games', {
    method: 'POST',
    body: JSON.stringify(config),
    signal,
  });
}

export function getGame(sessionId, signal) {
  return request(`/games/${encodeURIComponent(sessionId)}`, {
    method: 'GET',
    signal,
  });
}

export function resetGame(sessionId, overrides = {}, signal) {
  return request(`/games/${encodeURIComponent(sessionId)}/reset`, {
    method: 'POST',
    body: JSON.stringify(overrides),
    signal,
  });
}

export function playHumanMove(sessionId, col, autoAiReply = false, signal) {
  return request(`/games/${encodeURIComponent(sessionId)}/move`, {
    method: 'POST',
    body: JSON.stringify({ col, auto_ai_reply: autoAiReply }),
    signal,
  });
}

export function stepAiMove(sessionId, signal) {
  return request(`/games/${encodeURIComponent(sessionId)}/ai-move`, {
    method: 'POST',
    signal,
  });
}

export function undoMove(sessionId, signal) {
  return request(`/games/${encodeURIComponent(sessionId)}/undo`, {
    method: 'POST',
    signal,
  });
}

export function deleteGame(sessionId) {
  return request(`/games/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });
}

// --- Win a Prize ---

export function getWinAPrizeConfig(signal) {
  return request('/winaprize/config', { method: 'GET', signal });
}

export function createWinAPrizeGame(username, signal) {
  return request('/winaprize/games', {
    method: 'POST',
    body: JSON.stringify({ username, auto_play_opening_ai: false }),
    signal,
  });
}

// --- Online Friend Rooms (/game#XXXXXX) ---

export function createRoom(payload, signal) {
  return request('/rooms', {
    method: 'POST',
    body: JSON.stringify(payload),
    signal,
  });
}

export function getRoom(code, signal) {
  return request(`/rooms/${encodeURIComponent(code)}`, { method: 'GET', signal });
}

export function joinRoom(code, username, signal) {
  return request(`/rooms/${encodeURIComponent(code)}/join`, {
    method: 'POST',
    body: JSON.stringify({ username }),
    signal,
  });
}

export function playRoomMove(code, col, playerToken, signal) {
  return request(`/rooms/${encodeURIComponent(code)}/move`, {
    method: 'POST',
    body: JSON.stringify({ col, player_token: playerToken }),
    signal,
  });
}

export function rematchRoom(code, playerToken, randomStart = false, signal) {
  return request(`/rooms/${encodeURIComponent(code)}/rematch`, {
    method: 'POST',
    body: JSON.stringify({ player_token: playerToken, random_start: randomStart }),
    signal,
  });
}

export function getRoomStreamUrl(code) {
  return `${API_BASE}/rooms/${encodeURIComponent(code)}/stream`;
}

// --- Admin API ---

export function adminLogin(password) {
  return request('/admin/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
}

export function adminLogout(token) {
  return request('/admin/logout', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminListSessions(token) {
  return request('/admin/sessions', {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminUpdateSessionDifficulty(token, sessionId, aiLevel, ai2Level = null) {
  return request(`/admin/sessions/${encodeURIComponent(sessionId)}/difficulty`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ ai_level: aiLevel, ...(ai2Level ? { ai2_level: ai2Level } : {}) }),
  });
}

export function adminUpdateSessionLiveConfig(token, sessionId, config) {
  return request(`/admin/sessions/${encodeURIComponent(sessionId)}/live-config`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(config),
  });
}

export function adminDeleteSession(token, sessionId) {
  return request(`/admin/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminGetWinAPrizeConfig(token) {
  return request('/admin/winaprize/config', {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminUpdateWinAPrizeConfig(token, config) {
  return request('/admin/winaprize/config', {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(config),
  });
}

export function adminGetStats(token) {
  return request('/admin/stats', {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminListHistory(token, params = {}) {
  const qs = new URLSearchParams();
  if (params.channel && params.channel !== 'all') qs.set('channel', params.channel);
  if (params.outcome && params.outcome !== 'all') qs.set('outcome', params.outcome);
  if (params.search) qs.set('search', params.search);
  if (params.limit) qs.set('limit', String(params.limit));
  if (params.offset) qs.set('offset', String(params.offset));
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return request(`/admin/history${suffix}`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminGetHistoryRecord(token, recordId) {
  return request(`/admin/history/${encodeURIComponent(recordId)}`, {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminDeleteHistoryRecord(token, recordId) {
  return request(`/admin/history/${encodeURIComponent(recordId)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminListBlacklist(token) {
  return request('/admin/blacklist', {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function adminAddBlacklist(token, pattern, matchType = 'exact', reason = '') {
  return request('/admin/blacklist', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ pattern, match_type: matchType, reason }),
  });
}

export function adminDeleteBlacklist(token, entryId) {
  return request(`/admin/blacklist/${encodeURIComponent(entryId)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getAdminStreamUrl(token) {
  return `${API_BASE}/admin/stream?token=${encodeURIComponent(token)}`;
}
