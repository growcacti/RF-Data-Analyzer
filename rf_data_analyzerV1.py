#!/usr/bin/env python3
"""RF Data Analyzer: CSV, Excel, and Touchstone data visualization."""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import pandas as pd
import numpy as np


APP_TITLE = "JhLabs RF Data Analyzer"
FREQUENCY_FACTORS = {"HZ": 1, "KHZ": 1e3, "MHZ": 1e6, "GHZ": 1e9}
#By JH Labs

def display_frequency(value: float) -> str:
    """Format a frequency in the most readable engineering unit."""
    value = float(value)
    for factor, unit in ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")):
        if abs(value) >= factor:
            return "{:.6g} {}".format(value / factor, unit)
    return "{:.6g} Hz".format(value)


def parse_touchstone(path: Path) -> pd.DataFrame:
    """Read a two-port Touchstone S-parameter file into engineering columns."""
    option = ["GHZ", "S", "MA", "R", "50"]
    values = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.split("!", 1)[0].strip()
        if not line:
            continue
        if line.startswith("#"):
            option = line[1:].upper().split()
            continue
        if line.startswith("["):
            continue
        values.extend(line.split())

    if len(option) < 3 or option[1] != "S":
        raise ValueError("Only Touchstone S-parameter files are supported.")
    frequency_factor = FREQUENCY_FACTORS.get(option[0], None)
    if frequency_factor is None:
        raise ValueError("Unknown Touchstone frequency unit: {}".format(option[0]))
    data_format = option[2]
    if data_format not in {"RI", "MA", "DB"}:
        raise ValueError("Unsupported Touchstone format: {}".format(data_format))
    if len(values) % 9:
        raise ValueError("This does not appear to be a valid two-port .s2p file.")

    rows = []
    for offset in range(0, len(values), 9):
        try:
            fields = [float(value.replace("D", "E").replace("d", "e")) for value in values[offset:offset + 9]]
        except ValueError as exc:
            raise ValueError("Touchstone data contains an invalid numeric value.") from exc
        frequency = fields[0] * frequency_factor
        pairs = [fields[1:3], fields[3:5], fields[5:7], fields[7:9]]
        row = {"Frequency (Hz)": frequency}
        # Touchstone order for a two-port file is S11, S21, S12, S22.
        for name, (first, second) in zip(("S11", "S21", "S12", "S22"), pairs):
            if data_format == "RI":
                magnitude = math.hypot(first, second)
                phase = math.degrees(math.atan2(second, first))
                db = 20 * math.log10(max(magnitude, 1e-300))
            elif data_format == "MA":
                magnitude, phase = first, second
                db = 20 * math.log10(max(magnitude, 1e-300))
            else:
                db, phase = first, second
                magnitude = 10 ** (db / 20)
            row[name + " Magnitude"] = magnitude
            row[name + " (dB)"] = db
            row[name + " Phase (deg)"] = phase
        gamma = row["S11 Magnitude"]
        row["Return Loss (dB)"] = -row["S11 (dB)"]
        row["VSWR"] = (1 + gamma) / max(1 - gamma, 1e-12)
        rows.append(row)
    frame = pd.DataFrame(rows)
    frequency = frame["Frequency (Hz)"].to_numpy(dtype=float)
    if len(frequency) > 1 and np.all(np.diff(frequency) > 0):
        for port in ("S11", "S21", "S12", "S22"):
            phase = np.unwrap(np.deg2rad(frame[port + " Phase (deg)"].to_numpy(dtype=float)))
            frame[port + " Group Delay (ns)"] = -np.gradient(phase, 2 * np.pi * frequency) * 1e9
    gamma = frame["S11 Magnitude"].to_numpy() * np.exp(1j * np.deg2rad(frame["S11 Phase (deg)"].to_numpy()))
    z0 = float(option[option.index("R") + 1]) if "R" in option and option.index("R") + 1 < len(option) else 50.0
    impedance = np.full(len(frame), np.nan + 1j * np.nan)
    valid = np.abs(1 - gamma) > 1e-12
    impedance[valid] = z0 * (1 + gamma[valid]) / (1 - gamma[valid])
    frame["S11 Input R (Ohms)"] = impedance.real
    frame["S11 Input X (Ohms)"] = impedance.imag
    return frame


def rtf_to_text(content: str) -> str:
    """Remove the RTF control stream while retaining the report's text."""
    content = re.sub(r"\\par[d]?\b", "\n", content, flags=re.IGNORECASE)
    content = re.sub(r"\\line\b", "\n", content, flags=re.IGNORECASE)
    content = re.sub(r"\\'[0-9a-fA-F]{2}", "", content)
    content = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", content)
    content = content.replace("\\{", "{").replace("\\}", "}").replace("\\\\", "\\")
    return re.sub(r"\n{3,}", "\n\n", content.replace("{", "").replace("}", ""))


def parse_test_report(path: Path) -> dict[str, pd.DataFrame]:
    """Extract common engineering test tables from legacy RTF or text reports."""
    text = rtf_to_text(path.read_text(encoding="cp1252", errors="replace"))
    tables = {}
    input_power = []
    output_power = []
    phase_noise = []
    sqe = []
    agc = []

    for line in text.splitlines():
        match = re.match(r"\s*(PZ|SX)/TB(\d)/(Low|Nom|Hi)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\w+)", line, re.I)
        if match:
            input_power.append(dict(zip(("Rail", "Time Base", "Condition", "PZ Voltage (V)", "PZ Current (A)", "SX Voltage (V)", "SX Current (A)", "Total Power (W)", "Limit (W)", "Result"), match.groups())))
            continue
        match = re.match(r"\s*(Nom|Hi|Low)\s+([\d.]+)\s+(TB\d\+?\s*[\d.]*)\s+([\d.]+)\s+([\d.]+)\s+(-?[\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\w+)", line, re.I)
        if match:
            output_power.append(dict(zip(("Condition", "Prime Power (V)", "Time", "Temperature (Ohms)", "Power FFT (V)", "Power Meter", "RF Power", "Min Limit", "Max Limit", "Result"), match.groups())))
            continue
        match = re.match(r"\s*TB\d\s*\+\s*([\d.-]+)\s+(-?[\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\w+)", line, re.I)
        if match:
            phase_noise.append(dict(zip(("Time Offset (ms)", "Phase Noise (dBc/Hz)", "Phase Noise (deg RMS)", "Limit", "Result"), match.groups())))
            continue
        match = re.match(r"\s*(?:NDS\s+Nav|SFM)\s+(-?[\d.]+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+(\w+)\s+(\w+)", line, re.I)
        if match:
            sqe.append(dict(zip(("RF Level (dBm)", "Epochs", "SQE Mean", "SQE Std Dev", "FSK Sync", "Result"), match.groups())))
            continue
        match = re.match(r"\s*(-?\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*$", line)
        if match:
            agc.append({"RF Level (dBm)": match.group(1), "AGC FFT (V)": match.group(2)})

    def add_table(name, records):
        if records:
            frame = pd.DataFrame(records)
            for column in frame.columns:
                converted = pd.to_numeric(frame[column], errors="coerce")
                if converted.notna().all():
                    frame[column] = converted
            tables[name] = frame

    add_table("Input Power", input_power)
    add_table("Logic Output Power", output_power)
    add_table("Phase Noise", phase_noise)
    add_table("SQE vs RF Level", sqe)
    add_table("AGC Curve", agc)
    tables["Report Text"] = pd.DataFrame({"Report Text": text.splitlines()})
    return tables


class RFDataAnalyzer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1250x800")
        self.minsize(980, 620)
        self.data = None
        self.file_path = None
        self.datasets = {}
        self.sheet_var = tk.StringVar()
        self.x_var = tk.StringVar()
        self.plot_var = tk.StringVar(value="Line")
        self.status_var = tk.StringVar(value="Open a CSV, Excel, or Touchstone .s2p file to begin.")
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        controls = ttk.Frame(self, padding=(10, 10, 10, 5))
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)
        ttk.Button(controls, text="Open Data File...", command=self.open_file).grid(row=0, column=0, sticky="w")
        ttk.Label(controls, textvariable=self.status_var).grid(row=0, column=1, sticky="w", padx=10)
        self.sheet_label = ttk.Label(controls, text="Dataset:")
        self.sheet_box = ttk.Combobox(controls, textvariable=self.sheet_var, state="readonly", width=20)
        self.sheet_box.bind("<<ComboboxSelected>>", lambda event: self.load_selected_dataset())

        main = ttk.PanedWindow(self, orient="horizontal")
        main.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        side = ttk.Frame(main, padding=6)
        view = ttk.Frame(main, padding=6)
        main.add(side, weight=1)
        main.add(view, weight=4)
        side.columnconfigure(0, weight=1)
        view.columnconfigure(0, weight=1)
        view.rowconfigure(0, weight=1)

        ttk.Label(side, text="Plot Settings", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(side, text="X axis:").grid(row=1, column=0, sticky="w", pady=(10, 2))
        self.x_box = ttk.Combobox(side, textvariable=self.x_var, state="readonly")
        self.x_box.grid(row=2, column=0, sticky="ew")
        ttk.Label(side, text="Y axis columns:").grid(row=3, column=0, sticky="w", pady=(10, 2))
        y_frame = ttk.Frame(side)
        y_frame.grid(row=4, column=0, sticky="nsew")
        side.rowconfigure(4, weight=1)
        self.y_list = tk.Listbox(y_frame, selectmode="extended", exportselection=False, height=14)
        y_scroll = ttk.Scrollbar(y_frame, orient="vertical", command=self.y_list.yview)
        self.y_list.configure(yscrollcommand=y_scroll.set)
        self.y_list.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        y_frame.columnconfigure(0, weight=1)
        y_frame.rowconfigure(0, weight=1)
        ttk.Label(side, text="Plot type:").grid(row=5, column=0, sticky="w", pady=(10, 2))
        ttk.Combobox(side, textvariable=self.plot_var, values=("Line", "Scatter", "Histogram"), state="readonly").grid(row=6, column=0, sticky="ew")
        buttons = ttk.Frame(side)
        buttons.grid(row=7, column=0, sticky="ew", pady=10)
        ttk.Button(buttons, text="Create Plot", command=self.create_plot).pack(side="left")
        ttk.Button(buttons, text="Save Plot...", command=self.save_plot).pack(side="left", padx=5)
        ttk.Button(side, text="Export Report to Excel...", command=self.export_to_excel).grid(row=8, column=0, sticky="ew")
        ttk.Button(side, text="Plot RF Overview", command=self.plot_rf_overview).grid(row=9, column=0, sticky="ew", pady=(5, 0))
        ttk.Button(side, text="Find Peaks (SciPy)", command=self.find_peaks).grid(row=10, column=0, sticky="ew", pady=(5, 0))
        ttk.Button(side, text="Smith Chart (scikit-rf)", command=self.plot_smith).grid(row=11, column=0, sticky="ew", pady=(5, 0))

        self.figure = Figure(figsize=(8, 6), dpi=100, constrained_layout=True)
        self.axes = self.figure.add_subplot(111)
        self.axes.set_title("Open data to create a plot")
        self.canvas = FigureCanvasTkAgg(self.figure, master=view)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        toolbar = NavigationToolbar2Tk(self.canvas, view, pack_toolbar=False)
        toolbar.update()
        toolbar.grid(row=1, column=0, sticky="ew")

        lower = ttk.PanedWindow(self, orient="horizontal")
        lower.grid(row=2, column=0, sticky="nsew", padx=10, pady=(5, 0))
        data_frame = ttk.Labelframe(lower, text="Data Preview", padding=5)
        analysis_frame = ttk.Labelframe(lower, text="Analysis", padding=5)
        lower.add(data_frame, weight=3)
        lower.add(analysis_frame, weight=2)
        self.preview = ScrolledText(data_frame, height=10, wrap="none", state="disabled", font=("Consolas", 9))
        self.preview.pack(fill="both", expand=True)
        self.analysis = ScrolledText(analysis_frame, height=10, wrap="word", state="disabled")
        self.analysis.pack(fill="both", expand=True)
        ttk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken", padding=(8, 3)).grid(row=3, column=0, sticky="ew")

    def open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("Supported data", "*.csv *.txt *.rtf *.xlsx *.xls *.s2p *.S2P"),
                ("CSV files", "*.csv *.txt"),
                ("Excel files", "*.xlsx *.xls"),
                ("Touchstone files", "*.s2p *.S2P"),
                ("Test reports", "*.rtf *.txt"),
                ("All files", "*.*"),
            ]
        )
        if not path:
            return
        try:
            self.file_path = Path(path)
            suffix = self.file_path.suffix.lower()
            self.datasets = {}
            self.sheet_label.grid_forget()
            self.sheet_box.grid_forget()
            if suffix in (".s2p",):
                self.data = parse_touchstone(self.file_path)
            elif suffix in (".xlsx", ".xls"):
                workbook = pd.ExcelFile(self.file_path)
                self.datasets = {name: pd.read_excel(self.file_path, sheet_name=name) for name in workbook.sheet_names}
                self.sheet_box["values"] = workbook.sheet_names
                self.sheet_var.set(workbook.sheet_names[0])
                self.sheet_label.grid(row=0, column=2, sticky="e")
                self.sheet_box.grid(row=0, column=3, sticky="e", padx=(5, 0))
                self.data = self.datasets[self.sheet_var.get()]
            else:
                with self.file_path.open("r", encoding="utf-8-sig", errors="replace", newline="") as source:
                    sample = source.read(8192)
                if sample.lstrip().startswith("{\\rtf"):
                    self.datasets = parse_test_report(self.file_path)
                    plot_tables = [name for name, frame in self.datasets.items() if not frame.select_dtypes(include="number").empty]
                    if not plot_tables:
                        raise ValueError("No numeric test tables were found in the report.")
                    self.sheet_box["values"] = plot_tables
                    self.sheet_var.set(plot_tables[0])
                    self.sheet_label.grid(row=0, column=2, sticky="e")
                    self.sheet_box.grid(row=0, column=3, sticky="e", padx=(5, 0))
                    self.data = self.datasets[self.sheet_var.get()]
                else:
                    try:
                        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                        self.data = pd.read_csv(self.file_path, sep=dialect.delimiter)
                    except csv.Error:
                        self.data = pd.read_csv(self.file_path)
            self.set_data()
        except Exception as exc:
            messagebox.showerror("Open Data", str(exc))

    def load_excel_sheet(self):
        self.load_selected_dataset()

    def load_selected_dataset(self):
        try:
            self.data = self.datasets[self.sheet_var.get()]
            self.set_data()
        except Exception as exc:
            messagebox.showerror("Excel Sheet", str(exc))

    def set_data(self):
        self.data = self.data.dropna(axis=1, how="all")
        if self.data.empty:
            raise ValueError("The selected data file has no rows.")
        numeric = list(self.data.select_dtypes(include="number").columns)
        if not numeric:
            raise ValueError("No numeric columns were found to plot.")
        columns = list(self.data.columns)
        self.x_box["values"] = columns
        frequency = next((str(column) for column in columns if "freq" in str(column).lower()), str(numeric[0]))
        self.x_var.set(frequency)
        self.y_list.delete(0, "end")
        for column in numeric:
            self.y_list.insert("end", column)
        default_y = [idx for idx, col in enumerate(numeric) if col != self.x_var.get()][:4]
        for idx in default_y:
            self.y_list.selection_set(idx)
        self.update_text(self.preview, self.data.head(20).to_string(index=False))
        self.update_text(self.analysis, self.build_analysis())
        self.status_var.set("Loaded {} rows and {} columns from {}.".format(len(self.data), len(columns), self.file_path.name))
        self.create_plot()

    def update_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def build_analysis(self):
        numeric = self.data.select_dtypes(include="number")
        lines = ["Rows: {}".format(len(self.data)), "Numeric columns: {}".format(len(numeric.columns))]
        freq_col = next((col for col in numeric.columns if "freq" in str(col).lower()), None)
        if freq_col is not None:
            lines += ["", "Frequency range:", "  {} to {}".format(display_frequency(numeric[freq_col].min()), display_frequency(numeric[freq_col].max()))]
        lines += ["", "Summary (numeric columns):"]
        for column in numeric.columns[:12]:
            series = numeric[column].dropna()
            lines.append("  {}: min {:.5g}, max {:.5g}, mean {:.5g}".format(column, series.min(), series.max(), series.mean()))
        if "Return Loss (dB)" in numeric:
            result = numeric["Return Loss (dB)"]
            lines += ["", "RF assessment:", "  Best return loss: {:.2f} dB".format(result.max()), "  Worst return loss: {:.2f} dB".format(result.min())]
        if "S21 (dB)" in numeric:
            result = numeric["S21 (dB)"]
            lines.append("  S21 range: {:.2f} to {:.2f} dB".format(result.min(), result.max()))
        return "\n".join(lines)

    def selected_y_columns(self):
        return [self.y_list.get(index) for index in self.y_list.curselection()]

    def create_plot(self):
        if self.data is None:
            return
        x_name = self.x_var.get()
        y_names = self.selected_y_columns()
        if not y_names:
            messagebox.showinfo("Plot", "Select at least one Y-axis column.")
            return
        self.axes.clear()
        plot_type = self.plot_var.get()
        if plot_type == "Histogram":
            for name in y_names:
                self.axes.hist(self.data[name].dropna(), bins=40, alpha=.55, label=name)
            self.axes.set_xlabel("Value")
        else:
            x = self.data[x_name]
            for name in y_names:
                if plot_type == "Scatter":
                    self.axes.scatter(x, self.data[name], s=12, label=name)
                else:
                    self.axes.plot(x, self.data[name], linewidth=1.5, label=name)
            self.axes.set_xlabel(x_name)
        self.axes.set_ylabel("Value")
        self.axes.set_title("{}: {}".format(plot_type, self.file_path.name if self.file_path else "Data"))
        self.axes.grid(True, alpha=.3)
        self.axes.legend(fontsize=8)
        self.canvas.draw_idle()

    def plot_rf_overview(self):
        if self.data is None:
            return
        frequency = next((column for column in self.data.columns if "freq" in str(column).lower()), None)
        candidates = [column for column in ("S11 (dB)", "S21 (dB)", "S12 (dB)", "S22 (dB)", "Return Loss (dB)") if column in self.data]
        if frequency is None or not candidates:
            messagebox.showinfo("RF Overview", "RF Overview needs a frequency column and S-parameter columns. Use a .s2p file or choose columns manually.")
            return
        self.x_var.set(frequency)
        self.y_list.selection_clear(0, "end")
        for index in range(self.y_list.size()):
            if self.y_list.get(index) in candidates:
                self.y_list.selection_set(index)
        self.plot_var.set("Line")
        self.create_plot()

    def find_peaks(self):
        if self.data is None:
            return
        try:
            from scipy.signal import find_peaks
        except ImportError:
            messagebox.showinfo("SciPy required", "Install with: python -m pip install scipy")
            return
        x_name = self.x_var.get()
        y_names = self.selected_y_columns()
        if not y_names:
            messagebox.showinfo("Find Peaks", "Select at least one numeric Y column.")
            return
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        lines = ["Peak analysis (prominence: 10% of each column's range):"]
        for name in y_names:
            if name == x_name:
                continue
            frame = self.data[[x_name, name]].apply(pd.to_numeric, errors="coerce").dropna()
            frame = frame.sort_values(x_name).drop_duplicates(subset=x_name)
            x, y = frame[x_name].to_numpy(), frame[name].to_numpy()
            if len(y) < 3:
                lines.append("{}: fewer than 3 usable samples".format(name))
                continue
            span = float(np.ptp(y))
            peaks, properties = find_peaks(y, prominence=max(span * .1, 1e-12))
            ax.plot(x, y, label=name)
            ax.plot(x[peaks], y[peaks], "x", markersize=8)
            lines.append("{}: {} peaks".format(name, len(peaks)))
            for idx in np.argsort(properties["prominences"])[::-1][:10]:
                peak = peaks[idx]
                lines.append("  x={:.7g}, y={:.7g}, prominence={:.5g}".format(x[peak], y[peak], properties["prominences"][idx]))
        ax.set(xlabel=x_name, ylabel="Value", title="Prominent peaks")
        ax.grid(True, alpha=.3)
        if ax.lines:
            ax.legend(fontsize=8)
        self.canvas.draw_idle()
        self.axes = ax
        self.update_text(self.analysis, "\n".join(lines))

    def plot_smith(self):
        if self.data is None:
            return
        try:
            import skrf
        except ImportError:
            messagebox.showinfo("scikit-rf required", "Install with: python -m pip install scikit-rf")
            return
        available = [port for port in ("S11", "S22") if port + " Magnitude" in self.data and port + " Phase (deg)" in self.data]
        if not available:
            messagebox.showinfo("Smith Chart", "Open a two-port .s2p file with S11 or S22 data.")
            return
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        for port in available:
            magnitude = pd.to_numeric(self.data[port + " Magnitude"], errors="coerce").to_numpy()
            phase = pd.to_numeric(self.data[port + " Phase (deg)"], errors="coerce").to_numpy()
            gamma = magnitude * np.exp(1j * np.deg2rad(phase))
            gamma = gamma[np.isfinite(gamma)]
            if len(gamma):
                skrf.plotting.plot_smith(gamma, ax=ax, label=port)
        ax.set_title("Reflection coefficients")
        ax.legend()
        self.axes = ax
        self.canvas.draw_idle()

    def save_plot(self):
        if self.data is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG image", "*.png"), ("PDF image", "*.pdf"), ("SVG image", "*.svg")])
        if path:
            try:
                self.figure.savefig(path, dpi=200, bbox_inches="tight")
                self.status_var.set("Saved plot to {}.".format(Path(path).name))
            except Exception as exc:
                messagebox.showerror("Save Plot", str(exc))

    def export_to_excel(self):
        if self.data is None:
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel workbook", "*.xlsx")])
        if not path:
            return
        try:
            tables = self.datasets or {"Data": self.data}
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                for name, table in tables.items():
                    table.to_excel(writer, sheet_name=re.sub(r"[\\/*?:\[\]]", "_", name)[:31], index=False)
            self.status_var.set("Exported {} dataset(s) to {}.".format(len(tables), Path(path).name))
        except Exception as exc:
            messagebox.showerror("Export to Excel", str(exc))


if __name__ == "__main__":
    RFDataAnalyzer().mainloop()
