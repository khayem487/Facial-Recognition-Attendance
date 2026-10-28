# Facial Recognition Attendance

[Open the live demo](https://khayem-facial-attendance.vercel.app/) · [Local installation](#run-locally) · [Validation](#validation)

A real Flask/OpenCV attendance application with webcam registration, reference matching and persistent attendance history. Each browser has its own demonstration workspace.

## What you can try

| Step | Behavior |
| --- | --- |
| Add a profile | Choose a demo alias, activate the camera, then explicitly capture and save a reference. |
| Mark attendance | Compare webcam images with references in this browser's workspace. Repeated matches within 20 seconds produce one pointage. |
| Review | Read only your workspace's profiles and attendance history. |
| Delete | Remove a profile, its reference image and associated pointages after confirming in the interface. |

Camera capture starts only after a click. Stopping the camera or leaving the page releases its tracks; an image already accepted by the server may still finish processing. The microphone is never requested. Frames are reduced to at most 1280 x 720 before transmission.

The cloud demo uses OpenCV Haar face detection and histogram similarity. That score is not a probability of identity or a production access-control decision. The optional local `face_recognition` engine remains available when installed.

## Private browser workspaces

- An unpredictable 256-bit HttpOnly, SameSite=Strict cookie grants access to one workspace. This is browser isolation, not a user-account login or cross-device synchronization.
- The raw cookie is never returned in JSON, placed in a URL or stored in source control. Server namespaces use its SHA-256 hash.
- Mutating routes require a derived CSRF header and same-origin requests. Personal API responses are noncacheable.
- On Vercel, references and metadata remain in private Blob objects under that workspace's prefix. Local mode uses one SQLite database per workspace.
- Names, identifiers and roles are rendered as text. The interface does not request phone numbers or salary.
- Deletion removes the selected profile, reference image, cooldown and associated history. Blob deletion first places a nonpersonal tombstone so another warm instance cannot keep matching a deleted reference.
- Earlier shared CSV/images/Blob objects are neither exposed to new visitors nor automatically imported or deleted.

The workspace cookie lasts 30 days. Delete your profiles before clearing site cookies if you want the stored references removed. Losing or expiring the cookie loses access to that workspace; this version has no account recovery or automatic retention cleanup. Browser isolation does not authenticate the person using a shared browser.

## Run locally

Use Python 3.12 with functional OpenCV native bindings:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:5000/. Local data is created in the ignored `.attendance-workspaces/` directory. Set `ATTENDANCE_DATA_DIR` to choose another local directory.

For the optional full local engine, install `requirements-full.txt`. Existing legacy images are not silently imported into a visitor's workspace.

## Vercel deployment

The existing project is connected to this repository: pushes to `main` build production, and other branches produce protected previews.

The private Blob integration supplies `BLOB_READ_WRITE_TOKEN` or platform store access in the Vercel environment. No additional provider, login secret or paid plan is required by browser isolation. Credentials stay outside Git. A storage failure returns a generic error rather than switching silently to temporary local storage.

`vercel.json` retains the actual Flask service and Python 3.12 configuration. OpenCV is pinned to 4.12.0.88 to retain the CascadeClassifier API. The Render/Docker configuration remains available for existing installations.

The live demo persists new workspace data in private Vercel Blob. Local mode persists in SQLite. This does not promise fixed response times or uninterrupted free hosting.

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
node --test tests/test_workspace_client.mjs
.\.venv\Scripts\python.exe tests/smoke_deployment.py http://127.0.0.1:5000 --expect-storage local-workspace-sqlite --face-image /path/to/public-test-fixture.jpg
```

The offline suite covers two-visitor isolation, CSRF/origin checks, bounded image decoding, local SQLite/private Blob parity, persistence, deletion retry, stale-reference removal and untouched legacy data. Frontend checks cover session bootstrap, CSRF headers, errors, bounded capture and honest similarity display.

The deployment smoke test uses two separate cookie jars. With an explicitly supplied public test fixture it registers one deliberately disposable profile, checks actual face matching, history and cooldown, verifies that another visitor cannot read/match/delete it, then deletes the fixture and verifies it no longer matches. It never opens a webcam or uses a personal image, and cleans up only its own test registration.

## Data and source

Private images, workspace databases, cookies, environment files and exports are excluded by `.gitignore` and `.vercelignore`. The application is a portfolio demonstration; it is not a production HR or biometric access-control system.
