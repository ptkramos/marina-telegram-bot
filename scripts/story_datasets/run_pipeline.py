"""Offline build; downloads are deliberately a separate explicit command."""
from pipeline import build_library

if __name__ == '__main__':
    print(build_library())
