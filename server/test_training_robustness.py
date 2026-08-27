import sys
import os
import time
from pathlib import Path
import tempfile
import shutil

# Ensure 'server' is in path to import app correctly
sys.path.insert(0, os.path.abspath("."))

from app.api.v1.endpoints.inference import _model_cache, get_inference_model
from app.services.trainer import YOLOTrainer, TrainingCancelledException

def test_cache_invalidation_by_weights_version():
    """
    Task 1 Test: Prove that ModelCache evicts properly based on weights_version
    even when mtime is identical.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        model_path = Path(temp_dir) / "dummy_model.pt"
        model_path.touch()
        
        # Monkeypatch create_inference
        from app.services import trainer_factory
        
        class MockInference:
            def __init__(self, path):
                self.path = path
                
        original_create = trainer_factory.create_inference
        trainer_factory.create_inference = lambda path, t: MockInference(path)
        
        try:
            model_v1 = get_inference_model(str(model_path), "yolo", version="1")
            assert f"{model_path}_1" in _model_cache.cache
            
            # Mtime remains exactly the same, but we bump version
            model_v2 = get_inference_model(str(model_path), "yolo", version="2")
            
            # The cache key should be v2, and v1 should be evicted
            assert f"{model_path}_2" in _model_cache.cache
            assert f"{model_path}_1" not in _model_cache.cache
            print("test_cache_invalidation_by_weights_version passed!")
            
        finally:
            trainer_factory.create_inference = original_create
    finally:
        shutil.rmtree(temp_dir)

def test_onnx_export_skips_on_cancelled():
    """
    Task 5 Test: Verify ONNX is not exported when TrainingCancelledException is raised.
    """
    trainer = YOLOTrainer("yolov8n.pt")
    
    class MockModel:
        def __init__(self):
            self.train_called = False
            self.export_called = False
            
        def train(self, **kwargs):
            self.train_called = True
            raise TrainingCancelledException("Training cancelled by user")
            
        def export(self, **kwargs):
            self.export_called = True
            
        def add_callback(self, *args, **kwargs):
            pass
            
    trainer.model = MockModel()
    
    raised = False
    try:
        trainer.train(data_yaml="dummy.yaml", epochs=1)
    except TrainingCancelledException:
        raised = True
        
    assert raised is True
    assert trainer.model.train_called is True
    assert trainer.model.export_called is False
    print("test_onnx_export_skips_on_cancelled passed!")

if __name__ == "__main__":
    test_cache_invalidation_by_weights_version()
    test_onnx_export_skips_on_cancelled()
