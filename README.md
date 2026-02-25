# Facial Recognition Attendance System

Python + Flask project for attendance marking from webcam frames.

This repository now includes a **cloud-ready web demo** (Render free tier) and a **full local mode** with `face_recognition`.

## What runs in cloud demo mode

- Browser webcam capture (client-side)
- Frame processing in Flask backend
- Attendance logging to `attendance.csv`
- Fallback face detection (OpenCV Haar cascade)

> Full face-encoding recognition with `face_recognition` is optional and intended for local/full installs.

## One-click deploy (Render)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/khayem487/Facial-Recognition-Attendance)

Render free instance may sleep after inactivity.

## Tech stack

- Python 3.11
- Flask
- OpenCV
- NumPy
- Gunicorn
- Optional: `face_recognition`

## Run locally

### A) Cloud-equivalent mode (lightweight, no dlib)

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Open: `http://127.0.0.1:5000/mark_attendance_page`

### B) Full recognition mode (optional)

```bash
pip install -r requirements-full.txt
python app.py
```

If `face_recognition` is installed and valid reference images exist in `imageAttendance/`, the app switches to full recognition mode.

## Project structure

```text
Facial-Recognition-Attendance/
├── app.py
├── requirements.txt
├── requirements-full.txt
├── Dockerfile
├── render.yaml
├── imageAttendance/
├── static/
├── templates/
└── docs/
```

## Privacy note

`attendance.csv` and real face images are ignored by git (`.gitignore`) to avoid publishing personal data.
