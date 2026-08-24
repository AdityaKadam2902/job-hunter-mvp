const BASE_URL = "http://localhost:8000";

export async function fetchResumes() {
  const res = await fetch(`${BASE_URL}/api/resumes`);
  if (!res.ok) throw new Error(`Failed to fetch resumes: ${res.status}`);
  return res.json();
}

export async function fetchTopJobs(resumeId, limit = 20) {
  const qs = resumeId ? `?limit=${limit}&resume_id=${resumeId}` : `?limit=${limit}`;
  const res = await fetch(`${BASE_URL}/api/jobs/top${qs}`);
  if (!res.ok) throw new Error(`Failed to fetch jobs: ${res.status}`);
  return res.json();
}

export async function fetchApplications(resumeId) {
  const qs = resumeId ? `?resume_id=${resumeId}` : "";
  const res = await fetch(`${BASE_URL}/api/applications${qs}`);
  if (!res.ok) throw new Error(`Failed to fetch applications: ${res.status}`);
  return res.json();
}

export async function addApplication(jobId, resumeId, status = "saved") {
  const res = await fetch(`${BASE_URL}/api/applications`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, resume_id: resumeId, status }),
  });
  if (!res.ok) throw new Error(`Failed to track job: ${res.status}`);
  return res.json();
}

export async function updateApplicationStatus(applicationId, status) {
  const res = await fetch(`${BASE_URL}/api/applications/${applicationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(`Failed to update status: ${res.status}`);
  return res.json();
}