import pystripe
import os, sys, time, csv, re
import multiprocessing
import configparser
from pathlib import Path
from tkinter import *
from tkinter import ttk
from tkinter import messagebox
from datetime import datetime
import traceback


# [WinError 5] Access is denied: 'D:\\SmartSPIM_Data\\2022_07_15\\20220715_12_04_09_FileName' -> 'D:\\SmartSPIM_Data\\2022_07_15\\20220715_12_04_09_FileName_DST'

def log(message):
    now = datetime.now()
    if not os.path.exists(log_path):
        os.mkdir(log_path)
    month_str = "{}_{}".format(now.strftime('%Y'), now.strftime('%m'))
    month_log_dir = log_path / month_str
    if not os.path.exists(month_log_dir):
        os.mkdir(month_log_dir)
    day_name = "{}_{}_logging.txt".format(now.strftime('%m'), now.strftime('%d'))
    filename = month_log_dir / day_name
    with open(filename, "a") as f:
        time = now.strftime("%H:%M:%S")
        f.write("{}  -  {}\n".format(time, message))

def get_configs(config_path):
    config = configparser.ConfigParser()   
    config.read(config_path)
    return config

def run_pystripe(dir, configs):
    # Asynchronous function that runs pystripe batch_filter module and rename_images function

    log("Running pystripe on: {}".format(input_path))
    input_path = Path(dir['path'])
    output_path = Path(dir['output_path'])
    sig_strs = dir['metadata']['Destripe'].split('/')
    sigma = list(int(sig_str) for sig_str in sig_strs)
    workers = int(configs['params']['workers'])
    chunks = int(configs['params']['chunks'])
    
    with open('pystripe_output.txt', 'w') as f:
        sys.stdout = f
        sys.stderr = f
        pystripe.batch_filter(input_path,
                    output_path,
                    workers=workers,
                    chunks=chunks,
                    sigma=sigma,
                    auto_mode=True)
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
    
    log("Pystripe finished on: {}".format(input_path))
    rename_images(dir)

def rename_images(dir):
    # Appends .orig to images that have been destriped, after batch_filter finishes.  On same async thread as run_pystripe

    output_path = dir['output_path']
    input_path = dir['path']
    file_path = os.path.join(output_path, 'destriped_image_list.txt')
    with open(file_path, 'r') as f:
        image_list = f.readlines()
    images_len = len(image_list)
    log('Appending .orig to {} images in {}...'.format(str(images_len), input_path))

    for image in image_list:
        image = image.strip()
        try:
            os.rename(image, image + '.orig')
        except WindowsError as e:
            if e.winerror == 183:
                os.remove(image)
                log('    {}.orig already exists.  Deleting duplicate'.format(image))
        except:
            log(traceback.format_exc())
    log("Done renaming files in {}.  Deleting 'destriped_image_list.txt'".format(input_path))
    os.remove(file_path)

def search_directory(input_dir, output_dir, search_dir, ac_list, depth):
    # Recursive search function through input_dir to find directories with metadata.txt.  Ignores _DST and the no_list

    try:
        contents = os.listdir(search_dir)
    except WindowsError as e:
        log(traceback.format_exc())
        messagebox.showwarning('Windows Error', '{}\nInput and output drives can be set by editing:\n{}'.format(e, config_path))
    if 'metadata.txt' in contents:
        ac_list.append({
            'path': search_dir, 
            'output_path': os.path.join(output_dir, os.path.relpath(search_dir, input_dir))
        })
        log("Adding {} to provisional Acquisition Queue".format(search_dir))
        return ac_list
    if depth == 0: return ac_list
    for item in contents:
        item_path = os.path.join(search_dir, item)
        # print('isdir {}: {}'.format(item_path, os.path.isdir(item_path)))
        if os.path.isdir(item_path) and 'DST' not in item and item_path not in no_list:
            try:
                ac_list = search_directory(input_dir, output_dir, item_path, ac_list, depth-1)
            except: 
                log("Error encountered trying to add {} to New Acquisitions List:".format(item_path))
                log(traceback.format_exc())
                log("Continuing on anyway...")
                pass
    return ac_list

def get_acquisition_dirs(input_dir, output_dir):
    # run recursive search for new directories.  Build metadata dicts. Checks metadata flags and folder names to make
    # sure its actually new, and adds to no_list if not 

    global times
    search_dir = input_dir
    ac_dirs = search_directory(input_dir, output_dir, search_dir, list(), depth=3)
            
    for dir in ac_dirs:
        try:
            get_metadata(dir)
        except:
            log("An error occurred attempting to read metadata for {}:".format(dir['path']))
            log(traceback.format_exc())
            log("Adding {} to the No List".format(dir['path']))
            no_list.append(dir['path'])
            
    unfinished_dirs = []    
    for dir in ac_dirs:
        try:
            destripe_tag = dir['metadata']['Destripe']
            if 'N' in destripe_tag:
                no_list.append(dir['path'])
                log("Adding {} to No List because N/A flag set in metadata".format(dir['path']))
                continue
            elif 'D' in destripe_tag:
                no_list.append(dir['path'])
                log("Adding {} to No List becasue D flag set in metadata".format(dir['path']))
                continue
            elif dir['output_path'][-2:] == '_A':
                no_list.append(dir['path'])
                log("Adding {} to No List because _A flag set in output path".format(dir['path']))
                continue
            elif 'A' in destripe_tag:
                if pystripe_running == False:
                    abort(dir)
                else: log("Waiting for pystripe to finish before aborting {}".format(dir['path']))
            else: 
                unfinished_dirs.append(dir)
                log("Adding {} to final Acquisition Queue".format(dir['path']))
        except:
            log('Error encountered while checking metadata tags for {}:'.format(dir['path']))
            pass
    
    if len(unfinished_dirs) > 0: unfinished_dirs.sort(key=lambda x: x['path'])
    return unfinished_dirs

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
   
    dir['target_number'] = get_target_number(dir)
    print('target_number: {}'.format(dir['target_number']))


# def in_progress(dir):
    # destripe_tag = dir['metadata']['Destripe']
    # if 'N' in destripe_tag:
    # return 'D' not in destripe_tag and 'A' not in destripe_tag

def get_target_number(dir):
    # Calculates number of images in acquisition

    skips = list(int(tile['Skip']) for tile in dir['metadata']['tiles'])
    z_block = float(dir['metadata']['Z_Block'])
    z_step = float(dir['metadata']['Z step (m)'])
    target = int(sum(skips) * z_block / z_step)

    log("Target number calculation for {}:".format(dir['path']))
    log('skips: {}, z_block: {}, z_step: {}, target: {}'.format(skips, z_block, z_step, target))
    return target

def finish_directory(dir, processed_images):
    # Perform tasks needed once directory is finished destriping

    log('Finishing {}...'.format(dir['path']))
    no_list.append(dir['path'])
    log('    Adding {} to No List'.format(dir['path']))
    log('    Is pystripe running?: {}'.format(any(p.is_alive() for p in procs)))

    # add folder to "done queue"
    done_queue.insert('', 'end', values=(
        os.path.relpath(dir['path'], input_dir),
        processed_images,
        ))

    # convert .orig images back
    revert_count = 0
    for (root,dirs,files) in os.walk(dir['path']):
        for file in files:
            if Path(file).suffix == '.orig':
                file_path = os.path.join(root, file)
                try:
                    os.rename(file_path, os.path.splitext(file_path)[0])
                except Exception as e:
                    print(e)
                    pass
                revert_count += 1
    log('    Reverted {} images back from .orig'.format(revert_count))
     
    for path in [dir['output_path'], dir['path']]:
        # prepend 'D' to 'Destripe' label in metadata.txt
        log("    Adding 'D' to Destripe metadata tag in {}".format(path))
        metadata_path = os.path.join(path, 'metadata.txt')
        with open(metadata_path, errors="ignore") as f:
            reader = csv.reader(f, dialect='excel', delimiter='\t')
            line_list = list(reader)
        os.remove(metadata_path)
        destripe = line_list[1][6]
        line_list[1][6] = 'D' + destripe
        with open(metadata_path, 'w', newline='') as f:
            writer = csv.writer(f, dialect='excel', delimiter='\t')
            for row in line_list:
                writer.writerow(row)

        # append '_DST' to input and '_DONE to output directory name
        split = os.path.split(path)
        if path == dir['path']: suffix = '_DST'
        else: suffix = '_DONE'
        new_dir_name = split[1] + suffix
        new_path = os.path.join(split[0], new_dir_name)
        try:
            os.rename(path, new_path)
            log("    Adding '{}' to directory name : {}".format(suffix, path))
        except:
            log("    An error occurred while renaming {}:".format(path))
            log(traceback.format_exc())
            pass
    log('    Finished finishing {}'.format(dir['path']))
    
def abort(dir):
    # Perform tasks needed to respond to aborted acquisition
    
    log("Aborting {}...".format(dir['path']))
    no_list.append(dir['path'])
    if 'output_path' not in dir.keys():
        log('    No output path for {}: aborting abortion'.format(dir['path']))
        return

    # convert .orig images back
    revert_count = 0
    for (root,dirs,files) in os.walk(dir['path']):
        for file in files:
            if Path(file).suffix == '.orig':
                file_path = os.path.join(root, file)
                try:
                    os.rename(file_path, os.path.splitext(file_path)[0])
                    revert_count += 1
                except Exception as e:
                    log('    Error reverting image from .orig after aborted acquisition:')
                    log(traceback.format_exc())
                
    log('    Reverted {} images back from .orig'.format(revert_count))
    
    # append to A to output metadata destripe tag
    log('    Adding "A" to output metadata tag')
    metadata_path = os.path.join(dir['output_path'], 'metadata.txt')
    if not os.path.exists(metadata_path):
        dir['output_path'] += '_A'
        metadata_path = os.path.join(dir['output_path'], 'metadata.txt')
    if not os.path.exists(metadata_path):
        log('    Error: Cannot find metadata.txt path in output folder')
    else:        
        try:
            with open(metadata_path, errors="ignore") as f:
                reader = csv.reader(f, dialect='excel', delimiter='\t')
                line_list = list(reader)
            os.remove(metadata_path)
            destripe = line_list[1][6]
            if ('A' in destripe): log('    "A" already in output metadata')
            else: 
                line_list[1][6] = 'A' + destripe
                with open(metadata_path, 'w', newline='') as f:
                    writer = csv.writer(f, dialect='excel', delimiter='\t')
                    for row in line_list:
                        writer.writerow(row)
        except:
            log('    Error adding "A" to metadata tag:')
            log(traceback.format_exc())
            
    # append _A to output directory name
    log('    Appending "_A" to output path')
    if dir['output_path'][-2:] == '_A': log('    _A already in output path')
    else:
        try:
            split = os.path.split(dir['output_path'])
            new_dir_name = split[1] + '_A'
            new_path = os.path.join(split[0], new_dir_name)
            os.rename(dir['output_path'], new_path)
        except:
            log('    An error occured while appending "_A" to the output path:')
            log(traceback.format_exc())
    
    # append _A to input directory name
    log('    Appending "_A" to input path')
    if dir['path'][-2:] == '_A': log('    _A already in input path')
    else:
        try:
            split = os.path.split(dir['path'])
            new_dir_name = split[1] + '_A'
            new_path = os.path.join(split[0], new_dir_name)
            os.rename(dir['path'], new_path)
            print('renamed input path for: {}'.format(dir['path']))
        except:
            log('    An error occured while appending "_A" to the input path:')
            log(traceback.format_exc())
    log("Done aborting {}...".format(dir['path']))

# def update_status(active_dir):
#     current_dirs = []
#     extensions = pystripe.core.supported_extensions
#     # for dir in ac_dirs:
    
#     active_dir['unprocessed_images'] = 0
#     active_dir['orig_images'] = 0
#     active_dir['processed_images'] = 0

#     # get lists of processed and unprocessed images in input directory and processed images in output directory
#     for (root,dirs,files) in os.walk(active_dir['path']):
#         for file in files:
#             if Path(file).suffix in extensions:
#                 active_dir['unprocessed_images'] += 1
#             elif Path(file).suffix == '.orig':
#                 active_dir['orig_images'] += 1
#     current = 0
#     in_progress_list = os.path.join(active_dir['output_path'], 'destriped_image_list.txt')
#     if os.path.exists(in_progress_list):
#         with open(in_progress_list, 'r') as f:
#             current = len(f.readlines())
#     # print('currently being destriped: {}'.format(current))
#     active_dir['unprocessed_images'] -= current
    
#     for (root, dirs, files) in os.walk(active_dir['output_path']):
#         for file in files:
#             if Path(file).suffix in extensions:
#                 active_dir['processed_images'] += 1
    
    
#     if active_dir['processed_images'] >= active_dir['target_number']:
#         if pystripe_running: print('Waiting to finish {} until pystripe is complete'.format(active_dir['path']))
#         else: finish_directory(active_dir)
#     else:
#         current_dirs.append(active_dir)
    
#     return current_dirs

def count_processed_images(active_dir):
    # Count processed images in output path

    log("Begin image count for {}".format(active_dir['output_path']))
    processed_images = 0
    extensions = pystripe.core.supported_extensions
    for (root, dirs, files) in os.walk(active_dir['output_path']):
        for file in files:
            if Path(file).suffix in extensions:
                processed_images += 1
    log("Finish image count for {}".format(active_dir['output_path']))

    return processed_images

def update_message():
    # Move "searching for images...." message

    global counter, status_message
    period = 50
    count = counter % period
    if count < period/2:
        message = '-' * count + ' Searching for images ' + '-' * (int(period/2-1) - count)
    else:
        message = '-' * (period-1 - count) + ' Searching for images ' + '-' * (count - int(period/2))

    if searching:
        status_message.set(message)

def look_for_images():
    # Main loop

    global average_speed, progress_bar, searching, root, ac_queue, input_dir, output_dir, configs, procs, pystripe_running, counter, status_message, timer, output_widget
    
    # update GUI
    update_message()
    for item in ac_queue.get_children():
        ac_queue.delete(item)
    
    if not any(p.is_alive() for p in procs):
        pystripe_running = False
        output_widget.delete(1.0, 'end')
    else:
        get_pystripe_output()
        log('Average pystripe speed for acquisition: {:.2f} it/s'.format(average_speed[0]))
    
    # get acquisition directories
    acquisition_dirs = get_acquisition_dirs(input_dir, output_dir)
    
    if len(acquisition_dirs) > 0:
        active_dir = acquisition_dirs[0]
    # abort if A
        # if 'A' in active_dir['metadata']['Destripe'] and pystripe_running == False:
        #     abort(active_dir)
        #     acquisition_dirs.remove(active_dir)
        #     average_speed = [0,0]
        
    # finish if done
    if len(acquisition_dirs) > 0:
        active_dir = acquisition_dirs[0]
        processed_images = count_processed_images(active_dir)
        if processed_images >= active_dir['target_number'] and pystripe_running == False:
            finish_directory(active_dir, processed_images)
            acquisition_dirs.remove(active_dir)
            average_speed = [0,0]
            
    if len(acquisition_dirs) > 0:  
        # Add new acquisitions to GUI acquisition queue
        active_dir = acquisition_dirs[0]
        ac_queue.insert('', 'end', values=(
            os.path.relpath(active_dir['path'], input_dir),
            processed_images,
            active_dir['target_number']
        ))      
        for i in range(1, len(acquisition_dirs)):
            dir = acquisition_dirs[i]
            ac_queue.insert('', 'end', values=(
                os.path.relpath(dir['path'], input_dir),
                '0',
                dir['target_number']
            ))
              
# YOU ARE HERE


        pct = 100 * processed_images / active_dir['target_number']
        if pct > 100: pct = 100
        progress_bar['value'] = pct

        if pystripe_running == False and counter % 5 == 0:
            pystripe_running = True
            with open('pystripe_output.txt', 'w') as f:
                f.close()
            get_pystripe_output()
            p = multiprocessing.Process(target=run_pystripe, args=(active_dir, configs))
            procs.append(p)
            p.start()
            times['started pystripe'] = time.time()
    else:
        ac_queue.insert('', 'end', values=('No new acquisitions found...', '', '', ''))
        progress_bar['value'] = 0
    
    for key in times.keys():
        long_time = times[key]
        short_time = '{:.2f}'.format(long_time - timer)
        times[key] = short_time
    timer = time.time()
    counter += 1 
    root.after(1000, look_for_images) 

def update_average_speed(new_speed):
    global average_speed
    new_speed = float(new_speed)
    n = average_speed[1]
    avg = (average_speed[0] * n + new_speed) / (n + 1)
    # print('average pystripe speed for acquisition: {:.2f} it/s'.format(avg))
    average_speed = [avg, n+1]
    
def get_pystripe_output():
    global output_widget, pystripe_running, pystripe_progess, average_speed
    with open('pystripe_output.txt', 'r') as f:
        line_list = f.readlines()
    output_widget.delete(1.0, 'end')
    
    line_list2 = []
    first_line = True
    for line in line_list:
        if '%' in line:
            if not first_line: 
                line_list2[-1] = line
                regex = '(?<=, )(.*?)(?=it/s)'
                speed_list = re.findall(regex, line)
                try: update_average_speed(speed_list[0])
                except Exception as e:
                    pass
            else: 
                line_list2.append(line)
            first_line = False
        else: line_list2.append(line)
    output = ''.join(line_list2)
    output_widget.insert('end', output)
        
def build_gui():
    global status_message, button_text, searching, ac_queue, output_widget, done_queue, progress_bar, pb_length
    root.title("Destripe GUI")
    icon_path = Path(__file__).parent / 'data/lct.ico'
    root.iconbitmap(icon_path)

    mainframe = ttk.Frame(root, padding="3 3 12 12")
    
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    status_message = StringVar(mainframe, '')
    status_label = ttk.Label(mainframe, textvariable=status_message)

    # button_text = StringVar()
    # button_text.set('START')
    searching = True
    # start_button = ttk.Button(mainframe, textvariable=button_text, command=change_on_off, width=10)
    
    progress_label = ttk.Label(mainframe, text='Current Acquisiton Progress: ')
    progress_bar = ttk.Progressbar(mainframe, orient='horizontal', mode='determinate', length=630)
    
    output_label = ttk.Label(mainframe, text="Pystripe Output")
    output_widget = Text(mainframe, height=10, width=100)

    ac_label = ttk.Label(mainframe, text="Acquisition Queue")
    columns = ('folder_name', 'processed', 'total_images')
    ac_queue = ttk.Treeview(mainframe, columns=columns, show='headings', height=6)
    ac_queue.heading('folder_name', text='Folder Name')
    ac_queue.column("folder_name", minwidth=0, width=560, stretch=NO)
    ac_queue.heading('processed', text='Processed Images')
    ac_queue.column("processed", minwidth=0, width=125, stretch=NO)
    ac_queue.heading('total_images', text='Total Images')
    ac_queue.column("total_images", minwidth=0, width=125, stretch=NO)

    done_label = ttk.Label(mainframe, text="Destriped Acquisitions")
    columns = ('folder_name', 'total_images')
    done_queue = ttk.Treeview(mainframe, columns=columns, show='headings', height=8)
    done_queue.heading('folder_name', text='Folder Name')
    done_queue.column("folder_name", minwidth=0, width=560, stretch=NO)
    done_queue.heading('total_images', text='Total Images')
    done_queue.column("total_images", minwidth=0, width=250)
    
    mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
    
    
    # start_button.grid(column=0, row=2, sticky=S)
    progress_label.grid(column=0, row=4, sticky=W)
    progress_bar.grid(column=0, row=4, sticky=E)
    ac_label.grid(column=0, row=5, sticky=W)
    ac_queue.grid(column=0, row=6, sticky=(W,E))
    
    
    output_label.grid(column=0, row=7, sticky=W)
    output_widget.grid(column=0, row=8, sticky=W)
    
    done_label.grid(column=0, row=9, sticky=W)
    done_queue.grid(column=0, row=10, sticky=(W,E))
    status_label.grid(column=0, row=11, sticky=S)
    
    
    
    for child in mainframe.winfo_children():
        child.grid_configure(padx=5, pady=5)

def main():
    global config_path, configs, input_dir, output_dir, root, procs, pystripe_running, counter, timer, no_list, average_speed, log_path
    timer = 0
    counter = 0
    average_speed = [0,0]
    pystripe_running = False
    config_path = Path(__file__).parent / 'data/config.ini'
    log_path = Path(__file__).parent / 'data/logging'
    print('Config Path: {}'.format(config_path))
    configs = get_configs(config_path)
    procs = []
    no_list = []
    root = Tk()
    
    try:
        input_dir = Path(configs['paths']['input_dir'])
        output_dir = Path(configs['paths']['output_dir'])
        log('----------------   RESTART  -----------------')
        log('Input Directory: {}'.format(input_dir))
        log('Output Directory: {}'.format(output_dir))
    except:
        log(traceback.format_exc())
        messagebox.showwarning('Path Error', 'Could not access config file at: {}'.format(config_path))

    build_gui()
    look_for_images()
    root.mainloop()

    # while True:
        # look_for_images()
        # time.sleep(1)

if __name__ == "__main__":
    main()