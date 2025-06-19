import os
from pathlib import Path
from PIL import Image
from datetime import datetime
import gc
from tifffile import TiffFile

directory = r"D:\SmartSPIM_output\2025_06_17\20250617_16_25_59_File_Name_Destripe_DONE\Ex_561_Ch1\511900\511900_436660"
# directory = r"D:\SmartSPIM_output\2025_06_17\20250617_16_25_59_File_Name_Destripe_DONE\Ex_561_Ch1\511900\511900_462580"

# start = datetime.now()
# for filename in os.listdir(directory):
#     try:
#         img = Image.open(os.path.join(directory, filename))
#         img.verify()
#         # img = cv2.imread(os.path.join(directory, filename))
        
#     except:
#         print("Bad file: {}".format(filename))
# time = datetime.now() - start
# print("Total time: {} seconds".format(time.seconds))

start = datetime.now()
for filename in os.listdir(directory):
    path = os.path.join(directory, filename)
    with TiffFile(path) as img:
        if len(img.pages[0].tags) == 0:
            print("Bad file: {}".format(filename))
time = datetime.now() - start
print("Total time: {} seconds".format(time.seconds))