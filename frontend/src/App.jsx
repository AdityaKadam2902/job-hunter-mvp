import { useEffect, useMemo, useState } from "react";
import { fetchResumes, fetchTopJobs, fetchApplications, addApplication, updateApplicationStatus } from "./api";
import SignalBars from "./SignalBars";

const STATUSES = ["saved", "applied", "interviewing", "offer", "rejected", "withdrawn"];

export default function App() {
  const [tab, setTab] = useState("matches");
  const [resumes, setResumes] = useState([]);
  const [activeResumeId, setActiveResumeId] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [applications, setApplications] = useState([]);
  const [expandedJobId, setExpandedJobId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function loadResumes() {
    const list = await fetchResumes();
    setResumes(list);
    if (list.length > 0 && !activeResumeId) setActiveResumeId(list[0].id);
    return list;
  }

  async function loadForProfile(resumeId) {
    if (!resumeId) return;
    setLoading(true);
    try {
      const [j, a] = await Promise.all([fetchTopJobs(resumeId, 20), fetchApplications(resumeId)]);
      setJobs(j);
      setApplications(a);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadResumes();
  }, []);

  useEffect(() => {
    if (activeResumeId) loadForProfile(activeResumeId);
  }, [activeResumeId]);

  async function handleTrack(jobId) {
    await addApplication(jobId, activeResumeId, "saved");
    await loadForProfile(activeResumeId);
  }

  async function handleStatusChange(applicationId, newStatus) {
    await updateApplicationStatus(applicationId, newStatus);
    await loadForProfile(activeResumeId);
  }

  const trackedUrls = useMemo(() => new Set(applications.map((a) => a.url)), [applications]);

  const statusCounts = useMemo(() => {
    const counts = Object.fromEntries(STATUSES.map((s) => [s, 0]));
    applications.forEach((a) => { counts[a.status] = (counts[a.status] || 0) + 1; });
    return counts;
  }, [applications]);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">◈</span>
          <div>
            <div className="brand-name">JOB HUNTER</div>
            <div className="brand-sub">signal console</div>
          </div>
        </div>

        <div className="profile-switcher">
          <div className="stats-heading">Profile</div>
          {resumes.map((r) => (
            <button
              key={r.id}
              className={`profile-btn ${r.id === activeResumeId ? "active" : ""}`}
              onClick={() => setActiveResumeId(r.id)}
            >
              {r.label}
            </button>
          ))}
        </div>

        <nav className="nav">
          <button className={tab === "matches" ? "active" : ""} onClick={() => setTab("matches")}>
            Incoming signals
          </button>
          <button className={tab === "board" ? "active" : ""} onClick={() => setTab("board")}>
            Application board
          </button>
        </nav>

        <div className="stats">
          <div className="stats-heading">Pipeline</div>
          {STATUSES.map((s) => (
            <div className="stat-row" key={s}>
              <span className="stat-label">{s}</span>
              <span className="stat-value">{statusCounts[s]}</span>
            </div>
          ))}
        </div>

        <div className="legend">
          <div className="stats-heading">Signal key</div>
          <div className="legend-item"><span>SIM</span> semantic similarity</div>
          <div className="legend-item"><span>SKL</span> skill keyword match</div>
          <div className="legend-item"><span>LVL</span> seniority fit</div>
          <div className="legend-item"><span>DOM</span> domain fit</div>
          <div className="legend-item"><span>AI</span> AI-role specificity</div>
        </div>
      </aside>

      <main className="main">
        {error && (
          <div className="banner banner-error">
            Connection lost — {error}. Is the backend running? (uvicorn app.api:app --reload)
          </div>
        )}

        {tab === "matches" && (
          <>
            <div className="main-header">
              <h1>Incoming signals</h1>
              <p>Ranked by your active resume against {jobs.length} tracked candidates.</p>
            </div>
            {loading ? (
              <div className="empty">Scanning...</div>
            ) : jobs.length === 0 ? (
              <div className="empty">No signal yet — run <code>python -m app.match</code> to populate the pipeline.</div>
            ) : (
              <div className="job-list">
                {jobs.map((job) => (
                  <div className="job-card-wrap" key={job.id}>
                    <div className="job-card">
                      <SignalBars breakdown={job.breakdown} />
                      <div className="job-score">{job.score.toFixed(2)}</div>
                      <div className="job-info">
                        <div className="job-title-row">
                          <strong>{job.title}</strong>
                          {job.sub_role_tags?.map((tag) => (
                            <span className="role-badge" key={tag}>{tag}</span>
                          ))}
                        </div>
                        <span>{job.company} · {job.seniority} · {job.engagement_type}</span>
                        <a href={job.url} target="_blank" rel="noreferrer">View posting ↗</a>
                      </div>
                      <button
                        className="why-btn"
                        onClick={() => setExpandedJobId(expandedJobId === job.id ? null : job.id)}
                      >
                        {expandedJobId === job.id ? "Hide" : "Why?"}
                      </button>
                      <button
                        className="track-btn"
                        disabled={trackedUrls.has(job.url)}
                        onClick={() => handleTrack(job.id)}
                      >
                        {trackedUrls.has(job.url) ? "Tracked" : "Track"}
                      </button>
                    </div>
                    {expandedJobId === job.id && (
                      <div className="why-panel">
                        <div className="why-row">
                          <span className="why-label">Matched skills</span>
                          {job.matched_skills.length > 0 ? (
                            <div className="skill-chips">
                              {job.matched_skills.map((s) => <span className="chip" key={s}>{s}</span>)}
                            </div>
                          ) : (
                            <span className="why-empty">No direct skill keyword matches — ranked on semantic similarity alone.</span>
                          )}
                        </div>
                        <div className="why-row">
                          <span className="why-label">Score breakdown</span>
                          <span className="why-text">
                            Similarity {job.breakdown.similarity} · Skills {job.breakdown.keyword} ·
                            {" "}Level fit {job.breakdown.seniority} · Domain fit {job.breakdown.domain} ·
                            {" "}AI-role fit {job.breakdown.ai_fit}
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}

        {tab === "board" && (
          <>
            <div className="main-header">
              <h1>Application board</h1>
              <p>{applications.length} tracked, across the pipeline below.</p>
            </div>
            <div className="board">
              {STATUSES.map((status) => (
                <div className="board-column" key={status}>
                  <div className="board-column-head">
                    <span>{status}</span>
                    <span className="board-count">{statusCounts[status]}</span>
                  </div>
                  {applications.filter((a) => a.status === status).map((a) => (
                    <div className="board-card" key={a.id}>
                      <strong>{a.title}</strong>
                      <span>{a.company}</span>
                      {a.notes && <p className="notes">{a.notes}</p>}
                      <select value={a.status} onChange={(e) => handleStatusChange(a.id, e.target.value)}>
                        {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  );
}