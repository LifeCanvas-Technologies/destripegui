import pystripe
import os, sys, time, csv, re
import math
import multiprocessing
import configparser
from pathlib import Path
from tkinter import *
from tkinter import ttk
from tkinter import messagebox
from datetime import datetime
import traceback
import shutil
from win32event import CreateMutex
from win32api import GetLastError
from winerror import ERROR_ALREADY_EXISTS
from sys import exit

def delta_string(time2, time1):
    delta = time2 - time1
    seconds = delta.seconds
    hours = math.floor(seconds / 3600)
    seconds = seconds - hours*3600
    minutes = math.floor(seconds / 60)
    seconds = seconds - minutes*60
    if hours > 0:
        time_string = "{}h {}m {}s".format(hours, minutes, seconds)
    elif minutes > 0:
        time_string = "{}m {}s".format(minutes, seconds)
    else: time_string = "{}s".format(seconds)
    return time_string

def progress_write(dir, msg):
    file_path = os.path.join(output_path, progress_log)
    with open(file_path, "a") as f:
        time = now.strftime("%H:%M:%S %m/%d/%Y")
        f.write("{}  -  {}\n".format(time, msg))

def log(message, repeat):
    if not repeat:
        if message in logs: return

    try: logs.append(message)
    except: pass

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

def pystripe_log(message, log_path):
    now = datetime.now()
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

def run_pystripe(dir, configs, log_path):
    # Asynchronous function that runs pystripe batch_filter module and rename_images function

    pystripe_log("Running pystripe on: {}".format(dir['path']), log_path)
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
    
    pystripe_log("Pystripe finished on: {}".format(input_path), log_path)
    rename_images(dir, log_path)

def rename_images(dir, log_path):
    # Appends .orig to images that have been destriped, after batch_filter finishes.  On same async thread as run_pystripe

    output_path = dir['output_path']
    input_path = dir['path']
    file_path = os.path.join(output_path, 'destriped_image_list.txt')
    with open(file_path, 'r') as f:
        image_list = f.readlines()
    images_len = len(image_list)
    pystripe_log('Appending .orig to {} images in {}...'.format(str(images_len), input_path), log_path)

    for image in image_list:
        image = image.strip()
        try:
            os.rename(image, image + '.orig')
        except WindowsError as e:
            if e.winerror == 183:
                os.remove(image)
                pystripe_log('    {}.orig already exists.  Deleting duplicate'.format(image), log_path)
        except:
            pystripe_log(traceback.format_exc(), log_path)
    pystripe_log("Done renaming files in {}.  Deleting 'destriped_image_list.txt'".format(input_path), log_path)
    os.remove(file_path)

def search_directory(input_dir, output_dir, search_dir, ac_list, depth):
    # Recursive search function through input_dir to find directories with metadata.txt.  Ignores _DST and the no_list

    try:
        contents = os.listdir(search_dir)
    except WindowsError as e:
        log('Error: {} Input and output drives can be set by editing: {}'.format(e, config_path), False)
        log(traceback.format_exc(), False)
        messagebox.showwarning(title='Drive Access Error', message='Error: {}\nInput and output drives can be set by editing:\n{}'.format(e, config_path))
        return
    if 'metadata.txt' in contents:
        ac_list.append({
            'path': search_dir, 
            'output_path': os.path.join(output_dir, os.path.relpath(search_dir, input_dir))
        })
        log("Adding {} to provisional Acquisition Queue".format(search_dir), False)
        return ac_list
    if depth == 0: return ac_list
    for item in contents:
        item_path = os.path.join(search_dir, item)
        if os.path.isdir(item_path) and 'DST' not in item and item_path not in no_list:
            try:
                ac_list = search_directory(input_dir, output_dir, item_path, ac_list, depth-1)
            except: 
                log("Error encountered trying to add {} to New Acquisitions List:".format(item_path), True)
                log(traceback.format_exc(), True)
                log("Continuing on anyway...", True)
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
            log("An error occurred attempting to read metadata for {}:".format(dir['path']), True)
            log(traceback.format_exc(), True)
            log("Adding {} to the No List".format(dir['path']), True)
            no_list.append(dir['path'])
            
    unfinished_dirs = []    
    for dir in ac_dirs:
        destripe_string = dir['metadata']['Destripe']
        print('destripe_string: {}'.format(destripe_string))
        try:
            tag = ''
            for s in ['N', 'C', 'D', 'A']:
                if s in destripe_string:
                    tag = s
                    break
            if tag == 'N':
                no_list.append(dir['path'])
                log("Adding {} to No List because N(/A) flag set in metadata".format(dir['path']), True)
                continue
            elif tag == 'C':
                no_list.append(dir['path'])
                log("Adding {} to No List because C flag set in metadata".format(dir['path']), True)
                continue
            elif tag == 'D':
                no_list.append(dir['path'])
                log("Adding {} to No List because D flag set in metadata".format(dir['path']), True)
                continue
            elif tag == 'A':
                no_list.append(dir['path'])
                suffix_length = len(input_abort)
                if str(dir['path'])[-suffix_length:] != input_abort: abort(dir)
                log("Adding {} to No List because A flag set in metadata".format(dir['path']), True)
                continue
            else: 
                unfinished_dirs.append(dir)
                log("Adding {} to final Acquisition Queue".format(dir['path']), False)
        except:
            log('Error encountered while checking metadata tags for {}:'.format(dir['path']), True)
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

def get_target_number(dir):
    # Calculates number of images in acquisition

    skips = sum(list(int(tile['Skip']) for tile in dir['metadata']['tiles']))
    z_block = float(dir['metadata']['Z_Block'])
    z_step = float(dir['metadata']['Z step (m)'])
    steps_per_tile = max(z_block / z_step, 1)
    target = int(skips * steps_per_tile)

    log("Target number calculation for {}:".format(dir['path']), False)
    log('skips: {}, z_block: {}, z_step: {}, target: {}'.format(skips, z_block, z_step, target), False)
    return target

def finish_directory(dir, processed_images):
    # Perform tasks needed once directory is finished destriping

    log('Finishing {}...'.format(dir['path']), True)
    log('    Average pystripe speed for acquisition: {:.2f} it/s'.format(average_speed[0]), True)
    no_list.append(dir['path'])
    log('    Adding {} to No List'.format(dir['path']), True)
    log('    Is pystripe running?: {}'.format(any(p.is_alive() for p in procs)), True)
    progress_write(dir['path'], "Finished destriping {} images".format(processed_images))

    # add folder to "done queue"
    done_queue.insert('', 'end', values=(
        os.path.relpath(dir['path'], input_dir),
        processed_images,
        ))

    # convert .orig images back, add metadata tags and rename folders
    revert_images(dir)

    for file in Path(dir['path']).iterdir():
        file_name = os.path.split(file)[1]
        if Path(file).suffix in ['.txt', '.ini', '.json']:
            log('    Copying {} to {}'.format(file_name, dir['output_path']), True)
            output_file = os.path.join(Path(dir['output_path']), file_name)
            shutil.copyfile(file, output_file)

    prepend_tag(dir, 'in', 'D')
    prepend_tag(dir, 'out', 'D')
    append_folder_name(dir, 'in', input_done)
    append_folder_name(dir, 'out', output_done)

    log('Finished finishing {}'.format(dir['path']), True)

def append_folder_name(dir, drive, msg):
    # Update folder name after abort or pystripe finish

    if drive == 'in':
        path = dir['path'] 
    else:
        path = dir['output_path']
    split = os.path.split(path)
    new_dir_name = split[1] + msg
    new_path = os.path.join(split[0], new_dir_name)
    
    try:
        os.rename(path, new_path)
        log("    Adding '{}' to directory name : {}".format(msg, path), True)
        return True
    except:
        log("    An error occurred while renaming {}:".format(path), True)
        log(traceback.format_exc(), True)
        return False

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
        os.remove(metadata_path)
        destripe_position = line_list[0].index('Destripe')
        destripe = line_list[1][destripe_position]
        log("    Adding '{}' to Destripe metadata tag in {}".format(msg, metadata_path), True)
        if (msg in destripe): log('    "{}" already in output metadata'.format(msg))
        else:
            line_list[1][destripe_position] = msg + destripe
            with open(metadata_path, 'w', newline='') as f:
                writer = csv.writer(f, dialect='excel', delimiter='\t')
                for row in line_list:
                    writer.writerow(row)
        return 1
    except:
        log('    Error adding "{}" to metadata tag:'.format(msg), True)
        log(traceback.format_exc(), True)
        return 0

def revert_images(dir):
    # revert images back from .orig

    revert_count = 0
    for (root,dirs,files) in os.walk(dir['path']):
        for file in files:
            if Path(file).suffix == '.orig':
                file_path = os.path.join(root, file)
                try:
                    os.rename(file_path, os.path.splitext(file_path)[0])
                    revert_count += 1
                except Exception as e:
                    log('    Error reverting image from .orig after acquisition:', True)
                    log(traceback.format_exc(), True)
    log('    Reverted {} images back from .orig'.format(revert_count), True)

def abort(dir):
    # Perform tasks needed to respond to aborted acquisition
    
    log("Aborting {}...".format(dir['path']), True)

    revert_images(dir)
    append_folder_name(dir, 'in', input_abort)

    if os.path.exists(dir['output_path']):
        prepend_tag(dir, 'out', 'A')
        append_folder_name(dir, 'out', output_abort)
        if os.path.exists(os.path.join(dir['output_path'], 'destriped_image_list.txt')):
            os.remove(os.path.join(dir['output_path'], 'destriped_image_list.txt'))
            
    log("Done aborting {}...".format(dir['path']), True)

def count_processed_images(active_dir):
    # Count processed images in output path

    log("Begin image count for {}".format(active_dir['output_path']), False)
    processed_images = 0
    extensions = pystripe.core.supported_extensions
    for (root, dirs, files) in os.walk(active_dir['output_path']):
        for file in files:
            if Path(file).suffix in extensions:
                processed_images += 1
    log("Finish image count for {}".format(active_dir['output_path']), False)

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

    global old_active, active_dir, average_speed, progress_bar, searching, root, ac_queue, input_dir, output_dir, configs, procs, pystripe_running, counter, status_message, timer, output_widget, current_widget
    
    # update GUI

    update_message()

    for item in current_widget.get_children():
        current_widget.delete(item)
    for item in ac_queue.get_children():
        ac_queue.delete(item)
    
    if not any(p.is_alive() for p in procs):
        pystripe_running = False
        output_widget.delete(1.0, 'end')
        cancel_button['state'] = 'disabled'
    else:
        get_pystripe_output()
        cancel_button['state'] = 'normal'
    
    # get acquisition directories
    acquisition_dirs = get_acquisition_dirs(input_dir, output_dir)
        
    # finish if done
    if len(acquisition_dirs) > 0:
        active_dir = acquisition_dirs[0]
        processed_images = count_processed_images(active_dir)
        if processed_images >= active_dir['target_number'] and pystripe_running == False:
            finish_directory(active_dir, processed_images)
            acquisition_dirs.remove(active_dir)
            average_speed = [0,0]
            
    # Add new acquisitions to GUI acquisition queue
    if len(acquisition_dirs) > 0:  
        active_dir = acquisition_dirs[0]
        
        new_time = datetime.now()
        if os.path.relpath(active_dir['path'], input_dir) == old_active:
            elapsed_time = delta_string(new_time, timer)
        else:
            old_active = os.path.relpath(active_dir['path'], input_dir)
            timer = new_time
            elapsed_time = delta_string(timer, timer)


        print('processed_images: {}'.format(processed_images))
        current_widget.insert('', 'end', values=(
            os.path.relpath(active_dir['path'], input_dir),
            processed_images,
            active_dir['target_number'],
            elapsed_time
        ))      
        for i in range(1, len(acquisition_dirs)):
            dir = acquisition_dirs[i]
            ac_queue.insert('', 'end', values=(
                os.path.relpath(dir['path'], input_dir),
                dir['target_number']
            ))

        pct = 100 * processed_images / active_dir['target_number']
        if pct > 100: pct = 100
        progress_bar['value'] = pct

        # if pystripe is done and @ %5 seconds, run new pystripe batch
        if pystripe_running == False and counter % 5 == 0 and wait == False:
            pystripe_running = True
            with open('pystripe_output.txt', 'w') as f:
                f.close()
            get_pystripe_output()

            progress_write(active_dir['path'], "Starting pystripe batch.  {} images have been processed.")
            p = multiprocessing.Process(target=run_pystripe, args=(active_dir, configs, log_path))
            # p.daemon = True
            procs.append(p)
            p.start()
    else:
        ac_queue.insert('', 'end', values=('The acquisition queue is empty...', '', '', ''))
        progress_bar['value'] = 0
    
    counter += 1 
    root.after(1000, look_for_images) 

def update_average_speed(new_speed):
    global average_speed
    new_speed = float(new_speed)
    n = average_speed[1]
    avg = (average_speed[0] * n + new_speed) / (n + 1)
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
        
def cancel_destripe():
    wait = True
    log('Cancelling {}'.format(active_dir['path']), True)
    for p in procs:
        p.terminate()
    while wait:
        log('    waiting...', False)
        if not any(p.is_alive() for p in procs):
            no_list.append(active_dir['path'])
            revert_images(active_dir)
            prepend_tag(active_dir, 'in', 'C')
            prepend_tag(active_dir, 'out', 'C')

            image_list_path = os.path.join(active_dir['output_path'], 'destriped_image_list.txt')
            if os.path.exists(image_list_path):
                os.remove(image_list_path)
            append_folder_name(dir, 'in', input_cancel)
            append_folder_name(dir, 'out', output_cancel)
            wait = False

def build_gui():
    global status_message, button_text, searching, ac_queue, output_widget, done_queue, progress_bar, cancel_button, current_widget
    root.title("Destripe GUI")
    icon_path = Path(__file__).parent / 'data/lct.ico'
    root.iconbitmap(icon_path)

    mainframe = ttk.Frame(root, padding="3 3 12 12")
    
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    status_message = StringVar(mainframe, '')
    status_label = ttk.Label(mainframe, textvariable=status_message)

    button_text = StringVar()
    button_text.set('CANCEL')
    searching = True
    cancel_button = ttk.Button(mainframe, textvariable=button_text, command=cancel_destripe, width=20)
    cancel_button['state'] = 'disabled'
    
    progress_label = ttk.Label(mainframe, text='Progress:')
    progress_bar = ttk.Progressbar(mainframe, orient='horizontal', mode='determinate', length=520)
    
    output_label = ttk.Label(mainframe, text="Pystripe Output")
    output_widget = Text(mainframe, height=10, width=100)

    ac_label = ttk.Label(mainframe, text="Acquisition Queue")
    columns = ('folder_name', 'total_images')
    ac_queue = ttk.Treeview(mainframe, columns=columns, show='headings', height=6)
    ac_queue.heading('folder_name', text='Folder Name')
    ac_queue.column("folder_name", minwidth=0, width=685, stretch=NO)
    ac_queue.heading('total_images', text='Total Images')
    ac_queue.column("total_images", minwidth=0, width=125, stretch=NO)

    current_label = ttk.Label(mainframe, text="Currently Destriping:")
    columns = ('folder_name', 'processed', 'total_images', 'time')
    current_widget = ttk.Treeview(mainframe, columns=columns, show='headings', height=1)
    current_widget.heading('folder_name', text='Folder Name')
    current_widget.column("folder_name", minwidth=0, width=480, stretch=NO)
    current_widget.heading('processed', text='Processed Images')
    current_widget.column("processed", minwidth=0, width=110, stretch=NO)
    current_widget.heading('total_images', text='Total Images')
    current_widget.column("total_images", minwidth=0, width=110, stretch=NO)
    current_widget.heading('time', text='Elapsed Time')
    current_widget.column("time", minwidth=0, width=110, stretch=NO)
 

    done_label = ttk.Label(mainframe, text="Destriped Acquisitions")
    columns = ('folder_name', 'total_images')
    done_queue = ttk.Treeview(mainframe, columns=columns, show='headings', height=8)
    done_queue.heading('folder_name', text='Folder Name')
    done_queue.column("folder_name", minwidth=0, width=685, stretch=NO)
    done_queue.heading('total_images', text='Total Images')
    done_queue.column("total_images", minwidth=0, width=125)
    
    mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
    
    
    current_label.grid(column=0, row=1, sticky=W, columnspan = 3)
    current_widget.grid(column=0, row=2, sticky=W, columnspan = 3)

    progress_label.grid(column=0, row=4, sticky=W,)
    progress_bar.grid(column=1, row=4, sticky=W)

    ac_label.grid(column=0, row=7, sticky=W)
    ac_queue.grid(column=0, row=8, sticky=(W,E), columnspan = 3)
    
    
    output_label.grid(column=0, row=5, sticky=W)
    cancel_button.grid(column=2, row=4, sticky=E)
    output_widget.grid(column=0, row=6, sticky=W, columnspan = 3)
    
    done_label.grid(column=0, row=9, sticky=W)
    done_queue.grid(column=0, row=10, sticky=(W,E), columnspan = 3)
    status_label.grid(column=0, row=11, sticky=S, columnspan = 3)
    
    
    
    for child in mainframe.winfo_children():
        child.grid_configure(padx=5, pady=5)

def main():
    global start_time, progress_log, logs, config_path, configs, input_dir, output_dir, root, procs, pystripe_running, counter, timer, no_list, average_speed, log_path, wait, old_active, input_done, output_done, input_cancel, output_cancel, input_abort, output_abort
    double_test = CreateMutex(None, 1, 'A unique mutex name')
    if GetLastError(  ) == ERROR_ALREADY_EXISTS:
        # Take appropriate action, as this is the second
        # instance of this script; for example:
        messagebox.showwarning('Multiple Instances', 'Another instance of destripegui is already running')
        exit(1)

    timer = datetime.now()
    old_active = ''
    wait = False
    logs = []
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
    progress_log = configs['paths']['progress_log']
    
    try:
        input_dir = Path(configs['paths']['input_dir'])
        output_dir = Path(configs['paths']['output_dir'])

        input_done = configs['suffixes']['input_done']
        output_done = configs['suffixes']['output_done']

        input_cancel = configs['suffixes']['input_cancel']
        output_cancel = configs['suffixes']['output_cancel']

        input_abort = configs['suffixes']['input_abort']
        output_abort = configs['suffixes']['output_abort']

        log('----------------   RESTART  -----------------', True)
        log('Input Directory: {}'.format(input_dir), True)
        log('Output Directory: {}'.format(output_dir), True)
    except:
        log(traceback.format_exc(), True)
        messagebox.showwarning('Path Error', 'Could not access config file at: {}'.format(config_path))

    build_gui()
    look_for_images()
    root.mainloop()

    # while True:
        # look_for_images()
        # time.sleep(1)

if __name__ == "__main__":
    main()