"use client";
import { useEffect, useRef, useState } from "react";
import { X, Check, Settings, Info } from "lucide-react";
import { useApp } from "./AppProvider";
import { teams, TeamKey } from "../lib/teams";
import { ErrorBox } from "./Ui";

export function PersonalSettings({ close }: { close: () => void }) {
  const app = useApp();
  const [draft, setDraft] = useState<TeamKey>(app.team.key);
  const dialog = useRef<HTMLDialogElement>(null);
  const preview = teams.find((team) => team.key === draft)!;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = dialog.current!;
    element.showModal();
    return () => {
      element.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className="personal-settings"
      aria-labelledby="personal-settings-title"
      onCancel={(event) => {
        if (app.teamBusy) event.preventDefault();
        else close();
      }}
    >
      <header className="panel-heading">
        <h2 id="personal-settings-title">
          <Settings size={24} /> ตั้งค่าส่วนตัว
        </h2>
        <button aria-label="ปิดตั้งค่า" disabled={app.teamBusy} onClick={close}>
          <X size={20} />
        </button>
      </header>
      <p className="muted">เลือกทีมโปรดสำหรับธีม พื้นหลัง และมาสคอส</p>
      <fieldset className="favorite-options">
        <legend>ทีมโปรดของฉัน</legend>
        {teams.map((team) => (
          <label key={team.key} className={draft === team.key ? "chosen" : ""}>
            <input
              type="radio"
              name="favorite"
              value={team.key}
              checked={draft === team.key}
              disabled={app.teamBusy}
              onChange={() => setDraft(team.key)}
            />
            <img
              src={`/crests/${team.teamId}.png`}
              alt=""
              width={32}
              height={32}
            />
            {team.name}
            {draft === team.key && <Check size={18} />}
          </label>
        ))}
      </fieldset>
      <div
        className="favorite-preview"
        style={{
          backgroundImage: `linear-gradient(90deg,#060b14dd,#060b1455),url(/backgrounds/${preview.key}.png)`,
        }}
      >
        <small>ตัวอย่างธีมและมาสคอส</small>
        <h3>{preview.name}</h3>
        <p className="preview-tagline">สีที่เป็นคุณ · ทุกนัดของทีมโปรด</p>
        <div className="preview-palette" aria-label="ชุดสีตัวอย่าง">
          <span
            className="preview-swatch"
            style={{ background: preview.color }}
          />
          <span
            className="preview-swatch"
            style={{ background: preview.colorBright }}
          />
          <span className="preview-swatch" style={{ background: "#0b1c2c" }} />
          <span className="preview-swatch" style={{ background: "#f4f8ff" }} />
        </div>
        <div
          className="preview-pet"
          role="img"
          aria-label={`มาสคอส ${preview.name}`}
          style={{ backgroundImage: `url(${preview.mascot})` }}
        />
      </div>
      <p className="settings-note">
        <Info size={20} />
        การดูข้อมูลทีมอื่นจะไม่เปลี่ยนทีมโปรด ทีมโปรดใช้สำหรับธีมและมาสคอสของคุณ
      </p>
      <ErrorBox error={app.teamError} />
      <div className="settings-actions">
        <button disabled={app.teamBusy} onClick={close}>
          ยกเลิก
        </button>
        <button
          className="primary"
          disabled={app.teamBusy}
          onClick={async () => {
            if (
              app.user?.favorite_team_id === preview.teamId ||
              (await app.changeTeam(draft))
            )
              close();
          }}
        >
          {app.teamBusy ? "กำลังบันทึก…" : "บันทึกการตั้งค่า"}
        </button>
      </div>
    </dialog>
  );
}
