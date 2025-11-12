import cv2
import numpy as np
import face_recognition

imgkhayem = face_recognition.load_image_file("imagesbase/khayem.jpg")
imgkhayem = cv2.cvtColor(imgkhayem, cv2.COLOR_BGR2RGB)
imgkhayemtest = face_recognition.load_image_file("imagesbase/khayem test.jpg")
imgkhayemtest = cv2.cvtColor(imgkhayemtest, cv2.COLOR_BGR2RGB)

faceloc = face_recognition.face_locations(imgkhayem)[0]
encodekhayem = face_recognition.face_encodings(imgkhayem)[0]
cv2.rectangle(imgkhayem,(faceloc[3],faceloc[0]),(faceloc[1],faceloc[2]),(255,0,0),2)
faceloctest = face_recognition.face_locations(imgkhayemtest)[0]
encodekhayemtest = face_recognition.face_encodings(imgkhayemtest)[0]
cv2.rectangle(imgkhayemtest,(faceloctest[3],faceloctest[0]),(faceloctest[1],faceloctest[2]),(255,0,0),2)

results=face_recognition.compare_faces([encodekhayem],encodekhayemtest)
facedis = face_recognition.face_distance([encodekhayem],encodekhayemtest)
print(results,facedis)
cv2.putText(imgkhayemtest,f'{results}{round(facedis[0],2)}',(50,50),cv2.FONT_HERSHEY_SIMPLEX,1,(255,0,0),2)


cv2.imshow("khayem", imgkhayem)
cv2.imshow("khayemtest", imgkhayemtest)
cv2.waitKey(0)