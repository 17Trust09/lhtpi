import os
import sys

# Tests importieren Module aus dem terminboard-Verzeichnis
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Kein Hintergrund-Thread während der Tests
os.environ.setdefault('TERMINBOARD_WATCHER', '0')
