# AI and Fly Brains 
### Tools to study pain and aversive learning in fruit flies

This project is a final year individual project at the University of Nottingham, developed in collaboration between the Optics & Photonics Research Group (Faculty of Engineering) and the Department of Neuroscience (Faculty of Medical and Health Sciences). The goal is to build an AI-driven experimental system that can automatically detect and classify nocifensive (pain-related escape) behaviour in Drosophila melanogaster larvae. This provides an alternative, high-throughput method for testing potential painkillers, using optogenetics stimulation to trigger the behaviour and AI to track and classify each larvae's response in real time.
<p align="center">
<img width="444" height="251" alt="image" src="https://github.com/user-attachments/assets/9c5f20ef-eeef-4aec-8070-340ab54253d8" />
</p>
## How it works
1. The researcher sets up the experiment in the GUI: entering experiment name, remarks and PWM duration. And click Start Experiment
2. The software sends a PWM signal to the Arduino to control both the dark-field illumination LEDs and optogenetics LEDs
3. The Genie Nano CL-M5100 industrial camera starts capturing frames via the SaperaLT SDK
4. Raw frames are passed into the AI pipeline:
   - YOLO detects and tracks each individual larvae across frames
   - DeepLabCut extracts body keypoints (head, midpoint, tail) for each larvae
   - LSTM classifies whether each larvae performed a nocifensive response 
5. Results are saved as an annotated MP4 video and a CSV file, then stored in the database
6. The researcher can view all past experiments from the main window
<p align="center">
<img width="486" height="259" alt="image" src="https://github.com/user-attachments/assets/4d9f68b0-56d0-42d2-9bb1-fd5ef84e349b" />
</p>
<img width="200" height="203" alt="image" src="https://github.com/user-attachments/assets/4c273b32-0596-4491-9d9d-00a2298d1774" /> <img width="274" height="199" alt="image" src="https://github.com/user-attachments/assets/066ea858-07a8-4793-b8b5-5e4a9bb10384" />


## Folder Structure

```
AI-and-Fly-Brains/
   - AI_datasets_collection/     # Scripts and tools for collecting and preparing annotated datasets
   - AI_training/                # YOLO training scripts
   - ArduinoSerial/              # Arduino sketch for PWM control
   - CameraTest/ArduinoTestCamExpert   # Test scripts for camera and Arduino integration
   - Icon/                       # UI assets: Background image, sidebar icon
   - mainwindow.py               # Main GUI window: experiment list, search, delete, navigation
   - add_experiment_window.py    # Add new experiment window: settings input, triggers full pipeline
   - arduino_ctrl.py             # Handles serial communication between Python and Arduino
```

## Running the software

```bash
python mainwindow.py
```

Make sure the Arduino is connected via USB, rig connect to power supply and the camera is connected via 2 of Camera Link (PoCL) before starting an experiment.
<p align="center">

</p>
## Acknowledgements

- **Project Supervisor:** Dr Kevin Webb — Optics & Photonics Research Group, University of Nottingham
- **Stakeholder:** Dr Isabella Maiellaro — Department of Neuroscience, University of Nottingham
