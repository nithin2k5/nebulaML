import yaml
import shutil
from pathlib import Path
from typing import List, Dict, Optional
import os

def create_filtered_dataset(
    original_yaml_path: str, 
    target_dir: str, 
    selected_classes: List[str]
) -> str:
    """
    Create a filtered version of a dataset containing only selected classes.
    
    Args:
        original_yaml_path: Path to the original data.yaml
        target_dir: Directory where the filtered dataset should be created
        selected_classes: List of class names to keep
        
    Returns:
        Path to the new data.yaml file
    """
    original_yaml_path = Path(original_yaml_path)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Read original YAML
    with open(original_yaml_path, 'r') as f:
        data_config = yaml.safe_load(f)
        
    original_classes = data_config.get('names', {})
    # Handle if names is a list instead of dict (YOLO supports both)
    if isinstance(original_classes, list):
        original_classes = {i: name for i, name in enumerate(original_classes)}
        
    # 2. Map selected classes to new indices
    # We need to know:
    # - Which original indices to keep
    # - What their new index will be (0..N-1)
    
    keep_indices = []
    new_class_mapping = {} # old_idx -> new_idx
    new_class_names = {} # new_idx -> name
    
    for new_idx, class_name in enumerate(selected_classes):
        # Find original index
        found = False
        for old_idx, old_name in original_classes.items():
            if old_name == class_name:
                keep_indices.append(old_idx)
                new_class_mapping[old_idx] = new_idx
                new_class_names[new_idx] = class_name
                found = True
                break
        
        if not found:
            print(f"Warning: Selected class '{class_name}' not found in original dataset")

    # 3. Setup new directories
    splits = ['train', 'val', 'test']
    
    for split in splits:
        if split not in data_config:
            continue
            
        # Original paths (relative to yaml or absolute)
        # Note: data_config paths might be relative to the yaml file location
        # We assume standard structure: split/images and split/labels
        
        # We'll rely on the standard folder structure relative to the yaml file's parent
        dataset_root = original_yaml_path.parent
        
        src_images_dir = dataset_root / split / "images"
        src_labels_dir = dataset_root / split / "labels"
        
        if not src_images_dir.exists():
            continue
            
        dst_images_dir = target_dir / split / "images"
        dst_labels_dir = target_dir / split / "labels"
        
        dst_images_dir.mkdir(parents=True, exist_ok=True)
        dst_labels_dir.mkdir(parents=True, exist_ok=True)
        
        # 4. Process files
        for label_file in src_labels_dir.glob("*.txt"):
            # Read label to see if it contains any of the selected classes
            with open(label_file, 'r') as f:
                lines = f.readlines()
                
            new_lines = []
            has_selected_class = False
            
            for line in lines:
                parts = line.strip().split()
                if not parts:
                    continue
                    
                class_id = int(parts[0])
                
                if class_id in new_class_mapping:
                    has_selected_class = True
                    new_class_id = new_class_mapping[class_id]
                    # Reconstruct line with new class ID
                    new_line = f"{new_class_id} {' '.join(parts[1:])}\n"
                    new_lines.append(new_line)
            
            # If image has relevant objects, copy image and write new label
            # Option: strict (only images with objects) or loose (keep empty images?)
            # Usually for training we want background images too, but if we are filtering 
            # for specific objects, maybe we only want those?
            # Let's keep images that had annotations. If an image had annotations but none 
            # of the selected ones, it becomes a background image (empty label file).
            # If it was already a background image, we keep it.
            
            # Logic: Always copy image. Write filtered label file.
            
            # Copy Image
            image_name = label_file.stem
            # Try to find extension
            # This is tricky because we don't know the extension from the label file
            # We'll search for the file in images dir
            found_image = False
            for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.webp']:
                src_img = src_images_dir / f"{image_name}{ext}"
                if src_img.exists():
                    shutil.copy2(src_img, dst_images_dir / f"{image_name}{ext}")
                    found_image = True
                    break
            
            if found_image:
                # Write new label file
                with open(dst_labels_dir / label_file.name, 'w') as f:
                    f.writelines(new_lines)
                    
        # Also copy background images (no label file)?
        # For now we iterate based on labels. If there are images without labels (background), 
        # they are skipped in this loop.
        # To better support background images, we should iterate images instead.
        
        # IMPROVED LOOP: Iterate images
        for image_file in src_images_dir.iterdir():
            if image_file.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.bmp', '.webp']:
                continue
                
            label_file = src_labels_dir / f"{image_file.stem}.txt"
            
            new_lines = []
            
            if label_file.exists():
                with open(label_file, 'r') as f:
                    lines = f.readlines()
                
                for line in lines:
                    parts = line.strip().split()
                    if not parts:
                        continue
                    try:
                        class_id = int(float(parts[0])) # float just in case
                        if class_id in new_class_mapping:
                            new_class_id = new_class_mapping[class_id]
                            new_lines.append(f"{new_class_id} {' '.join(parts[1:])}\n")
                    except ValueError:
                        continue
            
            # Copy image
            shutil.copy2(image_file, dst_images_dir / image_file.name)
            
            # Write label file (even if empty - it's a background image for the selected classes)
            with open(dst_labels_dir / f"{image_file.stem}.txt", 'w') as f:
                f.writelines(new_lines)

    # 5. Create new data.yaml
    new_yaml_content = {
        'path': str(target_dir.resolve()),
        'train': 'train/images',
        'val': 'val/images',
        'names': new_class_names,
        'nc': len(new_class_names)
    }
    
    if 'test' in data_config:
        new_yaml_content['test'] = 'test/images'
        
    new_yaml_path = target_dir / 'data.yaml'
    with open(new_yaml_path, 'w') as f:
        yaml.dump(new_yaml_content, f, sort_keys=False)
        
    return str(new_yaml_path)

def split_dataset_stratified(
    images: List[Dict],
    train_ratio: float = 0.7,
    val_ratio: float = 0.2,
    test_ratio: float = 0.1,
    seed: int = 42
) -> Dict[str, List[Dict]]:
    """
    Split dataset into train/val/test sets using multi-label stratified sampling.
    This ensures that the distribution of ALL classes is preserved across splits.
    """
    if not images:
        return {'train': [], 'val': [], 'test': []}

    import numpy as np
    import random
    try:
        from iterstrat.ml_stratifiers import MultilabelStratifiedShuffleSplit
    except ImportError:
        # Fallback to random if package not installed yet in current env
        print("Warning: iterative-stratification not found. Falling back to random split.")
        shuffled = images.copy()
        random.seed(seed)
        random.shuffle(shuffled)
        n = len(shuffled)
        n_train = int(n * train_ratio)
        n_val = int(n * val_ratio)
        return {
            'train': shuffled[:n_train],
            'val': shuffled[n_train:n_train+n_val],
            'test': shuffled[n_train+n_val:]
        }

    # 1. Prepare multi-label indicators
    # We need to know all unique classes across the dataset
    all_classes = set()
    for img in images:
        if 'annotations' in img:
            for ann in img['annotations']:
                all_classes.add(ann.get('class_name', 'unknown'))
        if 'classes' in img:
            all_classes.update(img['classes'])
    
    class_to_idx = {name: i for i, name in enumerate(sorted(list(all_classes)))}
    num_classes = len(class_to_idx)
    
    if num_classes == 0:
        # Random split if no classes
        shuffled = images.copy()
        random.seed(seed)
        random.shuffle(shuffled)
        n = len(shuffled)
        n_train = int(n * train_ratio)
        n_val = int(n * val_ratio)
        return {
            'train': shuffled[:n_train],
            'val': shuffled[n_train:n_train+n_val],
            'test': shuffled[n_train+n_val:]
        }

    # Create indicator matrix Y
    Y = np.zeros((len(images), num_classes), dtype=int)
    for i, img in enumerate(images):
        img_classes = set()
        if 'annotations' in img:
            for ann in img['annotations']:
                img_classes.add(ann.get('class_name', 'unknown'))
        if 'classes' in img:
            img_classes.update(img['classes'])
        
        for cls in img_classes:
            if cls in class_to_idx:
                Y[i, class_to_idx[cls]] = 1

    # 2. Perform Split
    # We need to do this in two steps to get train/val/test
    # Step 1: Split into (train+val) and (test)
    test_size = test_ratio / (train_ratio + val_ratio + test_ratio)
    
    X = np.arange(len(images)).reshape(-1, 1) # Dummy X for index tracking
    
    msss1 = MultilabelStratifiedShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_val_indices, test_indices = next(msss1.split(X, Y))
    
    X_train_val = X[train_val_indices]
    Y_train_val = Y[train_val_indices]
    
    # Step 2: Split (train+val) into (train) and (val)
    val_size = val_ratio / (train_ratio + val_ratio)
    msss2 = MultilabelStratifiedShuffleSplit(n_splits=1, test_size=val_size, random_state=seed)
    train_indices_rel, val_indices_rel = next(msss2.split(X_train_val, Y_train_val))
    
    # Map relative indices back to original indices
    train_indices = train_val_indices[train_indices_rel]
    val_indices = train_val_indices[val_indices_rel]
    
    return {
        'train': [images[i] for i in train_indices],
        'val': [images[i] for i in val_indices],
        'test': [images[i] for i in test_indices]
    }

