"use client";

import { useApp } from "./AppProvider";
import { teams } from "../lib/teams";

export function AuthStory() {
  const app = useApp();
  return (
    <section className="login-story">
      <div className="wordmark">
        <img
          className="panda-mark"
          src="/panda-logo.svg"
          alt=""
          width={52}
          height={52}
        />
        <span>
          PANBALL<small>FOOTBALL BRINGS US CLOSER</small>
        </span>
      </div>
      <div className="login-headline">
        <span className="eyebrow">SOME PLACES THAT LIVE FOREVER.</span>
        <h1>
          YOUR CLUB.
          <br />
          YOUR WORLD.
        </h1>
        <p>ทุกเรื่องของทีมที่คุณรัก</p>
        <div className="login-teams" aria-label="เลือกธีมทีม">
          {teams.map((team) => (
            <button
              key={team.key}
              aria-label={team.name}
              aria-pressed={team.key === app.team.key}
              onClick={() => void app.changeTeam(team.key)}
            >
              <img
                src={"/crests/" + team.teamId + ".png"}
                alt=""
                width={56}
                height={56}
              />
            </button>
          ))}
        </div>
        <p className="club-manifesto">
          DIFFERENT COLOURS. SAME PASSION.
          <br />A BRIGHTER TOMORROW.
        </p>
      </div>
    </section>
  );
}
