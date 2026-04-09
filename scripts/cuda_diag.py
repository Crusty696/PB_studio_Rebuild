
import torch
import sys
import gc

def diagnose_cuda():
    print("=== CUDA DIAGNOSIS ===")
    print(f"Python Version: {sys.version}")
    print(f"PyTorch Version: {torch.__version__}")
    
    available = torch.cuda.is_available()
    print(f"CUDA Available: {available}")
    
    if not available:
        print("CRITICAL: CUDA NOT DETECTED BY PYTORCH.")
        return

    try:
        torch.cuda.init()
        print("CUDA Initialized successfully.")
    except Exception as e:
        print(f"CUDA Initialization FAILED: {e}")
        return

    device_count = torch.cuda.device_count()
    print(f"Device Count: {device_count}")
    
    for i in range(device_count):
        props = torch.cuda.get_device_properties(i)
        print(f"\nDevice {i}: {props.name}")
        print(f"  Capability: {props.major}.{props.minor}")
        print(f"  Total Memory: {props.total_memory / 1024**2:.0f} MB")
        
        free, total = torch.cuda.mem_get_info(i)
        print(f"  Hardware Free Memory: {free / 1024**2:.0f} MB")
        print(f"  Hardware Total Memory: {total / 1024**2:.0f} MB")
        
        allocated = torch.cuda.memory_allocated(i)
        reserved = torch.cuda.memory_reserved(i)
        print(f"  PyTorch Allocated: {allocated / 1024**2:.0f} MB")
        print(f"  PyTorch Reserved: {reserved / 1024**2:.0f} MB")

    print("\n--- Running dummy allocation test ---")
    try:
        x = torch.zeros((1024, 1024, 100), device='cuda')
        print("Allocation successful.")
        del x
        torch.cuda.empty_cache()
        gc.collect()
        print("Cleanup successful.")
    except Exception as e:
        print(f"Allocation test FAILED: {e}")

if __name__ == "__main__":
    diagnose_cuda()
