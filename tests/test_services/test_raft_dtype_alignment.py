import numpy as np
import torch


class _FakeRaft(torch.nn.Module):
    def __init__(self, dtype: torch.dtype):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.ones(1, dtype=dtype))
        self.seen_dtypes = []

    def forward(self, img1, img2):
        self.seen_dtypes.append((img1.dtype, img2.dtype))
        flow = torch.zeros((1, 2, 8, 8), dtype=img1.dtype, device=img1.device)
        return [flow]


def test_raft_motion_score_matches_model_parameter_dtype():
    from services.video_analysis_service import _raft_motion_score

    model = _FakeRaft(torch.float16).eval()
    frame1 = np.zeros((16, 16, 3), dtype=np.uint8)
    frame2 = np.ones((16, 16, 3), dtype=np.uint8)

    score = _raft_motion_score(model, torch.device("cpu"), frame1, frame2)

    assert score == 0.0
    assert model.seen_dtypes == [(torch.float16, torch.float16)]
