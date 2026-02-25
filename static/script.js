document.addEventListener("DOMContentLoaded", () => {
  const cameraFeed = document.getElementById("camera-feed");
  const startAttendanceButton = document.getElementById("start-attendance");
  const attendanceStatus = document.getElementById("attendance-status");
  const employeeNameElem = document.getElementById("employee-name");

  if (!cameraFeed || !startAttendanceButton) {
    return;
  }

  let isCameraActive = false;
  let stream = null;
  let intervalId = null;

  async function startCamera() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: true });
      const video = document.createElement("video");
      video.srcObject = stream;
      video.muted = true;
      await video.play();
      video.style.width = "100%";
      video.style.height = "100%";
      cameraFeed.innerHTML = "";
      cameraFeed.appendChild(video);

      isCameraActive = true;
      startAttendanceButton.textContent = "Camera Running";
      startAttendanceButton.disabled = true;

      intervalId = setInterval(() => {
        if (isCameraActive) {
          captureAndSendFrame(video);
        }
      }, 1200);
    } catch (err) {
      alert("Error accessing the camera: " + err.message);
    }
  }

  async function captureAndSendFrame(video) {
    if (!video.videoWidth || !video.videoHeight) return;

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const imageData = canvas.toDataURL("image/jpeg");

    try {
      const response = await fetch("/process_frame", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ frame: imageData })
      });

      const result = await response.json();
      if (result.success && attendanceStatus && employeeNameElem) {
        employeeNameElem.innerText = result.name || "VISITOR";
        attendanceStatus.style.display = "block";
      }
    } catch (err) {
      console.error("Recognition error:", err);
    }
  }

  startAttendanceButton.addEventListener("click", () => {
    if (!isCameraActive) {
      startCamera();
    }
  });

  window.addEventListener("beforeunload", () => {
    isCameraActive = false;
    if (intervalId) clearInterval(intervalId);
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
    }
  });
});
