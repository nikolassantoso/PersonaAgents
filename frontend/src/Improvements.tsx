import { useEffect, useRef, useState } from "react";
import { ApiError, apiAssetUrl, request } from "./api";
import type { Persona, Run } from "./data";
import { revampInProgress, screenshotCount, type Revamp } from "./revamp";
import "./Improvements.css";

function ComparisonImage({ url, alt }: { url: string; alt: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <div className="comparison-placeholder">Image unavailable. The saved screenshot may no longer be on the server.</div>;
  return (
    <a href={apiAssetUrl(url)} target="_blank" rel="noreferrer" aria-label={`${alt}. Open full-size image in a new tab`}>
      <img src={apiAssetUrl(url)} alt={alt} loading="lazy" decoding="async" onError={() => setFailed(true)} />
    </a>
  );
}

export default function Improvements({ run, personas, initialPersona, onBack }: {
  run: Run;
  personas: Persona[];
  initialPersona: string;
  onBack: () => void;
}) {
  const [revamp, setRevamp] = useState<Revamp | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [check, setCheck] = useState(0);
  const [selectedPersona, setSelectedPersona] = useState(initialPersona);
  const heading = useRef<HTMLHeadingElement>(null);
  const submission = useRef<AbortController | null>(null);

  useEffect(() => {
    heading.current?.focus();
    heading.current?.closest(".modal")?.scrollTo({ top: 0 });
    return () => submission.current?.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      let again = false;
      try {
        const data = await request<Revamp>(`/runs/${run.id}/revamp`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRevamp(data);
        setError("");
        again = revampInProgress(data);
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 404 && err.message === "Revamp not found") {
          setRevamp(null);
          setError("");
        } else {
          setError(err instanceof ApiError && err.status === 404
            ? "This run is no longer available on the server. Create a new test to generate improvements."
            : "Could not refresh improvements. Check your connection and try again.");
          again = !(err instanceof ApiError && err.status === 404);
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
      if (again && !controller.signal.aborted) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [run.id, check]);

  async function generate() {
    if (submission.current || loading || revamp || error) return;
    const controller = new AbortController();
    submission.current = controller;
    setGenerating(true);
    setError("");
    try {
      const data = await request<Revamp>(`/runs/${run.id}/revamp`, {
        method: "POST", signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        setRevamp(data);
        setCheck((value) => value + 1);
      }
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof ApiError
        ? err.message
        : "The generation request could not be confirmed. Check again to see whether it started.");
    } finally {
      submission.current = null;
      if (!controller.signal.aborted) setGenerating(false);
    }
  }

  const inProgress = revamp ? revampInProgress(revamp) : false;
  const images = revamp?.images.filter((image) => image.persona_id === selectedPersona)
    .sort((a, b) => a.step - b.step) || [];
  const failedCount = revamp?.images.filter((image) => image.status === "failed").length || 0;
  const personaName = (id: string) => run.persona_definitions?.[id]?.name || personas.find((persona) => persona.id === id)?.name || id;

  return (
    <section className="improvements" aria-labelledby="improvements-heading">
      <button className="text-button improvements-back" onClick={onBack}>← Back to journey</button>
      <h3 ref={heading} tabIndex={-1} id="improvements-heading">Improvements</h3>
      <p className="improvements-intro">Proposed designs based on this run’s feedback. These images do not change your website.</p>

      {loading && <p className="improvements-loading" role="status">Checking for existing improvements…</p>}
      {error && (
        <div className="form-error" role="alert">
          <p>{error}</p>
          <button className="text-button" disabled={loading || generating} onClick={() => {
            setLoading(true);
            setCheck((value) => value + 1);
          }}>Check again</button>
        </div>
      )}

      {!loading && !revamp && !error && (
        <div className="improvements-overview">
          <span className="improvements-kicker">THE WHOLE RUN</span>
          <h4>Generate improvements</h4>
          <p>Create proposed designs for screenshots across all perspectives in this test.</p>
          <div className="improvements-counts">
            <span>{run.personas.length} {run.personas.length === 1 ? "perspective" : "perspectives"}</span>
            <span>{screenshotCount(run)} {screenshotCount(run) === 1 ? "screenshot" : "screenshots"}</span>
          </div>
          <button className="button primary" disabled={generating} onClick={generate}>
            {generating ? "Starting generation…" : "Generate improvements"}
          </button>
          <p className="improvements-note">Images appear as they finish. You can return to the journey or close this modal while generation continues.</p>
        </div>
      )}

      {revamp && (
        <>
          <div className="improvements-progress">
            <div role="status" aria-live="polite">
              <strong>{inProgress ? "Generating improvements" : revamp.status === "completed" ? "Improvements ready" : revamp.status === "partial" ? "Some improvements are ready" : "Generation failed"}</strong>
              <span>{revamp.completed_images} of {revamp.total_images} images ready{failedCount ? ` · ${failedCount} failed` : ""}</span>
            </div>
            <progress aria-label="Images generated" value={revamp.completed_images} max={Math.max(1, revamp.total_images)} />
            {inProgress && <p>You can browse each perspective while the remaining images are generated.</p>}
            {revamp.error && <p className="form-error" role="alert">{revamp.error}</p>}
          </div>
          <div className="detail-tabs" aria-label="Improvement perspectives">
            {run.personas.map((id) => (
              <button key={id} className={selectedPersona === id ? "selected" : ""} aria-pressed={selectedPersona === id} onClick={() => setSelectedPersona(id)}>
                {personaName(id)}
              </button>
            ))}
          </div>
          <div className="timeline improvements-timeline">
            {images.map((image) => {
              const step = run.results[image.persona_id]?.steps.find((step) => step.step === image.step);
              return (
                <div className="timeline-step" key={`${image.persona_id}-${image.step}`}>
                  <span className="step-number">{image.step}</span>
                  <div>
                    <div className="step-title">
                      <strong>{step?.action.replaceAll("_", " ") || `Step ${image.step}`}</strong>
                      <span>{image.status === "completed" ? "Ready" : image.status === "generating" ? "Generating…" : image.status === "failed" ? "Failed" : inProgress ? "Queued" : "Not generated"}</span>
                    </div>
                    <p>{image.reasoning}</p>
                    <div className="comparison-grid">
                      <figure>
                        <figcaption>Before</figcaption>
                        <ComparisonImage key={image.original_screenshot_url} url={image.original_screenshot_url} alt={`${personaName(image.persona_id)}, step ${image.step}, original screenshot`} />
                      </figure>
                      <figure>
                        <figcaption>Proposed improvement</figcaption>
                        {image.fixed_screenshot_url ? (
                          <ComparisonImage key={image.fixed_screenshot_url} url={image.fixed_screenshot_url} alt={`${personaName(image.persona_id)}, step ${image.step}, proposed improvement`} />
                        ) : (
                          <div className={`comparison-placeholder ${image.status === "failed" ? "comparison-error" : ""}`}>
                            {image.status === "failed" ? image.error || "This image could not be generated." : inProgress ? image.status === "generating" ? "Creating a proposed improvement…" : "Waiting for generation…" : "No proposed image is available for this step."}
                          </div>
                        )}
                      </figure>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {!images.length && <div className="empty-state"><h3>No screenshots for this perspective</h3><p>Choose another perspective to view its improvements.</p></div>}
          <div className="modal-actions"><button className="button secondary" onClick={onBack}>← Back to journey</button></div>
        </>
      )}
    </section>
  );
}
