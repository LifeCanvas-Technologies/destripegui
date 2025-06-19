import os, sys, time, csv, re
import math
import multiprocessing
import configparser
from pathlib import Path
from datetime import datetime
import traceback
import shutil
from win32event import CreateMutex
from win32api import GetLastError
from winerror import ERROR_ALREADY_EXISTS
from sys import exit
#import torch
import subprocess
from pprint import pprint
import math
from tabulate import tabulate

def pair_key_value_lists(keys, values):
    # utility function for building metadata dict

    d = {}
    for i in range(0, len(keys)):
        key = keys[i]
        val = values[i]
        if "Z step" in key:
            key = "Z step"
        if key != '':
            d[key] = val
    return d

def get_metadata(dir):
    # builds metadata dict

    metadata_path = os.path.join(dir['path'], 'metadata.txt')
    print(dir['path'])

    metadata_dict = {
        'channels': [],
        'tiles': []
    }
    sections = {
        'channel_vals': [],
        'tile_vals': []
    }
    with open(metadata_path, encoding="utf8", errors="ignore") as f:
        reader = csv.reader(f, dialect='excel', delimiter='\t')
        section_num = 0
        for row in reader:
            if section_num == 0:
                sections['gen_keys'] = row
                section_num += 1
                continue
            if section_num == 1:
                sections['gen_vals'] = row
                section_num += 1
                continue
            if section_num == 2:
                sections['channel_keys'] = row
                section_num += 1
                continue
            if section_num == 3:
                if row[0] != 'X':
                    sections['channel_vals'].append(row)
                    continue
                else:
                    sections['tile_keys'] = row
                    section_num += 2
                    continue
            if section_num == 5:
                sections['tile_vals'].append(row)

    d = pair_key_value_lists(sections['gen_keys'], sections['gen_vals'])
    metadata_dict.update(d)

    for channel in sections['channel_vals']:
        d = pair_key_value_lists(sections['channel_keys'], channel)
        metadata_dict['channels'].append(d)

    for tile in sections['tile_vals']:
        d = pair_key_value_lists(sections['tile_keys'], tile)
        metadata_dict['tiles'].append(d)
    
    
    pprint(metadata_dict)
    dir['metadata'] = metadata_dict
   
    dir['target_per_tile'] = get_target_number(dir)

def get_target_number(dir):
    # Calculates number of images in acquisition

    skips = sum(list(int(tile['Skip']) for tile in dir['metadata']['tiles']))
    z_block = float(dir['metadata']['Z_Block'])
    z_step = float(dir['metadata']['Z step'])
    try:
        steps_per_tile = max(math.ceil(z_block / z_step) - 1, 1)
    except:
        steps_per_tile = 1
    target = int(skips * steps_per_tile)

    # log("Target number calculation for {}:".format(dir['path']), False)
    # log('skips: {}, z_block: {}, z_step: {}, target: {}'.format(skips, z_block, z_step, target), False)
    return steps_per_tile

    