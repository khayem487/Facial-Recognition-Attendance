# Image Attendance Folder

This folder contains reference face images for the facial recognition system.

## How to Use

1. **Add Images**: Place one clear, front-facing photo of each person in this folder
2. **Naming**: The filename (without extension) will be used as the person's name
   - Example: `john.jpg` → Name: "JOHN"
   - Example: `sarah_smith.png` → Name: "SARAH_SMITH"
3. **Format**: Supported formats: `.jpg`, `.jpeg`, `.png`
4. **Quality**: Use clear, well-lit photos with the face clearly visible

## Example Structure

```
imageAttendance/
├── john.jpg
├── sarah.png
├── alex_smith.jpeg
└── ...
```

## Privacy Note

By default, this folder is excluded from Git to protect privacy. If you want to include sample images for demonstration, modify the `.gitignore` file accordingly.

