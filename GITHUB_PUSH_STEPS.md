# Steps to Push to GitHub as "face_recognition"

## ⚠️ IMPORTANT: Restart Your Terminal First!

After installing Git, you **must restart your terminal/PowerShell** for it to work.

---

## Step 1: Restart Terminal & Verify Git

1. **Close this terminal/PowerShell window completely**
2. **Open a new terminal/PowerShell**
3. **Navigate to your project:**
   ```bash
   cd "C:\Users\khaye\OneDrive\Documents\project to e portfolio\facerecog2"
   ```
4. **Verify Git is installed:**
   ```bash
   git --version
   ```
   (Should show something like `git version 2.x.x`)

---

## Step 2: Initialize Git Repository

```bash
git init
```

---

## Step 3: Add All Files

```bash
git add .
```

This will add all files except those in `.gitignore` (like `attendance.csv` and personal images).

---

## Step 4: Make Your First Commit

```bash
git commit -m "Initial commit: Facial Recognition Attendance System"
```

---

## Step 5: Create Repository on GitHub

1. Go to **https://github.com** and sign in
2. Click the **"+"** icon in the top right → **"New repository"**
3. **Repository name:** `face_recognition` (exactly as you want it)
4. **Description:** "Facial Recognition Attendance System using Python, Flask, and OpenCV"
5. Choose **Public** or **Private**
6. **DO NOT** check "Add a README file" (we already have one)
7. **DO NOT** check "Add .gitignore" (we already have one)
8. **DO NOT** check "Choose a license" (we already have one)
9. Click **"Create repository"**

---

## Step 6: Connect and Push to GitHub

After creating the repository, GitHub will show you commands. Use these:

```bash
# Replace YOUR_USERNAME with your actual GitHub username
git remote add origin https://github.com/YOUR_USERNAME/face_recognition.git

# Set branch to main
git branch -M main

# Push to GitHub
git push -u origin main
```

**Note:** You'll be asked for your GitHub username and password (or personal access token).

---

## Step 7: Update README with Your GitHub Username

After pushing, edit `README.md` and replace:
- `YOUR_USERNAME` with your actual GitHub username (in 2 places)

---

## That's It! 🎉

Your repository will be live at:
**https://github.com/YOUR_USERNAME/face_recognition**

---

## Troubleshooting

**If Git still doesn't work after restarting:**
- Make sure Git was installed with "Add to PATH" option
- Try restarting your computer
- Or use GitHub Desktop instead (easier GUI option)

**If you get authentication errors:**
- GitHub no longer accepts passwords for Git operations
- You need a **Personal Access Token** instead
- Create one at: https://github.com/settings/tokens
- Use the token as your password when pushing

