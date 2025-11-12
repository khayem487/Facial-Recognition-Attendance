# Facial Recognition Attendance System

A Python + Flask project that uses OpenCV and `face_recognition` to detect faces from a webcam feed and log attendance automatically. Each time a known person is recognized, the app writes the person's name and the current timestamp to a CSV file. The project is tuned for GitHub publication and ready to showcase in a portfolio.

## Features
- Real-time face detection and recognition via OpenCV.
- Automatic attendance logging (Name;Timestamp) stored in `attendance.csv`.
- Web interface powered by Flask plus a standalone script for quick tests.
- Simple onboarding for new people: drop an image into `imageAttendance/`.
- Works offline after dependencies are installed.

## Tech Stack
- Python 3.9+
- Flask 3
- OpenCV (opencv-python)
- `face_recognition` (dlib powered)
- NumPy
- HTML/CSS/JavaScript

## Project Structure

```
Facial-Recognition-Attendance/
├── app.py                    # Flask application entry point
├── attendance.py             # Standalone webcam attendance script
├── basics.py                 # Minimal face-comparison example
├── attendance.csv            # Generated attendance log
│
├── imageAttendance/          # Known face images (filenames == labels)
├── imagesbase/               # Optional secondary image set
├── static/                   # CSS, JS, assets for the Flask UI
├── templates/                # HTML templates (index, mark attendance, etc.)
│
├── requirements.txt          # Python dependency pins
└── README.md                 # This guide
```

> **Privacy reminder:** `imageAttendance/`, `imagesbase/`, and `attendance.csv` contain personal data. Keep them out of public repos (already covered in `.gitignore`) or swap in anonymized/demo assets before publishing.

## How It Works

1. **Image preparation** — Place a clear front-facing image of each person inside `imageAttendance/`. The filename (without extension) becomes the displayed name.
2. **Encoding** — On startup, the app loads every image, generates face encodings (`face_recognition.face_encodings`), and caches them in memory.
3. **Recognition** — Web or desktop capture grabs frames from the webcam, finds faces, and compares encodings with the known set. Matches are labeled in the UI.
4. **Attendance logging** — Each unique match writes `Name;YYYY-MM-DD HH:MM:SS` to `attendance.csv`, skipping duplicates for the session/day depending on the script.

## Requirements

### Prerequisites (Install First!)

**⚠️ IMPORTANT:** Before installing Python packages, you must install **CMake** first. The `face_recognition` library requires `dlib`, which needs CMake to build.

**Windows users:**
1. **Install Visual Studio Build Tools** (required for compiling dlib):
   - Download from: https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022
   - Install "Desktop development with C++" workload
   - This includes the C++ compiler needed to build dlib
2. **Install CMake:**
   - Download from https://cmake.org/download/
   - Run the installer and **check "Add CMake to system PATH"** during installation
3. **Restart your terminal/PowerShell** after installation
4. Verify installations:
   - `cmake --version` (should show version number)
   - Visual Studio Build Tools should be installed
5. Then proceed to install Python dependencies below

**Linux users:**
```bash
sudo apt install cmake libdlib-dev libboost-all-dev python3-dev
```

**macOS users:**
```bash
brew install cmake
```

### Python Dependencies

`requirements.txt` contains the dependencies:

```
Flask>=3.0.3
opencv-python>=4.8.0
face-recognition>=1.3.0
numpy>=1.24.0
```

## Setup

1. **Clone** the repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Facial-Recognition-Attendance.git
   cd Facial-Recognition-Attendance
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   
   > **Note:** If you get a CMake error, make sure CMake is installed and added to your PATH, then restart your terminal before running this command.

4. **Add images** to `imageAttendance/` (filenames should match the desired label).

## Running the Web App

```bash
python app.py
# or: flask --app app run
```

Visit http://127.0.0.1:5000/mark_attendance_page to access the live feed, start the camera, and watch attendance entries appear in real time.

## Example Attendance Log

```
Name;Time
KHAYEM;12/11/2025 15:02:47
SARAH;12/11/2025 15:04:11
```

## Adding a New Person

1. Take a clear, well-lit, front-facing photo.
2. Rename it to the person's name (e.g., `alex.jpg`).
3. Copy it into `imageAttendance/`.
4. Restart `app.py` (or rerun `attendance.py`) so encodings refresh.

## Future Enhancements

- Multiple reference images per person for higher accuracy.
- Admin dashboard to view/export attendance history.
- Switch storage from CSV to SQLite/PostgreSQL.
- Authentication & user roles for managing faces/logs.
- Deploy on Raspberry Pi / Jetson for embedded setups.

## Author

**Khayem Ben Ghorbel**  
CY Tech, Cergy, France  
📧 [khayembg07@gmail.com](mailto:khayembg07@gmail.com)  
💼 [LinkedIn](www.linkedin.com/in/khayem-bg)  
💻 [GitHub](https://github.com/khayem487)

---

## Ready to Run?

```bash
python app.py
```

Open your browser to http://127.0.0.1:5000/mark_attendance_page and start marking attendance automatically.
