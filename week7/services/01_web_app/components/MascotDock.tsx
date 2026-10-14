"use client";
import { PointerEvent, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useApp } from "./AppProvider";
import { ChatPanel } from "./ChatPanel";
import { clampPet, PET_FRAMES, PET_HEIGHT, PET_WIDTH } from "../lib/pet";
export function MascotDock() {
  const app = useApp(),
    path = usePathname();
  const [position, setPosition] = useState<{ x: number; y: number }>();
  const [viewport, setViewport] = useState({ width: 1000, height: 800 });
  const [open, setOpen] = useState(false),
    [dragging, setDragging] = useState(false),
    [left, setLeft] = useState(false),
    [wave, setWave] = useState(false),
    [reduced, setReduced] = useState(false),
    [visible, setVisible] = useState(true),
    [frame, setFrame] = useState(0);
  const button = useRef<HTMLButtonElement>(null);
  const drag = useRef<{
    x: number;
    y: number;
    start: { x: number; y: number };
    moved: boolean;
  }>();
  const suppressClick = useRef(false);
  const row = dragging
    ? left
      ? 2
      : 1
    : app.pending
      ? 7
      : app.error
        ? 5
        : wave
          ? 3
          : 0;
  useEffect(() => {
    let saved: { x: number; y: number } | undefined;
    try {
      saved =
        JSON.parse(
          localStorage.getItem("pitchside-mascot-position") ?? "null",
        ) ?? undefined;
    } catch {
      /* Storage may be unavailable. */
    }
    const resize = () => {
      setViewport({ width: window.innerWidth, height: window.innerHeight });
      setPosition((current) =>
        clampPet(
          current?.x ?? saved?.x ?? window.innerWidth - 175,
          current?.y ?? saved?.y ?? window.innerHeight - 200,
          window.innerWidth,
          window.innerHeight,
        ),
      );
    };
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)"),
      update = () => setReduced(motion.matches),
      visibility = () => setVisible(!document.hidden);
    resize();
    update();
    visibility();
    window.addEventListener("resize", resize);
    motion.addEventListener("change", update);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      window.removeEventListener("resize", resize);
      motion.removeEventListener("change", update);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, []);
  useEffect(() => {
    setFrame(0);
    if (reduced || !visible) return;
    const timer = setInterval(
      () => setFrame((frame) => (frame + 1) % PET_FRAMES[row]),
      row === 7 ? 130 : 170,
    );
    return () => clearInterval(timer);
  }, [row, reduced, visible, app.team.key]);
  useEffect(() => {
    if (!wave) return;
    const timer = setTimeout(() => setWave(false), 1100);
    return () => clearTimeout(timer);
  }, [wave]);
  useEffect(() => {
    if (app.openSignal) setOpen(true);
  }, [app.openSignal]);
  useEffect(() => {
    setOpen(false);
  }, [path]);
  function save(point: { x: number; y: number }) {
    try {
      localStorage.setItem("pitchside-mascot-position", JSON.stringify(point));
    } catch {
      /* Movement still works without persistence. */
    }
  }
  function pointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (!position || event.button !== 0) return;
    suppressClick.current = false;
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      start: position,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function pointerMove(event: PointerEvent<HTMLButtonElement>) {
    const current = drag.current;
    if (!current) return;
    const dx = event.clientX - current.x,
      dy = event.clientY - current.y;
    if (Math.abs(dx) + Math.abs(dy) > 5) current.moved = true;
    if (!current.moved) return;
    setDragging(true);
    setLeft(dx < 0);
    setPosition(
      clampPet(
        current.start.x + dx,
        current.start.y + dy,
        viewport.width,
        viewport.height,
      ),
    );
  }
  function pointerUp(event: PointerEvent<HTMLButtonElement>) {
    suppressClick.current = !!drag.current?.moved;
    drag.current = undefined;
    setDragging(false);
    if (position) save(position);
    if (event.currentTarget.hasPointerCapture(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId);
  }
  if (!position) return null;
  const width = Math.min(420, viewport.width - 24),
    height = Math.min(540, viewport.height - 24);
  const panelLeft = Math.max(
    12,
    Math.min(
      position.x + PET_WIDTH / 2 - width / 2,
      viewport.width - width - 12,
    ),
  );
  const top = Math.max(
    12,
    Math.min(
      position.y >= height + 20
        ? position.y - height - 10
        : position.y + PET_HEIGHT + 10,
      viewport.height - height - 12,
    ),
  );
  return (
    <div className="mascot-layer">
      {open && (
        <section
          role="dialog"
          aria-label="แชทกับมาสคอส"
          className="mascot-chat"
          style={{ left: panelLeft, top, width, height }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setOpen(false);
              button.current?.focus();
            }
          }}
        >
          <header className="panel-heading">
            <div>
              <strong>PANBALL · คุยกับแพนด้า</strong>
              <small>เพื่อนคุยฟุตบอลประจำทีม</small>
            </div>
            <button
              aria-label="ปิดแชทมาสคอส"
              onClick={() => {
                setOpen(false);
                button.current?.focus();
              }}
            >
              <X size={20} />
            </button>
          </header>
          <p className="chat-context">
            ทีมโปรด: {app.team.shortName} · ถามถึงทีมอื่นให้ระบุชื่อทีมในคำถาม
          </p>
          <button className="text-link" onClick={app.newChat}>
            แชทใหม่
          </button>
          <ChatPanel surface="dock" />
        </section>
      )}
      <button
        ref={button}
        className={"mascot-pet" + (dragging ? " dragging" : "")}
        style={{ left: position.x, top: position.y }}
        aria-label={"มาสคอส " + app.team.name + " เปิดแชทหรือลากเพื่อย้าย"}
        aria-expanded={open}
        onPointerDown={pointerDown}
        onPointerMove={pointerMove}
        onPointerUp={pointerUp}
        onPointerCancel={() => {
          drag.current = undefined;
          suppressClick.current = true;
          setDragging(false);
        }}
        onClick={() => {
          if (suppressClick.current) {
            suppressClick.current = false;
            return;
          }
          setOpen((value) => !value);
          setWave(true);
        }}
        onKeyDown={(event) => {
          const moves: Record<string, number[]> = {
            ArrowLeft: [-20, 0],
            ArrowRight: [20, 0],
            ArrowUp: [0, -20],
            ArrowDown: [0, 20],
          };
          const move = moves[event.key];
          if (move) {
            event.preventDefault();
            const next = clampPet(
              position.x + move[0],
              position.y + move[1],
              viewport.width,
              viewport.height,
            );
            setPosition(next);
            save(next);
          }
        }}
      >
        <span
          className="mascot-sprite"
          aria-hidden="true"
          style={{
            backgroundImage: "url(" + app.team.mascot + ")",
            backgroundPosition:
              -(reduced ? 0 : frame % PET_FRAMES[row]) * PET_WIDTH +
              "px " +
              -row * PET_HEIGHT +
              "px",
          }}
        />
        <span className="mascot-hint">คุยกับ {app.team.shortName}</span>
      </button>
    </div>
  );
}
