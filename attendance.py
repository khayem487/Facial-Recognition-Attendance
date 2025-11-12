import cv2
import numpy as np
import face_recognition
import os
from datetime import datetime

path = 'imageAttendance'
images=[]
classnames=[]
mylist = os.listdir(path)
print(mylist)
# Filter for image files only
image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
for cl in mylist:
    # Skip non-image files (like README.md)
    if not any(cl.lower().endswith(ext) for ext in image_extensions):
        continue
    curimg = cv2.imread(f'{path}/{cl}')
    # Only add if image loaded successfully
    if curimg is not None:
        images.append(curimg)
        classnames.append(os.path.splitext(cl)[0])
print(classnames)

def findencodings(images):
    encodelist = []
    for img in images:
        if img is None:
            continue
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        encodes = face_recognition.face_encodings(img)
        if len(encodes) > 0:
            encodelist.append(encodes[0])
    return encodelist

def markattendance(name):
    file_path = 'attendance.csv'
    file_exists = os.path.exists(file_path)

    with open(file_path, 'a+', encoding='utf-8') as f:
        if not file_exists:
            f.write('Name;Time\n')
        now = datetime.now()
        dtstring = now.strftime("%d/%m/%Y %H:%M:%S")
        f.write(f'{name};{dtstring}\n')

encodelistknown = findencodings(images)
print('encoding complete')

cap = cv2.VideoCapture(0)

while True:
    success, img = cap.read()
    imgs = cv2.resize(img,(0,0),None,0.25,0.25)
    imgs = cv2.cvtColor(imgs, cv2.COLOR_BGR2RGB)

    facescurframe = face_recognition.face_locations(imgs)
    encodecurframe = face_recognition.face_encodings(imgs,facescurframe)

    for encodeface,faceloc in zip(encodecurframe,facescurframe):
        matches = face_recognition.compare_faces(encodelistknown,encodeface)
        facedis = face_recognition.face_distance(encodelistknown,encodeface)
        print(facedis)
        matchindex = np.argmin(facedis)

        if matches[matchindex]:
            name = classnames[matchindex].upper()
            print(name)
            y1, x2, y2, x1 = faceloc
            y1, x2, y2, x1 = y1*4, x2*4, y2*4, x1*4
            cv2.rectangle(img, (x1, y1), (x2, y2), (255, 0, 0), 2)
            cv2.rectangle(img, (x1, y2-35), (x2, y2), (255, 0, 0), cv2.FILLED)
            cv2.putText(img,name,(x1+6,y2-6),cv2.FONT_HERSHEY_PLAIN,1,(255,255,255),2)
            markattendance(name)

    cv2.imshow('webcam', img)
    cv2.waitKey(1)