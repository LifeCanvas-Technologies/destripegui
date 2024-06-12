import csv, os

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

dir = {'path': r'S:\SmartSPIM_Data\2024_06_12\20240612_14_30_26_File_Name_Destripe_DONE'}

prepend_tag(dir, 'in', 'N')