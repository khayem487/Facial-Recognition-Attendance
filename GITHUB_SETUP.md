# 🚀 GitHub Setup Guide

Follow these steps to publish your Facial Recognition Attendance System to GitHub:

## Step 1: Initialize Git Repository

```bash
# Navigate to your project directory
cd facerecog2

# Initialize git (if not already done)
git init
```

## Step 2: Add Files to Git

```bash
# Add all files (respects .gitignore)
git add .

# Check what will be committed
git status
```

## Step 3: Make Your First Commit

```bash
git commit -m "Initial commit: Facial Recognition Attendance System"
```

## Step 4: Create GitHub Repository

1. Go to [GitHub](https://github.com) and sign in
2. Click the **"+"** icon in the top right → **"New repository"**
3. Name it: `Facial-Recognition-Attendance` (or your preferred name)
4. **Don't** initialize with README, .gitignore, or license (we already have these)
5. Click **"Create repository"**

## Step 5: Connect Local Repository to GitHub

```bash
# Replace YOUR_USERNAME with your GitHub username
git remote add origin https://github.com/YOUR_USERNAME/Facial-Recognition-Attendance.git

# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

## Step 6: Update README with Your GitHub Username

After pushing, edit `README.md` and replace:
- `YOUR_USERNAME` with your actual GitHub username (appears in 2 places)

## Step 7: Optional - Add Repository Topics

On your GitHub repository page:
1. Click the gear icon ⚙️ next to "About"
2. Add topics: `python`, `flask`, `opencv`, `face-recognition`, `attendance-system`, `computer-vision`

## Step 8: Optional - Add Screenshots/Demo

Consider adding:
- A screenshot of the web interface
- A demo GIF showing the recognition in action
- Create a `screenshots/` folder and add images

## 🔒 Privacy Reminder

The `.gitignore` file is configured to exclude:
- `attendance.csv` (personal attendance logs)
- `imageAttendance/*` (personal face images)

If you want to include sample/demo images:
1. Remove the `imageAttendance/*` line from `.gitignore`
2. Add some non-personal sample images
3. Commit and push

---

**That's it!** Your project is now on GitHub and ready to share! 🎉

