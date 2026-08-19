from ultralytics import YOLO

# 1. Load a pre-trained YOLO model (Small model is great for this)
model = YOLO("yolov8s.pt") 

if __name__ == '__main__':
    
    # 2. Train the model using your exact data.yaml path
    results = model.train(
	data="dataset/yolo_symbols/data.yaml",        

        # Training parameters optimized for small symbols:
        epochs=150,       # Higher epochs because small symbols take longer to learn
        imgsz=1280,       # High resolution is critical so the AI can see tiny details
        batch=4,          # If your computer crashes with "Out of Memory", change this to 4
        device=0,         # Change to 'cpu' if you are not using an NVIDIA GPU
        
        # Where to save the finished model:
        project="runs/symbols_training", 
        name="yolo_symbols"
    )