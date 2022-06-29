import pystripe
import os
import multiprocessing
import configparser
from pathlib import Path
import csv
from tkinter import *
from tkinter import ttk
import sys

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
        f.close()
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
    rename_images(dir)

def rename_images(dir):
    output_path = dir['output_path']
    input_path = dir['path']
    file_path = os.path.join(output_path, 'destriped_image_list.txt')
    with open(file_path, 'r') as f:
        image_list = f.readlines()
        f.close()
    os.remove(file_path)
    for image in image_list:
        image = image.strip()
        try:
            os.rename(image, os.path.splitext(image)[0] + '.orig')
        except WindowsError as e:
            if e.winerror == 183:
                os.remove(image)
        except Exception as e:
            print(e)

def get_acquisition_dirs(input_dir, output_dir):
    ac_dirs = []
    for (root,dirs,files) in os.walk(input_dir):
        if 'metadata.txt' in files:
            ac_dirs.append({
                'path': root,
                'output_path': os.path.join(output_dir, os.path.relpath(root, input_dir))
            })
    for dir in ac_dirs:
        get_metadata(dir)

    unfinished_dirs = []
    for dir in ac_dirs:
        if in_progress(dir):
            unfinished_dirs.append(dir)

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
        f.close()

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

def in_progress(dir):
    destripe_tag = dir['metadata']['Destripe']
    return 'D' not in destripe_tag and 'A' not in destripe_tag

def get_target_number(dir):
    skips = list(int(tile['Skip']) for tile in dir['metadata']['tiles'])
    return sum(skips) * int(dir['metadata']['Z_Block']) / int(dir['metadata']['Z step (m)'])

def finish_directory(dir):
    global done_queue

    # add folder to "done queue"
    done_queue.insert('', 'end', values=(
        os.path.relpath(dir['path'], input_dir),
        dir['processed_images'],
        ))

    # prepend 'D' to 'Destripe' label in metadata.txt
    metadata_path = os.path.join(dir['path'], 'metadata.txt')
    with open(metadata_path, encoding="utf8", errors="ignore") as f:
        reader = csv.reader(f, dialect='excel', delimiter='\t')
        line_list = list(reader)
        f.close()
    os.remove(metadata_path)
    destripe = line_list[1][6]
    line_list[1][6] = 'D' + destripe
    with open(metadata_path, 'w', newline='') as f:
        writer = csv.writer(f, dialect='excel', delimiter='\t')
        for row in line_list:
            writer.writerow(row)
        f.close()

    # prepend 'DST_' to input and output directory name
    
    for path in (dir['output_path'], dir['path']):
        split = os.path.split(path)
        new_dir_name = 'DST_' + split[1]
        new_path = os.path.join(split[0], new_dir_name)
        try:
            os.rename(path, new_path)
        except:
            pass

    # convert .orig images to .tiff
    for (root,dirs,files) in os.walk(dir['path']):
        for file in files:
            if Path(file).suffix == '.orig':
                file_path = os.path.join(root, file)
                base = os.path.splitext(file_path)[0]
                os.rename(file_path, base + '.tiff')

def update_status(ac_dirs):
    current_dirs = []
    for dir in ac_dirs:
        extensions = pystripe.core.supported_extensions
        dir['unprocessed_images'] = 0
        dir['orig_images'] = 0
        dir['processed_images'] = 0

        # get lists of processed and unprocessed images in input directory and processed images in output directory
        for (root,dirs,files) in os.walk(dir['path']):
            for file in files:
                if Path(file).suffix in extensions:
                    dir['unprocessed_images'] += 1
                elif Path(file).suffix == '.orig':
                    dir['orig_images'] += 1
        for (root, dirs, files) in os.walk(dir['output_path']):
            for file in files:
                if Path(file).suffix in extensions:
                    dir['processed_images'] += 1

        if dir['processed_images'] >= dir['target_number']:
            finish_directory(dir)
        else:
            current_dirs.append(dir)
    return current_dirs

def update_message():
    global counter, status_message, searching
    period = 50
    count = counter % period
    if count < period/2:
        message = '-' * count + ' Searching for images ' + '-' * (int(period/2-1) - count)
    else:
        message = '-' * (period-1 - count) + ' Searching for images ' + '-' * (count - int(period/2))

    if searching:
        status_message.set(message)


def look_for_images():
    global searching, root, ac_queue, input_dir, output_dir, configs, procs, pystripe_running, counter, status_message
    acquisition_dirs = get_acquisition_dirs(input_dir, output_dir)
    acquisition_dirs = update_status(acquisition_dirs)
    update_message()

    for item in ac_queue.get_children():
            ac_queue.delete(item)

    if len(acquisition_dirs) > 0:
        acquisition_dirs.sort(key=lambda x: x['path'])

        for dir in acquisition_dirs:
            
            ac_queue.insert('', 'end', values=(
                os.path.relpath(dir['path'], input_dir),
                dir['unprocessed_images'],
                dir['processed_images'],
                dir['target_number'],
                ))

        if not any(p.is_alive() for p in procs):
            pystripe_running = False
            dir = acquisition_dirs[0]
            if dir['unprocessed_images'] > 0:
                pystripe_running = True
                with open('pystripe_output.txt', 'w') as f:
                    f.close()
                get_pystripe_output()
                p = multiprocessing.Process(target=run_pystripe, args=(dir, configs))
                procs.append(p)
                p.start()
    else:
        ac_queue.insert('', 'end', values=('No new acquisitions found...', '', '', ''))

    if searching:
        counter += 1 
        root.after(1000, look_for_images) 

def get_pystripe_output():
    global output_widget, pystripe_running, root
    with open('pystripe_output.txt', 'r') as f:
        output_widget.delete(1.0, 'end')
        line_list = f.readlines()
        if len(line_list) < 7:
            output = ''.join(line_list)
        elif 'Done' in line_list[-1]:
            output = ''.join(line_list[:5] + line_list[-2:])
        else:
            output = ''.join(line_list[:5] + line_list[-1:])
        output_widget.insert('end', output)

    if pystripe_running:
        root.after(100, get_pystripe_output)

def change_on_off():
    global searching, button_text, status_message, counter
    searching = not searching
    if searching:
        button_text.set('STOP')
        status_message.set('Searching for images')
        look_for_images()
        
        
    else: 
        button_text.set('START')
        status_message.set('')
        
def build_gui():
    global status_message, button_text, searching, ac_queue, output_widget, done_queue
    root.title("Destripe GUI")
    icon_path = Path(__file__).parent / 'data/lct.ico'
    root.iconbitmap(icon_path)

    mainframe = ttk.Frame(root, padding="3 3 12 12")
    mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    status_message = StringVar(mainframe, '')
    status_label = ttk.Label(mainframe, textvariable=status_message)
    status_label.grid(column=0, row=1, sticky=S)

    button_text = StringVar()
    button_text.set('START')
    searching = False
    start_button = ttk.Button(mainframe, textvariable=button_text, command=change_on_off, width=10)
    start_button.grid(column=0, row=2, sticky=S)

    ttk.Label(mainframe, text="Pystripe Output").grid(column=0, row=3, sticky=W)
    output_widget = Text(mainframe, height=10, width=100)
    output_widget.grid(column=0, row=4, sticky=W)

    ttk.Label(mainframe, text="Acquisition Queue").grid(column=0, row=5, sticky=W)
    columns = ('folder_name', 'new_images', 'destriped_images', 'total_images')
    ac_queue = ttk.Treeview(mainframe, columns=columns, show='headings', height=6)
    ac_queue.heading('folder_name', text='Folder Name')
    ac_queue.column("folder_name", minwidth=0, width=450, stretch=NO)

    ac_queue.heading('new_images', text='New Images')
    ac_queue.column("new_images", minwidth=0, width=110, stretch=NO)

    ac_queue.heading('destriped_images', text='Processed Images')
    ac_queue.column("destriped_images", minwidth=0, width=110, stretch=NO)

    ac_queue.heading('total_images', text='Total Images Expected')
    ac_queue.column("total_images", minwidth=0, width=130)

    ac_queue.grid(column=0, row=6, sticky=(W,E))

    ttk.Label(mainframe, text="Destriped Acquisitions").grid(column=0, row=7, sticky=W)
    columns = ('folder_name','total_images')
    done_queue = ttk.Treeview(mainframe, columns=columns, show='headings', height=8)
    done_queue.heading('folder_name', text='Folder Name')
    done_queue.column("folder_name", minwidth=0, width=450, stretch=NO)

    done_queue.heading('total_images', text='Total Images')
    done_queue.column("total_images", minwidth=0, width=100)
    done_queue.grid(column=0, row=8, sticky=(W,E))

    for child in mainframe.winfo_children():
        child.grid_configure(padx=5, pady=5)

def main():
    global config_path, configs, input_dir, output_dir, root, procs, pystripe_running, counter
    
    counter = 0
    pystripe_running = False
    config_path = Path(__file__).parent / 'data/config.ini'
    print('Config Path: {}'.format(config_path))
    configs = get_configs(config_path)
    input_dir = Path(configs['paths']['input_dir'])
    output_dir = Path(configs['paths']['output_dir'])
    procs = []

    root = Tk()
    build_gui()
    root.mainloop()

if __name__ == "__main__":
    main()