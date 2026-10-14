"use client";
import { useEffect, useState } from "react";
import { api, isCancelled } from "./api";
export function useRemote<T>(path: string | null, revision = 0) {
  const [state, setState] = useState<{
    data?: T;
    error?: Error;
    loading: boolean;
    path: string | null;
  }>({ loading: !!path, path });
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: !!path, path });
    if (path)
      void api<T>(path, { signal: controller.signal })
        .then((data) => {
          if (!controller.signal.aborted)
            setState({ data, loading: false, path });
        })
        .catch((error) => {
          if (!controller.signal.aborted && !isCancelled(error))
            setState({ error, loading: false, path });
        });
    return () => controller.abort();
  }, [path, revision]);
  return state.path === path
    ? state
    : { data: undefined, error: undefined, loading: !!path };
}
