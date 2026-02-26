async function startWebcam(videoElement) {
  const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
  videoElement.srcObject = stream;
  videoElement.muted = true;
  await videoElement.play();
  return stream;
}

function stopWebcam(stream) {
  if (!stream) return;
  stream.getTracks().forEach(track => track.stop());
}

function captureFrame(videoElement) {
  const canvas = document.createElement("canvas");
  canvas.width = videoElement.videoWidth;
  canvas.height = videoElement.videoHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.9);
}

async function fetchRecentAttendance(targetEl) {
  if (!targetEl) return;

  try {
    const response = await fetch("/api/attendance/recent");
    const data = await response.json();
    const rows = data.rows || [];

    if (!rows.length) {
      targetEl.innerHTML = "<li class='muted'>No attendance records yet.</li>";
      return;
    }

    targetEl.innerHTML = rows
      .slice(0, 10)
      .map(
        row =>
          `<li><strong>${row.Name || "Unknown"}</strong> · ${row.Time || "-"} <span class='pill'>${row.Mode || "-"}</span></li>`
      )
      .join("");
  } catch (err) {
    targetEl.innerHTML = "<li class='muted'>Unable to load attendance log.</li>";
  }
}

function initAttendancePage() {
  const video = document.getElementById("attendance-video");
  const startBtn = document.getElementById("start-attendance");
  const stopBtn = document.getElementById("stop-attendance");
  const statusBox = document.getElementById("attendance-status");
  const employeeName = document.getElementById("employee-name");
  const employeeMode = document.getElementById("employee-mode");
  const employeeConfidence = document.getElementById("employee-confidence");
  const recentList = document.getElementById("recent-attendance-list");

  if (!video || !startBtn || !stopBtn) return;

  let stream = null;
  let timer = null;

  async function processFrame() {
    if (!video.videoWidth || !video.videoHeight) return;
    const frame = captureFrame(video);

    try {
      const response = await fetch("/process_frame", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frame })
      });

      const result = await response.json();
      if (result.success) {
        statusBox.classList.remove("hidden");
        employeeName.textContent = result.name || "Unknown";
        employeeMode.textContent = result.mode || "-";
        employeeConfidence.textContent =
          result.confidence !== null && result.confidence !== undefined
            ? `${Math.round(Number(result.confidence) * 100)}%`
            : "-";

        if (result.marked) {
          fetchRecentAttendance(recentList);
        }
      }
    } catch (err) {
      console.error("Attendance frame processing failed", err);
    }
  }

  startBtn.addEventListener("click", async () => {
    try {
      stream = await startWebcam(video);
      startBtn.disabled = true;
      stopBtn.disabled = false;
      timer = setInterval(processFrame, 1200);
    } catch (err) {
      alert("Unable to access camera: " + err.message);
    }
  });

  stopBtn.addEventListener("click", () => {
    if (timer) clearInterval(timer);
    timer = null;
    stopWebcam(stream);
    stream = null;
    startBtn.disabled = false;
    stopBtn.disabled = true;
  });

  fetchRecentAttendance(recentList);

  window.addEventListener("beforeunload", () => {
    if (timer) clearInterval(timer);
    stopWebcam(stream);
  });
}

function initCreateUserPage() {
  const video = document.getElementById("register-video");
  const startBtn = document.getElementById("start-camera-btn");
  const captureBtn = document.getElementById("capture-user-btn");
  const form = document.getElementById("create-user-form");
  const resultEl = document.getElementById("register-result");
  const usersList = document.getElementById("users-list");

  if (!video || !startBtn || !captureBtn || !form) return;

  let stream = null;

  async function refreshUsers() {
    if (!usersList) return;
    try {
      const response = await fetch("/api/users");
      const data = await response.json();
      const users = data.users || [];
      if (!users.length) {
        usersList.innerHTML = "<li class='muted'>No users registered yet.</li>";
        return;
      }
      usersList.innerHTML = users
        .map(
          user => `<li><strong>${user.name}</strong>${user.user_id ? ` · ${user.user_id}` : ""}</li>`
        )
        .join("");
    } catch (err) {
      usersList.innerHTML = "<li class='muted'>Unable to load users.</li>";
    }
  }

  startBtn.addEventListener("click", async () => {
    try {
      stream = await startWebcam(video);
      startBtn.disabled = true;
      captureBtn.disabled = false;
    } catch (err) {
      alert("Unable to access camera: " + err.message);
    }
  });

  captureBtn.addEventListener("click", async () => {
    if (!stream) {
      alert("Start the camera first.");
      return;
    }

    if (!video.videoWidth || !video.videoHeight) {
      alert("Camera not ready yet. Please wait a second.");
      return;
    }

    const frame = captureFrame(video);
    const payload = {
      name: form.name.value,
      id: form.id.value,
      mobile: form.mobile.value,
      designation: form.designation.value,
      salary: form.salary.value,
      frame
    };

    try {
      const response = await fetch("/api/register_user", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || "Registration failed");
      }

      resultEl.className = "feedback success";
      resultEl.textContent = `User ${data.user.name} registered successfully.`;
      form.reset();
      refreshUsers();
    } catch (err) {
      resultEl.className = "feedback error";
      resultEl.textContent = err.message;
    }
  });

  refreshUsers();

  window.addEventListener("beforeunload", () => {
    stopWebcam(stream);
  });
}

function initHomePage() {
  const healthEl = document.getElementById("health-summary");
  if (!healthEl) return;

  fetch("/health")
    .then(res => res.json())
    .then(data => {
      healthEl.textContent = `Mode: ${data.mode || "-"} · Known users: ${data.known_users ?? 0}`;
    })
    .catch(() => {
      healthEl.textContent = "Status unavailable.";
    });
}

document.addEventListener("DOMContentLoaded", () => {
  initHomePage();
  initAttendancePage();
  initCreateUserPage();
});
