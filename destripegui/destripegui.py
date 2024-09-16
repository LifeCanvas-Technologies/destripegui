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

from destripegui.destripe.core import main as cpu_destripe
from destripegui.destripe.utils import find_all_images
from destripegui.destripe import supported_extensions

def get_configs(config_path):
    config = configparser.ConfigParser()   
    config.read(config_path)
    return config

def run_pystripe(input_path, output_path, current_dir):
    # input_path = Path(dir['path'])
    # output_path = Path(dir['output_path'])
    sig_strs = current_dir['metadata']['Destripe'].split('/')
    sigma = list(int(sig_str) for sig_str in sig_strs)

    # sigma = [256, 0]
    workers = int(configs['params']['workers'])
    chunks = int(configs['params']['chunks'])
    use_gpu = int(configs["params"]["use_gpu"])
    cpu_readers = int(configs["params"]["cpu_readers"])
    gpu_chunksize = int(configs["params"]["gpu_chunksize"])
    ram_loadsize = int(configs["params"]["ram_loadsize"])

    contents = os.listdir(input_path)
    if len(contents) == 1:
        # input_path = os.path.join(input_path, contents[0])
        # output_path = os.path.join(output_path, contents[0])
        use_gpu = 0

    if 'MIP' in input_path:
        use_gpu = 0

    if use_gpu:
        print("Using GPU Destriper")
        from destripegui.destripe.core_gpu import main as gpu_destripe
        cmd = ["-i", str(input_path),
                        "-o", str(output_path), 
                        "--sigma1", str(sigma[0]),
                        "--sigma2", str(sigma[1]),
                        "--cpu-readers", str(workers), 
                        "--gpu-chunksize", str(gpu_chunksize),
                        "--extra-smoothing", "True"]
        if ram_loadsize > 0:
            cmd.append("--ram-loadsize")
            cmd.append(str(ram_loadsize))
        print(cmd)
        
        gpu_destripe(cmd)        

    else:
        print("Using CPU Destriper")
        cpu_destripe(["-i", str(input_path),
                        "-o", str(output_path), 
                        "--sigma1", str(sigma[0]),
                        "--sigma2", str(sigma[1]),
                        "--workers", str(workers),
                        "--chunks", str(chunks)])
        
def pair_key_value_lists(keys, values):
    # utility function for building metadata dict

    d = {}
    for i in range(0, len(keys)):
        key = keys[i]
        val = values[i]
        if key != '':
            d[key] = val
    return d

def get_metadata(dir):
    # builds metadata dict

    metadata_path = os.path.join(dir['path'], 'metadata.txt')

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
    
    dir['metadata'] = metadata_dict
   
    dir['target_per_tile'] = get_target_number(dir)

def get_target_number(dir):
    # Calculates number of images in acquisition

    skips = sum(list(int(tile['Skip']) for tile in dir['metadata']['tiles']))
    z_block = float(dir['metadata']['Z_Block'])
    z_step = float(dir['metadata']['Z step (m)'])
    try:
        steps_per_tile = max(math.ceil(z_block / z_step) - 1, 1)
    except:
        steps_per_tile = 1
    target = int(skips * steps_per_tile)

    # log("Target number calculation for {}:".format(dir['path']), False)
    # log('skips: {}, z_block: {}, z_step: {}, target: {}'.format(skips, z_block, z_step, target), False)
    return steps_per_tile

def search_directory(search_dir, ac_list, depth):
    # Recursive search function through input_dir to find directories with metadata.txt.  Ignores no_list

    # try:
    #     contents = os.listdir(search_dir)
    # except WindowsError as e:
    #     log('Error: {} Input and output drives can be set by editing: {}'.format(e, config_path), False)
    #     log(traceback.format_exc(), False)
    #     messagebox.showwarning(title='Drive Access Error', message='Error: {}\nInput and output drives can be set by editing:\n{}'.format(e, config_path))
    #     return

    try:
        contents = os.listdir(search_dir)
    except:
        print('Could not access input directory: {}.'.format(input_dir))
        print('Make sure drive is accessible, and not open in another program.')
        x = input('Press Enter to retry...')
        search_loop()

    if 'metadata.txt' in contents:
        ac_list.append({
            'path': search_dir, 
            'output_path': os.path.join(output_dir, os.path.relpath(search_dir, input_dir))
        })
        # log("Adding {} to provisional Acquisition Queue".format(search_dir), False)
        return ac_list
    if depth == 0: return ac_list
    for item in contents:
        item_path = os.path.join(search_dir, item)
        if os.path.isdir(item_path) and item_path not in no_list:
            # try:
            #     ac_list = search_directory(input_dir, output_dir, item_path, ac_list, depth-1)
            # except: 
            #     log("Error encountered trying to add {} to New Acquisitions List:".format(item_path), True)
            #     log(traceback.format_exc(), True)
            #     log("Continuing on anyway...", True)
            #     pass
            ac_list = search_directory(item_path, ac_list, depth-1)
    return ac_list
        
def get_acquisition_dirs():
    # run recursive search for new directories.  Build metadata dicts. Checks metadata flags and folder names to make
    # sure its actually new, and adds to no_list if not 

    search_dir = input_dir
    ac_dirs = search_directory(search_dir, list(), depth=3)
            
    for dir in ac_dirs:
        try:
            get_metadata(dir)
        except:
            print('Could not parse metadata.txt for {}\n'.format(dir['path']))
            ac_dirs.remove(dir)
            no_list.append(dir['path'])
            
    unfinished_dirs = []    
    for dir in ac_dirs:
        # print(dir)
        destripe_string = dir['metadata']['Destripe']
        try:
            tag = ''
            for s in ['N', 'C', 'D', 'A']:
                if s in destripe_string:
                    tag = s
                    break
            if tag == 'N':
                no_list.append(dir['path'])
                continue
            elif tag == 'C':
                no_list.append(dir['path'])
                continue
            elif tag == 'D':
                no_list.append(dir['path'])
                continue
            elif tag == 'A':
                no_list.append(dir['path'])
                continue
            else: 
                unfinished_dirs.append(dir)
        except:
            print('Error encountered while checking metadata tags for {}:'.format(dir['path']))
            pass
    
    if len(unfinished_dirs) > 0: unfinished_dirs.sort(key=lambda x: x['path'])
    return unfinished_dirs

def count_tiles(dir):
    tiles = []
    for tile in dir['metadata']['tiles']:
        if tile['Skip'] == '0':
            expected = 1
        else:
            expected = dir['target_per_tile']
        laser = tile['Laser']
        filter = tile['Filter']
        x = tile['X']
        y = tile['Y']
        tile_path = os.path.join('Ex_{}_Ch{}'.format(laser, filter), x, '{}_{}'.format(x, y))
        input_images = len(os.listdir(os.path.join(dir['path'], tile_path)))
        try:
            output_images = len(os.listdir(os.path.join(dir['output_path'], tile_path)))
        except:
            output_images = 0      
        tiles.append({
            'path': tile_path,
            'input_images': input_images,
            'output_images': output_images,
            'expected': expected
        })
    dir['tiles'] = tiles

def show_output(ac_dirs, current_dir):
    headers = ['Tile', 'Images Expected', 'Images on Acquisition Drive', 'Images on Stitch Drive']
    data = []
    total_images = 0
    total_destriped = 0
    for tile in current_dir['tiles']:
        total_images += tile['expected']
        total_destriped += tile['output_images']
        data.append([
            tile['path'],
            tile['expected'],
            tile['input_images'],
            tile['output_images']
        ])
    print('Current Acquisition: {}\n'.format(current_dir['path']))
    print(tabulate(data, headers))
    pct = total_destriped / total_images
    bar_length = 72
    print('\nOVERALL DESTRIPING PROGRESS: {:.0%} [{}{}]'.format(pct, '#'*round(pct*bar_length), '-'*round((1-pct)*bar_length)))

    if len(ac_dirs) > 1:
        print('\nAdditional Acquisitions in Destriping Queue:')
        for i in range(1, len(ac_dirs)):
            print(ac_dirs[i]['path'])
    
def check_mips(current_dir):
    for item in os.listdir(current_dir['path']):
        if 'MIP' in item:
            input_path = os.path.join(current_dir['path'], item)
            output_path = os.path.join(current_dir['output_path'], item)
            try:
                output_images = len(os.listdir(output_path))
            except:
                output_images = 0

            if len(os.listdir(input_path)) != output_images:
                print('\nDestriping {}...\n'.format(item))
                run_pystripe(input_path, output_path, current_dir)

def finish_directory(dir):
    # print('finishing {}'.format(dir['path']))
    # Perform tasks needed once directory is finished destriping

    # log('Finishing {}...'.format(dir['path']), True)
    # log('    Average pystripe speed for acquisition: {:.2f} it/s'.format(average_speed[0]), True)
    no_list.append(dir['path'])
    # log('    Adding {} to No List'.format(dir['path']), True)
    # log('    Is pystripe running?: {}'.format(any(p.is_alive() for p in procs)), True)
    # progress_write(dir['path'], "Finished destriping {} images".format(processed_images))
    # duration = datetime.now() - start_time
    # progress_write(dir['path'], "Total time elapsed: {}".format(str(duration)))

    # add folder to "done queue"
    # done_queue.insert('', 'end', values=(
    #     os.path.relpath(dir['path'], input_dir),
    #     processed_images,
    #     ))

    # convert .orig images back, add metadata tags and rename folders
    # revert_images(dir)

    for file in Path(dir['path']).iterdir():
        file_name = os.path.split(file)[1]
        if Path(file).suffix in ['.txt', '.ini', '.json']:
            # log('    Copying {} to {}'.format(file_name, dir['output_path']), True)
            output_file = os.path.join(Path(dir['output_path']), file_name)
            shutil.copyfile(file, output_file)

    prepend_tag(dir, 'in', 'D')
    prepend_tag(dir, 'out', 'D')
    # x = input('about to rename...')
    append_folder_name(dir, 'in', configs['suffixes']['input_done'])
    append_folder_name(dir, 'out', configs['suffixes']['output_done'])

    # log(' finishing {}'.format(dir['path']), True)

def append_folder_name(dir, drive, msg, attempts = 0):
    if drive == 'in':
        path = dir['path'] 
    else:
        path = dir['output_path']

    try:
        split = os.path.split(path)
        if msg not in split[1]:
            new_dir_name = split[1] + msg
            new_path = os.path.join(split[0], new_dir_name)
            os.rename(path, new_path)
    except Exception as error:
        print(error)
        print('Cannot access {} to rename folder'.format(path))
        x = input('Make sure it is accessible and not open in another program, then press Enter to retry...\n')
        append_folder_name(dir, drive, msg)

def prepend_tag(dir, drive, msg):
    # prepend tag to metadata file
    
    if drive == 'in':
        metadata_path = os.path.join(dir['path'], 'metadata.txt')
    else:
        metadata_path = os.path.join(dir['output_path'], 'metadata.txt')
    try:
        with open(metadata_path, errors="ignore") as f:
            reader = csv.reader(f, dialect='excel', delimiter='\t')
            line_list = list(reader)
            
        destripe_position = line_list[0].index('Destripe')
        destripe = line_list[1][destripe_position]
        for char in 'ACDNacdn':
            destripe = destripe.replace(char, '')

        line_list[1][destripe_position] = msg + destripe
        # os.remove(metadata_path)
        with open(metadata_path, 'w', newline='') as f:
            writer = csv.writer(f, dialect='excel', delimiter='\t')
            for row in line_list:
                writer.writerow(row)
    except:
        print('Cannot access {} to change destripe tag'.format(metadata_path))
        x = input('Make sure it is accessible and not open in another program, then press Enter to retry...\n')
        prepend_tag(dir, drive, msg)

def abort(dir):
    # Perform tasks needed to respond to aborted acquisition
    
    print("\nAborting {}...\n".format(dir['path']))

    prepend_tag(dir, 'in', 'A')
    append_folder_name(dir, 'in', configs['suffixes']['input_abort'])

    if os.path.exists(dir['output_path']):
        if os.path.exists(os.path.join(dir['output_path'], 'metadata.txt')):
            prepend_tag(dir, 'out', 'A')
        append_folder_name(dir, 'out', configs['suffixes']['output_abort'])
            

def search_loop():
    while True:
        print('\n-------------\n\n')
        ac_dirs = get_acquisition_dirs()

        if len(ac_dirs) == 0:
            print("Waiting for new acquisitions...")
            time.sleep(5)
            continue
        if len(ac_dirs) > 0:
            current_dir = ac_dirs[0]
            count_tiles(current_dir)
            
            show_output(ac_dirs, current_dir)
            if safe_mode:
                x = input('Press Enter to exit program...')
                exit()

            finished = True
            for tile in current_dir['tiles']:
                if tile['output_images'] < tile['expected']:
                    finished = False
            if finished:
                print('\nAll tiles have been destriped.  Checking for Maximum Intensity Projections...')
                check_mips(current_dir)
                finish_directory(current_dir)
                continue

            destripe_tile = False
            waiting_tile = False

            for tile in current_dir['tiles']:
                if tile['input_images'] >= tile['expected'] and tile['output_images'] < tile['expected']:
                    destripe_tile = tile['path']
                    break

            if not destripe_tile:
                for tile in current_dir['tiles']:
                    if tile['input_images'] > 0 and tile['output_images'] == 0:
                        waiting_tile = tile
                        break 
            
            if destripe_tile:
                input_path = os.path.join(current_dir['path'], destripe_tile)
                output_path = os.path.join(current_dir['output_path'], destripe_tile)
                print('\nDestriping {}...\n'.format(destripe_tile))
                time.sleep(2)
                run_pystripe(input_path, output_path, current_dir)

            elif waiting_tile:
                print('\nWaiting for current tile: {} to finish being acquired...'.format(waiting_tile['path']))
                if stall_counter[0] == waiting_tile['path'] and stall_counter[1] == waiting_tile['input_images']:
                    stall_counter[2] += 1
                else:
                    stall_counter[0] = waiting_tile['path']
                    stall_counter[1] = waiting_tile['input_images']
                    stall_counter[2] = 0

                if stall_counter[2] > 60:
                    x = input('\nThis acquisition ({}) seems to be incomplete.  Mark as aborted (y/n)?\n'.format(current_dir['path']))
                    if x in 'yesYesyeahsure':
                        abort(current_dir)
                        continue
                time.sleep(5)

            else:
                time.sleep(5)
            
def main():
    if 'configs' not in globals():
        double_test = CreateMutex(None, 1, 'A unique mutex name')
        if GetLastError(  ) == ERROR_ALREADY_EXISTS:
            # Take appropriate action, as this is the second
            # instance of this script; for example:
            print('Another instance of destripegui is already running')
            exit(1)


    print('''
                                                                        
                                               ......              .....                        
                                           ...-=++++=-..       ..:-=+++=-:..                    
                                          ..=+=:...=+=-.        .-++-. .-=+-..                  
                                         .:+=.. ..==-..          ..=+-.  .-==.                  
                                        .:+=. ..-=-..              .:==:. .-==..                
                                    ..:-=+++===+=:.                  .-=====+++=:..             
                                 ..:-==-:::-=++=:                     .-++=--::--==-..          
                                ..=+-.      ..-==.                   .:==:.      .:==-..        
                               .:+=.    ..-:. .:=-.                  .=-.  .-:..    :==..       
                              ..+=.   ..-++=:  .:=:                 .-=.  .-++=:..   :=-.       
                              .-+.  ..:+=--+=.  .--.                :=:.  :==:=+=..   -+..      
                              .==.  .:=:..:+=.  ...                  ..   :==...-=..  :+:.      
                              .==  .:=.  .-=:.                            .=+:. .:=.. :+:.      
                              .-+:.-+=::-==:.    ..:-.           .:-:.     .-==-:-+=..=+:.      
                             ..=++=++++=-:.  .:-==++=:           .-+++=--.. ..:-=+++=+++:.      
                            .-=++==-:..    .:==-:::==:           .-+-::-=+-..   ..:--=+++=:..   
                          .-+==:..        .-+-.  .:=-.            :=-.   :==:.        .:-=+=:.  
                         .==:.           .:+=. ..:=-.             .:=-..  :==..           .-+-..
                        .+=.  ...:-====---++=--=+=-...           ....-++=--=+=---====:...   :+-.
                        =+:   .:+++=------====-:...--.           .:=:...-====-------=++=..  .=+:
                        ++:  .:+=..              .:=:             .-=.              ..-+=.   =+-
                        =+-  .-+:            ... .-=:             .-+:.....           .=+.. .=+:
                        .=+. .:+-.    ..:-==++++++++-.            :=+++++++==-:..     .==...-+-.
                         .-+-..=+=-::-=+=-:......:-+=:.          .-+=-:.. ..:-=+=-:::-=+-.:==:. 
                           :=++++++++=-:.         .:==:.        .-=-.          .:-=+++++++=-..  
                            ..::--::.    ..-..      .==:.      .-=-.     ..::.     .:---:..     
                         .--....          .:+=:..   .:+=.     .:=-.   ...-+-.           ...:-.. 
                          -+++++-.          .=++=:.  .-+-.    :=+:.  .-=++:.         .:=+++++.. 
                          .+=...-=+=.     .:=+++++=-..-+-.    :=+:.:=+++++=-..    .-=+=:..:+-.  
                           :+:  ..:=+:..:=+++=::..:-===+-.    :=+===:...:-=++=-:..=+-..  .==..  
                           .-=:. ..:++++=-:..      ..-++-.    :=+=:.       ..:-==++=..  .-=:.   
                            .:-===++=-:.     ...    .:=+-.    :=+-.    ...     ..:=++====-..    
                               .....       ..-+-.    .-+-.    :=+:.    :==:..       ....        
                             ....         .:+=+=:    .-+-.    :==:    .-+=+=..         ....     
                             .-++-:...    .==::==.   .-+-.    :==:   .:=-.-+-.    ...-=++..     
                             .-+-=+++=.   :+=:.-=:   .-+-.    :==:   .-+:.-+-.   -+++=-=+..     
                             .:+: ...-+-  .-=::+=:   .-+-.    :=+:   .-+=.=+:. .==:....==..     
                             ..=+:   .-=: ..=++=:.  .-++-.    .=+=:.  .-+++:. .=+:.  .=+:.      
                              ..:===--=+=  ..:-=+===+++-.     .:=++===++=:..  :=+=--=+=..       
                                ..::-=++=.     ...::-+=:       .-+=-::...    .-++=--:..         
                                     ..:==:..    ..-==:.        .-==:..   ..:-=-..              
                                        ..:=+=---=+=:.           ..-=+=--===-:.                 
                                           ..-==-:.                  .:===:.                    
                                                                  
    ''')

    global configs, input_dir, output_dir, no_list, stall_counter, safe_mode
    
    safe_mode = False
    try:
        if sys.argv[1] == '-s':
            safe_mode = True
    except:
        pass

    if safe_mode:
        print('\nRunning in Safe Mode.  No changes will be made to any files.\n')
    
    print('Reading config file...\n')

    config_path = Path(__file__).parent / 'data/config.ini'
    configs = get_configs(config_path)

    input_dir = Path(configs['paths']['input_dir'])
    output_dir = Path(configs['paths']['output_dir'])
    try:
        x = os.listdir(input_dir)
    except:
        print('Could not access input directory: {}.'.format(input_dir))
        print('Make sure drive is accessible, or change drive location in config file: {}'.format(config_path))
        x = input('Press Enter to retry...')
        main()
    try:
        x = os.listdir(output_dir)
    except:
        print('Could not access output directory: {}.'.format(output_dir))
        print('Make sure drive is accessible, or change drive location in config file: {}'.format(config_path))
        x = input('Press Enter to retry...')
        main()
    stall_counter = ['', 0, 0]
    no_list = []
    print('\nScanning {} for new acquisitions...\n'.format(input_dir))
    search_loop()
    

if __name__ == "__main__":
    main()
