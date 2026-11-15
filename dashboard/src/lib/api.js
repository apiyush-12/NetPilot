export const API_BASE =
  import.meta.env.VITE_NETPILOT_API_BASE || "http://127.0.0.1:8000";

// Clerk authentication token getter
let getClerkToken = null;

export function setClerkTokenGetter(getToken) {
  getClerkToken = getToken;
}

// Attach Clerk session token to backend requests
async function clerkHeaders() {
  const sessionToken = await getClerkToken?.();

  if (!sessionToken) {
    throw new Error("Sign in to NetPilot to access the API");
  }

  return {
    Authorization: `Bearer ${sessionToken}`,
  };
}



// GET requests
export async function apiGet(path, signal) {
  const response = await fetch(`${API_BASE}${path}`, {
    signal,
    cache: "no-store",
    headers: await clerkHeaders(),
  });

  if (!response.ok) {
    throw new Error(`GET ${path}: HTTP ${response.status}`);
  }

  return response.json();
}

// POST requests with NetPilot control token
export async function apiPost(path, token) {
  if (!token) {
    throw new Error(
      "Unlock controls with your temporary local control token first.",
    );
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      ...(await clerkHeaders()),
      "X-NetPilot-Token": token,
    },
    cache: "no-store",
  });

  let body = null;

  try {
    body = await response.json();
  } catch {
    // Response may be empty
  }

  if (!response.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : `HTTP ${response.status}`;

    throw new Error(detail);
  }

  return body;
}

// POST requests with JSON payload
export async function apiPostJson(path, token, payload) {
  if (!token) {
    throw new Error(
      "Unlock controls using your NetPilot token first.",
    );
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      ...(await clerkHeaders()),
      "Content-Type": "application/json",
      "X-NetPilot-Token": token,
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  let data = null;

  try {
    data = await response.json();
  } catch {
    // The backend may return an empty response
  }

  if (!response.ok) {
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : `AI request failed: HTTP ${response.status}`,
    );
  }

  return data;
}
export async function authorizedFetch(input, options = {}) {
  const headers = new Headers(options.headers);
  const auth = await clerkHeaders();

  headers.set("Authorization", auth.Authorization);

  return fetch(input, {
    ...options,
    headers,
  });
}