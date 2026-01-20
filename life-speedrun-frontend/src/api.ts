// src/api.ts
const API_BASE = 'http://localhost:8000';

// src/api.ts → замени handleResponse
const handleResponse = async (res: Response) => {
  // Логируем для отладки
  console.log('API Response:', res.status, res.statusText, res.url);
  
  if (!res.ok) {
    let errorData = { message: `HTTP ${res.status}`, detail: '' };
    try {
      // Пытаемся распарсить как JSON
      const json = await res.json();
      errorData = {
        message: json.detail || json.msg || json.error || `HTTP ${res.status}`,
        detail: JSON.stringify(json, null, 2)
      };
    } catch (jsonError) {
      // Если не JSON - читаем текст
      try {
        errorData.message = await res.text() || `HTTP ${res.status} (No response body)`;
      } catch (textError) {
        errorData.message = `HTTP ${res.status} (Failed to read response)`;
      }
    }
    
    console.error('API Error Details:', errorData);
    const error = new Error(errorData.message);
    (error as any).detail = errorData.detail;
    throw error;
  }
  
  // Успешный ответ - пытаемся распарсить как JSON
  try {
    return await res.json();
  } catch (jsonError) {
    console.warn('Response is not JSON, returning as text:', jsonError);
    try {
      return await res.text();
    } catch {
      return null;
    }
  }
};

export const api = {
  // Auth
  register: (email: string, password: string) => 
  fetch(`${API_BASE}/register`, {
    method: 'POST',
    headers: { 
      'Content-Type': 'application/json'  // ← ДОЛЖНО БЫТЬ ТОЧНО ТАК
    },
    body: JSON.stringify({ email, password })
  }).then(handleResponse),

  verify: (email: string, code: string) =>
    fetch(`${API_BASE}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, code })
    }).then(handleResponse),

  login: (email: string, password: string) => {
  const formData = new URLSearchParams();
  // Отправляем email как username (OAuth2 требует username)
  formData.append('username', email);  // ← КРИТИЧНО: username вместо email
  formData.append('password', password);
  return fetch(`${API_BASE}/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData.toString()
  }).then(handleResponse);
},
  me: (token: string) =>
    fetch(`${API_BASE}/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(handleResponse),

  // Events
  createEvent: (token: string, event: {
    title: string;
    startTime: string;
    endTime: string;
    date: string;
    isRange: boolean;
    isRecurring: boolean;
    recurrenceDays: number;
    reminder: boolean;
    reminderMinutes: number;
    color: string;
    description: string | null;
    tags: number[];
  }) =>
    fetch(`${API_BASE}/events`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(event)
    }).then(handleResponse),

  getEvents: (token: string, date: string) =>
    fetch(`${API_BASE}/events?date=${date}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(handleResponse),

  // Token helpers
  setToken: (token: string) => localStorage.setItem('jwt_token', token),
  getToken: () => localStorage.getItem('jwt_token'),
  clearToken: () => localStorage.removeItem('jwt_token'),

  startTimer: (token: string, eventId: number) => 
    fetch(`${API_BASE}/events/${eventId}/start`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(handleResponse),

  stopTimer: (token: string, eventId: number) => 
    fetch(`${API_BASE}/events/${eventId}/stop`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(handleResponse),

  getStats: (token: string) => 
    fetch(`${API_BASE}/events/stats`, {
      headers: { 'Authorization': `Bearer ${token}` }
    }).then(handleResponse)
};