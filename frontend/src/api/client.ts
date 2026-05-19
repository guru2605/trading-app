import axios from "axios";

const client = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      window.dispatchEvent(new CustomEvent("kite-auth-expired"));
    }
    return Promise.reject(error);
  },
);

export async function fetchAuthStatus(): Promise<boolean> {
  const { data } = await client.get<{ authenticated: boolean }>("/auth/status");
  return data.authenticated;
}

export default client;
