from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Dict, Any
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

@router.post("")
async def chat_with_assistant(
    messages: List[Dict[str, str]] = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """
    Handle chat requests. Currently a rule-based mock implementation, 
    but structured to be easily swapped with an LLM provider.
    """
    if not messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty")
        
    last_message = messages[-1].get("content", "").lower()
    
    # Simple rule-based responses
    if "train" in last_message or "model" in last_message:
        response = "To train a model, go to a Project and navigate to the 'Train' tab. You can select an architecture (like YOLOv8), adjust hyperparameters like epochs and batch size, and start training on our cloud GPUs."
    elif "dataset" in last_message or "upload" in last_message:
        response = "You can create a new dataset from the Projects tab. Once created, use the 'Upload' tab within the project to add images. We support JPG and PNG formats."
    elif "annotate" in last_message or "label" in last_message:
        response = "Our annotation tool allows you to draw bounding boxes and polygons. We also offer an auto-label feature and a SAM (Segment Anything Model) integration to speed up your workflow."
    elif "deploy" in last_message or "api" in last_message:
        response = "Once a model is trained, head to the 'Deploy' tab. You can test inference directly in the browser, generate an API key, and find code snippets to integrate the model into your own applications."
    elif "error" in last_message or "fail" in last_message:
        response = "I'm sorry to hear you're experiencing an error. Please check the 'Monitor' tab for logs, or reach out to us via the 'Help & Contact' tab so we can investigate."
    else:
        response = "I've received your request! I'm Nebula AI, here to assist with dataset management, training configurations, and deployment strategies. (Note: Full LLM capabilities are currently in beta)."

    return {
        "role": "assistant",
        "content": response
    }
