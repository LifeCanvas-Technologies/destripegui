call conda env create -f environment.yml

call conda activate destripegui_gpu

call pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

call pip install -e .