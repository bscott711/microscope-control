# A professional-looking dark theme for the application.
STYLESHEET = """
QWidget {
    background-color: #2e2e2e;
    color: #e0e0e0;
    font-size: 10pt;
}
QMainWindow::separator {
    background-color: #444444;
    width: 2px;
    height: 2px;
}
QDockWidget {
    titlebar-close-icon: none;
    titlebar-float-icon: none;
}
QDockWidget::title {
    background-color: #444444;
    padding: 4px;
    border-radius: 4px;
}
QGroupBox {
    background-color: #383838;
    border: 1px solid #555555;
    border-radius: 5px;
    margin-top: 1ex;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 3px;
}
QPushButton {
    background-color: #555555;
    border: 1px solid #666666;
    padding: 5px;
    border-radius: 5px;
}
QPushButton:hover {
    background-color: #666666;
}
QPushButton:pressed {
    background-color: #4a4a4a;
}
QPushButton:disabled {
    background-color: #404040;
    color: #888888;
}
QLineEdit, QDoubleSpinBox, QSpinBox {
    background-color: #444444;
    border: 1px solid #555555;
    padding: 4px;
    border-radius: 3px;
}
QProgressBar {
    border: 1px solid #555;
    border-radius: 5px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #0078d7;
    width: 20px;
}
"""
