import sys
print("Python Executable:", sys.executable)
print("Python Version:", sys.version)
print("sys.path:")
for p in sys.path:
    print(p)

try:
    from moviepy.editor import VideoFileClip
    print("\nSuccessfully imported VideoFileClip from moviepy.editor!")
except ModuleNotFoundError as e:
    print(f"\nFailed to import moviepy.editor: {e}")
except ImportError as e:
    print(f"\nFailed to import moviepy.editor (ImportError): {e}")