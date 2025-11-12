document.addEventListener('DOMContentLoaded', () => {
    const cameraFeed = document.getElementById('camera-feed');
    const startAttendanceButton = document.getElementById('start-attendance');
    const attendanceStatus = document.getElementById('attendance-status');
    const employeeNameElem = document.getElementById('employee-name');
    let isCameraActive = false;
    let stream = null;

    async function startCamera() {
        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            const video = document.createElement('video');
            video.srcObject = stream;
            video.play();
            video.style.width = '100%';
            video.style.height = '100%';
            cameraFeed.innerHTML = '';
            cameraFeed.appendChild(video);

            isCameraActive = true;

            // Continuously capture frames and send to the backend
            setInterval(() => {
                if (isCameraActive) {
                    captureAndSendFrame(video);
                }
            }, 1000); // Process every 1 second
        } catch (err) {
            alert('Error accessing the camera: ' + err.message);
        }
    }

    async function captureAndSendFrame(video) {
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        const imageData = canvas.toDataURL('image/jpeg');

        try {
            const response = await fetch('/process_frame', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ frame: imageData }),
            });

            const result = await response.json();
            if (result.success) {
                employeeNameElem.innerText = result.name;
                attendanceStatus.style.display = 'block';
            }
        } catch (err) {
            console.error('Error during recognition:', err);
        }
    }

    // Attach event to start the camera feed
    startAttendanceButton.addEventListener('click', () => {
        if (!isCameraActive) {
            startCamera();
        }
    });
});
