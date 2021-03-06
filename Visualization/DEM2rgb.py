"""
    Downloads the corresponding rgb image to a input DEM file, using Google earth engine data.
    Example 'python3 DEM2rgb.py sample/temp.tif'
    Output should be sample/temp.jpg

    *Note, Image is resized to match input DEM width, height*
"""
import os, sys
DEM = sys.argv[1]
DEMorig = DEM
tempdir = "tempdir"
os.system("mkdir " + tempdir)
if(os.path.isfile(tempdir + "/" + "temp.tif")):
    os.remove(tempdir + "/" + "temp.tif")

os.system("gdalwarp -ot Float32 -q " + DEM + " " + tempdir + "/" + "temp.tif")
DEM = "temp"

outdir = tempdir
SATELLITE_SR = "COPERNICUS/S2_SR"
SCALE = 50
PERCENTILE_SCALE = 50  # Resolution in meters to compute the percentile at


import ee
import time
import requests
import rasterio
import rasterio.features
import rasterio.warp
import numpy as np
from requests.auth import HTTPBasicAuth
import re
import urllib
import zipfile
import glob, os
from PIL import Image

with rasterio.open(outdir + "/" + DEM + ".tif") as dataset:

    # Read the dataset's valid data mask as a ndarray.
    mask = dataset.dataset_mask()

    # Extract feature shapes and values from the array.
    for geom, val in rasterio.features.shapes(
            mask, transform=dataset.transform):

        # Transform shapes from the dataset's own coordinate
        # reference system to CRS84 (EPSG:4326).
        geom = rasterio.warp.transform_geom(
            dataset.crs, 'EPSG:4326', geom, precision=6)
        # Print GeoJSON shapes to stdout.
        print("Geometry selected:")
        print(geom)


Xmin = geom['coordinates'][0][0][0]
Xmax = geom['coordinates'][0][0][0]
Ymin = geom['coordinates'][0][0][1]
Ymax = geom['coordinates'][0][0][1]
RGB = ['B4', 'B3', 'B2']
#RGB = ['TCI_R', 'TCI_G', 'TCI_B'] # for true color
for coord in geom['coordinates'][0]:
    if coord[0] < Xmin:
        Xmin = coord[0]
    elif coord[0] > Xmax:
        Xmax = coord[0]
    if coord[1] < Ymin:
        Ymin = coord[1]
    elif coord[1] > Ymax:
        Ymax = coord[1]

def mask_l8_sr(image):
    # Bits 3 and 5 are cloud shadow and cloud, respectively.
    cloud_shadow_bit_mask = (1 << 3)
    clouds_bit_mask = (1 << 5)
    # Get the pixel QA band.
    qa = image.select('pixel_qa')
    # Both flags should be set to zero, indicating clear conditions.
    mask = qa.bitwiseAnd(cloud_shadow_bit_mask).eq(0) and (qa.bitwiseAnd(clouds_bit_mask).eq(0))
    return image.updateMask(mask)

region = '[[{}, {}], [{}, {}], [{}, {}], [{}, {}]]'.format(Xmin, Ymax, Xmax, Ymax, Xmax, Ymin, Xmin, Ymin)
ee.Initialize()
print("Region selected from Geometry:")
print(region)
# dataset = ee.ImageCollection(SATELLITE_SR).filterBounds(geom).map(mask_l8_sr).select(RGB)
dataset = ee.ImageCollection(SATELLITE_SR).filterBounds(geom).select(RGB)
image = dataset.reduce('median')
percentiles = image.reduceRegion(ee.Reducer.percentile([0, 100], ['min', 'max']),
                                 geom, PERCENTILE_SCALE, bestEffort=True).getInfo()

mymin = [percentiles['B4_median_min'], percentiles['B3_median_min'], percentiles['B2_median_min']]
mymax = [percentiles['B4_median_max'], percentiles['B3_median_max'], percentiles['B2_median_max']]

minn = np.amax(np.array(mymin))
maxx = np.amin(np.array(mymax))

NEWRGB = ['B4_median', 'B3_median', 'B2_median']
# NEWRGB = ['TCI_R_median', 'TCI_G_median', 'TCI_B_median'] # for true color
reduction = image.visualize(bands=NEWRGB,
                            min=[minn, minn, minn], # reverse since bands are given in the other way (b2,b3,4b)
                            max=[maxx, maxx, maxx],
                            gamma=1)

path = reduction.getDownloadUrl({
    'scale': SCALE,
    'crs': 'EPSG:4326',
    'maxPixels': 1e20,
    'region': region,
    'bestEffort': True
})
print("Downloading file:")
print(path)
file = re.search("docid=.*&", path).group()[:-1][6:]

urllib.request.urlretrieve(path, outdir + "/" + file + ".zip")

with zipfile.ZipFile(outdir + "/" + file + ".zip", 'r') as zip_ref:
    zip_ref.extractall(outdir)

for f in glob.glob(outdir + "/*.tfw"):
    os.remove(f)
os.remove(outdir + "/" + file + ".zip")

im = Image.open(DEMorig)
width, height = im.size

red    = Image.open(outdir + '/' + file + '.vis-red.tif')
green  = Image.open(outdir + '/' + file + '.vis-green.tif')
blue   = Image.open(outdir + '/' + file + '.vis-blue.tif')


rgb = Image.merge("RGB",(red,green,blue))
rgb = rgb.resize((int(width), int(height)),Image.ANTIALIAS)

rgb.save(outdir + "/rgb" + DEM + '.tif')
rgb.save(outdir + "/" + DEM + '.jpg')

os.system("gdal2xyz.py -band 1 -csv " + outdir + "/" + DEM + ".tif " + outdir + "/" + DEM + ".csv")

os.system("gdal_translate -of GTiff " + outdir + "/" + DEM + ".tif " + outdir + "/1" + DEM + ".tif")

os.system("cp tempdir/temp.jpg " + DEMorig[:-4] + ".jpg")

for f in glob.glob(outdir + "/*.xml"):
    os.remove(f)

os.system('rm -rf ' + tempdir)
