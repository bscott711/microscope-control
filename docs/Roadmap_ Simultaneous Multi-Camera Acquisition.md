# **Roadmap: Simultaneous Multi-Camera Acquisition**

This document outlines the necessary steps to modify the microscope-control application to support simultaneous multi-camera acquisition using the Micro-Manager "Multi Camera" utility device.

## **Phase 1: Dynamic Camera Detection & Configuration**

**Objective:** Ensure the application's acquisition logic correctly uses the camera device currently selected in Micro-Manager, which could be a single physical camera or the "Multi Camera" utility device.  
**Files to Modify:** microscope/acquisition/worker.py, microscope/application/mda\_setup.py  
**Tasks:**

1. **Query Active Camera at Runtime:**  
   * The acquisition logic should not force a specific camera. Instead, at the beginning of each acquisition (in both the AcquisitionWorker and the MultiCameraWriter), the system must query mmcore.getCameraDevice() to identify the currently active camera.  
2. **Adapt Logic Based on Active Camera:**  
   * The AcquisitionWorker and MultiCameraWriter must be able to handle both single and multi-camera scenarios based on the device returned by getCameraDevice().  
   * **If a single camera is active:** The system should proceed with a standard single-stream acquisition and save to a single file.  
   * **If "Multi Camera" is active:** The system must switch to the multi-camera acquisition mode, adapting the image count calculation and image collection loop as detailed in Phase 2, and activating the multi-file saving logic from Phase 3\.  
3. **User Responsibility for Configuration:**  
   * The user remains responsible for ensuring the hardware configuration file (.cfg) is correctly set up. If they intend to use simultaneous acquisition, they must have the "Multi Camera" device configured with its physical cameras assigned. The application will then adapt to whichever camera they select as active.

### **Phase 2: Adapt the Acquisition Worker**

**Objective:** Modify the acquisition worker to correctly handle the multiple images that will be generated from a single trigger of the "Multi Camera" device.  
**File to Modify:** microscope/acquisition/worker.py  
**Tasks:**

1. **Update Image Count Calculation:**  
   * The total\_images\_expected calculation needs to be updated. It should be multiplied by the number of active physical cameras associated with the active camera device.  
   * The number of cameras can be determined at the start of the run method by querying the active camera device. If it's the "Multi Camera" device, query how many physical cameras are assigned to it. If it's a single camera, the count is 1\.  
2. **Revise Image Collection Loop:**  
   * The main loop in the run method currently assumes one image is generated per useq.MDAEvent. This needs to be changed.  
   * After triggering the acquisition, the loop should continuously check mmc.getRemainingImageCount().  
   * It should pop *all* available images from the buffer in an inner loop before advancing to the next useq event. This will handle the burst of images from all cameras that arrive after a single trigger.  
3. **Event and Metadata Association:**  
   * For each image popped from the buffer, it's crucial to associate it with the correct useq.MDAEvent.  
   * The TaggedImage metadata from popNextTaggedImage() will contain the name of the *physical* camera that acquired the image. This information is essential for the data saving phase.

### **Phase 3: Implement Multi-Camera Data Saving**

**Objective:** Create a custom data handler that can save the streams of images from multiple cameras into separate, clearly identified files.  
**File to Modify:** microscope/application/mda\_setup.py (and potentially a new file for the custom handler class).  
**Tasks:**

1. **Create a MultiCameraWriter Class:**  
   * Define a new handler class, for example, MultiCameraWriter. This class will manage multiple writer instances (e.g., one OMETiffWriter per camera).  
   * This can be in a new file within the application module or directly in mda\_setup.py.  
2. **Implement sequenceStarted Method:**  
   * In the sequenceStarted method of the MultiCameraWriter, determine the number and names of the physical cameras from the active camera device.  
   * For each camera, create a unique file path. A good convention is to append the camera's device label to the base filename provided by the user (e.g., my-experiment\_CameraA.ome.tif).  
   * Instantiate and store a separate file writer for each camera.  
3. **Implement frameReady Method:**  
   * The frameReady method will be called for each image that comes from the acquisition worker.  
   * Inside this method, inspect the frame's metadata to get the Camera name. This identifies the physical camera that captured the image.  
   * Use the camera name to look up the correct file writer instance and write the image data to the corresponding file.  
4. **Integrate the New Handler:**  
   * In the setup\_mda\_widget function within mda\_setup.py, replace the existing logic for creating OMETiffWriter or OMEZarrWriter with logic that instantiates your new MultiCameraWriter.

### **Phase 4: Validation and Testing**

**Objective:** Thoroughly test the new multi-camera acquisition pipeline to ensure it functions correctly and reliably.  
**Tasks:**

1. **Test Configuration:**  
   * Use a Micro-Manager configuration file with at least two demo cameras assigned to a "Multi Camera" device.  
2. **Run Test Acquisitions:**  
   * Perform a simple time-lapse acquisition.  
   * Perform a more complex acquisition involving a Z-stack and multiple time points.  
3. **Verify Outputs:**  
   * **File Creation:** Confirm that the correct number of output files are created (one for each physical camera).  
   * **File Naming:** Check that the files are named correctly, including the camera identifier.  
   * **Data Integrity:** Open the saved files and inspect the image data. Verify that the number of frames, Z-slices, and time points match the acquisition plan.  
   * **Metadata Correctness:** Check the metadata within the saved files to ensure that timestamps, Z-positions, and other parameters are accurate for each camera's data stream.  
   * **Application Stability:** Ensure the GUI remains responsive and that there are no crashes or hangs during or after the acquisition.
