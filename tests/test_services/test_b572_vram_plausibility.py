import unittest
from unittest.mock import patch, MagicMock
from services.model_manager import get_cuda_memory_info_bytes


class TestB572VramPlausibility(unittest.TestCase):
    @patch("services.model_manager.torch")
    def test_vram_plausibility_fallback_triggered(self, mock_torch):
        # Setup mock behavior
        mock_torch.cuda.is_available.return_value = True
        
        # Simuliere WDDM Bug: mem_get_info meldet 0 Bytes frei bei 6 GB total
        total_memory = 6 * 1024 * 1024 * 1024
        mock_torch.cuda.mem_get_info.return_value = (0, total_memory)
        
        # PyTorch selbst hat aber fast nichts allokiert (z.B. 50 MB)
        allocated_memory = 50 * 1024 * 1024
        mock_torch.cuda.memory_allocated.return_value = allocated_memory
        
        # Mock device properties
        mock_props = MagicMock()
        mock_props.total_memory = total_memory
        mock_torch.cuda.get_device_properties.return_value = mock_props
        
        # Call function
        free_bytes, total_bytes = get_cuda_memory_info_bytes(device=0)
        
        # Verify fallback was triggered and returned (total - allocated)
        self.assertEqual(total_bytes, total_memory)
        self.assertEqual(free_bytes, total_memory - allocated_memory)

    @patch("services.model_manager.torch")
    def test_vram_plausibility_normal_behavior(self, mock_torch):
        # Setup mock behavior
        mock_torch.cuda.is_available.return_value = True
        
        # Normalfall: 4 GB frei bei 6 GB total
        total_memory = 6 * 1024 * 1024 * 1024
        free_memory_info = 4 * 1024 * 1024 * 1024
        mock_torch.cuda.mem_get_info.return_value = (free_memory_info, total_memory)
        
        # PyTorch allokiert 1 GB
        allocated_memory = 1 * 1024 * 1024 * 1024
        mock_torch.cuda.memory_allocated.return_value = allocated_memory
        
        # Mock device properties
        mock_props = MagicMock()
        mock_props.total_memory = total_memory
        mock_torch.cuda.get_device_properties.return_value = mock_props
        
        # Call function
        free_bytes, total_bytes = get_cuda_memory_info_bytes(device=0)
        
        # Verify normal values were returned
        self.assertEqual(total_bytes, total_memory)
        self.assertEqual(free_bytes, free_memory_info)


if __name__ == "__main__":
    unittest.main()
