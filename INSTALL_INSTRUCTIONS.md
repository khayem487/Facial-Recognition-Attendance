# Installation Instructions for Face Recognition

## The Issue
The `face-recognition` library requires `dlib`, which needs **CMake** to build from source on Windows.

## Solution: Install CMake

### Option 1: Install CMake (Recommended)
1. Download CMake from: https://cmake.org/download/
2. Choose "Windows x64 Installer"
3. **IMPORTANT**: During installation, check "Add CMake to system PATH"
4. Restart your terminal/PowerShell
5. Verify installation: `cmake --version`
6. Then run: `pip install face-recognition`

### Option 2: Use Conda (Alternative)
If you have Anaconda/Miniconda installed:
```bash
conda install -c conda-forge dlib
pip install face-recognition
```

### Option 3: Try Pre-built Wheel (May not work for Python 3.13)
```bash
pip install dlib-bin
pip install face-recognition --no-deps
pip install face-recognition-models Pillow
```

## After Installing CMake

Once CMake is installed, run:
```bash
pip install face-recognition
```

Then you can run the app:
```bash
python app.py
```

