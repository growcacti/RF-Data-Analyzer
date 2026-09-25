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

Test Report Automation
Open an RTF test report directly. The analyzer removes RTF formatting and detects common fixed-width report tables, including input power, logic output power, phase noise, SQE versus RF level, and AGC curves. Choose a parsed dataset from the Dataset selector, plot it, then select Export Report to Excel to generate a workbook with a worksheet for every extracted table plus the cleaned report text.

Batch Processing
Use process_data_sets.py to process a single file or every supported file in a folder. Each input creates a subfolder containing data.xlsx, analysis.txt, and PNG charts.

powershell python process_data_sets.py "C:\Test Data\incoming" --output "C:\Test Data\processed"

For a graphical workflow, run:

powershell python batch_processor_gui.py

The batch tool supports RTF test reports, CSV/text data, Excel workbooks, and Touchstone .s2p files. Failed files are listed in errors.txt without preventing the remaining files from being processed.

Live Profile Workbook
Create a live test log and chart dashboard from a profile template:

powershell python create_live_profile_workbook.py TestProfile.xlsx TestProfile_Live.xlsx

Enter a timestamp, ETM, temperature setpoint, actual temperature, and test state in the Live Log sheet. The Live Profile charts update from the expanded log range without manually copying values into a profile chart.
