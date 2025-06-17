import os, cv2
from PIL import Image
from datetime import datetime
import gc
directory = 'C:/image_test'

start = datetime.now()
for filename in os.listdir(directory):
    try:
        # img = Image.open(os.path.join(directory, filename))
        # img.verify()
        img = cv2.imread(os.path.join(directory, filename))
        
    except:
        print("Bad file: {}".format(filename))
time = datetime.now() - start
print("Total time: {} seconds".format(time.seconds))