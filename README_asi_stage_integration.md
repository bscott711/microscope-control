# Roadmap: ASI Stage Integration

## Overview

This document outlines the development roadmap and progress for integrating actual ASI stage hardware control into the napari stage control widget. The goal is to provide reliable, bidirectional control of an ASI stage's X-axis (initially) directly from a napari interface.

## Key Features & Improvements

- **Napari Widget:** User-friendly interface within napari for stage operations.
- **Bidirectional Step Movement:** Move the stage by defined increments.
- **Bidirectional Jog Movement:** Incrementally move the stage at a defined "speed" (currently implemented as small steps per click).
- **Live Position Display:** Continuously updated display of the current stage position.
- **ASI Hardware Integration:** Utilizes `pymmcore-plus` to communicate with and control physical ASI stages.
- **Mock Hardware Mode:** Allows testing and UI interaction without a connected physical stage.

## Progress Checklist

- [x] Basic widget UI and layout (`StageControlWidget`).
- [x] Placeholder stage control logic (`Stage` class initial version).
- [x] Unit tests for placeholder logic.
- [x] Integration of `pymmcore-plus` for ASI stage communication (X-axis).
- [x] Updated unit tests with comprehensive `pymmcore-plus` mocking.
- [ ] Manual hardware testing and feedback incorporation.
- [ ] (Future) Y-axis control / Combined XY control.
- [ ] (Future) True continuous jogging with hold-to-move (if required).
- [ ] (Future) Configuration of stage parameters (device labels, config file) via UI or settings file instead of code modification.
- [ ] (Future) Enhanced error handling and user feedback for hardware issues.
