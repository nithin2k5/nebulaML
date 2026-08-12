"""
Zero-Shot Vision-Language Auto-Labeling Service using Microsoft Florence-2.
"""
import logging
import threading
from PIL import Image
import torch
from typing import List, Dict, Any, Union

logger = logging.getLogger(__name__)

_florence_model = None
_florence_processor = None
_florence_lock = threading.Lock()
_FLORENCE_MODEL_ID = "microsoft/Florence-2-base"

def _get_device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    elif torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")

def _load_florence():
    global _florence_model, _florence_processor
    if _florence_model is None:
        with _florence_lock:
            if _florence_model is None:
                logger.info(f"Loading {_FLORENCE_MODEL_ID} for Zero-Shot Annotation...")
                try:
                    from transformers import AutoProcessor, AutoModelForCausalLM
                    device = _get_device()
                    _florence_model = AutoModelForCausalLM.from_pretrained(
                        _FLORENCE_MODEL_ID, 
                        trust_remote_code=True
                    ).to(device).eval()
                    _florence_processor = AutoProcessor.from_pretrained(
                        _FLORENCE_MODEL_ID, 
                        trust_remote_code=True
                    )
                    logger.info("Florence-2 loaded successfully.")
                except Exception as e:
                    logger.error(f"Failed to load Florence-2: {e}")
                    raise RuntimeError(f"Vision-Language model failed to load: {e}")
    return _florence_model, _florence_processor

def zero_shot_predict(image_path: Union[str, Image.Image], text_prompt: str) -> List[Dict[str, Any]]:
    """
    Run zero-shot object detection (Phrase Grounding) using Florence-2.
    
    Args:
        image_path: Path to the image or PIL Image object.
        text_prompt: The object(s) to search for, e.g., "blue car" or "rusty pipes".
        
    Returns:
        A list of bounding box dictionaries with class_name and bbox.
    """
    model, processor = _load_florence()
    device = _get_device()
    
    if isinstance(image_path, str):
        image = Image.open(image_path).convert("RGB")
    else:
        image = image_path.convert("RGB")
        
    # Task prefix for Florence-2 phrase grounding
    task = "<CAPTION_TO_PHRASE_GROUNDING>"
    text_input = task + " " + text_prompt
    
    inputs = processor(text=text_input, images=image, return_tensors="pt").to(device)
    
    with torch.no_grad():
        generated_ids = model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            max_new_tokens=1024,
            num_beams=3
        )
        
    generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    
    # Process the text output into coordinates
    parsed_answer = processor.post_process_generation(
        generated_text, 
        task=task, 
        image_size=(image.width, image.height)
    )
    
    # Florence-2 returns data under the task name key
    grounding_results = parsed_answer.get(task, {})
    
    bboxes = grounding_results.get("bboxes", [])
    labels = grounding_results.get("labels", [])
    
    detections = []
    for box, label in zip(bboxes, labels):
        # Florence-2 bbox format is [x1, y1, x2, y2]
        x1, y1, x2, y2 = box
        
        detections.append({
            "class_name": label,
            "bbox": [int(x1), int(y1), int(x2), int(y2)],
            "box_width": int(x2 - x1),
            "box_height": int(y2 - y1)
        })
        
    return detections
