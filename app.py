import base64
import cv2
import numpy as np
import face_recognition
import os
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# Path to reference images
path = 'imageAttendance'
images = []
classnames = []
mylist = os.listdir(path)
# Filter for image files only
image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
for cl in mylist:
    # Skip non-image files (like README.md)
    if not any(cl.lower().endswith(ext) for ext in image_extensions):
        continue
    curimg = cv2.imread(f'{path}/{cl}')
    # Skip if image couldn't be loaded
    if curimg is not None:
        images.append(curimg)
        classnames.append(os.path.splitext(cl)[0])
    else:
        print(f"Warning: Could not load image {cl}")

# Encode faces
def find_encodings(images):
    encodelist = []
    for img in images:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        encode = face_recognition.face_encodings(img)[0]
        encodelist.append(encode)
    return encodelist

# Mark attendance
def mark_attendance(name):
    file_path = 'attendance.csv'
    file_exists = os.path.exists(file_path)

    with open(file_path, 'a+', encoding='utf-8') as f:
        if not file_exists:
            f.write('Name;Time\n')
        now = datetime.now()
        dtstring = now.strftime("%d/%m/%Y %H:%M:%S")
        f.write(f'{name};{dtstring}\n')

# Initialize face encodings
encodelistknown = find_encodings(images)
print("Face encodings loaded.")

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/mark_attendance_page')
def mark_attendance_page():
    return render_template('mark_attendance_page.html')

@app.route('/create_user')
def create_user():
    return render_template('create_user.html')

@app.route('/process_frame', methods=['POST'])
def process_frame():
    # Receive the image from the frontend
    data = request.json
    frame_data = data['frame']
    frame_data = frame_data.split(',')[1]
    frame_bytes = base64.b64decode(frame_data)
    nparr = np.frombuffer(frame_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Resize for performance optimization
    imgs = cv2.resize(frame, (0, 0), None, 0.25, 0.25)
    imgs = cv2.cvtColor(imgs, cv2.COLOR_BGR2RGB)

    # Detect faces
    faces_cur_frame = face_recognition.face_locations(imgs)
    encodes_cur_frame = face_recognition.face_encodings(imgs, faces_cur_frame)

    for encode_face, face_loc in zip(encodes_cur_frame, faces_cur_frame):
        matches = face_recognition.compare_faces(encodelistknown, encode_face)
        face_dist = face_recognition.face_distance(encodelistknown, encode_face)
        match_index = np.argmin(face_dist)

        if matches[match_index]:
            name = classnames[match_index].upper()
            mark_attendance(name)
            return jsonify(success=True, name=name)

    return jsonify(success=False)

if __name__ == '__main__':
    app.run(debug=True)
