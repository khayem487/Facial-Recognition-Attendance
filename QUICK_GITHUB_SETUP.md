# Quick GitHub Setup

## Option 1: Install Git (Recommended)

1. **Download Git for Windows:**
   - Go to: https://git-scm.com/download/win
   - Download and install (use default settings)
   - **Important:** Choose "Git from the command line and also from 3rd-party software" when prompted

2. **Restart your terminal/PowerShell**

3. **Then follow the commands below**

## Option 2: Use GitHub Desktop (Easier GUI)

1. **Download GitHub Desktop:**
   - Go to: https://desktop.github.com/
   - Install and sign in with your GitHub account

2. **In GitHub Desktop:**
   - File → Add Local Repository
   - Select your `facerecog2` folder
   - Click "Publish repository" button

---

## Quick Commands (After Git is installed):

```bash
# 1. Initialize git
git init

# 2. Add all files (respects .gitignore)
git add .

# 3. Make first commit
git commit -m "Initial commit: Facial Recognition Attendance System"

# 4. Create repository on GitHub.com first, then:
git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git
git branch -M main
git push -u origin main
```

**Note:** Replace `YOUR_USERNAME` and `REPO_NAME` with your actual GitHub username and repository name.

