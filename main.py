# main.py

from tkinter import Tk
from ui.app_ui import SentimentAppUI

def main():
    root = Tk()
    app = SentimentAppUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
