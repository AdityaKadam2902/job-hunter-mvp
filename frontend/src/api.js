const BASE_URL = "http://localhost:8000";

export async function fetchTopJobs(limit = 20) {
  const res = await fetch(`${BASE_URL}/api/jobs/top?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to fetch jobs: ${res.status}`);
  return res.json();
}

export async function fetchApplications() {
  const res = await fetch(`${BASE_URL}/api/applications`);
  if (!res.ok) throw new Error(`Failed to fetch applications: ${res.status}`);
  return res.json();
}

export async function addApplication(jobId, status = "saved") {
  const res = await fetch(`${BASE_URL}/api/applications`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, status }),
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