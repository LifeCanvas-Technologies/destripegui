import numpy as np
import tifffile
from scipy import fftpack, ndimage

img_path = 'C:/image_testing/test1.tiff'
save_path = 'C:/image_testing/test_manipulated2.tiff'

rotate_deg = 1
scale = 1.05
shift_x = 6
shift_y = 12
crop_x = 2000
crop_y = 1600

d1 = 2
d2 = 4

img = tifffile.imread(img_path)
print('input:')
print('shape: {}'.format(np.shape(img)))
print('d1,d1: {}, d2,d1: {}, d1,d2: {}, d2,d2: {}'.format(img[d1,d1], img[d2,d1], img[d1,d2],img[d2,d2]))

# print(np.shape(img))
if scale != 1:
    img = ndimage.zoom(img, scale)
    print('scaled:')
    print('shape: {}'.format(np.shape(img)))
    print('d1,d1: {}, d2,d1: {}, d1,d2: {}, d2,d2: {}'.format(img[d1,d1], img[d2,d1], img[d1,d2],img[d2,d2]))

if rotate_deg != 0:
    img = ndimage.rotate(img, rotate_deg, reshape=False)
    print('rotated:')
    print('shape: {}'.format(np.shape(img)))
    print('d1,d1: {}, d2,d1: {}, d1,d2: {}, d2,d2: {}'.format(img[d1,d1], img[d2,d1], img[d1,d2],img[d2,d2]))

if shift_x != 0 or shift_y != 0:
    img = np.roll(img, (shift_x, shift_y), (1,0))
    print('shifted:')
    print('shape: {}'.format(np.shape(img)))
    print('d1,d1: {}, d2,d1: {}, d1,d2: {}, d2,d2: {}'.format(img[d1,d1], img[d2,d1], img[d1,d2],img[d2,d2]))

if crop_x != 0 or crop_y != 0:
    (input_x, input_y) = np.shape(img)
    if crop_x == 0 or crop_x > input_x: crop_x = input_x
    if crop_y == 0 or crop_y > input_y: crop_y = input_y
    offset_x = int((input_x - crop_x) / 2)
    offset_y = int((input_y - crop_y) / 2)
    img = img[offset_y:(crop_y + offset_y), offset_x:(crop_x + offset_x)]
    print('cropped:')
    print('shape: {}'.format(np.shape(img)))
    print('d1,d1: {}, d2,d1: {}, d1,d2: {}, d2,d2: {}'.format(img[d1,d1], img[d2,d1], img[d1,d2],img[d2,d2]))

tifffile.imwrite(save_path, img)