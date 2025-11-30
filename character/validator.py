import os
import json
import csv

class ValidationReport:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.ok = []

    def add_error(self, msg):
        self.errors.append(msg)

    def add_warning(self, msg):
        self.warnings.append(msg)

    def add_ok(self, msg):
        self.ok.append(msg)

    def to_dict(self):
        return {
            "errors": self.errors,
            "warnings": self.warnings,
            "ok": self.ok
        }


def validate_json(path, report, required_type=dict, default=None):
    if not os.path.exists(path):
        report.add_error(f"JSON file missing: {path}")
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, required_type):
            report.add_error(f"Invalid JSON structure in {path}")
            return default
        report.add_ok(f"Valid JSON: {path}")
        return data

    except Exception as e:
        report.add_error(f"JSON decode error in {path}: {e}")
        return default


def validate_csv(path, report):
    if not os.path.exists(path):
        report.add_error(f"CSV file missing: {path}")
        return []

    try:
        rows = []
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        report.add_ok(f"Valid CSV: {path}")
        return rows

    except Exception as e:
        report.add_error(f"CSV read error in {path}: {e}")
        return []


def validate_txt_block(path, report=None):
    # Wrappers seguros
    def log_error(msg):
        if report is not None:
            report.add_error(msg)

    def log_warning(msg):
        if report is not None:
            report.add_warning(msg)

    def log_ok(msg):
        if report is not None:
            report.add_ok(msg)

    # Archivo no existe
    if not os.path.exists(path):
        log_warning(f"TXT file missing: {path}")
        return []

    try:
        blocks = []
        temp = []

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip() == "":
                    if temp:
                        blocks.append(temp)
                        temp = []
                else:
                    temp.append(line.rstrip("\n"))

        if temp:
            blocks.append(temp)

        log_ok(f"Valid TXT: {path}")
        return blocks

    except Exception as e:
        log_error(f"TXT read error in {path}: {e}")
        return []
