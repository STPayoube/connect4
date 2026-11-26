const API_BASE = import.meta.env.VITE_API_BASE || '/api';

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
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
          : `Request failed with status ${res.status}`;
    throw new ApiError(detail, res.status);
  }

  return data;
}

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

export function adminDeleteSession(token, sessionId) {
  return request(`/admin/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getAdminStreamUrl(token) {
  return `${API_BASE}/admin/stream?token=${encodeURIComponent(token)}`;
}
