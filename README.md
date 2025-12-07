# msagent-qt
Display old Microsoft Agent Animations with PySide6


## How to extract MS Agent files

1. Download a .acs agent file, for example Merlin: https://tmafe.com/classic-ms-agents/Merlin.acs
2. Download the MS Agent decompiler: https://archive.org/download/msagent-decompiler/DecompileMSAgent.exe
3. Run the decompiler and open the .acs file to extract the animation frames, sound files and .acd file.


## Usage

### Standalone

1. Make sure you have Python installed (tested with Python 3.11).

2. Install requirements:
```bash
pip install PySide6
```

3. Run the application with the path to the extracted .acd file. By default, it will list all available animations:
```bash
python msagent.py path/to/extracted.acd
```

4. To play a specific animation, provide the animation name as a second argument (you can provide multiple animation names separated by commas):
```bash
python msagent.py path/to/extracted.acd Show,Congratulate,Hide
```

Other optional arguments:
- `--scale SCALE`: Scale factor for the animation (default: 1.0)
- `--volume VOLUME`: Volume for sound playback (default: 1.0)
- `--cycles CYCLES`: Number of times to repeat the animation (default: 1, use -1 for infinite)
- `--speed SPEED`: Speed multiplier for the animation (default: 1.0)


### As a module

Of course, you can also use the `MSAgentWidget` in your own PySide6 applications:

```python
from PySide6.QtWidgets import QApplication, QMainWindow
from msagent import MSAgentWidget

app = QApplication([])
window = QMainWindow()

widget = MSAgentWidget("path/to/extracted.acd")

window.setCentralWidget(widget)
window.show()
app.exec()
```