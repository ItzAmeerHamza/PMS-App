import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "../api/client";

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
  const [staff, setStaff] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    function onUnauthorized() {
      setStaff(null);
      setReady(true);
    }
    window.addEventListener("pharmacare-unauthorized", onUnauthorized);
    if (!getToken()) {
      setReady(true);
      return () => window.removeEventListener("pharmacare-unauthorized", onUnauthorized);
    }
    api
      .me()
      .then(setStaff)
      .catch(() => {
        setToken("");
        setStaff(null);
      })
      .finally(() => setReady(true));
    return () => window.removeEventListener("pharmacare-unauthorized", onUnauthorized);
  }, []);

  async function login(username, password) {
    const session = await api.login(username, password);
    setToken(session.token);
    setStaff(session);
    return session;
  }

  async function logout() {
    try {
      await api.logout();
    } catch {
      setToken("");
    }
    setToken("");
    setStaff(null);
  }

  return <SessionContext.Provider value={{ staff, ready, login, logout }}>{children}</SessionContext.Provider>;
}

export function useSession() {
  return useContext(SessionContext);
}
