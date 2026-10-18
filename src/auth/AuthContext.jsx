import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import * as api from "../api";
import AuthModal from "./AuthModal";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  const [modal, setModal] = useState(null); // { mode, role, reason } | null

  useEffect(() => {
    if (!api.getToken()) { setReady(true); return; }
    api.fetchMe().then(setUser).catch(() => api.setToken(null)).finally(() => setReady(true));
  }, []);

  useEffect(() => {
    const onLogout = () => setUser(null);
    window.addEventListener("bari:logout", onLogout);
    return () => window.removeEventListener("bari:logout", onLogout);
  }, []);

  const finish = useCallback(({ access_token, user }) => {
    api.setToken(access_token);
    setUser(user);
    setModal(null);
    return user;
  }, []);

  const value = useMemo(() => ({
    user,
    ready,
    login: async (email, password) => finish(await api.login(email, password)),
    signup: async (data) => finish(await api.signup(data)),
    logout: () => { api.setToken(null); setUser(null); },
    openAuth: (opts = {}) => setModal({ mode: "login", role: "renter", ...opts }),
  }), [user, ready, finish]);

  return (
    <AuthContext.Provider value={value}>
      {children}
      {modal && <AuthModal {...modal} onClose={() => setModal(null)} />}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
