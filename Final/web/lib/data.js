"use client";

import { api, ApiError } from "@/lib/api";
import { isMockOn } from "@/lib/mock/mode";
import { mockApi } from "@/lib/mock/server";

// One place for every call the pages make. Each function returns the same
// Contract.md shape whether it reads the real api (through the /api proxy) or
// the in-browser mock (lib/mock/server.js). Pages never check the mode.

const real = async (path, options) => (await api(path, options)).data;
const pick = (mockFn, realFn) => (...args) => (isMockOn() ? mockFn(...args) : realFn(...args));

/** Upload with progress. fetch() cannot report upload progress, so this uses XHR. */
function uploadCvReal(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/cv");
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onerror = () =>
      reject(new ApiError(0, { code: "NETWORK_ERROR", message_th: "เชื่อมต่อไม่ได้ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่" }));
    xhr.onload = () => {
      let body = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new ApiError(xhr.status, { request_id: xhr.getResponseHeader("x-request-id"), ...(body || {}) }));
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export const data = {
  /** GET /api/auth/me → {user} */
  me: pick(mockApi.me, () => real("/auth/me")),
  /** POST /api/auth/logout */
  logout: pick(mockApi.logout, () => real("/auth/logout", { method: "POST" })),
  /** GET /api/quota → Quota */
  quota: pick(mockApi.quota, () => real("/quota")),

  /** GET /api/cv → {cv: CvParsed | null} */
  getCv: pick(mockApi.getCv, () => real("/cv")),
  /** POST /api/cv (multipart) → {cv} ; onProgress(0..1) */
  uploadCv: pick(mockApi.uploadCv, uploadCvReal),
  /** PUT /api/cv/confirm → {cv, completeness} */
  confirmCv: pick(mockApi.confirmCv, (body) => real("/cv/confirm", { method: "PUT", body })),
  /** DELETE /api/cv → {deleted, completeness} */
  deleteCv: pick(mockApi.deleteCv, () => real("/cv", { method: "DELETE" })),

  /** GET /api/questionnaire → {version, sections, attribution} */
  questionnaire: pick(mockApi.questionnaire, () => real("/questionnaire")),
  /** GET /api/questionnaire/answers → {answers, answered, total} */
  answers: pick(mockApi.answers, () => real("/questionnaire/answers")),
  /** PUT /api/questionnaire/answers/{id} → {saved, completeness} */
  saveAnswer: pick(mockApi.saveAnswer, (id, value) =>
    real(`/questionnaire/answers/${encodeURIComponent(id)}`, { method: "PUT", body: { value } }),
  ),

  /** GET /api/profile/completeness → Completeness */
  completeness: pick(mockApi.completeness, () => real("/profile/completeness")),
  /** POST /api/profile/generate → {profile, matches} */
  generateProfile: pick(mockApi.generateProfile, () => real("/profile/generate", { method: "POST" })),
  /** GET /api/profile → {profile: Profile | null} */
  getProfile: pick(mockApi.getProfile, () => real("/profile")),
  /** DELETE /api/profile/skills/{skill_id} → {profile, matches} */
  removeSkill: pick(mockApi.removeSkill, (id) => real(`/profile/skills/${encodeURIComponent(id)}`, { method: "DELETE" })),
  /** POST /api/profile/skills/{skill_id}/restore → {profile, matches} */
  restoreSkill: pick(mockApi.restoreSkill, (id) => real(`/profile/skills/${encodeURIComponent(id)}/restore`, { method: "POST" })),
  /** GET /api/profile/removed-skills → {skills: [{skill_id, name_th, removed_at}]} */
  removedSkills: pick(mockApi.removedSkills, () => real("/profile/removed-skills")),

  /** GET /api/profile/edits/pending → {edits: EditProposal[]} */
  pendingEdits: pick(mockApi.pendingEdits, () => real("/profile/edits/pending")),
  /** POST /api/profile/edits/{edit_id}/confirm → {profile, matches} */
  confirmEdit: pick(mockApi.confirmEdit, (id) => real(`/profile/edits/${encodeURIComponent(id)}/confirm`, { method: "POST" })),
  /** POST /api/profile/edits/{edit_id}/reject → {ok} */
  rejectEdit: pick(mockApi.rejectEdit, (id) => real(`/profile/edits/${encodeURIComponent(id)}/reject`, { method: "POST" })),

  /** GET /api/roles → {roles: [{role_id, title_th, title_en, summary_th, career_stage}]} */
  roles: pick(mockApi.roles, () => real("/roles")),
  /** GET /api/roles/matches → MatchList */
  matches: pick(mockApi.matches, () => real("/roles/matches")),
  /** POST /api/roles/matches/explain → MatchList (counts toward quota) */
  explainMatches: pick(mockApi.explainMatches, () => real("/roles/matches/explain", { method: "POST" })),
  /** GET /api/roles/{role_id} → {role: RoleDetail, match: RoleMatch | null} */
  role: pick(mockApi.role, (id) => real(`/roles/${encodeURIComponent(id)}`)),
  /** GET /api/roles/{role_id}/market?listings=5 → RoleMarket */
  roleMarket: pick(mockApi.roleMarket, (id, { listings = 5 } = {}) => real(`/roles/${encodeURIComponent(id)}/market?listings=${listings}`)),

  /** GET /api/admin/overview?window=today|7d|30d → AdminOverview (admins only, else 403 FORBIDDEN) */
  adminOverview: pick(mockApi.adminOverview, (window = "today") => real(`/admin/overview?window=${encodeURIComponent(window)}`)),

  /** DELETE /api/me {confirm: "DELETE"} → {deleted: true} */
  deleteMe: pick(mockApi.deleteMe, (body) => real("/me", { method: "DELETE", body })),

  /** POST /api/chat → ChatResponse */
  chat: pick(mockApi.chat, (message) => real("/chat", { method: "POST", body: { message } })),
  /** GET /api/chat/history → {messages: ChatMessage[]} */
  chatHistory: pick(mockApi.chatHistory, () => real("/chat/history?limit=50")),
};

