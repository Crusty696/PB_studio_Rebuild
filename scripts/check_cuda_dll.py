
import ctypes
import os

def check_cuda_dll():
    print("Checking for nvcuda.dll...")
    try:
        dll = ctypes.WinDLL('nvcuda.dll')
        print("SUCCESS: nvcuda.dll loaded.")
    except Exception as e:
        print(f"ERROR: Failed to load nvcuda.dll: {e}")

    print("\nChecking for nvml.dll...")
    try:
        dll = ctypes.WinDLL('nvml.dll')
        print("SUCCESS: nvml.dll loaded.")
    except Exception as e:
        print(f"ERROR: Failed to load nvml.dll: {e}")

if __name__ == "__main__":
    check_cuda_dll()
