import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  demoRuns,
  fallbackPersonas,
  type Persona,
  type Run,
} from "./data";
import { apiAssetUrl, request } from "./api";
import Improvements from "./Improvements";
import { canRevamp } from "./revamp";
import {
  createLocalPersonaId,
  isSavedPersona,
  loadSavedPersonas,
  mergePersonas,
  personaNameKey,
  savePersonas,
} from "./personaStorage";
import "./App.css";

type IconName =
  | "grid"
  | "play"
  | "people"
  | "chart"
  | "arrow"
  | "plus"
  | "globe"
  | "check"
  | "chevron"
  | "close"
  | "search"
  | "bolt"
  | "external"
  | "download"
  | "help"
  | "clock"
  | "target"
  | "copy";
function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </>
    ),
    play: <path d="m9 5 11 7-11 7Z" />,
    people: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 5" />
      </>
    ),
    chart: <path d="M4 3v17h17M8 15v-4m5 4V7m5 8V4" />,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    plus: <path d="M12 5v14M5 12h14" />,
    globe: (
      <>
        <circle cx="12" cy="12" r="9" />
        <ellipse cx="12" cy="12" rx="4" ry="9" />
        <path d="M3 12h18" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    chevron: <path d="m9 5 7 7-7 7" />,
    close: <path d="m6 6 12 12M6 18 18 6" />,
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 5 5" />
      </>
    ),
    bolt: <path d="m13 2-9 12h7l-1 8 10-13h-7Z" />,
    external: <path d="M14 3h7v7m0-7L10 14M10 4H4v16h16v-6" />,
    download: <path d="M12 3v12m-5-5 5 5 5-5M4 15v6h16v-6" />,
    help: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M9 8a3 3 0 0 1 6 0c0 2-3 2-3 5m0 3v1" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    target: (
      <>
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="5" />
        <circle cx="12" cy="12" r="1" />
      </>
    ),
    copy: (
      <>
        <rect x="8" y="8" width="11" height="11" rx="1.5" />
        <path d="M16 8V5H5a1 1 0 0 0-1 1v11h4" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
function Mark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 48 48" fill="none">
        <path className="mark-orbit" d="M8.5 29.5C4.4 18.9 9.8 7.1 20.4 3" />
        <path className="mark-orbit mark-orbit-two" d="M27.6 45C38.2 40.9 43.6 29.1 39.5 18.5" />
        <path className="mark-stroke" d="M15.2 31V13h8.7a6.5 6.5 0 0 1 0 13h-8.7" />
        <path className="mark-stroke mark-stroke-two" d="M15.2 31V13" />
        <circle className="mark-core" cx="25.2" cy="19.5" r="2.25" />
      </svg>
    </span>
  );
}
function Avatar({ id, small = false }: { id: string; small?: boolean }) {
  const tone =
    id === "power_user"
      ? "lilac"
      : id === "elderly"
        ? "peach"
        : id === "mobile_user"
          ? "sky"
          : id === "accessibility_advocate"
            ? "sun"
            : id === "privacy_conscious"
              ? "violet"
              : "mint";
  const icon: IconName =
    id === "power_user"
      ? "bolt"
      : id === "elderly" || id === "mobile_user"
        ? "globe"
        : id === "accessibility_advocate"
          ? "grid"
          : id === "privacy_conscious"
            ? "target"
            : "people";
  return (
    <span
      className={`avatar ${tone} ${small ? "small" : ""}`}
    >
      <Icon name={icon} size={small ? 14 : 22} />
    </span>
  );
}
function Modal({
  title,
  subtitle,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    ref.current?.focus();
    function keys(event: KeyboardEvent) {
      if (event.key === "Escape") closeRef.current();
      if (event.key === "Tab") {
        const items = ref.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), input, textarea, select, a[href], [tabindex="0"]',
        );
        if (!items?.length) return;
        const first = items[0],
          last = items[items.length - 1];
        if (
          event.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === ref.current)
        ) {
          event.preventDefault();
          last.focus();
        }
        if (
          !event.shiftKey &&
          (document.activeElement === last ||
            document.activeElement === ref.current)
        ) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", keys);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", keys);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`modal ${wide ? "wide" : ""}`}
      >
        <div className="modal-heading">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            <Icon name="close" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
const MAX_PERSPECTIVES = 2;
function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
function metrics(runs: Run[]) {
  const results = runs.flatMap((run) => Object.values(run.results));
  const scores = results.flatMap((r) => (r.score == null ? [] : [r.score]));
  const completed = results.filter((r) => r.success).length;
  return {
    runs: runs.length,
    journeys: results.length,
    completed,
    success: results.length ? Math.round((completed / results.length) * 100) : null,
    score: scores.length
      ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1)
      : "—",
    actions: results.reduce((sum, result) => sum + result.steps.length, 0),
    issues:
      results.filter((r) => !r.success).length +
      runs.reduce((sum, r) => sum + Object.keys(r.errors).length, 0),
  };
}
function loadRuns(): Run[] {
  try {
    const value = JSON.parse(localStorage.getItem("persona-runs-v1") || "[]");
    return Array.isArray(value)
      ? value.filter(
          (r) =>
            r &&
            typeof r.id === "string" &&
            typeof r.task === "string" &&
            typeof r.url === "string" &&
            Array.isArray(r.personas) &&
            r.results &&
            r.errors &&
            r.session_viewer_urls,
        )
      : [];
  } catch {
    return [];
  }
}

function App() {
  const [page, setPage] = useState("Overview");
  const [demo, setDemo] = useState(false);
  const [personas, setPersonas] = useState<Persona[]>(() => {
    const saved = loadSavedPersonas();
    return saved.length ? saved : fallbackPersonas;
  });
  const [connected, setConnected] = useState(false);
  const [runs, setRuns] = useState<Run[]>(loadRuns);
  const [modal, setModal] = useState<"run" | "persona" | null>(null);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [improvementsRunId, setImprovementsRunId] = useState<string | null>(null);
  const improvementsButton = useRef<HTMLButtonElement>(null);
  const [selectedPersona, setSelectedPersona] = useState("first_time");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("All tests");
  const [error, setError] = useState("");
  const [pollError, setPollError] = useState("");
  const [busy, setBusy] = useState(false);
  const [chosen, setChosen] = useState<string[]>([
    "first_time",
    "power_user",
  ]);
  const [toast, setToast] = useState("");
  const [replay, setReplay] = useState(0);
  const [replaying, setReplaying] = useState(false);
  useEffect(() => {
    let active = true;
    const check = () =>
      request<Record<string, Persona>>("/personas")
        .then((data) => {
          if (active) {
            setPersonas((current) =>
              mergePersonas(current.filter(isSavedPersona), Object.values(data)),
            );
            setConnected(true);
          }
        })
        .catch(() => {
          if (active) setConnected(false);
        });
    void check();
    const timer = window.setInterval(check, 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    if (!personas.some(isSavedPersona)) return;
    try {
      savePersonas(personas);
    } catch {
      // Keep server personas usable in memory. Explicit saves report storage errors.
    }
  }, [personas]);
  useEffect(() => {
    try {
      localStorage.setItem("persona-runs-v1", JSON.stringify(runs));
    } catch {
      /* Keep the session usable when storage is unavailable. */
    }
  }, [runs]);
  const activeIds = runs
    .filter((r) => r.status === "running" || r.status === "created")
    .map((r) => r.id)
    .join(",");
  useEffect(() => {
    if (!activeIds) return;
    let active = true;
    let pending = false;
    const poll = async () => {
      if (pending) return;
      pending = true;
      const updates = await Promise.allSettled(
        activeIds.split(",").map((id) => request<Run>(`/runs/${id}`)),
      );
      if (active) {
        const fresh = updates.flatMap((r) =>
          r.status === "fulfilled" ? [r.value] : [],
        );
        setRuns((current) =>
          current.map((r) => fresh.find((f) => f.id === r.id) || r),
        );
        setPollError(
          updates.some((r) => r.status === "rejected")
            ? "Unable to refresh a run. The server may be offline or the run may have expired. Retrying automatically."
            : "",
        );
      }
      pending = false;
    };
    void poll();
    const timer = window.setInterval(poll, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [activeIds]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 4000);
    return () => clearTimeout(t);
  }, [toast]);
  useEffect(() => {
    if (!replaying || replay >= 4) return;
    const t = setTimeout(() => setReplay((v) => v + 1), 1100);
    return () => clearInterval(t);
  }, [replaying, replay]);
  const displayed = demo ? demoRuns : runs;
  const stats = metrics(displayed);
  const visibleRuns = displayed.filter(
    (r) =>
      `${r.task} ${r.url}`.toLowerCase().includes(search.toLowerCase()) &&
      (filter === "All tests" ||
        (filter === "In progress"
          ? ["created", "running"].includes(r.status)
          : r.status === filter.toLowerCase())),
  );
  const detail = selectedRun
    ? runs.find((r) => r.id === selectedRun.id) || selectedRun
    : null;
  const detailPersona = detail?.personas.includes(selectedPersona)
    ? selectedPersona
    : detail?.personas[0] || "";
  const result = detail?.results[detailPersona];
  const replayActive = replaying && replay < (result?.steps.length || 0);
  function openRun() {
    setError("");
    setChosen(personas.slice(0, MAX_PERSPECTIVES).map((p) => p.id));
    setModal("run");
  }
  function inspect(run: Run) {
    setImprovementsRunId(null);
    setSelectedPersona(run.personas[0]);
    setSelectedRun(run);
    setReplay(4);
    setReplaying(false);
  }
  function startDemo() {
    setImprovementsRunId(null);
    setDemo(true);
    setSelectedRun(demoRuns[0]);
    setSelectedPersona("first_time");
    setReplay(0);
    setReplaying(true);
  }
  async function submitRun(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    if (!chosen.length) {
      setError("Select at least one persona to start a test.");
      return;
    }
    if (chosen.length > MAX_PERSPECTIVES) {
      setError(`Select at most ${MAX_PERSPECTIVES} perspectives per test.`);
      return;
    }
    const form = new FormData(e.currentTarget);
    const url = String(form.get("url")).trim();
    if (!/^https?:\/\//i.test(url)) {
      setError(
        "Enter a complete website URL starting with https:// or http://.",
      );
      return;
    }
    const task = String(form.get("task")).trim();
    if (!task) {
      setError("Describe the goal you want the agents to complete.");
      return;
    }
    const selected = chosen.map((id) => personas.find((p) => p.id === id));
    if (selected.some((persona) => !persona)) {
      setError("A selected perspective is no longer available. Choose your perspectives again.");
      return;
    }
    // Placeholder demo personas have no prompt; resolve those on the server.
    const personaDefinitions = Object.fromEntries(
      selected.filter(isSavedPersona).map((persona) => [persona.id, persona]),
    );
    setBusy(true);
    try {
      const { run_id } = await request<{ run_id: string }>("/runs", {
        method: "POST",
        body: JSON.stringify({ url, task, personas: chosen, persona_definitions: personaDefinitions }),
      });
      const run: Run = {
        id: run_id,
        url,
        task,
        personas: chosen,
        persona_definitions: personaDefinitions,
        status: "created",
        results: {},
        errors: {},
        session_viewer_urls: {},
        createdAt: new Date().toISOString(),
      };
      setRuns((current) => [run, ...current]);
      setDemo(false);
      setModal(null);
      setSelectedRun(run);
      setSelectedPersona(chosen[0]);
      setToast("Test launched. Your agents are getting ready.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not start the test. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  function submitPersona(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      const name = String(form.get("name") || "").trim();
      const existing = personas.find((p) => personaNameKey(p.name) === personaNameKey(name));
      const persona: Persona = {
        id: existing?.id || createLocalPersonaId(),
        name,
        description: String(form.get("description") || "").trim(),
        system_prompt: String(form.get("system_prompt") || "").trim(),
      };
      if (!isSavedPersona(persona)) {
        setError("Enter a name, description, and behavior instructions within the field limits.");
        return;
      }
      const updated = mergePersonas([persona], personas);
      savePersonas(updated);
      setPersonas(updated);
      setModal(null);
      setToast(`${persona.name} is saved in this browser and ready to test.`);
    } catch {
      setError("Could not save the persona in this browser. Check that browser storage is available and try again.");
    } finally {
      setBusy(false);
    }
  }
  function exportRun(run: Run) {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(run, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `persona-${run.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setToast("Report downloaded.");
  }
  const navigation: [string, IconName][] = [
    ["Overview", "grid"],
    ["Test runs", "play"],
    ["Personas", "people"],
    ["Insights", "chart"],
    ["Why we built this", "help"],
  ];
  return (
    <div className="app-shell">
      <aside className="sidebar" inert={!!modal || !!selectedRun}>
        <a
          className="brand"
          href="#"
          aria-label="PersonaAgent overview"
          onClick={(e) => {
            e.preventDefault();
            setPage("Overview");
          }}
        >
          <Mark />
          <span>
            persona<span className="brand-light">agent</span>
            <span className="brand-period">.</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon"><Icon name="globe" size={16} /></span>
          <div>
            <strong>Local session</strong>
            <span>No account required</span>
          </div>
          <span className="workspace-dot" />
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav aria-label="Main navigation">
          {navigation.map(([label, icon]) => (
            <button
              key={label}
              aria-label={label}
              aria-current={page === label ? "page" : undefined}
              className={`nav-item ${page === label ? "active" : ""}`}
              onClick={() => {
                setPage(label);
                setSearch("");
                setFilter("All tests");
              }}
            >
              <Icon name={icon} />
              <span>{label}</span>
              {label === "Test runs" && (
                <span className="nav-count">{displayed.length}</span>
              )}
            </button>
          ))}
        </nav>
      </aside>
      <div className="main-shell" inert={!!modal || !!selectedRun}>
        <header className="topbar">
          <div className="breadcrumbs">
            Workspace <span>/</span>
            <strong>{page}</strong>
          </div>
          <div className="topbar-right">
            <span className={`connection ${connected ? "online" : ""}`}>
              <i />
              {connected ? "Backend connected" : "Backend offline"}
            </span>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <h1>
                {page === "Overview"
                  ? "AI personas test what users actually do."
                  : page === "Test runs"
                    ? "Run history."
                    : page === "Personas"
                      ? "Personas."
                      : page === "Insights"
                        ? "Results by persona."
                        : "Why PersonaAgent exists."}
              </h1>
              <p>
                {page === "Overview"
                  ? "AI-powered browser personas navigate a task and explain every action."
                  : page === "Test runs"
                    ? "Tasks, outcomes, and step-by-step evidence."
                    : page === "Personas"
                      ? "Configure the users your tests should represent."
                      : page === "Insights"
                        ? "Compare completion and scores across runs."
                        : "The testing gap we wanted to close."}
              </p>
            </div>
            <button
              className="button primary"
              aria-label={page === "Personas" ? "Create persona" : "New test run"}
              onClick={
                page === "Personas"
                  ? () => {
                      setError("");
                      setModal("persona");
                    }
                  : openRun
              }
            >
              <Icon name="plus" size={17} />
              {page === "Personas" ? "Create persona" : "New test run"}
            </button>
          </div>
          {page !== "Personas" && page !== "Why we built this" && (
            <div className="mode-bar">
              <div>
                <span className={`mode-dot ${demo ? "" : "live"}`} />
                <strong>{demo ? "AI persona demo" : "AI test session"}</strong>
                <span>
                  {demo
                    ? "Sample results"
                    : "Saved in this browser"}
                </span>
              </div>
              <button
                onClick={() => {
                  setDemo(!demo);
                  setSearch("");
                  setFilter("All tests");
                }}
              >
                {demo ? "Switch to live" : "View demo"}
                <Icon name="arrow" size={15} />
              </button>
            </div>
          )}
          {page === "Overview" && (
            <section className="hero-panel">
              <div className="hero-copy">
                <div className="hero-kicker"><span /> AI-POWERED PERSONA TESTING</div>
                <h2>
                  Let AI personas find
                  <br />
                  the friction first.
                </h2>
                <p>
                  Give an AI persona a goal. It navigates your site, explains its decisions, and records where the experience breaks.
                </p>
                <div className="hero-actions">
                  <button className="button primary" onClick={openRun}>
                    Run a test <Icon name="arrow" size={17} />
                  </button>
                  <button className="text-button" onClick={startDemo}>
                    <span className="play-circle">
                      <Icon name="play" size={12} />
                    </span>
                    View demo
                  </button>
                </div>
              </div>
              <div className="orbit-art" aria-hidden="true">
                <div className="orbit orbit-one" />
                <div className="orbit orbit-two" />
                <div className="orbit orbit-three" />
                <div className="orbit-cross horizontal" />
                <div className="orbit-cross vertical" />
                <div className="orbit-scan" />
                <span className="orbit-star star-one" />
                <span className="orbit-star star-two" />
                <span className="orbit-star star-three" />
                <span className="orbit-dot dot-one" />
                <span className="orbit-dot dot-two" />
                <div className="center-node">
                  <Mark />
                </div>
                <div className="orbit-person person-one">
                  <Avatar id="first_time" />
                  <div>
                    <strong>First-time user</strong>
                    <span>Exploring the possibilities</span>
                  </div>
                  <span className="person-status" />
                </div>
                <div className="orbit-person person-two">
                  <Avatar id="power_user" />
                  <div>
                    <strong>Power user</strong>
                    <span>Finding the fastest path</span>
                  </div>
                  <span className="person-status" />
                </div>
                <div className="orbit-person person-three">
                  <Avatar id="elderly" />
                  <div>
                    <strong>Older adult</strong>
                    <span>Taking a closer look</span>
                  </div>
                  <span className="person-status" />
                </div>
                <span className="orbit-caption">
                  SIX AI PERSONAS. ONE CLEARER PRODUCT.
                </span>
              </div>
            </section>
          )}
          {page !== "Personas" && (
            <section className="stats-grid" aria-label="Test statistics">
              {[
                {
                  label: "Journeys evaluated",
                  value: stats.journeys,
                  icon: "play",
                  foot: `Across ${stats.runs} test runs`,
                },
                {
                  label: "Completion rate",
                  value: stats.success == null ? "—" : `${stats.success}%`,
                  icon: "check",
                  foot: `${stats.completed} of ${stats.journeys} persona journeys`,
                },
                {
                  label: "Avg. experience score",
                  value: stats.score,
                  icon: "target",
                  foot: "Mean score from scored journeys",
                },
                {
                  label: "Interaction steps",
                  value: stats.actions,
                  icon: "bolt",
                  foot: `${stats.issues} ${stats.issues === 1 ? "friction point" : "friction points"} surfaced`,
                },
              ].map((stat, i) => (
                <div className="stat-card" key={stat.label}>
                  <div className="stat-label">
                    {stat.label}
                    <Icon name={stat.icon as IconName} size={17} />
                  </div>
                  <div className={`stat-value ${i === 1 ? "green" : ""}`}>
                    {stat.value}
                    {i === 2 && stats.score !== "—" && <span>/ 10</span>}
                    <span
                      className={`stat-decoration decoration-${i}`}
                      aria-hidden="true"
                    >
                      <Icon name={stat.icon as IconName} size={32} />
                    </span>
                  </div>
                  <p>{stat.foot}</p>
                </div>
              ))}
            </section>
          )}
          {(page === "Overview" || page === "Test runs") && (
            <section className="runs-section">
              <div className="section-heading">
                <div>
                  <h2>
                    {page === "Overview" ? "Recent test runs" : "Test runs"}
                    <span className="count-pill">{displayed.length}</span>
                  </h2>
                  <p>Latest tasks and their outcomes.</p>
                </div>
                {page === "Overview" && (
                  <button
                    className="text-button"
                    onClick={() => setPage("Test runs")}
                  >
                    View all runs
                    <Icon name="arrow" size={15} />
                  </button>
                )}
              </div>
              <div className="table-card">
                <div className="table-toolbar">
                  <div className="tabs">
                    {["All tests", "Completed", "In progress", "Failed"].map(
                      (tab) => (
                        <button
                          key={tab}
                          aria-pressed={filter === tab}
                          className={filter === tab ? "selected" : ""}
                          onClick={() => setFilter(tab)}
                        >
                          {tab}
                        </button>
                      ),
                    )}
                  </div>
                  <label className="search-field">
                    <Icon name="search" size={16} />
                    <input
                      aria-label="Search test runs"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search tests…"
                    />
                  </label>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>TEST / WEBSITE</th>
                        <th>PERSONAS</th>
                        <th>STATUS</th>
                        <th>EXPERIENCE</th>
                        <th>RESULTS</th>
                        <th>
                          <span className="sr-only">Details</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleRuns.map((run) => {
                        const m = metrics([run]);
                        return (
                          <tr key={run.id}>
                            <td>
                              <div className="run-name">
                                <span
                                  className={`site-icon ${run.id === "demo-2" ? "lavender" : run.id === "demo-3" ? "orange" : ""}`}
                                >
                                  <Icon name="globe" size={20} />
                                </span>
                                <span>
                                  <button
                                    className="run-task"
                                    onClick={() => inspect(run)}
                                  >
                                    <strong>{run.task}</strong>
                                  </button>
                                  <span>
                                    <a
                                      className="run-link"
                                      href={run.url}
                                      target="_blank"
                                      rel="noreferrer"
                                      onClick={(event) => event.stopPropagation()}
                                    >
                                      {host(run.url)}
                                    </a>
                                    <span className="run-date">
                                      ·{" "}
                                      {run.id.startsWith("demo")
                                        ? "Sample test"
                                        : "Live test"}
                                    </span>
                                  </span>
                                </span>
                              </div>
                            </td>
                            <td>
                              <div className="avatar-stack">
                                {run.personas.slice(0, 4).map((id) => (
                                  <Avatar key={id} id={id} small />
                                ))}
                                <span>{run.personas.length} personas</span>
                              </div>
                            </td>
                            <td>
                              <span className={`status ${run.status}`}>
                                <i />
                                {run.status === "created"
                                  ? "Queued"
                                  : run.status.charAt(0).toUpperCase() +
                                    run.status.slice(1)}
                              </span>
                            </td>
                            <td>
                              <div className="table-score">
                                <span>
                                  {m.score}
                                  <small>
                                    {m.score !== "—" ? " / 10" : ""}
                                  </small>
                                </span>
                                <div>
                                  <i
                                    style={{
                                      width: `${Number(m.score) * 10 || 0}%`,
                                    }}
                                  />
                                </div>
                              </div>
                            </td>
                            <td>
                              <span
                                className={m.issues ? "issue-count" : "muted"}
                              >
                                {m.issues
                                  ? `${m.issues} ${m.issues === 1 ? "issue" : "issues"}`
                                  : Object.keys(run.results).length
                                    ? "No blockers"
                                    : "Awaiting agents"}
                              </span>
                            </td>
                            <td>
                              <button
                                className="icon-button"
                                aria-label={`View ${run.task}`}
                                onClick={() => inspect(run)}
                              >
                                <Icon name="chevron" size={16} />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {!visibleRuns.length && (
                  <div className="empty-state">
                    <Icon
                      name={
                        search || filter !== "All tests" ? "search" : "play"
                      }
                      size={28}
                    />
                    <h3>
                      {search || filter !== "All tests"
                        ? "No matching tests"
                        : "No test runs yet."}
                    </h3>
                    <p>
                      {search || filter !== "All tests"
                        ? "Try another search or choose a different status."
                        : "Add a URL and a task to start collecting evidence."}
                    </p>
                    <button
                      className="button secondary"
                      onClick={
                        search || filter !== "All tests"
                          ? () => {
                              setSearch("");
                              setFilter("All tests");
                            }
                          : openRun
                      }
                    >
                      {search || filter !== "All tests"
                        ? "Clear filters"
                        : "Create your first test"}
                    </button>
                  </div>
                )}
                <div className="table-footer">
                  <span>
                    {demo
                      ? "Sample data · Open a run to inspect its actions"
                      : `${visibleRuns.length} test runs · Results refresh automatically`}
                  </span>
                  <span>
                    <Icon name="clock" size={13} />{" "}
                    {demo ? "Demo preview" : "Live results"}
                  </span>
                </div>
              </div>
            </section>
          )}
          {page === "Personas" && (
            <section className="personas-section">
              <div className="section-heading">
                <div>
                  <h2>Personas</h2>
                  <p>Behavior profiles for your tests.</p>
                </div>
                <button
                  className="text-button"
                  onClick={() => {
                    setError("");
                    setModal("persona");
                  }}
                >
                  <Icon name="plus" size={15} />
                  Create persona
                </button>
              </div>
              <div className="persona-grid">
                {personas.map((persona) => (
                  <button
                    className="persona-card"
                    key={persona.id}
                    onClick={() => {
                      setChosen([persona.id]);
                      setError("");
                      setModal("run");
                    }}
                  >
                    <div className="persona-card-top">
                      <Avatar id={persona.id} />
                      <span className="persona-type">
                        {fallbackPersonas.some((preset) => preset.id === persona.id)
                          ? "PRESET PERSONA"
                          : "CUSTOM PERSONA"}
                      </span>
                      <Icon name="arrow" size={17} />
                    </div>
                    <h3>
                      {persona.name === "Elderly"
                        ? "Older adult"
                        : persona.name}
                    </h3>
                    <p>{persona.description}</p>
                    <div className="persona-traits">
                      {(persona.id === "first_time"
                        ? ["Curious", "Needs guidance"]
                        : persona.id === "power_user"
                          ? ["Efficient", "Shortcut seeker"]
                          : persona.id === "elderly"
                            ? ["Deliberate", "Larger text"]
                            : persona.id === "mobile_user"
                              ? ["Small screen", "Tap friendly"]
                              : persona.id === "accessibility_advocate"
                                ? ["Keyboard first", "Clear focus"]
                                : persona.id === "privacy_conscious"
                                  ? ["Trust focused", "Consent aware"]
                            : ["Custom profile"]
                      ).map((trait) => (
                        <span key={trait}>{trait}</span>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
              <div className="persona-guide">
                <div className="persona-guide-copy">
                  <div className="guide-kicker"><span /> PERSONA GUIDE</div>
                  <h2>Write a persona that changes the test.</h2>
                  <p>Describe how someone behaves, what they know, and what makes them stop. A useful persona creates a different set of actions and observations.</p>
                  <div className="guide-steps">
                    <div><b>01</b><span><strong>Name the behavior</strong><small>“Price-conscious shopper” is more useful than “Shopper.”</small></span></div>
                    <div><b>02</b><span><strong>State the constraints</strong><small>Include device comfort, time pressure, knowledge, or accessibility needs.</small></span></div>
                    <div><b>03</b><span><strong>Tell the agent what to notice</strong><small>Ask it to explain hesitation, confusing labels, and failed attempts.</small></span></div>
                  </div>
                </div>
                <div className="persona-template">
                  <div className="template-heading"><span>STARTER TEMPLATE</span><Icon name="copy" size={15} /></div>
                  <pre>{`You are a [type of user].
Your goal is to [specific goal].
You already know [relevant context].
You struggle with [constraint or risk].
As you work, explain what you expect,
what is unclear, and what stops you.`}</pre>
                  <button className="text-button" onClick={() => { setError(""); setModal("persona"); }}>Use this template <Icon name="arrow" size={15} /></button>
                </div>
              </div>
            </section>
          )}
          {page === "Insights" && (
            <section className="insights-panel">
              <div className="section-heading">
                <div>
                  <h2>Experience by persona</h2>
                  <p>
                    Task completion across {demo ? "sample" : "your"} test
                    results.
                  </p>
                </div>
                <span className="count-pill">
                  {demo ? "Sample data" : "Live results"}
                </span>
              </div>
              {personas.map((p) => {
                const results = displayed.flatMap((r) =>
                  r.results[p.id] ? [r.results[p.id]] : [],
                );
                const passed = results.filter((r) => r.success).length;
                return (
                  <div className="insight-row" key={p.id}>
                    <Avatar id={p.id} />
                    <div>
                      <strong>{p.name}</strong>
                      <span>{results.length} completed evaluations</span>
                    </div>
                    <div className="insight-track">
                      <i
                        style={{
                          width: `${results.length ? (passed / results.length) * 100 : 0}%`,
                        }}
                      />
                    </div>
                    <strong>
                      {results.length
                        ? `${Math.round((passed / results.length) * 100)}%`
                        : "—"}
                    </strong>
                  </div>
                );
              })}
              <div className="insight-note">
                <Icon name="help" />
                <p>
                  AI personas score the experience from their own context. Review
                  each action and its reasoning before changing the site.
                </p>
              </div>
            </section>
          )}
          {page === "Why we built this" && (
            <section className="motivation-page" aria-labelledby="motivation-title">
              <div className="motivation-intro">
                <div className="motivation-kicker"><span /> THE REASON THIS EXISTS</div>
                <h2 id="motivation-title">The hardest bugs are the ones<br className="desktop-break" /> your test suite never sees.</h2>
                <p>Teams can prove that a button works. They still need to know whether a new user can find it, understand it, and use it without hesitation.</p>
              </div>
              <div className="motivation-grid">
                <article className="motivation-card motivation-card-featured">
                  <span className="motivation-number">01</span>
                  <h3>Scripted tests follow instructions.</h3>
                  <p>They are excellent at protecting known paths. But they begin with the answer: the exact selector, the expected click, and the happy path.</p>
                  <div className="motivation-line"><span className="line-dot" /> Known path <span className="line-arrow">→</span> predictable result</div>
                </article>
                <article className="motivation-card">
                  <span className="motivation-number">02</span>
                  <h3>People bring context.</h3>
                  <p>First-time visitors need guidance. Power users look for shortcuts. Older adults need legible controls. The same interface can fail in different ways.</p>
                  <div className="motivation-personas"><Avatar id="first_time" small /><Avatar id="power_user" small /><Avatar id="elderly" small /><Avatar id="mobile_user" small /><span>six behavior profiles</span></div>
                </article>
                <article className="motivation-card">
                  <span className="motivation-number">03</span>
                  <h3>PersonaAgent makes that visible.</h3>
                  <p>We give AI personas a goal and a behavior profile. They explore the product, explain each decision, and capture evidence a checklist cannot provide.</p>
                  <button className="button primary motivation-cta" onClick={openRun}>Test your website <Icon name="arrow" size={16} /></button>
                </article>
              </div>
              <div className="motivation-callout"><div className="callout-mark"><Mark /></div><div><strong>What we wanted to change</strong><p>Make usability evidence as easy to collect as a passing test. The result is a record of what each persona saw, tried, and could not finish.</p></div></div>
            </section>
          )}
          {pollError && !demo && (
            <div role="status" className="form-error">
              {pollError}
            </div>
          )}
          <footer className="page-footer">
            <span>
              <Mark />
              PersonaAgent
            </span>
            <span>
              No account required.
            </span>
          </footer>
        </main>
      </div>
      {modal === "run" && (
        <Modal
          title="A new perspective starts here."
          subtitle="Give your agents a destination and a goal."
          onClose={() => {
            if (!busy) setModal(null);
          }}
        >
          <form onSubmit={submitRun}>
            <label className="form-label">
              Website URL
              <input
                name="url"
                type="url"
                required
                placeholder="https://your-product.com"
              />
            </label>
            <label className="form-label">
              What should your users accomplish?
              <textarea
                name="task"
                required
                maxLength={3000}
                rows={3}
                placeholder="e.g. Find a pair of running shoes and add them to the cart."
              />
            </label>
            <div className="form-label">
              Choose your perspectives
              <span aria-live="polite">
                {chosen.length} / {MAX_PERSPECTIVES} selected
              </span>
            </div>
            <div className="persona-choices">
              {personas.map((p) => (
                <label
                  key={p.id}
                  className={`persona-choice ${chosen.includes(p.id) ? "chosen" : ""}`}
                >
                  <Avatar id={p.id} small />
                  <span>
                    <strong>{p.name}</strong>
                    <small>{p.description}</small>
                  </span>
                  <input
                    type="checkbox"
                    checked={chosen.includes(p.id)}
                    disabled={
                      !chosen.includes(p.id) &&
                      chosen.length >= MAX_PERSPECTIVES
                    }
                    onChange={() =>
                      setChosen((current) =>
                        current.includes(p.id)
                          ? current.filter((id) => id !== p.id)
                          : current.length < MAX_PERSPECTIVES
                            ? [...current, p.id]
                            : current,
                      )
                    }
                  />
                </label>
              ))}
            </div>
            <div className="form-note">
              <Icon name="globe" size={16} />
              {connected
                ? "Each persona explores in its own browser session."
                : "Start the backend on port 8000 to launch real agents. You can explore the demo anytime."}
            </div>
            {error && (
              <p role="alert" className="form-error">
                {error}
              </p>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="button secondary"
                disabled={busy}
                onClick={() => setModal(null)}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="button primary"
                disabled={busy || !chosen.length}
              >
                {busy ? "Launching agents…" : "Launch test run"}
                <Icon name="arrow" size={16} />
              </button>
            </div>
          </form>
        </Modal>
      )}
      {modal === "persona" && (
        <Modal
          title="Create a persona"
          subtitle="Add a behavior profile for future tests."
          onClose={() => {
            if (!busy) setModal(null);
          }}
        >
          <form onSubmit={submitPersona}>
            <label className="form-label">
              Name
              <input
                name="name"
                required
                maxLength={100}
                placeholder="e.g. The comparison shopper"
              />
            </label>
            <label className="form-label">
              Short description
              <input
                name="description"
                required
                maxLength={100}
                placeholder="Carefully compares options before making a decision."
              />
            </label>
            <label className="form-label">
              Behavior and instructions
              <textarea
                name="system_prompt"
                required
                maxLength={10000}
                rows={5}
                placeholder="You compare prices, read product details, and look for reviews. Explain your thinking and note any friction you encounter."
              />
            </label>
            <p className="form-note">
              Saved in this browser. A matching name replaces your saved version.
            </p>
            {error && (
              <p role="alert" className="form-error">
                {error}
              </p>
            )}
            <div className="modal-actions">
              <button
                className="button secondary"
                type="button"
                disabled={busy}
                onClick={() => setModal(null)}
              >
                Cancel
              </button>
              <button className="button primary" disabled={busy}>
                {busy ? "Creating…" : "Create persona"}
                <Icon name="plus" size={16} />
              </button>
            </div>
          </form>
        </Modal>
      )}
      {detail && (
        <Modal
          wide
          title={detail.task}
          subtitle={`${host(detail.url)} · ${detail.id.startsWith("demo") ? "Illustrative demo · not a real website evaluation" : `Run ${detail.id.slice(0, 8)}`}`}
          onClose={() => {
            setSelectedRun(null);
            setImprovementsRunId(null);
            setReplaying(false);
          }}
        >
          <div className="detail-summary">
            <span
              className={`status ${replayActive ? "running" : detail.status}`}
            >
              <i />
              {replayActive ? "Demo replay" : detail.status}
            </span>
            <span>{detail.personas.length} personas</span>
            <button className="text-button" onClick={() => exportRun(detail)}>
              <Icon name="download" size={15} />
              Export report
            </button>
          </div>
          {improvementsRunId === detail.id ? (
            <Improvements
              key={detail.id}
              run={detail}
              personas={personas}
              initialPersona={detailPersona}
              onBack={() => {
                setImprovementsRunId(null);
                requestAnimationFrame(() => improvementsButton.current?.focus());
              }}
            />
          ) : (
            <>
          <div className="detail-tabs">
            {detail.personas.map((id) => (
              <button
                className={detailPersona === id ? "selected" : ""}
                aria-pressed={detailPersona === id}
                key={id}
                onClick={() => {
                  setSelectedPersona(id);
                  setReplaying(false);
                }}
              >
                <Avatar id={id} small />
                {detail.persona_definitions?.[id]?.name || personas.find((p) => p.id === id)?.name || id}
              </button>
            ))}
          </div>
          {detail.session_viewer_urls[detailPersona] &&
            /^https?:\/\//.test(detail.session_viewer_urls[detailPersona]) && (
              <a
                className="live-session"
                href={detail.session_viewer_urls[detailPersona]}
                target="_blank"
                rel="noreferrer"
              >
                <span className="mode-dot live" />
                Open live browser session
                <Icon name="external" size={15} />
              </a>
            )}
          {result ? (
            <>
              <div
                className={`result-overview ${result.success ? "" : "has-issue"}`}
              >
                <span className="result-icon">
                  <Icon name={result.success ? "check" : "bolt"} size={23} />
                </span>
                <div>
                  <h3>
                    {result.success ? "Goal accomplished" : "Friction found"}
                  </h3>
                  <p>{result.summary}</p>
                </div>
                <div className="result-score">
                  {result.score ?? "—"}
                  <span>/ 10</span>
                </div>
              </div>
              {result.score_justification && (
                <p className="score-reason">{result.score_justification}</p>
              )}
              <div className="journey-heading">
                <h3>Actions</h3>
                <span>
                  {replayActive
                    ? `${Math.min(replay, result.steps.length)} / `
                    : ""}
                  {result.steps.length} actions
                </span>
              </div>
              <div className="timeline">
                {result.steps
                  .slice(0, replayActive ? replay : undefined)
                  .map((step) => (
                    <div className="timeline-step" key={step.step}>
                      <span className="step-number">{step.step}</span>
                      <div>
                        <div className="step-title">
                          <strong>{step.action.replaceAll("_", " ")}</strong>
                          <span
                            className={
                              step.outcome === "ok" ? "step-ok" : "step-failure"
                            }
                          >
                            {step.outcome}
                          </span>
                        </div>
                        <p>{step.reasoning}</p>
                        {step.value && <code>{step.value}</code>}
                        {step.screenshot_url && (
                          <img
                            className="step-screenshot"
                            src={apiAssetUrl(step.screenshot_url)}
                            alt={`Screenshot for step ${step.step}: ${step.action.replaceAll("_", " ")}`}
                            loading="lazy"
                            decoding="async"
                          />
                        )}
                      </div>
                    </div>
                  ))}
                {replayActive && (
                  <div className="replay-wait">
                    <span className="loading-dot" />
                    Loading sample actions…
                  </div>
                )}
              </div>
              {result.access_checks?.some((c) => c.evidence.length) && (
                <details className="access-details">
                  <summary>Page access diagnostics</summary>
                  {result.access_checks.map((check, i) => (
                    <p key={i}>
                      {check.state}: {check.evidence.join(" · ")}
                    </p>
                  ))}
                </details>
              )}
            </>
          ) : detail.errors[detailPersona] ? (
            <div className="form-error">
              <h3>This agent couldn’t finish</h3>
              <p>{detail.errors[detailPersona]}</p>
            </div>
          ) : (
            <div className="empty-state">
              <span className="agent-loader">
                <Mark />
              </span>
              <h3>
                {detail.status === "failed" || detail.status === "completed"
                  ? "No result available"
                  : "Your agent is finding its way."}
              </h3>
              <p>
                {detail.status === "failed" || detail.status === "completed"
                  ? "This run ended without a result for this persona."
                  : "Browser sessions appear when ready. Results update automatically."}
              </p>
            </div>
          )}
          {pollError && !detail.id.startsWith("demo") && (
            <p className="form-error" role="status">
              {pollError}
            </p>
          )}
          {canRevamp(detail) && (
            <div className="modal-actions">
              <button ref={improvementsButton} className="button primary" onClick={() => setImprovementsRunId(detail.id)}>
                Next: Improvements <Icon name="arrow" size={16} />
              </button>
            </div>
          )}
            </>
          )}
        </Modal>
      )}
      {toast && (
        <div role="status" className="toast">
          <Icon name="check" size={17} />
          {toast}
        </div>
      )}
    </div>
  );
}
export default App;
