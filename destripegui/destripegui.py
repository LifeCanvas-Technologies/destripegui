import pystripe
import os, sys, time, csv, re
import multiprocessing
import configparser
from pathlib import Path
from tkinter import *
from tkinter import ttk
from tkinter import messagebox
from pprint import pprint


# [WinError 5] Access is denied: 'D:\\SmartSPIM_Data\\2022_07_15\\20220715_12_04_09_FileName' -> 'D:\\SmartSPIM_Data\\2022_07_15\\20220715_12_04_09_FileName_DST'

def get_configs(config_path):
    config = configparser.ConfigParser()   
    config.read(config_path)
    return config

def run_pystripe(dir, configs):
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
    # file_path = os.path.join(input_path, 'image_count.txt')
    # os.remove(file_path)
    rename_images(dir)

def rename_images(dir):
    output_path = dir['output_path']
    input_path = dir['path']
    file_path = os.path.join(output_path, 'destriped_image_list.txt')
    with open(file_path, 'r') as f:
        image_list = f.readlines()
    print('renaming...')
    t1 = time.time()
    for image in image_list:
        image = image.strip()
        try:
            os.rename(image, image + '.orig')
        except WindowsError as e:
            if e.winerror == 183:
                os.remove(image)
        except Exception as e:
            print(e)
    os.remove(file_path)
    dt = '{:.2f}'.format(time.time() - t1)
    print('done renaming after {} seconds'.format(dt))

def walklevel(some_dir, level):
    some_dir = str(some_dir)
    some_dir = some_dir.rstrip(os.path.sep)
    assert os.path.isdir(some_dir)
    num_sep = some_dir.count(os.path.sep)
    for root, dirs, files in os.walk(some_dir):
        yield root, dirs, files
        num_sep_this = root.count(os.path.sep)
        if num_sep + level <= num_sep_this:
            del dirs[:]

def search_directory(input_dir, output_dir, search_dir, ac_list, depth):
    # print(directory)
    try:
        contents = os.listdir(search_dir)
    except WindowsError as e:
        if e.winerror == 3:
            print(e)
    #     # root.geometry("300x200")
    #     # w = Label(root, text ='DestripeGUI', font = "50") 
    #     # w.pack()
            messagebox.showwarning('Error', 'Error reading from drive: {}.  Please make sure network drives are accessible.'.format(input_dir))
    #     # root.mainloop()
    #     # while True:
    #     #     time.sleep(1)
    # contents = os.listdir(search_dir)
    # print(contents)
    if 'metadata.txt' in contents:
        ac_list.append({
            'path': search_dir, 
            'output_path': os.path.join(output_dir, os.path.relpath(search_dir, input_dir))
        })
        return ac_list
    if depth == 0: return ac_list
    for item in contents:
        item_path = os.path.join(search_dir, item)
        # print('isdir {}: {}'.format(item_path, os.path.isdir(item_path)))
        if os.path.isdir(item_path) and 'DST' not in item and item_path not in no_list:
            try:
                ac_list = search_directory(input_dir, output_dir, item_path, ac_list, depth-1)
            except: pass
    return ac_list

def get_acquisition_dirs(input_dir, output_dir):
    global times
    search_dir = input_dir
    ac_dirs = search_directory(input_dir, output_dir, search_dir, list(), depth=3)
    
    # for (root,dirs,files) in walklevel(input_dir, 2):
        # print(os.path.abspath(root))
        # if 'metadata.txt' in files:
            # ac_dirs.append({
                # 'path': root,
                # 'output_path': os.path.join(output_dir, os.path.relpath(root, input_dir))
            # })
            
    times['search_directory'] = time.time()
    for dir in ac_dirs:
        try:
            get_metadata(dir)
        except:
            no_list.append(dir['path'])
        
    
        
    times['get_metadata'] = time.time()    
    # print('before metadata check: {}'.format(len(ac_dirs)))
    unfinished_dirs = []    
    for dir in ac_dirs:
        try:
            destripe_tag = dir['metadata']['Destripe']
            if 'N' in destripe_tag or 'D' in destripe_tag:
                no_list.append(dir['path'])
                continue
            elif dir['output_path'][-2:] == '_A':
                no_list.append(dir['path'])
                continue
            elif 'A' in destripe_tag:
                if pystripe_running == False:
                    print('aborting: {}'.format(dir['path']))
                    abort(dir)
                else: print('waiting to abort {}'.format(dir['path']))
            else: unfinished_dirs.append(dir)
        except:
            pass
        
        # if in_progress(dir):
            # unfinished_dirs.append(dir)
            
    # print('after metadata check:{}'.format(len(unfinished_dirs)))
    # for dir in unfinished_dirs:
        # print(dir['path'])
    
    if len(unfinished_dirs) > 0: unfinished_dirs.sort(key=lambda x: x['path'])
    return unfinished_dirs

def pair_key_value_lists(keys, values):
    d = {}
    for i in range(0, len(keys)):
        key = keys[i]
        val = values[i]
        if key != '':
            d[key] = val
    return d

def get_metadata(dir):
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


# def in_progress(dir):
    # destripe_tag = dir['metadata']['Destripe']
    # if 'N' in destripe_tag:
    # return 'D' not in destripe_tag and 'A' not in destripe_tag

def get_target_number(dir):
    skips = list(int(tile['Skip']) for tile in dir['metadata']['tiles'])
    return int(sum(skips) * int(dir['metadata']['Z_Block']) / int(dir['metadata']['Z step (m)']))

def finish_directory(dir, processed_images):
    global done_queue, pystripe_running
    no_list.append(dir['path'])
    print('finish_directory: {}'.format(os.path.split(dir['path'])[1]))
    print('proc test (i.e. python_running): {}'.format(any(p.is_alive() for p in procs)))

    
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
    print('reverted {} images back from .orig'.format(revert_count))
     
    for path in [dir['output_path'], dir['path']]:
        print('path: {}'.format(path))
    
        # prepend 'D' to 'Destripe' label in metadata.txt
        metadata_path = os.path.join(path, 'metadata.txt')
        print('metadata path: {}'.format(metadata_path))
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
        except Exception as e:
            print(e)
            pass
    print('finished finishing {}'.format(os.path.split(dir['path'])[1]))
    
def abort(dir):
    no_list.append(dir['path'])
    if 'output_path' not in dir.keys():
        print('no output path: aborting abortion')
        return

    # if dir['output_path'][-2:] == '_A': return
    print('abort directory: {}'.format(dir['output_path']))

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
                    print('Error reverting image from .orig after aborted acquisition:')
                    print(e)
                
    print('reverted {} images back from .orig'.format(revert_count))
    
    # append to A to output metadata destripe tag
    metadata_path = os.path.join(dir['output_path'], 'metadata.txt')
    if not os.path.exists(metadata_path):
        dir['output_path'] += '_A'
        metadata_path = os.path.join(dir['output_path'], 'metadata.txt')
    if not os.path.exists(metadata_path):
        print('no metadata path')
    else:        
        try:
            with open(metadata_path, errors="ignore") as f:
                reader = csv.reader(f, dialect='excel', delimiter='\t')
                line_list = list(reader)
            os.remove(metadata_path)
            destripe = line_list[1][6]
            if ('A' in destripe): print('A already in output metadata for: {}'.format(dir['path']))
            else: 
                line_list[1][6] = 'A' + destripe
                with open(metadata_path, 'w', newline='') as f:
                    writer = csv.writer(f, dialect='excel', delimiter='\t')
                    for row in line_list:
                        writer.writerow(row)
        except Exception as e:
            print(e)
            
    # append _A to output directory name
    if dir['output_path'][-2:] == '_A': print('_A already in output path for: {}'.format(dir['path']))
    else:
        try:
            split = os.path.split(dir['output_path'])
            new_dir_name = split[1] + '_A'
            new_path = os.path.join(split[0], new_dir_name)
            os.rename(dir['output_path'], new_path)
            print('renamed output path for: {}'.format(dir['path']))
        except Exception as e:
            print(e)  
    
    # append _A to input directory name
    if dir['path'][-2:] == '_A': print('_A already in input path for: {}'.format(dir['path']))
    else:
        try:
            split = os.path.split(dir['path'])
            new_dir_name = split[1] + '_A'
            new_path = os.path.join(split[0], new_dir_name)
            os.rename(dir['path'], new_path)
            print('renamed input path for: {}'.format(dir['path']))
        except Exception as e:
            print(e)

def update_status(active_dir):
    global pystripe_running, procs
    current_dirs = []
    extensions = pystripe.core.supported_extensions
    # for dir in ac_dirs:
    
    active_dir['unprocessed_images'] = 0
    active_dir['orig_images'] = 0
    active_dir['processed_images'] = 0

    # get lists of processed and unprocessed images in input directory and processed images in output directory
    for (root,dirs,files) in os.walk(active_dir['path']):
        for file in files:
            if Path(file).suffix in extensions:
                active_dir['unprocessed_images'] += 1
            elif Path(file).suffix == '.orig':
                active_dir['orig_images'] += 1
    current = 0
    in_progress_list = os.path.join(active_dir['output_path'], 'destriped_image_list.txt')
    if os.path.exists(in_progress_list):
        with open(in_progress_list, 'r') as f:
            current = len(f.readlines())
    # print('currently being destriped: {}'.format(current))
    active_dir['unprocessed_images'] -= current
    
    for (root, dirs, files) in os.walk(active_dir['output_path']):
        for file in files:
            if Path(file).suffix in extensions:
                active_dir['processed_images'] += 1
    
    
    if active_dir['processed_images'] >= active_dir['target_number']:
        if pystripe_running: print('Waiting to finish {} until pystripe is complete'.format(active_dir['path']))
        else: finish_directory(active_dir)
    else:
        current_dirs.append(active_dir)
    
    return current_dirs

def count_processed_images(active_dir):
    processed_images = 0
    extensions = pystripe.core.supported_extensions
    for (root, dirs, files) in os.walk(active_dir['output_path']):
        for file in files:
            if Path(file).suffix in extensions:
                processed_images += 1
    return processed_images

def update_message():
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
    global times, average_speed, progress_bar, searching, root, ac_queue, input_dir, output_dir, configs, procs, pystripe_running, counter, status_message, timer, output_widget
    times = {}
    times['start'] = time.time()
    
    # update GUI
    update_message()
    for item in ac_queue.get_children():
        ac_queue.delete(item)
    
    if not any(p.is_alive() for p in procs):
        pystripe_running = False
        output_widget.delete(1.0, 'end')
    else:
        get_pystripe_output()
        # print('average pystripe speed for acquisition: {:.2f} it/s'.format(average_speed[0]))
    # print('pystripe running: {}'.format(pystripe_running))
    
    times['update GUI'] = time.time()
    
    # get acquisition directories
    acquisition_dirs = get_acquisition_dirs(input_dir, output_dir)
    times['return ac_dirs'] = time.time()
    
    if len(acquisition_dirs) > 0:
        active_dir = acquisition_dirs[0]
    # abort if A
        if 'A' in active_dir['metadata']['Destripe'] and pystripe_running == False:
            # print('aborting: {}'.format(active_dir['path']))
            abort(active_dir)
            acquisition_dirs.remove(active_dir)
            times['aborted dir'] = time.time()
            average_speed = [0,0]
        
    # finish if done
    if len(acquisition_dirs) > 0:
        active_dir = acquisition_dirs[0]
        processed_images = count_processed_images(active_dir)
        times['count processed'] = time.time()
        if processed_images >= active_dir['target_number'] and pystripe_running == False:
            finish_directory(active_dir, processed_images)
            acquisition_dirs.remove(active_dir)
            times['finished dir'] = time.time()
            average_speed = [0,0]
        
    if len(acquisition_dirs) > 0:  
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
    # print(times)
    
    # if searching:
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
                # print('line: {}'.format(line))
                # print('speed_list: {}'.format(speed_list))
                try: update_average_speed(speed_list[0])
                except Exception as e:
                    # print('could not update average speed:\n{}'.format(e))
                    pass
            else: 
                line_list2.append(line)
            first_line = False
        else: line_list2.append(line)
    
    # if len(line_list) < 7:
        # output = ''.join(line_list)
    # elif 'Done' in line_list[-1]:
        # output = ''.join(line_list[:5] + line_list[-2:])
    # else:
        # output = ''.join(line_list[:5] + line_list[-1:])
    output = ''.join(line_list2)
    # print(output)
    
    output_widget.insert('end', output)

    # if pystripe_running:
        # root.after(300, get_pystripe_output)

# def change_on_off():
    # global searching, button_text, status_message, counter, timer
    # searching = not searching
    # if searching:
        # counter = 0
        # timer = 0
        # button_text.set('STOP')
        # status_message.set('Searching for images')
        # look_for_images()
        
        
    # else: 
        # button_text.set('START')
        # status_message.set('')
        
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
    global config_path, configs, input_dir, output_dir, root, procs, pystripe_running, counter, timer, no_list, average_speed
    timer = 0
    counter = 0
    average_speed = [0,0]
    pystripe_running = False
    config_path = Path(__file__).parent / 'data/config.ini'
    print('Config Path: {}'.format(config_path))
    configs = get_configs(config_path)
    procs = []
    no_list = []
    
    root = Tk()
    try:
        input_dir = Path(configs['paths']['input_dir'])
        output_dir = Path(configs['paths']['output_dir'])
        print('Input Directory: {}, Output Directory: {}'.format(input_dir, output_dir))
    except:
        print('error message')
        root.geometry("300x200")
        w = Label(root, text ='DestripeGUI', font = "50") 
        w.pack()
        messagebox.showwarning('showwarning', 'Could not find drive')
        root.mainloop()

    build_gui()
    look_for_images()
    root.mainloop()

    # while True:
        # look_for_images()
        # time.sleep(1)

if __name__ == "__main__":
    main()