const API_BASE = window.pharmacare?.apiBase || "http://127.0.0.1:8000/api/v1";
const TOKEN_KEY = "pharmacare_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(path, options = {}) {
  const { body, form, ...rest } = options;
  const token = getToken();
  const headers = {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(rest.headers || {}),
  };
  if (!form) headers["Content-Type"] = "application/json";
  const response = await fetch(`${API_BASE}${path}`, {
    headers,
    ...rest,
    body: form || (body ? JSON.stringify(body) : undefined),
  });

  if (response.status === 204) return null;

  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && !path.startsWith("/auth/login")) {
    setToken("");
    window.dispatchEvent(new Event("pharmacare-unauthorized"));
  }
  if (!response.ok) {
    const message = data.detail || data.message || `Request failed (${response.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data;
}

export const api = {
  login: (username, password) => request("/auth/login", { method: "POST", body: { username, password } }),
  me: () => request("/auth/me"),
  logout: () => request("/auth/logout", { method: "POST" }),
  pharmacies: () => request("/pharmacies/"),
  dashboard: (pharmacyId) => request(`/dashboard/?pharmacy_id=${pharmacyId}`),
  medicines: (pharmacyId, { search = "", lowStock = false } = {}) => {
    const params = new URLSearchParams({ pharmacy_id: pharmacyId });
    if (search) params.set("search", search);
    if (lowStock) params.set("low_stock", "true");
    return request(`/inventory/medicines?${params}`);
  },
  createMedicine: (body) => request("/inventory/medicines", { method: "POST", body }),
  importMedicines: (pharmacyId, file) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/inventory/medicines/import?pharmacy_id=${pharmacyId}`, { method: "POST", form });
  },
  updateMedicine: (id, body) => request(`/inventory/medicines/${id}`, { method: "PUT", body }),
  deleteMedicine: (id) => request(`/inventory/medicines/${id}`, { method: "DELETE" }),
  addBatch: (medicineId, body) => request(`/inventory/medicines/${medicineId}/batches`, { method: "POST", body }),
  adjustBatch: (batchId, quantityDelta) =>
    request(`/inventory/batches/${batchId}/adjust`, { method: "POST", body: { quantity_delta: quantityDelta } }),
  patients: (pharmacyId, search = "") => {
    const params = new URLSearchParams({ pharmacy_id: pharmacyId });
    if (search) params.set("search", search);
    return request(`/patients/?${params}`);
  },
  patient: (id) => request(`/patients/${id}`),
  createPatient: (body) => request("/patients/", { method: "POST", body }),
  updatePatient: (id, body) => request(`/patients/${id}`, { method: "PUT", body }),
  prescriptions: (pharmacyId, { patientId, status } = {}) => {
    const params = new URLSearchParams({ pharmacy_id: pharmacyId });
    if (patientId) params.set("patient_id", patientId);
    if (status) params.set("status", status);
    return request(`/prescriptions/?${params}`);
  },
  prescription: (id) => request(`/prescriptions/${id}`),
  createPrescription: (body) => request("/prescriptions/", { method: "POST", body }),
  dispense: (id) => request(`/prescriptions/${id}/dispense`, { method: "POST" }),
  cancel: (id) => request(`/prescriptions/${id}/cancel`, { method: "POST" }),
};
