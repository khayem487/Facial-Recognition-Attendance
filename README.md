# Facial Recognition Attendance System

Python + Flask project for attendance marking from webcam frames.

This repository now includes a **cloud-ready web demo** (Render free tier) and a **full local mode** with `face_recognition`.

## What runs in cloud demo mode

- Browser webcam capture (client-side)
- User registration page (capture + save face snapshots)
- Attendance marking page with live status + recent logs
- Attendance logging to `attendance.csv`
- Lightweight fallback recognition using OpenCV face detection + face histogram matching

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

`attendance.csv`, `users.csv`, and real face images are ignored by git (`.gitignore`) to avoid publishing personal data.

## Vercel deployment — actual Flask application

**Live application: https://khayem-facial-attendance.vercel.app/**

The Vercel project is connected to this GitHub repository. Pushing to `main`
automatically builds production; other branches create protected previews.
Blob access remains configured in the Vercel environment, outside Git.
Private Blob storage protects object access; it does not itself authenticate
visitors to this application's public registration and attendance routes.
Use fictional test identities for this public demonstration.

Vercel runs the existing Flask routes, original webcam interface, OpenCV Haar face detection and histogram matching used by the Render cloud demo. It is not the static browser simulation previously linked from the portfolio. The optional `face_recognition`/dlib mode remains available for full local installations; this cloud deployment reports `mode: fallback` and matches with `fallback-hist`, as the original Render demo did.

Vercel has a read-only application filesystem. `blob_storage.py` therefore provides a private Vercel Blob adapter for reference images, registration metadata and attendance history. Private image objects have no anonymous public access. Separate event objects and conditional cooldown claims keep history shared across instances and prevent duplicate pointages. Short-lived in-process caches reduce repeated listings. Local and Render deployments without Blob credentials retain their CSV/filesystem backend.

Python is pinned to 3.12. OpenCV is pinned to 4.12.0.88 because OpenCV 5 removes the `CascadeClassifier` API used by this application. `vercel.json` exports the original Flask application and excludes local personal data, environments and tests from the function bundle.

Connect a private Blob store to this project, with `BLOB_READ_WRITE_TOKEN` set in the Vercel project environment. The deployed store began empty: existing face images and CSV records were not uploaded or migrated. Credentials stay in the project environment and ignored `.env*` files.

```sh
npx vercel@64.7.0 deploy --prod
python tests/smoke_deployment.py https://khayem-facial-attendance.vercel.app --face-image /path/to/public-test-fixture.jpg
```

The smoke test must use a deliberately disposable test identity and a supplied public fixture, never a personal photo. It creates one test registration and attendance event; the store owner must remove those scoped test objects afterward. On 20 October 2026 the actual deployed registration, server-side face match, attendance history and duplicate cooldown passed. All three test objects were removed afterward; the demo returned to zero registered users.

The observed health request took 0.68 seconds, registration 2.46 seconds and recognition with persistence 2.24 seconds. These are individual measurements, not latency or uptime guarantees. Vercel Functions can cold-start and have free-plan quotas. Render configuration remains available as a fallback.
