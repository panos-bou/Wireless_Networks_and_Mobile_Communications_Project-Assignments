# Wireless Networks and Mobile Communications (WNMC) - Project & Assignments

This repository contains the experimental networking assignments and the final Python-based TCP Client-Server project for the WNMC course at the Athens University of Economics and Business (AUEB).

## Project & Assignments Overview

* **Assignment 1:** Experimental measurements evaluating Wi-Fi channels (IEEE 802.11 standard), signal attenuation, and interference from neighboring networks. The analysis utilizes Wi-Fi Analyzer applications across different coverage areas to map signal strength against connection speeds.
* **Assignment 2:** Transport layer throughput analysis using TCP and UDP protocols. Network performance and bottleneck identification are evaluated utilizing the iPerf 3.0 tool between devices in various spatial configurations.
* **Assignment 3 (Final Project):** A custom Python-based TCP Client-Server architecture designed for the parallel downloading of 160 multimedia file segments (`.m4s`) over mixed network topologies.
    * **Server (`server.py`):** Binds to a specified host and port to serve directory files. It processes filename requests using security measures to prevent path traversal and transmits data using an 8-byte unsigned 64-bit integer size header followed by 4096-byte chunks.
    * **Client (`client.py`):** Utilizes a round-robin load-balancing approach, requesting a configurable ratio of files (`nA` files from Server A and `nB` files from Server B) to minimize total transfer time. Integrates automated network benchmarking by triggering `iperf3` via subprocesses. It parses the JSON output to capture simultaneous throughput metrics (bits per second sent/received) alongside the file transfer rates.
    * **Data Logging:** All experiment telemetry, including timestamps, spatial scenarios, transfer times, and iperf3 bandwidth data, is automatically appended to a CSV file for structured data analysis.

## Technologies & System Requirements
* **Programming Language:** Python (utilizing `socket`, `struct`, `subprocess`, `argparse`, and `csv` modules)
* **Networking & Telemetry:** iPerf 3.0 (specifically requiring JSON output support)
* **Signal Analysis:** Wi-Fi Analyzer

## Author
* **Panagiotis Bourazanas** - Department of Informatics, Athens University of Economics and Business (AUEB)
