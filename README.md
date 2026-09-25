RF Data Analyzer
A desktop Python application for reviewing and visualizing CSV, Excel, and Touchstone .s2p data.

Supported Data
CSV and delimited text files
Excel .xlsx and .xls workbooks, with selectable sheets
Two-port Touchstone .s2p files in RI, MA, and DB formats
Legacy RTF engineering test reports
Touchstone files are converted into frequency, S11/S21/S12/S22 magnitude, dB, and phase columns. The program also derives return loss and VSWR from S11.

Install and Run
powershell cd rf_data_analyzer python -m pip install -r requirements.txt python rf_data_analyzer.py

Use
Open a data file.
Choose the X axis and one or more Y columns.
Create line, scatter, or histogram plots; use the embedded toolbar to zoom and pan.
Use Plot RF Overview for S-parameter datasets.
Save plots as PNG, PDF, or SVG.
The Analysis pane reports numeric ranges, averages, frequency coverage, and key return-loss/S21 results when those fields are available.

