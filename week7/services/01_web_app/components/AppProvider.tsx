"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  api,
  body,
  accountEpoch,
  invalidateAccount,
  isCancelled,
} from "../lib/api";
import { ChatEntry, ChatResult, Session, User } from "../lib/types";
import { TeamKey, browseClubs, teamFromId, teams } from "../lib/teams";

function useAppState() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);
  const [authError, setAuthError] = useState<Error>();
  const [teamKey, setTeamKey] = useState<TeamKey>(teams[0].key);
  const [browsingKey, setBrowsingKey] = useState<string>(teams[0].key);
  const [loggingOut, setLoggingOut] = useState(false);
  const logoutTask = useRef<Promise<void> | null>(null);
  const [teamError, setTeamError] = useState<Error>();
  const [historyTarget, setHistoryTarget] = useState<string | null>(null);
  const historyTargetRef = useRef<string | null>(null);
  const [teamBusy, setTeamBusy] = useState(false);
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState<Error>();
  const [historyError, setHistoryError] = useState<Error>();
  const [draft, setDraft] = useState("");
  const [openSignal, setOpenSignal] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const identity = useRef<string | null>(null);
  const busy = useRef(false);
  const preferenceBusy = useRef(false);
  const conversation = useRef(0);
  const team = teams.find((item) => item.key === teamKey) ?? teams[0];
  const browsingTeam =
    browseClubs.find((item) => item.key === browsingKey) ?? browseClubs[0];

  const clearAccount = useCallback(() => {
    invalidateAccount();
    conversation.current++;
    identity.current = null;
    busy.current = false;
    preferenceBusy.current = false;
    setUser(null);
    setTeamKey(teams[0].key);
    setBrowsingKey(teams[0].key);
    setOpenSignal(0);
    setSettingsOpen(false);
    setEntries([]);
    setSessions([]);
    setSessionId(null);
    setPending(false);
    setHistoryLoading(false);
    historyTargetRef.current = null;
    setHistoryTarget(null);
    setTeamBusy(false);
    setTeamError(undefined);
    setDraft("");
    setError(undefined);
    setHistoryError(undefined);
    setAuthError(undefined);
  }, []);

  const refreshSessions = useCallback(async () => {
    const epoch = accountEpoch();
    try {
      const data = await api<{ sessions: Session[] }>("/sessions");
      setSessions(data.sessions);
      setHistoryError(undefined);
    } catch (error) {
      if (epoch === accountEpoch() && !isCancelled(error))
        setHistoryError(error as Error);
    }
  }, []);

  const acceptUser = useCallback(
    (next: User) => {
      const changed = identity.current !== next.id;
      if (changed) clearAccount();
      identity.current = next.id;
      setUser(next);
      const favorite = teamFromId(next.favorite_team_id);
      setTeamKey(favorite?.key ?? teams[0].key);
      if (changed) setBrowsingKey(favorite?.key ?? teams[0].key);
      setAuthError(undefined);
      setChecked(true);
      void refreshSessions();
    },
    [clearAccount, refreshSessions],
  );

  const checkAuth = useCallback(
    async (signal?: AbortSignal) => {
      if (logoutTask.current) return;
      setAuthError(undefined);
      try {
        const data = await api<{ user: User }>("/auth/me", { signal });
        if (!signal?.aborted) acceptUser(data.user);
      } catch (error) {
        if (!signal?.aborted && !isCancelled(error)) {
          if ((error as { status?: number }).status !== 401)
            setAuthError(error as Error);
        }
      } finally {
        if (!signal?.aborted) setChecked(true);
      }
    },
    [acceptUser],
  );

  useEffect(() => {
    const controller = new AbortController();
    const expire = () => {
      clearAccount();
      setChecked(true);
      router.replace("/login?expired=1");
    };
    window.addEventListener("pitchside:expired", expire);
    void checkAuth(controller.signal);
    return () => {
      controller.abort();
      window.removeEventListener("pitchside:expired", expire);
    };
  }, [checkAuth, clearAccount, router]);

  async function login(username: string, password: string) {
    if (logoutTask.current) await logoutTask.current;
    const data = await api<{ user: User }>(
      "/auth/login",
      body({ username, password }),
    );
    acceptUser(data.user);
    router.replace("/");
  }
  async function register(
    username: string,
    displayName: string,
    password: string,
  ) {
    if (logoutTask.current) await logoutTask.current;
    const data = await api<{ user: User }>(
      "/auth/register",
      body({ username, display_name: displayName, password }),
    );
    acceptUser(data.user);
    router.replace("/");
  }
  function logout(): Promise<void> {
    if (logoutTask.current) return logoutTask.current;
    clearAccount();
    setLoggingOut(true);
    const task = (async () => {
      try {
        await api("/auth/logout", { method: "POST" });
      } catch (error) {
        if (!isCancelled(error)) setAuthError(error as Error);
      } finally {
        router.replace("/login");
        setLoggingOut(false);
        logoutTask.current = null;
      }
    })();
    logoutTask.current = task;
    return task;
  }
  function newChat() {
    conversation.current++;
    busy.current = false;
    setPending(false);
    setHistoryLoading(false);
    historyTargetRef.current = null;
    setHistoryTarget(null);
    setEntries([]);
    setSessionId(null);
    setDraft("");
    setError(undefined);
  }
  async function selectSession(id: string) {
    const ticket = ++conversation.current;
    busy.current = false;
    setPending(false);
    setHistoryLoading(true);
    setError(undefined);
    setEntries([]);
    setDraft("");
    setSessionId(null);
    historyTargetRef.current = id;
    setHistoryTarget(id);
    try {
      const data = await api<{
        messages: (Omit<ChatEntry, "id"> & { message_id: string })[];
      }>("/history/" + encodeURIComponent(id));
      if (ticket === conversation.current) {
        setSessionId(id);
        historyTargetRef.current = null;
        setHistoryTarget(null);
        setEntries(
          data.messages.map((item) => ({ ...item, id: item.message_id })),
        );
      }
    } catch (error) {
      if (ticket === conversation.current && !isCancelled(error)) {
        if (error instanceof ApiError && error.status === 404) {
          historyTargetRef.current = null;
          setHistoryTarget(null);
          setError(
            new Error("ไม่พบบทสนทนานี้ กรุณาเริ่มแชทใหม่หรือเลือกบทสนทนาอื่น"),
          );
          void refreshSessions();
        } else setError(error as Error);
      }
    } finally {
      if (ticket === conversation.current) setHistoryLoading(false);
    }
  }
  async function changeTeam(key: TeamKey) {
    const next = teams.find((item) => item.key === key)!;
    if (
      preferenceBusy.current ||
      busy.current ||
      (key === teamKey && (!user || user.favorite_team_id === next.teamId))
    )
      return false;
    if (!user) {
      setTeamKey(key);
      return true;
    }
    const epoch = accountEpoch();
    preferenceBusy.current = true;
    setTeamBusy(true);
    setTeamError(undefined);
    try {
      const data = await api<{ user: User }>("/me/preferences", {
        method: "PATCH",
        body: JSON.stringify({ favorite_team_id: next.teamId }),
      });
      setUser(data.user);
      setTeamKey(key);
      return true;
    } catch (error) {
      if (epoch === accountEpoch() && !isCancelled(error))
        setTeamError(error as Error);
      return false;
    } finally {
      if (epoch === accountEpoch()) {
        preferenceBusy.current = false;
        setTeamBusy(false);
      }
    }
  }
  async function sendQuestion(question: string) {
    const message = question.trim();
    if (
      !user ||
      busy.current ||
      preferenceBusy.current ||
      historyTargetRef.current !== null ||
      loggingOut ||
      !message ||
      message.length > 2000
    )
      return false;
    const epoch = accountEpoch(),
      ticket = conversation.current;
    busy.current = true;
    setPending(true);
    setError(undefined);
    const optimisticId = crypto.randomUUID();
    setEntries((current) => [
      ...current,
      { id: optimisticId, role: "user", content: message },
    ]);
    try {
      const result = await api<ChatResult>(
        "/chat",
        body({ session_id: sessionId, message }),
      );
      if (epoch !== accountEpoch() || ticket !== conversation.current)
        return false;
      setSessionId(result.session_id);
      setEntries((current) => [
        ...current,
        {
          ...result,
          id: result.message_id,
          role: "assistant",
          content: result.answer,
        },
      ]);
      setDraft((current) => (current === question ? "" : current));
      void refreshSessions();
      return true;
    } catch (error) {
      if (
        epoch === accountEpoch() &&
        ticket === conversation.current &&
        !isCancelled(error)
      ) {
        setError(error as Error);
        setEntries((current) =>
          current.filter((item) => item.id !== optimisticId),
        );
      }
      return false;
    } finally {
      if (epoch === accountEpoch() && ticket === conversation.current) {
        busy.current = false;
        setPending(false);
      }
    }
  }
  function ask(prompt = "") {
    if (prompt) setDraft(prompt);
    setOpenSignal((current) => current + 1);
  }
  function updateRating(id: string, rating: number) {
    setEntries((current) =>
      current.map((item) => (item.id === id ? { ...item, rating } : item)),
    );
  }
  return {
    user,
    checked,
    authError,
    checkAuth,
    team,
    browsingTeam,
    browseTeam: setBrowsingKey,
    teamBusy,
    teamError,
    loggingOut,
    changeTeam,
    login,
    register,
    logout,
    entries,
    sessions,
    sessionId,
    selectSession,
    newChat,
    pending,
    historyLoading,
    historyTarget,
    error,
    historyError,
    refreshSessions,
    draft,
    setDraft,
    sendQuestion,
    openSignal,
    settingsOpen,
    setSettingsOpen,
    ask,
    updateRating,
  };
}
type AppState = ReturnType<typeof useAppState>;
const Context = createContext<AppState | null>(null);
export function AppProvider({ children }: { children: React.ReactNode }) {
  const value = useAppState();
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useApp() {
  const value = useContext(Context);
  if (!value) throw new Error("AppProvider required");
  return value;
}
