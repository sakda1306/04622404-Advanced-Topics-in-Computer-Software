// Builds the mock API fixtures from the shared /data files, in the exact shapes
// the api returns (Contract.md 2.3, 2.6, 2.7). Run after /data changes:
//   npm run mock:fixtures
// The web image is built from ./web only, so the output is committed.

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = join(here, "..", "..", "data");
const outDir = join(here, "..", "lib", "mock", "fixtures");

const read = (name) => JSON.parse(readFileSync(join(dataDir, name), "utf8"));
const questionnaire = read("questionnaire.json");
const skills = read("skills.json");
const roles = read("roles.json");

const roleList = Array.isArray(roles) ? roles : roles.roles;

// options_source is resolved by the api: hard skills from skills.json, roles from roles.json.
const OPTION_SOURCES = {
  "skills.json": skills
    .filter((s) => s.type === "hard")
    .map((s) => ({ value: s.id, label_th: s.name_th }))
    .sort((a, b) => a.label_th.localeCompare(b.label_th, "th")),
  "roles.json": roleList.map((r) => ({ value: r.id, label_th: r.name_th, label_en: r.name_en })),
};

// File-only fields are never sent to the web (Contract.md 2.3).
const FILE_ONLY = new Set(["slot", "trait", "skill_id", "source_ids", "options_source"]);

function toApiQuestion(q) {
  const out = {};
  for (const [key, value] of Object.entries(q)) if (!FILE_ONLY.has(key)) out[key] = value;
  if (q.options_source) out.options = OPTION_SOURCES[q.options_source];
  return out;
}

const response = {
  version: questionnaire.version,
  sections: questionnaire.sections.map((s) => ({
    id: s.id,
    title_th: s.title_th,
    questions: s.questions.map(toApiQuestion),
  })),
  attribution: {
    text_th:
      "คำถามพัฒนาโดยทีมผู้พัฒนา โดยดัดแปลงจากมิติ Work Styles และ Skills ของ O*NET® (USDOL/ETA, CC BY 4.0) ซึ่ง USDOL/ETA ไม่ได้รับรองเนื้อหานี้",
    sources: questionnaire.sources
      .filter((s) => s.url)
      .map(({ title, url, license, license_url, attribution }) => ({ title, url, license, license_url, attribution })),
  },
};

// The mock completeness needs to know which slot each question fills.
const slots = Object.fromEntries(
  questionnaire.sections.flatMap((s) => s.questions.map((q) => [q.question_id, q.slot])),
);

// Skill names for the CV review (name, English name), keyed by skill id.
const skillNames = Object.fromEntries(skills.map((s) => [s.id, { th: s.name_th, en: s.name_en, type: s.type }]));

// Role profiles (data/roles/<id>.json + .md) for the role results and role detail
// mocks: requirements and work style for scoring (Design.md 4.3), and the
// description and learning path text from the .md file.
function mdSection(md, heading) {
  const m = new RegExp(`^## ${heading}\\s*$([\\s\\S]*?)(?=^## |(?![\\s\\S]))`, "m").exec(md);
  return m ? m[1].trim() : "";
}

// Salary reference layer (data/salary/reference.csv): one row per role at most.
function readCsv(file) {
  const [head, ...lines] = readFileSync(file, "utf8").trim().split(/\r?\n/);
  const cols = head.split(",");
  return lines.map((line) => {
    const cells = [];
    let cur = "";
    let quoted = false;
    for (const ch of line) {
      if (ch === '"') quoted = !quoted;
      else if (ch === "," && !quoted) {
        cells.push(cur);
        cur = "";
      } else cur += ch;
    }
    cells.push(cur);
    return Object.fromEntries(cols.map((c, i) => [c, cells[i] ?? ""]));
  });
}
const salaryRef = Object.fromEntries(
  readCsv(join(dataDir, "salary", "reference.csv")).map((r) => [
    r.role_id,
    { min_thb: Number(r.min), max_thb: Number(r.max), measure: r.measure, source: r.source, url: r.url, as_of: r.published_at || r.retrieved_at },
  ]),
);

const roleProfiles = roleList.map((r) => {
  const json = JSON.parse(readFileSync(join(dataDir, "roles", `${r.id}.json`), "utf8"));
  const mdFile = join(dataDir, "roles", `${r.id}.md`);
  const md = existsSync(mdFile) ? readFileSync(mdFile, "utf8") : "";
  return {
    role_id: json.role_id,
    title_th: json.title_th,
    title_en: json.title_en,
    career_stage: json.career_stage,
    required: json.required.map((q) => ({ skills: q.any_of ?? [q.skill_id], min_level: q.min_level, weight: q.weight })),
    nice_to_have: json.nice_to_have,
    soft_skills: json.soft_skills,
    work_style: json.work_style,
    description_th: mdSection(md, "Role description"),
    learning_path_th: mdSection(md, "Learning path"),
    author: json.author,
    reviewer: json.reviewer,
    status: json.status,
    sources: json.sources.map(({ url, language, file }) => ({ url, language, ...(file ? { file } : {}) })),
    salary_reference: salaryRef[json.role_id] ?? null,
  };
});

mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, "roles.json"), `${JSON.stringify(roleProfiles, null, 1)}\n`);
writeFileSync(join(outDir, "questionnaire.json"), `${JSON.stringify(response, null, 1)}\n`);
writeFileSync(join(outDir, "question-slots.json"), `${JSON.stringify(slots, null, 1)}\n`);
writeFileSync(join(outDir, "skills.json"), `${JSON.stringify(skillNames)}\n`);
console.log(
  `mock fixtures: ${response.sections.length} sections, ${Object.keys(slots).length} questions, ${Object.keys(skillNames).length} skills, ${roleProfiles.length} roles (${roleProfiles.filter((r) => r.salary_reference).length} with reference salary)`,
);
